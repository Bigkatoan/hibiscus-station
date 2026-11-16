"""Replay a stored trajectory (station-programs.md §3.2, state ``playing``).

Sub-phases ``approach`` (minimum-jerk move to the first sample when the arm is farther than the
threshold) → ``replay`` → ``done``, all driven by :class:`~hibiscus_station.programs.player.TrajectoryPlayer`.
Dead-man heartbeat on. Every goal goes through the owner's SafetyFilter; e-stop drops the player in
the tick it is seen (the owner never calls ``step`` again).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from hibiscus_station.sessions.base import MotionSession, TickInput

if TYPE_CHECKING:
    from hibiscus_station.hw.owner import HardwareOwner
    from hibiscus_station.programs.player import TrajectoryPlayer
    from hibiscus_station.programs.trajectories import TrajectoryStore


@dataclass
class TrajPlaySession(MotionSession):
    player: TrajectoryPlayer | None = None
    trajectory_id: str | None = None
    speed_pct: float = 100.0
    check: bool = False
    store: TrajectoryStore | None = None

    def __post_init__(self) -> None:
        self.deadman = True
        self.episode.of = 1

    def _player(self) -> TrajectoryPlayer:
        if self.player is None:  # pragma: no cover - built by Station.play_trajectory
            raise RuntimeError("no trajectory player")
        return self.player

    def begin(self, owner: HardwareOwner, obs: dict[str, Any]) -> None:
        p = self._player()
        p.begin(owner, obs)
        self.set_phase(p.phase)
        self.episode.limit_s = round(p.expected_s, 2)

    def step(self, owner: HardwareOwner, inp: TickInput) -> dict[str, float] | None:
        p = self._player()
        goal = p.step(owner, inp)
        self.episode.elapsed_s = inp.t
        if p.done:
            self.set_phase("done")
            self.finish(p.outcome or "completed")
        else:
            self.set_phase(p.phase)
        return goal

    def control(self, owner: HardwareOwner, action: str) -> None:
        if action == "stop" and self.player is not None:
            self.player.cancel()
        super().control(owner, action)

    def end(self, owner: HardwareOwner, reason: str) -> None:
        p = self.player
        if p is not None and not p.done:
            p.cancel()
        completed = self.outcome == "completed"
        if self.check and completed and self.store is not None and self.trajectory_id is not None:
            self.store.note_check_replay(self.trajectory_id)
        self.summary.update(
            {
                "trajectory": self.trajectory_id,
                "speed_pct": self.speed_pct,
                "check": self.check,
                "checked": self.check and completed,
                "progress": round(p.progress, 3) if p is not None else 0.0,
            }
        )

    def view(self) -> dict[str, Any]:
        v = super().view()
        v["trajectory"] = self.trajectory_id
        return v
