"""TrajectoryPlayer: replay one stored take (station-programs.md §3.2).

1. **Approach**: when any joint is more than ``approach_threshold_deg`` from the first sample, a
   minimum-jerk move to it whose peak speed is ``approach_speed_deg_s`` (phase ``approach``).
2. **Replay**: the samples, time-scaled by ``speed_pct`` (10-150 %) and **resampled** at the session
   fps by linear interpolation, so a slower replay is smoother and a faster one never skips the end
   (phase ``replay``). The last sample is always sent.

``TrajectoryPlaySession`` (state ``playing``) and the ``play trajectory`` block of a program both drive
this class, so both are the same code path. The owner applies the SafetyFilter to every goal.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import numpy as np

from hibiscus_station.programs.interfaces import MotionOutcome, TrajectorySamples
from hibiscus_station.programs.motion import MotionHost, Phase, PoseMove, joint_positions

if TYPE_CHECKING:
    from hibiscus_station.sessions.base import TickInput

MIN_SPEED_PCT = 10.0
MAX_SPEED_PCT = 150.0


def resample(samples: TrajectorySamples, speed_pct: float, fps: int) -> list[list[float]]:
    """Rows at ``fps`` of the take played at ``speed_pct``: output tick k shows source time
    ``k / fps · speed_pct / 100`` (linear interpolation), and the final sample closes the list."""
    if not MIN_SPEED_PCT <= speed_pct <= MAX_SPEED_PCT:
        raise ValueError(f"speed_pct must be within {MIN_SPEED_PCT}-{MAX_SPEED_PCT}")
    if fps <= 0:
        raise ValueError("fps must be positive")
    t = np.asarray(samples.t, dtype=np.float64)
    rows = np.asarray(samples.rows, dtype=np.float64)
    if len(t) == 0:
        return []
    t = t - t[0]
    duration = float(t[-1])
    scale = speed_pct / 100.0
    n = math.floor(duration / scale * fps + 1e-9)
    src = np.arange(n + 1, dtype=np.float64) / fps * scale
    if duration - src[-1] > 1e-9:
        src = np.append(src, duration)
    out = np.column_stack([np.interp(src, t, rows[:, j]) for j in range(rows.shape[1])])
    return [[float(v) for v in r] for r in out]


class TrajectoryPlayer:
    """``programs.interfaces.TrajectoryPlayerFactory`` / ``MotionPrimitive``."""

    def __init__(
        self,
        samples: TrajectorySamples,
        *,
        speed_pct: float,
        fps: int,
        approach_speed_deg_s: float,
        approach_threshold_deg: float = 3.0,
    ) -> None:
        if not samples.t:
            raise ValueError("an empty trajectory cannot be played")
        self.names = list(samples.names)
        self.speed_pct = float(speed_pct)
        self.fps = int(fps)
        self.approach_speed_deg_s = float(approach_speed_deg_s)
        self.approach_threshold_deg = float(approach_threshold_deg)
        self.rows = resample(samples, self.speed_pct, self.fps)
        self.first = dict(zip(self.names, self.rows[0], strict=True))
        self.phase: Phase = "replay"
        self.done = False
        self.outcome: MotionOutcome | None = None
        self.approach: PoseMove | None = None
        self.cursor = 0

    @property
    def replay_s(self) -> float:
        """Duration of the replay part at this speed."""
        return (len(self.rows) - 1) / self.fps

    @property
    def expected_s(self) -> float:
        approach = self.approach.expected_s if self.approach is not None else 0.0
        return approach + self.replay_s

    @property
    def progress(self) -> float:
        return self.cursor / len(self.rows)

    def distance_to_start(self, obs: dict[str, float]) -> float:
        present = joint_positions(obs)
        return max((abs(present[k] - v) for k, v in self.first.items() if k in present), default=0.0)

    def begin(self, owner: MotionHost, obs: dict[str, float]) -> None:
        if self.distance_to_start(obs) > self.approach_threshold_deg:
            self.approach = PoseMove(
                dict(self.first),
                self.approach_speed_deg_s,
                phase="approach",
                settle_tol=self.approach_threshold_deg,
                settle_s=1.0,
            )
            self.approach.begin(owner, obs)
            self.phase = "approach"
        else:
            self.phase = "replay"

    def step(self, owner: MotionHost, inp: TickInput) -> dict[str, float] | None:
        if self.done:
            return None
        if self.phase == "approach" and self.approach is not None:
            goal = self.approach.step(owner, inp)
            if self.approach.done:
                self.phase = "replay"  # the next tick sends the first sample (= this target)
            return goal
        row = self.rows[self.cursor]
        self.cursor += 1
        if self.cursor >= len(self.rows):
            self.done = True
            self.outcome = "completed"
        return dict(zip(self.names, row, strict=True))

    def cancel(self) -> None:
        if not self.done:
            self.done = True
            self.outcome = "cancelled"
