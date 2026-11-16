"""Trajectories, poses and motion primitives without hardware (station-programs.md §2, §3, §12)."""

from __future__ import annotations

import itertools
import json
import math
import stat
import threading
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from conftest import wait_for

from hibiscus_station.errors import StationError
from hibiscus_station.profiles import FollowerProfile, RobotProfile
from hibiscus_station.programs.calibration_ref import NO_CALIBRATION, calibration_file, calibration_hash
from hibiscus_station.programs.interfaces import MotionPrimitive, MotionResult, TrajectorySamples
from hibiscus_station.programs.motion import (
    GRIPPER,
    Built,
    HoldMotion,
    MotionDriver,
    MotionFactory,
    PoseMove,
    min_jerk,
    min_jerk_duration,
)
from hibiscus_station.programs.paths import RobotDataPaths
from hibiscus_station.programs.player import TrajectoryPlayer, resample
from hibiscus_station.programs.poses import PoseStore
from hibiscus_station.programs.schemas import (
    GoHomeStmt,
    GripperStmt,
    MoveToPoseStmt,
    PlayTrajectoryStmt,
    PoseInput,
    RelaxArmStmt,
    RunModelStmt,
    TrajectoryUpdate,
    TrimRange,
)
from hibiscus_station.programs.sim_port import SimMotionPort
from hibiscus_station.programs.trajectories import (
    TrajectoryStore,
    apply_trim,
    max_joint_speed,
    series,
    suggest_trim,
)
from hibiscus_station.sessions.base import TickInput
from hibiscus_station.settings import ProgramSettings

NAMES = ["shoulder_pan.pos", "elbow_flex.pos", "gripper.pos"]
FPS = 30


def take(
    idle_start_s: float = 1.0, move_s: float = 1.0, idle_end_s: float = 1.0, fps: int = FPS
) -> TrajectorySamples:
    """Idle, then a 0 -> 30 degree cosine move on two joints, then idle."""
    n = round((idle_start_s + move_s + idle_end_s) * fps) + 1
    t = [i / fps for i in range(n)]
    rows = []
    for x in t:
        u = min(1.0, max(0.0, (x - idle_start_s) / move_s))
        s = 0.5 - 0.5 * math.cos(math.pi * u)
        rows.append([30.0 * s, -20.0 * s, 10.0 + 60.0 * s])
    return TrajectorySamples(fps=fps, names=list(NAMES), t=t, rows=rows)


class Cal:
    def __init__(self, value: str = "aaaa") -> None:
        self.value = value

    def __call__(self) -> str:
        return self.value


@pytest.fixture
def paths(tmp_path: Path) -> RobotDataPaths:
    p = RobotDataPaths(tmp_path / "home", "desk")
    p.ensure()
    return p


@pytest.fixture
def cal() -> Cal:
    return Cal()


@pytest.fixture
def trajs(paths: RobotDataPaths, cal: Cal) -> TrajectoryStore:
    return TrajectoryStore(paths, cal)


def tick(t: float, obs: dict[str, float], k: int = 0) -> TickInput:
    return TickInput(k, t, dict(obs), {}, [])


class Host:
    def __init__(self, last_sent: dict[str, float] | None = None) -> None:
        self.last_sent = dict(last_sent or {})


def drive(prim: Any, obs: dict[str, float], fps: int = FPS, max_s: float = 30.0) -> list[dict[str, float]]:
    """Run a primitive against an arm that reaches every goal at once."""
    host = Host()
    prim.begin(host, obs)
    goals: list[dict[str, float]] = []
    pos = dict(obs)
    k = 0
    while not prim.done and k < max_s * fps:
        g = prim.step(host, tick(k / fps, pos, k))
        if g:
            pos.update(g)
            host.last_sent = dict(g)
            goals.append(dict(g))
        k += 1
    return goals


