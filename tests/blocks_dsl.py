"""Build Blockly workspace JSON (``Blockly.serialization.workspaces.save()``) for tests.

Shapes follow programs/blocks.py and the editor (web/src/station/programs/blockly/serialize.ts): fields are
plain values, a variable field is ``{"id": ...}``, inputs are ``{"block": ...}`` (or ``shadow``),
statements chain through ``next``.
"""

from __future__ import annotations

import itertools
from typing import Any

Block = dict[str, Any]
_ids = itertools.count(1)


def blk(
    type_: str,
    id_: str | None = None,
    *,
    fields: dict[str, Any] | None = None,
    inputs: dict[str, Block | None] | None = None,
    extra: dict[str, Any] | None = None,
    shadow: dict[str, Block] | None = None,
) -> Block:
    b: Block = {"type": type_, "id": id_ or f"{type_}_{next(_ids)}"}
    if fields:
        b["fields"] = fields
    ins: dict[str, Any] = {}
    for k, v in (inputs or {}).items():
        if v is None:
            continue
        ins[k] = {"block": v}
    for k, v in (shadow or {}).items():
        ins[k] = {"shadow": v}
    if ins:
        b["inputs"] = ins
    if extra:
        b["extraState"] = extra
    return b


def chain(*blocks: Block) -> Block | None:
    """Link statements with ``next`` (returns the first)."""
    if not blocks:
        return None
    for a, b in itertools.pairwise(blocks):
        a["next"] = {"block": b}
    return blocks[0]


def program(
    *stmts: Block,
    variables: list[tuple[str, str, str]] = (),  # type: ignore[assignment]
    tops: list[Block] = (),  # type: ignore[assignment]
    start_id: str = "start",
) -> dict[str, Any]:
    start = blk("hb_start", start_id, inputs={"DO": chain(*stmts)})
    return {
        "blocks": {"languageVersion": 0, "blocks": [start, *tops]},
        "variables": [{"id": vid, "name": name, "type": typ} for vid, name, typ in variables],
    }


# ---------------------------------------------------------------- values
def num(x: float, id_: str | None = None) -> Block:
    return blk("math_number", id_, fields={"NUM": x})


def text(s: str, id_: str | None = None) -> Block:
    return blk("text", id_, fields={"TEXT": s})


def var(vid: str, id_: str | None = None) -> Block:
    return blk("variables_get", id_, fields={"VAR": {"id": vid}})


def arith(op: str, a: Block, b: Block, id_: str | None = None) -> Block:
    return blk("math_arithmetic", id_, fields={"OP": op}, inputs={"A": a, "B": b})


def join(*parts: Block, id_: str | None = None) -> Block:
    return blk(
        "text_join",
        id_,
        extra={"itemCount": len(parts)},
        inputs={f"ADD{i}": p for i, p in enumerate(parts)},
    )


# ---------------------------------------------------------------- conditions
def key(k: str, id_: str | None = None) -> Block:
    return blk("hb_key_pressed", id_, fields={"KEY": k})


def button(name: str, id_: str | None = None) -> Block:
    return blk("hb_button_pressed", id_, fields={"BUTTON": name})


def sees(detector: str, label: str, camera: str = "", id_: str | None = None) -> Block:
    return blk("hb_camera_sees", id_, fields={"CAMERA": camera, "DETECTOR": detector, "LABEL": label})


def either(a: Block, b: Block, id_: str | None = None) -> Block:
    return blk("logic_operation", id_, fields={"OP": "OR"}, inputs={"A": a, "B": b})


def boolean(v: bool, id_: str | None = None) -> Block:
    return blk("logic_boolean", id_, fields={"BOOL": "TRUE" if v else "FALSE"})


def compare(op: str, a: Block, b: Block, id_: str | None = None) -> Block:
    return blk("logic_compare", id_, fields={"OP": op}, inputs={"A": a, "B": b})


# ---------------------------------------------------------------- statements
def play(trajectory: str, speed: float = 100, id_: str | None = None) -> Block:
    return blk("hb_play_trajectory", id_, fields={"TRAJECTORY": trajectory, "SPEED": speed})


def move(pose: str, speed: float = 30, id_: str | None = None) -> Block:
    return blk("hb_move_to_pose", id_, fields={"POSE": pose, "SPEED": speed})


def wait(seconds: float, id_: str | None = None) -> Block:
    return blk("hb_wait", id_, inputs={"SECONDS": num(seconds)})


