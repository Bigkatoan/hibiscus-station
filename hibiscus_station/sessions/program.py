"""A block program driving the arm (station-programs.md §5.1, state ``programming``).

``ProgramSession`` is the owner side of a run and implements ``programs.interfaces.MotionPort`` for the
program runner thread (team B's ``ProgramRuntime``):

* ``begin`` starts the runtime (``runtime.start(self)``);
* the runner calls :meth:`submit` with one motion statement; the owner starts it at the next tick and
  drives it tick by tick through a :class:`~hibiscus_station.programs.motion.MotionDriver` (the same
  ``TrajectoryPlayer`` / minimum-jerk code as ``playing``); every goal goes through the SafetyFilter;
* after each tick a :class:`~hibiscus_station.programs.interfaces.RobotSnapshot` is published for the
  runner's robot-state conditions;
* ``poll`` ends the session once ``runtime.finished``;
* ``end`` (inside ``stopping``, also after an e-stop) resolves every open motion with ``aborted`` and
  calls ``runtime.abort`` ("estopped" when the e-stop is latched). The program never resumes by itself.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from hibiscus_station.programs.interfaces import MotionResult, RobotSnapshot
from hibiscus_station.programs.motion import Built, MotionDriver, MotionFactory, MotionTicket
from hibiscus_station.sessions.base import MotionSession, TickInput

if TYPE_CHECKING:
    from hibiscus_station.hw.owner import HardwareOwner
    from hibiscus_station.programs.interfaces import ProgramRuntime
    from hibiscus_station.programs.schemas import MotionStmt

log = logging.getLogger(__name__)

STATE_POLL_S = 0.1  # how often the session phase follows the runtime status (≤ 10 Hz)
RUNTIME_PHASES = {"waiting": "waiting", "paused": "paused"}
OUTCOMES = {"completed", "stopped", "failed", "estopped", "timeout"}


@dataclass
class ProgramSession(MotionSession):
    runtime: ProgramRuntime | None = None
    factory: MotionFactory | None = None
    program_id: str | None = None
    driver: MotionDriver | None = None
    motions: int = 0
    _snapshot: RobotSnapshot | None = None
    _snap_lock: threading.Lock = field(default_factory=threading.Lock)
    _ending: threading.Event = field(default_factory=threading.Event)
    _frames: dict[str, Any] = field(default_factory=dict)
    _stale: list[str] = field(default_factory=list)
    _frame_tick: int = -1
    _tick: int = 0
    _load: dict[str, float | None] = field(default_factory=dict)
    _temp: dict[str, float | None] = field(default_factory=dict)
    _last_state_poll: float = -1.0
    _runtime_phase: str = "running"

    def __post_init__(self) -> None:
        self.deadman = True
        self.episode.of = 1
        if self.driver is None:
            if self.factory is None:
                raise ValueError("ProgramSession needs a MotionFactory or a MotionDriver")
            self.driver = MotionDriver(self.factory.build)

    @property
    def _drv(self) -> MotionDriver:
        if self.driver is None:  # pragma: no cover - set in __post_init__
            raise RuntimeError("no motion driver")
        return self.driver

    @property
    def _rt(self) -> ProgramRuntime:
        if self.runtime is None:  # pragma: no cover - built by the programs service
            raise RuntimeError("no program runtime")
        return self.runtime

    # ================================================================== MotionPort (runner thread)
    @property
    def aborted(self) -> bool:
        return self._ending.is_set() or self.finished

    def submit(self, stmt: MotionStmt) -> MotionTicket:
        if self.aborted:
            t = MotionTicket(stmt)
            t.resolve(MotionResult("aborted", "the program is ending"))
            return t
        return self._drv.submit(stmt)

    def snapshot(self) -> RobotSnapshot:
        with self._snap_lock:
            snap = self._snapshot
        if snap is None:
            return RobotSnapshot(
                t=0.0, tick=0, positions={}, goal={}, load_pct={}, temp_c={}, frames={}, frame_tick=-1
            )
        return snap

    # ================================================================== owner thread
    def begin(self, owner: HardwareOwner, obs: dict[str, Any]) -> None:
        self.set_phase("running")
        self._publish(owner, 0.0)
        self._rt.start(self)

    def _on_start(self, owner: HardwareOwner, built: Built) -> None:
        self.motions += 1
        self.policy_input = built.kind == "run_model"
        if not owner.follower_torque:  # after a relax arm: the next motion turns torque back on
            owner._torque_on()

    def _on_end(self, owner: HardwareOwner, built: Built, result: MotionResult) -> None:
        self.policy_input = False
        if getattr(built.primitive, "torque_off_after", False) and result.outcome == "completed":
            owner._torque_off()  # relax arm: parked at the rest pose, now limp

    def step(self, owner: HardwareOwner, inp: TickInput) -> dict[str, float] | None:
        self._frames = inp.frames
        self._stale = list(inp.stale)
        self._frame_tick = inp.tick
        self._tick = inp.tick
        drv = self._drv
        goal = drv.tick(
            owner,
            inp,
            on_start=lambda b: self._on_start(owner, b),
            on_end=lambda b, r: self._on_end(owner, b, r),
        )
        active = drv.active
        if active is not None:
            self.set_phase(active.primitive.phase)
        else:
            self.set_phase(self._runtime_phase)
        return goal

    def on_telemetry(self, line: dict[str, Any]) -> None:
        if line.get("arm") != "follower":
            return
        load = line.get("load_pct")
        temp = line.get("temp_c")
        if isinstance(load, dict) and load:
            self._load = {str(k): (float(v) if v is not None else None) for k, v in load.items()}
        if isinstance(temp, dict) and temp:
            self._temp = {str(k): (float(v) if v is not None else None) for k, v in temp.items()}

    def _publish(self, owner: HardwareOwner, now: float) -> None:
        snap = RobotSnapshot(
            t=round(now, 4),
            tick=self._tick,
            positions=dict(owner.last_obs),
            goal=dict(owner.last_sent),
            load_pct=dict(self._load),
            temp_c=dict(self._temp),
            frames=dict(self._frames),
            frame_tick=self._frame_tick,
            stale_cameras=list(self._stale),
        )
        with self._snap_lock:
            self._snapshot = snap

    def poll(self, owner: HardwareOwner, now: float) -> None:
        self._publish(owner, now)
        self.episode.elapsed_s = now
        rt = self._rt
        mono = time.monotonic()
        if mono - self._last_state_poll >= STATE_POLL_S:
            self._last_state_poll = mono
            try:
                status = rt.state().status
            except Exception:  # pragma: no cover - a runtime bug must not break the control loop
                log.exception("program state failed")
                status = "running"
            self._runtime_phase = RUNTIME_PHASES.get(status, "running")
            if self._drv.active is None:
                self.set_phase(self._runtime_phase)
        if rt.finished:
            outcome = rt.outcome or "completed"
            self.finish(outcome if outcome in OUTCOMES else "failed")

    def control(self, owner: HardwareOwner, action: str) -> None:
        if action == "stop":
            self._ending.set()
        super().control(owner, action)

    def end(self, owner: HardwareOwner, reason: str) -> None:
        self._ending.set()
        estopped = owner.estop.is_set
        why = "estopped" if estopped else reason
        self._drv.close("aborted", why)
        rt = self.runtime
        if rt is not None and not rt.finished:
            try:
                rt.abort(why)
            except Exception as exc:
                log.exception("program abort failed")
                self.summary["abort_error"] = str(exc)[:300]
        self.policy_input = False
        self.summary.update(
            {
                "program": self.program_id,
                "motions": self.motions,
                "program_outcome": rt.outcome if rt is not None else None,
            }
        )

    def view(self) -> dict[str, Any]:
        v = super().view()
        v["program"] = self.program_id
        return v