# =========================================================================== calibration hash
def test_calibration_hash_follows_the_follower_file(tmp_path: Path) -> None:
    prof = RobotProfile(
        id="desk",
        name="Desk",
        follower=FollowerProfile(type="hibiscus_mock_follower", port="mock://f", calibration_id="desk_f"),
    )
    root = tmp_path / "cal"
    assert calibration_hash(root, prof) == NO_CALIBRATION
    f = calibration_file(root, prof)
    f.parent.mkdir(parents=True)
    f.write_text(json.dumps({"shoulder_pan": {"range_min": 100}}))
    h1 = calibration_hash(root, prof)
    assert len(h1) == 16 and h1 == calibration_hash(root, prof)
    f.write_text(json.dumps({"shoulder_pan": {"range_min": 101}}))
    assert calibration_hash(root, prof) != h1


# =========================================================================== trim, preview, series
def test_suggested_trim_cuts_idle_start_and_end() -> None:
    s = take(1.0, 1.0, 1.5)
    trim = suggest_trim(s, 0.5, 0.5)
    assert trim.start_s == pytest.approx(1.0, abs=2 / FPS)
    assert trim.end_s == pytest.approx(1.5, abs=4 / FPS)
    kept = apply_trim(s, trim)
    assert kept.t[0] == 0.0
    assert kept.t[-1] == pytest.approx(1.0, abs=6 / FPS)
    assert max(abs(v) for v in kept.rows[0][:2]) <= 0.5  # starts where the motion starts


def test_short_idle_is_not_trimmed_and_still_take_is_kept() -> None:
    assert suggest_trim(take(0.3, 1.0, 0.3), 0.5, 0.5) == TrimRange(start_s=0.0, end_s=0.0)
    still = TrajectorySamples(fps=FPS, names=["a.pos"], t=[i / FPS for i in range(90)], rows=[[1.0]] * 90)
    assert suggest_trim(still, 0.5, 0.5) == TrimRange(start_s=0.0, end_s=0.0)


def test_trim_that_leaves_one_sample_is_refused() -> None:
    s = take(0.0, 1.0, 0.0)
    with pytest.raises(StationError) as e:
        apply_trim(s, TrimRange(start_s=0.99, end_s=0.02))
    assert e.value.code == "validation_failed"


def test_series_is_decimated_and_keeps_the_last_sample() -> None:
    s = take(2.0, 20.0, 2.0, fps=50)  # 1201 samples
    out = series(s)
    assert len(out.t) <= 600 and out.t[-1] == pytest.approx(s.t[-1], abs=1e-3)
    assert set(out.joints) == set(NAMES) and all(len(v) == len(out.t) for v in out.joints.values())
    small = series(take(0.0, 0.2, 0.0))
    assert len(small.t) == 7


def test_max_joint_speed_ignores_the_gripper() -> None:
    s = take(0.0, 1.0, 0.0)
    # peak of 30 * (0.5 - 0.5 cos(pi u)) over 1 s is 30 * pi / 2 deg/s; gripper (60 units) not counted
    assert max_joint_speed(s) == pytest.approx(15 * math.pi, rel=0.02)


# =========================================================================== store
def test_create_draft_writes_the_layout(trajs: TrajectoryStore, paths: RobotDataPaths) -> None:
    jpg = b"\xff\xd8fake\xff\xd9"
    tr = trajs.create_draft(
        name="A", fps=FPS, samples=take(), keyframes={"wrist": [jpg, jpg]}, keyframe_times=[0.0, 1.0]
    )
    d = paths.trajectory_dir(tr.id)
    assert {p.name for p in d.iterdir()} == {"trajectory.json", "samples.parquet", "keyframes"}
    assert stat.S_IMODE(d.stat().st_mode) == 0o700
    assert stat.S_IMODE((d / "trajectory.json").stat().st_mode) == 0o600
    assert stat.S_IMODE((d / "samples.parquet").stat().st_mode) == 0o600
    assert tr.status == "draft" and tr.trim == tr.suggested_trim and tr.trim.start_s > 0.9
    assert tr.samples == len(take().t) and tr.raw_duration_s == pytest.approx(3.0)
    assert tr.duration_s == pytest.approx(3.0 - tr.trim.start_s - tr.trim.end_s, abs=1e-6)
    assert tr.end_pose["shoulder_pan.pos"] == pytest.approx(30.0, abs=0.5)  # within the idle band
    assert tr.calibration_hash == "aaaa" and tr.keyframe_cameras == ["wrist"]
    assert trajs.keyframe(tr.id, "wrist", 1) == jpg
    with pytest.raises(StationError) as e:
        trajs.keyframe(tr.id, "wrist", 2)
    assert e.value.code == "not_found"
    raw = trajs.samples(tr.id, trimmed=False)
    assert raw.names == NAMES and raw.rows == take().rows
    listed = trajs.all()
    assert [s.id for s in listed] == [tr.id] and all(len(v) == 64 for v in listed[0].preview.values())
    detail = trajs.detail(tr.id)
    assert len(detail.series.t) == tr.samples


