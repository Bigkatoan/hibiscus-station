"""SimMotionPort: the ``MotionPort`` of a dry run (station-programs.md §5.2, §11 "Dry runs").

A dry run never touches the HardwareOwner and never changes the Station state. The program runner
talks to this port exactly as it talks to ``ProgramSession``; motions are the same primitives
(``TrajectoryPlayer``, minimum-jerk moves) driven by the same :class:`MotionDriver`, on a simulated
arm in a ``sim-arm`` thread at the program fps:

* the sim arm reaches each goal after the SafetyFilter (relative-target cap) at once;
* ``run model`` holds for its duration (no policy is loaded for a dry run);
* cameras are synthetic grey frames (team B's ``FakeConditions`` decide what the camera "sees");
* ``aborted`` follows the owner's e-stop: a press during a dry run aborts it within one sim tick.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

import numpy as np

from hibiscus_station.hw.safety import SafetyFilter
from hibiscus_station.programs.interfaces import MotionResult, RobotSnapshot
from hibiscus_station.programs.motion import MotionDriver, MotionFactory, MotionTicket
from hibiscus_station.sessions.base import TickInput

if TYPE_CHECKING:
    from hibiscus_station.programs.schemas import MotionStmt
    from hibiscus_station.station import Station

SIM_TEMP_C = 30.0
DEFAULT_POSE = {
    "shoulder_pan.pos": 0.0,
    "shoulder_lift.pos": 0.0,
    "elbow_flex.pos": 0.0,
    "wrist_flex.pos": 0.0,
    "wrist_roll.pos": 0.0,
    "gripper.pos": 50.0,
}


class _SimHost:
    """The part of the HardwareOwner a primitive reads."""

    def __init__(self) -> None:
        self.last_sent: dict[str, float] = {}


class SimMotionPort:
    """``programs.interfaces.MotionPort`` on a simulated arm. Call :meth:`close` when the run ends."""

    def __init__(
        self,
        factory: MotionFactory,
        *,
        start_pose: dict[str, float] | None = None,
        cameras: dict[str, tuple[int, int, int]] | None = None,
        estop: Callable[[], bool] | None = None,
        max_relative_target: float | dict[str, float] | None = 5.0,
        speedup: float = 1.0,
    ) -> None:
        self.fps = factory.fps
        self.driver = MotionDriver(factory.build)
        self.positions: dict[str, float] = dict(start_pose or DEFAULT_POSE)
        self.host = _SimHost()
        self.safety = SafetyFilter(max_relative_target)
        self.estop = estop or (lambda: False)
        self.speedup = max(1.0, float(speedup))
        self.frames: dict[str, Any] = {
            name: np.full(shape, 127, dtype=np.uint8) for name, shape in (cameras or {}).items()
        }
        self.torque = True
        self.tick_count = 0
        self.t = 0.0
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._closed = False
        self._snapshot = self._snap()
        self._thread = threading.Thread(target=self._run, name="sim-arm", daemon=True)
        self._thread.start()

    # ---- MotionPort (runner thread)
    @property
    def aborted(self) -> bool:
        return self._closed or self.estop()

    def submit(self, stmt: MotionStmt) -> MotionTicket:
        if self.aborted:
            t = MotionTicket(stmt)
            t.resolve(MotionResult("aborted", "e-stop" if self.estop() else "the dry run is over"))
            return t
        return self.driver.submit(stmt)

    def snapshot(self) -> RobotSnapshot:
        with self._lock:
            return self._snapshot

    # ---- lifecycle
    def close(self, detail: str = "the dry run is over") -> None:
        self._closed = True
        self._stop.set()
        if threading.current_thread() is not self._thread:
            self._thread.join(timeout=2.0)
        self.driver.close("aborted", detail)

    # ---- sim thread
    def _snap(self) -> RobotSnapshot:
        return RobotSnapshot(
            t=round(self.t, 4),
            tick=self.tick_count,
            positions=dict(self.positions),
            goal=dict(self.host.last_sent),
            load_pct={k.removesuffix(".pos"): 0.0 for k in self.positions},
            temp_c={k.removesuffix(".pos"): SIM_TEMP_C for k in self.positions},
            frames=dict(self.frames),
            frame_tick=self.tick_count,
        )

    def _on_end(self, built: Any, result: MotionResult) -> None:
        if getattr(built.primitive, "torque_off_after", False) and result.outcome == "completed":
            self.torque = False

    def _on_start(self, built: Any) -> None:
        self.torque = True

    def step_once(self) -> None:
        """One sim tick (the thread calls it at ``fps``; tests may call it directly)."""
        if self.estop():
            self.driver.close("aborted", "estopped")
            return
        inp = TickInput(self.tick_count, self.t, dict(self.positions), dict(self.frames), [])
        goal = self.driver.tick(self.host, inp, on_start=self._on_start, on_end=self._on_end)
        if goal and self.torque:
            safe, _ = self.safety.apply(goal, self.positions)
            self.positions.update(safe)
            self.host.last_sent = safe
        self.tick_count += 1
        self.t = self.tick_count / self.fps
        snap = self._snap()
        with self._lock:
            self._snapshot = snap

    def _run(self) -> None:
        period = 1.0 / self.fps / self.speedup
        nxt = time.perf_counter()
        while not self._stop.is_set():
            self.step_once()
            nxt += period
            delay = nxt - time.perf_counter()
            if delay > 0:
                self._stop.wait(delay)
            else:
                nxt = time.perf_counter()


def sim_port_for_station(station: Station, fps: int, *, speedup: float = 1.0) -> SimMotionPort:
    """The dry-run port of the connected (or active) profile, starting from the last known pose."""
    factory = MotionFactory.for_station(station, fps, policy=False)
    owner = station.owner
    start = dict(owner.last_obs) if owner.last_obs else None
    profile = owner.profile or station.profiles.get(station.programs.robot_id())
    shapes: dict[str, tuple[int, int, int]] = {}
    if profile is not None:
        shapes = {n: (c.height, c.width, 3) for n, c in profile.cameras.items()}
    rel = profile.follower.max_relative_target if profile is not None else None
    return SimMotionPort(
        factory,
        start_pose=start,
        cameras=shapes,
        estop=lambda: owner.estop.is_set,
        max_relative_target=rel if rel is not None else station.settings.safety.max_relative_target,
        speedup=speedup,
    )
