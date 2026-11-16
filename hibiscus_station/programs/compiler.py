"""Blockly workspace JSON → :class:`~hibiscus_station.programs.schemas.ProgramAst` (§5, §12.4).

Section numbers refer to station-programs.md.

The compiler is pure: it never executes anything and never reads a store. It checks what can be told
from the document alone (block types, fields, inputs, variable types, the start block, busy loops,
``relax arm`` in loops) and reports everything else to the validator (``validator.py``) through
:class:`ProgramRefs`. Rules:

* the program is the stack under the single top-level ``hb_start`` block; other top-level stacks are
  ``unreachable`` warnings; zero or several ``hb_start`` blocks are errors;
* every AST node's ``id`` is the Blockly block id (live highlight, traces, issue markers). Nodes made
  up from one block (``hb_joint_compare`` → ``compare(joint_value, number)``) get ``<id>:<part>`` ids;
* an input holding a shadow block and no real block uses the shadow (Blockly semantics);
* any ``error`` issue makes ``ast`` ``None`` (the program is still saved).
"""

from __future__ import annotations

import math
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import TypeAdapter, ValidationError

from hibiscus_station.programs.blocks import CATALOG
from hibiscus_station.programs.schemas import (
    ITEM_ID_RE,
    KEY_RE,
    MOTION_KINDS,
    SIGNAL_NAME_RE,
    TRAJECTORY_ID_RE,
    BlockSpec,
    CheckIssue,
    CondExpr,
    IssueCode,
    OperatorButton,
    ProgramAst,
    ProgramRefs,
    Stmt,
    ValueExpr,
    VarDecl,
)

SPECS: dict[str, BlockSpec] = {b.type: b for b in CATALOG.blocks}
START = "hb_start"
LOOP_TYPES = frozenset({"hb_repeat_forever", "controls_repeat_ext", "controls_whileUntil"})
#: Statements that hand the runner thread over to time (a loop containing one is never busy).
YIELDING_KINDS = MOTION_KINDS | {"wait", "wait_until", "ask"}
#: Blocks nested in blocks (statement bodies, value inputs). Blockly programs stay far below this; a
#: deeper document would exhaust the compiler's, the interpreter's or pydantic's recursion limits.
MAX_NESTING = 32

Severity = Literal["error", "warning", "confirm"]
ValueType = Literal["number", "text", "any"]

_STMT: TypeAdapter[Any] = TypeAdapter(Stmt)
_VALUE: TypeAdapter[Any] = TypeAdapter(ValueExpr)
_COND: TypeAdapter[Any] = TypeAdapter(CondExpr)

ARITH_OPS = {"ADD": "add", "MINUS": "sub", "MULTIPLY": "mul", "DIVIDE": "div", "POWER": "pow"}
COMPARE_OPS = {"EQ": "eq", "NEQ": "ne", "LT": "lt", "LTE": "le", "GT": "gt", "GTE": "ge"}


def issue(code: IssueCode, severity: Severity, block_id: str | None, **params: Any) -> CheckIssue:
    return CheckIssue(
        id=f"{code}:{block_id or '-'}",
        code=code,
        severity=severity,
        block_id=block_id,
        message_key=f"programs.issues.{code}",
        params=params,
    )


@dataclass
class CompileResult:
    ast: ProgramAst | None
    issues: list[CheckIssue]
    refs: ProgramRefs
    blocks: int = 0

    @property
    def ok(self) -> bool:
        return self.ast is not None and not any(i.severity == "error" for i in self.issues)


@dataclass
class _Var:
    id: str
    name: str
    type: Literal["number", "text"]


@dataclass
class _Ctx:
    buttons: set[str]
    variables: dict[str, _Var]
    issues: list[CheckIssue] = field(default_factory=list)
    keys: set[str] = field(default_factory=set)
    refs: dict[str, set[str]] = field(default_factory=lambda: {k: set() for k in ProgramRefs.model_fields})
    seen_issue_ids: set[str] = field(default_factory=set)

    def add(self, code: IssueCode, severity: Severity, block_id: str | None, **params: Any) -> None:
        i = issue(code, severity, block_id, **params)
        if i.id not in self.seen_issue_ids:
            self.seen_issue_ids.add(i.id)
            self.issues.append(i)


