"""The seams between the three teams (station-programs.md "Implementation map" §3).

Only Protocols and small value types live here: each team implements its side in its own modules
and tests against fakes of the other side. A change to a signature here is a contract change.

Threads (station.md §4.2):

* **owner** — the HardwareOwner thread. ``MotionPrimitive.begin/step`` and every ``MotionSession``
  hook run here, inside the control tick. Nothing here may block, evaluate a detector or wait.
* **runner** — one ``program-runner`` thread per program run (team B). It walks the AST, evaluates
  conditions at ≤ ``settings.programs.condition_hz`` and talks to the owner only through
  :class:`MotionPort` (thread-safe, never blocks the owner).
* **api** — FastAPI handlers; they reach the owner through ``owner.call`` as everywhere else.

E-stop: the owner freezes the arm within the tick (station.md §4.7), then tears the session down;
``ProgramSession.end`` calls ``ProgramRuntime.abort`` and resolves every pending
:class:`MotionHandle` with ``aborted``. The runner also polls ``MotionPort.aborted`` between
statements, so no statement starts after an e-stop.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal, Protocol, runtime_checkable

from hibiscus_station.programs.schemas import (
    Detector,
    DetectorInput,
    DetectorResult,
    FakeConditions,
    MotionStmt,
    OperatorInput,
    Pose,
    PoseInput,
    Program,
    ProgramInput,
    ProgramLogLine,
    ProgramState,
    ProgramSummary,
    Scalar,
    Signal,
    SignalSource,
    Trajectory,
    TrajectoryDetail,
    TrajectorySummary,
    TrajectoryUpdate,
)

if TYPE_CHECKING:
    from pathlib import Path

    import numpy as np
    import numpy.typing as npt

    from hibiscus_station.hw.owner import HardwareOwner
    from hibiscus_station.profiles import RobotProfile
    from hibiscus_station.sessions.base import TickInput

    Frame = npt.NDArray[np.uint8]  # (h, w, 3) RGB, as CameraHub.read_latest_all returns it


# =========================================================================== team A: motion
MotionOutcome = Literal["completed", "cancelled", "timeout", "aborted", "failed"]


@dataclass(frozen=True)
class MotionResult:
    outcome: MotionOutcome
    detail: str | None = None
    elapsed_s: float = 0.0


@dataclass(frozen=True)
class TrajectorySamples:
    """``samples.parquet`` in memory (trim applied by the caller that asks for it)."""

    fps: int
    names: list[str]  # "shoulder_pan.pos" ... "gripper.pos"
    t: list[float]  # seconds from the first kept sample, strictly increasing
    rows: list[list[float]]  # len(rows) == len(t); len(row) == len(names)


@runtime_checkable
class MotionPrimitive(Protocol):
    """One motion driven tick by tick in the owner thread (a ``MotionSession`` delegates to it).

    ``step`` returns the goal for this tick (before the SafetyFilter, which the owner always applies)
    or ``None`` to send nothing (the follower holds). ``phase`` is the session sub-phase to show:
    ``approach`` while moving to the start, ``replay`` while playing, ``episode`` for a policy.
    """

    phase: Literal["approach", "replay", "episode"]
    done: bool
    outcome: MotionOutcome | None

    def begin(self, owner: HardwareOwner, obs: dict[str, float]) -> None: ...

    def step(self, owner: HardwareOwner, inp: TickInput) -> dict[str, float] | None: ...

    def cancel(self) -> None: ...


class TrajectoryPlayerFactory(Protocol):
    """``hibiscus_station.programs.player.TrajectoryPlayer`` (team A) has this constructor.

    Minimum-jerk approach at ``approach_speed_deg_s`` when any joint is more than
    ``approach_threshold_deg`` from the first sample; then the samples resampled by time scaling
    (``speed_pct`` 10-150, linear interpolation at the session fps, never skipped frames).
    """

    def __call__(
        self,
        samples: TrajectorySamples,
        *,
        speed_pct: float,
        fps: int,
        approach_speed_deg_s: float,
        approach_threshold_deg: float = 3.0,
    ) -> MotionPrimitive: ...


@dataclass(frozen=True)
class RobotSnapshot:
    """What the runner may read about the robot (copied in the owner thread after each tick)."""

    t: float  # seconds since the program started
    tick: int
    positions: dict[str, float]  # present position, "shoulder_pan.pos" -> degrees (gripper 0-100)
    goal: dict[str, float]  # last goal sent after the SafetyFilter (empty before the first send)
    load_pct: dict[str, float | None]  # follower motor -> last Present_Load, signed % (telemetry)
    temp_c: dict[str, float | None]  # follower motor -> last temperature
    frames: dict[str, Frame]  # camera -> latest frame (same arrays as the tick, never mutated)
    frame_tick: int
    stale_cameras: list[str] = field(default_factory=list)


class MotionHandle(Protocol):
    """A motion submitted by the runner. Thread-safe."""

    def wait(self, timeout: float | None = None) -> MotionResult | None:
        """Block the runner until the motion ends (``None`` if ``timeout`` passed first)."""
        ...

    def cancel(self) -> None:
        """Finish at the next tick, holding the current goal (``run_model ... until`` uses it)."""
        ...

    @property
    def result(self) -> MotionResult | None: ...


class MotionPort(Protocol):
    """Implemented by ``ProgramSession`` (team A); called from the runner thread (team B)."""

    @property
    def aborted(self) -> bool:
        """True once the session is ending (e-stop, stop, fault): run nothing more."""
        ...

    def submit(self, stmt: MotionStmt) -> MotionHandle:
        """Queue one motion statement; the owner starts it at the next tick. Raises
        ``StationError`` (``busy`` if a motion is already in flight, ``not_found`` for a missing
        trajectory/pose/model). ``RunModelStmt.until`` is ignored here: the runner evaluates it and
        calls ``cancel``."""
        ...

    def snapshot(self) -> RobotSnapshot: ...


class TrajectoryStore(Protocol):
    """``programs/trajectories.py`` (team A). One instance per robot profile
    (``TrajectoryStore(paths: RobotDataPaths, calibration_hash: Callable[[], str])``); thread-safe.
    Missing ids raise ``StationError("not_found")``. ``status`` is recomputed on read: a stored
    ``calibration_hash`` that differs from the current one gives ``needs_check``."""

    def all(self) -> list[TrajectorySummary]: ...

    def get(self, trajectory_id: str) -> Trajectory: ...

    def detail(self, trajectory_id: str) -> TrajectoryDetail: ...

    def samples(self, trajectory_id: str, *, trimmed: bool = True) -> TrajectorySamples: ...

    def create_draft(
        self,
        *,
        name: str,
        fps: int,
        samples: TrajectorySamples,
        keyframes: dict[str, list[bytes]],
        keyframe_times: list[float],
    ) -> Trajectory:
        """Write a new take (status ``draft``) with its suggested trim applied as the trim."""
        ...

    def update(self, trajectory_id: str, upd: TrajectoryUpdate) -> Trajectory: ...

    def delete(self, trajectory_id: str) -> None: ...

    def mark_checked(self, trajectory_id: str) -> Trajectory:
        """needs_check → ready with the current calibration hash (after a check replay)."""
        ...

    def keyframe(self, trajectory_id: str, camera: str, index: int) -> bytes: ...


class PoseStore(Protocol):
    """``programs/poses.py`` (team A): ``poses.json`` of one robot profile; thread-safe."""

    def all(self) -> list[Pose]: ...

    def get(self, name: str) -> Pose: ...

    def replace(self, poses: list[PoseInput]) -> list[Pose]: ...

    def capture(self, name: str, positions: dict[str, float]) -> Pose: ...


# =========================================================================== team B: program runtime
class ProgramRuntime(Protocol):
    """The interpreter of one run (team B, ``programs/interpreter.py``). Built by the Station for
    ``POST /programs/{id}/run`` and handed to ``ProgramSession`` (team A), which calls ``start``
    from ``begin``, ``abort`` from ``end``, and polls ``finished`` from ``poll``."""

    def start(self, port: MotionPort) -> None:
        """Spawn the runner thread. Never blocks."""
        ...

    def pause(self) -> None:
        """Finish the current motion statement, then wait (status ``pausing`` → ``paused``)."""
        ...

    def resume(self) -> None: ...

    def stop(self, reason: str = "stopped") -> None:
        """Ask the runner to stop after cancelling the motion in flight."""
        ...

    def abort(self, reason: str) -> None:
        """E-stop/fault: stop now, join the runner (≤ 2 s), write the end log line."""
        ...

    def input(self, ev: OperatorInput) -> None: ...

    def fake(self, fakes: FakeConditions) -> None:
        """Dry runs only (``StationError('validation_failed')`` otherwise)."""
        ...

    @property
    def finished(self) -> bool: ...

    @property
    def outcome(self) -> str | None:
        """completed | stopped | failed | estopped | timeout (None while running)."""
        ...

    def state(self) -> ProgramState: ...


ProgramRuntimeFactory = Callable[[], ProgramRuntime]


# =========================================================================== team B: conditions
class DetectorRuntime(Protocol):
    """A loaded detector (``programs/detectors.py``: ``load_detector(det, root) -> DetectorRuntime``).

    ``evaluate`` runs in the runner or an API worker thread, never in the owner thread; it must not
    keep a reference to ``frame``. Colour rules ~2 ms on 640x480; ONNX on CPU through onnxruntime.
    """

    def evaluate(self, frame: Frame, *, tick: int = -1) -> DetectorResult: ...

    def close(self) -> None: ...


class SignalBus(Protocol):
    """Process-wide external signals (``programs/signals.py``). Thread-safe; ``set`` publishes a
    ``signal`` WS message through the owner's ``emit``."""

    def set(self, name: str, value: Scalar, source: SignalSource) -> Signal: ...

    def get(self, name: str) -> Signal | None: ...

    def all(self) -> list[Signal]: ...

    @property
    def seq(self) -> int:
        """Counter of every ``set`` so far (``message_received`` compares against it)."""
        ...

    def last_seq(self, name: str, source: Literal["http", "mqtt"]) -> int:
        """``seq`` of the latest message on ``name`` from ``source`` (0 = none yet)."""
        ...

    def subscribe(self, fn: Callable[[Signal], None]) -> Callable[[], None]:
        """Call ``fn`` on every set; returns the unsubscribe function."""
        ...


