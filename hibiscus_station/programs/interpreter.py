"""The block-program interpreter: one ``program-runner`` thread per run (station-programs.md §5.1, §11).

:class:`Interpreter` implements ``programs.interfaces.ProgramRuntime``. It walks the compiled
:class:`~hibiscus_station.programs.schemas.ProgramAst` in its own thread and touches the arm only
through a :class:`~hibiscus_station.programs.interfaces.MotionPort`:

* real runs: ``ProgramSession`` (the ``programming`` motion session on the owner thread; every goal
  goes through the SafetyFilter, ThermalGuard, e-stop and dead-man there);
* dry runs: ``SimMotionPort`` (simulated arm, synthetic camera, :class:`FakeConditions`).

Conditions and values go through :class:`~hibiscus_station.programs.conditions.ConditionEngine`
(≤ ``condition_hz``, never in the owner thread). Rules:

* **E-stop always wins.** Between statements, inside every wait and while a motion runs the runner
  checks ``port.aborted`` / ``abort``; the owner freezes the arm within the tick and ends the
  session, which calls :meth:`Interpreter.abort` ("estopped"). The program never resumes by itself.
* **Pause** finishes the motion statement in flight, then waits (``pausing`` → ``paused``).
* **Stop** cancels the motion in flight (the arm holds) and ends the run (``stopped``).
* Every wait has a timeout (``wait until``: the block's, default ``settings.programs.wait_timeout_s``;
  motions: the driver's automatic one); a timeout runs the block's ``on timeout`` branch or ends the
  run with outcome ``timeout`` and a clear message.
* Every loop iteration lasts at least one ``condition_hz`` period: a busy loop the compiler could not
  prove (``while <condition>`` with no wait inside, ``wait 0``, a wait on a variable that is 0)
  cannot spin the CPU.

Every run writes ``runs/programs/<run_id>.jsonl`` (:class:`RunLog`): start, a ``block`` line per
statement, condition changes, variables, motions, inputs, faults, end. ``program_state`` messages go
out on every statement, status change and ≤ 5 Hz while waiting.
"""

from __future__ import annotations

import logging
import math
import threading
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Literal

from hibiscus_station.errors import StationError
from hibiscus_station.programs.conditions import ConditionEngine, ConditionError, OperatorLatches
from hibiscus_station.programs.schemas import (
    MOTION_KINDS,
    AskPrompt,
    AskStmt,
    ChangeVarStmt,
    ConditionValue,
    FakeConditions,
    ForeverStmt,
    IfStmt,
    LogStmt,
    MotionStmt,
    NotifyStmt,
    OperatorInput,
    PlayTrajectoryStmt,
    Program,
    ProgramState,
    ProgramStatus,
    RepeatStmt,
    RunModelStmt,
    Scalar,
    SetSignalStmt,
    SetVarStmt,
    Stmt,
    StopStmt,
    ValueExpr,
    WaitInfo,
    WaitStmt,
    WaitUntilStmt,
    WhileStmt,
)

if TYPE_CHECKING:
    from hibiscus_station.programs.interfaces import MotionHandle, MotionPort, RobotSnapshot, SignalBus
    from hibiscus_station.programs.runlog import RunLog

log = logging.getLogger(__name__)

Emit = Callable[[str, dict[str, Any]], None]
EngineFactory = Callable[
    [
        Callable[[], "RobotSnapshot"],
        OperatorLatches,
        Callable[[str], Scalar],
        Callable[[ConditionValue, bool], None],
    ],
    ConditionEngine,
]
Outcome = Literal["completed", "stopped", "failed", "estopped", "timeout"]
TERMINAL: frozenset[str] = frozenset({"completed", "stopped", "failed", "estopped", "timeout"})

WAIT_EMIT_S = 0.2  # program_state at most 5 Hz while waiting
MOTION_POLL_S = 0.05
ABORT_REASON_WAIT_S = 1.0  # port ended without a reason yet: wait this long for ``abort(reason)``
ABORT_GRACE_S = 2.0  # a motion handle that does not resolve after an abort is given up
JOIN_S = 2.0
MAX_REPEAT = 1_000_000
MAX_WAIT_S = 86400.0
TRACE_LIMIT = 10000  # block / condition lines kept in the run file (the WS still gets all)