class _BadBlockError(Exception):
    """This block cannot be compiled (an issue was recorded)."""


# =========================================================================== helpers on raw JSON
def _obj(v: Any) -> dict[str, Any]:
    return v if isinstance(v, dict) else {}


def _input_block(b: dict[str, Any], name: str) -> dict[str, Any] | None:
    inp = _obj(_obj(b.get("inputs")).get(name))
    blk = inp.get("block") or inp.get("shadow")
    return blk if isinstance(blk, dict) else None


def _next(b: dict[str, Any]) -> dict[str, Any] | None:
    nxt = _obj(b.get("next"))
    blk = nxt.get("block")
    return blk if isinstance(blk, dict) else None


def _bid(b: dict[str, Any]) -> str:
    v = b.get("id")
    return v if isinstance(v, str) and v else "?"


def scan(tops: list[dict[str, Any]]) -> tuple[int, int]:
    """``(blocks, nesting)`` of a workspace, without recursion: the number of blocks (inputs and
    ``next`` chains) and the deepest nesting of a block in another block's input (a ``next`` chain
    stays at the same level)."""
    count = 0
    deepest = 0
    todo: list[tuple[dict[str, Any], int]] = [(t, 0) for t in tops]
    while todo:
        b, level = todo.pop()
        count += 1
        deepest = max(deepest, level)
        for inp in _obj(b.get("inputs")).values():
            blk = _obj(inp).get("block") or _obj(inp).get("shadow")
            if isinstance(blk, dict):
                todo.append((blk, level + 1))
        nxt = _next(b)
        if nxt is not None:
            todo.append((nxt, level))
    return count, deepest


