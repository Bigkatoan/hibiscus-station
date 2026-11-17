"""A Feetech STS3215 servo chain emulated on a pseudo-terminal (POSIX only).

Unlike ``hibiscus_station.mock.fakebus`` (which replaces ``rustypot.Bus``), this speaks the real
Feetech wire protocol, so the *real* rustypot and lerobot stack (``SOFollower`` / ``SOLeader``, the
``so101_*`` profile types, ``DeviceLock`` on a ``/dev/pts/N`` path) runs unchanged against it:

* instructions PING, READ, WRITE, SYNC_READ, SYNC_WRITE, broadcast ID 0xFE;
* a 0..86 byte register file per servo with factory EEPROM values, sign-magnitude
  ``Homing_Offset`` (bit 11) / ``Present_Position`` (bit 15) / ``Present_Load`` (bit 10);
* ``present = actual - homing_offset`` (rustypot ``homing_offset_sign = -1``), goals clamped to
  the position limits, torque-off joints follow a "hand" function;
* fault injection: dropped answers, corrupted checksums, response latency, status/alarm bits;
* optional wire timing (:meth:`STSEmulator.realistic`): bytes at 1 Mbaud, each servo's
  ``Return_Delay_Time`` (register 7, 2 us units) and the USB adapter's latency in both directions,
  plus a first-order servo response (``tau_s``, ``vmax_steps_s``) for latency measurements;
* ``goal_log``: every Goal_Position the servos received, with its monotonic time.

Used by ``tests/test_real_stack.py`` and handy for manual checks (``python tests/sts_emulator.py``
prints a port and serves until Ctrl-C).
"""

from __future__ import annotations

import math
import os
import random
import select
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


def pty_unavailable(platform: str = sys.platform) -> str | None:
    """Why the emulator's pseudo-terminal cannot carry the real serial stack on ``platform``, or None.

    macOS: pyserial sets a non-standard speed (1 Mbps) with the IOKit ioctl IOSSIOSPEED, which a pty
    refuses with ENOTTY ("Not a typewriter"); a real USB serial adapter accepts it.
    """
    if platform == "win32":
        return "pseudo-terminals are POSIX only"
    if platform == "darwin":
        return "a macOS pty refuses pyserial's 1 Mbps ioctl (IOSSIOSPEED: ENOTTY)"
    return None


MODEL_STS3215 = 777
RES = 4096

# Factory EEPROM of a 7.4 V STS3215 (C001), as read from new servos; lerobot rewrites some at connect.
FACTORY: dict[int, tuple[int, int]] = {  # addr: (size, value)
    0: (1, 3),  # firmware major
    1: (1, 10),  # firmware minor
    3: (2, MODEL_STS3215),
    7: (1, 250),  # return delay (2 us units)
    8: (1, 1),  # response status level
    9: (2, 0),  # min position limit
    11: (2, 4095),  # max position limit
    13: (1, 70),  # max temperature limit
    14: (1, 80),  # max voltage limit (8.0 V)
    15: (1, 40),  # min voltage limit (4.0 V)
    16: (2, 1000),  # max torque limit
    18: (1, 12),  # phase
    19: (1, 44),  # unloading condition
    20: (1, 47),  # LED alarm condition
    21: (1, 32),  # P
    22: (1, 32),  # D
    23: (1, 0),  # I
    24: (2, 16),  # minimum startup force
    26: (1, 1),  # cw dead zone
    27: (1, 1),  # ccw dead zone
    28: (2, 500),  # protection current
    30: (1, 1),  # angular resolution
    31: (2, 0),  # homing offset
    33: (1, 0),  # operating mode
    34: (1, 20),  # protective torque
    35: (1, 200),  # protection time
    36: (1, 80),  # overload torque
    40: (1, 0),  # torque enable
    41: (1, 0),  # acceleration
    55: (1, 1),  # lock
    85: (1, 0),  # maximum acceleration
}


def checksum(body: bytes) -> int:
    return (~sum(body)) & 0xFF


def sm_encode(value: int, sign_bit: int) -> int:
    return (abs(value) | (1 << sign_bit)) if value < 0 else value


