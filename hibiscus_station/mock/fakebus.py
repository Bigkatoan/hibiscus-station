"""A simulated STS3215 servo chain behind lerobot's real ``SerialMotorsBus`` (spec §9.1).

``MockMotorsBus`` *is* a lerobot ``SerialMotorsBus``: only ``_open_bus`` is replaced, so every
normalisation, calibration, sync read/write and torque code path Station uses is lerobot's own.
The returned :class:`FakeServoBus` implements the slice of the ``rustypot.Bus`` API lerobot calls,
backed by :class:`MockArmWorld` (registers + a small physics model):

* goal -> present position: first-order lag with a speed limit (torque on only);
* temperature: ``dT/dt = k1*|load| - k2*(T - T_amb)``; load rises with goal error (stall);
* voltage sags under current; the servo's own overheat protection cuts torque at
  ``Max_Temperature_Limit`` like the real STS3215 does;
* fault injection: :meth:`MockArmWorld.inject` (temperature, status bits, timeouts, disconnect).

The world also checks hardware ownership: every bus call must come from one thread
(``owner_violations`` collects offenders, and the call raises).
"""

from __future__ import annotations

import math
import random
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from lerobot.motors import Motor, MotorCalibration, SerialMotorsBus

from hibiscus_station.hw import feetech

MODEL_NUMBER = 777
RESOLUTION = 4096
HOMING_SIGN = -1  # rustypot sts3215.homing_offset_sign: present = actual + sign * offset
MOTOR_NAMES = ("shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll", "gripper")


class MockBusError(OSError):
    """Raised for an injected timeout / disconnect (lerobot maps OSError to ConnectionError)."""


@dataclass
class ServoState:
    id: int
    actual: float = 2048.0  # encoder steps in the motor's own frame (before homing offset)
    goal: float = 2048.0
    torque: bool = False
    temp_c: float = 28.0
    voltage_v: float = 7.4
    current_a: float = 0.0
    load_pct: float = 0.0
    regs: dict[str, int] = field(default_factory=dict)
    inject_temp_c: float | None = None
    inject_status: int = 0
    blocked: bool = False  # mechanically blocked: no motion, load climbs


@dataclass
class FaultPlan:
    timeout_rate: float = 0.0
    disconnect_at: float | None = None  # monotonic deadline
    fail_registers: set[str] = field(default_factory=set)  # always time out on these registers