# =========================================================================== the compiler
class _Compiler:
    def __init__(self, ctx: _Ctx, wait_timeout_s: float) -> None:
        self.ctx = ctx
        self.wait_timeout_s = wait_timeout_s
        self.loop_depth = 0

    # ---------------------------------------------------------------- fields
    def _field(self, b: dict[str, Any], name: str) -> Any:
        return _obj(b.get("fields")).get(name)

    def _spec_field(self, b: dict[str, Any], name: str) -> Any:
        spec = SPECS[b["type"]]
        return next((f for f in spec.fields if f.name == name), None)

    def number(self, b: dict[str, Any], name: str, *, optional: bool = False) -> float | None:
        raw = self._field(b, name)
        f = self._spec_field(b, name)
        if raw is None or raw == "":
            if f is not None and f.default is not None and not isinstance(f.default, bool) and not optional:
                return float(f.default)
            if optional:
                return None
            self.ctx.add("bad_field", "error", _bid(b), field=name, reason="missing")
            raise _BadBlockError
        try:
            v = float(raw)
        except (TypeError, ValueError):
            self.ctx.add(
                "bad_field", "error", _bid(b), field=name, reason="not a number", value=str(raw)[:40]
            )
            raise _BadBlockError from None
        lo = f.min if f is not None else None
        hi = f.max if f is not None else None
        if not math.isfinite(v) or (lo is not None and v < lo) or (hi is not None and v > hi):
            self.ctx.add("bad_field", "error", _bid(b), field=name, value=v, min=lo, max=hi)
            raise _BadBlockError
        return v

    def text(self, b: dict[str, Any], name: str, *, optional: bool = False, max_len: int = 500) -> str | None:
        raw = self._field(b, name)
        if raw is None or (isinstance(raw, str) and raw.strip() == ""):
            if optional:
                return None
            self.ctx.add("bad_field", "error", _bid(b), field=name, reason="missing")
            raise _BadBlockError
        if isinstance(raw, bool) or not isinstance(raw, str | int | float):
            self.ctx.add("bad_field", "error", _bid(b), field=name, reason="not a text")
            raise _BadBlockError
        s = str(raw)
        if len(s) > max_len:
            self.ctx.add("bad_field", "error", _bid(b), field=name, reason="too long", max=max_len)
            raise _BadBlockError
        return s

    def option(self, b: dict[str, Any], name: str) -> str:
        f = self._spec_field(b, name)
        raw = self._field(b, name)
        if (raw is None or raw == "") and f is not None and isinstance(f.default, str):
            raw = f.default
        options = f.options if f is not None else None
        if not isinstance(raw, str) or (options is not None and raw not in options):
            self.ctx.add("bad_field", "error", _bid(b), field=name, value=str(raw)[:40], options=options)
            raise _BadBlockError
        return raw

    def ref(
        self, b: dict[str, Any], name: str, pattern: Any, what: str, *, optional: bool = False
    ) -> str | None:
        s = self.text(b, name, optional=optional, max_len=200)
        if s is None:
            return None
        if pattern is not None and not pattern.fullmatch(s):
            self.ctx.add("bad_field", "error", _bid(b), field=name, value=s[:40], reason=f"bad {what} id")
            raise _BadBlockError
        return s

    def variable(self, b: dict[str, Any], name: str = "VAR") -> _Var:
        raw = self._field(b, name)
        vid = raw.get("id") if isinstance(raw, dict) else raw
        var = None
        if isinstance(vid, str):
            var = self.ctx.variables.get(vid) or next(
                (v for v in self.ctx.variables.values() if v.name == vid), None
            )
        if var is None:
            self.ctx.add("unknown_variable", "error", _bid(b), variable=str(vid)[:40] if vid else None)
            raise _BadBlockError
        return var

    # ---------------------------------------------------------------- inputs
    def _required(self, b: dict[str, Any], name: str) -> dict[str, Any]:
        blk = _input_block(b, name)
        if blk is None:
            self.ctx.add("missing_input", "error", _bid(b), input=name)
            raise _BadBlockError
        return blk

    def value_input(self, b: dict[str, Any], name: str, want: ValueType) -> dict[str, Any]:
        node, _ = self.value(self._required(b, name), want)
        return node

    def cond_input(self, b: dict[str, Any], name: str) -> dict[str, Any]:
        return self.cond(self._required(b, name))

    def stmts_input(self, b: dict[str, Any], name: str) -> list[dict[str, Any]]:
        return self.stack(_input_block(b, name))

    # ---------------------------------------------------------------- statements
    def stack(self, b: dict[str, Any] | None) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        depth = 0
        while b is not None:
            depth += 1
            if depth > 20000:  # pragma: no cover - max_blocks stops this first
                break
            node = self.stmt(b)
            if node is not None:
                out.append(node)
            b = _next(b)
        return out

    def _known(self, b: dict[str, Any], output: str | tuple[str, ...]) -> BlockSpec | None:
        t = b.get("type")
        spec = SPECS.get(t) if isinstance(t, str) else None
        if spec is None or spec.type == START:
            self.ctx.add("unknown_block", "error", _bid(b), type=str(t)[:60])
            return None
        outs = (output,) if isinstance(output, str) else output
        if spec.output not in outs:
            self.ctx.add(
                "type_mismatch", "error", _bid(b), type=spec.type, expected=list(outs), got=spec.output
            )
            return None
        return spec

    def stmt(self, b: dict[str, Any]) -> dict[str, Any] | None:
        spec = self._known(b, "statement")
        if spec is None:
            return None
        try:
            return self._stmt(b, spec)
        except _BadBlockError:
            return None

    def _stmt(self, b: dict[str, Any], spec: BlockSpec) -> dict[str, Any]:
        bid = _bid(b)
        t = spec.type
        base: dict[str, Any] = {"id": bid, "kind": spec.ast}
        if t == "hb_play_trajectory":
            tr = self.ref(b, "TRAJECTORY", TRAJECTORY_ID_RE, "trajectory")
            tr = _must(tr)
            self.ctx.refs["trajectories"].add(tr)
            return {**base, "trajectory": tr, "speed_pct": self.number(b, "SPEED")}
        if t == "hb_move_to_pose":
            pose = self.ref(b, "POSE", ITEM_ID_RE, "pose")
            pose = _must(pose)
            self.ctx.refs["poses"].add(pose)
            return {**base, "pose": pose, "speed_deg_s": self.number(b, "SPEED")}
        if t == "hb_gripper":
            action = self.option(b, "ACTION")
            pct = self.number(b, "PERCENT", optional=True)
            if action == "set" and pct is None:
                self.ctx.add("bad_field", "error", bid, field="PERCENT", reason="missing")
                raise _BadBlockError
            return {**base, "action": action, "percent": pct if action == "set" else None}
        if t in ("hb_go_home",):
            return base
        if t == "hb_relax_arm":
            if self.loop_depth > 0:
                self.ctx.add("relax_in_loop", "confirm", bid)
            return base
        if t in ("hb_run_model_for", "hb_run_model_until"):
            model = self.text(b, "MODEL", max_len=200)
            model = _must(model)
            self.ctx.refs["models"].add(model)
            task = self.text(b, "TASK", optional=True) or ""
            if t == "hb_run_model_for":
                return {**base, "model": model, "task": task, "duration_s": self.number(b, "SECONDS")}
            until = self.cond_input(b, "UNTIL")
            timeout = self.number(b, "TIMEOUT", optional=True)
            on_timeout = self.stmts_input(b, "ON_TIMEOUT") if _input_block(b, "ON_TIMEOUT") else None
            return {
                **base,
                "model": model,
                "task": task,
                "until": until,
                "timeout_s": timeout,
                "on_timeout": on_timeout,
            }
        if t == "controls_if":
            extra = _obj(b.get("extraState"))
            n_elif = extra.get("elseIfCount", 0)
            n_elif = n_elif if isinstance(n_elif, int) and 0 <= n_elif <= 64 else 0
            branches = []
            for k in range(n_elif + 1):
                branches.append({"cond": self.cond_input(b, f"IF{k}"), "body": self.stmts_input(b, f"DO{k}")})
            has_else = bool(extra.get("hasElse")) or _input_block(b, "ELSE") is not None
            return {
                **base,
                "branches": branches,
                "else_body": self.stmts_input(b, "ELSE") if has_else else None,
            }
        if t in LOOP_TYPES:
            self.loop_depth += 1
            try:
                body = self.stmts_input(b, "DO")
            finally:
                self.loop_depth -= 1
            if t == "controls_repeat_ext":
                return {**base, "times": self.value_input(b, "TIMES", "number"), "body": body}
            if t == "hb_repeat_forever":
                if not _yields(body):
                    self.ctx.add("busy_loop", "error", bid)
                return {**base, "body": body}
            mode = self.option(b, "MODE").lower()
            cond = self.cond_input(b, "BOOL")
            if not _yields(body) and _constant(cond) == (mode == "while"):
                self.ctx.add("busy_loop", "error", bid)
            return {**base, "mode": mode, "cond": cond, "body": body}
        if t == "hb_wait":
            return {**base, "seconds": self.value_input(b, "SECONDS", "number")}
        if t == "hb_wait_until":
            timeout = self.number(b, "TIMEOUT", optional=True)
            on_timeout = self.stmts_input(b, "ON_TIMEOUT") if _input_block(b, "ON_TIMEOUT") else None
            return {
                **base,
                "cond": self.cond_input(b, "COND"),
                "timeout_s": timeout if timeout is not None else self.wait_timeout_s,
                "on_timeout": on_timeout,
            }
        if t == "hb_stop_program":
            return base
        if t == "variables_set":
            var = self.variable(b)
            value, vt = self.value(self._required(b, "VALUE"), "any")
            if var.type == "number" and vt == "text":
                self.ctx.add("type_mismatch", "error", bid, variable=var.name, expected="number", got="text")
                raise _BadBlockError
            return {**base, "name": var.name, "value": value}
        if t == "math_change":
            var = self.variable(b)
            if var.type != "number":
                self.ctx.add("type_mismatch", "error", bid, variable=var.name, expected="number", got="text")
                raise _BadBlockError
            return {**base, "name": var.name, "by": self.value_input(b, "DELTA", "number")}
        if t == "hb_ask_operator":
            question = self.text(b, "QUESTION", max_len=200)
            raw = self.text(b, "CHOICES", max_len=1000) or ""
            choices = list(dict.fromkeys(c.strip() for c in raw.split(",") if c.strip()))
            if not 1 <= len(choices) <= 8 or any(len(c) > 80 for c in choices):
                self.ctx.add("bad_field", "error", bid, field="CHOICES", reason="1-8 choices")
                raise _BadBlockError
            var = self.variable(b)
            if var.type != "text":
                self.ctx.add("type_mismatch", "error", bid, variable=var.name, expected="text", got="number")
                raise _BadBlockError
            return {
                **base,
                "question": question,
                "choices": choices,
                "var": var.name,
                "timeout_s": self.number(b, "TIMEOUT", optional=True),
            }
        if t == "hb_log":
            return {**base, "text": self.value_input(b, "TEXT", "any")}
        if t == "hb_notify":
            webhook = self._field(b, "WEBHOOK")
            on = webhook is True or (isinstance(webhook, str) and webhook.upper() == "TRUE")
            return {**base, "text": self.value_input(b, "TEXT", "any"), "webhook": on}
        if t == "hb_set_signal":
            name = self.ref(b, "NAME", SIGNAL_NAME_RE, "signal")
            name = _must(name)
            self.ctx.refs["signals"].add(name)
            return {**base, "name": name, "value": self.value_input(b, "VALUE", "any")}
        self.ctx.add("unknown_block", "error", bid, type=t)  # pragma: no cover - catalogue drift
        raise _BadBlockError

    # ---------------------------------------------------------------- values
    def value(self, b: dict[str, Any], want: ValueType) -> tuple[dict[str, Any], ValueType]:
        spec = self._known(b, ("number", "text"))
        if spec is None:
            raise _BadBlockError
        node, got = self._value(b, spec)
        if want != "any" and got != "any" and got != want:
            self.ctx.add("type_mismatch", "error", _bid(b), expected=want, got=got)
            raise _BadBlockError
        return node, got

    def _value(self, b: dict[str, Any], spec: BlockSpec) -> tuple[dict[str, Any], ValueType]:
        bid = _bid(b)
        t = spec.type
        base: dict[str, Any] = {"id": bid, "kind": spec.ast}
        if t == "math_number":
            v = self.number(b, "NUM")
            return {**base, "value": v}, "number"
        if t == "text":
            raw = self._field(b, "TEXT")
            s = "" if raw is None else str(raw)
            if len(s) > 500:
                self.ctx.add("bad_field", "error", bid, field="TEXT", reason="too long", max=500)
                raise _BadBlockError
            return {**base, "value": s}, "text"
        if t == "variables_get":
            var = self.variable(b)
            return {**base, "name": var.name}, var.type
        if t == "math_arithmetic":
            op = ARITH_OPS[self.option(b, "OP")]
            return {
                **base,
                "op": op,
                "left": self.value_input(b, "A", "number"),
                "right": self.value_input(b, "B", "number"),
            }, "number"
        if t == "math_modulo":
            return {
                **base,
                "op": "mod",
                "left": self.value_input(b, "DIVIDEND", "number"),
                "right": self.value_input(b, "DIVISOR", "number"),
            }, "number"
        if t == "math_random_int":
            return {
                **base,
                "low": self.value_input(b, "FROM", "number"),
                "high": self.value_input(b, "TO", "number"),
            }, "number"
        if t == "text_join":
            n = _obj(b.get("extraState")).get("itemCount", 2)
            n = n if isinstance(n, int) and 0 <= n <= 64 else 2
            parts = []
            for k in range(n):
                blk = _input_block(b, f"ADD{k}")
                if blk is not None:
                    parts.append(self.value(blk, "any")[0])
            return {**base, "parts": parts}, "text"
        if t == "hb_joint_value":
            return {**base, "joint": self._joint(b, "JOINT")}, "number"
        if t == "hb_motor_temp":
            return {**base, "motor": self._motor(b)}, "number"
        if t == "hb_detector_confidence":
            det = self._detector(b)
            label = self.text(b, "LABEL", optional=True, max_len=64)
            return {**base, "detector": det, "camera": self._camera(b), "label": label}, "number"
        if t == "hb_signal_value":
            name = self.ref(b, "NAME", SIGNAL_NAME_RE, "signal")
            name = _must(name)
            self.ctx.refs["signals"].add(name)
            return {**base, "name": name}, "any"
        self.ctx.add("unknown_block", "error", bid, type=t)  # pragma: no cover - catalogue drift
        raise _BadBlockError

    def _joint(self, b: dict[str, Any], name: str) -> str:
        j = self.text(b, name, max_len=64)
        j = _must(j)
        return j.removesuffix(".pos")

    def _motor(self, b: dict[str, Any]) -> str | None:
        m = self.text(b, "MOTOR", optional=True, max_len=64)
        return None if m is None or m == "any" else m.removesuffix(".pos")

    def _detector(self, b: dict[str, Any]) -> str:
        det = self.ref(b, "DETECTOR", ITEM_ID_RE, "detector")
        det = _must(det)
        self.ctx.refs["detectors"].add(det)
        return det

    def _camera(self, b: dict[str, Any]) -> str | None:
        cam = self.text(b, "CAMERA", optional=True, max_len=64)
        if cam is not None:
            self.ctx.refs["cameras"].add(cam)
        return cam

    # ---------------------------------------------------------------- conditions
    def cond(self, b: dict[str, Any]) -> dict[str, Any]:
        spec = self._known(b, "boolean")
        if spec is None:
            raise _BadBlockError
        return self._cond(b, spec)

    def _cond(self, b: dict[str, Any], spec: BlockSpec) -> dict[str, Any]:
        bid = _bid(b)
        t = spec.type
        base: dict[str, Any] = {"id": bid, "kind": spec.ast}
        if t == "logic_operation":
            op = self.option(b, "OP").lower()
            return {**base, "op": op, "left": self.cond_input(b, "A"), "right": self.cond_input(b, "B")}
        if t == "logic_negate":
            return {**base, "operand": self.cond_input(b, "BOOL")}
        if t == "logic_boolean":
            return {**base, "value": self.option(b, "BOOL") == "TRUE"}
        if t == "logic_compare":
            op = COMPARE_OPS[self.option(b, "OP")]
            left, lt = self.value(self._required(b, "A"), "any")
            right, rt = self.value(self._required(b, "B"), "any")
            if op not in ("eq", "ne") and "text" in (lt, rt):
                self.ctx.add("type_mismatch", "error", bid, expected="number", got="text")
                raise _BadBlockError
            return {**base, "op": op, "left": left, "right": right}
        if t == "hb_camera_sees":
            det = self._detector(b)
            label = self.text(b, "LABEL", max_len=64)
            return {**base, "detector": det, "camera": self._camera(b), "label": label}
        if t == "hb_button_pressed":
            button = self.ref(b, "BUTTON", ITEM_ID_RE, "button")
            if button not in self.ctx.buttons:
                self.ctx.add("unknown_button", "error", bid, button=button)
                raise _BadBlockError
            return {**base, "button": button}
        if t == "hb_key_pressed":
            key = (self.text(b, "KEY", max_len=1) or "").lower()
            if not KEY_RE.fullmatch(key):
                self.ctx.add("bad_field", "error", bid, field="KEY", value=key, reason="keys are 0-9 and a-z")
                raise _BadBlockError
            self.ctx.keys.add(key)
            return {**base, "key": key}
        if t == "hb_gripper_holding":
            return base
        if t == "hb_joint_compare":
            op = COMPARE_OPS[self.option(b, "OP")]
            return {
                **base,
                "op": op,
                "left": {"id": f"{bid}:joint", "kind": "joint_value", "joint": self._joint(b, "JOINT")},
                "right": {"id": f"{bid}:deg", "kind": "number", "value": self.number(b, "DEG")},
            }
        if t == "hb_near_pose":
            pose = self.ref(b, "POSE", ITEM_ID_RE, "pose")
            pose = _must(pose)
            self.ctx.refs["poses"].add(pose)
            return {**base, "pose": pose, "tolerance_deg": self.number(b, "TOLERANCE")}
        if t == "hb_motor_temp_compare":
            op = COMPARE_OPS[self.option(b, "OP")]
            return {
                **base,
                "op": op,
                "left": {"id": f"{bid}:motor", "kind": "motor_temp", "motor": self._motor(b)},
                "right": {"id": f"{bid}:temp", "kind": "number", "value": self.number(b, "TEMP")},
            }
        if t == "hb_signal_equals":
            name = self.ref(b, "NAME", SIGNAL_NAME_RE, "signal")
            name = _must(name)
            self.ctx.refs["signals"].add(name)
            raw = self._field(b, "VALUE")
            return {**base, "name": name, "value": _scalar(raw)}
        if t == "hb_message_received":
            source = self.option(b, "SOURCE")
            name = self.text(b, "NAME", max_len=200)
            if source == "http" and name is not None and not SIGNAL_NAME_RE.fullmatch(name):
                self.ctx.add(
                    "bad_field", "error", bid, field="NAME", value=name[:40], reason="bad signal name"
                )
                raise _BadBlockError
            if name is not None:
                self.ctx.refs["signals"].add(name.replace("/", "."))
            return {**base, "source": source, "name": name}
        self.ctx.add("unknown_block", "error", bid, type=t)  # pragma: no cover - catalogue drift
        raise _BadBlockError


