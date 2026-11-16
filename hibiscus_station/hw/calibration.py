"""Non-interactive two-step calibration on lerobot's public bus API (spec §2 L7, §6.3).

Same semantics as ``SerialMotorsBus.record_calibration`` (``motors_bus.py:931-1008``) without
``input()``: torque off, position mode, Feetech drive mode 0 (software), ``set_half_turn_homings``
at "Set home", then min/max of raw positions per motor; ``wrist_roll`` is full-turn (whole encoder).
Runs only in the hardware-owner thread.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from lerobot.motors import MotorCalibration

FULL_TURN_MOTORS = ("wrist_roll",)
MIN_RANGE_STEPS = 100


class CalibrationError(Exception):
    pass


@dataclass
class CalibrationProcess:
    arm: str  # follower | leader
    device: Any  # SOFollower / SOLeader
    step: str = "home"
    homings: dict[str, int] = field(default_factory=dict)
    mins: dict[str, int] = field(default_factory=dict)
    maxes: dict[str, int] = field(default_factory=dict)
    pos: dict[str, int] = field(default_factory=dict)

    @property
    def bus(self) -> Any:
        return self.device.bus

    def start(self) -> None:
        motors = list(self.bus.motors)
        self.bus.disable_torque(motors)
        self.bus.set_operating_mode("position", motors)
        self.step = "home"
        self.sample()

    def sample(self) -> dict[str, int]:
        raw = self.bus.sync_read("Present_Position", normalize=False, num_retry=1)
        self.pos = {m: int(v) for m, v in raw.items()}
        if self.step == "ranges":
            for m, v in self.pos.items():
                if m in FULL_TURN_MOTORS:
                    continue
                self.mins[m] = min(self.mins.get(m, v), v)
                self.maxes[m] = max(self.maxes.get(m, v), v)
        return self.pos

    def set_home(self) -> None:
        if self.step != "home":
            raise CalibrationError(f"set_home is only valid in step 'home' (now {self.step})")
        self.homings = self.bus.set_half_turn_homings(list(self.bus.motors))
        self.step = "ranges"
        self.mins, self.maxes = {}, {}
        self.sample()

    def warnings(self) -> list[str]:
        out = []
        for m in self.bus.motors:
            if m in FULL_TURN_MOTORS:
                continue
            lo, hi = self.mins.get(m), self.maxes.get(m)
            if lo is None or hi is None:
                continue
            if hi - lo < MIN_RANGE_STEPS:
                out.append(
                    f"{m}: range {hi - lo} steps (< {MIN_RANGE_STEPS}); move it through its full range"
                )
        return out

    def view(self) -> dict[str, Any]:
        motors: dict[str, Any] = {}
        for m in self.bus.motors:
            full = m in FULL_TURN_MOTORS
            motors[m] = {
                "min": 0 if full and self.step == "ranges" else self.mins.get(m),
                "pos": self.pos.get(m),
                "max": self.bus.resolution(self.bus.motors[m].model) - 1
                if full and self.step == "ranges"
                else self.maxes.get(m),
                "full_turn": full,
            }
        return {"arm": self.arm, "step": self.step, "motors": motors, "warnings": self.warnings()}

    def finish(self) -> tuple[dict[str, MotorCalibration], list[str]]:
        if self.step != "ranges":
            raise CalibrationError("finish_ranges is only valid in step 'ranges'")
        errors = []
        for m in self.bus.motors:
            if m in FULL_TURN_MOTORS:
                continue
            if self.mins.get(m) is None or self.mins.get(m) == self.maxes.get(m):
                errors.append(f"{m}: min and max are equal; move it through its range")
        if errors:
            raise CalibrationError("; ".join(errors))
        cal: dict[str, MotorCalibration] = {}
        for m, motor in self.bus.motors.items():
            if m in FULL_TURN_MOTORS:
                lo, hi = 0, self.bus.resolution(motor.model) - 1
            else:
                lo, hi = self.mins[m], self.maxes[m]
            cal[m] = MotorCalibration(
                id=motor.id,
                drive_mode=0,
                homing_offset=int(self.homings[m]),
                range_min=int(lo),
                range_max=int(hi),
            )
        warnings = self.warnings()
        self.bus.write_calibration(cal)
        self.device.calibration = cal
        self.device._save_calibration()
        self.step = "done"
        return cal, warnings

    def cancel(self) -> None:
        self.step = "cancelled"


def apply_existing(device: Any) -> bool:
    """``keep_existing``: write the calibration file of this id to the motors (torque off)."""
    if not device.calibration:
        return False
    device.bus.disable_torque()
    device.bus.write_calibration(device.calibration)
    return True
