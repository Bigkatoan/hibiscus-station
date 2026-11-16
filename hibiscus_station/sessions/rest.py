"""Return to rest pose (field report 0.2.8, state ``playing``, kind ``rest``).

After an e-stop / safe stop the arm stands wherever it froze. Once the operator has reset the e-stop
the UI offers this: one minimum-jerk move of every joint to the profile's rest pose, peak speed
capped (``programs.approach_speed_deg_s``), dead-man heartbeat on, cancellable with ``stop``. Every
goal goes through the owner's SafetyFilter and the e-stop freezes it within the tick, like any
motion session.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from hibiscus_station.programs.motion import PoseMove, joint_positions
from hibiscus_station.sessions.base import MotionSession, TickInput

if TYPE_CHECKING:
    from hibiscus_station.hw.owner import HardwareOwner


@dataclass
class RestSession(MotionSession):
    target: dict[str, float] | None = None
    speed_deg_s: float = 30.0
    move: PoseMove | None = None

    def __post_init__(self) -> None:
        self.deadman = True
        self.episode.of = 1
        if not self.target:
            raise ValueError("RestSession needs a rest pose")

    def begin(self, owner: HardwareOwner, obs: dict[str, Any]) -> None:
        present = joint_positions(obs)
        target = {k: v for k, v in (self.target or {}).items() if k in present}  # this arm's joints only
        self.move = PoseMove(target, self.speed_deg_s, phase="approach", settle_s=1.0)
        self.move.begin(owner, obs)
        self.set_phase("approach")
        self.episode.limit_s = round(self.move.expected_s, 2)

    def step(self, owner: HardwareOwner, inp: TickInput) -> dict[str, float] | None:
        m = self.move
        if m is None:  # pragma: no cover - begin() builds it
            return None
        goal = m.step(owner, inp)
        self.episode.elapsed_s = inp.t
        if m.done:
            self.set_phase("done")
            self.finish(m.outcome or "completed")
        return goal

    def control(self, owner: HardwareOwner, action: str) -> None:
        if action == "stop" and self.move is not None:
            self.move.cancel()
        super().control(owner, action)

    def end(self, owner: HardwareOwner, reason: str) -> None:
        self.summary.update({"rest_pose": dict(self.target or {}), "completed": self.outcome == "completed"})