def _must(v: str | None) -> str:
    """A required field (``text``/``ref`` already recorded the issue when it was missing)."""
    if v is None:  # pragma: no cover - text()/ref() raise first for required fields
        raise _BadBlockError
    return v


def _scalar(raw: Any) -> float | str:
    """``hb_signal_equals`` VALUE: numeric text compares as a number (booleans arrive as 1/0)."""
    if isinstance(raw, bool):
        return 1.0 if raw else 0.0
    if isinstance(raw, int | float):
        return float(raw)
    s = "" if raw is None else str(raw)[:500]
    try:
        f = float(s)
    except ValueError:
        return s
    return f if math.isfinite(f) else s


def _yields(body: list[dict[str, Any]]) -> bool:
    """True when some statement in ``body`` (at any depth) waits or moves."""
    for s in body:
        if s.get("kind") in YIELDING_KINDS:
            return True
        for key in ("body", "else_body", "on_timeout"):
            sub = s.get(key)
            if isinstance(sub, list) and _yields(sub):
                return True
        for br in s.get("branches") or []:
            if _yields(br.get("body") or []):
                return True
    return False


def _constant(cond: dict[str, Any]) -> bool | None:
    """The value of a condition that is a literal (``while true``), else ``None``."""
    if cond.get("kind") == "bool":
        return bool(cond.get("value"))
    return None


