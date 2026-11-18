"""Program validation against the live stores and the robot profile (station-programs.md §6).

The compiler (``compiler.py``) only knows the document. :func:`validate` adds what depends on the
Station: referenced trajectories, poses, detectors and models exist and still match the follower
calibration (``needs_check``), joints/motors/cameras exist on the robot, speed above 100 % is allowed
for this profile (and then needs a confirmation), ``go home`` / ``relax arm`` have a rest pose, and
the first motion starts within the approach limit from where the arm is now. ``check`` runs on the
saved version.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from hibiscus_station.errors import StationError
from hibiscus_station.programs.compiler import issue, iter_exprs, iter_stmts
from hibiscus_station.programs.schemas import (
    MOTION_KINDS,
    CheckIssue,
    CheckReport,
    Detector,
    GoHomeStmt,
    MoveToPoseStmt,
    PlayTrajectoryStmt,
    Pose,
    Program,
    ProgramAst,
    RelaxArmStmt,
    RunModelStmt,
    Trajectory,
)

if TYPE_CHECKING:
    from hibiscus_station.profiles import RobotProfile
    from hibiscus_station.station import Station

#: SO-101 motors (lerobot ``so101_follower``); used when no follower is connected to ask.
DEFAULT_MOTORS = ("shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll", "gripper")


@dataclass
class ValidationContext:
    """What the validator may look at (built from the Station by :func:`context_for`)."""

    trajectory: Callable[[str], Trajectory]
    pose: Callable[[str], Pose]
    detector: Callable[[str], Detector]
    model_exists: Callable[[str], bool]
    motors: list[str]
    cameras: list[str]
    rest_pose: dict[str, float] | None
    allow_fast_replay: bool
    max_approach_deg: float
    positions: dict[str, float] = field(default_factory=dict)  # present follower pose ({} = unknown)
    require_dry_run: bool = True


def _get(fn: Callable[[str], Any], key: str) -> Any | None:
    try:
        return fn(key)
    except StationError:
        return None


def _start_pose(stmt: Any, ctx: ValidationContext) -> dict[str, float] | None:
    kind = stmt.kind
    if kind == "play_trajectory":
        tr = _get(ctx.trajectory, stmt.trajectory)
        return dict(tr.start_pose) if tr is not None else None
    if kind == "move_to_pose":
        p = _get(ctx.pose, stmt.pose)
        return dict(p.positions) if p is not None else None
    return None


def validate_ast(ast: ProgramAst, ctx: ValidationContext) -> list[CheckIssue]:
    out: list[CheckIssue] = []
    seen: set[str] = set()

    def add(i: CheckIssue) -> None:
        if i.id not in seen:
            seen.add(i.id)
            out.append(i)

    motors = set(ctx.motors)
    first_motion: Any | None = None
    for s, _loops in iter_stmts(ast.body):
        if s.kind in MOTION_KINDS and first_motion is None:
            first_motion = s
        if isinstance(s, PlayTrajectoryStmt):
            tr = _get(ctx.trajectory, s.trajectory)
            if tr is None:
                add(issue("unknown_trajectory", "error", s.id, trajectory=s.trajectory))
            elif tr.status == "draft":
                add(issue("trajectory_draft", "error", s.id, trajectory=tr.name))
            elif tr.status == "needs_check":
                add(issue("trajectory_needs_check", "error", s.id, trajectory=tr.name))
            if s.speed_pct > 100:
                if ctx.allow_fast_replay:
                    add(issue("fast_replay", "confirm", s.id, speed=s.speed_pct))
                else:
                    add(issue("fast_replay_not_allowed", "error", s.id, speed=s.speed_pct))
        elif isinstance(s, MoveToPoseStmt):
            p = _get(ctx.pose, s.pose)
            if p is None:
                add(issue("unknown_pose", "error", s.id, pose=s.pose))
            elif p.needs_check:
                add(issue("pose_needs_check", "error", s.id, pose=s.pose))
        elif isinstance(s, GoHomeStmt | RelaxArmStmt):
            if not ctx.rest_pose:
                add(issue("no_rest_pose", "error", s.id))
        elif isinstance(s, RunModelStmt) and not ctx.model_exists(s.model):
            add(issue("unknown_model", "error", s.id, model=s.model))
    for e in iter_exprs(ast.body):
        k = e.kind
        if k in ("camera_sees", "detector_confidence"):
            det = _get(ctx.detector, e.detector)
            if det is None:
                add(issue("unknown_detector", "error", e.id, detector=e.detector))
                continue
            if det.spec.kind == "classifier" and det.model_file is None:
                add(issue("detector_no_model", "error", e.id, detector=det.name))
            label = getattr(e, "label", None)
            if label is not None and label not in det.labels:
                add(issue("unknown_label", "error", e.id, label=label, detector=det.name))
            cam = e.camera or det.spec.camera
            if ctx.cameras and cam not in ctx.cameras:
                add(issue("unknown_camera", "error", e.id, camera=cam))
        elif k == "near_pose":
            p = _get(ctx.pose, e.pose)
            if p is None:
                add(issue("unknown_pose", "error", e.id, pose=e.pose))
            elif p.needs_check:
                add(issue("pose_needs_check", "warning", e.id, pose=e.pose))
        elif k == "joint_value" and e.joint not in motors:
            add(issue("unknown_joint", "error", _owner_block(e.id), joint=e.joint))
        elif k == "motor_temp" and e.motor is not None and e.motor not in motors:
            add(issue("unknown_joint", "error", _owner_block(e.id), joint=e.motor))
    if first_motion is not None and ctx.positions:
        start = _start_pose(first_motion, ctx)
        if start:
            far = max(
                (
                    abs(v - ctx.positions[j])
                    for j, v in start.items()
                    if j in ctx.positions and j != "gripper.pos"
                ),
                default=0.0,
            )
            # Information, not a warning (field report 0.2.9, D-24): the player always approaches
            # the first sample slowly, so this only says what the run will do first.
            if far > ctx.max_approach_deg:
                add(
                    issue(
                        "first_motion_far",
                        "info",
                        first_motion.id,
                        deg=round(far, 1),
                        max_deg=ctx.max_approach_deg,
                    )
                )
    return out


def _owner_block(node_id: str) -> str:
    """``<block>:joint`` (a sub-node of ``hb_joint_compare``) → the block id the editor knows."""
    return node_id.split(":", 1)[0]


def check_program(program: Program, ctx: ValidationContext) -> CheckReport:
    """Compile issues (kept on the program) + validation issues → :class:`CheckReport`."""
    issues = list(program.issues)
    if program.ast is not None:
        known = {i.id for i in issues}
        issues += [i for i in validate_ast(program.ast, ctx) if i.id not in known]
    ok = program.ast is not None and not any(i.severity == "error" for i in issues)
    return CheckReport(
        ok=ok,
        version=program.version,
        issues=issues,
        ast=program.ast,
        dry_run_required=ctx.require_dry_run and program.dry_run_version != program.version,
    )


def blocking(report: CheckReport, confirmed: list[str]) -> list[CheckIssue]:
    """Issues that stop a run: errors, and confirmations that were not acknowledged."""
    acks = set(confirmed)
    return [
        i for i in report.issues if i.severity == "error" or (i.severity == "confirm" and i.id not in acks)
    ]


def context_for(station: Station, profile: RobotProfile) -> ValidationContext:
    hub = station.programs
    rid = profile.id
    owner = station.owner
    connected = owner.profile is not None and owner.profile.id == rid and owner.follower is not None
    motors = (
        list(owner.follower.bus.motors) if connected and owner.follower is not None else list(DEFAULT_MOTORS)
    )
    positions = (
        {k: float(v) for k, v in owner.last_obs.items() if k.endswith(".pos") and isinstance(v, int | float)}
        if connected
        else {}
    )
    detectors = hub.detectors(rid)
    return ValidationContext(
        trajectory=hub.trajectories(rid).get,
        pose=hub.poses(rid).get,
        detector=detectors.get,
        model_exists=lambda key: station.registry.get(key) is not None,
        motors=motors,
        cameras=list(profile.cameras),
        rest_pose=dict(profile.follower.rest_pose) if profile.follower.rest_pose else None,
        allow_fast_replay=profile.follower.allow_fast_replay,
        max_approach_deg=station.settings.safety.max_approach_deg,
        positions=positions,
        require_dry_run=station.settings.programs.require_dry_run,
    )