class MockArmWorld:
    """Physics + registers of one simulated arm (one serial port)."""

    def __init__(
        self,
        port: str,
        *,
        nominal_voltage_v: float = 7.4,
        read_latency_s: float = 0.0015,
        write_latency_s: float = 0.0003,
        auto_sweep: bool = False,
        seed: int = 0,
    ) -> None:
        self.port = port
        self.lock = threading.RLock()
        self.rng = random.Random(seed)
        self.read_latency_s = read_latency_s
        self.write_latency_s = write_latency_s
        self.auto_sweep = auto_sweep  # torque-off joints follow a "hand" trajectory
        self.hand: Callable[[str, float], float | None] | None = None  # (motor, t) -> actual steps
        self.ambient_c = 28.0
        self.k1 = 0.004  # degC / s per % load
        self.k2 = 0.01  # 1/s
        self.speed_steps_s = 3000.0
        self.tau_s = 0.03
        self.sweep_steps = 150.0  # demo "hand" amplitude (about 13 degrees)
        self.sweep_hold_mid = False  # demo "hand" holds every joint mid-range (calibration: Home)
        self.servos: dict[int, ServoState] = {}
        for i, name in enumerate(MOTOR_NAMES, start=1):
            s = ServoState(id=i, voltage_v=nominal_voltage_v)
            s.actual = 2048.0 + self.rng.uniform(-200, 200)
            s.goal = s.actual
            s.regs = {
                "model_number": MODEL_NUMBER,
                "model": MODEL_NUMBER,
                "firmware_major_version": 3,
                "firmware_minor_version": 10,
                "id": i,
                "min_position_limit": 0,
                "max_position_limit": RESOLUTION - 1,
                "homing_offset": 0,
                "operating_mode": 0,
                "max_temperature_limit": 70,
                "max_voltage_limit": 140,
                "min_voltage_limit": 40,
                "protection_current": 0,
                "max_torque_limit": 1000,
                "lock": 0,
            }
            self.servos[i] = s
            _ = name
        self.names = {i: n for i, n in enumerate(MOTOR_NAMES, start=1)}
        self.ids = {n: i for i, n in self.names.items()}
        self.faults = FaultPlan()
        self._t_last = time.monotonic()
        self._t0 = self._t_last
        self.owner_ident: int | None = None
        self.strict_thread = True
        self.owner_violations: list[str] = []
        self.calls: list[tuple[float, int, str, str]] = []  # (t, thread ident, op, register)
        self.record_calls = False
        self.open = False

    # ------------------------------------------------------------------ test hooks (any thread)
    def inject(
        self,
        motor: str | None = None,
        *,
        temp_c: float | None = None,
        clear_temp: bool = False,
        status_bits: list[str] | None = None,
        timeout_rate: float | None = None,
        disconnect_after_s: float | None = None,
        blocked: bool | None = None,
        fail_registers: set[str] | None = None,
    ) -> None:
        with self.lock:
            targets = [self.servos[self.ids[motor]]] if motor else list(self.servos.values())
            for s in targets:
                if temp_c is not None:
                    s.inject_temp_c = temp_c
                    s.temp_c = temp_c
                if clear_temp:
                    s.inject_temp_c = None
                if status_bits is not None:
                    s.inject_status = feetech.encode_status(status_bits)
                if blocked is not None:
                    s.blocked = blocked
            if timeout_rate is not None:
                self.faults.timeout_rate = timeout_rate
            if disconnect_after_s is not None:
                self.faults.disconnect_at = time.monotonic() + disconnect_after_s
            if fail_registers is not None:
                self.faults.fail_registers = set(fail_registers)

    def follow(self, other: MockArmWorld | None) -> None:
        """Demo/test hook: the "hand" holds every torque-off joint at ``other``'s position.

        A leader mirroring the follower makes a teleop/record start deterministic (never
        ``leader_far``) instead of waiting for the demo sweep to pass the follower pose, which a slow
        host can miss. ``None`` gives the default hand back (the sweep, on a leader).
        """
        with self.lock:
            if other is None or other is self:
                self.hand = None
                return
            src = other

            def mirror(motor: str, _t: float) -> float:
                return src.servos[src.ids[motor]].actual  # a float read: no lock (no lock ordering)

            self.hand = mirror

    def set_hand(self, motor: str, raw_present: float) -> None:
        """Move a torque-off joint by hand to a raw *present* position (calibration tests)."""
        with self.lock:
            s = self.servos[self.ids[motor]]
            s.actual = raw_present - HOMING_SIGN * s.regs["homing_offset"]

    def place_all(self, actual: float = 2048.0) -> None:
        """Teleport every joint (and its goal) to ``actual`` steps (test setup)."""
        with self.lock:
            for s in self.servos.values():
                s.actual = actual
                s.goal = actual

    def present_raw(self, motor: str) -> int:
        with self.lock:
            return self._present(self.servos[self.ids[motor]])

    def torque_on(self, motor: str) -> bool:
        with self.lock:
            return self.servos[self.ids[motor]].torque

    def any_torque(self) -> bool:
        with self.lock:
            return any(s.torque for s in self.servos.values())

    def goal_writes(self) -> list[tuple[float, int]]:
        return [
            (t, ident) for t, ident, op, reg in self.calls if op == "sync_write" and reg == "goal_position"
        ]

    # ------------------------------------------------------------------ physics
    def _present(self, s: ServoState) -> int:
        return round(s.actual + HOMING_SIGN * s.regs["homing_offset"]) % RESOLUTION

    def step(self) -> None:
        now = time.monotonic()
        dt = min(0.2, max(0.0, now - self._t_last))
        self._t_last = now
        t = now - self._t0
        for s in self.servos.values():
            name = self.names[s.id]
            if s.torque and not s.blocked:
                err = s.goal - s.actual
                step = err * (1.0 - math.exp(-dt / self.tau_s)) if dt > 0 else 0.0
                vmax = self.speed_steps_s * dt
                s.actual += max(-vmax, min(vmax, step))
            elif not s.torque:
                pos = self.hand(name, t) if self.hand else None
                if pos is not None:
                    s.actual = pos
                elif self.auto_sweep and self.sweep_hold_mid:
                    s.actual = 2048.0
                elif self.auto_sweep:
                    amp = self.sweep_steps if name != "wrist_roll" else 2 * self.sweep_steps
                    s.actual = 2048.0 + amp * math.sin(2 * math.pi * (0.15 + 0.03 * s.id) * t + s.id)
            err = (s.goal - s.actual) if s.torque else 0.0
            load = max(-100.0, min(100.0, err * 0.6))
            if s.blocked and s.torque:
                load = 100.0 if err >= 0 else -100.0
            s.load_pct = load
            s.current_a = abs(load) * 0.012
            if s.inject_temp_c is not None:
                s.temp_c = s.inject_temp_c
            else:
                s.temp_c += (self.k1 * abs(load) - self.k2 * (s.temp_c - self.ambient_c)) * dt
            if s.temp_c >= s.regs["max_temperature_limit"] and s.torque:
                s.torque = False  # the servo's own protection: the arm drops

    def _status(self, s: ServoState) -> int:
        st = s.inject_status
        if s.temp_c >= s.regs["max_temperature_limit"]:
            st |= 1 << 2
        return st

    # ------------------------------------------------------------------ register access
    def read_reg(self, motor_id: int, name: str) -> int:
        s = self.servos[motor_id]
        if name in ("present_position",):
            return self._present(s)
        if name == "goal_position":
            return round(s.goal + HOMING_SIGN * s.regs["homing_offset"]) % RESOLUTION
        if name == "present_temperature":
            return round(s.temp_c)
        if name == "present_voltage":
            sag = s.current_a * 0.3
            return round((s.voltage_v - sag) / feetech.VOLTAGE_UNIT_V)
        if name == "present_current":
            return round(s.current_a / feetech.CURRENT_UNIT_A)
        if name == "present_load":
            return feetech.encode_load(s.load_pct)
        if name == "status":
            return self._status(s)
        if name == "moving":
            return int(s.torque and abs(s.goal - s.actual) > 2)
        if name == "torque_enable":
            return int(s.torque)
        if name in ("present_speed", "present_velocity"):
            return 0
        return int(s.regs.get(name, 0))

    def write_reg(self, motor_id: int, name: str, value: int) -> None:
        s = self.servos[motor_id]
        if name == "goal_position":
            lo, hi = s.regs["min_position_limit"], s.regs["max_position_limit"]
            if lo < hi:
                value = max(lo, min(hi, value))
            s.goal = value - HOMING_SIGN * s.regs["homing_offset"]
        elif name == "torque_enable":
            self._torque(s, bool(value))
        else:
            s.regs[name] = int(value)

    def _torque(self, s: ServoState, enabled: bool) -> None:
        if enabled and not s.torque:
            s.goal = s.actual
        s.torque = enabled