def test_update_rename_trim_save_and_delete(trajs: TrajectoryStore) -> None:
    tr = trajs.create_draft(name="A", fps=FPS, samples=take(), keyframes={}, keyframe_times=[])
    up = trajs.update(
        tr.id, TrajectoryUpdate(name="Pick A", trim=TrimRange(start_s=0.0, end_s=0.0), save=True)
    )
    assert up.name == "Pick A" and up.status == "ready" and up.duration_s == pytest.approx(3.0)
    assert up.start_pose["shoulder_pan.pos"] == 0.0
    assert trajs.samples(tr.id).t[-1] == pytest.approx(3.0)
    with pytest.raises(StationError) as e:
        trajs.update(tr.id, TrajectoryUpdate(trim=TrimRange(start_s=2.0, end_s=1.0)))
    assert e.value.code == "validation_failed"
    trajs.delete(tr.id)
    assert trajs.all() == []
    for call in (lambda: trajs.get(tr.id), lambda: trajs.delete(tr.id)):
        with pytest.raises(StationError) as e:
            call()
        assert e.value.code == "not_found"


def test_bad_takes_are_refused(trajs: TrajectoryStore) -> None:
    bad = [
        TrajectorySamples(fps=FPS, names=["a.pos"], t=[0.0], rows=[[1.0]]),
        TrajectorySamples(fps=FPS, names=["a.pos"], t=[0.0, 0.0], rows=[[1.0], [2.0]]),
        TrajectorySamples(fps=FPS, names=["a.pos"], t=[0.0, 0.1], rows=[[1.0], [math.nan]]),
        TrajectorySamples(fps=FPS, names=["a.pos", "a.pos"], t=[0.0, 0.1], rows=[[1.0, 1.0], [2.0, 2.0]]),
    ]
    for s in bad:
        with pytest.raises(StationError) as e:
            trajs.create_draft(name="x", fps=FPS, samples=s, keyframes={}, keyframe_times=[])
        assert e.value.code == "validation_failed"
    with pytest.raises(StationError):
        trajs.create_draft(name="x", fps=FPS, samples=take(), keyframes={"wrist": [b"x"]}, keyframe_times=[])


def test_calibration_change_marks_needs_check_until_confirmed(trajs: TrajectoryStore, cal: Cal) -> None:
    tr = trajs.create_draft(name="A", fps=FPS, samples=take(), keyframes={}, keyframe_times=[])
    trajs.update(tr.id, TrajectoryUpdate(save=True))
    cal.value = "bbbb"
    assert trajs.get(tr.id).status == "needs_check"
    assert trajs.all()[0].status == "needs_check"
    with pytest.raises(StationError) as e:
        trajs.confirm(tr.id)
    assert e.value.code == "needs_check"
    trajs.note_check_replay(tr.id)
    ok = trajs.confirm(tr.id)
    assert ok.status == "ready" and ok.calibration_hash == "bbbb" and ok.checked_at is not None
    assert trajs.confirm(tr.id).status == "ready"  # idempotent
    cal.value = "cccc"
    trajs.note_check_replay(tr.id)
    cal.value = "dddd"  # recalibrated again after the check replay: not good enough
    with pytest.raises(StationError):
        trajs.confirm(tr.id)


def test_a_broken_take_does_not_hide_the_others(trajs: TrajectoryStore, paths: RobotDataPaths) -> None:
    a = trajs.create_draft(name="A", fps=FPS, samples=take(), keyframes={}, keyframe_times=[])
    b = trajs.create_draft(name="B", fps=FPS, samples=take(), keyframes={}, keyframe_times=[])
    paths.trajectory_samples(a.id).write_bytes(b"not parquet")
    (paths.trajectories / "junk").mkdir()
    assert [s.id for s in trajs.all()] == [b.id]


