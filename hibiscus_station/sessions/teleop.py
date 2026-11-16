"""Teleop session: leader drives follower at a fixed rate, nothing recorded (spec §6.5, L10)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from hibiscus_station.errors import StationError
from hibiscus_station.programs.motion import PoseMove, joint_positions
from hibiscus_station.sessions.base import MotionSession, TickInput

if TYPE_CHECKING:
    from hibiscus_station.hw.owner import HardwareOwner


def blend(start: dict[str, float], target: dict[str, float], alpha: float) -> dict[str, float]:
    a = max(0.0, min(1.0, alpha))
    return {k: start.get(k, v) * (1 - a) + v * a for k, v in target.items()}


def check_leader_close(
    obs: dict[str, Any], leader: dict[str, float], max_deg: float, *, can_align: bool = False
) -> None:
    """Risk §11.6: refuse a long automatic move; ask the user to bring the leader closer.

    ``can_align``: the session can instead move the follower to the leader slowly (teleop with
    ``align=true``); the UI then offers "Align follower to leader"."""
    far = {
        k.removesuffix(".pos"): round(abs(float(obs[k]) - v), 1)
        for k, v in leader.items()
        if k in obs and k != "gripper.pos" and abs(float(obs[k]) - v) > max_deg
    }
    if far:
        raise StationError(
            "leader_far",
            "Move the leader arm closer to the follower pose first",
            params={"joints": far, "max_deg": max_deg, "can_align": can_align},
        )


GRIPPER = "gripper.pos"


def leader_gap(obs: dict[str, Any], leader: dict[str, float]) -> float:
    """Largest follower - leader distance over the arm joints (the gripper does not count)."""
    present = joint_positions(obs)
    return max((abs(present[k] - v) for k, v in leader.items() if k in present and k != GRIPPER), default=0.0)


@dataclass
class TeleopSession(MotionSession):
    approach_s: float = 1.5
    #: "Align follower to leader" (field report 0.2.8): when the leader is farther than
    #: ``align_max_deg``, a minimum-jerk move at ``align_speed_deg_s`` peak speed brings the follower
    #: to the leader's pose (phase ``align``, dead-man on), then the usual short approach, then teleop.
    align: bool = False
    align_speed_deg_s: float = 30.0
    align_max_deg: float = 30.0
    _start_pose: dict[str, float] = field(default_factory=dict)
    _approach_t0: float | None = None
    _move: PoseMove | None = None
    _last_goal: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.uses_leader = True
        # Plain teleop only: subclasses (trajectory recording) need frames and observations.
        self.lean = type(self) is TeleopSession

    def begin(self, owner: HardwareOwner, obs: dict[str, Any]) -> None:
        self._start_pose = {k: float(v) for k, v in obs.items() if k.endswith(".pos")}
        if self.align:
            self.deadman = True
            self.set_phase("align")
            return
        self.set_phase("approach")

    def _align(self, owner: HardwareOwner, inp: TickInput) -> dict[str, float] | None:
        if inp.leader is None:
            return None
        if self._move is not None and not self._move.done:
            goal = self._move.step(owner, inp)
            if goal:
                self._last_goal = goal
            return goal
        present = joint_positions(inp.obs)
        if leader_gap(inp.obs, inp.leader) <= self.align_max_deg:
            # Close enough (the leader may have moved a little meanwhile): the usual short blend.
            self._start_pose = dict(self._last_goal or present)
            self._approach_t0 = None
            self._move = None
            self.deadman = False
            self.set_phase("approach")
            return self.approach(inp)
        target = {k: float(v) for k, v in inp.leader.items() if k in present}
        self._move = PoseMove(target, self.align_speed_deg_s, phase="approach", settle_tol=3.0, settle_s=0.5)
        self._move.begin(owner, inp.obs)
        goal = self._move.step(owner, inp)
        if goal:
            self._last_goal = goal
        return goal

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
        if self.episode.phase == "align":
            return self._align(owner, inp)
        if self.episode.phase == "approach":
            target = self.approach(inp)
            if self.approach_done(inp):
                self.set_phase("teleop")
            return target
        self.episode.elapsed_s = inp.t
        return dict(inp.leader) if inp.leader is not None else None