class FakeServoBus:
    """The subset of ``rustypot.Bus`` that ``SerialMotorsBus`` calls."""

    def __init__(self, world: MockArmWorld) -> None:
        self.world = world
        with world.lock:
            if world.open:
                raise OSError(f"{world.port}: port is in use")
            world.open = True
            world.owner_ident = None  # whoever opens the port owns it

    # -- helpers
    def _enter(self, op: str, register: str, *, write: bool = False) -> None:
        w = self.world
        ident = threading.get_ident()
        if w.owner_ident is None:
            w.owner_ident = ident
        elif w.strict_thread and ident != w.owner_ident:
            msg = f"{op}({register}) from thread {threading.current_thread().name} (not the owner)"
            w.owner_violations.append(msg)
            raise AssertionError(msg)
        if w.record_calls:
            w.calls.append((time.monotonic(), ident, op, register))
        if not w.open:
            raise MockBusError("bus closed")
        if w.faults.disconnect_at is not None and time.monotonic() >= w.faults.disconnect_at:
            raise MockBusError("device disconnected")
        if register in w.faults.fail_registers:
            raise MockBusError(f"timeout reading {register}")
        if w.faults.timeout_rate and w.rng.random() < w.faults.timeout_rate:
            raise MockBusError("timeout")
        lat = w.write_latency_s if write else w.read_latency_s
        if lat > 0:
            time.sleep(lat)

    # -- rustypot.Bus API
    def close(self) -> None:
        with self.world.lock:
            self.world.open = False

    def is_open(self) -> bool:
        return self.world.open

    def set_timeout(self, timeout: float) -> None:
        return None

    def set_baudrate(self, baudrate: int) -> None:
        return None

    def broadcast_scan(self, definition: Any) -> dict[int, int]:
        return dict.fromkeys(self.world.servos, MODEL_NUMBER)

    def scan(self, definition: Any) -> dict[int, int]:
        return self.broadcast_scan(definition)

    def set_torque(self, ids: list[int], enabled: bool, retries: int = 0) -> dict[int, str]:
        self._enter("set_torque", "torque_enable", write=True)
        with self.world.lock:
            self.world.step()
            for i in ids:
                self.world._torque(self.world.servos[i], enabled)
        return {}

    def read_register_with_error(self, motor_id: int, name: str, retries: int = 0) -> tuple[int, int]:
        self._enter("read", name)
        with self.world.lock:
            if motor_id not in self.world.servos:
                raise MockBusError(f"no motor {motor_id}")
            self.world.step()
            s = self.world.servos[motor_id]
            return self.world.read_reg(motor_id, name), self.world._status(s)

    def write_register_with_error(self, motor_id: int, name: str, value: int, retries: int = 0) -> int:
        self._enter("write", name, write=True)
        with self.world.lock:
            self.world.step()
            self.world.write_reg(motor_id, name, int(value))
            return 0

    def sync_read_register_with_error(
        self, ids: list[int], name: str, retries: int = 0
    ) -> list[tuple[int, int]]:
        self._enter("sync_read", name)
        with self.world.lock:
            self.world.step()
            return [(self.world.read_reg(i, name), self.world._status(self.world.servos[i])) for i in ids]

    def sync_write_register(self, ids: list[int], name: str, values: list[int], retries: int = 0) -> None:
        self._enter("sync_write", name, write=True)
        with self.world.lock:
            self.world.step()
            for i, v in zip(ids, values, strict=True):
                self.world.write_reg(i, name, int(v))