class DetectorStore(Protocol):
    """``programs/detectors.py`` (team B): ``detectors/`` of one robot profile; thread-safe."""

    def all(self) -> list[Detector]: ...

    def get(self, detector_id: str) -> Detector: ...

    def put(self, detector_id: str, body: DetectorInput) -> Detector: ...

    def delete(self, detector_id: str) -> None: ...

    def set_model(self, detector_id: str, onnx: bytes) -> Detector: ...

    def runtime(self, detector_id: str) -> DetectorRuntime:
        """Loaded once and cached until the detector changes (``detector_invalid`` on failure)."""
        ...


class ProgramStore(Protocol):
    """``programs/store.py`` (team B): ``programs/`` of one robot profile; thread-safe."""

    def all(self) -> list[ProgramSummary]: ...

    def get(self, program_id: str) -> Program: ...

    def put(self, program_id: str, body: ProgramInput) -> Program:
        """Save as version + 1 and compile (``ast``/``issues`` filled)."""
        ...

    def delete(self, program_id: str) -> None: ...

    def mark_dry_run(self, program_id: str, version: int) -> None: ...


class RunLog(Protocol):
    """``runs/programs/<run_id>.jsonl`` writer (team B); every line is also emitted as
    ``program_log``. ``write`` fills ``run_id``, ``seq`` and ``t``."""

    def write(
        self,
        kind: str,
        message: str,
        *,
        level: Literal["info", "warn", "error"] = "info",
        block_id: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> ProgramLogLine: ...

    def close(self, outcome: str) -> None: ...


# =========================================================================== shared helpers (team A)
class CalibrationRef(Protocol):
    """``programs/calibration_ref.py`` (team A): ``calibration_hash(cal_root, profile) -> str``,
    sha256 (first 16 hex) of the follower calibration file bytes; ``"none"`` when missing. Stores
    compare it to mark trajectories and poses ``needs_check``; the validator (B) calls it too."""

    def __call__(self, cal_root: Path, profile: RobotProfile) -> str: ...