def sm_decode(raw: int, sign_bit: int) -> int:
    mag = raw & ((1 << sign_bit) - 1)
    return -mag if raw & (1 << sign_bit) else mag


@dataclass
class Servo:
    id: int
    actual: float = 2048.0  # steps in the motor's own frame
    mem: bytearray = field(default_factory=lambda: bytearray(90))
    temp_c: float = 30.0
    voltage_v: float = 5.0
    status: int = 0  # alarm bits (register 65 and the error byte of every answer)
    current_raw: int = 12
    load_raw: int = 0
    dead: bool = False  # never answers

    def __post_init__(self) -> None:
        for addr, (size, val) in FACTORY.items():
            self.put(addr, size, val)
        self.put(5, 1, self.id)

    def get(self, addr: int, size: int) -> int:
        return int.from_bytes(self.mem[addr : addr + size], "little")

    def put(self, addr: int, size: int, val: int) -> None:
        self.mem[addr : addr + size] = int(val).to_bytes(size, "little")

    @property
    def offset(self) -> int:
        return sm_decode(self.get(31, 2), 11)

    @property
    def present(self) -> int:
        return round(self.actual - self.offset) % RES


class STSEmulator:
    """One serial port (pty) with six STS3215 servos, ids 1-6."""

    def __init__(
        self, *, ids: tuple[int, ...] = (1, 2, 3, 4, 5, 6), voltage_v: float = 5.0, seed: int = 0
    ) -> None:
        import pty
        import tty

        self.master, self.slave = pty.openpty()
        tty.setraw(self.master)
        tty.setraw(self.slave)
        self.port = os.ttyname(self.slave)
        self.servos = {i: Servo(i, voltage_v=voltage_v) for i in ids}
        for s in self.servos.values():
            s.actual = 2048.0 + (s.id * 37) % 300 - 150
        self.rng = random.Random(seed)
        self.drop_rate = 0.0  # answer missing (timeout on the host)
        self.corrupt_rate = 0.0  # bad checksum
        self.latency_s = 0.0005
        # wire timing (0 = off): see realistic()
        self.baud = 0.0
        self.usb_out_s = 0.0  # host -> adapter (USB frame)
        self.usb_in_s = 0.0  # adapter -> host (USB latency timer)
        self.return_delay = False  # honour register 7 (Return_Delay_Time)
        # servo dynamics: first-order lag towards the goal, speed limited
        self.tau_s = 0.03
        self.vmax_steps_s = 4000.0
        self.goal_log: list[tuple[float, int, int]] = []  # (monotonic t, id, goal in present frame)
        self.record_goals = False
        self.transactions = 0
        self.hand: Callable[[int, float], float | None] | None = None
        self.lock = threading.Lock()
        self.log: list[tuple[str, int, int]] = []  # (instr, id, addr)
        self._stop = threading.Event()
        self._t0 = time.monotonic()
        self._last = self._t0
        self._thread = threading.Thread(target=self._serve, name=f"sts-{self.port}", daemon=True)
        self._thread.start()

    # ------------------------------------------------------------------ helpers for tests
    def realistic(
        self,
        *,
        usb_out_s: float = 0.0005,
        usb_in_s: float = 0.001,
        baud: float = 1_000_000.0,
        tau_s: float = 0.05,
        vmax_steps_s: float = 3400.0,
    ) -> STSEmulator:
        """Wire timing of a real SO-101 bus: 1 Mbaud bytes, return delays, a 1 ms USB latency timer
        (CH34x / FTDI set to 1 ms; FTDI's Windows default is 16 ms) and a ~300 deg/s servo."""
        self.latency_s = 0.0
        self.baud = baud
        self.usb_out_s = usb_out_s
        self.usb_in_s = usb_in_s
        self.return_delay = True
        self.tau_s = tau_s
        self.vmax_steps_s = vmax_steps_s
        return self

    def sample(self) -> dict[int, float]:
        """Physics step now, then every servo's position in its present frame (steps)."""
        with self.lock:
            self._step()
            return {i: s.actual - s.offset for i, s in self.servos.items()}

    def close(self) -> None:
        self._stop.set()
        self._thread.join(1)
        for fd in (self.master, self.slave):
            try:
                os.close(fd)
            except OSError:
                pass

    def preload_calibration(self, cal: dict[str, dict[str, int]]) -> None:
        """EEPROM as LeLab / lerobot left it after a calibration (``{motor: {id, homing_offset, range_*}}``)."""
        with self.lock:
            for v in cal.values():
                s = self.servos[int(v["id"])]
                s.put(31, 2, sm_encode(int(v["homing_offset"]), 11))
                s.put(9, 2, int(v["range_min"]))
                s.put(11, 2, int(v["range_max"]))
                s.actual = (int(v["range_min"]) + int(v["range_max"])) / 2 + s.offset

    def set_present(self, motor_id: int, present: float) -> None:
        with self.lock:
            s = self.servos[motor_id]
            s.actual = present + s.offset

    def torque(self, motor_id: int) -> bool:
        return bool(self.servos[motor_id].get(40, 1))

    # ------------------------------------------------------------------ physics
    def _step(self) -> None:
        now = time.monotonic()
        dt = min(0.2, now - self._last)
        self._last = now
        t = now - self._t0
        for s in self.servos.values():
            if s.get(40, 1):
                goal = sm_decode(s.get(42, 2), 15)
                lo, hi = s.get(9, 2), s.get(11, 2)
                if lo or hi:
                    goal = max(lo, min(hi, goal))
                target = goal + s.offset
                err = target - s.actual
                vmax = self.vmax_steps_s * dt
                s.actual += max(-vmax, min(vmax, err * (1 - math.exp(-dt / self.tau_s))))
                s.load_raw = sm_encode(max(-1000, min(1000, round(err * 4))), 10)
            elif self.hand is not None:
                pos = self.hand(s.id, t)
                if pos is not None:
                    s.actual = pos + s.offset
                s.load_raw = 0

    def _reg(self, s: Servo, addr: int) -> int | None:
        """Live registers (one byte each, little endian); None: from memory."""
        live: dict[int, int] = {}
        p = sm_encode(s.present, 15)
        live[56], live[57] = p & 0xFF, p >> 8
        live[60], live[61] = s.load_raw & 0xFF, s.load_raw >> 8
        live[62] = round(s.voltage_v * 10)
        live[63] = round(s.temp_c)
        live[65] = s.status
        live[66] = 0
        live[69], live[70] = s.current_raw & 0xFF, s.current_raw >> 8
        return live.get(addr)

    def _read(self, s: Servo, addr: int, n: int) -> bytes:
        out = bytearray()
        for a in range(addr, addr + n):
            v = self._reg(s, a)
            out.append(s.mem[a] if v is None else v)
        return bytes(out)

    def _write(self, s: Servo, addr: int, data: bytes) -> None:
        if self.record_goals and addr <= 42 < addr + len(data) - 1:
            raw = data[42 - addr] | (data[43 - addr] << 8)
            self.goal_log.append((time.monotonic(), s.id, sm_decode(raw, 15)))
        for i, b in enumerate(data):
            a = addr + i
            if a == 40 and b and not s.mem[40]:
                pos = sm_encode(s.present, 15)
                s.mem[42], s.mem[43] = pos & 0xFF, pos >> 8  # torque on: hold where it is
            s.mem[a] = b

    # ------------------------------------------------------------------ wire
    def _answer(self, s: Servo, params: bytes = b"") -> bytes:
        body = bytes([s.id, len(params) + 2, s.status]) + params
        chk = checksum(body)
        if self.corrupt_rate and self.rng.random() < self.corrupt_rate:
            chk ^= 0x5A
        return b"\xff\xff" + body + bytes([chk])

    def _respond(self, s: Servo | None, params: bytes = b"") -> bytes:
        if s is None or s.dead:
            return b""
        if self.drop_rate and self.rng.random() < self.drop_rate:
            return b""
        return self._answer(s, params)

    def handle(self, pkt_id: int, instr: int, params: bytes) -> bytes:
        with self.lock:
            self._step()
            s = self.servos.get(pkt_id)
            if instr == 0x01:  # ping
                if pkt_id == 0xFE:
                    return b"".join(self._respond(x) for x in self.servos.values())
                return self._respond(s)
            if instr == 0x02 and s is not None:  # read
                self.log.append(("read", pkt_id, params[0]))
                return self._respond(s, self._read(s, params[0], params[1]))
            if instr == 0x03 and s is not None:  # write
                self.log.append(("write", pkt_id, params[0]))
                self._write(s, params[0], params[1:])
                return self._respond(s)
            if instr == 0x82:  # sync read
                addr, n, ids = params[0], params[1], params[2:]
                self.log.append(("sync_read", 0xFE, addr))
                return b"".join(
                    self._respond(self.servos.get(i), self._read(self.servos[i], addr, n))
                    for i in ids
                    if i in self.servos
                )
            if instr == 0x83:  # sync write
                addr, n = params[0], params[1]
                self.log.append(("sync_write", 0xFE, addr))
                rest = params[2:]
                for k in range(0, len(rest), n + 1):
                    sid = rest[k]
                    if sid in self.servos:
                        self._write(self.servos[sid], addr, rest[k + 1 : k + 1 + n])
                return b""
            return b""

    def _serve(self) -> None:
        buf = bytearray()
        while not self._stop.is_set():
            r, _, _ = select.select([self.master], [], [], 0.05)
            if not r:
                continue
            try:
                buf += os.read(self.master, 4096)
            except OSError:
                return
            while True:
                start = buf.find(b"\xff\xff")
                if start < 0:
                    buf.clear()
                    break
                del buf[:start]
                if len(buf) < 4:
                    break
                length = buf[3]
                total = 4 + length
                if len(buf) < total:
                    break
                pkt = bytes(buf[:total])
                del buf[:total]
                if checksum(pkt[2:-1]) != pkt[-1]:
                    continue
                self.transactions += 1
                if self.baud:
                    _wait(self.usb_out_s + len(pkt) * 10 / self.baud)
                out = self.handle(pkt[2], pkt[4], pkt[5:-1])
                if out:
                    delay = self.latency_s
                    if self.baud:
                        delay += len(out) * 10 / self.baud + self.usb_in_s
                    if self.return_delay:
                        n = len(pkt[7:-1]) if pkt[4] == 0x82 else 1  # sync read: one answer per id
                        delay += n * max(s.get(7, 1) for s in self.servos.values()) * 2e-6
                    if delay:
                        _wait(delay)
                    os.write(self.master, out)