def test_store_is_thread_safe(trajs: TrajectoryStore) -> None:
    errors: list[BaseException] = []

    def work() -> None:
        try:
            for _ in range(3):
                tr = trajs.create_draft(
                    name="T", fps=FPS, samples=take(0, 0.5, 0), keyframes={}, keyframe_times=[]
                )
                trajs.update(tr.id, TrajectoryUpdate(name="T2"))
                trajs.all()
        except BaseException as exc:  # pragma: no cover - reported below
            errors.append(exc)

    threads = [threading.Thread(target=work) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors and len(trajs.all()) == 12


# =========================================================================== poses
def test_poses_replace_capture_and_needs_check(paths: RobotDataPaths, cal: Cal) -> None:
    poses = PoseStore(paths, cal)
    assert poses.all() == []
    out = poses.replace([PoseInput(name="home", positions={"shoulder_pan.pos": 0.0})])
    created = out[0].created_at
    assert out[0].calibration_hash == "aaaa" and not out[0].needs_check
    assert stat.S_IMODE(paths.poses.stat().st_mode) == 0o600
    cal.value = "bbbb"
    assert poses.get("home").needs_check
    out = poses.replace(
        [
            PoseInput(name="home", positions={"shoulder_pan.pos": 0.0}),
            PoseInput(name="above_bin", positions={"shoulder_pan.pos": 40.0}, source="trajectory_end"),
        ]
    )
    home = next(p for p in out if p.name == "home")
    assert home.created_at == created and home.needs_check  # unchanged pose keeps its calibration
    assert next(p for p in out if p.name == "above_bin").calibration_hash == "bbbb"
    live = poses.capture("home", {"shoulder_pan.pos": 5.123456, "gripper.pos": 30.0})
    assert live.source == "live" and live.positions["shoulder_pan.pos"] == 5.123 and not live.needs_check
    assert {p.name for p in poses.all()} == {"home", "above_bin"}
    with pytest.raises(StationError) as e:
        poses.get("nowhere")
    assert e.value.code == "not_found"
    for bad in (
        [PoseInput(name="a", positions={"x.pos": 1.0}), PoseInput(name="a", positions={"x.pos": 2.0})],
        [PoseInput(name="a", positions={"shoulder_pan": 1.0})],
        [PoseInput(name="a", positions={})],
        [PoseInput(name="a", positions={"x.pos": math.inf})],
    ):
        with pytest.raises(StationError) as e:
            poses.replace(bad)
        assert e.value.code == "validation_failed"
    with pytest.raises(StationError):
        poses.capture("Bad Name", {"x.pos": 1.0})


# =========================================================================== minimum jerk + player
def test_min_jerk_profile() -> None:
    assert min_jerk(0.0) == 0.0 and min_jerk(1.0) == 1.0 and min_jerk(0.5) == pytest.approx(0.5)
    assert min_jerk(-1) == 0.0 and min_jerk(2) == 1.0
    xs = [min_jerk(i / 100) for i in range(101)]
    assert all(b >= a for a, b in itertools.pairwise(xs))
    # zero speed at both ends
    assert min_jerk(0.001) < 1e-7 and 1 - min_jerk(0.999) < 1e-7
    assert min_jerk_duration({"a": 0.0}, {"a": 30.0}, 30.0) == pytest.approx(1.875)
    assert min_jerk_duration({"a": 0.0}, {"a": 0.1}, 30.0) == pytest.approx(0.3)  # floor
    assert min_jerk_duration({"a": 0.0}, {"b": 90.0}, 30.0) == pytest.approx(0.3)  # unknown joint


def test_pose_move_peak_speed_hold_and_settle() -> None:
    move = PoseMove({"a.pos": 60.0}, 30.0)
    assert isinstance(move, MotionPrimitive)
    host = Host({"b.pos": 7.0})
    move.begin(host, {"a.pos": 0.0, "b.pos": 5.0})
    goals = []
    for k in range(int(10 * FPS)):
        g = move.step(host, tick(k / FPS, {"a.pos": goals[-1]["a.pos"] if goals else 0.0, "b.pos": 5.0}))
        if g is None:
            break
        goals.append(g)
        if move.done:
            break
    assert move.outcome == "completed"
    assert all(g["b.pos"] == 7.0 for g in goals)  # other joints hold their last goal
    a = [g["a.pos"] for g in goals]
    peak = max(abs(y - x) for x, y in itertools.pairwise(a)) * FPS
    assert peak <= 30.0 * 1.01 and a[-1] == pytest.approx(60.0)
    assert len(goals) / FPS == pytest.approx(3.75, abs=0.1)
    # a gripper closing on an object never reaches 0: completes after the settle time anyway
    grip = PoseMove({GRIPPER: 0.0}, 150.0)
    grip.begin(Host(), {GRIPPER: 80.0})
    k = 0
    while not grip.done:
        grip.step(Host(), tick(k / FPS, {GRIPPER: 25.0}))
        k += 1
    assert grip.outcome == "completed" and k / FPS == pytest.approx(grip.duration_s + grip.settle_s, abs=0.1)
    grip.cancel()
    assert grip.outcome == "completed"


def test_resample_time_scaling() -> None:
    s = take(0.0, 2.0, 0.0)  # 61 samples, 2 s
    assert np.allclose(resample(s, 100, FPS), s.rows)
    slow = resample(s, 50, FPS)
    assert len(slow) == 121 and slow[-1] == pytest.approx(s.rows[-1])
    assert slow[2] == pytest.approx(s.rows[1])  # tick 2 at 50 % shows source time 1/30 s
    fast = resample(s, 150, FPS)
    assert len(fast) == 41 and fast[-1] == pytest.approx(s.rows[-1])  # 2 s at 150 % = 40 ticks
    odd = resample(take(0.0, 1.0, 0.0), 70, FPS)  # 42.86 ticks: the closing sample is added
    assert len(odd) == 44 and odd[-1] == pytest.approx(take(0.0, 1.0, 0.0).rows[-1])
    other_fps = resample(s, 100, 50)
    assert len(other_fps) == 101 and other_fps[-1] == pytest.approx(s.rows[-1])
    for bad in (5, 151):
        with pytest.raises(ValueError):
            resample(s, bad, FPS)


def test_player_replays_without_approach_when_near() -> None:
    s = take(0.0, 1.0, 0.0)
    p = TrajectoryPlayer(s, speed_pct=50, fps=FPS, approach_speed_deg_s=30)
    assert isinstance(p, MotionPrimitive)
    start = dict(zip(NAMES, s.rows[0], strict=True))
    goals = drive(p, {k: v + 1.0 for k, v in start.items()})  # 1 degree away: no approach
    assert p.outcome == "completed" and p.approach is None
    assert len(goals) == 61 and goals[-1] == pytest.approx(dict(zip(NAMES, s.rows[-1], strict=True)))
    assert p.replay_s == pytest.approx(2.0)


def test_player_approaches_first_at_the_capped_speed() -> None:
    s = take(0.0, 1.0, 0.0)
    p = TrajectoryPlayer(s, speed_pct=100, fps=FPS, approach_speed_deg_s=30, approach_threshold_deg=3)
    host = Host()
    obs = {"shoulder_pan.pos": -45.0, "elbow_flex.pos": 0.0, "gripper.pos": 10.0}
    p.begin(host, obs)
    assert p.phase == "approach" and p.expected_s > 2.8 + 1.0
    phases, pans = [], []
    pos = dict(obs)
    k = 0
    while not p.done:
        g = p.step(host, tick(k / FPS, pos))
        phases.append(p.phase)
        if g:
            pos.update(g)
            pans.append(g["shoulder_pan.pos"])
        k += 1
    assert phases[0] == "approach" and phases[-1] == "replay"
    n_approach = phases.index("replay") + 1
    approach = pans[:n_approach]
    assert max(abs(b - a) for a, b in itertools.pairwise(approach)) * FPS <= 30 * 1.01
    assert approach[-1] == pytest.approx(0.0)
    assert len(pans) - n_approach == 31 and pans[-1] == pytest.approx(30.0)


def test_player_cancel_stops_sending() -> None:
    p = TrajectoryPlayer(take(0.0, 1.0, 0.0), speed_pct=100, fps=FPS, approach_speed_deg_s=30)
    host = Host()
    p.begin(host, {n: 0.0 for n in NAMES} | {GRIPPER: 10.0})
    assert p.step(host, tick(0.0, {})) is not None
    p.cancel()
    assert p.done and p.outcome == "cancelled" and p.step(host, tick(0.1, {})) is None
    with pytest.raises(ValueError):
        TrajectoryPlayer(
            TrajectorySamples(fps=FPS, names=["a.pos"], t=[], rows=[]),
            speed_pct=100,
            fps=FPS,
            approach_speed_deg_s=30,
        )


# =========================================================================== driver + factory
def _factory(trajs: TrajectoryStore, poses: PoseStore, **kw: Any) -> MotionFactory:
    return MotionFactory(
        trajectories=trajs,
        poses=poses,
        settings=ProgramSettings(),
        fps=FPS,
        rest_pose=kw.pop("rest_pose", {"shoulder_pan.pos": 0.0, "elbow_flex.pos": 0.0, GRIPPER: 0.0}),
        **kw,
    )


def test_driver_runs_one_motion_at_a_time_with_cancel_and_timeout() -> None:
    def build(stmt: Any) -> Built:
        return Built(HoldMotion(stmt.duration_s), stmt.timeout_s, stmt.kind)

    drv = MotionDriver(build)
    host = Host()
    t1 = drv.submit(RunModelStmt(id="b1", kind="run_model", model="m", duration_s=0.2))
    with pytest.raises(StationError) as e:
        drv.submit(RunModelStmt(id="b2", kind="run_model", model="m", duration_s=0.2))
    assert e.value.code == "busy"
    assert t1.wait(0) is None and t1.result is None
    k = 0
    while t1.result is None:
        drv.tick(host, tick(k / FPS, {}))
        k += 1
    assert t1.result.outcome == "completed" and t1.result.elapsed_s == pytest.approx(0.2, abs=0.05)
    t2 = drv.submit(RunModelStmt(id="b2", kind="run_model", model="m", duration_s=10))
    drv.tick(host, tick(1.0, {}))
    t2.cancel()
    drv.tick(host, tick(1.1, {}))
    assert t2.wait(1) == MotionResult("cancelled", "run_model: cancelled", pytest.approx(0.1))  # type: ignore[arg-type]
    t3 = drv.submit(RunModelStmt(id="b3", kind="run_model", model="m", duration_s=10, timeout_s=0.5))
    drv.tick(host, tick(2.0, {}))
    drv.tick(host, tick(2.6, {}))
    assert t3.result is not None and t3.result.outcome == "timeout"
    t4 = drv.submit(RunModelStmt(id="b4", kind="run_model", model="m", duration_s=10))
    drv.close("aborted", "estopped")
    assert t4.result == MotionResult("aborted", "estopped")
    t5 = drv.submit(RunModelStmt(id="b5", kind="run_model", model="m", duration_s=10))
    assert t5.result is not None and t5.result.outcome == "aborted"


def test_factory_resolves_statements_and_refuses_unsafe_ones(
    trajs: TrajectoryStore, paths: RobotDataPaths, cal: Cal
) -> None:
    poses = PoseStore(paths, cal)
    poses.replace([PoseInput(name="bin", positions={"shoulder_pan.pos": 40.0})])
    tr = trajs.create_draft(name="A", fps=FPS, samples=take(), keyframes={}, keyframe_times=[])
    f = _factory(trajs, poses)
    b = f.build(PlayTrajectoryStmt(id="p", kind="play_trajectory", trajectory=tr.id, speed_pct=50))
    assert isinstance(b.primitive, TrajectoryPlayer) and b.primitive.speed_pct == 50 and b.timeout_s is None
    with pytest.raises(StationError) as e:
        f.build(PlayTrajectoryStmt(id="p", kind="play_trajectory", trajectory=tr.id, speed_pct=120))
    assert e.value.code == "fast_replay_not_allowed"
    assert _factory(trajs, poses, allow_fast_replay=True).build(
        PlayTrajectoryStmt(id="p", kind="play_trajectory", trajectory=tr.id, speed_pct=120)
    )
    move = f.build(MoveToPoseStmt(id="m", kind="move_to_pose", pose="bin", speed_deg_s=20))
    assert move.primitive.target == {"shoulder_pan.pos": 40.0} and move.primitive.speed == 20
    assert f.build(GripperStmt(id="g", kind="gripper", action="open")).primitive.target == {GRIPPER: 100.0}
    assert f.build(GripperStmt(id="g", kind="gripper", action="close")).primitive.target == {GRIPPER: 0.0}
    assert f.build(GripperStmt(id="g", kind="gripper", action="set", percent=40)).primitive.target == {
        GRIPPER: 40.0
    }
    with pytest.raises(StationError):
        f.build(GripperStmt(id="g", kind="gripper", action="set"))
    assert not f.build(GoHomeStmt(id="h", kind="go_home")).primitive.torque_off_after
    assert f.build(RelaxArmStmt(id="r", kind="relax_arm")).primitive.torque_off_after
    hold = f.build(RunModelStmt(id="r", kind="run_model", model="m", duration_s=2)).primitive
    assert isinstance(hold, HoldMotion) and hold.duration_s == 2 and not hold.timeout_outcome
    until = f.build(
        RunModelStmt(id="r", kind="run_model", model="m", until={"id": "c", "kind": "bool", "value": True})  # type: ignore[arg-type]
    )
    assert until.primitive.duration_s == 30 and until.primitive.timeout_outcome and until.timeout_s is None
    no_rest = _factory(trajs, poses, rest_pose=None)
    for stmt in (GoHomeStmt(id="h", kind="go_home"), RelaxArmStmt(id="r", kind="relax_arm")):
        with pytest.raises(StationError) as e:
            no_rest.build(stmt)
        assert e.value.params["code"] == "no_rest_pose"
    for stmt in (
        PlayTrajectoryStmt(id="p", kind="play_trajectory", trajectory="t_20260101_000000_abcd"),
        MoveToPoseStmt(id="m", kind="move_to_pose", pose="nowhere"),
    ):
        with pytest.raises(StationError) as e:
            f.build(stmt)
        assert e.value.code == "not_found"
    cal.value = "recalibrated"
    for stmt in (
        PlayTrajectoryStmt(id="p", kind="play_trajectory", trajectory=tr.id),
        MoveToPoseStmt(id="m", kind="move_to_pose", pose="bin"),
    ):
        with pytest.raises(StationError) as e:
            f.build(stmt)
        assert e.value.code == "needs_check"


# =========================================================================== dry runs
def test_sim_port_plays_a_trajectory_and_aborts_on_estop(
    trajs: TrajectoryStore, paths: RobotDataPaths, cal: Cal
) -> None:
    tr = trajs.create_draft(name="A", fps=FPS, samples=take(0.0, 1.0, 0.0), keyframes={}, keyframe_times=[])
    estop = threading.Event()
    port = SimMotionPort(
        _factory(trajs, PoseStore(paths, cal)),
        start_pose={"shoulder_pan.pos": 10.0, "elbow_flex.pos": 0.0, GRIPPER: 10.0},
        cameras={"wrist": (96, 128, 3)},
        estop=estop.is_set,
        speedup=20,
    )
    try:
        snap = port.snapshot()
        assert snap.frames["wrist"].shape == (96, 128, 3) and snap.temp_c["gripper"] == 30.0
        h = port.submit(PlayTrajectoryStmt(id="p", kind="play_trajectory", trajectory=tr.id))
        res = h.wait(10)
        assert res is not None and res.outcome == "completed", res
        snap = port.snapshot()
        assert snap.positions["shoulder_pan.pos"] == pytest.approx(30.0)
        assert snap.goal["shoulder_pan.pos"] == pytest.approx(30.0) and snap.tick > 0
        relax = port.submit(RelaxArmStmt(id="r", kind="relax_arm"))
        assert relax.wait(10) is not None and not port.torque
        h = port.submit(RunModelStmt(id="m", kind="run_model", model="m", duration_s=60))
        wait_for(lambda: port.torque, 2)  # the next motion turns torque back on
        estop.set()
        res = h.wait(2)
        assert res is not None and res.outcome == "aborted" and port.aborted
        late = port.submit(GoHomeStmt(id="h", kind="go_home"))
        assert late.result is not None and late.result.outcome == "aborted"
    finally:
        port.close()
    assert not port._thread.is_alive()
