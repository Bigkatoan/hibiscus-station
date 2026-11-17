"""``hibiscus-station doctor`` against emulated STS3215 chains (``tests/sts_emulator.py``).

K-11 / SP-1 / REG-13: current, load and a raw register dump of every servo on every port, read
only. D-15, D-21: the LIKELY PROBLEMS section. The zip carries no token.

Every test that talks to an arm runs on every platform (QD-4, QD-7) through a **loopback port**: the
Feetech packets the doctor sends (through pyserial: :mod:`hibiscus_station.hw.probe`) go byte for
byte to the emulator's ``handle()`` and its answers come back as bytes, late answers included. On
Linux the same tests also run through a real pseudo-terminal with pyserial's real serial port (a pty
does not work there on macOS, "Not a typewriter", and Windows has none).
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import types
import zipfile
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest import mock

import pytest
from sts_emulator import STSEmulator, checksum, lelab_calibration, sm_decode, sm_encode

from hibiscus_station import doctor
from hibiscus_station.profiles import (
    CameraProfile,
    FollowerProfile,
    LeaderProfile,
    ProfileStore,
    RobotProfile,
)
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
        self.bad_checksum = False
        self.last: tuple[bytes, int] = (b"", 0)
        self.refuse: str | None = None  # the OS error text when another program holds the port
        self.pending: list[tuple[float, bytes]] = []  # late answers on their way (first in, first out)
        #: well-formed answers that reached the host while the port was open, by servo id
        self.delivered: dict[int, int] = {}

    def open(self, who: object) -> None:
        if self.refuse:
            raise OSError(self.refuse)
        if self.owner is not None:
            raise OSError(16, "Device or resource busy")
        self.owner = who
        self.rx.clear()
        self._tx.clear()
        self.pending.clear()

    def close(self, who: object) -> None:
        if self.owner is who:
            self.owner = None
            self.pending.clear()  # what had not arrived yet never reaches the host

    def _arrive(self, data: bytes) -> None:
        self.rx += data
        rest = data
        while len(rest) >= 6 and len(rest) >= 4 + rest[3]:
            pkt, rest = rest[: 4 + rest[3]], rest[4 + rest[3] :]
            if checksum(pkt[2:-1]) == pkt[-1]:
                self.delivered[pkt[2]] = self.delivered.get(pkt[2], 0) + 1

    def release(self) -> None:
        """Late answers whose time has come reach the host."""
        now = time.perf_counter()
        while self.pending and self.pending[0][0] <= now:
            self._arrive(self.pending.pop(0)[1])

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
        out, timed = e.answers(pkt[2], pkt[4], pkt[5:-1])
        if not out:
            return
        delay = e.latency_s
        if e.baud:
            delay += len(out) * 10 / e.baud + e.usb_in_s
        if e.return_delay:
            n = len(pkt[7:-1]) if pkt[4] == 0x82 else 1
            delay += n * max(s.get(7, 1) for s in e.servos.values()) * 2e-6
        self.release()
        if timed or self.pending:  # behind a late answer: everything waits its turn
            t = time.perf_counter() + delay
            for p, extra in timed or [(out, 0.0)]:
                self.pending.append((max(t + extra, self.pending[-1][0] if self.pending else 0.0), p))
            return
        _sleep(delay)
        self._arrive(out)

    def status(self, motor_id: int) -> tuple[bytes, int] | None:
        """The next well-formed status packet of ``motor_id``: (params, error byte). ``bad_checksum``
        tells afterwards whether an answer of ``motor_id`` came with a wrong checksum."""
        self.bad_checksum = False
        while True:
            start = self.rx.find(b"\xff\xff")
            if start < 0 or len(self.rx) < start + 4 or len(self.rx) < start + 4 + self.rx[start + 3]:
                self.rx.clear()
                return None
            del self.rx[:start]
            pkt = bytes(self.rx[: 4 + self.rx[3]])
            del self.rx[: len(pkt)]
            if pkt[2] != motor_id:
                continue
            if checksum(pkt[2:-1]) == pkt[-1]:
                return pkt[5:-1], pkt[4]
            self.bad_checksum = True

    def sync_answer(self, motor_id: int) -> str:
        """The next packet whatever its id, as rustypot reads a sync read's answers: ``"ok"`` (in
        ``last``), ``"Operation timed out"``, ``"Checksum error"`` or ``"Parsing error"``."""
        rx = self.rx
        start = rx.find(b"\xff\xff")
        if start < 0 or len(rx) < start + 4 or len(rx) < start + 4 + rx[start + 3]:
            rx.clear()
            return "Operation timed out"
        del rx[:start]
        pkt = bytes(rx[: 4 + rx[3]])
        del rx[: len(pkt)]
        if checksum(pkt[2:-1]) != pkt[-1]:
            return "Checksum error"
        if pkt[2] != motor_id:
            return "Parsing error"
        self.last = (pkt[5:-1], pkt[4])
        return "ok"

    def failure(self) -> str:
        """rustypot's words for the last failed answer: a corrupt packet or none at all."""
        return "Checksum error" if self.bad_checksum else "Operation timed out"


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
        self.port.release()
        return len(self.port.rx)

    def reset_input_buffer(self) -> None:
        self.port.release()
        self.port.rx.clear()

    def write(self, data: bytes) -> int:
        self.port.write(data)
        return len(data)

    def flush(self) -> None:
        return None

    def read(self, n: int = 1) -> bytes:
        self.port.release()
        if not self.port.rx:
            time.sleep(self.timeout)
            self.port.release()
        out = bytes(self.port.rx[:n])
        del self.port.rx[:n]
        return out

    def close(self) -> None:
        self.port.close(self)


