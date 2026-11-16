"""Control-loop timing statistics (spec §4.5.1 step 9, §5.3 ``joints.loop``)."""

from __future__ import annotations

import time
from collections import deque


def percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = min(len(s) - 1, max(0, round(q / 100.0 * (len(s) - 1))))
    return s[k]


class LoopStats:
    def __init__(self, window_s: float = 2.0) -> None:
        self.window_s = window_s
        self.ticks: deque[tuple[float, float]] = deque()  # (start, duration)
        self.inference: deque[tuple[float, float]] = deque()
        self.overruns = 0
        self.total_ticks = 0
        self.all_durations: list[float] = []  # whole session, for tests / session.json
        self.slow_inference_since: float | None = None

    def _trim(self, now: float) -> None:
        while self.ticks and now - self.ticks[0][0] > self.window_s:
            self.ticks.popleft()
        while self.inference and now - self.inference[0][0] > self.window_s:
            self.inference.popleft()

    def tick(self, start: float, duration: float, period: float) -> None:
        self.ticks.append((start, duration))
        self.total_ticks += 1
        self.all_durations.append(duration)
        if len(self.all_durations) > 100_000:
            del self.all_durations[:50_000]
        if duration > period:
            self.overruns += 1
        self._trim(start)

    def inference_ms(self, start: float, ms: float, period: float) -> None:
        self.inference.append((start, ms))
        if ms > 2000.0 * period:
            if self.slow_inference_since is None:
                self.slow_inference_since = start
        else:
            self.slow_inference_since = None
        self._trim(start)

    def fps(self) -> float:
        if len(self.ticks) < 2:
            return 0.0
        span = self.ticks[-1][0] - self.ticks[0][0]
        return round((len(self.ticks) - 1) / span, 2) if span > 0 else 0.0

    def snapshot(self, telemetry_forced: int = 0) -> dict[str, float | int]:
        durs = [d * 1000.0 for _, d in self.ticks]
        out: dict[str, float | int] = {
            "fps": self.fps(),
            "tick_ms_p95": round(percentile(durs, 95), 2),
            "overruns": self.overruns,
            "telemetry_forced": telemetry_forced,
        }
        if self.inference:
            inf = [m for _, m in self.inference]
            out["inference_ms_p50"] = round(percentile(inf, 50), 2)
            out["inference_ms_p95"] = round(percentile(inf, 95), 2)
        return out

    def session_p95_ms(self) -> float:
        return percentile([d * 1000.0 for d in self.all_durations], 95)


class Deadline:
    """perf_counter deadline scheduler; never accumulates lag after an overrun."""

    def __init__(self, period: float) -> None:
        self.period = period
        self.next = time.perf_counter() + period

    def remaining(self) -> float:
        return self.next - time.perf_counter()

    def wait(self) -> float:
        """Sleep until the deadline; returns the slack (negative = overrun)."""
        slack = self.next - time.perf_counter()
        if slack > 0:
            time.sleep(slack)
            self.next += self.period
        else:
            self.next = time.perf_counter() + self.period
        return slack
