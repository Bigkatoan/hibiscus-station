"""``hibiscus-station doctor`` against emulated STS3215 chains (``tests/sts_emulator.py``).

K-11 / SP-1 / REG-13: current, load and a raw register dump of every servo on every port, read
only. D-15, D-21: the LIKELY PROBLEMS section. The zip carries no token.

Every test that talks to an arm runs on every platform (QD-4, QD-7) through a **loopback port**: the
Feetech packets the doctor sends (through lerobot's bus and through pyserial for the raw dump) go
byte for byte to the emulator's ``handle()`` and its answers come back as bytes. On Linux the same
tests also run through a real pseudo-terminal, with the real rustypot serial port underneath (a pty
does not work there on macOS, "Not a typewriter", and Windows has none).
"""

from __future__ import annotations

import json
import os
import sys
import time
import types
import zipfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest import mock

import pytest
from sts_emulator import STSEmulator, checksum, lelab_calibration, sm_decode, sm_encode

from hibiscus_station import doctor
from hibiscus_station.profiles import FollowerProfile, LeaderProfile, ProfileStore, RobotProfile
from hibiscus_station.settings import StationPaths

WRITES = {"write", "sync_write"}
LINUX = sys.platform.startswith("linux")
#: "loop" everywhere; "pty" (real serial port code on a pseudo-terminal) where it works.
TRANSPORTS = ["loop", "pty"] if LINUX else ["loop"]


# ------------------------------------------------------------------------------- loopback port
class LoopSTS(STSEmulator):
    """The emulator without its pseudo-terminal: :class:`LoopbackPort` calls ``handle()`` itself."""

    def __init__(self, port: str, **kwargs: Any) -> None:
        no_pty = types.SimpleNamespace(openpty=lambda: (-1, -1))
        no_tty = types.SimpleNamespace(setraw=lambda _fd: None)
        with (
            mock.patch.dict(sys.modules, {"pty": no_pty, "tty": no_tty}),
            mock.patch.object(os, "ttyname", lambda _fd: port, create=True),
        ):
            super().__init__(**kwargs)

    def _serve(self) -> None:  # no pty to serve
        return

    def close(self) -> None:
        self._stop.set()
        self._thread.join(1)


class LoopbackPort:
    """One USB serial port, wire level: complete Feetech packets go to the emulator, its answer
    bytes (with the emulator's timing) wait to be read. One owner at a time, as a real port."""

    def __init__(self, emu: STSEmulator) -> None:
        self.emu = emu
        self.rx = bytearray()
        self._tx = bytearray()
        self.owner: object | None = None
        self.refuse: str | None = None  # the OS error text when another program holds the port

    def open(self, who: object) -> None:
        if self.refuse:
            raise OSError(self.refuse)
        if self.owner is not None:
            raise OSError(16, "Device or resource busy")
        self.owner = who
        self.rx.clear()
        self._tx.clear()

    def close(self, who: object) -> None:
        if self.owner is who:
            self.owner = None

    def write(self, data: bytes) -> None:
        self._tx += data
        while True:
            start = self._tx.find(b"\xff\xff")
            if start < 0:
                self._tx.clear()
                return
            del self._tx[:start]
            if len(self._tx) < 4 or len(self._tx) < 4 + self._tx[3]:
                return
            pkt = bytes(self._tx[: 4 + self._tx[3]])
            del self._tx[: len(pkt)]
            if checksum(pkt[2:-1]) == pkt[-1]:
                self._transact(pkt)

    def _transact(self, pkt: bytes) -> None:
        """What ``STSEmulator._serve`` does with one packet, timing included."""
        e = self.emu
        e.transactions += 1
        if e.baud:
            _sleep(e.usb_out_s + len(pkt) * 10 / e.baud)
        out = e.handle(pkt[2], pkt[4], pkt[5:-1])
        if not out:
            return
        delay = e.latency_s
        if e.baud:
            delay += len(out) * 10 / e.baud + e.usb_in_s
        if e.return_delay:
            n = len(pkt[7:-1]) if pkt[4] == 0x82 else 1
            delay += n * max(s.get(7, 1) for s in e.servos.values()) * 2e-6
        _sleep(delay)
        self.rx += out

    def status(self, motor_id: int) -> tuple[bytes, int] | None:
        """The next well-formed status packet of ``motor_id``: (params, error byte)."""
        while True:
            start = self.rx.find(b"\xff\xff")
            if start < 0 or len(self.rx) < start + 4 or len(self.rx) < start + 4 + self.rx[start + 3]:
                self.rx.clear()
                return None
            del self.rx[:start]
            pkt = bytes(self.rx[: 4 + self.rx[3]])
            del self.rx[: len(pkt)]
            if checksum(pkt[2:-1]) == pkt[-1] and pkt[2] == motor_id:
                return pkt[5:-1], pkt[4]