class Arms:
    """Makes emulated arms on the chosen transport; ``port`` is what a profile names."""

    def __init__(self, transport: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self.transport = transport
        self.tmp_path = tmp_path
        self.emus: list[STSEmulator] = []
        self.loops: dict[str, LoopbackPort] = {}
        if transport == "loop":
            import serial

            real_serial = serial.Serial

            def open_serial(port: str, *args: Any, **kwargs: Any) -> Any:
                lp = self.loops.get(str(port))
                if lp is None:
                    return real_serial(port, *args, **kwargs)
                return LoopSerial(lp, kwargs.get("timeout") or 0.005)

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


def _motor_check(text: str) -> list[str]:
    return text.split("Motor check (read only):\n")[1].split("\n\n")[0].splitlines()


def test_no_ping_says_the_motor_check_was_skipped_not_that_there_is_no_arm(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """QD-13: a profile with two real arms and --no-ping."""
    monkeypatch.setenv("HF_LEROBOT_CALIBRATION", str(tmp_path / "calibration"))
    home = tmp_path / "home"
    home.mkdir()
    ProfileStore(StationPaths(home).robots).put(
        RobotProfile(
            id="desk",
            follower=FollowerProfile(port="COM3", calibration_id="desk_follower"),
            leader=LeaderProfile(port="COM4", calibration_id="desk_leader"),
        )
    )
    text, _t = doctor.run(home, tmp_path / "out", ping=False, probe_cameras=False, echo=lambda _s: None)
    lines = _motor_check(text)
    assert lines == ["  skipped (--no-ping): the serial ports were not opened"], lines
    assert "no real arm" not in text


def test_motor_check_without_any_arm_says_so(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HF_LEROBOT_CALIBRATION", str(tmp_path / "calibration"))
    monkeypatch.setattr(doctor, "ports", lambda _p: [])
    text, _t = _run(tmp_path / "home", tmp_path / "out")
    assert _motor_check(text) == ["  nothing to check: no real arm in the profiles and no USB serial port"]


def test_a_lelab_file_with_the_profiles_id_is_named_once_and_consistently(
    tmp_path: Path, emus: tuple[STSEmulator, STSEmulator], monkeypatch: pytest.MonkeyPatch
) -> None:
    """QD-10: LeLab's ``so101_follower/arm_follower.json``, the profile expects ``arm_follower``,
    the motors carry it. One true sentence, no "no calibration" / "MISSING" next to it."""
    f, ld = emus
    home = _calibrated_home(tmp_path, f, ld, monkeypatch)
    cal_root = tmp_path / "calibration"
    station_file = cal_root / "robots" / "so_follower" / "arm_follower.json"
    (cal_root / "robots" / "so101_follower").mkdir(parents=True)
    station_file.rename(cal_root / "robots" / "so101_follower" / "arm_follower.json")
    text, _t = _run(home, tmp_path / "out")
    problems = text.split("\n\n")[0].splitlines()[1:]
    assert problems == [
        "  ! arm follower: calibration 'arm_follower' is in LeLab's folder (so101_follower), "
        "Station does not use it yet: Calibrate > Use this file"
    ], problems
    assert "no calibration 'arm_follower'" not in text
    profile = next(x for x in text.splitlines() if x.startswith("    follower: "))
    assert profile.endswith(
        "calibration 'arm_follower' in LeLab's folder (so101_follower), not used by Station yet"
    ), profile
    assert "MISSING" not in text
    carry = next(x for x in text.splitlines() if "motors carry the calibration of: " in x)
    assert carry.endswith(str(cal_root / "robots" / "so101_follower" / "arm_follower.json")), carry


def test_a_missing_calibration_lists_the_other_files_of_that_arm(tmp_path: Path) -> None:
    report: dict[str, Any] = {
        "profiles": {
            "active": "arm",
            "robots": [
                {
                    "id": "arm",
                    "mock": False,
                    "arms": {
                        "follower": {
                            "calibration_id": "arm_follower",
                            "file_exists": False,
                            "expects": "/c/robots/so_follower/arm_follower.json",
                        }
                    },
                }
            ],
        },
        "ports": [],
        "calibrations": [
            {
                "arm": "follower",
                "id": "my_follower",
                "dir": "so101_follower",
                "path": "/c/x/my_follower.json",
            },
            {"arm": "leader", "id": "arm_follower", "dir": "so101_leader", "path": "/c/y/arm_follower.json"},
        ],
        "running": None,
        "arms": [],
    }
    assert doctor.warnings(report) == [
        "arm follower: no calibration 'arm_follower' (files found: my_follower - Calibrate > Use this file)"
    ]


def test_a_calibration_file_that_differs_from_the_motors_is_a_likely_problem(
    tmp_path: Path, emus: tuple[STSEmulator, STSEmulator], monkeypatch: pytest.MonkeyPatch
) -> None:
    """QD-14 (FL-11): ``so_leader/arm_leader.json`` says elbow_flex homing_offset 300, the motor 396."""
    f, ld = emus
    home = _calibrated_home(tmp_path, f, ld, monkeypatch)
    lf = tmp_path / "calibration" / "teleoperators" / "so_leader" / "arm_leader.json"
    data = json.loads(lf.read_text(encoding="utf-8"))
    data["elbow_flex"]["homing_offset"] = 300
    lf.write_text(json.dumps(data), encoding="utf-8")
    ld.servos[6].dead = True  # a silent motor is "does not answer", never a calibration mismatch
    text, _t = _run(home, tmp_path / "out")
    problems = text.split("\n\n")[0].splitlines()[1:]
    assert (
        "  ! arm leader: calibration file 'arm_leader' does not match the motors (1 of 6 motors: "
        "elbow_flex homing_offset: file 300 motor 396); Connect writes the file to the motors: if it "
        "is not this arm's file, calibrate the arm again"
    ) in problems, problems
    assert "  ! arm leader: motor id(s) 6 do not answer (power? cable?)" in problems
    assert not any("follower" in p for p in problems), problems


def test_a_silent_motor_is_not_reported_as_a_slow_bus(
    tmp_path: Path, emus: tuple[STSEmulator, STSEmulator], monkeypatch: pytest.MonkeyPatch
) -> None:
    """QD-21: failed sync reads wait for a timeout; timing them made a loose servo cable look like
    a slow USB adapter ("slow bus (51 ms per read)", "~14 Hz") and sent the user to the hub."""
    f, ld = emus
    home = _calibrated_home(tmp_path, f, ld, monkeypatch)
    f.servos[6].dead = True
    text, _t = _run(home, tmp_path / "out")
    problems = text.split("\n\n")[0]
    assert "  ! arm follower: motor id(s) 6 do not answer (power? cable?)" in problems.splitlines(), problems
    assert "slow bus" not in text and "latency timer" not in text, text
    fol = text[text.index("  arm follower on ") :]
    fol = fol[: fol.index("\n  arm leader on ")] if "\n  arm leader on " in fol else fol
    assert "teleop estimate: not measured (motor id(s) 6 do not answer)" in fol, fol
    assert "Hz, leader -> follower latency" not in fol, fol


def test_a_bus_that_loses_answers_is_a_likely_problem(
    tmp_path: Path, emus: tuple[STSEmulator, STSEmulator], monkeypatch: pytest.MonkeyPatch
) -> None:
    """QD-22: every motor answers but some reads are lost (a loose servo cable, a dipping supply).
    The report must say so in LIKELY PROBLEMS and keep the speed of the reads that worked."""
    f, ld = emus
    home = _calibrated_home(tmp_path, f, ld, monkeypatch)
    f.rng.seed(7)
    f.drop_rate = 0.05
    text, _t = _run(home, tmp_path / "out")
    fol = text[text.index("  arm follower on ") :]
    fol = fol[: fol.index("\n  arm leader on ")] if "\n  arm leader on " in fol else fol
    lost = re.search(r"sync read: (\d+)/20 failed", fol)
    assert lost, fol
    assert int(lost.group(1)) > 0, fol  # 5 % drops over 20 reads of 6 motors: lost reads are certain
    problems = text.split("\n\n")[0]
    assert "arm follower: unreliable bus: " in problems, problems
    assert "do not answer" not in problems, problems
    assert "do not answer" not in fol, fol
    assert "although every motor answers a ping" in fol, fol


def _faulty_sync_reads(emu: STSEmulator, fault: Callable[[int], str]) -> None:
    """Every sync read answer of ``emu`` goes through ``fault(n)`` (n = 0, 1, ... per sync read):
    ``"drop"`` (no answer at all), ``"corrupt"`` (bad checksum on the first servo) or ``"ok"``.
    Pings and plain reads are untouched: every motor still answers."""
    handle, count = emu.handle, iter(range(10**6))

    def faulty(pkt_id: int, instr: int, params: bytes) -> bytes:
        out = handle(pkt_id, instr, params)
        if instr != 0x82 or not out:
            return out
        how = fault(next(count))
        if how == "drop":
            return b""
        if how == "corrupt":
            first = 4 + out[3]
            return out[: first - 1] + bytes([out[first - 1] ^ 0x5A]) + out[first:]
        return out

    emu.handle = faulty  # type: ignore[method-assign]


def _section(text: str, arm: str) -> str:
    sec = text[text.index(f"  arm {arm} on ") :].split("\n\n")[0]
    nxt = re.search(r"\n  \S", sec[3:])
    return sec[: nxt.start() + 3] if nxt else sec


def test_every_read_lost_while_every_motor_answers_is_not_a_silent_motor(
    tmp_path: Path, emus: tuple[STSEmulator, STSEmulator], monkeypatch: pytest.MonkeyPatch
) -> None:
    """QD-23: every ping answers, every sync read is lost. The report said "some motors did not
    answer" under "unreliable bus ... although every motor answers"."""
    f, ld = emus
    home = _calibrated_home(tmp_path, f, ld, monkeypatch)
    _faulty_sync_reads(f, lambda _n: "drop")
    text, _t = _run(home, tmp_path / "out")
    problems, fol = text.split("\n\n")[0], _section(text, "follower")
    assert "do not answer" not in text and "did not answer" not in fol, text
    assert (
        "arm follower: unreliable bus: 20 of 20 reads failed (20 got no answer) although every motor "
        "answers a ping; " in problems
    ), problems
    assert "    teleop estimate: not measured (too few reads succeeded: 0 of 20)" in fol.splitlines(), fol
    assert "slow bus" not in text, text


def test_checksum_errors_are_not_called_no_answer(
    tmp_path: Path, emus: tuple[STSEmulator, STSEmulator], monkeypatch: pytest.MonkeyPatch
) -> None:
    """QD-24: a corrupt answer is an answer; the report called it "got no answer". Counts by class."""
    f, ld = emus
    home = _calibrated_home(tmp_path, f, ld, monkeypatch)
    _faulty_sync_reads(f, lambda n: {0: "corrupt", 1: "drop"}.get(n % 4, "ok"))
    text, target = _run(home, tmp_path / "out")
    problems, fol = text.split("\n\n")[0], _section(text, "follower")
    sr = _arm(_report(target), "follower")["sync_read_present_position"]
    assert (sr["failed"], sr["no_answer"], sr["corrupt"], sr["ok"]) == (10, 5, 5, 10), sr
    assert (
        "unreliable bus: 10 of 20 reads failed (5 got no answer, 5 got corrupted answers (checksum)) "
        "although every motor answers a ping" in problems
    ), problems
    assert "(speed of the 10 reads that worked)" in fol, fol
    _faulty_sync_reads(ld, lambda n: "corrupt" if n % 2 else "ok")
    text, _t = _run(home, tmp_path / "out2")
    lead = _section(text, "leader")
    mine = [p for p in text.split("\n\n")[0].splitlines() if p.startswith("  ! arm leader: ")]
    assert "got no answer" not in lead and "got no answer" not in " ".join(mine), text
    assert any("(10 got corrupted answers (checksum))" in p for p in mine), mine
    assert "sync read: 10/20 failed (10 got corrupted answers (checksum)), 10 worked, " in lead, lead


def test_the_scan_line_agrees_with_the_pings(
    tmp_path: Path, emus: tuple[STSEmulator, STSEmulator], monkeypatch: pytest.MonkeyPatch
) -> None:
    """QD-24: the one-shot scan missed id 4, a ping with retries reached it: the report said
    "ids answering: 1-3, 5-6" above a full id 4 line and "every motor answers"."""
    f, ld = emus
    home = _calibrated_home(tmp_path, f, ld, monkeypatch)
    handle, missed = f.handle, []

    def miss_first(pkt_id: int, instr: int, params: bytes) -> bytes:
        out = handle(pkt_id, instr, params)
        if pkt_id in (4, 0xFE) and instr in (0x01, 0x02) and not missed:
            missed.append(instr)
            if pkt_id == 0xFE:  # broadcast ping: id 4's answer is lost
                pkts, rest = [], out
                while rest:
                    pkts.append(rest[: 4 + rest[3]])
                    rest = rest[4 + rest[3] :]
                return b"".join(x for x in pkts if x[2] != 4)
            return b""
        return out

    f.handle = miss_first  # type: ignore[method-assign]
    text, _t = _run(home, tmp_path / "out")
    fol = _section(text, "follower")
    head = fol.splitlines()[0]
    assert head.endswith(": ids answering at 1 Mbps: 1-6 (model 777); 4 answered only on a retry"), head
    assert "    id 4: model 777 fw 3.10 " in fol, fol


def _true_registers(emu: STSEmulator, motor_id: int) -> dict[str, int]:
    """The registers the doctor shows for one servo, as the emulated servo holds them."""
    return _truth(emu)[motor_id]


def _late_once(emu: STSEmulator, hit: Callable[[int, int, bytes], bool], seconds: float) -> None:
    """The answer to the first request ``hit(instr, id, params)`` picks comes ``seconds`` late."""
    done: list[bool] = []

    def late(instr: int, req_id: int, params: bytes, _answer_id: int) -> float:
        if not done and hit(instr, req_id, params):
            done.append(True)
            return seconds
        return 0.0

    emu.late = late


@pytest.mark.parametrize("late_s", [0.06, 0.15])
def test_a_late_answer_never_shifts_a_register_value(
    tmp_path: Path, emus: tuple[STSEmulator, STSEmulator], monkeypatch: pytest.MonkeyPatch, late_s: float
) -> None:
    """QD-25: the answer to the read of id 1's homing offset came 60 ms late; every later read of
    id 1 took the answer of the read before it: "80C", "341.3 V", "overheat, overload", limits
    "44-684", and "calibrate the arm again" for a file that matches. A late answer is now a bus
    fault the report names, never a value."""
    f, ld = emus
    home = _calibrated_home(tmp_path, f, ld, monkeypatch)
    _late_once(f, lambda instr, i, params: instr == 0x02 and i == 1 and params[0] in (28, 31), late_s)
    text, target = _run(home, tmp_path / "out")
    problems, fol = text.split("\n\n")[0], _section(text, "follower")
    m1 = _arm(_report(target), "follower")["motors"]["1"]
    for reg, value in _true_registers(f, 1).items():
        shown = m1.get("model_number" if reg == "Model_Number" else reg)
        assert shown is None or shown == value, (reg, shown, value, fol)
    assert (m1["Present_Temperature"], m1["Present_Voltage"], m1["Status"]) == (30, 120, 0), m1
    assert "calibrate the arm again" not in text and "does not match" not in text, problems
    assert "overheat" not in fol and "341.3 V" not in fol and "80C" not in fol, fol
    assert "arm follower: unreliable bus: " in problems and "came late (" in problems, problems
    assert "do not answer" not in text, problems


def test_a_slow_adapter_is_a_slow_bus_not_shifted_values(
    tmp_path: Path, emus: tuple[STSEmulator, STSEmulator], monkeypatch: pytest.MonkeyPatch
) -> None:
    """QD-25 variant: an adapter that delays every answer by 60 ms (longer than the bus timeout):
    "0 of 6 match", "fw 777.3", "voltage 341.3 V" on every servo. Now every value is true and the
    report says "slow bus"."""
    f, ld = emus
    home = _calibrated_home(tmp_path, f, ld, monkeypatch)
    f.adapter_delay_s = 0.06
    text, target = _run(home, tmp_path / "out")
    problems, fol = text.split("\n\n")[0], _section(text, "follower")
    fol_json = _arm(_report(target), "follower")
    for mid, m in fol_json["motors"].items():
        for reg, value in _true_registers(f, int(mid)).items():
            shown = m.get("model_number" if reg == "Model_Number" else reg)
            assert shown is None or shown == value, (mid, reg, shown, value, fol)
    assert "calibrate the arm again" not in text and "do not answer" not in text, problems
    assert "arm follower on " in problems and "slow bus (" in problems, problems
    assert "    calibration file vs motors: all 6 match" in fol.splitlines(), fol
    for mid, row in fol_json["raw_dump"]["motors"].items():
        for rng, blk in row["blocks"].items():
            lo, hi = (int(x) for x in rng.split("-"))
            assert bytes.fromhex(blk["data"]) == f._read(f.servos[int(mid)], lo, hi - lo + 1), (mid, rng)


def test_a_register_that_could_not_be_read_is_not_a_calibration_mismatch(
    tmp_path: Path, emus: tuple[STSEmulator, STSEmulator], monkeypatch: pytest.MonkeyPatch
) -> None:
    """QD-26: a read of id 1's position limits never got an answer; the report said the matching
    calibration file "does not match the motors (... motor error: Failed to read ...)" and to
    calibrate the arm again. A register that could not be read is a bus problem."""
    f, ld = emus
    home = _calibrated_home(tmp_path, f, ld, monkeypatch)
    handle = f.handle

    def no_limits(pkt_id: int, instr: int, params: bytes) -> bytes:
        out = handle(pkt_id, instr, params)
        if instr == 0x02 and pkt_id == 1 and params[0] <= 11 < params[0] + params[1]:
            return b""  # every read that covers Max_Position_Limit of id 1 is lost
        return out

    f.handle = no_limits  # type: ignore[method-assign]
    text, target = _run(home, tmp_path / "out")
    problems, fol = text.split("\n\n")[0], _section(text, "follower")
    assert "calibrate the arm again" not in text and "does not match" not in text, problems
    mine = [p for p in problems.splitlines() if p.startswith("  ! arm follower: could not read register(s) ")]
    assert len(mine) == 1 and "Max_Position_Limit of shoulder_pan" in mine[0], problems
    assert "(a bus problem, not the calibration)" in mine[0], mine
    assert "arm follower: unreliable bus: " in problems, problems
    cmp = _arm(_report(target), "follower")["calibration_vs_eeprom"]
    assert cmp["shoulder_pan"].startswith("could not read ") and "Max_Position_Limit" in cmp["shoulder_pan"]
    assert all(v == "match" for k, v in cmp.items() if k != "shoulder_pan"), cmp
    assert "    motors carry the calibration of: not known (" in fol, fol


def test_a_motor_that_answers_anything_is_not_called_silent(
    tmp_path: Path, emus: tuple[STSEmulator, STSEmulator], monkeypatch: pytest.MonkeyPatch
) -> None:
    """QD-27: id 5 answered the scan, every sync read and every register read, only its pings were
    lost; the report said "motor id(s) 5 do not answer (power? cable?)" next to "5 answered the
    first scan" and sync reads that worked, and did not name the bus."""
    f, ld = emus
    home = _calibrated_home(tmp_path, f, ld, monkeypatch)
    handle = f.handle

    def no_ping(pkt_id: int, instr: int, params: bytes) -> bytes:
        out = handle(pkt_id, instr, params)
        if pkt_id == 5 and (instr == 0x01 or (instr == 0x02 and params[:2] == bytes([3, 2]))):
            return b""  # a ping (lerobot pinged with a read of Model_Number)
        return out

    f.handle = no_ping  # type: ignore[method-assign]
    text, target = _run(home, tmp_path / "out")
    problems, fol = text.split("\n\n")[0], _section(text, "follower")
    assert "do not answer" not in text and "power? cable?" not in text, problems
    assert "answer only now and then" in problems and "arm follower: unreliable bus: " in problems, problems
    assert fol.splitlines()[0].endswith("1-6 (model 777); 5 answer only now and then (no ping answered)"), fol
    assert "    id 5: model 777 fw 3.10 " in fol, fol
    assert "    calibration file vs motors: all 6 match" in fol.splitlines(), fol
    m5 = _arm(_report(target), "follower")["motors"]["5"]
    assert m5["state"] == "flaky" and m5["evidence"]["scan"] and m5["evidence"]["sync_reads"] == 20, m5


def test_a_motor_that_sends_only_corrupted_packets_is_not_called_silent(
    tmp_path: Path, emus: tuple[STSEmulator, STSEmulator], monkeypatch: pytest.MonkeyPatch
) -> None:
    """QD-27: every packet of id 5 had a wrong checksum: the servo is powered and on the bus, the
    packets are damaged. "answers only with corrupted packets", never "do not answer"."""
    f, ld = emus
    home = _calibrated_home(tmp_path, f, ld, monkeypatch)
    handle = f.handle

    def damage_5(pkt_id: int, instr: int, params: bytes) -> bytes:
        out, rest, pkts = handle(pkt_id, instr, params), b"", []
        rest = out
        while rest:
            pkts.append(rest[: 4 + rest[3]])
            rest = rest[4 + rest[3] :]
        return b"".join(p[:-1] + bytes([p[-1] ^ 0x5A]) if p[2] == 5 else p for p in pkts)

    f.handle = damage_5  # type: ignore[method-assign]
    text, _t = _run(home, tmp_path / "out")
    problems, fol = text.split("\n\n")[0], _section(text, "follower")
    assert "do not answer" not in text and "power? cable?" not in text, problems
    assert "    id 5: answers only with corrupted packets (checksum), no register could be read" in fol, fol
    assert "motor id(s) 5 answer only with corrupted packets (checksum)" in problems, problems
    assert "got corrupted answers (checksum)" in fol and "got no answer" not in fol, fol
    assert "[0-4] corrupted answer (checksum)" in fol, fol
    assert "calibrate the arm again" not in text, problems


def _mangle(emu: STSEmulator, fn: Callable[[int, int, bytes, bytes], bytes]) -> None:
    """Every answer packet of ``emu`` goes through ``fn(instr, request id, params, packet)``: what
    the bus does to it on its way to the host (a flipped bit, a cut-short packet...)."""
    handle = emu.handle

    def mangled(pkt_id: int, instr: int, params: bytes) -> bytes:
        out, pkts = handle(pkt_id, instr, params), []
        while out:
            pkts.append(out[: 4 + out[3]])
            out = out[4 + out[3] :]
        return b"".join(fn(instr, pkt_id, params, p) for p in pkts)

    emu.handle = mangled  # type: ignore[method-assign]


@pytest.mark.parametrize("where", ["read", "sync"])
def test_a_corrupted_id_byte_never_makes_a_silent_motor_answer(
    tmp_path: Path, emus: tuple[STSEmulator, STSEmulator], monkeypatch: pytest.MonkeyPatch, where: str
) -> None:
    """QD-28: servo 6 has no power; one answer of servo 2 had its id byte flipped to 6 (so a wrong
    checksum). The report said "6 answer only with corrupted packets" and no longer that 6 does not
    answer. A packet with a wrong checksum cannot say which servo sent it: it is never evidence for
    the id it carries."""
    f, ld = emus
    home = _calibrated_home(tmp_path, f, ld, monkeypatch)
    f.servos[6].dead = True
    done: list[int] = []

    def flip(instr: int, req_id: int, params: bytes, p: bytes) -> bytes:
        hit = p[2] == 2 and (instr == 0x82 if where == "sync" else instr == 0x02 and params[:1] == b"\x00")
        if done or not hit:
            return p
        done.append(1)
        return p[:2] + bytes([p[2] ^ 0x04]) + p[3:]  # 2 -> 6, checksum left as it was

    _mangle(f, flip)
    text, target = _run(home, tmp_path / "out")
    assert done, "the flip never happened"
    problems, fol = text.split("\n\n")[0], _section(text, "follower")
    assert "  ! arm follower: motor id(s) 6 do not answer (power? cable?)" in problems.splitlines(), problems
    assert "    id 6: no answer" in fol.splitlines(), fol
    assert "6 answer only with" not in text and "id 6: answers only" not in fol, fol
    m6 = _arm(_report(target), "follower")["motors"]["6"]
    assert m6["state"] == "silent" and m6["evidence"]["corrupt"] == 0, m6


def test_damaged_packets_count_for_the_servo_asked_after_a_scan_nobody_answered(
    tmp_path: Path, emus: tuple[STSEmulator, STSEmulator], monkeypatch: pytest.MonkeyPatch
) -> None:
    """QD-28 follow-up: the scan got no answer at all (its answers lost), and every packet of id 5
    has a wrong checksum. A scan nobody answered is not a request whose late answers may still come
    for id 5's ping: id 5's damaged answers to its own pings count for it, so it "answers only with
    corrupted packets", never "do not answer"."""
    f, ld = emus
    home = _calibrated_home(tmp_path, f, ld, monkeypatch)
    _mangle(
        f,
        lambda instr, req, _p, p: (
            b"" if instr == 0x01 and req == 0xFE else p[:-1] + bytes([p[-1] ^ 0x5A]) if p[2] == 5 else p
        ),
    )
    text, target = _run(home, tmp_path / "out")
    problems, fol = text.split("\n\n")[0], _section(text, "follower")
    assert "do not answer" not in text, problems
    assert "    id 5: answers only with corrupted packets (checksum), no register could be read" in fol, fol
    m5 = _arm(_report(target), "follower")["motors"]["5"]
    assert m5["state"] == "corrupt" and m5["evidence"]["corrupt"] > 0, m5


def test_a_motor_whose_every_answer_is_cut_short_is_not_silent(
    tmp_path: Path, emus: tuple[STSEmulator, STSEmulator], monkeypatch: pytest.MonkeyPatch
) -> None:
    """QD-29: every answer lost its last 2 bytes (a half-duplex adapter turning round too early).
    Servos 2, 4, 6 were "do not answer (power? cable?)" next to a raw dump of the same report saying
    they sent "malformed answer". Every servo sent bytes: each one answers only with malformed
    packets, and the report names the bus."""
    f, ld = emus
    home = _calibrated_home(tmp_path, f, ld, monkeypatch)
    _mangle(f, lambda _i, _r, _p, p: p[:-2])
    text, target = _run(home, tmp_path / "out")
    problems, fol = text.split("\n\n")[0], _section(text, "follower")
    assert "do not answer" not in text and "power? cable?" not in text, problems
    assert "  ! arm follower: unreliable bus: " in problems, problems
    assert "motor id(s) 1, 2, 3, 4, 5, 6 answer only with malformed packets" in problems, problems
    for mid in range(1, 7):
        assert f"    id {mid}: answers only with malformed packets (cut short or the wrong length)" in fol, (
            fol
        )
    motors = _arm(_report(target), "follower")["motors"]
    assert {m["state"] for m in motors.values()} == {"corrupt"}, motors
    assert all(m["evidence"]["garbled"] > 0 for m in motors.values()), motors
    assert "got corrupted answers (checksum)" not in fol, fol


def _ms_each(fol: str) -> float | None:
    """The speed the motor check printed ("... 50.6 ms each"), None when it printed none."""
    m = re.search(r"sync read: .*?([\d.]+) ms each", fol)
    return float(m.group(1)) if m else None


def test_a_bus_stall_during_the_scan_is_a_bus_fault_not_a_flaky_motor(
    tmp_path: Path, emus: tuple[STSEmulator, STSEmulator], monkeypatch: pytest.MonkeyPatch
) -> None:
    """QD-30: one 300 ms USB stall during the scan (every answer waits behind it). The late answers
    were taken for nothing and servo 1 was "answers only now and then (no valid answer to 3 pings)"
    although it answered 20 of 20 sync reads and every register. A late answer is matched to the
    request it answers: every servo answers, and the stall is named as a bus fault."""
    f, ld = emus
    home = _calibrated_home(tmp_path, f, ld, monkeypatch)
    _late_once(f, lambda instr, i, _params: instr == 0x01 and i == 0xFE, 0.3)
    text, target = _run(home, tmp_path / "out")
    problems, fol = text.split("\n\n")[0], _section(text, "follower")
    assert "now and then" not in text and "do not answer" not in text, problems
    mine = [p for p in problems.splitlines() if p.startswith("  ! arm follower: unreliable bus: ")]
    assert len(mine) == 1 and " came late (up to " in mine[0] and "motor id(s)" not in mine[0], problems
    assert "stalled); plug the USB adapter straight into the PC" in mine[0], mine
    assert fol.splitlines()[0].endswith(": ids answering at 1 Mbps: 1-6 (model 777)"), fol
    assert "    calibration file vs motors: all 6 match" in fol.splitlines(), fol
    motors = _arm(_report(target), "follower")["motors"]
    assert {m["state"] for m in motors.values()} == {"answers"}, motors


@pytest.mark.parametrize("delay_s", [0.2])
def test_a_steadily_slow_adapter_is_a_slow_bus_not_loose_cables(
    tmp_path: Path, emus: tuple[STSEmulator, STSEmulator], monkeypatch: pytest.MonkeyPatch, delay_s: float
) -> None:
    """QD-30: an adapter that delays every answer by 200 ms (the servos keep answering, the bytes
    come out in order). Late answers were counted for the next request: servo 2 "answers only now
    and then", "unreliable bus ... check the 3-pin cables". It is a slow bus, nothing else."""
    f, ld = emus
    home = _calibrated_home(tmp_path, f, ld, monkeypatch)
    f.adapter_delay_s = delay_s
    text, _t = _run(home, tmp_path / "out")
    problems, fol = text.split("\n\n")[0], _section(text, "follower")
    assert "unreliable bus" not in text and "3-pin cables" not in text, problems
    assert "now and then" not in text and "do not answer" not in text, problems
    assert "  ! arm follower on " in problems and ": slow bus (" in problems, problems
    ms = _ms_each(fol)
    assert ms is not None and abs(ms - (delay_s + f.latency_s) * 1000) <= 0.2 * delay_s * 1000, fol
    assert "    calibration file vs motors: all 6 match" in fol.splitlines(), fol


def test_a_slow_adapter_next_to_a_dead_motor_is_not_called_loose_cables(
    tmp_path: Path, emus: tuple[STSEmulator, STSEmulator], monkeypatch: pytest.MonkeyPatch
) -> None:
    """QD-30: a 60 ms adapter and servo 6 without power: "unreliable bus: 5 answers came too late
    and were discarded; check the 3-pin cables" next to the dead servo. Only servo 6 is a problem."""
    f, ld = emus
    home = _calibrated_home(tmp_path, f, ld, monkeypatch)
    f.adapter_delay_s = 0.06
    f.servos[6].dead = True
    text, _t = _run(home, tmp_path / "out")
    problems, fol = text.split("\n\n")[0], _section(text, "follower")
    mine = [p for p in problems.splitlines() if p.startswith("  ! arm follower")]
    assert mine[0] == "  ! arm follower: motor id(s) 6 do not answer (power? cable?)", problems
    assert "unreliable bus" not in text and "late" not in problems, problems
    assert "now and then" not in fol, fol


@pytest.mark.parametrize(
    ("mode", "delay_s"),
    [
        ("pipelined", 0.05),
        ("blocking", 0.05),
        ("blocking", 0.2),
        ("pipelined", 0.26),
        pytest.param("blocking", 0.3, marks=pytest.mark.slow),
    ],
)
def test_the_bus_speed_is_measured_only_from_answers_to_their_own_request(
    tmp_path: Path,
    emus: tuple[STSEmulator, STSEmulator],
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    delay_s: float,
) -> None:
    """QD-31: an adapter answering every request 50 ms late was "44.66 ms each" with "unreliable bus
    ... check the 3-pin cables", one 260 ms late was "31.06 ms each, ~24 Hz": the late answer to the
    previous (identical) sync read was timed as this one's. The speed comes only from answers
    matched to their own request, within 20 % of the truth, or "slower than the timeout (> 250 ms)"
    when every answer comes after the longest wait ("pipelined": the servos keep answering and the
    bytes wait in the adapter; "blocking": the adapter takes that long per request)."""
    f, ld = emus
    home = _calibrated_home(tmp_path, f, ld, monkeypatch)
    if mode == "pipelined":
        f.adapter_delay_s = delay_s
        truth_ms = (delay_s + f.latency_s) * 1000
    else:
        f.latency_s = delay_s
        truth_ms = delay_s * 1000
    text, _t = _run(home, tmp_path / "out")
    problems, fol = text.split("\n\n")[0], _section(text, "follower")
    assert "unreliable bus" not in text and "3-pin cables" not in text, problems
    assert "now and then" not in text and "do not answer" not in text, problems
    assert "  ! arm follower on " in problems and ": slow bus (" in problems, problems
    ms = _ms_each(fol)
    if ms is None:
        assert "teleop estimate: not measured (slower than the timeout (> 250 ms per read))" in fol, fol
        assert truth_ms > 250, fol
    else:
        assert abs(ms - truth_ms) <= 0.2 * truth_ms, (ms, truth_ms, fol)
    assert "    calibration file vs motors: all 6 match" in fol.splitlines(), fol


# ------------------------------------------------------------------ invariants over a fault grid
GRID_DROP = (0.0, 0.01, 0.05, 0.2, 0.35, 0.4, 1.0)
GRID_CORRUPT = (0.0, 0.05, 0.4)
GRID_SILENT = ("none", "one", "all")
GRID_SEEDS = (0, 1, 2)
#: Late answers (QD-25): exactly one answer late (of the scan, of a ping of id 3, of the read of
#: id 1's homing offset block, of one sync read, of a raw block), 2 % of the answers late, or a
#: slow adapter delaying every answer.
GRID_LATE = ("scan", "ping3", "homing1", "sync", "raw", "random2pct")
GRID_LATE_S = (0.06, 0.15)
GRID_ADAPTER_S = (0.05, 0.1)
#: One servo losing most of its answers (QD-27): which id and how many.
GRID_FLAKY_IDS = (1, 4, 6)
GRID_FLAKY_RATES = (0.3, 0.9)


@dataclass(frozen=True)
class Case:
    drop: float = 0.0
    corrupt: float = 0.0
    silent: str = "none"
    seed: int = 0
    slow: bool = False  # a 9 ms adapter for the timed reads
    late: str = ""  # one of GRID_LATE, or "adapter"
    late_s: float = 0.0
    flaky_id: int = 0
    flaky_rate: float = 0.0
    wrong_file: bool = False  # the calibration file differs from the motors (elbow_flex offset)

    @property
    def id(self) -> str:
        parts = [f"drop{self.drop}", f"corrupt{self.corrupt}", f"silent_{self.silent}", f"seed{self.seed}"]
        parts.append("slow" if self.slow else "fast")
        if self.late:
            parts.append(f"late_{self.late}{self.late_s}")
        if self.flaky_id:
            parts.append(f"flaky{self.flaky_id}x{self.flaky_rate}")
        if self.wrong_file:
            parts.append("wrongfile")
        return "-".join(parts)


def _grid() -> Iterator[Any]:
    """Every combination. The default suite (every OS) keeps a representative part: seed 0 with
    the slow adapter off, the clean and the lossy bus with the slow adapter on, one of each late
    answer on a clean bus, a slow adapter of 50 ms, a servo losing 90 % of its answers, and a
    wrong calibration file on a lossy bus; the rest is ``slow``."""
    cases: list[tuple[Case, bool]] = []
    for drop in GRID_DROP:
        for corrupt in GRID_CORRUPT:
            for silent in GRID_SILENT:
                for seed in GRID_SEEDS:
                    for slow in (False, True):
                        quick = seed == 0 and (
                            not slow or (silent != "all" and drop in (0.0, 0.05, 1.0) and corrupt < 0.4)
                        )
                        cases.append((Case(drop, corrupt, silent, seed, slow), quick))
    for late in GRID_LATE:
        for late_s in GRID_LATE_S:
            for drop, corrupt in ((0.0, 0.0), (0.05, 0.0), (0.0, 0.05)):
                for seed in (0, 1):
                    quick = seed == 0 and drop == corrupt == 0.0
                    cases.append((Case(drop, corrupt, seed=seed, late=late, late_s=late_s), quick))
    for adapter in GRID_ADAPTER_S:
        for drop in (0.0, 0.05):
            for silent in ("none", "one"):
                quick = adapter == 0.05 and drop == 0.0 and silent == "none"
                cases.append((Case(drop, silent=silent, late="adapter", late_s=adapter), quick))
    for fid in GRID_FLAKY_IDS:
        for rate in GRID_FLAKY_RATES:
            for seed in GRID_SEEDS:
                for drop in (0.0, 0.05):
                    quick = seed == 0 and drop == 0.0 and rate == 0.9 and fid == 4
                    cases.append((Case(drop, seed=seed, flaky_id=fid, flaky_rate=rate), quick))
    for drop, corrupt in ((0.0, 0.0), (0.05, 0.05), (0.2, 0.0), (0.0, 0.4)):
        for seed in GRID_SEEDS:
            quick = seed == 0 and (drop, corrupt) in ((0.0, 0.0), (0.05, 0.05))
            cases.append((Case(drop, corrupt, seed=seed, wrong_file=True), quick))
    for drop, corrupt in ((0.05, 0.0), (0.0, 0.05)):
        for seed in GRID_SEEDS:  # a late answer on a lossy bus with a wrong file
            cases.append(
                (Case(drop, corrupt, seed=seed, late="random2pct", late_s=0.06, wrong_file=True), False)
            )
    for case, quick in cases:
        yield pytest.param(case, id=case.id, marks=() if quick else (pytest.mark.slow,))


def _grid_report(arm: dict[str, Any]) -> tuple[str, list[str]]:
    report: dict[str, Any] = {
        "versions": {
            "hibiscus_station": "x",
            "python": "x",
            "lerobot": "x",
            "rustypot": "x",
            "os": "x",
            "machine": "x",
        },
        "home": "h",
        "calibration_root": "c",
        "ports": [],
        "calibrations": [],
        "profiles": {"active": None, "robots": []},
        "running": None,
        "arms": [dict(arm, robot="arm", arm="follower")],
        "log_tail": [],
    }
    report["warnings"] = doctor.warnings(report)
    mine = [w[len("arm follower") :] for w in report["warnings"] if w.startswith("arm follower")]
    return doctor.summary(report), mine


def _one_late(case: Case) -> Callable[[int, int, bytes, int], float]:
    """Exactly one answer of ``case.late`` comes ``case.late_s`` late."""
    done: list[int] = []
    syncs: list[int] = []

    def late(instr: int, req_id: int, params: bytes, answer_id: int) -> float:
        if done:
            return 0.0
        if instr == 0x82:
            syncs.append(1)
        hit = {
            "scan": instr == 0x01 and req_id == 0xFE and answer_id == 3,
            "ping3": instr == 0x01 and req_id == 3,
            "homing1": instr == 0x02 and req_id == 1 and params[:1] == bytes([28]),
            "sync": instr == 0x82 and answer_id == 2 and len(syncs) >= 6,
            "raw": instr == 0x02 and req_id == 4 and params[:2] == bytes([56, 15]),
        }[case.late]
        if hit:
            done.append(1)
            return case.late_s
        return 0.0

    return late


def _truth(emu: STSEmulator) -> dict[int, dict[str, int]]:
    """Every register the doctor reports, as the emulated servos hold it."""
    table = doctor._register_table()
    out: dict[int, dict[str, int]] = {}
    for i, s in emu.servos.items():
        row: dict[str, int] = {}
        for reg, (addr, size, sign) in table.items():
            raw = int.from_bytes(emu._read(s, addr, size), "little")
            row[reg] = sm_decode(raw, sign) if sign is not None else raw
        out[i] = row
    return out


@pytest.mark.parametrize("case", list(_grid()))
def test_the_report_never_contradicts_itself(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: Case
) -> None:
    """QD-21 - QD-27 as invariants over lost / corrupt / late answers, silent and flaky servos, slow
    adapters and calibration files right or wrong: every value shown is the servo's true value or
    "?" (unreadable), "calibrate again" only when validated values differ from the file, "do not
    answer" only for servos that sent nothing, and no two sentences of the report disagree
    (loopback port: the same on every OS)."""
    arms = Arms("loop", tmp_path, monkeypatch)
    emu = arms(seed=case.seed)
    cal = lelab_calibration()
    emu.preload_calibration(cal)
    file_cal = json.loads(json.dumps(cal))
    if case.wrong_file:
        file_cal["elbow_flex"]["homing_offset"] = 300  # the motor (id 3) holds 396
    loop = arms.loop(emu)
    try:
        emu.rng.seed(case.seed)
        emu.late_rng.seed(case.seed + 1000)
        emu.drop_rate, emu.corrupt_rate = case.drop, case.corrupt
        dead = {"none": (), "one": (6,), "all": tuple(emu.servos)}[case.silent]
        for i in dead:
            emu.servos[i].dead = True
        if case.flaky_id:
            emu.servos[case.flaky_id].drop_rate = case.flaky_rate
        if case.late == "adapter":
            emu.adapter_delay_s = case.late_s
        elif case.late == "random2pct":
            emu.late_rate, emu.late_s = 0.02, case.late_s
        elif case.late:
            emu.late = _one_late(case)
        if case.slow:  # a slow adapter (16 ms latency timer, hub): only the timed reads pay for it here
            handle = emu.handle

            def slow_handle(pkt_id: int, instr: int, params: bytes) -> bytes:
                emu.latency_s = 0.009 if instr == 0x82 else 0.0005
                return handle(pkt_id, instr, params)

            emu.handle = slow_handle  # type: ignore[method-assign]
        arm = doctor.ping_arm(emu.port, file_cal, {"/c/arm_follower.json": file_cal}, vid_pid="1a86:55d3")
        arm["calibration_file"] = "/c/arm_follower.json"
        truth = _truth(emu)
    finally:
        arms.close()
    text, problems = _grid_report(arm)
    fol = _section(text, "follower")
    lines = fol.splitlines()
    sr = arm["sync_read_present_position"]
    failed = sr["failed"]
    ok = sr.get("ok", sr["reads"] - failed)
    joined = " ".join(problems)
    every = joined + fol
    ctx = f"{case.id}\n{problems}\n{fol}"

    # QD-25: every value shown is the servo's true value, or unreadable (None, shown as "?")
    for mid, m in arm["motors"].items():
        for reg, value in truth[int(mid)].items():
            key = "model_number" if reg == "Model_Number" else reg
            assert m.get(key) is None or m[key] == value, (mid, reg, m.get(key), value, ctx)
        if m.get("state") not in (None, "silent", "corrupt"):
            assert sorted(m["unreadable"]) == sorted(r for r in doctor.PING_REGISTERS if m.get(r) is None), m
    for mid, row in (arm.get("raw_dump") or {}).get("motors", {}).items():
        servo = emu.servos[int(mid)]
        for rng, blk in row["blocks"].items():
            lo, hi = (int(x) for x in rng.split("-"))
            if blk.get("data") is not None:
                assert bytes.fromhex(blk["data"]) == emu._read(servo, lo, hi - lo + 1), (mid, rng, blk, ctx)
            else:
                assert blk["answer"] is None and blk["error"] in (
                    "no answer",
                    "corrupted answer (checksum)",
                    "malformed answer (cut short or the wrong length)",
                ), blk

    # QD-27: one state per motor; "do not answer" only for a servo that sent nothing at all
    no_answer = {int(m.group(1)) for m in re.finditer(r"^    id (\d+): no answer$", fol, re.M)}
    full = {int(m.group(1)) for m in re.finditer(r"^    id (\d+): model ", fol, re.M)}
    garbage = {
        int(m.group(1))
        for m in re.finditer(r"^    id (\d+): answers only with (?:corrupted|malformed)", fol, re.M)
    }
    assert no_answer | full | garbage == set(range(1, 7)), ctx
    assert not (no_answer & full or no_answer & garbage or full & garbage), ctx
    assert set(dead) <= no_answer, ctx
    for i in no_answer:
        assert loop.delivered.get(i, 0) == 0, (i, loop.delivered, ctx)
    scan = re.search(r": ids answering at 1 Mbps: (.*)$", lines[0])
    assert scan, ctx
    ids: set[int] = set()
    for group in scan.group(1).split("; "):
        if " (model " not in group:
            continue
        listed = group.split(" (model ")[0]
        for part in listed.split(", "):
            lo, _, hi = part.partition("-")
            ids |= set(range(int(lo), int(hi or lo) + 1))
    assert ids == full | garbage, ctx
    flaky = {int(k) for k, m in arm["motors"].items() if m.get("state") == "flaky"}
    if flaky:
        assert "answers only now and then" in fol and "answer only now and then" in joined, ctx

    # silent motors: named; nothing about speed; the bus named only from the others' evidence
    dna = [p for p in problems if "do not answer" in p]
    if no_answer:
        assert dna == [
            f": motor id(s) {', '.join(map(str, sorted(no_answer)))} do not answer (power? cable?)"
        ], ctx
        assert (
            f"teleop estimate: not measured (motor id(s) {', '.join(map(str, sorted(no_answer)))} do not answer)"
            in fol
        ), ctx
        assert "every motor answers" not in every, ctx
        assert "slow bus" not in every and " Hz, " not in fol, ctx
    else:
        assert not dna and "do not answer" not in fol, ctx

    # QD-26: "calibrate again" only when validated values differ from the file
    mismatch = "calibrate the arm again" in joined
    m3 = arm["motors"]["3"]
    assert mismatch == (case.wrong_file and m3.get("Homing_Offset") == 396), ctx
    unread_cal = [
        k
        for k, m in arm["motors"].items()
        if m.get("state") != "silent"
        and any(m.get(r) is None for r in ("Homing_Offset", "Min_Position_Limit", "Max_Position_Limit"))
        and not (case.wrong_file and k == "3" and m.get("Homing_Offset") == 396)  # a mismatch shown
    ]
    assert ("could not read register(s)" in joined) == bool(unread_cal), ctx
    if unread_cal:
        assert "unreliable bus" in joined and "could not be read" in joined, ctx

    # failed reads by class: each class named only when it happened
    classes = {k: sr.get(k, 0) for k in ("no_answer", "corrupt", "garbled", "late", "other")}
    assert sum(classes.values()) == failed and ok + failed == sr["reads"], sr
    assert ("got no answer" in fol) == (classes["no_answer"] > 0), ctx
    assert ("got corrupted answers (checksum)" in fol) == (classes["corrupt"] > 0), ctx
    if case.corrupt == 0:
        assert classes["corrupt"] == 0, sr
    if case.drop == 0 and not dead and not case.flaky_id and not case.late:
        assert classes["no_answer"] == classes["garbled"] == classes["other"] == 0, sr
    states = {m.get("state") for m in arm["motors"].values()}
    if not no_answer:
        assert ("although every motor answers a ping" in joined) == (failed > 0 and states == {"answers"}), (
            ctx
        )
        if failed:
            assert "unreliable bus" in joined and "unreliable bus" in fol, ctx
    if "unreliable bus" in joined:  # named only from evidence of a fault
        assert (
            failed
            or states - {"answers", "silent"}
            or arm["bus_errors"].get("late_answers")
            or unread_cal
            or any(m.get("unreadable") for m in arm["motors"].values())
        ), ctx
    if case.late and case.late != "adapter" and not dead and case.drop == case.corrupt == 0.0:
        # a late answer is a bus fault the report names; it never moves a value (checked above)
        assert "unreliable bus" in joined, ctx

    # one conclusion about speed
    est = [x for x in lines if x.startswith("    teleop estimate: ")]
    assert len(est) == 1, ctx
    measured = " Hz, leader -> follower latency" in est[0]
    assert measured == (not no_answer and ok >= doctor.MIN_OK_READS), ctx
    if not no_answer and not measured:
        assert est[0] == f"    teleop estimate: not measured (too few reads succeeded: {ok} of 20)", ctx
    assert ("reads that worked" in est[0]) == (measured and failed > 0), ctx
    if "slow bus" in every:
        assert not no_answer and ok >= doctor.MIN_OK_READS and failed < ok, ctx
    if not no_answer and failed == 0 and case.late != "adapter":
        assert ("slow bus" in every) == case.slow, ctx
    if case.late == "adapter" and not no_answer and failed == 0:
        assert "slow bus" in every, ctx


def test_a_calibration_file_of_another_arm_names_every_motor_that_differs() -> None:
    cmp = {m: "homing_offset: file 1 motor 0; range_min: file 2 motor 0" for m in ("a", "b", "c")}
    report: dict[str, Any] = {
        "profiles": {"active": "x", "robots": []},
        "ports": [],
        "calibrations": [],
        "running": None,
        "arms": [
            {
                "robot": "desk",
                "arm": "leader",
                "port": "COM4",
                "motors": {},
                "calibration_vs_eeprom": dict(cmp, d="match"),
                "calibration_file": "/c/teleoperators/so_leader/desk_leader.json",
            }
        ],
    }
    w = [x for x in doctor.warnings(report) if "does not match" in x]
    assert w == [
        "desk leader: calibration file 'desk_leader' does not match the motors (3 of 4 motors: a, b, c; "
        "first: a homing_offset: file 1 motor 0); Connect writes the file to the motors: if it is not "
        "this arm's file, calibrate the arm again"
    ], w


def _status(calibrated: bool, issue: str | None, last: str | None) -> dict[str, Any]:
    arm = {"calibrated": calibrated, "issue": issue, "bus_errors": 0 if last is None else 2}
    return {
        "pid": 1697856,
        "http": 200,
        "status": {
            "state": "idle",
            "reason": None,
            "detail": None,
            "station": {"mock": False},
            "robot": {
                "id": "desk",
                "mock": False,
                "arms": {
                    "follower": dict(arm, last_bus_error=last),
                    "leader": dict(arm, bus_errors=0, last_bus_error=None),
                },
            },
            "alerts": [],
        },
    }


@pytest.mark.parametrize("log_lines", [0, 1, 3])
def test_report_has_no_python_values_and_counts_log_lines_in_words(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, log_lines: int
) -> None:
    """QD-11: Station running and connected; no None / False / True, "1 log line"."""
    monkeypatch.setenv("HF_LEROBOT_CALIBRATION", str(tmp_path / "calibration"))
    home = tmp_path / "home"
    if log_lines:
        (home / "logs").mkdir(parents=True)
        (home / "logs" / "station.log").write_text("x\n" * log_lines, encoding="utf-8")
    issue = "no calibration file /c/robots/so_follower/desk_follower.json"
    monkeypatch.setattr(doctor, "running_status", lambda _p: _status(False, issue, None))
    real_versions = doctor.versions()
    monkeypatch.setattr(doctor, "versions", lambda: dict(real_versions, rustypot=None))
    text, _t = doctor.run(home, tmp_path / "out", ping=False, probe_cameras=False, echo=lambda _s: None)
    for word in ("None", "False", "True"):
        assert word not in text.split(), (word, text)
    running = text.split("Running Station:\n")[1].split("\n\n")[0].splitlines()
    assert running[0] == "  pid 1697856: mode real, state idle", running
    assert running[2] == f"    follower: not calibrated ({issue}), bus errors 0", running
    assert "rustypot not installed" in text
    want = {
        0: "No Station log found (logs/station.log).",
        1: "The last log line is in the zip.",
        3: "The last 3 log lines are in the zip.",
    }[log_lines]
    assert want in text.splitlines(), text

    monkeypatch.setattr(doctor, "running_status", lambda _p: _status(True, None, "follower: timeout id 3"))
    text, _t = doctor.run(home, tmp_path / "out", ping=False, probe_cameras=False, echo=lambda _s: None)
    running = text.split("Running Station:\n")[1].split("\n\n")[0].splitlines()
    assert running[2] == "    follower: calibrated, bus errors 2, last: follower: timeout id 3", running
    assert running[3] == "    leader: calibrated, bus errors 0", running


def test_raw_dump_line_of_a_servo_that_answered_one_block_has_no_python_values() -> None:
    """QD-11: only block 56-70 answered: the values of the other blocks are "-", not None."""
    live = bytes(range(15))
    dump = {
        "baud": 1_000_000,
        "motors": {
            "1": {
                "blocks": {
                    "0-4": {"answer": None, "error": "no answer"},
                    "13-15": {"answer": None, "error": "no answer"},
                    "56-70": {"answer": "ff", "data": live.hex(" "), "error_byte": 0},
                },
                "decoded": doctor.decode_raw({56 + i: b for i, b in enumerate(live)}),
            }
        },
    }
    text = "\n".join(doctor._raw_lines(dump))
    assert "None" not in text.split(), text
    assert "-> fw - model - " in text and "(max limit - C)" in text


#: What a Python container / constant looks like when it leaks into the report (QD-11, QD-16).
PY_LITERAL = (
    r"\{'|\{\"|\['|\[\"|\[\]|\{\}|\(\)|', '|\", \"|'[\w./ -]+': |\"[\w./ -]+\": "
    r"|\b(?:None|True|False)\b|[\[(]\d+(?:, \d+)+[\])]"
)


def _python_literals(text: str) -> list[str]:
    """Lines with a Python literal. What follows "last error: " is the bus library's own exception
    text (e.g. lerobot's "motor IDs [1, 2, 3]"), quoted as is for the engineer, not a value of ours."""
    import re

    return [line for line in text.splitlines() if re.search(PY_LITERAL, line.split("last error: ")[0])]


def test_python_literal_scan_catches_every_container_repr() -> None:
    """The scan of the next test sees the dict / list / bool forms QC found (QD-16)."""
    for leaked in (
        "  desk (active): cameras []",
        "  demo_so101 (active): cameras ['front', 'wrist']",
        "  ids answering at 1 Mbps {'1': 777, '2': 777}",
        "    calibration file vs motors: {'shoulder_pan': 'match'}",
        "    motors carry the calibration of: ['/c/a.json', '/c/b.json']",
        "    bus errors: {'errors': 3}",
        "  front  V4L2  {'width': 640}",
        "    status []",
        "  x None y",
    ):
        assert _python_literals(leaked), leaked


def test_report_text_has_no_python_containers_anywhere(
    tmp_path: Path, emus: tuple[STSEmulator, STSEmulator], monkeypatch: pytest.MonkeyPatch
) -> None:
    """QD-16: the whole report (two real arms, a LeLab copy the motors also carry, a silent motor,
    cameras, a running Station with an alert) is plain text: no dict / list / None / True / False."""
    f, ld = emus
    home = _calibrated_home(tmp_path, f, ld, monkeypatch)
    lelab = tmp_path / "calibration" / "robots" / "so101_follower"
    lelab.mkdir(parents=True)
    (lelab / "arm_follower.json").write_text(json.dumps(lelab_calibration()), encoding="utf-8")
    store = ProfileStore(StationPaths(home).robots)
    prof = store.get("arm")
    store.put(prof.model_copy(update={"cameras": {"wrist": CameraProfile(), "front": CameraProfile()}}))
    ld.servos[6].dead = True  # a ping error on the bus, "motor did not answer" in the comparison
    status = _status(True, None, "follower: timeout id 3")
    status["status"]["alerts"] = [
        {"level": "warning", "message_key": "bus.slow", "params": {"arm": "leader", "ids": [1, 2]}}
    ]
    status["status"]["last_session"] = {"kind": "teleop", "fps": 30, "loop": {"latency_ms_p50": 12.5}}
    monkeypatch.setattr(doctor, "running_status", lambda _p: status)
    monkeypatch.setattr(
        doctor,
        "cameras",
        lambda: [
            {
                "id": "/dev/video0",
                "backend_api": "V4L2",
                "default_stream_profile": {"fourcc": "MJPG", "width": 640, "height": 480, "fps": 30.0},
            }
        ],
    )
    text, _t = doctor.run(home, tmp_path / "out", probe_cameras=True, echo=lambda _s: None)
    assert _python_literals(text) == [], text

    lines = text.splitlines()
    assert "  arm (active): cameras front, wrist" in lines, text
    fol = next(x for x in lines if x.startswith("  arm follower on "))
    assert fol.endswith(": ids answering at 1 Mbps: 1-6 (model 777)"), fol
    lead = next(x for x in lines if x.startswith("  arm leader on "))
    assert lead.endswith(": ids answering at 1 Mbps: 1-5 (model 777)"), lead
    assert "    calibration file vs motors: all 6 match" in lines, text
    assert "    calibration file vs motors: 5 of 6 match; gripper: motor did not answer" in lines, text
    carry = [x for x in lines if x.startswith("    motors carry the calibration of: ")]
    assert carry[0].endswith(
        str(Path("so_follower", "arm_follower.json")) + ", " + str(lelab / "arm_follower.json")
    ), carry
    assert "  /dev/video0  V4L2  640x480 30 fps MJPG" in lines, text
    bus = next(x for x in lines if x.startswith("    bus errors: ") and "ping [6] x" in x)
    assert "retried ok (" in bus and "; last error: " in bus, bus
    assert "    alert warning bus.slow: arm leader, ids 1, 2" in lines, text


def test_calibration_file_times_are_local_with_their_offset(monkeypatch: pytest.MonkeyPatch) -> None:
    """QD-19: the listing stores UTC; the report must show local time and say which offset."""
    import re

    shown = doctor._local_time("2026-11-17T10:35:15.123456+00:00")
    assert re.fullmatch(r"\d{4}-\d\d-\d\d \d\d:\d\d:\d\d UTC[+-]\d\d:\d\d", shown), shown
    assert doctor._local_time("not a time") == "not a time"
    if hasattr(time, "tzset"):  # POSIX: pin the zone and check the exact local time
        monkeypatch.setenv("TZ", "Asia/Ho_Chi_Minh")
        time.tzset()
        try:
            assert doctor._local_time("2026-11-17T10:35:15+00:00") == "2026-11-17 17:35:15 UTC+07:00"
        finally:
            monkeypatch.delenv("TZ")
            time.tzset()
