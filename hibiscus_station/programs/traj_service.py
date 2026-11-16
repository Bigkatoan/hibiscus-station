"""Station-level operations for trajectories, poses and program sessions (team A).

The REST handlers (``api_trajectories.py``) call these; the programs service (team B) calls
:func:`start_program_session`. Hardware is only reached through ``owner.call`` (owner thread).
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from hibiscus_station.errors import StationError
from hibiscus_station.programs.motion import MotionFactory
from hibiscus_station.programs.player import TrajectoryPlayer
from hibiscus_station.programs.schemas import (
    PlayTrajectoryRequest,
    Pose,
    RecordTrajectoryRequest,
    Trajectory,
    TrajectoryDetail,
    TrajectoryUpdate,
)
from hibiscus_station.programs.trajectories import TrajectoryStore
from hibiscus_station.sessions.program import ProgramSession
from hibiscus_station.sessions.traj_play import TrajPlaySession
from hibiscus_station.sessions.traj_record import TrajRecordSession

if TYPE_CHECKING:
    from hibiscus_station.hw.owner import HardwareOwner
    from hibiscus_station.profiles import RobotProfile
    from hibiscus_station.programs.interfaces import ProgramRuntime
    from hibiscus_station.sessions.base import MotionSession
    from hibiscus_station.station import Station

STOP_WAIT_S = 15.0


def _profile(station: Station) -> RobotProfile:
    owner = station.owner
    if owner.profile is None or owner.follower is None:
        raise StationError("not_connected", "connect a robot first")
    return owner.profile


def store(station: Station) -> TrajectoryStore:
    s = station.programs.trajectories()
    if not isinstance(s, TrajectoryStore):  # pragma: no cover - the hub always builds this class
        raise StationError("internal_error", "unexpected trajectory store")
    return s


# =========================================================================== record
def start_record(station: Station, req: RecordTrajectoryRequest) -> dict[str, Any]:
    profile = _profile(station)
    limits = station.settings.programs
    if req.limit_s > limits.traj_max_s:
        raise StationError(
            "validation_failed",
            "take longer than the configured maximum",
            params={"max_s": limits.traj_max_s},
        )
    trajectories = station.programs.trajectories(profile.id)

    def build(owner: HardwareOwner) -> MotionSession:
        return TrajRecordSession(
            kind="traj_record",
            fps=req.fps,
            approach_s=station.settings.safety.smooth_approach_s,
            store=trajectories,
            name=req.name or "",
            limit_s=req.limit_s,
            countdown_s=req.countdown_s,
            keyframe_hz=req.keyframe_hz,
        )

    return station.owner.call(  # type: ignore[no-any-return]
        "start_session",
        kind="traj_record",
        build=build,
        needs_leader=True,
        leader_check_deg=station.settings.safety.max_approach_deg,
        timeout=10.0,
    )


def _last_take(station: Station) -> str | None:
    last = station.owner.last_session_summary
    if last is None or last.get("kind") != "traj_record":
        return None
    tid = last.get("summary", {}).get("trajectory")
    return str(tid) if tid else None


def stop_record(station: Station) -> TrajectoryDetail:
    """End the take and answer its draft (also when the time limit ended it a moment ago)."""
    owner = station.owner
    s = owner.session
    if isinstance(s, TrajRecordSession):
        owner.call("control", action="stop", timeout=STOP_WAIT_S)
        deadline = time.monotonic() + STOP_WAIT_S
        while owner.session is s and time.monotonic() < deadline:  # pragma: no cover - control is sync
            time.sleep(0.02)
        tid = s.trajectory_id
    else:
        tid = _last_take(station)
        if tid is None:
            raise StationError("busy", "no trajectory is being recorded", params={"state": owner.state})
    if tid is None:
        raise StationError("validation_failed", "the take was too short to save (fewer than 2 samples)")
    return store(station).detail(tid)


# =========================================================================== play
def _playing(station: Station, trajectory_id: str) -> bool:
    s = station.owner.session
    return isinstance(s, TrajPlaySession) and s.trajectory_id == trajectory_id


def refuse_if_playing(station: Station, trajectory_id: str) -> None:
    if _playing(station, trajectory_id):
        raise StationError(
            "busy",
            "this trajectory is playing",
            params={"state": station.owner.state, "trajectory": trajectory_id},
        )


def play(station: Station, trajectory_id: str, req: PlayTrajectoryRequest) -> dict[str, Any]:
    profile = _profile(station)
    st = store(station)
    tr = st.get(trajectory_id)
    settings = station.settings.programs
    speed = settings.check_speed_pct if req.check else req.speed_pct
    if tr.status == "needs_check" and not req.check:
        raise StationError(
            "needs_check",
            f"calibration changed: replay once with check=true ({settings.check_speed_pct:g} %) and confirm",
            params={"trajectory": tr.id, "check_speed_pct": settings.check_speed_pct},
        )
    if speed > 100 and not profile.follower.allow_fast_replay:
        raise StationError(
            "fast_replay_not_allowed",
            "speed above 100 % needs follower.allow_fast_replay in the robot profile",
            params={"speed_pct": speed},
        )
    samples = st.samples(trajectory_id)
    fps = tr.fps
    player = TrajectoryPlayer(
        samples,
        speed_pct=speed,
        fps=fps,
        approach_speed_deg_s=req.approach_speed_deg_s or settings.approach_speed_deg_s,
        approach_threshold_deg=settings.approach_threshold_deg,
    )

    def build(owner: HardwareOwner) -> MotionSession:
        return TrajPlaySession(
            kind="traj_play",
            fps=fps,
            player=player,
            trajectory_id=tr.id,
            speed_pct=speed,
            check=req.check,
            store=st,
        )

    return station.owner.call(  # type: ignore[no-any-return]
        "start_session", kind="traj_play", build=build, needs_leader=False, timeout=10.0
    )


def confirm(station: Station, trajectory_id: str) -> Trajectory:
    refuse_if_playing(station, trajectory_id)
    return store(station).confirm(trajectory_id)


def update(station: Station, trajectory_id: str, upd: TrajectoryUpdate) -> TrajectoryDetail:
    refuse_if_playing(station, trajectory_id)
    st = store(station)
    st.update(trajectory_id, upd)
    return st.detail(trajectory_id)


def delete(station: Station, trajectory_id: str) -> None:
    refuse_if_playing(station, trajectory_id)
    store(station).delete(trajectory_id)


# =========================================================================== poses
def capture_pose(station: Station, name: str) -> Pose:
    owner = station.owner
    _profile(station)
    if owner.state != "idle":
        raise StationError("busy", "capture a pose while idle", params={"state": owner.state})
    if not owner.follower_calibrated:
        raise StationError("not_calibrated", "calibrate the follower first", params={"arm": "follower"})
    positions: dict[str, float] = owner.call("read_positions")
    if not positions:
        raise StationError("not_connected", "no follower position yet")
    return station.programs.poses().capture(name, positions)


# =========================================================================== programs (team B entry)
def start_program_session(
    station: Station, *, program_id: str, runtime: ProgramRuntime, fps: int
) -> dict[str, Any]:
    """idle → programming: the runtime gets a ``ProgramSession`` as its ``MotionPort``.

    The motion factory is built here (stores, rest pose, fast-replay flag, the loaded policy), so
    ``run model`` reuses the ``inferring`` path and every motion obeys the profile's safety settings.
    """
    _profile(station)
    factory = MotionFactory.for_station(station, fps)

    def build(owner: HardwareOwner) -> MotionSession:
        return ProgramSession(
            kind="program", fps=fps, runtime=runtime, factory=factory, program_id=program_id
        )

    return station.owner.call(  # type: ignore[no-any-return]
        "start_session", kind="program", build=build, needs_leader=False, timeout=10.0
    )