def _wait(seconds: float) -> None:
    """Sleep with ~20 us precision (time.sleep alone overshoots sub-millisecond waits)."""
    end = time.perf_counter() + seconds
    if seconds > 0.0006:
        time.sleep(seconds - 0.0005)
    while time.perf_counter() < end:
        pass


def lelab_calibration(seed: int = 1) -> dict[str, dict[str, Any]]:
    """A follower calibration json as lerobot / LeLab write it (values of a real SO-101)."""
    _ = seed
    return {
        "shoulder_pan": {"id": 1, "drive_mode": 0, "homing_offset": 44, "range_min": 684, "range_max": 3413},
        "shoulder_lift": {"id": 2, "drive_mode": 0, "homing_offset": 81, "range_min": 887, "range_max": 3267},
        "elbow_flex": {"id": 3, "drive_mode": 0, "homing_offset": 396, "range_min": 885, "range_max": 3122},
        "wrist_flex": {"id": 4, "drive_mode": 0, "homing_offset": -347, "range_min": 859, "range_max": 3190},
        "wrist_roll": {"id": 5, "drive_mode": 0, "homing_offset": -1194, "range_min": 0, "range_max": 4095},
        "gripper": {"id": 6, "drive_mode": 0, "homing_offset": -545, "range_min": 1761, "range_max": 3231},
    }


if __name__ == "__main__":  # pragma: no cover - manual use
    emu = STSEmulator()
    print(emu.port, flush=True)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        emu.close()
