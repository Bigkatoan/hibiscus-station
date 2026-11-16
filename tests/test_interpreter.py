"""The program interpreter against a fake MotionPort (station-programs.md §5.1, §6, §12.3).

Order of statements, operator keys/buttons/answers, variables, waits and timeouts, pause/resume,
stop, abort (e-stop), faults, dry-run fakes, loop pacing, and the run log + program_state trace.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

import pytest
from blocks_dsl import (
    arith,
    ask,
    blk,
    change,
    compare,
    forever,
    if_,
    key,
    keys_program,
    log,
    num,
    play,
    program,
    repeat,
    run_model_until,
    sees,
    set_signal,
    set_var,
    stop,
    text,
    var,
    wait,
    wait_until,
    while_,
)
from conftest import is_private, wait_for

from hibiscus_station.errors import StationError
from hibiscus_station.profiles import GripHold
from hibiscus_station.programs import schemas as ps
from hibiscus_station.programs.compiler import compile_program
from hibiscus_station.programs.conditions import ConditionEngine
from hibiscus_station.programs.interfaces import MotionResult, RobotSnapshot
from hibiscus_station.programs.interpreter import Interpreter, outcome_for
from hibiscus_station.programs.motion import MotionTicket
from hibiscus_station.programs.runlog import RunLog, list_runs, read_run
from hibiscus_station.programs.signals import SignalBus

A = "t_20261116_120000_aaaa"
B = "t_20261116_120000_bbbb"
RUN = "r_20261116_120000_abcd"


class FakePort:
    """MotionPort: each motion takes ``duration`` seconds unless cancelled."""

    def __init__(self, duration: float = 0.05, outcomes: dict[str, str] | None = None) -> None:
        self.duration = duration
        self.outcomes = outcomes or {}
        self.submitted: list[ps.MotionStmt] = []
        self.tickets: list[MotionTicket] = []
        self.ended = False
        self.refuse: StationError | None = None

    @property
    def aborted(self) -> bool:
        return self.ended

    def submit(self, stmt: ps.MotionStmt) -> MotionTicket:
        if self.refuse is not None:
            raise self.refuse
        if any(t.result is None for t in self.tickets):
            raise StationError("busy", "a motion is already running")
        t = MotionTicket(stmt)
        self.submitted.append(stmt)
        self.tickets.append(t)

        def drive() -> None:
            t0 = time.monotonic()
            while time.monotonic() - t0 < self.duration:
                if t.cancel_requested or self.ended:
                    t.resolve(
                        MotionResult("aborted" if self.ended else "cancelled", None, time.monotonic() - t0)
                    )
                    return
                time.sleep(0.005)
            outcome = self.outcomes.get(stmt.kind, "completed")
            t.resolve(MotionResult(outcome, None if outcome == "completed" else outcome, self.duration))  # type: ignore[arg-type]

        threading.Thread(target=drive, daemon=True).start()
        return t

    def snapshot(self) -> RobotSnapshot:
        return RobotSnapshot(
            t=0.0,
            tick=1,
            positions={"elbow_flex.pos": 10.0},
            goal={},
            load_pct={},
            temp_c={},
            frames={},
            frame_tick=1,
        )

    @property
    def kinds(self) -> list[str]:
        out = []
        for s in self.submitted:
            out.append(getattr(s, "trajectory", None) or s.kind)
        return out


def make_program(doc: dict[str, Any], buttons: list[ps.OperatorButton] | None = None) -> ps.Program:
    r = compile_program(doc, buttons)
    assert r.ast is not None, r.issues
    return ps.Program(
        id="ab",
        name="A/B",
        robot="desk",
        version=1,
        created_at="",
        updated_at="",
        editor=doc,
        buttons=buttons or [],
        ast=r.ast,
        issues=r.issues,
        refs=r.refs,
        dry_run_version=None,
    )


class Run:
    """An Interpreter wired to a FakePort, a real ConditionEngine, a RunLog in tmp and an event list."""

    def __init__(
        self,
        tmp: Path,
        doc: dict[str, Any],
        *,
        port: FakePort | None = None,
        dry_run: bool = True,
        buttons: list[ps.OperatorButton] | None = None,
        estopped: bool = False,
        hz: float = 10.0,
    ) -> None:
        self.home = tmp
        self.events: list[tuple[str, dict[str, Any]]] = []
        self.lock = threading.Lock()
        self.signals = SignalBus()
        self.port = port or FakePort()
        self.estop = estopped
        self.finished_cb = threading.Event()
        self.program = make_program(doc, buttons)
        self.log = RunLog(tmp, RUN, program_id="ab", version=1, dry_run=dry_run, emit=self.emit)

        def engine(snapshot: Any, latches: Any, variables: Any, on_value: Any) -> ConditionEngine:
            def no_detector(d: str) -> Any:
                raise StationError("not_found", d)

            return ConditionEngine(
                snapshot=snapshot,
                signals=self.signals,
                detector=no_detector,
                detector_camera=lambda d: "wrist",
                pose=lambda n: {"elbow_flex.pos": 10.0},
                grip_hold=GripHold(),
                latches=latches,
                variables=variables,
                condition_hz=hz,
                dry_run=dry_run,
                on_value=on_value,
            )

        self.rt = Interpreter(
            program=self.program,
            run_id=RUN,
            dry_run=dry_run,
            runlog=self.log,
            engine_factory=engine,
            signals=self.signals,
            emit=self.emit,
            estopped=lambda: self.estop,
            on_finished=lambda rt: self.finished_cb.set(),
            condition_hz=hz,
        )

    def emit(self, kind: str, payload: dict[str, Any]) -> None:
        with self.lock:
            self.events.append((kind, payload))

    def of(self, kind: str) -> list[dict[str, Any]]:
        with self.lock:
            return [p for k, p in self.events if k == kind]

    def start(self) -> Run:
        self.rt.start(self.port)  # type: ignore[arg-type]
        return self

    def done(self, timeout: float = 5.0) -> str:
        assert self.rt.join(timeout), self.rt.state()
        assert self.rt.outcome is not None
        return self.rt.outcome

    def lines(self) -> list[dict[str, Any]]:
        return [
            json.loads(x)
            for x in (self.home / "runs" / "programs" / f"{RUN}.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
        ]

    def status(self) -> str:
        return self.rt.state().status


def press(run: Run, k: str) -> None:
    run.rt.input(ps.OperatorInput(kind="key", value=k))


# =========================================================================== flow
def test_ab_program_with_keys_and_trace(tmp_path: Path) -> None:
    run = Run(tmp_path, keys_program(A, B), dry_run=False).start()
    wait_for(lambda: run.status() == "waiting", 3)
    assert run.rt.state().keys == ["1", "2"] and run.port.submitted == []
    press(run, "1")
    wait_for(lambda: len(run.port.submitted) == 1, 3)
    press(run, "2")
    wait_for(lambda: len(run.port.submitted) == 2, 3)
    press(run, "1")
    wait_for(lambda: len(run.port.submitted) == 3, 3)
    assert run.port.kinds == [A, B, A] and run.rt.played == [A, B, A]
    with pytest.raises(StationError):  # a key the program does not read
        press(run, "9")
    run.rt.stop()
    assert run.done() == "stopped"
    lines = run.lines()
    assert lines[0]["kind"] == "start" and lines[0]["data"]["program_id"] == "ab"
    assert lines[-1]["kind"] == "end" and lines[-1]["data"]["outcome"] == "stopped"
    blocks = [ln["block_id"] for ln in lines if ln["kind"] == "block"]
    assert {"loop", "if_keys", "play_a", "play_b", "tick"} <= set(blocks)
    motions = [(ln["block_id"], ln["data"].get("outcome")) for ln in lines if ln["kind"] == "motion"]
    assert motions[:4] == [
        ("play_a", None),
        ("play_a", "completed"),
        ("play_b", None),
        ("play_b", "completed"),
    ]
    assert [ln["message"] for ln in lines if ln["kind"] == "input"][:2] == ["key 1", "key 2"]
    assert [ln["seq"] for ln in lines] == list(range(1, len(lines) + 1))
    # every line also went out as program_log; program_state followed the blocks
    assert [p["seq"] for p in run.of("program_log")] == [ln["seq"] for ln in lines]
    states = run.of("program_state")
    assert any(s["block_id"] == "play_b" for s in states) and states[-1]["status"] == "stopped"
    for s in states:
        ps.ProgramStateMsg.model_validate({**s, "type": "program_state"})
    for ln in run.of("program_log"):
        ps.ProgramLogMsg.model_validate({**ln, "type": "program_log"})
    summary = list_runs(tmp_path, "ab")[0]
    assert summary.outcome == "stopped" and summary.steps > 5 and summary.faults == 0 and not summary.dry_run
    full = read_run(tmp_path, "ab", RUN)
    assert len(full.lines) == len(lines)
    with pytest.raises(StationError):
        read_run(tmp_path, "other", RUN)
    assert run.finished_cb.is_set()


def test_variables_if_repeat_and_completion(tmp_path: Path) -> None:
    doc = program(
        repeat(num(3), change("n", num(1), id_="inc"), id_="rep"),
        if_(
            [(compare("GT", var("n"), num(2)), [set_var("t", text("big"), id_="big")])],
            else_=[set_var("t", text("small"), id_="small")],
        ),
        set_var("n", arith("POWER", var("n"), num(2)), id_="sq"),
        log(var("t"), id_="say"),
        set_signal("count", var("n"), id_="sig"),
        variables=[("n", "n", "Number"), ("t", "t", "String")],
    )
    run = Run(tmp_path, doc).start()
    assert run.done() == "completed"
    st = run.rt.state()
    assert st.variables == {"n": 9.0, "t": "big"} and st.status == "completed" and st.steps == 9
    assert run.signals.get("count") is not None and run.signals.get("count").value == 9.0  # type: ignore[union-attr]
    logs = [ln for ln in run.lines() if ln["kind"] == "log"]
    assert [ln["message"] for ln in logs] == ["big"]
    assert any(ln["kind"] == "variable" and ln["data"] == {"name": "n", "value": 9.0} for ln in run.lines())


def test_stop_block_ends_the_run(tmp_path: Path) -> None:
    run = Run(tmp_path, program(log(text("a")), stop(id_="s"), log(text("never")))).start()
    assert run.done() == "stopped"
    assert run.rt.state().message == "stop block"
    assert [ln["message"] for ln in run.lines() if ln["kind"] == "log"] == ["a"]


def test_wait_until_timeout_runs_the_branch_or_ends_the_run(tmp_path: Path) -> None:
    doc = program(
        wait_until(key("1"), timeout=0.3, on_timeout=[log(text("late"), id_="late")], id_="w"),
        log(text("after")),
    )
    run = Run(tmp_path, doc).start()
    assert run.done() == "completed"
    assert [ln["message"] for ln in run.lines() if ln["kind"] == "log"] == ["late", "after"]
    assert any(ln["kind"] == "timeout" and ln["block_id"] == "w" for ln in run.lines())

    doc = program(wait_until(key("1"), timeout=0.3, id_="w"), log(text("never")))
    run = Run(tmp_path / "b", doc).start()
    assert run.done() == "timeout"
    assert "timed out" in (run.rt.state().message or "")


def test_waiting_status_and_wait_info(tmp_path: Path) -> None:
    run = Run(tmp_path, program(wait(0.6, id_="w"), log(text("x")))).start()
    wait_for(lambda: run.status() == "waiting", 2)
    st = run.rt.state()
    assert st.waiting is not None and st.waiting.kind == "wait" and st.block_id == "w"
    assert run.done() == "completed"
    assert run.rt.elapsed() >= 0.6


def test_ask_operator(tmp_path: Path) -> None:
    doc = program(
        ask("Which bin?", "left,right", "v", id_="a"), log(var("v")), variables=[("v", "bin", "String")]
    )
    run = Run(tmp_path, doc).start()
    wait_for(lambda: run.rt.state().ask is not None, 2)
    st = run.rt.state()
    assert st.ask is not None and st.ask.choices == ["left", "right"] and st.status == "waiting"
    with pytest.raises(StationError):
        run.rt.input(ps.OperatorInput(kind="answer", value="middle"))
    run.rt.input(ps.OperatorInput(kind="answer", value="right"))
    assert run.done() == "completed"
    assert run.rt.state().variables == {"bin": "right"} and run.rt.state().ask is None

    doc = program(ask("Which bin?", "left,right", "v", timeout=0.3), variables=[("v", "bin", "String")])
    run = Run(tmp_path / "b", doc).start()
    assert run.done() == "timeout"


def test_buttons(tmp_path: Path) -> None:
    doc = program(wait_until(blk("hb_button_pressed", "b", fields={"BUTTON": "go"}), timeout=5), play(A))
    run = Run(tmp_path, doc, buttons=[ps.OperatorButton(name="go", label="Go")]).start()
    wait_for(lambda: run.status() == "waiting", 2)
    assert [b.name for b in run.rt.state().buttons] == ["go"]
    run.rt.input(ps.OperatorInput(kind="button", value="go"))
    assert run.done() == "completed" and run.port.kinds == [A]


# =========================================================================== pause / stop / abort
def test_pause_finishes_the_motion_then_waits(tmp_path: Path) -> None:
    port = FakePort(duration=0.5)
    run = Run(tmp_path, program(play(A, id_="p1"), play(B, id_="p2")), port=port).start()
    wait_for(lambda: len(port.submitted) == 1, 2)
    run.rt.pause()
    assert run.status() == "pausing"
    wait_for(lambda: run.status() == "paused", 3)
    assert port.tickets[0].result is not None and port.tickets[0].result.outcome == "completed"
    time.sleep(0.3)
    assert len(port.submitted) == 1  # nothing new while paused
    run.rt.resume()
    assert run.done() == "completed" and port.kinds == [A, B]


def test_pause_inside_a_wait_until_stops_its_clock(tmp_path: Path) -> None:
    run = Run(tmp_path, program(wait_until(key("1"), timeout=0.5, id_="w"))).start()
    wait_for(lambda: run.status() == "waiting", 2)
    run.rt.pause()
    wait_for(lambda: run.status() == "paused", 2)
    time.sleep(0.8)  # longer than the timeout: the clock is stopped
    assert not run.rt.finished
    run.rt.resume()
    wait_for(lambda: run.status() == "waiting", 2)
    press(run, "1")
    assert run.done() == "completed"


def test_stop_cancels_the_motion_in_flight(tmp_path: Path) -> None:
    port = FakePort(duration=30)
    run = Run(tmp_path, program(play(A), play(B)), port=port).start()
    wait_for(lambda: len(port.submitted) == 1, 2)
    t0 = time.monotonic()
    run.rt.stop()
    assert run.done(2) == "stopped" and time.monotonic() - t0 < 1.0
    assert port.tickets[0].result is not None and port.tickets[0].result.outcome == "cancelled"
    assert port.kinds == [A]


@pytest.mark.parametrize(
    ("reason", "outcome"), [("estopped", "estopped"), ("deadman", "failed"), ("stopped", "stopped")]
)
def test_abort_ends_the_run_now(tmp_path: Path, reason: str, outcome: str) -> None:
    port = FakePort(duration=30)
    run = Run(tmp_path, program(forever(play(A))), port=port).start()
    wait_for(lambda: len(port.submitted) == 1, 2)
    t0 = time.monotonic()
    port.ended = True
    run.rt.abort(reason)
    assert run.rt.finished and time.monotonic() - t0 < 1.0
    assert run.rt.outcome == outcome and outcome_for(reason) == outcome
    assert run.lines()[-1]["data"]["outcome"] == outcome
    assert len(port.submitted) == 1  # never resumes by itself
    run.rt.abort("again")  # idempotent
    run.rt.resume()
    assert run.rt.outcome == outcome


def test_port_ending_with_the_estop_latched_is_an_estop(tmp_path: Path) -> None:
    port = FakePort(duration=30)
    run = Run(tmp_path, program(forever(play(A))), port=port, estopped=True).start()
    wait_for(lambda: len(port.submitted) == 1, 2)
    port.ended = True  # e.g. SimMotionPort.aborted follows the owner's e-stop in a dry run
    assert run.done(2) == "estopped"
    assert run.rt.state().message == "e-stop"


def test_abort_before_start_finishes_the_run(tmp_path: Path) -> None:
    run = Run(tmp_path, program(wait(1)))
    run.rt.abort("estopped")
    assert run.rt.finished and run.rt.outcome == "estopped"


# =========================================================================== faults and motions
def test_a_bad_value_is_a_fault(tmp_path: Path) -> None:
    doc = program(
        set_var("n", arith("DIVIDE", num(1), num(0), id_="div"), id_="s"), variables=[("n", "n", "Number")]
    )
    run = Run(tmp_path, doc).start()
    assert run.done() == "failed"
    faults = [ln for ln in run.lines() if ln["kind"] == "fault"]
    assert len(faults) == 1 and faults[0]["block_id"] == "div" and faults[0]["level"] == "error"
    assert list_runs(tmp_path, "ab")[0].faults == 1


def test_a_refused_motion_is_a_fault(tmp_path: Path) -> None:
    port = FakePort()
    port.refuse = StationError("needs_check", "calibration changed")
    run = Run(tmp_path, program(play(A, id_="p")), port=port).start()
    assert run.done() == "failed"
    assert run.rt.state().message == "calibration changed"


@pytest.mark.parametrize(("outcome", "expected"), [("timeout", "timeout"), ("failed", "failed")])
def test_motion_timeout_and_failure(tmp_path: Path, outcome: str, expected: str) -> None:
    run = Run(
        tmp_path, program(play(A), log(text("never"))), port=FakePort(outcomes={"play_trajectory": outcome})
    ).start()
    assert run.done() == expected


def test_run_model_until_cancels_when_the_condition_holds(tmp_path: Path) -> None:
    port = FakePort(duration=30)
    doc = program(run_model_until("act", key("1"), timeout=20, id_="rm"), log(text("done")))
    run = Run(tmp_path, doc, port=port).start()
    wait_for(lambda: len(port.submitted) == 1, 2)
    wait_for(lambda: (w := run.rt.state().waiting) is not None and w.kind == "run_model", 2)
    press(run, "1")
    assert run.done(3) == "completed"
    assert port.tickets[0].result.outcome == "cancelled"  # type: ignore[union-attr]


def test_run_model_timeout_runs_on_timeout(tmp_path: Path) -> None:
    port = FakePort(outcomes={"run_model": "timeout"})
    doc = program(
        run_model_until("act", key("1"), timeout=1, on_timeout=[log(text("gave up"))]), log(text("end"))
    )
    run = Run(tmp_path, doc, port=port).start()
    assert run.done() == "completed"
    assert [ln["message"] for ln in run.lines() if ln["kind"] == "log"] == ["gave up", "end"]


# =========================================================================== conditions, fakes, pacing
def test_dry_run_fakes_pick_the_branch(tmp_path: Path) -> None:
    doc = program(
        wait_until(sees("cubes", "blue"), timeout=5),
        if_([(sees("cubes", "red"), [play(A)]), (sees("cubes", "blue"), [play(B)])]),
    )
    run = Run(tmp_path, doc).start()
    wait_for(lambda: run.status() == "waiting", 2)
    run.rt.fake(ps.FakeConditions(detectors={"cubes": ps.FakeDetector(label="blue")}))
    assert run.done() == "completed" and run.port.kinds == [B]
    assert any(c.block_id for c in run.rt.state().conditions)


def test_fakes_are_refused_outside_dry_runs(tmp_path: Path) -> None:
    run = Run(tmp_path, program(wait(0.2)), dry_run=False).start()
    with pytest.raises(StationError) as e:
        run.rt.fake(ps.FakeConditions(gripper_holding=True))
    assert e.value.code == "validation_failed"
    run.done()


def test_condition_changes_are_logged_once(tmp_path: Path) -> None:
    run = Run(tmp_path, program(wait_until(key("1"), timeout=5, id_="w"))).start()
    time.sleep(0.5)  # ~5 evaluations, all false
    press(run, "1")
    run.done()
    conds = [ln for ln in run.lines() if ln["kind"] == "condition"]
    assert [c["data"]["value"] for c in conds] == [False, True]


def test_a_loop_without_waits_is_paced(tmp_path: Path) -> None:
    doc = program(
        while_(compare("LT", var("n"), num(5)), change("n", num(1))), variables=[("n", "n", "Number")]
    )
    run = Run(tmp_path, doc, hz=10).start()
    t0 = time.monotonic()
    assert run.done() == "completed"
    assert time.monotonic() - t0 >= 0.4  # 5 iterations at ≤ 10 Hz
    assert run.rt.state().variables["n"] == 5.0


def test_input_after_the_end_is_refused(tmp_path: Path) -> None:
    run = Run(tmp_path, keys_program(A, B)).start()
    run.rt.stop()
    run.done()
    with pytest.raises(StationError) as e:
        press(run, "1")
    assert e.value.code == "not_found"


def test_a_program_that_does_not_compile_cannot_run(tmp_path: Path) -> None:
    p = make_program(program(wait(1))).model_copy(update={"ast": None})
    with pytest.raises(StationError) as e:
        Interpreter(
            program=p,
            run_id=RUN,
            dry_run=True,
            runlog=RunLog(tmp_path, RUN, program_id="ab", version=1, dry_run=True),
            engine_factory=lambda *a: None,  # type: ignore[arg-type,return-value]
            signals=SignalBus(),
        )
    assert e.value.code == "program_invalid"


def test_run_files_are_private(tmp_path: Path) -> None:
    run = Run(tmp_path, program(log(text("x")))).start()
    run.done()
    path = tmp_path / "runs" / "programs" / f"{RUN}.jsonl"
    assert is_private(path) and is_private(path.parent, 0o700)