def _variables(editor: dict[str, Any], ctx_issues: list[CheckIssue]) -> dict[str, _Var]:
    out: dict[str, _Var] = {}
    names: set[str] = set()
    for raw in editor.get("variables") or []:
        v = _obj(raw)
        vid, name, typ = v.get("id"), v.get("name"), v.get("type") or ""
        if not isinstance(vid, str) or not isinstance(name, str) or not 1 <= len(name) <= 40:
            continue
        if name in names:
            continue
        names.add(name)
        out[vid] = _Var(vid, name, "text" if typ == "String" else "number")
    return out


def compile_program(
    editor: dict[str, Any],
    buttons: list[OperatorButton] | None = None,
    *,
    max_blocks: int = 2000,
    wait_timeout_s: float = 30.0,
) -> CompileResult:
    """Compile a Blockly workspace (``Blockly.serialization.workspaces.save()``)."""
    buttons = list(buttons or [])
    issues: list[CheckIssue] = []
    variables = _variables(editor, issues)
    ctx = _Ctx(buttons={b.name for b in buttons}, variables=variables, issues=issues)
    tops = [b for b in (_obj(editor.get("blocks")).get("blocks") or []) if isinstance(b, dict)]
    count, nesting = scan(tops)
    refs_empty = ProgramRefs(trajectories=[], poses=[], detectors=[], models=[], signals=[], cameras=[])
    if count > max_blocks:
        ctx.add("too_many_blocks", "error", None, blocks=count, max=max_blocks)
        return CompileResult(None, ctx.issues, refs_empty, count)
    if nesting > MAX_NESTING:
        ctx.add("too_many_blocks", "error", None, nesting=nesting, max_nesting=MAX_NESTING)
        return CompileResult(None, ctx.issues, refs_empty, count)
    starts = [b for b in tops if b.get("type") == START]
    if not starts:
        ctx.add("no_start_block", "error", None)
    for extra in starts[1:]:
        ctx.add("many_start_blocks", "error", _bid(extra))
    for top in tops:
        if top.get("type") != START and starts:
            ctx.add("unreachable", "warning", _bid(top))
    comp = _Compiler(ctx, wait_timeout_s)
    body: list[dict[str, Any]] = []
    if starts:
        body = comp.stack(_input_block(starts[0], "DO"))
    refs = ProgramRefs(**{k: sorted(v) for k, v in ctx.refs.items()})
    ast: ProgramAst | None = None
    if not any(i.severity == "error" for i in ctx.issues):
        try:
            ast = ProgramAst(
                variables=[
                    VarDecl(name=v.name, type=v.type, initial=0.0 if v.type == "number" else "")
                    for v in variables.values()
                ],
                buttons=buttons,
                keys=sorted(ctx.keys),
                body=[_STMT.validate_python(s) for s in body],
            )
        except ValidationError as exc:  # a value outside the AST's own bounds
            errs = exc.errors()
            ctx.add("bad_field", "error", None, reason=(errs[0]["msg"] if errs else "invalid")[:200])
            ast = None
    return CompileResult(ast, ctx.issues, refs, count)


