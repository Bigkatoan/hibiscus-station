"""Teleop session: leader drives follower at a fixed rate, nothing recorded (spec §6.5, L10)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from hibiscus_station.errors import StationError
from hibiscus_station.sessions.base import MotionSession, TickInput

if TYPE_CHECKING:
    from hibiscus_station.hw.owner import HardwareOwner


def blend(start: dict[str, float], target: dict[str, float], alpha: float) -> dict[str, float]:
    a = max(0.0, min(1.0, alpha))
    return {k: start.get(k, v) * (1 - a) + v * a for k, v in target.items()}


def check_leader_close(obs: dict[str, Any], leader: dict[str, float], max_deg: float) -> None:
    """Risk §11.6: refuse a long automatic move; ask the user to bring the leader closer."""
    far = {
        k.removesuffix(".pos"): round(abs(float(obs[k]) - v), 1)
        for k, v in leader.items()
        if k in obs and k != "gripper.pos" and abs(float(obs[k]) - v) > max_deg
    }
    if far:
        raise StationError(
            "leader_far",
            "Move the leader arm closer to the follower pose first",
            params={"joints": far, "max_deg": max_deg},
        )


@dataclass
class TeleopSession(MotionSession):
    approach_s: float = 1.5
    _start_pose: dict[str, float] = field(default_factory=dict)
    _approach_t0: float | None = None

    def __post_init__(self) -> None:
        self.uses_leader = True
        self.lean = True

    def begin(self, owner: HardwareOwner, obs: dict[str, Any]) -> None:
        self._start_pose = {k: float(v) for k, v in obs.items() if k.endswith(".pos")}
        self.set_phase("approach")

    def approach(self, inp: TickInput) -> dict[str, float] | None:
        """Smooth approach to the leader pose (``follower_smooth_move_to`` semantics, one tick at a time)."""
        if inp.leader is None:
            return None
        if self._approach_t0 is None:
            self._approach_t0 = inp.t
        alpha = (inp.t - self._approach_t0) / self.approach_s if self.approach_s > 0 else 1.0
        return blend(self._start_pose, inp.leader, alpha)

    def approach_done(self, inp: TickInput) -> bool:
        return self._approach_t0 is not None and inp.t - self._approach_t0 >= self.approach_s

    def step(self, owner: HardwareOwner, inp: TickInput) -> dict[str, float] | None:
        if self.episode.phase == "approach":
            target = self.approach(inp)
            if self.approach_done(inp):
                self.set_phase("teleop")
            return target
        self.episode.elapsed_s = inp.t
        return dict(inp.leader) if inp.leader is not None else None