def wait_until(
    cond: Block, timeout: float | None = None, on_timeout: list[Block] = (), id_: str | None = None
) -> Block:  # type: ignore[assignment]
    return blk(
        "hb_wait_until",
        id_,
        fields={"TIMEOUT": timeout} if timeout is not None else None,
        inputs={"COND": cond, "ON_TIMEOUT": chain(*on_timeout)},
    )


def forever(*body: Block, id_: str | None = None) -> Block:
    return blk("hb_repeat_forever", id_, inputs={"DO": chain(*body)})


def repeat(times: Block, *body: Block, id_: str | None = None) -> Block:
    return blk("controls_repeat_ext", id_, inputs={"TIMES": times, "DO": chain(*body)})


def while_(cond: Block, *body: Block, mode: str = "WHILE", id_: str | None = None) -> Block:
    return blk("controls_whileUntil", id_, fields={"MODE": mode}, inputs={"BOOL": cond, "DO": chain(*body)})


def if_(
    branches: list[tuple[Block, list[Block]]], else_: list[Block] | None = None, id_: str | None = None
) -> Block:
    inputs: dict[str, Block | None] = {}
    for i, (c, body) in enumerate(branches):
        inputs[f"IF{i}"] = c
        inputs[f"DO{i}"] = chain(*body)
    extra: dict[str, Any] = {}
    if len(branches) > 1:
        extra["elseIfCount"] = len(branches) - 1
    if else_ is not None:
        extra["hasElse"] = True
        inputs["ELSE"] = chain(*else_)
    return blk("controls_if", id_, inputs=inputs, extra=extra or None)


def set_var(vid: str, value: Block, id_: str | None = None) -> Block:
    return blk("variables_set", id_, fields={"VAR": {"id": vid}}, inputs={"VALUE": value})


def change(vid: str, by: Block, id_: str | None = None) -> Block:
    return blk("math_change", id_, fields={"VAR": {"id": vid}}, inputs={"DELTA": by})


def log(value: Block, id_: str | None = None) -> Block:
    return blk("hb_log", id_, inputs={"TEXT": value})


def ask(question: str, choices: str, vid: str, timeout: float | None = None, id_: str | None = None) -> Block:
    fields: dict[str, Any] = {"QUESTION": question, "CHOICES": choices, "VAR": {"id": vid}}
    if timeout is not None:
        fields["TIMEOUT"] = timeout
    return blk("hb_ask_operator", id_, fields=fields)


def stop(id_: str | None = None) -> Block:
    return blk("hb_stop_program", id_)


def relax(id_: str | None = None) -> Block:
    return blk("hb_relax_arm", id_)


def go_home(id_: str | None = None) -> Block:
    return blk("hb_go_home", id_)


def set_signal(name: str, value: Block, id_: str | None = None) -> Block:
    return blk("hb_set_signal", id_, fields={"NAME": name}, inputs={"VALUE": value})


def run_model_until(
    model: str, cond: Block, timeout: float, on_timeout: list[Block] = (), id_: str | None = None
) -> Block:  # type: ignore[assignment]
    return blk(
        "hb_run_model_until",
        id_,
        fields={"MODEL": model, "TASK": "", "TIMEOUT": timeout},
        inputs={"UNTIL": cond, "ON_TIMEOUT": chain(*on_timeout)},
    )


def ab_program(a: str, b: str, *, detector: str = "cubes") -> dict[str, Any]:
    """The owner's example (§0): repeat forever: wait until the camera sees red or blue; if red play A,
    else if blue play B."""
    return program(
        forever(
            wait_until(
                either(sees(detector, "red", id_="w_red"), sees(detector, "blue", id_="w_blue"), id_="w_or"),
                timeout=60,
                id_="wait_cube",
            ),
            if_(
                [
                    (sees(detector, "red", id_="sees_red"), [play(a, id_="play_a")]),
                    (sees(detector, "blue", id_="sees_blue"), [play(b, id_="play_b")]),
                ],
                id_="if_ab",
            ),
            id_="loop",
        )
    )


def keys_program(a: str, b: str) -> dict[str, Any]:
    """§10 P2: the A/B program driven by the operator keys 1 / 2."""
    return program(
        forever(
            if_(
                [
                    (key("1", id_="key_1"), [play(a, id_="play_a")]),
                    (key("2", id_="key_2"), [play(b, id_="play_b")]),
                ],
                id_="if_keys",
            ),
            wait(0.1, id_="tick"),
            id_="loop",
        )
    )
