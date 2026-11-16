"""Motion primitives and the motion driver (station-programs.md §3.2, §5, implementation map §3).

Everything here runs one tick at a time in the thread that drives the arm: the HardwareOwner thread
for real runs (``ProgramSession``, ``TrajectoryPlaySession``), the sim thread for dry runs
(``SimMotionPort``). A primitive returns the goal of the tick **before** the SafetyFilter; the caller
always applies the filter (relative-target cap, calibrated range clamp) before anything is sent.

* :class:`PoseMove`: minimum-jerk move to a joint target at a capped peak speed (move to pose, go
  home, gripper, and the trajectory approach).
* :class:`HoldMotion`: hold for a while (``run model`` in a dry run).
* :class:`PolicyMotion`: the ``inferring`` code path (``sessions/run.py``) for ``run model``.
* :class:`MotionDriver`: one statement in flight at a time, submitted from the runner thread,
  started at the next tick, with cancel, timeout and abort.
* :class:`MotionFactory`: ``MotionStmt`` → primitive, resolving trajectories, poses and the rest pose.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal, Protocol

from hibiscus_station.errors import StationError
from hibiscus_station.programs.interfaces import (
    MotionOutcome,
    MotionPrimitive,
    MotionResult,
    PoseStore,
    TrajectoryStore,
)
from hibiscus_station.programs.schemas import (
    GoHomeStmt,
    GripperStmt,
    MotionStmt,
    MoveToPoseStmt,
    PlayTrajectoryStmt,
    RelaxArmStmt,
    RunModelStmt,
)

if TYPE_CHECKING:
    from hibiscus_station.hw.owner import HardwareOwner
    from hibiscus_station.sessions.base import TickInput
    from hibiscus_station.sessions.run import RunSession
    from hibiscus_station.settings import ProgramSettings
    from hibiscus_station.station import Station

Phase = Literal["approach", "replay", "episode"]
GRIPPER = "gripper.pos"
GRIPPER_OPEN = 100.0
GRIPPER_CLOSED = 0.0
GRIPPER_SPEED = 150.0  # gripper range units (0-100) per second at the peak of the move
MIN_MOVE_S = 0.3
SETTLE_TOL_DEG = 2.0
SETTLE_S = 0.5
AUTO_TIMEOUT_MARGIN_S = 5.0
RUN_MODEL_UNTIL_TIMEOUT_S = 30.0


class MotionHost(Protocol):
    """What a primitive may read from the thread that drives it (the HardwareOwner has it)."""

    last_sent: dict[str, float]


def joint_positions(obs: dict[str, Any]) -> dict[str, float]:
    return {k: float(v) for k, v in obs.items() if k.endswith(".pos") and isinstance(v, (int, float))}


# =========================================================================== minimum jerk
def min_jerk(tau: float) -> float:
    """Normalised minimum-jerk profile s(τ) = 10τ³ - 15τ⁴ + 6τ⁵ (zero speed and acceleration at both ends)."""
    x = min(1.0, max(0.0, tau))
    return x * x * x * (10.0 + x * (-15.0 + 6.0 * x))


def min_jerk_duration(
    start: dict[str, float], target: dict[str, float], speed: float, *, min_s: float = MIN_MOVE_S
) -> float:
    """Duration whose peak speed (1.875 * D / T for minimum jerk) is ``speed`` on the joint that moves
    the most. Joints missing from ``start`` do not count."""
    if speed <= 0:
        raise ValueError("speed must be positive")
    dist = max((abs(v - start[k]) for k, v in target.items() if k in start), default=0.0)
    return max(min_s, 1.875 * dist / speed)


@dataclass
class PoseMove:
    """Minimum-jerk move from the present position to ``target`` with a peak speed of ``speed``.

    Joints of the arm that are not in ``target`` hold their last goal. The move completes once the
    profile has ended and every target joint is within ``settle_tol`` of it, or ``settle_s`` later
    (a gripper closing on an object never reaches its target: that is expected).
    """

    target: dict[str, float]
    speed: float
    phase: Phase = "approach"
    settle_tol: float = SETTLE_TOL_DEG
    settle_s: float = SETTLE_S
    min_s: float = MIN_MOVE_S
    torque_off_after: bool = False  # relax arm: the driver cuts torque once parked
    done: bool = False
    outcome: MotionOutcome | None = None
    duration_s: float = 0.0
    _start: dict[str, float] = field(default_factory=dict)
    _hold: dict[str, float] = field(default_factory=dict)
    _t0: float | None = None

    @property
    def expected_s(self) -> float:
        return self.duration_s + self.settle_s

    def begin(self, owner: MotionHost, obs: dict[str, float]) -> None:
        present = joint_positions(obs)
        self._start = {k: present[k] for k in self.target if k in present}
        self._hold = {k: owner.last_sent.get(k, v) for k, v in present.items() if k not in self.target}
        self.duration_s = min_jerk_duration(self._start, self.target, self.speed, min_s=self.min_s)

    def goal_at(self, elapsed: float) -> dict[str, float]:
        s = min_jerk(elapsed / self.duration_s) if self.duration_s > 0 else 1.0
        goal = dict(self._hold)
        for k, v in self.target.items():
            a = self._start.get(k, v)
            goal[k] = a + (v - a) * s
        return goal

    def settled(self, obs: dict[str, Any]) -> bool:
        present = joint_positions(obs)
        return all(abs(present[k] - v) <= self.settle_tol for k, v in self.target.items() if k in present)

    def step(self, owner: MotionHost, inp: TickInput) -> dict[str, float] | None:
        if self.done:
            return None
        if self._t0 is None:
            self._t0 = inp.t
        elapsed = inp.t - self._t0
        goal = self.goal_at(elapsed)
        if elapsed >= self.duration_s and (
            self.settled(inp.obs) or elapsed >= self.duration_s + self.settle_s
        ):
            self.done = True
            self.outcome = "completed"
        return goal

    def cancel(self) -> None:
        if not self.done:
            self.done = True
            self.outcome = "cancelled"


@dataclass
class HoldMotion:
    """Send nothing (the follower holds) for ``duration_s``: ``run model`` in a dry run."""

    duration_s: float | None
    phase: Phase = "episode"
    timeout_outcome: bool = False  # the ``until`` form ends by timeout when nothing cancels it
    done: bool = False
    outcome: MotionOutcome | None = None
    _t0: float | None = None

    @property
    def expected_s(self) -> float:
        return self.duration_s or 0.0

    def begin(self, owner: MotionHost, obs: dict[str, float]) -> None:
        return None

    def step(self, owner: MotionHost, inp: TickInput) -> dict[str, float] | None:
        if self.done:
            return None
        if self._t0 is None:
            self._t0 = inp.t
        if self.duration_s is not None and inp.t - self._t0 >= self.duration_s:
            self.done = True
            self.outcome = "timeout" if self.timeout_outcome else "completed"
        return None

    def cancel(self) -> None:
        if not self.done:
            self.done = True
            self.outcome = "cancelled"


@dataclass
class PolicyMotion:
    """``run model [policy] for [N] s / until [cond]``: a one-episode ``RunSession`` without countdown,
    driven tick by tick (same inference, stale-camera and slow-model rules as ``inferring``)."""

    run: RunSession
    until: bool = False  # the until form: reaching ``episode_time_s`` is a timeout
    phase: Phase = "episode"
    done: bool = False
    outcome: MotionOutcome | None = None

    @property
    def expected_s(self) -> float:
        return self.run.episode_time_s

    def begin(self, owner: HardwareOwner, obs: dict[str, float]) -> None:
        self.run.begin(owner, obs)

    def step(self, owner: HardwareOwner, inp: TickInput) -> dict[str, float] | None:
        if self.done:
            return None
        self.run.poll(owner, inp.t)  # countdown 0 -> episode; episode time reached -> finished
        if self.run.finished:
            self.done = True
            self.outcome = "timeout" if self.until else "completed"
            return None
        return self.run.step(owner, inp)

    def cancel(self) -> None:
        if not self.done:
            self.done = True
            self.outcome = "cancelled"


# =========================================================================== driver
class MotionTicket:
    """``programs.interfaces.MotionHandle``: one submitted statement. Thread-safe."""

    def __init__(self, stmt: MotionStmt) -> None:
        self.stmt = stmt
        self._done = threading.Event()
        self._lock = threading.Lock()
        self._result: MotionResult | None = None
        self.cancel_requested = False

    def wait(self, timeout: float | None = None) -> MotionResult | None:
        if self._done.wait(timeout):
            return self._result
        return None

    def cancel(self) -> None:
        self.cancel_requested = True

    @property
    def result(self) -> MotionResult | None:
        return self._result

    def resolve(self, result: MotionResult) -> bool:
        with self._lock:
            if self._result is not None:
                return False
            self._result = result
        self._done.set()
        return True


@dataclass
class Built:
    """A statement turned into a primitive (``timeout_s`` None = expected duration + 5 s)."""

    primitive: Any  # MotionPrimitive; PoseMove & co. accept a narrower host than HardwareOwner
    timeout_s: float | None
    kind: str


@dataclass
class _Active:
    built: Built
    ticket: MotionTicket
    t0: float
    deadline: float | None


class MotionDriver:
    """At most one statement in flight. ``submit`` runs in the runner thread and never blocks the
    driving thread; ``tick`` runs in the driving thread once per control tick."""

    def __init__(self, build: Callable[[MotionStmt], Built]) -> None:
        self.build = build
        self._lock = threading.Lock()
        self._pending: tuple[Built, MotionTicket] | None = None
        self._active: _Active | None = None
        self.closed = False
        self.last_result: MotionResult | None = None

    # ---- runner thread
    def submit(self, stmt: MotionStmt) -> MotionTicket:
        ticket = MotionTicket(stmt)
        if self.closed:
            ticket.resolve(MotionResult("aborted", "the session is ending"))
            return ticket
        with self._lock:
            if self._pending is not None or self._active is not None:
                raise StationError("busy", "a motion is already running")
        built = self.build(stmt)  # store reads happen here, never in the control tick
        with self._lock:
            if self.closed:
                ticket.resolve(MotionResult("aborted", "the session is ending"))
                return ticket
            if self._pending is not None or self._active is not None:
                raise StationError("busy", "a motion is already running")
            self._pending = (built, ticket)
        return ticket

    # ---- driving thread
    @property
    def active(self) -> Built | None:
        a = self._active
        return a.built if a is not None else None

    @property
    def busy(self) -> bool:
        return self._pending is not None or self._active is not None

    def tick(
        self,
        host: Any,
        inp: TickInput,
        *,
        on_start: Callable[[Built], None] | None = None,
        on_end: Callable[[Built, MotionResult], None] | None = None,
    ) -> dict[str, float] | None:
        a = self._active
        if a is None:
            with self._lock:
                nxt, self._pending = self._pending, None
            if nxt is None:
                return None
            built, ticket = nxt
            if on_start is not None:
                on_start(built)
            built.primitive.begin(host, joint_positions(inp.obs))
            timeout = built.timeout_s
            if timeout is None:
                timeout = float(getattr(built.primitive, "expected_s", 0.0)) + AUTO_TIMEOUT_MARGIN_S
            a = self._active = _Active(built, ticket, inp.t, inp.t + timeout)
        prim = a.built.primitive
        forced: MotionOutcome | None = None
        if a.ticket.cancel_requested:
            forced = "cancelled"
        elif a.deadline is not None and inp.t >= a.deadline:
            forced = "timeout"
        goal: dict[str, float] | None = None
        if forced is not None:
            prim.cancel()
        else:
            goal = prim.step(host, inp)
        if prim.done or forced is not None:
            outcome: MotionOutcome = forced or prim.outcome or "completed"
            detail = None if outcome == "completed" else f"{a.built.kind}: {outcome}"
            result = MotionResult(outcome, detail, round(inp.t - a.t0, 3))
            self._active = None
            if on_end is not None:
                on_end(a.built, result)
            self.last_result = result
            a.ticket.resolve(result)
        return goal

    def close(self, outcome: MotionOutcome = "aborted", detail: str | None = None) -> None:
        """Resolve every open ticket (session teardown, e-stop); later submits answer ``aborted``."""
        with self._lock:
            self.closed = True
            pending, self._pending = self._pending, None
        a, self._active = self._active, None
        if a is not None:
            a.built.primitive.cancel()
            a.ticket.resolve(MotionResult(outcome, detail))
        if pending is not None:
            pending[1].resolve(MotionResult(outcome, detail))


# =========================================================================== factory
@dataclass
class MotionFactory:
    """``MotionStmt`` → :class:`Built` for one robot profile (used by ``ProgramSession`` and
    ``SimMotionPort``). ``policy`` builds ``run model``; ``None`` holds instead (dry runs)."""

    trajectories: TrajectoryStore
    poses: PoseStore
    settings: ProgramSettings
    fps: int
    rest_pose: dict[str, float] | None
    allow_fast_replay: bool = False
    policy: Callable[[RunModelStmt], MotionPrimitive] | None = None

    def player(self, stmt: PlayTrajectoryStmt) -> Built:
        from hibiscus_station.programs.player import TrajectoryPlayer

        tr = self.trajectories.get(stmt.trajectory)
        if tr.status == "needs_check":
            raise StationError(
                "needs_check",
                "calibration changed: replay this trajectory at low speed and confirm it first",
                params={"trajectory": tr.id},
            )
        if stmt.speed_pct > 100 and not self.allow_fast_replay:
            raise StationError(
                "fast_replay_not_allowed",
                "speed above 100 % needs follower.allow_fast_replay",
                params={"speed_pct": stmt.speed_pct},
            )
        samples = self.trajectories.samples(stmt.trajectory)
        prim = TrajectoryPlayer(
            samples,
            speed_pct=stmt.speed_pct,
            fps=self.fps,
            approach_speed_deg_s=self.settings.approach_speed_deg_s,
            approach_threshold_deg=self.settings.approach_threshold_deg,
        )
        return Built(prim, stmt.timeout_s, stmt.kind)

    def _rest(self) -> dict[str, float]:
        if not self.rest_pose:
            raise StationError(
                "validation_failed",
                "this robot has no rest pose: set one first",
                params={"code": "no_rest_pose"},
            )
        return dict(self.rest_pose)

    def build(self, stmt: MotionStmt) -> Built:
        speed = self.settings.approach_speed_deg_s
        if isinstance(stmt, PlayTrajectoryStmt):
            return self.player(stmt)
        if isinstance(stmt, MoveToPoseStmt):
            pose = self.poses.get(stmt.pose)
            if pose.needs_check:
                raise StationError(
                    "needs_check", "calibration changed since this pose was saved", params={"pose": pose.name}
                )
            return Built(PoseMove(dict(pose.positions), stmt.speed_deg_s), stmt.timeout_s, stmt.kind)
        if isinstance(stmt, GripperStmt):
            if stmt.action == "open":
                pct = GRIPPER_OPEN
            elif stmt.action == "close":
                pct = GRIPPER_CLOSED
            else:
                if stmt.percent is None:
                    raise StationError("validation_failed", "gripper set needs a percent")
                pct = float(stmt.percent)
            return Built(PoseMove({GRIPPER: pct}, GRIPPER_SPEED), stmt.timeout_s, stmt.kind)
        if isinstance(stmt, GoHomeStmt):
            return Built(PoseMove(self._rest(), speed), stmt.timeout_s, stmt.kind)
        if isinstance(stmt, RelaxArmStmt):
            return Built(PoseMove(self._rest(), speed, torque_off_after=True), stmt.timeout_s, stmt.kind)
        if isinstance(stmt, RunModelStmt):
            if (stmt.duration_s is None) == (stmt.until is None):
                raise StationError("validation_failed", "run model needs exactly one of duration / until")
            limit = stmt.duration_s or stmt.timeout_s or RUN_MODEL_UNTIL_TIMEOUT_S
            until = stmt.until is not None
            # the until form ends by timeout at ``limit`` inside the primitive; leave the driver margin
            timeout = None if until else stmt.timeout_s
            if self.policy is None:
                return Built(HoldMotion(limit, timeout_outcome=until), timeout, stmt.kind)
            return Built(self.policy(stmt), timeout, stmt.kind)
        raise StationError("validation_failed", f"not a motion statement: {stmt!r}")  # pragma: no cover

    @classmethod
    def for_station(cls, station: Station, fps: int, *, policy: bool = True) -> MotionFactory:
        """The factory of the connected profile (``policy=False`` for dry runs)."""
        hub = station.programs
        profile = station.owner.profile or station.profiles.get(hub.robot_id())
        if profile is None:
            raise StationError("not_connected", "add a robot profile first")
        return cls(
            trajectories=hub.trajectories(profile.id),
            poses=hub.poses(profile.id),
            settings=station.settings.programs,
            fps=fps,
            rest_pose=dict(profile.follower.rest_pose) if profile.follower.rest_pose else None,
            allow_fast_replay=profile.follower.allow_fast_replay,
            policy=(lambda stmt: policy_motion(station, stmt, fps)) if policy else None,
        )


def policy_motion(station: Station, stmt: RunModelStmt, fps: int) -> PolicyMotion:
    """``run model``: the loaded policy, checked against the connected robot like ``start_run``."""
    from hibiscus_station.models import compat
    from hibiscus_station.sessions.run import RunSession

    profile = station.owner.profile
    if profile is None or station.owner.follower is None:
        raise StationError("not_connected", "connect a robot first")
    entry = station.registry.get(stmt.model)
    if entry is None:
        raise StationError("not_found", f"no model {stmt.model}", params={"model": stmt.model})
    lp = station.loaded
    if lp is None or lp.key != entry.key:
        raise StationError("model_not_loaded", "load the model first", params={"model": entry.key})
    report = compat.check(entry, profile, None, device=lp.device)
    if not report["ok"]:
        raise StationError(
            "model_incompatible",
            "the model does not match this robot",
            errors=[c for c in report["checks"] if not c["ok"]],
        )
    until = stmt.until is not None
    limit = stmt.duration_s or stmt.timeout_s or RUN_MODEL_UNTIL_TIMEOUT_S
    motors = [f"{m}.pos" for m in station.owner.follower.bus.motors]
    run = RunSession(
        kind="run",
        fps=fps,
        task=stmt.task or entry.task or "",
        model=entry.key,
        loaded=lp,
        camera_map=report["camera_map"],
        num_episodes=1,
        episode_time_s=limit,
        countdown_s=0.0,
        robot_type=station.owner.follower.robot_type,
    )
    run.build_features(motors, station.hub.shapes())
    return PolicyMotion(run, until=until)