def iter_stmts(body: list[Stmt]) -> Iterator[tuple[Stmt, int]]:
    """Every statement of an AST body (depth first, in program order) with its loop depth."""

    def go(stmts: list[Stmt], loops: int) -> Iterator[tuple[Stmt, int]]:
        for s in stmts:
            yield s, loops
            inner = loops + (1 if s.kind in ("repeat", "forever", "while") else 0)
            if s.kind == "if":
                for br in s.branches:
                    yield from go(br.body, inner)
                if s.else_body:
                    yield from go(s.else_body, inner)
            for key in ("body", "on_timeout"):
                sub = getattr(s, key, None)
                if isinstance(sub, list):
                    yield from go(sub, inner)

    yield from go(body, 0)


def iter_exprs(body: list[Stmt]) -> Iterator[Any]:
    """Every condition and value node of an AST body (for the validator's reference checks)."""

    def expr(e: Any) -> Iterator[Any]:
        yield e
        for key in ("operand", "left", "right", "low", "high"):
            sub = getattr(e, key, None)
            if sub is not None and hasattr(sub, "kind"):
                yield from expr(sub)
        for p in getattr(e, "parts", None) or []:
            yield from expr(p)

    for s, _ in iter_stmts(body):
        for key in ("cond", "until", "times", "seconds", "value", "by", "text"):
            sub = getattr(s, key, None)
            if sub is not None and hasattr(sub, "kind"):
                yield from expr(sub)
        if s.kind == "if":
            for br in s.branches:
                yield from expr(br.cond)
