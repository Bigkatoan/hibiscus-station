"""ProgramSession: the owner side of a program run, driven by a fake ProgramRuntime (team B's seam).

station-programs.md §5.1, §11, §12.3: one motion at a time submitted from the runner thread, the
same TrajectoryPlayer as ``playing``, robot snapshots for conditions, pause/wait phases, relax arm,
e-stop aborting the program within one tick, stop, dead-man, run model through the inferring path.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from conftest import (
    Heartbeat,
    connect_calibrated,
    fast_hand,
    mock_profile,
    press_estop_frozen_within_one_tick,
    wait_for,
)

from hibiscus_station.errors import StationError
from hibiscus_station.mock import get_world
from hibiscus_station.mock.policy import make_dummy_act
from hibiscus_station.models.importer import import_dir
from hibiscus_station.programs.interfaces import MotionPort, MotionResult, RobotSnapshot
from hibiscus_station.programs.schemas import (
    FakeConditions,
    GoHomeStmt,
    GripperStmt,
    MotionStmt,
    MoveToPoseStmt,
    OperatorInput,
    PlayTrajectoryStmt,
    PoseInput,
    ProgramState,
    RecordTrajectoryRequest,
    RelaxArmStmt,
    RunModelStmt,
    TrajectoryUpdate,
)
from hibiscus_station.programs.sim_port import sim_port_for_station
from hibiscus_station.programs.traj_service import start_program_session, start_record, stop_record
from hibiscus_station.sessions.program import ProgramSession
from hibiscus_station.sessions.run import RunSession
from hibiscus_station.station import Station

RUN_ID = "r_20261116_120000_abcd"
Script = Callable[["FakeRuntime", MotionPort], str]


class FakeRuntime:
    """A ProgramRuntime whose program is a Python function run in a ``program-runner`` thread."""

    def __init__(self, script: Script) -> None:
        self.script = script
        self.status = "starting"
        self.results: list[MotionResult | None] = []
        self.errors: list[StationError] = []
        self.snapshots: list[RobotSnapshot] = []
        self.aborted_with: str | None = None
        self.stopped_with: str | None = None
        self._outcome: str | None = None
        self._done = threading.Event()
        self.abort_event = threading.Event()
        self.thread: threading.Thread | None = None
        self.port: MotionPort | None = None

    # ---- ProgramRuntime
    def start(self, port: MotionPort) -> None:
        self.port = port
        self.status = "running"
        self.thread = threading.Thread(target=self._run, name="program-runner", daemon=True)
        self.thread.start()

    def _run(self) -> None:
        assert self.port is not None
        try:
            outcome = self.script(self, self.port)
        except Exception as exc:  # the runner reports failures as an outcome
            self.errors.append(exc)  # type: ignore[arg-type]
            outcome = "failed"
        if self._outcome is None:
            self._outcome = outcome
        self.status = self._outcome
        self._done.set()

    def pause(self) -> None:
        self.status = "paused"

    def resume(self) -> None:
        self.status = "running"

    def stop(self, reason: str = "stopped") -> None:
        self.stopped_with = reason

    def abort(self, reason: str) -> None:
        self.aborted_with = reason
        self.abort_event.set()
        if self._outcome is None:
            self._outcome = "estopped" if reason == "estopped" else "stopped"
        if self.thread is not None:
            self.thread.join(2.0)

    def input(self, ev: OperatorInput) -> None:
        return None

    def fake(self, fakes: FakeConditions) -> None:
        raise StationError("validation_failed", "not a dry run")

    @property
    def finished(self) -> bool:
        return self._done.is_set()

    @property
    def outcome(self) -> str | None:
        return self._outcome if self._done.is_set() else None

    def state(self) -> ProgramState:
        return ProgramState(
            run_id=RUN_ID,
            program_id="ab",
            version=1,
            dry_run=False,
            status=self.status,  # type: ignore[arg-type]
            block_id=None,
            block_kind=None,
            t=0.0,
            steps=len(self.results),
            variables={},
            conditions=[],
            waiting=None,
            ask=None,
            buttons=[],
            keys=[],
            message=None,
        )

    # ---- helpers for scripts
    def run(self, port: MotionPort, stmt: MotionStmt, timeout: float = 20.0) -> MotionResult | None:
        if port.aborted:
            return None
        try:
            h = port.submit(stmt)
        except StationError as exc:
            self.errors.append(exc)
            return None
        res = h.wait(timeout)
        self.results.append(res)
        self.snapshots.append(port.snapshot())
        return res


def _take(st: Station, name: str, seconds: float = 1.0) -> str:
    start_record(st, RecordTrajectoryRequest(name=name, countdown_s=0.1, limit_s=seconds + 5))
    get_world("mock://leader").hand = fast_hand(amplitude=120.0, hz=0.7)
    wait_for(lambda: st.owner.session is not None and st.owner.session.episode.phase == "capture", 5)
    time.sleep(seconds)
    tid = stop_record(st).id
    get_world("mock://leader").hand = None
    st.programs.trajectories().update(tid, TrajectoryUpdate(save=True))
    return tid


def _start(st: Station, rt: FakeRuntime) -> dict[str, Any]:
    return start_program_session(st, program_id="ab", runtime=rt, fps=30)


@pytest.fixture
def ready(connected: Station) -> Station:
    st = connected
    st.owner.call("set_rest_pose")
    st.programs.poses().replace(
        [PoseInput(name="bin", positions={"shoulder_pan.pos": 12.0, "elbow_flex.pos": 8.0})]
    )
    return st


def test_program_runs_motions_in_order(ready: Station) -> None:
    st = ready
    a, b = _take(st, "A"), _take(st, "B")
    seen_phases: list[str | None] = []

    def script(rt: FakeRuntime, port: MotionPort) -> str:
        rt.run(port, PlayTrajectoryStmt(id="blk_a", kind="play_trajectory", trajectory=a))
        rt.run(port, PlayTrajectoryStmt(id="blk_b", kind="play_trajectory", trajectory=b, speed_pct=50))
        rt.run(port, MoveToPoseStmt(id="blk_p", kind="move_to_pose", pose="bin", speed_deg_s=60))
        rt.run(port, GripperStmt(id="blk_g", kind="gripper", action="close"))
        rt.status = "waiting"
        time.sleep(0.4)
        seen_phases.append(st.owner.session.episode.phase if st.owner.session else None)
        rt.status = "running"
        rt.run(port, GoHomeStmt(id="blk_h", kind="go_home"))
        return "completed"

    rt = FakeRuntime(script)
    with Heartbeat(st):
        view = _start(st, rt)
        assert view["kind"] == "program" and view["program"] == "ab" and st.owner.state == "programming"
        wait_for(lambda: st.owner.state == "idle", 40)
    assert not rt.errors, rt.errors
    assert [r.outcome if r else None for r in rt.results] == ["completed"] * 5
    assert seen_phases == ["waiting"]
    summary = st.owner.last_session_summary
    assert summary is not None and summary["outcome"] == "completed" and summary["summary"]["motions"] == 5
    assert rt.aborted_with is None  # finished by itself: nothing to abort
    # snapshots: positions, goals after the SafetyFilter, telemetry, camera frames of the tick
    snap = rt.snapshots[2]
    assert snap.positions["shoulder_pan.pos"] == pytest.approx(12.0, abs=2.5)
    assert snap.goal["shoulder_pan.pos"] == pytest.approx(12.0, abs=0.5)
    assert snap.frames["wrist"].shape == (96, 128, 3) and snap.frame_tick > 0 and snap.tick > 0
    assert set(snap.temp_c) >= {"gripper", "shoulder_pan"} and "gripper" in snap.load_pct
    rest = st.owner.profile.follower.rest_pose  # type: ignore[union-attr]
    end = st.owner.call("read_positions")
    assert all(abs(end[k] - v) < 3 for k, v in rest.items() if k != "gripper.pos")  # type: ignore[union-attr]


def test_estop_aborts_the_program_within_one_tick(ready: Station) -> None:
    st = ready
    a = _take(st, "A", 2.0)
    started = threading.Event()

    def script(rt: FakeRuntime, port: MotionPort) -> str:
        h = port.submit(PlayTrajectoryStmt(id="blk_a", kind="play_trajectory", trajectory=a, speed_pct=25))
        started.set()
        rt.results.append(h.wait(30))
        # the program must not start anything after the e-stop
        rt.results.append(port.submit(GoHomeStmt(id="blk_h", kind="go_home")).wait(1))
        return "completed"

    rt = FakeRuntime(script)
    world = get_world("mock://follower")
    with Heartbeat(st):
        _start(st, rt)
        started.wait(5)
        wait_for(lambda: st.owner.session is not None and st.owner.session.episode.phase == "replay", 10)
        time.sleep(0.3)
        press_estop_frozen_within_one_tick(st, world)
    assert rt.aborted_with == "estopped"
    wait_for(lambda: len(rt.results) == 2, 3)
    assert rt.results[0] == MotionResult("aborted", "estopped")
    assert rt.results[1] is not None and rt.results[1].outcome == "aborted"
    assert st.owner.last_session_summary["summary"]["program_outcome"] == "estopped"  # type: ignore[index]
    st.owner.call("estop_reset")
    assert st.owner.state == "idle"  # it does not resume by itself


def test_stop_cancel_busy_and_refusals(ready: Station) -> None:
    st = ready
    a = _take(st, "A", 1.0)
    st.programs.trajectories()  # warm
    gate = threading.Event()

    def script(rt: FakeRuntime, port: MotionPort) -> str:
        # run_model until: the runner cancels it (a dry hold here is not used: real policy missing)
        try:
            port.submit(RunModelStmt(id="m", kind="run_model", model="nope", duration_s=1))
        except StationError as exc:
            rt.errors.append(exc)
        h = port.submit(PlayTrajectoryStmt(id="p", kind="play_trajectory", trajectory=a, speed_pct=10))
        try:
            port.submit(GoHomeStmt(id="h", kind="go_home"))
        except StationError as exc:
            rt.errors.append(exc)
        time.sleep(0.5)
        h.cancel()
        rt.results.append(h.wait(2))
        for bad in (
            PlayTrajectoryStmt(id="x", kind="play_trajectory", trajectory=a, speed_pct=140),
            MoveToPoseStmt(id="y", kind="move_to_pose", pose="nowhere"),
        ):
            try:
                port.submit(bad)
            except StationError as exc:
                rt.errors.append(exc)
        gate.wait(10)
        return "completed"

    rt = FakeRuntime(script)
    with Heartbeat(st):
        _start(st, rt)
        wait_for(lambda: len(rt.errors) == 4, 10)
        assert [e.code for e in rt.errors] == ["not_found", "busy", "fast_replay_not_allowed", "not_found"]
        res = rt.results[0]
        assert res is not None and res.outcome == "cancelled"
        assert st.owner.state == "programming"
        st.owner.call("control", action="stop")
        assert st.owner.state == "idle"
    gate.set()
    assert rt.aborted_with == "stopped"
    assert st.owner.last_session_summary["outcome"] == "stopped"  # type: ignore[index]


def test_relax_arm_then_the_next_motion_turns_torque_on(ready: Station) -> None:
    st = ready
    world = get_world("mock://follower")
    torque: list[bool] = []

    def script(rt: FakeRuntime, port: MotionPort) -> str:
        rt.run(port, RelaxArmStmt(id="r", kind="relax_arm"))
        torque.append(world.any_torque())
        rt.run(port, MoveToPoseStmt(id="m", kind="move_to_pose", pose="bin", speed_deg_s=60))
        torque.append(world.any_torque())
        return "completed"

    rt = FakeRuntime(script)
    with Heartbeat(st):
        _start(st, rt)
        wait_for(lambda: st.owner.state == "idle", 20)
    assert [r.outcome if r else None for r in rt.results] == ["completed", "completed"]
    assert torque == [False, True]


def test_runtime_failure_and_deadman(ready: Station) -> None:
    st = ready

    def boom(rt: FakeRuntime, port: MotionPort) -> str:
        raise StationError("internal_error", "runner bug")

    rt = FakeRuntime(boom)
    with Heartbeat(st):
        _start(st, rt)
        wait_for(lambda: st.owner.state == "idle", 5)
    assert st.owner.last_session_summary["outcome"] == "failed"  # type: ignore[index]

    def forever(rt: FakeRuntime, port: MotionPort) -> str:
        rt.abort_event.wait(10)
        return "stopped"

    rt = FakeRuntime(forever)
    _start(st, rt)  # no heartbeat
    wait_for(lambda: st.owner.state == "estopped", 4)
    assert st.owner.reason == "ui_lost" and rt.aborted_with == "estopped"
    st.owner.call("estop_reset")


def test_program_session_needs_a_factory() -> None:
    with pytest.raises(ValueError):
        ProgramSession(kind="program", fps=30)


def test_needs_check_trajectory_is_refused_in_a_program(ready: Station) -> None:
    st = ready
    a = _take(st, "A", 0.6)
    from hibiscus_station.programs.calibration_ref import calibration_file

    f = calibration_file(st.cal_root, st.owner.profile)  # type: ignore[arg-type]
    f.write_text(f.read_text(encoding="utf-8") + " ")

    def script(rt: FakeRuntime, port: MotionPort) -> str:
        rt.run(port, PlayTrajectoryStmt(id="p", kind="play_trajectory", trajectory=a))
        return "failed" if rt.errors else "completed"

    rt = FakeRuntime(script)
    with Heartbeat(st):
        _start(st, rt)
        wait_for(lambda: st.owner.state == "idle", 5)
    assert [e.code for e in rt.errors] == ["needs_check"]


def test_dry_run_port_does_not_touch_the_owner(ready: Station) -> None:
    st = ready
    a = _take(st, "A", 0.8)
    world = get_world("mock://follower")
    port = sim_port_for_station(st, 30, speedup=10)
    world.record_calls = True
    t0 = time.monotonic()
    try:
        with pytest.raises(StationError) as e:  # a dry run obeys the same profile rules
            port.submit(PlayTrajectoryStmt(id="p", kind="play_trajectory", trajectory=a, speed_pct=150))
        assert e.value.code == "fast_replay_not_allowed"
        h = port.submit(PlayTrajectoryStmt(id="p", kind="play_trajectory", trajectory=a))
        res = h.wait(10)
        assert res is not None and res.outcome == "completed"
        h = port.submit(RunModelStmt(id="m", kind="run_model", model="any", duration_s=0.5))
        res = h.wait(5)
        assert res is not None and res.outcome == "completed"  # no policy in a dry run: hold
        assert st.owner.state == "idle"
        assert not [t for t, _ in world.goal_writes() if t > t0]  # the real arm got nothing
        assert set(port.snapshot().frames) == {"wrist"}
        h = port.submit(RunModelStmt(id="m", kind="run_model", model="any", duration_s=30))
        st.owner.press_estop("user")
        res = h.wait(2)
        assert res is not None and res.outcome == "aborted" and port.aborted
    finally:
        port.close()
        wait_for(lambda: st.owner.state == "estopped", 3)
        st.owner.call("estop_reset")


def test_run_model_block_uses_the_inferring_path(
    tmp_path: Path, station: Station, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``run model for 0.6 s`` runs the inferring path (a ``RunSession`` episode) for 0.6 s of loop
    ticks at the session fps, as every episode does (a recorded episode is its frames). Its length
    is counted in those ticks, not in this thread's seconds: a loaded runner made the CPU inference
    overrun its ticks and the run took 1.686 s of wall time, the right 18 ticks."""
    st = station
    runs: list[RunSession] = []
    begin = RunSession.begin

    def tracked(self: RunSession, owner: Any, obs: Any) -> None:
        runs.append(self)
        begin(self, owner, obs)

    monkeypatch.setattr(RunSession, "begin", tracked)
    connect_calibrated(st, mock_profile())
    src = make_dummy_act(tmp_path / "act" / "pretrained_model", {"wrist": (96, 128)})
    entry = import_dir(st.registry, src, st.paths.staging, [tmp_path])
    job = st.load_model(entry.key, "cpu")
    st.jobs.wait(job.id)
    sessions: list[Any] = []

    def script(rt: FakeRuntime, port: MotionPort) -> str:
        # an explicit timeout: the automatic one (expected + 5 s of wall time) aborts a motion
        # that hangs, which a starved test host can look like; this test is about the path
        rt.run(port, RunModelStmt(id="m", kind="run_model", model=entry.key, duration_s=0.6, timeout_s=60))
        sessions.append(st.owner.session)
        h = port.submit(
            RunModelStmt(
                id="u", kind="run_model", model=entry.key, until={"id": "c", "kind": "bool", "value": False}
            )  # type: ignore[arg-type]
        )
        time.sleep(0.4)
        h.cancel()  # the runner's until condition became true
        rt.results.append(h.wait(3))
        return "completed"

    rt = FakeRuntime(script)
    with Heartbeat(st):
        _start(st, rt)
        wait_for(lambda: st.owner.state == "idle", 20)
    assert not rt.errors, rt.errors
    assert [r.outcome if r else None for r in rt.results] == ["completed", "cancelled"]
    res = rt.results[0]
    run = runs[0]
    assert run._episode_ticks == round(0.6 * run.fps), (run._episode_ticks, run.fps)
    # never shorter than its ticks at the session fps (the loop never runs faster than its fps)
    assert res is not None and res.elapsed_s >= (run._episode_ticks - 1) / run.fps * 0.98, res
    assert isinstance(sessions[0], ProgramSession)