class _RunEndError(Exception):
    def __init__(self, outcome: Outcome, message: str | None = None) -> None:
        super().__init__(message or outcome)
        self.outcome: Outcome = outcome
        self.message = message


class _FaultError(Exception):
    def __init__(self, message: str, *, code: str = "fault", block_id: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.block_id = block_id


def outcome_for(reason: str) -> Outcome:
    """``abort(reason)`` → run outcome."""
    if reason in ("estopped", "estop", "user"):
        return "estopped"
    if reason in ("stopped", "stop", "completed"):
        return "stopped"
    if reason == "timeout":
        return "timeout"
    return "failed"


def as_text(v: Scalar) -> str:
    if isinstance(v, float) and v.is_integer() and abs(v) < 1e15:
        return str(int(v))
    return str(v)


class Interpreter:
    """``programs.interfaces.ProgramRuntime`` for one run of one program version."""

    def __init__(
        self,
        *,
        program: Program,
        run_id: str,
        dry_run: bool,
        runlog: RunLog,
        engine_factory: EngineFactory,
        signals: SignalBus,
        emit: Emit | None = None,
        estopped: Callable[[], bool] | None = None,
        notify: Callable[[str], None] | None = None,
        on_finished: Callable[[Interpreter], None] | None = None,
        condition_hz: float = 10.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if program.ast is None:
            raise StationError("program_invalid", "the program does not compile")
        self.program = program
        self.ast = program.ast
        self.run_id = run_id
        self.dry_run = dry_run
        self.runlog = runlog
        self._engine_factory = engine_factory
        self.signals = signals
        self._emit = emit
        self._estopped = estopped or (lambda: False)
        self._notify = notify
        self._on_finished = on_finished
        self.period_s = 1.0 / min(10.0, max(0.1, condition_hz))
        self._clock = clock
        self.latches = OperatorLatches([b.name for b in self.ast.buttons], self.ast.keys)
        self.variables: dict[str, Scalar] = {v.name: v.initial for v in self.ast.variables}
        self._var_types = {v.name: v.type for v in self.ast.variables}
        self.engine: ConditionEngine | None = None
        self.port: MotionPort | None = None
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._abort_evt = threading.Event()
        self._thread: threading.Thread | None = None
        self._t0 = clock()
        self._t_end: float | None = None  # the clock when the run ended: its time stops there
        self._status: ProgramStatus = "starting"
        self._block_id: str | None = None
        self._block_kind: str | None = None
        self._steps = 0
        self._waiting: WaitInfo | None = None
        self._message: str | None = None
        self._outcome: Outcome | None = None
        self._finished = False
        self._finishing = False
        self._stop_reason: str | None = None
        self._abort_reason: str | None = None
        self._pause_req = False
        self._handle: MotionHandle | None = None
        self._pending_fakes: list[FakeConditions] = []
        self._last_wait_emit = -math.inf
        self._trace_lines = 0
        self.played: list[str] = []  # trajectory ids in the order they were played (tests, logs)

    # ================================================================== ProgramRuntime
    def start(self, port: MotionPort) -> None:
        if self._thread is not None:
            raise StationError("busy", "this run was already started")
        self.port = port
        self.engine = self._engine_factory(port.snapshot, self.latches, self._variable, self._on_value)
        for f in self._pending_fakes:
            self.engine.fake(f)
        self._pending_fakes.clear()
        self._t0 = self._clock()
        self._thread = threading.Thread(target=self._main, name=f"program-runner-{self.run_id}", daemon=True)
        self._thread.start()

    def pause(self) -> None:
        with self._lock:
            if self._finished or self._status in ("paused", "pausing"):
                return
            self._pause_req = True
            self._status = "pausing"
        self.runlog.write("input", "pause requested", block_id=self._block_id)
        self._kick()
        self._publish()

    def resume(self) -> None:
        with self._lock:
            if self._finished or not self._pause_req:
                return
            self._pause_req = False
            if self._status == "pausing":  # still inside the motion / wait it was asked in
                waits = self._waiting is not None and self._waiting.kind in ("wait", "wait_until", "ask")
                self._status = "waiting" if waits else "running"
            elif self._status == "paused":  # the runner restores the exact status when it wakes
                self._status = "running"
        self.runlog.write("input", "resume", block_id=self._block_id)
        self._kick()
        self._publish()

    def stop(self, reason: str = "stopped") -> None:
        with self._lock:
            if self._finished:
                return
            if self._stop_reason is None:
                self._stop_reason = reason
            if self._status not in TERMINAL:
                self._status = "stopping"
        self._cancel_motion()
        self._kick()
        self._publish()

    def abort(self, reason: str) -> None:
        with self._lock:
            if self._finished:
                return
            if self._abort_reason is None:
                self._abort_reason = reason
        self._abort_evt.set()
        self._cancel_motion()
        self._kick()
        t = self._thread
        if t is not None and t is not threading.current_thread():
            t.join(JOIN_S)
        if t is None or not self._finished:  # never started, or the runner is stuck in a callback
            self._finish(outcome_for(reason), f"aborted: {reason}")

    def input(self, ev: OperatorInput) -> None:
        if self._finished:
            raise StationError("not_found", "the program is not running")
        self.latches.push(ev)  # validation_failed for a button/key the program does not have
        self.runlog.write("input", f"{ev.kind} {ev.value}", data=ev.model_dump(mode="json"))
        self._kick()

    def fake(self, fakes: FakeConditions) -> None:
        if not self.dry_run:
            raise StationError("validation_failed", "fake conditions are for dry runs only")
        if self.engine is None:
            self._pending_fakes.append(fakes)
        else:
            self.engine.fake(fakes)
        self.runlog.write("input", "fake conditions", data=fakes.model_dump(mode="json"))
        self._kick()

    @property
    def finished(self) -> bool:
        return self._finished

    @property
    def outcome(self) -> str | None:
        return self._outcome if self._finished else None

    def state(self) -> ProgramState:
        engine = self.engine
        conditions = engine.values() if engine is not None else []
        with self._lock:
            return ProgramState(
                run_id=self.run_id,
                program_id=self.program.id,
                version=self.program.version,
                dry_run=self.dry_run,
                status=self._status,
                block_id=self._block_id,
                block_kind=self._block_kind,
                t=round(self.elapsed(), 3),
                steps=self._steps,
                variables=dict(self.variables),
                conditions=conditions,
                waiting=self._waiting,
                ask=self.latches.prompt,
                buttons=list(self.ast.buttons),
                keys=list(self.ast.keys),
                message=self._message,
            )

    # ================================================================== helpers
    def elapsed(self) -> float:
        """Seconds since the start; frozen at the end of the run (QC 0.2.9 QD-16)."""
        end = self._t_end
        return (end if end is not None else self._clock()) - self._t0

    def join(self, timeout: float | None = None) -> bool:
        t = self._thread
        if t is not None:
            t.join(timeout)
        return self._finished

    def _kick(self) -> None:
        self._wake.set()
        if self.engine is not None:
            self.engine.wake.set()

    def _cancel_motion(self) -> None:
        h = self._handle
        if h is not None:
            h.cancel()

    def _publish(self) -> None:
        if self._emit is None:
            return
        try:
            self._emit("program_state", self.state().model_dump(mode="json"))
        except Exception:  # pragma: no cover - a listener must never break the program
            log.exception("program_state emit failed")

    def _variable(self, name: str) -> Scalar:
        with self._lock:
            return self.variables[name]

    def _on_value(self, cv: ConditionValue, changed: bool) -> None:
        if not changed:
            return
        self._trace(
            "condition",
            f"{cv.block_id} = {cv.value}" if cv.message is None else f"{cv.block_id}: {cv.message}",
            block_id=cv.block_id,
            data={"value": cv.value, "message": cv.message},
        )

    def _trace(
        self, kind: str, message: str, *, block_id: str | None, data: dict[str, Any] | None = None
    ) -> None:
        self._trace_lines += 1
        if self._trace_lines == TRACE_LIMIT:
            self.runlog.write(
                "log", "trace limit reached: block and condition lines are no longer logged", level="warn"
            )
        if self._trace_lines >= TRACE_LIMIT:
            return
        self.runlog.write(kind, message, block_id=block_id, data=data)

    def _set_status(self, status: ProgramStatus, waiting: WaitInfo | None = None) -> None:
        with self._lock:
            if self._finished or self._status == "stopping":
                return
            if self._pause_req and status in ("running", "waiting"):
                status = "pausing"
            self._status = status
            self._waiting = waiting

    # ---------------------------------------------------------------- cancellation
    def _cancel_requested(self) -> bool:
        port = self.port
        return (
            self._abort_reason is not None
            or self._stop_reason is not None
            or (port is not None and port.aborted)
        )

    def _raise_if_cancelled(self) -> None:
        if self._abort_reason is not None:
            raise _RunEndError(outcome_for(self._abort_reason), self._abort_message(self._abort_reason))
        if self._stop_reason is not None:
            raise _RunEndError(
                "stopped", self._stop_reason if self._stop_reason != "stopped" else "stopped by the operator"
            )
        port = self.port
        if port is not None and port.aborted:
            if self._estopped():
                raise _RunEndError("estopped", "e-stop")
            self._abort_evt.wait(ABORT_REASON_WAIT_S)  # the session is ending: let it say why
            reason = self._abort_reason
            if reason is not None:
                raise _RunEndError(outcome_for(reason), self._abort_message(reason))
            if self._estopped():
                raise _RunEndError("estopped", "e-stop")
            raise _RunEndError("stopped", "the session ended")

    @staticmethod
    def _abort_message(reason: str) -> str:
        return "e-stop" if outcome_for(reason) == "estopped" else reason

    def _checkpoint(self) -> None:
        self._raise_if_cancelled()
        self._pause_here()

    def _pause_here(self) -> None:
        """Pause between statements or inside a wait; restore the status after ``resume``."""
        if not self._pause_req:
            return
        with self._lock:
            prev_status, prev_waiting = self._status, self._waiting
            if self._status != "stopping":
                self._status = "paused"
                self._waiting = None
        self.runlog.write("log", "paused", block_id=self._block_id)
        self._publish()
        while self._pause_req:
            self._raise_if_cancelled()
            self._wake.wait(0.2)
            self._wake.clear()
        self._raise_if_cancelled()
        resumed: ProgramStatus = (
            "waiting"
            if prev_status == "waiting"
            or (
                prev_status == "pausing"
                and prev_waiting is not None
                and prev_waiting.kind in ("wait", "wait_until", "ask")
            )
            else "running"
        )
        self._set_status(resumed, prev_waiting)
        self._publish()

    def _sleep(self, seconds: float) -> None:
        """Interruptible sleep (stop, abort, e-stop end it early; a pause stops the clock)."""
        deadline = self._clock() + seconds
        while True:
            self._raise_if_cancelled()
            if self._pause_req:
                t0 = self._clock()
                self._pause_here()
                deadline += self._clock() - t0
            left = deadline - self._clock()
            if left <= 0:
                return
            self._wake.wait(min(left, 0.1))
            self._wake.clear()

    # ================================================================== runner thread
    def _main(self) -> None:
        outcome: Outcome = "completed"
        message: str | None = None
        try:
            self.runlog.start()
            self._set_status("running")
            self._publish()
            self._exec(self.ast.body)
            self._raise_if_cancelled()
        except _RunEndError as e:
            outcome, message = e.outcome, e.message
        except _FaultError as f:
            outcome, message = "failed", f.message
            self.runlog.write(
                "fault",
                f.message,
                level="error",
                block_id=f.block_id or self._block_id,
                data={"code": f.code},
            )
        except Exception as exc:  # a bug must end the run cleanly, never hang the session
            log.exception("program runner crashed")
            outcome, message = "failed", f"internal error: {exc}"[:300]
            self.runlog.write(
                "fault", message, level="error", block_id=self._block_id, data={"code": "internal"}
            )
        self._finish(outcome, message)

    def _finish(self, outcome: Outcome, message: str | None) -> None:
        with self._lock:
            if self._finished or self._finishing:
                return
            self._finishing = True
            self._t_end = self._clock()
        self.latches.cancel_ask()
        try:
            self.runlog.close(outcome, message)
        except Exception:  # pragma: no cover - disk full: the run still ends
            log.exception("run log close failed")
        with self._lock:
            self._outcome = outcome
            self._message = message
            self._status = outcome
            self._waiting = None
            self._finished = True
        self._publish()
        cb = self._on_finished
        if cb is not None:
            try:
                cb(self)
            except Exception:  # pragma: no cover
                log.exception("program on_finished failed")

    def _exec(self, body: list[Stmt]) -> None:
        for s in body:
            self._checkpoint()
            self._step(s)

    def _step(self, s: Stmt) -> None:
        with self._lock:
            self._steps += 1
            self._block_id = s.id
            self._block_kind = s.kind
            steps = self._steps
        self.runlog.steps = steps
        self._set_status("running")
        self._trace("block", s.kind, block_id=s.id)
        self._publish()
        try:
            self._dispatch(s)
        except ConditionError as exc:
            raise _FaultError(exc.message, code=exc.code, block_id=exc.block_id or s.id) from exc
        except StationError as exc:
            raise _FaultError(exc.detail, code=exc.code, block_id=s.id) from exc

    def _dispatch(self, s: Stmt) -> None:
        if s.kind in MOTION_KINDS:
            self._motion(s)  # type: ignore[arg-type]
        elif isinstance(s, IfStmt):
            for br in s.branches:
                if self._test(br.cond):
                    self._exec(br.body)
                    return
            if s.else_body is not None:
                self._exec(s.else_body)
        elif isinstance(s, RepeatStmt):
            n = self._number(s.times)
            times = int(min(MAX_REPEAT, max(0, round(n))))
            for _ in range(times):
                self._iteration(s.body)
        elif isinstance(s, ForeverStmt):
            while True:
                self._iteration(s.body)
        elif isinstance(s, WhileStmt):
            while True:
                v = self._test(s.cond)
                if (s.mode == "while" and not v) or (s.mode == "until" and v):
                    return
                self._iteration(s.body)
        elif isinstance(s, WaitStmt):
            self._wait(s)
        elif isinstance(s, WaitUntilStmt):
            self._wait_until(s)
        elif isinstance(s, StopStmt):
            raise _RunEndError("stopped", "stop block")
        elif isinstance(s, SetVarStmt):
            self._assign(s.name, self._value(s.value), s.id)
        elif isinstance(s, ChangeVarStmt):
            cur = self._variable(s.name)
            base = cur if isinstance(cur, float) else 0.0
            self._assign(s.name, base + self._number(s.by), s.id)
        elif isinstance(s, AskStmt):
            self._ask(s)
        elif isinstance(s, LogStmt):
            self.runlog.write("log", as_text(self._value(s.text)), block_id=s.id)
        elif isinstance(s, NotifyStmt):
            text = as_text(self._value(s.text))
            sent = s.webhook and self._notify is not None and not self.dry_run
            self.runlog.write("notify", text, block_id=s.id, data={"webhook": bool(sent)})
            if sent and self._notify is not None:
                self._notify(text)
        elif isinstance(s, SetSignalStmt):
            value = self._value(s.value)
            self.signals.set(s.name, value, "program")
            self.runlog.write("signal", f"{s.name} = {as_text(value)}", block_id=s.id, data={"value": value})
        else:  # pragma: no cover - the AST union is closed
            raise _FaultError(f"unknown statement {s.kind}", block_id=s.id)

    def _iteration(self, body: list[Stmt]) -> None:
        t0 = self._clock()
        self._exec(body)
        self._checkpoint()
        # Every iteration lasts at least one condition period, whatever it contains: a ``wait 0`` (or
        # a wait on a variable that is 0) passes the compiler's busy-loop rule but must not spin the
        # CPU, flood the control socket with program_state or fill the run log.
        left = self.period_s - (self._clock() - t0)
        if left > 0:
            self._sleep(left)

    # ---------------------------------------------------------------- values
    def _eng(self) -> ConditionEngine:
        if self.engine is None:  # pragma: no cover - built in start()
            raise _FaultError("the run was not started")
        return self.engine

    def _value(self, e: ValueExpr) -> Scalar:
        return self._eng().value(e)

    def _number(self, e: ValueExpr) -> float:
        v = self._value(e)
        if isinstance(v, float):
            return v
        try:
            f = float(v)
        except ValueError:
            raise _FaultError(f"{v!r} is not a number", code="type_mismatch", block_id=e.id) from None
        if not math.isfinite(f):
            raise _FaultError(f"{v!r} is not a number", code="type_mismatch", block_id=e.id)
        return f

    def _test(self, cond: Any) -> bool:
        v = self._eng().check(cond)
        return bool(v)

    def _assign(self, name: str, value: Scalar, block_id: str) -> None:
        typ = self._var_types.get(name, "number")
        if typ == "number":
            if not isinstance(value, float):
                try:
                    value = float(value)
                except ValueError:
                    raise _FaultError(
                        f"{value!r} is not a number", code="type_mismatch", block_id=block_id
                    ) from None
            if not math.isfinite(value):
                raise _FaultError("not a finite number", code="type_mismatch", block_id=block_id)
        else:
            value = as_text(value)[:500]
        with self._lock:
            self.variables[name] = value
        self.runlog.write(
            "variable", f"{name} = {as_text(value)}", block_id=block_id, data={"name": name, "value": value}
        )

    # ---------------------------------------------------------------- waits
    def _waiting_tick(self) -> None:
        now = self._clock()
        if now - self._last_wait_emit >= WAIT_EMIT_S:
            self._last_wait_emit = now
            self._publish()

    def _wait(self, s: WaitStmt) -> None:
        seconds = min(MAX_WAIT_S, max(0.0, self._number(s.seconds)))
        self._set_status(
            "waiting", WaitInfo(kind="wait", block_id=s.id, since_s=round(self.elapsed(), 3), timeout_s=None)
        )
        self._publish()
        self._sleep(seconds)

    def _wait_until(self, s: WaitUntilStmt) -> None:
        self._set_status(
            "waiting",
            WaitInfo(
                kind="wait_until", block_id=s.id, since_s=round(self.elapsed(), 3), timeout_s=s.timeout_s
            ),
        )
        self._publish()
        left = s.timeout_s
        while True:
            t0 = self._clock()
            res = self._eng().wait_until(
                s.cond,
                timeout_s=left,
                cancelled=lambda: self._cancel_requested() or self._pause_req,
                on_tick=self._waiting_tick,
            )
            if res == "true":
                return
            if res == "timeout":
                self._timed_out(s.id, "wait until", s.timeout_s, s.on_timeout)
                return
            self._raise_if_cancelled()
            left = max(0.0, left - (self._clock() - t0))
            self._pause_here()  # a pause stops the timeout clock

    def _timed_out(
        self, block_id: str, what: str, timeout_s: float | None, branch: list[Stmt] | None
    ) -> None:
        msg = f"{what} timed out after {timeout_s:g} s" if timeout_s is not None else f"{what} timed out"
        self.runlog.write(
            "timeout", msg, level="warn", block_id=block_id, data={"on_timeout": branch is not None}
        )
        if branch is None:
            raise _RunEndError("timeout", msg)
        self._exec(branch)

    def _ask(self, s: AskStmt) -> None:
        self.latches.ask(AskPrompt(block_id=s.id, question=s.question, choices=list(s.choices)))
        self._set_status(
            "waiting",
            WaitInfo(kind="ask", block_id=s.id, since_s=round(self.elapsed(), 3), timeout_s=s.timeout_s),
        )
        self._publish()
        deadline = None if s.timeout_s is None else self._clock() + s.timeout_s
        try:
            while True:
                self._raise_if_cancelled()
                ans = self.latches.take_answer()
                if ans is not None:
                    break
                if self._pause_req:
                    t0 = self._clock()
                    self._pause_here()
                    if deadline is not None:
                        deadline += self._clock() - t0
                if deadline is not None and self._clock() >= deadline:
                    self.latches.cancel_ask()
                    self._timed_out(s.id, "ask operator", s.timeout_s, None)
                self.latches.changed.wait(0.1)
                self.latches.changed.clear()
        finally:
            self.latches.cancel_ask()
        self._assign(s.var, ans, s.id)

    # ---------------------------------------------------------------- motions
    def _motion(self, s: MotionStmt) -> None:
        port = self.port
        if port is None:  # pragma: no cover - built in start()
            raise _FaultError("the run was not started")
        data: dict[str, Any] = {"kind": s.kind}
        for key in (
            "trajectory",
            "pose",
            "model",
            "speed_pct",
            "speed_deg_s",
            "action",
            "percent",
            "duration_s",
        ):
            v = getattr(s, key, None)
            if v is not None:
                data[key] = v
        self.runlog.write("motion", f"{s.kind} start", block_id=s.id, data=data)
        kind: Literal["motion", "run_model"] = "run_model" if s.kind == "run_model" else "motion"
        self._set_status(
            "running",
            WaitInfo(kind=kind, block_id=s.id, since_s=round(self.elapsed(), 3), timeout_s=s.timeout_s),
        )
        self._publish()
        try:
            handle = port.submit(s)
        except StationError as exc:
            raise _FaultError(exc.detail, code=exc.code, block_id=s.id) from exc
        if isinstance(s, PlayTrajectoryStmt):
            self.played.append(s.trajectory)
        with self._lock:
            self._handle = handle
        if self._cancel_requested():
            handle.cancel()
        until = s.until if isinstance(s, RunModelStmt) else None
        by_until = False
        gave_up_at: float | None = None
        result = None
        try:
            while result is None:
                result = handle.wait(self.period_s if until is not None else MOTION_POLL_S)
                if result is not None:
                    break
                if self._cancel_requested():
                    handle.cancel()
                    now = self._clock()
                    gave_up_at = gave_up_at or now
                    if now - gave_up_at > ABORT_GRACE_S:
                        break  # the port is gone: do not wait for it any longer
                elif until is not None and not by_until and self._test(until):
                    by_until = True
                    handle.cancel()
        finally:
            with self._lock:
                self._handle = None
        outcome = result.outcome if result is not None else "aborted"
        self.runlog.write(
            "motion",
            f"{s.kind} {outcome}",
            level="info" if outcome in ("completed", "cancelled") else "warn",
            block_id=s.id,
            data={
                **data,
                "outcome": outcome,
                "detail": result.detail if result is not None else None,
                "elapsed_s": result.elapsed_s if result is not None else None,
            },
        )
        if outcome == "completed":
            return
        if outcome == "cancelled":
            if by_until:
                return
            self._raise_if_cancelled()
            return
        if outcome == "aborted":
            self._raise_if_cancelled()
            raise _RunEndError("stopped", "the motion was aborted")
        if outcome == "timeout":
            self._raise_if_cancelled()
            branch = s.on_timeout if isinstance(s, RunModelStmt) else None
            self._timed_out(s.id, s.kind.replace("_", " "), s.timeout_s, branch)
            return
        raise _FaultError(
            (result.detail if result is not None else None) or f"{s.kind} failed",
            code="motion_failed",
            block_id=s.id,
        )