def _sleep(seconds: float) -> None:
    end = time.perf_counter() + seconds
    if seconds > 0.0006:
        time.sleep(seconds - 0.0005)
    while time.perf_counter() < end:
        pass


def _packet(motor_id: int, instr: int, params: bytes = b"") -> bytes:
    body = bytes([motor_id, len(params) + 2, instr]) + params
    return b"\xff\xff" + body + bytes([checksum(body)])


class LoopSerial:
    """The part of ``serial.Serial`` the raw dump uses."""

    def __init__(self, port: LoopbackPort, timeout: float = 0.005) -> None:
        self.port, self.timeout = port, timeout
        port.open(self)

    @property
    def in_waiting(self) -> int:
        return len(self.port.rx)

    def reset_input_buffer(self) -> None:
        self.port.rx.clear()

    def write(self, data: bytes) -> int:
        self.port.write(data)
        return len(data)

    def flush(self) -> None:
        return None

    def read(self, n: int = 1) -> bytes:
        if not self.port.rx:
            time.sleep(self.timeout)
        out = bytes(self.port.rx[:n])
        del self.port.rx[:n]
        return out

    def close(self) -> None:
        self.port.close(self)


class LoopBus:
    """The part of ``rustypot.Bus`` lerobot's ``SerialMotorsBus`` calls, as Feetech packets on a
    :class:`LoopbackPort`; registers laid out and decoded from rustypot's own STS3215 table."""

    def __init__(self, port: LoopbackPort) -> None:
        import rustypot

        found = rustypot.find_model("sts3215")
        assert found is not None
        self.model, self.definition = found
        self.port = port
        port.open(self)
        self._open = True

    def _reg(self, name: str) -> Any:
        info = self.definition.register(name.lower())
        if info is None:
            raise ValueError(f"no register {name}")
        return info

    @staticmethod
    def _decode(info: Any, data: bytes) -> int:
        raw = int.from_bytes(data[: info.size], "little")
        return sm_decode(raw, info.sign_bit) if info.encoding == "sign_magnitude" else raw

    @staticmethod
    def _encode(info: Any, value: int) -> bytes:
        raw = sm_encode(int(value), info.sign_bit) if info.encoding == "sign_magnitude" else int(value)
        return raw.to_bytes(info.size, "little")

    def _ask(self, motor_id: int, instr: int, params: bytes, retries: int) -> tuple[bytes, int]:
        for _ in range(retries + 1):
            self.port.rx.clear()
            self.port.write(_packet(motor_id, instr, params))
            got = self.port.status(motor_id)
            if got is not None:
                return got
        raise RuntimeError(f"timeout waiting for motor {motor_id}")

    # -- rustypot.Bus API
    def close(self) -> None:
        self._open = False
        self.port.close(self)

    def is_open(self) -> bool:
        return self._open

    def set_timeout(self, timeout: float) -> None:
        return None

    def set_baudrate(self, baudrate: int) -> None:
        return None

    def read_register_with_error(self, motor_id: int, name: str, retries: int = 0) -> tuple[int, int]:
        info = self._reg(name)
        data, err = self._ask(motor_id, 0x02, bytes([info.addr, info.size]), retries)
        return self._decode(info, data), err

    def write_register_with_error(self, motor_id: int, name: str, value: int, retries: int = 0) -> int:
        info = self._reg(name)
        return self._ask(motor_id, 0x03, bytes([info.addr]) + self._encode(info, value), retries)[1]

    def sync_read_register_with_error(
        self, ids: list[int], name: str, retries: int = 0
    ) -> list[tuple[int, int]]:
        info = self._reg(name)
        for _ in range(retries + 1):
            self.port.rx.clear()
            self.port.write(_packet(0xFE, 0x82, bytes([info.addr, info.size, *ids])))
            got = [self.port.status(i) for i in ids]
            if all(g is not None for g in got):
                return [(self._decode(info, g[0]), g[1]) for g in got if g is not None]
        raise RuntimeError(f"sync read {name}: timeout")

    def sync_write_register(self, ids: list[int], name: str, values: list[int], retries: int = 0) -> None:
        info = self._reg(name)
        body = b"".join(bytes([i]) + self._encode(info, v) for i, v in zip(ids, values, strict=True))
        self.port.write(_packet(0xFE, 0x83, bytes([info.addr, info.size]) + body))

    def set_torque(self, ids: list[int], enabled: bool, retries: int = 0) -> dict[int, str]:
        for i in ids:
            self.write_register_with_error(i, "torque_enable", int(enabled), retries)
        return {}

    def broadcast_scan(self, definition: Any) -> dict[int, int]:
        self.port.rx.clear()
        self.port.write(_packet(0xFE, 0x01))
        ids = []
        while (got := self._next_any()) is not None:
            ids.append(got)
        return {i: self.read_register_with_error(i, "model_number")[0] for i in sorted(ids)}

    def scan(self, definition: Any, ids: list[int] | None = None) -> dict[int, int]:
        out = {}
        for i in ids or range(0, 253):
            try:
                out[i] = self.read_register_with_error(i, "model_number")[0]
            except RuntimeError:
                continue
        return out

    def _next_any(self) -> int | None:
        rx = self.port.rx
        start = rx.find(b"\xff\xff")
        if start < 0 or len(rx) < start + 4 or len(rx) < start + 4 + rx[start + 3]:
            return None
        del rx[:start]
        pkt = bytes(rx[: 4 + rx[3]])
        del rx[: len(pkt)]
        return pkt[2]


