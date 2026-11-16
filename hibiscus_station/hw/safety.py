"""SafetyFilter, EStop latch and dead-man Watchdog (spec §4.7)."""

from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass


class SafetyFilter:
    """Clamp ``goal - obs`` per joint (``ensure_safe_goal_position`` semantics) and into the range.

    The observation is the one already read in step 1 of the tick: no extra bus read.
    """

    def __init__(
        self,
        max_relative_target: float | Mapping[str, float] | None,
        ranges: Mapping[str, tuple[float, float]] | None = None,
    ) -> None:
        if isinstance(max_relative_target, int):
            max_relative_target = float(max_relative_target)
        self.max_rel = max_relative_target
        self.ranges = dict(ranges or {})
        self.clip_window: deque[tuple[float, bool]] = deque(maxlen=600)

    def _cap(self, key: str) -> float | None:
        if self.max_rel is None:
            return None
        if isinstance(self.max_rel, float):
            return self.max_rel
        motor = key.removesuffix(".pos")
        val = self.max_rel.get(motor, self.max_rel.get(key))
        return float(val) if val is not None else None

    def apply(
        self, action: Mapping[str, float], obs: Mapping[str, object]
    ) -> tuple[dict[str, float], list[str]]:
        safe: dict[str, float] = {}
        clipped: list[str] = []
        for key, goal in action.items():
            g = float(goal)
            present = obs.get(key)
            cap = self._cap(key)
            if cap is not None and isinstance(present, (int, float)):
                p = float(present)
                lo, hi = p - cap, p + cap
                if g < lo or g > hi:
                    g = min(hi, max(lo, g))
                    clipped.append(key.removesuffix(".pos"))
            rng = self.ranges.get(key)
            if rng is not None:
                r = min(rng[1], max(rng[0], g))
                if r != g and key.removesuffix(".pos") not in clipped:
                    clipped.append(key.removesuffix(".pos"))
                g = r
            safe[key] = g
        self.clip_window.append((time.monotonic(), bool(clipped)))
        return safe, clipped

    def clipped_fraction(self, window_s: float = 2.0) -> float:
        now = time.monotonic()
        recent = [c for t, c in self.clip_window if now - t <= window_s]
        return sum(recent) / len(recent) if recent else 0.0


@dataclass
class EStopPress:
    t: float
    relax: bool


class EStop:
    """Latching e-stop. ``press()`` is safe from any thread and never waits on the command queue.

    First press: freeze (hold, torque on). A second press within ``double_press_s``, or
    ``press(relax=True)``: torque off.
    """

    def __init__(self, double_press_s: float = 2.0, clock: Callable[[], float] = time.monotonic) -> None:
        self.double_press_s = double_press_s
        self.clock = clock
        self.event = threading.Event()
        self.relax_event = threading.Event()
        self._lock = threading.Lock()
        self._last_press: float | None = None
        self.reason: str = "user"
        self.detail: str | None = None

    def press(self, reason: str = "user", *, relax: bool = False, detail: str | None = None) -> EStopPress:
        with self._lock:
            now = self.clock()
            if (
                self.event.is_set()
                and self._last_press is not None
                and now - self._last_press <= self.double_press_s
            ):
                relax = True
            if not self.event.is_set():
                self.reason = reason
                self.detail = detail
            self._last_press = now
            self.event.set()
            if relax:
                self.relax_event.set()
            return EStopPress(now, relax)

    @property
    def is_set(self) -> bool:
        return self.event.is_set()

    def clear(self) -> None:
        with self._lock:
            self.event.clear()
            self.relax_event.clear()
            self._last_press = None
            self.reason = "user"
            self.detail = None


class Watchdog:
    """Dead-man heartbeat: any client's heartbeat refreshes it (§4.7)."""

    def __init__(self, timeout_s: float = 1.0, clock: Callable[[], float] = time.monotonic) -> None:
        self.timeout_s = timeout_s
        self.clock = clock
        self._last = clock()
        self._lock = threading.Lock()

    def beat(self) -> None:
        with self._lock:
            self._last = self.clock()

    def arm(self) -> None:
        """Start a window now (session start), so a fresh session never trips immediately."""
        self.beat()

    def expired(self) -> bool:
        with self._lock:
            return self.clock() - self._last > self.timeout_s