class MockMotorsBus(SerialMotorsBus):  # type: ignore[misc]
    """lerobot ``SerialMotorsBus`` whose port is a :class:`MockArmWorld`."""

    def __init__(
        self,
        port: str,
        motors: dict[str, Motor],
        calibration: dict[str, MotorCalibration] | None = None,
        world: MockArmWorld | None = None,
    ) -> None:
        super().__init__(port, motors, calibration)
        self.world = world or get_world(port)

    def _open_bus(self) -> Any:
        return FakeServoBus(self.world)


# --------------------------------------------------------------------------- world registry
_WORLDS: dict[str, MockArmWorld] = {}
_WORLDS_LOCK = threading.Lock()


def get_world(port: str, **kwargs: Any) -> MockArmWorld:
    """The simulated arm behind ``port`` (created on first use; kwargs only apply then)."""
    with _WORLDS_LOCK:
        w = _WORLDS.get(port)
        if w is None:
            if "auto_sweep" not in kwargs:
                kwargs["auto_sweep"] = "leader" in port
            if "nominal_voltage_v" not in kwargs and "leader" in port:
                kwargs["nominal_voltage_v"] = 5.0
            w = MockArmWorld(port, **kwargs)
            _WORLDS[port] = w
        return w


def reset_worlds() -> None:
    with _WORLDS_LOCK:
        _WORLDS.clear()
