"""``hibiscus-station doctor`` against emulated STS3215 chains (``tests/sts_emulator.py``). POSIX only.

K-11 / SP-1 / REG-13: current, load and a raw register dump of every servo on every port, read
only. D-15, D-21: the LIKELY PROBLEMS section. The zip carries no token.
"""

from __future__ import annotations

import json
import sys
import zipfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

if sys.platform == "win32":  # pragma: no cover
    pytest.skip("pseudo-terminals are POSIX only", allow_module_level=True)

from sts_emulator import STSEmulator, lelab_calibration, sm_encode

from hibiscus_station import doctor
from hibiscus_station.profiles import FollowerProfile, LeaderProfile, ProfileStore, RobotProfile
from hibiscus_station.settings import StationPaths

WRITES = {"write", "sync_write"}


@pytest.fixture
def emus() -> Iterator[tuple[STSEmulator, STSEmulator]]:
    f, ld = STSEmulator(seed=1, voltage_v=12.0), STSEmulator(seed=2)
    yield f, ld
    f.close()
    ld.close()


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
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A demo profile active, the real arm on a USB port no profile names: it is still dumped."""
    emu = STSEmulator(seed=3)
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


def test_raw_dump_reports_a_missing_servo(tmp_path: Path) -> None:
    emu = STSEmulator(ids=(1, 2))
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
    tmp_path: Path, emus: tuple[STSEmulator, STSEmulator], monkeypatch: pytest.MonkeyPatch
) -> None:
    """AT-77 step 6: LeLab (here a child process) has the follower's port open."""
    import subprocess

    f, ld = emus
    home = _calibrated_home(tmp_path, f, ld, monkeypatch)
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
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    emu = STSEmulator(seed=4).realistic(usb_in_s=0.016)  # a slow adapter / hub
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