class Arms:
    """Makes emulated arms on the chosen transport; ``port`` is what a profile names."""

    def __init__(self, transport: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self.transport = transport
        self.tmp_path = tmp_path
        self.emus: list[STSEmulator] = []
        self.loops: dict[str, LoopbackPort] = {}
        if transport == "loop":
            import serial

            from hibiscus_station.hw.bus import StationMotorsBus

            real_open = StationMotorsBus._open_bus
            real_serial = serial.Serial

            def open_bus(bus: Any) -> Any:
                lp = self.loops.get(str(bus.port))
                return LoopBus(lp) if lp is not None else real_open(bus)

            def open_serial(port: str, *args: Any, **kwargs: Any) -> Any:
                lp = self.loops.get(str(port))
                if lp is None:
                    return real_serial(port, *args, **kwargs)
                return LoopSerial(lp, kwargs.get("timeout") or 0.005)

            monkeypatch.setattr(StationMotorsBus, "_open_bus", open_bus)
            monkeypatch.setattr(serial, "Serial", open_serial)

    def __call__(self, **kwargs: Any) -> STSEmulator:
        emu: STSEmulator
        if self.transport == "loop":
            # A real file, so "is the port there?" sees it; its name is never opened as a file.
            path = self.tmp_path / f"ttyLOOP{len(self.loops)}"
            path.touch()
            emu = LoopSTS(str(path), **kwargs)
            self.loops[str(path)] = LoopbackPort(emu)
        else:
            emu = STSEmulator(**kwargs)
        self.emus.append(emu)
        return emu

    def loop(self, emu: STSEmulator) -> LoopbackPort:
        return self.loops[emu.port]

    def close(self) -> None:
        for e in self.emus:
            e.close()


@pytest.fixture(params=TRANSPORTS)
def arms(request: pytest.FixtureRequest, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Arms]:
    a = Arms(request.param, tmp_path, monkeypatch)
    yield a
    a.close()


@pytest.fixture
def emus(arms: Arms) -> tuple[STSEmulator, STSEmulator]:
    return arms(seed=1, voltage_v=12.0), arms(seed=2)


def _home(tmp_path: Path, f: STSEmulator, ld: STSEmulator, monkeypatch: pytest.MonkeyPatch) -> Path:
    cal_root = tmp_path / "calibration"
    monkeypatch.setenv("HF_LEROBOT_CALIBRATION", str(cal_root))
    home = tmp_path / "home"
    home.mkdir()
    ProfileStore(StationPaths(home).robots).put(
        RobotProfile(
            id="arm",
            follower=FollowerProfile(port=f.port, calibration_id="arm_follower"),
            leader=LeaderProfile(port=ld.port, calibration_id="arm_leader"),
        )
    )
    return home


def _run(home: Path, out: Path) -> tuple[str, Path]:
    return doctor.run(home, out, probe_cameras=False, echo=lambda _s: None)


def _report(target: Path) -> dict[str, Any]:
    with zipfile.ZipFile(target) as z:
        data: dict[str, Any] = json.loads(z.read("report.json"))
    return data


def _arm(report: dict[str, Any], arm: str) -> dict[str, Any]:
    return next(a for a in report["arms"] if a["arm"] == arm)


def test_doctor_reads_current_load_and_dumps_raw_registers(
    tmp_path: Path, emus: tuple[STSEmulator, STSEmulator], monkeypatch: pytest.MonkeyPatch
) -> None:
    """REG-13 in one run: the customer's 0 deg C / ~1000 raw current, raw bytes and decoded values."""
    f, ld = emus
    for s in ld.servos.values():  # the customer's leader: 0 C and ~1000 raw current on every motor
        s.temp_c = 0
        s.current_raw = 1000
    f.servos[2].load_raw = sm_encode(-250, 10)  # -25.0 %
    f.servos[2].current_raw = 154  # 1.001 A
    home = _home(tmp_path, f, ld, monkeypatch)
    text, target = _run(home, tmp_path / "out")
    report = _report(target)

    fol = _arm(report, "follower")
    m2 = fol["motors"]["2"]
    assert m2["Present_Current"] == 154 and m2["Present_Load"] == -250
    assert m2["decoded"]["current_a"] == pytest.approx(1.001)
    assert m2["decoded"]["load_pct"] == -25.0 and m2["decoded"]["load_pct_plausible"] is True
    assert m2["Max_Temperature_Limit"] == 70
    assert m2["model_number"] == 777 and m2["Firmware_Major_Version"] == 3

    lead = _arm(report, "leader")
    dump = lead["raw_dump"]["motors"]
    assert sorted(dump, key=int) == ["1", "2", "3", "4", "5", "6"]
    for mid, row in dump.items():
        live = row["blocks"]["56-70"]
        data = bytes.fromhex(live["data"])
        assert len(data) == 15
        assert data[63 - 56] == 0  # temperature byte
        assert data[69 - 56 : 71 - 56] == (1000).to_bytes(2, "little")  # current bytes e8 03
        assert data[62 - 56] == 50  # 5.0 V
        assert (
            live["request"] == f"ff ff 0{mid} 04 02 38 0f " + f"{(~(int(mid) + 4 + 2 + 56 + 15)) & 0xFF:02x}"
        )
        assert bytes.fromhex(row["blocks"]["0-4"]["data"])[:2] == bytes([3, 10])
        assert bytes.fromhex(row["blocks"]["13-15"]["data"])[0] == 70
        d = row["decoded"]
        assert d["temperature_raw"] == 0 and d["temp_c_plausible"] is False
        assert d["current_raw"] == 1000 and d["current_a"] == 6.5 and d["current_a_plausible"] is False
        assert d["voltage_v"] == 5.0 and d["voltage_v_plausible"] is True
        assert d["firmware"] == "3.10" and d["model_number"] == 777 and d["max_temperature_limit_c"] == 70
    fdump = fol["raw_dump"]["motors"]["2"]["decoded"]
    assert fdump["load_raw"] == sm_encode(-250, 10) and fdump["load_pct"] == -25.0
    assert fdump["voltage_v"] == 12.0

    assert "current raw 1000 = 6.5 A (IMPLAUSIBLE" in text
    assert "raw register dump (READ per block" in text
    assert "[56-70] " in text and "e8 03" in text
    problems = text.split("LIKELY PROBLEMS:")[1].split("\n\n")[0]
    assert "arm leader: motor id(s) 1, 2, 3, 4, 5, 6 report an impossible temperature" in problems
    assert "arm leader: motor id(s) 1, 2, 3, 4, 5, 6 report an impossible current" in problems
    assert "follower: motor id(s)" not in problems


def test_doctor_never_writes_to_a_motor(
    tmp_path: Path, emus: tuple[STSEmulator, STSEmulator], monkeypatch: pytest.MonkeyPatch
) -> None:
    f, ld = emus
    f.preload_calibration(lelab_calibration())
    eeprom = {e: {i: bytes(s.mem[:56]) for i, s in e.servos.items()} for e in (f, ld)}
    home = _home(tmp_path, f, ld, monkeypatch)
    _run(home, tmp_path / "out")
    for emu in (f, ld):
        instructions = {op for op, _id, _addr in emu.log}
        assert instructions, "the doctor talked to the arm"
        assert instructions <= {"read", "sync_read"}, instructions
        assert sum(op in WRITES for op, _id, _addr in emu.log) == 0
        assert {addr for op, _id, addr in emu.log if op == "read"} >= {0, 13, 56}  # raw blocks
        assert all(not emu.torque(i) for i in emu.servos)
        assert {i: bytes(s.mem[:56]) for i, s in emu.servos.items()} == eeprom[emu]


def test_doctor_checks_a_detected_port_without_a_profile(
    tmp_path: Path, arms: Arms, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A demo profile active, the real arm on a USB port no profile names: it is still dumped."""
    emu = arms(seed=3)
    try:
        monkeypatch.setenv("HF_LEROBOT_CALIBRATION", str(tmp_path / "calibration"))
        row = {"device": emu.port, "vid_pid": "1a86:55d3", "description": "USB Single Serial"}
        monkeypatch.setattr(doctor, "ports", lambda _p: [dict(row, station_lock_pid=None, open_by=[])])
        text, target = _run(tmp_path / "home", tmp_path / "out")
        arm = _arm(_report(target), "no profile")
        assert arm["port"] == emu.port and arm["robot"] == "-"
        assert len(arm["raw_dump"]["motors"]) == 6
        assert arm["motors"]["1"]["Present_Current"] == 12
        assert f"- no profile on {emu.port}: ids answering" in text
        assert sum(op in WRITES for op, _id, _addr in emu.log) == 0
    finally:
        emu.close()


def test_raw_dump_reports_a_missing_servo(arms: Arms) -> None:
    emu = arms(ids=(1, 2))
    try:
        out = doctor.raw_dump(emu.port, (1, 2, 3), timeout_s=0.05)
    finally:
        emu.close()
    assert out["motors"]["3"]["error"] == "no answer"
    assert out["motors"]["3"]["blocks"]["56-70"]["answer"] is None
    assert out["motors"]["1"]["decoded"]["temp_c"] == 30.0
    assert all(op == "read" for op, _i, _a in emu.log)


# ------------------------------------------------------------------------------------- D-15
def _calibrated_home(
    tmp_path: Path, f: STSEmulator, ld: STSEmulator, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """A real profile whose calibration files exist and match the motors: nothing to warn about."""
    home = _home(tmp_path, f, ld, monkeypatch)
    cal = lelab_calibration()
    cal_root = tmp_path / "calibration"
    for sub, name in (
        ("robots/so_follower", "arm_follower"),
        ("teleoperators/so_leader", "arm_leader"),
    ):
        (cal_root / sub).mkdir(parents=True)
        (cal_root / sub / f"{name}.json").write_text(json.dumps(cal), encoding="utf-8")
    f.preload_calibration(cal)
    ld.preload_calibration(cal)
    return home


def test_doctor_always_starts_with_likely_problems(
    tmp_path: Path, emus: tuple[STSEmulator, STSEmulator], monkeypatch: pytest.MonkeyPatch
) -> None:
    f, ld = emus
    home = _calibrated_home(tmp_path, f, ld, monkeypatch)
    text, _target = _run(home, tmp_path / "out")
    assert text.splitlines()[:2] == ["LIKELY PROBLEMS:", "  No likely problems found"], text[:600]


def test_doctor_says_not_running_for_a_stale_pid_file(
    tmp_path: Path, emus: tuple[STSEmulator, STSEmulator], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Station killed with kill -9: station.pid stays, nothing listens on its port (AT-77 step 5)."""
    f, ld = emus
    home = _calibrated_home(tmp_path, f, ld, monkeypatch)
    (home / "station.pid").write_text(json.dumps({"pid": 4242, "port": 18349}), encoding="utf-8")
    (home / "token").write_text("t" * 43, encoding="utf-8")
    text, _target = _run(home, tmp_path / "out")
    assert "ConnectError" not in text and "Connection refused" not in text
    running = text.split("Running Station:\n")[1].splitlines()[0]
    assert running.startswith("  Station is not running") and "4242" in running
    assert text.splitlines()[1] == "  No likely problems found"


def test_doctor_lists_a_port_held_by_another_program_in_likely_problems(
    tmp_path: Path, arms: Arms, emus: tuple[STSEmulator, STSEmulator], monkeypatch: pytest.MonkeyPatch
) -> None:
    """AT-77 step 6: LeLab has the follower's port open. Linux names the holder (``/proc``, here a
    child process); Windows and macOS only see the port refuse to open, with their own error."""
    import subprocess

    f, ld = emus
    home = _calibrated_home(tmp_path, f, ld, monkeypatch)
    if not LINUX:
        arms.loop(f).refuse = (
            "could not open port: PermissionError(13, 'Access is denied.', None, 5)"
            if sys.platform == "win32"
            else "[Errno 16] Resource busy"
        )
        text, _target = _run(home, tmp_path / "out")
        problems = text.split("\n\n")[0]
        assert f"arm follower on {f.port} is busy or not accessible" in problems, problems
        assert "close it and run the doctor again" in problems
        assert not any(op == "read" for op, _i, _a in f.log)
        return
    holder = subprocess.Popen(  # noqa: S603 - our own interpreter
        [
            sys.executable,
            "-c",
            f"import sys,time; h=open({f.port!r},'rb',buffering=0); print('ok', flush=True); time.sleep(60)",
        ],
        stdout=subprocess.PIPE,
    )
    try:
        assert holder.stdout is not None and holder.stdout.readline().strip() == b"ok"
        text, _target = _run(home, tmp_path / "out")
    finally:
        holder.kill()
        holder.wait()
    problems = text.split("\n\n")[0]
    assert f"arm follower on {f.port} is busy, held by pid {holder.pid}" in problems, problems
    assert "close that program" in problems
    assert not any(op == "read" for op, _i, _a in f.log)  # a held port is never opened


def test_doctor_lists_a_port_held_by_station_in_likely_problems(
    tmp_path: Path, emus: tuple[STSEmulator, STSEmulator], monkeypatch: pytest.MonkeyPatch
) -> None:
    f, ld = emus
    home = _calibrated_home(tmp_path, f, ld, monkeypatch)
    monkeypatch.setattr(doctor, "station_lock_holder", lambda _p, dev: 4242 if dev == ld.port else None)
    text, _target = _run(home, tmp_path / "out")
    problems = text.split("\n\n")[0]
    assert f"arm leader on {ld.port}: held by Station pid 4242, motors not checked" in problems


def test_a_port_another_program_holds_on_windows_is_a_likely_problem() -> None:
    report: dict[str, Any] = {
        "profiles": {"active": "arm", "robots": []},
        "ports": [{"device": "COM3", "vid_pid": "1a86:55d3", "open_by": []}],
        "calibrations": [],
        "running": None,
        "arms": [
            {
                "robot": "-",
                "arm": "no profile",
                "port": "COM3",
                "error": "cannot open: could not open port 'COM3': PermissionError(13, 'Access is denied.')",
            }
        ],
    }
    w = doctor.warnings(report)
    assert any(x.startswith("- no profile on COM3 is busy or not accessible") for x in w), w


# ------------------------------------------------------------------------------------- D-21
def test_slow_bus_advice_names_the_latency_timer_only_for_ftdi() -> None:
    wch = doctor.teleop_estimate(17.0, "WCH")
    assert wch is not None and "latency timer to 1 ms" not in wch["warning"]
    assert "slow USB adapter / hub: plug the arm straight into the PC" in wch["warning"]
    ftdi = doctor.teleop_estimate(17.0, "FTDI")
    assert ftdi is not None and "latency timer to 1 ms" in ftdi["warning"]
    unknown = doctor.teleop_estimate(17.0)
    assert unknown is not None and "only if the adapter is an FTDI chip" in unknown["warning"]
    assert doctor.usb_chip("1a86:55d3") == "WCH" and doctor.usb_chip("0403:6001") == "FTDI"
    assert doctor.usb_chip("1234:5678") is None and doctor.usb_chip(None) is None


def test_doctor_on_a_slow_wch_adapter_does_not_mention_the_latency_timer(
    tmp_path: Path, arms: Arms, monkeypatch: pytest.MonkeyPatch
) -> None:
    emu = arms(seed=4).realistic(usb_in_s=0.016)  # a slow adapter / hub
    try:
        monkeypatch.setenv("HF_LEROBOT_CALIBRATION", str(tmp_path / "calibration"))
        row = {"device": emu.port, "vid_pid": "1a86:7523", "description": "USB-SERIAL CH340"}
        monkeypatch.setattr(doctor, "ports", lambda _p: [dict(row, station_lock_pid=None, open_by=[])])
        text, _target = _run(tmp_path / "home", tmp_path / "out")
    finally:
        emu.close()
    problems = text.split("\n\n")[0]
    assert f"- no profile on {emu.port}: slow bus (" in problems, problems
    assert "slow USB adapter / hub: plug the arm straight into the PC" in problems
    assert "latency timer to 1 ms" not in text


# ---------------------------------------------------------------------- what to send, secrets
def test_doctor_ends_with_what_to_send_in_english_and_vietnamese(
    tmp_path: Path, emus: tuple[STSEmulator, STSEmulator], monkeypatch: pytest.MonkeyPatch
) -> None:
    f, ld = emus
    home = _calibrated_home(tmp_path, f, ld, monkeypatch)
    text, target = _run(home, tmp_path / "out")
    tail = text.split("WHAT TO SEND / CẦN GỬI GÌ\n")[1]
    assert f"  EN: Send us this one file: {target.resolve()}" in tail
    assert f"  VI: Bạn chỉ cần gửi cho chúng tôi một tệp: {target.resolve()}" in tail
    assert "Feetech FD" in tail and "tệp hiệu chỉnh" in tail
    assert "incomplete" not in tail and "chưa đủ" not in tail  # both arms were read
    with zipfile.ZipFile(target) as z:
        assert "WHAT TO SEND / CẦN GỬI GÌ" in z.read("report.txt").decode()

    monkeypatch.setattr(doctor, "station_lock_holder", lambda _p, _d: 4242)
    text, _target = _run(home, tmp_path / "out2")
    tail = text.split("WHAT TO SEND / CẦN GỬI GÌ\n")[1]
    assert "The motor check is incomplete" in tail and "run `hibiscus-station doctor --verbose` again" in tail
    assert "Phần kiểm tra động cơ chưa đủ" in tail and "tắt Station và LeLab" in tail


def test_doctor_zip_has_no_token_or_pat(
    tmp_path: Path, emus: tuple[STSEmulator, STSEmulator], monkeypatch: pytest.MonkeyPatch
) -> None:
    f, ld = emus
    home = _calibrated_home(tmp_path, f, ld, monkeypatch)
    token = "Zk3v9QmT2xLp8RwYc4NbJ7HdFs6GaE1u0Io5KqWzXyV"  # fake, 43 chars as Station makes them  # gitleaks:allow
    pat = "hbp_AbCd1234_" + "x7Yq2Lm9Pz4Rt6Wv8Ks1Hn3Bf5Dj0Gc2Qe4Ua6Io8Ty"
    pat_secret = pat[len("hbp_AbCd") :]
    (home / "token").write_text(token, encoding="utf-8")
    (home / "server.json").write_text(json.dumps({"url": "https://hibiscus.example", "token": pat}))
    (home / "logs").mkdir()
    (home / "logs" / "station.log").write_text(
        f"GET /auth?t={token}\nAuthorization: Bearer {token}\nupload with {pat}\nraw {token}\n",
        encoding="utf-8",
    )
    with (home / "robots.yaml").open("a", encoding="utf-8") as fh:
        fh.write(f"# token {token}\n# pat {pat}\n")
    (home / "settings.yaml").write_text(f"# {pat}\n", encoding="utf-8")
    (home / "sessions" / "s1").mkdir(parents=True)
    (home / "sessions" / "s1" / "session.json").write_text(json.dumps({"note": f"{token} {pat}"}))
    cal = tmp_path / "calibration" / "robots" / "so_follower" / "arm_follower.json"
    data = json.loads(cal.read_text(encoding="utf-8"))
    data["shoulder_pan"]["note"] = token
    cal.write_text(json.dumps(data), encoding="utf-8")

    text, target = _run(home, tmp_path / "out")
    with zipfile.ZipFile(target) as z:
        names = z.namelist()
        blobs = {n: z.read(n) for n in names}
    assert "token" not in names and "server.json" not in names
    assert {"report.txt", "report.json", "station.log.tail", "robots.yaml", "settings.yaml"} <= set(names)
    assert "sessions/s1.json" in names and "calibration/follower/so_follower/arm_follower.json" in names
    for name, blob in blobs.items():
        assert token.encode() not in blob, name
        assert pat_secret.encode() not in blob, name
    assert token not in text and pat_secret not in text


def test_doctor_with_no_ping_says_to_run_again_without_it(tmp_path: Path) -> None:
    text, _target = doctor.run(
        tmp_path / "home", tmp_path / "out", ping=False, probe_cameras=False, echo=lambda _s: None
    )
    tail = text.split("WHAT TO SEND / CẦN GỬI GÌ\n")[1]
    assert "The motors were not checked (--no-ping)" in tail and "without --no-ping" in tail
    assert "Động cơ chưa được kiểm tra (--no-ping)" in tail and "không có --no-ping" in tail
    assert "close Station and LeLab" not in tail
