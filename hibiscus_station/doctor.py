"""``hibiscus-station doctor``: one report a user can send when the arm does not work.

Collects versions, serial ports (VID:PID, stable path, who holds them), cameras, calibration files,
robot profiles and the calibration each one expects, the running Station's status, the last log
lines, and (when the port is free) a read-only ping of every motor on each configured arm and on
every other USB serial port: model, firmware, voltage, temperature, current, load, status, EEPROM
calibration compared with the file, plus a raw dump of registers 0-4, 13-15 and 56-70 of each
servo, read with one plain READ instruction per block (no sync read, no rustypot decoding) so a
field report shows the exact bytes the servo sent (REG-13). Nothing is written to a motor and no
torque is switched on: only PING, READ and SYNC_READ instructions are sent.

The report is printed and saved with copies of the files into ``hibiscus-station-doctor-<ts>.zip``.
Login tokens and Hibiscus PATs never go in: the token file and ``server.json`` are skipped and every
text goes through :func:`hibiscus_station.logs.redact`.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import platform
import sys
import time
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from hibiscus_station import __version__
from hibiscus_station.logs import redact
from hibiscus_station.settings import StationPaths, calibration_root

LOG_LINES = 200
MOTOR_IDS = range(1, 7)
#: Registers read per motor (all read-only for the motor: nothing is written).
PING_REGISTERS = (
    "Firmware_Major_Version",
    "Firmware_Minor_Version",
    "Present_Position",
    "Homing_Offset",
    "Min_Position_Limit",
    "Max_Position_Limit",
    "Present_Voltage",
    "Min_Voltage_Limit",
    "Max_Voltage_Limit",
    "Present_Temperature",
    "Max_Temperature_Limit",
    "Present_Current",
    "Present_Load",
    "Protection_Current",
    "Status",
    "Torque_Enable",
    "Lock",
    "Return_Delay_Time",
    "Operating_Mode",
)

#: Register blocks dumped raw from every servo id, one READ instruction each (SP-1): firmware and
#: model (0-4), temperature and voltage limits (13-15), the live block (56-70: position, speed,
#: load, voltage, temperature, status, moving, current).
RAW_BLOCKS: tuple[tuple[int, int], ...] = ((0, 5), (13, 3), (56, 15))
RAW_BAUD = 1_000_000
RAW_TIMEOUT_S = 0.1
FEETECH_READ = 0x02  # the only instruction the raw dump sends


def _checksum(body: bytes) -> int:
    return (~sum(body)) & 0xFF


def read_packet(motor_id: int, addr: int, length: int) -> bytes:
    """A Feetech READ instruction (never a write): ``FF FF id 4 0x02 addr length checksum``."""
    body = bytes([motor_id, 4, FEETECH_READ, addr, length])
    return b"\xff\xff" + body + bytes([_checksum(body)])


def _read_answer(ser: Any, motor_id: int, timeout_s: float) -> bytes | None:
    """The first well-formed status packet from ``motor_id`` (None on timeout)."""
    buf = bytearray()
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        chunk = ser.read(ser.in_waiting or 1)
        if chunk:
            buf += chunk
        while True:
            start = buf.find(b"\xff\xff")
            if start < 0:
                del buf[:-1]
                break
            del buf[:start]
            if len(buf) < 4:
                break
            total = 4 + buf[3]
            if len(buf) < total:
                break
            pkt = bytes(buf[:total])
            del buf[:total]
            if pkt[2] == motor_id and _checksum(pkt[2:-1]) == pkt[-1]:
                return pkt
    return None


def _u16(b: dict[int, int], addr: int) -> int | None:
    lo, hi = b.get(addr), b.get(addr + 1)
    return None if lo is None or hi is None else lo | (hi << 8)


def decode_raw(b: dict[int, int]) -> dict[str, Any]:
    """Values from the raw bytes, with the same masks, units and plausibility rules as telemetry
    (:mod:`hibiscus_station.hw.feetech`). ``*_plausible`` False: Station shows the value as unknown."""
    from hibiscus_station.hw import feetech

    out: dict[str, Any] = {
        "firmware": f"{b[0]}.{b[1]}" if 0 in b and 1 in b else None,
        "model_number": _u16(b, 3),
        "max_temperature_limit_c": b.get(13),
        "max_voltage_limit_v": feetech.decode_voltage(b[14]) if 14 in b else None,
        "min_voltage_limit_v": feetech.decode_voltage(b[15]) if 15 in b else None,
        "present_position_raw": _u16(b, 56),
        "present_speed_raw": _u16(b, 58),
    }
    rows = (
        ("temp_c", "temperature_raw", b.get(63)),
        ("voltage_v", "voltage_raw", b.get(62)),
        ("current_a", "current_raw", _u16(b, 69)),
        ("load_pct", "load_raw", _u16(b, 60)),
        ("status", "status_raw", b.get(65)),
    )
    for group, raw_key, raw in rows:
        out[raw_key] = raw
        if raw is None:
            out[group] = None
            continue
        value = feetech.decode(group, raw)
        out[group] = value
        if group != "status":
            out[f"{group}_plausible"] = feetech.plausible(group, value)
    if out.get("max_temperature_limit_c") is not None:
        lo, hi = feetech.PLAUSIBLE_MAX_TEMP_C
        out["max_temperature_limit_plausible"] = lo <= out["max_temperature_limit_c"] <= hi
    return out


def raw_dump(port: str, ids: Any = MOTOR_IDS, *, timeout_s: float = RAW_TIMEOUT_S) -> dict[str, Any]:
    """Each servo's :data:`RAW_BLOCKS`, read with plain READ instructions through pyserial (not
    rustypot, so a decoding error there cannot hide here). Read only: nothing else is sent."""
    import serial

    out: dict[str, Any] = {"baud": RAW_BAUD, "blocks": [list(b) for b in RAW_BLOCKS], "motors": {}}
    try:
        ser = serial.Serial(port, RAW_BAUD, timeout=0.005, write_timeout=1)
    except Exception as exc:
        out["error"] = f"cannot open: {type(exc).__name__}: {exc}"
        return out
    try:
        ser.reset_input_buffer()
        for mid in ids:
            row: dict[str, Any] = {"blocks": {}}
            regs: dict[int, int] = {}
            for addr, length in RAW_BLOCKS:
                req = read_packet(mid, addr, length)
                ser.write(req)
                ser.flush()
                ans = _read_answer(ser, mid, timeout_s)
                blk: dict[str, Any] = {"request": req.hex(" ")}
                if ans is None:
                    blk["answer"] = None
                    blk["error"] = "no answer"
                else:
                    params = ans[5:-1]
                    blk["answer"] = ans.hex(" ")
                    blk["error_byte"] = ans[4]
                    blk["data"] = params.hex(" ")
                    if len(params) != length:
                        blk["error"] = f"answered {len(params)} bytes, asked {length}"
                    for i, v in enumerate(params[:length]):
                        regs[addr + i] = v
                row["blocks"][f"{addr}-{addr + length - 1}"] = blk
            if regs:
                row["decoded"] = decode_raw(regs)
            else:
                row["error"] = "no answer"
            out["motors"][str(mid)] = row
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        try:
            ser.close()
        except Exception:  # noqa: S110 - best effort close
            pass
    return out


def decode_registers(row: dict[str, Any]) -> dict[str, Any]:
    """The telemetry values of one motor's lerobot reads, decoded as Station's telemetry does."""
    from hibiscus_station.hw import feetech

    out: dict[str, Any] = {}
    for group, reg in (
        ("temp_c", "Present_Temperature"),
        ("voltage_v", "Present_Voltage"),
        ("current_a", "Present_Current"),
        ("load_pct", "Present_Load"),
        ("status", "Status"),
    ):
        raw = row.get(reg)
        if not isinstance(raw, int):
            continue
        value = feetech.decode(group, raw)
        out[group] = value
        if group != "status":
            out[f"{group}_plausible"] = feetech.plausible(group, value)
    return out


def _pkg_version(name: str) -> str | None:
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version(name)
    except PackageNotFoundError:
        return None


def versions() -> dict[str, Any]:
    return {
        "hibiscus_station": __version__,
        "python": sys.version.split()[0],
        "executable": sys.executable,
        "os": platform.platform(),
        "machine": platform.machine(),
        "lerobot": _pkg_version("lerobot"),
        "rustypot": _pkg_version("rustypot"),
        "pyserial": _pkg_version("pyserial"),
        "opencv": _pkg_version("opencv-python") or _pkg_version("opencv-python-headless"),
    }


# ----------------------------------------------------------------------------------------- ports
def port_holders(device: str) -> list[str]:
    """Processes that have ``device`` open (Linux ``/proc``; empty elsewhere)."""
    if not sys.platform.startswith("linux"):
        return []
    try:
        real = os.path.realpath(device)
    except OSError:
        return []
    out: list[str] = []
    for pid in os.listdir("/proc"):
        if not pid.isdigit() or int(pid) == os.getpid():
            continue
        fd_dir = f"/proc/{pid}/fd"
        try:
            fds = os.listdir(fd_dir)
        except OSError:
            continue
        for fd in fds:
            try:
                if os.readlink(f"{fd_dir}/{fd}") == real:
                    cmd = (
                        Path(f"/proc/{pid}/cmdline")
                        .read_bytes()
                        .replace(b"\0", b" ")
                        .decode(errors="replace")
                    )
                    out.append(f"pid {pid}: {cmd.strip()[:160]}")
                    break
            except OSError:
                continue
    return out


def station_lock_holder(paths: StationPaths, device: str) -> int | None:
    """PID of the Station process holding ``device``'s lock file, if any."""
    from hibiscus_station.hw.locks import DeviceBusyError, DeviceLock

    lk = DeviceLock(paths.locks, device)
    if not lk.path.exists():
        return None
    try:
        lk.acquire()
    except DeviceBusyError as exc:
        return exc.holder or -1
    except OSError:
        return None
    lk.release()
    return None


def ports(paths: StationPaths) -> list[dict[str, Any]]:
    from hibiscus_station.hw.ports import list_ports

    rows = list_ports(usb_only=True)  # the arms' adapters are USB; ttyS* legacy ports are noise
    for r in rows:
        dev = str(r["device"])
        r["station_lock_pid"] = station_lock_holder(paths, dev)
        r["open_by"] = port_holders(dev)
    return rows


# ----------------------------------------------------------------------------------- calibration
def calibrations(cal_root: Path) -> list[dict[str, Any]]:
    from hibiscus_station.hw.factory import calibration_files

    out = []
    for f in calibration_files(cal_root):
        row = dict(f)
        try:
            data = json.loads(Path(f["path"]).read_text(encoding="utf-8"))
            row["motors"] = {
                m: {k: v.get(k) for k in ("id", "homing_offset", "range_min", "range_max")}
                for m, v in data.items()
            }
        except Exception as exc:
            row["error"] = f"{type(exc).__name__}: {exc}"
        out.append(row)
    return out


def profiles(paths: StationPaths, cal_root: Path) -> dict[str, Any]:
    from hibiscus_station.hw.factory import follower_calibration_dir, leader_calibration_dir
    from hibiscus_station.profiles import ProfileStore

    try:
        store = ProfileStore(paths.robots)
    except Exception as exc:
        return {"error": f"{paths.robots}: {type(exc).__name__}: {exc}", "robots": []}
    robots = []
    for p in store.list():
        f = follower_calibration_dir(cal_root) / f"{p.follower.calibration_id}.json"
        arms = {
            "follower": {
                "type": p.follower.type,
                "port": p.follower.port,
                "calibration_id": p.follower.calibration_id,
                "expects": str(f),
                "file_exists": f.is_file(),
            }
        }
        if p.leader is not None:
            lf = leader_calibration_dir(cal_root) / f"{p.leader.calibration_id}.json"
            arms["leader"] = {
                "type": p.leader.type,
                "port": p.leader.port,
                "calibration_id": p.leader.calibration_id,
                "expects": str(lf),
                "file_exists": lf.is_file(),
            }
        robots.append(
            {"id": p.id, "name": p.name, "mock": p.is_mock, "arms": arms, "cameras": sorted(p.cameras)}
        )
    return {"active": store.active, "robots": robots}


# ----------------------------------------------------------------------------------------- motors
def ping_arm(
    port: str,
    calibration: dict[str, Any] | None = None,
    candidates: dict[str, dict[str, Any]] | None = None,
    *,
    raw: bool = True,
    vid_pid: str | None = None,
    calibration_file: str | None = None,
) -> dict[str, Any]:
    """Read-only check of an SO-101 arm on ``port``: which ids answer, their registers, and
    (``raw``) a raw dump of every id once the lerobot bus is closed again."""
    from lerobot.motors import Motor, MotorNormMode

    from hibiscus_station.hw.bus import StationMotorsBus

    motors = {f"id{i}": Motor(i, "sts3215", MotorNormMode.RANGE_M100_100) for i in MOTOR_IDS}
    bus = StationMotorsBus(port, motors, arm="doctor")
    out: dict[str, Any] = {"port": port, "motors": {}}
    t0 = time.perf_counter()
    try:
        bus.connect(handshake=False)
    except Exception as exc:
        out["error"] = f"cannot open: {exc.__cause__ or exc}"
        return out
    try:
        try:
            from rustypot import find_model

            found = find_model("sts3215")
            if found is None:
                raise ValueError("rustypot has no sts3215 definition")
            _, definition = found
            out["scan_1mbps"] = {str(k): v for k, v in sorted(bus._scan(definition).items())}
        except Exception as exc:
            out["scan_1mbps"] = f"{type(exc).__name__}: {exc}"
        for name, m in motors.items():
            row: dict[str, Any] = {}
            key = f"ping Model_Number [{m.id}]"
            missed = bus.errors[key]
            model = bus.ping(name, num_retry=PING_RETRIES)
            row["model_number"] = model
            # The one source of truth for "this motor answers": a ping, with retries (QD-24).
            row["ping_tries"] = bus.errors[key] - missed + (model is not None)
            if model is None:
                row["error"] = "no answer"
                out["motors"][str(m.id)] = row
                continue
            for reg in PING_REGISTERS:
                try:
                    row[reg] = bus.read(reg, name, normalize=False, num_retry=1)
                except Exception as exc:
                    row[reg] = f"error: {exc}"
            row["decoded"] = decode_registers(row)
            out["motors"][str(m.id)] = row
        out["sync_read_present_position"] = time_sync_reads(bus)
        out["usb_chip"] = usb_chip(vid_pid)
        verdict = bus_verdict(out)
        out["bus_verdict"] = verdict
        out["teleop_estimate"] = verdict["estimate"] if verdict else None
        if calibration:
            out["calibration_vs_eeprom"] = _compare(calibration, out["motors"])
            out["calibration_file"] = calibration_file
        # Which calibration file (any id, e.g. LeLab's) the motors' EEPROM carries now.
        out["eeprom_matches"] = [
            path
            for path, cal in (candidates or {}).items()
            if cal and all(v == "match" for v in _compare(cal, out["motors"]).values())
        ]
    finally:
        out["bus_errors"] = bus.error_summary()
        try:
            bus.disconnect(disable_torque=False)
        except Exception:  # noqa: S110 - best effort close
            pass
    if raw:
        out["raw_dump"] = raw_dump(port)
    out["seconds"] = round(time.perf_counter() - t0, 2)
    return out


#: Pings per motor (1 + retries) before it counts as silent.
PING_RETRIES = 2
#: Sync reads timed per arm, and how many of them must succeed for a speed estimate (QD-23).
SYNC_READS = 20
MIN_OK_READS = 5
#: Classes of a failed read: the servo did not answer (timeout), it answered but the packet was
#: corrupt (checksum), the answers did not parse (in a sync read, mostly one servo's answer missing
#: so the next one's came in its place), anything else. Their words in the report.
READ_FAILURES: dict[str, str] = {
    "no_answer": "got no answer",
    "corrupt": "got corrupted answers (checksum)",
    "garbled": "got malformed answers (parse error: a servo's answer missing or cut short)",
    "other": "failed with another error",
}


def read_failure(exc: BaseException) -> str:
    """The class (a key of :data:`READ_FAILURES`) of a failed bus read, from rustypot's words:
    ``... Operation timed out``, ``... Checksum error`` or ``... Parsing error`` (a sync read whose
    answer of one servo is missing reads the next servo's answer in its place)."""
    text = f"{exc} {exc.__cause__ or ''}".lower()
    if "checksum" in text:
        return "corrupt"
    if any(w in text for w in ("timed out", "timeout", "no answer", "no status")):
        return "no_answer"
    if "parsing error" in text or "parse error" in text:
        return "garbled"
    return "other"


def time_sync_reads(bus: Any, n: int = SYNC_READS) -> dict[str, Any]:
    """``n`` sync reads of Present_Position, no retry: how many worked, how fast (the successful
    ones only: a failed read waits for a timeout, QD-21) and the failures by class (QD-24)."""
    by_class = dict.fromkeys(READ_FAILURES, 0)
    ok_ms: list[float] = []
    for _ in range(n):
        t = time.perf_counter()
        try:
            bus.sync_read("Present_Position", normalize=False, num_retry=0)
        except Exception as exc:
            by_class[read_failure(exc)] += 1
        else:
            ok_ms.append((time.perf_counter() - t) * 1000)
    return {
        "reads": n,
        "ok": len(ok_ms),
        "failed": n - len(ok_ms),
        **by_class,
        "ms_per_read": round(sum(ok_ms) / len(ok_ms), 2) if ok_ms else None,
    }


def failures_text(sr: dict[str, Any]) -> str:
    """``"3 got no answer, 2 got corrupted answers (checksum)"``: the failed reads by class."""
    parts = [f"{sr[k]} {words}" for k, words in READ_FAILURES.items() if sr.get(k)]
    return ", ".join(parts) or "failed"


BUS_ADVICE = (
    "check the 3-pin cables between the servos, the power supply (it may drop under load) and plug "
    "the USB adapter straight into the PC"
)


def bus_verdict(a: dict[str, Any]) -> dict[str, Any] | None:
    """The one conclusion about an arm's bus that every line of the report repeats (QD-21 - QD-24).

    Inputs: the ping of each motor (with retries: the only source of "a motor answers"), the
    ``SYNC_READS`` timed sync reads (ok / failed by class / ms of the reads that worked), the USB
    chip. ``N`` is :data:`MIN_OK_READS`.

    ===========  =================  ===============================  ===================  ==============
    motors       sync reads         LIKELY PROBLEMS                  teleop estimate      slow-bus advice
    (ping)                                                                                (D-21)
    ===========  =================  ===============================  ===================  ==============
    some silent  any (they fail)    "motor id(s) X do not answer     not measured (motor  never
                                    (power? cable?)"                 id(s) X do not
                                                                     answer)
    all answer   all ok             nothing (slow-bus advice if      ~Hz                  if > 6 ms per
                                    slow)                                                 read
    all answer   some fail, >= N    "unreliable bus: F of R reads    ~Hz (speed of the K  if slow and
                 ok                 failed (A got no answer, C got   reads that worked)   fewer reads
                                    corrupted answers (checksum), G                       failed than
                                    got malformed answers (parse                          worked
                                    error ...), O failed with
                                    another error) although every
                                    motor answers a ping; <cables,
                                    power, USB>"
    all answer   < N ok             the same "unreliable bus" line   not measured (too    never
                                                                     few reads
                                                                     succeeded: K of R)
    ===========  =================  ===============================  ===================  ==============

    Only the classes that happened are named, so a checksum error is never called "no answer".
    The scan line of the summary (:func:`answering_text`) is derived from the same pings.

    Returns ``{"kind": "silent" | "unreliable" | "ok", "silent": [ids], "problem": str | None,
    "estimate": dict | None, "not_measured": str | None, "estimate_of": str | None}``, or None
    when no motor was pinged (port not opened).
    """
    motors = a.get("motors") or {}
    if not motors:
        return None
    silent = [k for k, m in motors.items() if m.get("error")]
    out: dict[str, Any] = {
        "kind": "ok",
        "silent": silent,
        "problem": None,
        "estimate": None,
        "not_measured": None,
        "estimate_of": None,
    }
    if silent:
        ids = ", ".join(silent)
        out.update(
            kind="silent",
            problem=f"motor id(s) {ids} do not answer (power? cable?)",
            not_measured=f"motor id(s) {ids} do not answer",
        )
        return out
    sr = a.get("sync_read_present_position")
    if not sr:
        return out
    reads, failed = int(sr.get("reads") or 0), int(sr.get("failed") or 0)
    ok = int(sr["ok"]) if sr.get("ok") is not None else reads - failed
    if failed:
        out.update(
            kind="unreliable",
            problem=(
                f"unreliable bus: {failed} of {reads} reads failed ({failures_text(sr)}) although "
                f"every motor answers a ping; {BUS_ADVICE}"
            ),
        )
    if ok < MIN_OK_READS or sr.get("ms_per_read") is None:
        out["not_measured"] = f"too few reads succeeded: {ok} of {reads}"
        return out
    est = teleop_estimate(sr["ms_per_read"], a.get("usb_chip"))
    if est and est.get("warning") and failed >= ok:
        del est["warning"]  # most reads failed: the bus is the problem, not the adapter's speed
    out["estimate"] = est
    if failed:
        out["estimate_of"] = f"speed of the {ok} reads that worked"
    return out


def answering_text(a: dict[str, Any]) -> str:
    """The ids that answer, from the pings (:func:`bus_verdict`'s source), never contradicting the
    per-motor lines; the one-shot broadcast scan only adds notes: ids it missed that answered a
    later ping, ids it saw that no ping reached, ids outside 1-6."""
    motors = a.get("motors") or {}
    scan = a.get("scan_1mbps")
    seen = scan if isinstance(scan, dict) else {}
    answering = {k: m["model_number"] for k, m in motors.items() if not m.get("error")}
    out = _scan_text(answering)
    retry = [
        int(k)
        for k, m in motors.items()
        if not m.get("error") and (int(m.get("ping_tries") or 1) > 1 or (seen and k not in seen))
    ]
    notes: list[str] = []
    if retry:
        notes.append(f"{_ranges(retry)} answered only on a retry")
    lost = [int(k) for k, m in motors.items() if m.get("error") and k in seen]
    if lost:
        notes.append(f"{_ranges(lost)} answered the first scan, then no ping")
    other = {k: v for k, v in seen.items() if k not in motors}
    if other:
        notes.append(f"other ids on the bus: {_scan_text(other)}")
    if scan is not None and not isinstance(scan, dict):
        notes.append(f"scan failed ({scan})")
    return out + "".join(f"; {n}" for n in notes)


#: A sync read of six STS3215 at 1 Mbaud takes ~1.5-3 ms through an adapter with a 1 ms USB
#: latency timer. Slower means a 16 ms latency timer (FTDI default on Windows) or a USB hub.
SLOW_READ_MS = 6.0


#: USB vendor id -> serial chip family. Only FTDI chips have a latency timer the user can set
#: (WCH CH340 / CH343, the SO-101 boards' chips, have none: D-21).
USB_CHIPS: dict[str, str] = {"0403": "FTDI", "1a86": "WCH", "10c4": "CP210x", "067b": "Prolific"}


def usb_chip(vid_pid: str | None) -> str | None:
    """``"FTDI"``, ``"WCH"``... from ``"vvvv:pppp"`` (None when unknown)."""
    if not vid_pid:
        return None
    return USB_CHIPS.get(vid_pid.split(":")[0].lower())


def slow_bus_advice(ms_per_read: float, chip: str | None) -> str:
    """What to do about a slow bus: the latency timer is named only for FTDI chips (D-21)."""
    head = f"slow bus ({ms_per_read} ms per read)"
    ftdi = (
        "set the FTDI adapter's latency timer to 1 ms (Windows: Device Manager > Ports > the COM port "
        "> Port Settings > Advanced)"
    )
    if chip == "FTDI":
        return f"{head}: {ftdi} and plug the arm straight into the PC, without a hub"
    if chip is not None:
        return (
            f"{head}: slow USB adapter / hub: plug the arm straight into the PC, without a hub "
            f"(a {chip} adapter has no latency timer to change)"
        )
    return (
        f"{head}: slow USB adapter / hub: plug the arm straight into the PC, without a hub; only if the "
        f"adapter is an FTDI chip (USB VID 0403): {ftdi}"
    )


def teleop_estimate(ms_per_read: float | None, chip: str | None = None) -> dict[str, Any] | None:
    """Teleop rate and leader -> follower latency this bus allows: one leader read plus one goal
    write (~1/3 of a read) per tick, a leader move waiting half a tick on average. ``chip``
    (:func:`usb_chip`) picks the advice for a slow bus."""
    if not ms_per_read or ms_per_read <= 0:
        return None
    tick = ms_per_read * 1.35 + 0.3
    from hibiscus_station.hw.loop import TELEOP_FPS

    tick = max(tick, 1000.0 / TELEOP_FPS)
    out: dict[str, Any] = {
        "hz": round(1000.0 / tick),
        "latency_ms": round(ms_per_read * 1.35 + tick / 2, 1),
    }
    if ms_per_read > SLOW_READ_MS:
        out["warning"] = slow_bus_advice(ms_per_read, chip)
    return out


NO_ANSWER = "motor did not answer"
#: Start of a comparison whose registers could not be read: a bus problem, never a mismatch (QD-26).
COULD_NOT_READ = "could not read"
CALIBRATION_REGISTERS = (
    ("homing_offset", "Homing_Offset"),
    ("range_min", "Min_Position_Limit"),
    ("range_max", "Max_Position_Limit"),
)


def _compare(cal: dict[str, Any], motors: dict[str, Any]) -> dict[str, Any]:
    """Each motor of a calibration file against the motor's EEPROM: ``"match"``, the values that
    differ, :data:`NO_ANSWER`, or ``"could not read <registers>"`` when a register needed for the
    comparison could not be read (QD-26): that is a bus problem, never a calibration mismatch."""
    out: dict[str, Any] = {}
    for name, v in cal.items():
        row = motors.get(str(v.get("id")), {})
        if not row or row.get("error"):
            out[name] = NO_ANSWER  # listed as "do not answer", never as a calibration mismatch
            continue
        diffs, unread = [], []
        for key, reg in CALIBRATION_REGISTERS:
            value = row.get(reg)
            if not isinstance(value, int) or isinstance(value, bool):
                unread.append(reg)
            elif value != v.get(key):
                diffs.append(f"{key}: file {v.get(key)} motor {value}")
        if diffs:
            out[name] = "; ".join(diffs + ([f"{COULD_NOT_READ} {', '.join(unread)}"] if unread else []))
        elif unread:
            out[name] = f"{COULD_NOT_READ} {', '.join(unread)}"
        else:
            out[name] = "match"
    return out


def _unread(d: Any) -> bool:
    return isinstance(d, str) and d.startswith(COULD_NOT_READ)


# ------------------------------------------------------------------------------------- the report
def running_status(paths: StationPaths) -> dict[str, Any] | None:
    """``GET /api/v1/status`` of the running Station (None when none runs).

    A ``station.pid`` left behind by a Station that was killed (nothing listens on its port) is
    "not running" with ``stale_pid`` set, never a raw connection error (D-15)."""
    try:
        info = json.loads(paths.pid.read_text(encoding="utf-8"))
        token = paths.token.read_text(encoding="utf-8").strip()
    except (OSError, ValueError):
        return None
    try:
        import httpx

        port = int(info.get("port", 18210))
        r = httpx.get(
            f"http://127.0.0.1:{port}/api/v1/status",
            headers={"Authorization": f"Bearer {token}", "Host": f"127.0.0.1:{port}"},
            timeout=3,
        )
        return {"pid": info.get("pid"), "http": r.status_code, "status": r.json()}
    except Exception as exc:
        import httpx

        if isinstance(exc, httpx.ConnectError):
            return {"not_running": True, "stale_pid": info.get("pid")}
        return {"pid": info.get("pid"), "error": f"{type(exc).__name__}: {exc}"}


def log_tail(paths: StationPaths, lines: int = LOG_LINES) -> list[str]:
    f = paths.logs / "station.log"
    try:
        text = f.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    return [redact(x) for x in text[-lines:]]


def cameras() -> list[dict[str, Any]] | str:
    try:
        from hibiscus_station.hw.cameras import find_opencv_cameras

        return find_opencv_cameras()
    except Exception as exc:
        return f"{type(exc).__name__}: {exc}"


def collect(
    paths: StationPaths,
    cal_root: Path,
    *,
    ping: bool = True,
    probe_cameras: bool = True,
    echo: Callable[[str], None] = lambda _s: None,
) -> dict[str, Any]:
    echo("versions...")
    report: dict[str, Any] = {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "versions": versions()}
    report["home"] = str(paths.home)
    report["calibration_root"] = str(cal_root)
    echo("serial ports...")
    report["ports"] = ports(paths)
    echo("calibration files and profiles...")
    report["calibrations"] = calibrations(cal_root)
    report["profiles"] = profiles(paths, cal_root)
    echo("running Station...")
    running = running_status(paths)
    report["running"] = running
    if probe_cameras:
        echo("cameras...")
        report["cameras"] = cameras()
    arms: list[dict[str, Any]] = []
    if ping:
        arms = check_arms(paths, report, echo)
    report["arms"] = arms
    report["ping"] = ping
    report["warnings"] = warnings(report)
    report["log_tail"] = log_tail(paths)
    return report


def _targets(report: dict[str, Any]) -> list[tuple[str, str, str, str | None]]:
    """(robot, arm, port, calibration file the profile expects) for every arm port in the profiles,
    then every other detected USB serial port (an arm without a profile, e.g. while a demo profile
    is active): each port once."""
    from hibiscus_station.hw.locks import normalize_device

    out: list[tuple[str, str, str, str | None]] = []
    seen: set[str] = set()
    for robot in report["profiles"].get("robots", []):
        for arm, a in robot["arms"].items():
            port = str(a["port"])
            if port.startswith("mock://") or normalize_device(port) in seen:
                continue
            seen.add(normalize_device(port))
            out.append((str(robot["id"]), arm, port, a.get("expects")))
    for row in report["ports"]:
        port = str(row["device"])
        if normalize_device(port) in seen:
            continue
        seen.add(normalize_device(port))
        out.append(("-", "no profile", port, None))
    return out


def _vid_pid(report: dict[str, Any], port: str) -> str | None:
    from hibiscus_station.hw.locks import normalize_device

    for p in report["ports"]:
        if normalize_device(str(p["device"])) == normalize_device(port) or p.get("stable_path") == port:
            vp = p.get("vid_pid")
            return str(vp) if vp else None
    return None


def check_arms(
    paths: StationPaths, report: dict[str, Any], echo: Callable[[str], None] = lambda _s: None
) -> list[dict[str, Any]]:
    """The read-only motor check of every target port that no program holds."""
    cal_by_path = {c["path"]: c.get("motors") for c in report["calibrations"]}
    arms: list[dict[str, Any]] = []
    for robot, arm, port, expects in _targets(report):
        row: dict[str, Any] = {"robot": robot, "arm": arm, "port": port}
        holder = station_lock_holder(paths, port)
        others = port_holders(port)
        if holder is not None:
            row["skipped"] = f"in use by Station (pid {holder}); stop it to ping the motors"
            row["held_by"] = [f"Station pid {holder}"]
        elif others:
            row["skipped"] = "in use by " + "; ".join(others)
            row["held_by"] = others
        elif not Path(port).exists() and os.name != "nt":
            row["skipped"] = "port not found (unplugged? another name now?)"
        else:
            echo(f"pinging {arm} on {port}...")
            same_arm = {
                c["path"]: c.get("motors")
                for c in report["calibrations"]
                if arm == "no profile" or c["arm"] == arm
            }
            row.update(
                ping_arm(
                    port,
                    cal_by_path.get(expects) if expects else None,
                    same_arm,
                    vid_pid=_vid_pid(report, port),
                    calibration_file=expects,
                )
            )
        arms.append(row)
    return arms


def _local_time(iso: str) -> str:
    """An ISO timestamp (UTC from the calibration listing) as local time with its offset, e.g.
    ``2026-11-17 17:35:15 UTC+07:00``, so it reads like the zip name and ``generated_at``."""
    try:
        t = dt.datetime.fromisoformat(iso)
    except (TypeError, ValueError):
        return str(iso)[:19]
    if t.tzinfo is None:
        t = t.replace(tzinfo=dt.UTC)
    t = t.astimezone()
    off = t.strftime("%z")  # e.g. +0700
    return f"{t:%Y-%m-%d %H:%M:%S} UTC{off[:3]}:{off[3:]}"


#: Port open errors that mean "another program has it" (Windows, macOS, Linux).
BUSY_MARKERS = ("access is denied", "permission denied", "resource busy", "busy", "errno 13", "errno 16")


def _looks_busy(error: str) -> bool:
    e = error.lower()
    return any(m in e for m in BUSY_MARKERS)


def lelab_copies(report: dict[str, Any], arm: str, a: dict[str, Any]) -> list[str]:
    """The folders (``so101_follower``...) of LeLab / older lerobot files that carry the
    calibration id a profile arm expects, outside the folder Station reads."""
    cal_id, expects = a.get("calibration_id"), a.get("expects")
    return [
        str(c.get("dir"))
        for c in report.get("calibrations", [])
        if c.get("arm") == arm and c.get("id") == cal_id and c.get("path") != expects
    ]


def warnings(report: dict[str, Any]) -> list[str]:
    """The likely causes the report shows, in plain words (first lines of the summary)."""
    out: list[str] = []
    prof = report["profiles"]
    robots = {r["id"]: r for r in prof.get("robots", [])}
    active = robots.get(prof.get("active") or "")
    real_ports = [p["device"] for p in report["ports"] if p.get("vid_pid")]
    running = (report.get("running") or {}).get("status") or {}
    connected = (running.get("robot") or {}) if isinstance(running, dict) else {}
    if connected.get("mock") or (active and active["mock"]):
        name = connected.get("id") or (active or {}).get("id")
        msg = f"MOCK PROFILE ACTIVE: '{name}' drives SIMULATED arms, the real arm will not move"
        if real_ports:
            msg += f" (real serial ports present: {', '.join(real_ports)}); create a profile for the real arm"
        out.append(msg)
    if not any(not r["mock"] for r in robots.values()):
        out.append("no profile for a real arm: Robot > New robot, pick the arm's serial port")
    for r in robots.values():
        for arm, a in r["arms"].items():
            if not r["mock"] and not a["file_exists"]:
                lelab = lelab_copies(report, arm, a)
                if lelab:
                    out.append(
                        f"{r['id']} {arm}: calibration '{a['calibration_id']}' is in LeLab's folder "
                        f"({', '.join(lelab)}), Station does not use it yet: Calibrate > Use this file"
                    )
                    continue
                found = [c["id"] for c in report["calibrations"] if c["arm"] == arm]
                out.append(
                    f"{r['id']} {arm}: no calibration '{a['calibration_id']}'"
                    + (f" (files found: {', '.join(found)} - Calibrate > Use this file)" if found else "")
                )
    run = report.get("running") or {}
    if run.get("error"):
        out.append(f"Station (pid {run.get('pid') or '?'}) does not answer: {run['error']}")
    checked: set[str] = set()
    for a in report.get("arms", []):
        checked.add(str(a["port"]))
        where = f"{a['robot']} {a['arm']} on {a['port']}"
        if a.get("held_by") and str(a["held_by"][0]).startswith("Station pid"):
            out.append(
                f"{where}: held by {a['held_by'][0]}, motors not checked: stop Station and run "
                "`hibiscus-station doctor --verbose` again"
            )
        elif a.get("held_by"):
            out.append(
                f"{where} is busy, held by {'; '.join(a['held_by'])}: close that program (LeLab, "
                "a lerobot-* command, Feetech FD) and run the doctor again"
            )
        elif a.get("skipped"):
            out.append(f"{where}: {a['skipped']}")
        if a.get("error") and _looks_busy(str(a["error"])):
            out.append(
                f"{where} is busy or not accessible ({a['error']}): another program holds it (LeLab, "
                "a lerobot-* command, Feetech FD, Arduino IDE); close it and run the doctor again"
            )
        elif a.get("error"):
            out.append(f"{where}: {a['error']}")
        verdict = bus_verdict(a) or {}
        if verdict.get("problem"):
            out.append(f"{a['robot']} {a['arm']}: {verdict['problem']}")
        cmp = a.get("calibration_vs_eeprom") or {}
        diffs = {m: d for m, d in cmp.items() if d not in ("match", NO_ANSWER) and not _unread(d)}
        unread = {m: str(d)[len(COULD_NOT_READ) + 1 :] for m, d in cmp.items() if _unread(d)}
        if unread:
            name = Path(str(a.get("calibration_file") or "")).stem or "?"
            what = "; ".join(f"{regs} of {m}" for m, regs in unread.items())
            out.append(
                f"{a['robot']} {a['arm']}: could not read register(s) {what} (a bus problem, not the "
                f"calibration): the calibration file '{name}' could not be checked for "
                f"{len(unread)} of {len(cmp)} motors; fix the bus and run the doctor again"
            )
        if diffs:
            names = list(diffs)
            first = f"{names[0]} {diffs[names[0]].split('; ')[0]}"
            detail = first if len(names) == 1 else f"{', '.join(names)}; first: {first}"
            name = Path(str(a.get("calibration_file") or "")).stem or "?"
            out.append(
                f"{a['robot']} {a['arm']}: calibration file '{name}' does not match the motors "
                f"({len(names)} of {len(cmp)} motors: {detail}); Connect writes the file to the "
                "motors: if it is not this arm's file, calibrate the arm again"
            )
        est = verdict.get("estimate") or {}
        if est.get("warning"):
            out.append(f"{where}: {est['warning']}")
        bad: dict[str, list[str]] = {}
        dump = (a.get("raw_dump") or {}).get("motors") or {}
        for mid, m in a.get("motors", {}).items():
            d = (dump.get(mid) or {}).get("decoded") or m.get("decoded") or {}
            for key, label in (
                ("temp_c", "temperature"),
                ("current_a", "current"),
                ("load_pct", "load"),
                ("voltage_v", "voltage"),
            ):
                if d.get(f"{key}_plausible") is False:
                    bad.setdefault(label, []).append(mid)
        for label, ids in bad.items():
            out.append(
                f"{a['robot']} {a['arm']}: motor id(s) {', '.join(ids)} report an impossible {label} "
                "(Station shows it as unknown); the raw register bytes are in the motor check below"
            )
    for p in report["ports"]:
        if p.get("open_by") and str(p["device"]) not in checked:
            out.append(f"{p['device']} is open by another program: {'; '.join(p['open_by'])}")
    return out


def motor_check_incomplete(report: dict[str, Any]) -> bool:
    """True when the motor check could not read every arm (skipped, held, no port, --no-ping)."""
    arms = report.get("arms") or []
    if not report.get("ping", True) or not arms:
        return True
    return any(a.get("skipped") or a.get("error") for a in arms)


def send_instructions(report: dict[str, Any], target: Path | None) -> list[str]:
    """The last lines, English then Vietnamese: the one file to send, and when to run again."""
    name = str(target.resolve()) if target is not None else "hibiscus-station-doctor-<time>.zip"
    again = motor_check_incomplete(report)
    no_ping = not report.get("ping", True)
    lines = [
        "WHAT TO SEND / CẦN GỬI GÌ",
        f"  EN: Send us this one file: {name}",
        "      It holds this report, the last log lines, the robot profiles and the calibration files;",
        "      no login token and no access token.",
    ]
    if no_ping:
        lines += [
            "      The motors were not checked (--no-ping): to send the full report, run",
            "      `hibiscus-station doctor --verbose` without --no-ping and send the new file instead.",
        ]
    elif again:
        lines += [
            "      The motor check is incomplete (see LIKELY PROBLEMS): close Station and LeLab, keep both",
            "      arms plugged in and powered, run `hibiscus-station doctor --verbose` again and send the",
            "      new file instead.",
        ]
    lines += [
        "      If we asked for it, add a screenshot of Feetech FD showing the temperature, voltage and",
        "      current of the same servos.",
        f"  VI: Bạn chỉ cần gửi cho chúng tôi một tệp: {name}",
        "      Tệp này có báo cáo này, các dòng nhật ký cuối, hồ sơ robot và các tệp hiệu chỉnh;",
        "      không có token đăng nhập hay token truy cập.",
    ]
    if no_ping:
        lines += [
            "      Động cơ chưa được kiểm tra (--no-ping): để gửi báo cáo đầy đủ, chạy",
            "      `hibiscus-station doctor --verbose` không có --no-ping rồi gửi tệp mới thay cho tệp này.",
        ]
    elif again:
        lines += [
            "      Phần kiểm tra động cơ chưa đủ (xem LIKELY PROBLEMS): tắt Station và LeLab, giữ cả hai tay",
            "      cắm cáp và có điện, chạy lại `hibiscus-station doctor --verbose` rồi gửi tệp mới thay cho",
            "      tệp này.",
        ]
    lines += [
        "      Nếu chúng tôi có nhờ, gửi kèm ảnh chụp màn hình Feetech FD có nhiệt độ, điện áp và dòng",
        "      của cùng các động cơ.",
    ]
    return lines


def summary(report: dict[str, Any], target: Path | None = None) -> str:
    """Human-readable lines (what the terminal shows), ending with what to send."""
    v = report["versions"]
    problems = report.get("warnings") or []
    lines = [
        "LIKELY PROBLEMS:",
        *([f"  ! {w}" for w in problems] or ["  No likely problems found"]),
        "",
        f"Hibiscus Station {v['hibiscus_station']} · Python {v['python']} · "
        f"lerobot {v['lerobot'] or 'not installed'} · rustypot {v['rustypot'] or 'not installed'}",
        f"OS: {v['os']} ({v['machine']})",
        f"Data: {report['home']}",
        f"Calibration folder: {report['calibration_root']}",
        "",
        "Serial ports:",
    ]
    if not report["ports"]:
        lines.append("  (none) - is the arm's USB cable plugged in? Windows: check Device Manager > Ports")
    for p in report["ports"]:
        held = []
        if p.get("station_lock_pid"):
            held.append(f"Station pid {p['station_lock_pid']}")
        held += p.get("open_by") or []
        lines.append(
            f"  {p['device']}  {p.get('vid_pid') or '-'}  {p.get('description') or ''}"
            + (f"  by-id {p['stable_path']}" if p.get("stable_path") else "")
            + (f"  OPEN BY: {', '.join(held)}" if held else "")
        )
    lines += ["", "Calibration files:"]
    if not report["calibrations"]:
        lines.append("  (none)")
    for c in report["calibrations"]:
        when = _local_time(c["modified_at"])
        lines.append(f"  {c['arm']:<8} {c['id']:<24} {c['dir']:<15} {when}  {c['path']}")
        if c.get("error"):
            lines.append(f"     ! {c['error']}")
    lines += ["", "Robot profiles:"]
    prof = report["profiles"]
    if prof.get("error"):
        lines.append(f"  ! {prof['error']}")
    for r in prof.get("robots", []):
        lines.append(
            f"  {r['id']}{' (active)' if r['id'] == prof.get('active') else ''}: "
            f"cameras {_text(r['cameras'])}"
        )
        for arm, a in r["arms"].items():
            lelab = [] if a["file_exists"] else lelab_copies(report, arm, a)
            if a["file_exists"]:
                ok = "found"
            elif lelab:
                ok = f"in LeLab's folder ({', '.join(lelab)}), not used by Station yet"
            else:
                ok = "MISSING"
            lines.append(f"    {arm}: {a['type']} on {a['port']}, calibration '{a['calibration_id']}' {ok}")
    run = report.get("running")
    lines += ["", "Running Station:"]
    if not run or run.get("not_running"):
        lines.append(
            "  Station is not running"
            + (
                f" (station.pid of pid {run['stale_pid']} left behind, nothing answers)"
                if run and run.get("stale_pid")
                else ""
            )
        )
    elif run.get("error"):
        lines.append(f"  pid {run.get('pid') or '?'} does not answer: {run['error']}")
    else:
        st = run["status"]
        robot = st.get("robot") or {}
        mode = "MOCK" if (st.get("station") or {}).get("mock") else "real"
        lines.append(
            f"  pid {run.get('pid') or '?'}: mode {mode}, state {st.get('state') or '?'}"
            + (f", reason {st['reason']}" if st.get("reason") else "")
            + (f", detail {st['detail']}" if st.get("detail") else "")
        )
        if robot:
            lines.append(
                f"  connected profile {_text(robot.get('id'))}"
                + (" [DEMO: simulated arms]" if robot.get("mock") else " (real arms)")
            )
        for arm, a in (robot.get("arms") or {}).items():
            if a:
                lines.append(
                    f"    {arm}: {'calibrated' if a.get('calibrated') else 'not calibrated'}"
                    + (f" ({a['issue']})" if a.get("issue") else "")
                    + f", bus errors {a.get('bus_errors') or 0}"
                    + (f", last: {a['last_bus_error']}" if a.get("last_bus_error") else "")
                )
        last = st.get("last_session") or {}
        lp = last.get("loop") or {}
        if lp.get("latency_ms_p50") is not None:
            lines.append(
                f"  last {_text(last.get('kind'))} session: {_text(lp.get('fps'))} Hz "
                f"(asked {_text(last.get('fps'))}), "
                f"leader -> follower latency ~{_text(lp.get('latency_ms_p50'))} ms "
                f"(p95 {_text(lp.get('latency_ms_p95'))} ms), overruns {_text(lp.get('overruns'))}"
            )
        for al in st.get("alerts", []):
            lines.append(
                f"    alert {_text(al.get('level'))} {_text(al.get('message_key'))}"
                + (f": {_text(al['params'])}" if al.get("params") else "")
            )
    cams = report.get("cameras")
    if cams is not None:
        lines += ["", "Cameras:"]
        if isinstance(cams, str):
            lines.append(f"  ! {cams}")
        else:
            lines += [
                f"  {_text(c.get('id'))}  {_text(c.get('backend_api'))}  "
                f"{_stream_text(c.get('default_stream_profile'))}"
                for c in cams
            ] or ["  (none)"]
    lines += ["", "Motor check (read only):"]
    if not report.get("ping", True):
        lines.append("  skipped (--no-ping): the serial ports were not opened")
    elif not report["arms"]:
        lines.append("  nothing to check: no real arm in the profiles and no USB serial port")
    for a in report["arms"]:
        head = f"  {a['robot']} {a['arm']} on {a['port']}"
        if a.get("skipped"):
            lines.append(f"{head}: skipped, {a['skipped']}")
            continue
        if a.get("error"):
            lines.append(f"{head}: {a['error']}")
            continue
        lines.append(f"{head}: ids answering at 1 Mbps: {answering_text(a)}")
        for mid, m in a.get("motors", {}).items():
            if m.get("error"):
                lines.append(f"    id {mid}: {m['error']}")
                continue
            g = {k: _text(m.get(k)) for k in ("model_number", *PING_REGISTERS)}
            lines.append(
                f"    id {mid}: model {g['model_number']} fw {g['Firmware_Major_Version']}."
                f"{g['Firmware_Minor_Version']} pos {g['Present_Position']} "
                f"{g['Present_Voltage']}x0.1V "
                f"(min {g['Min_Voltage_Limit']} max {g['Max_Voltage_Limit']}) "
                f"{g['Present_Temperature']}C (max {g['Max_Temperature_Limit']}) "
                f"status {g['Status']} "
                f"torque {g['Torque_Enable']} lock {g['Lock']} offset {g['Homing_Offset']} "
                f"limits {g['Min_Position_Limit']}-{g['Max_Position_Limit']}"
            )
            d = m.get("decoded") or {}
            lines.append(
                f"           current raw {g['Present_Current']} = {_fmt(d, 'current_a', 'A')} "
                f"load raw {g['Present_Load']} = {_fmt(d, 'load_pct', '%')} "
                f"temperature {_fmt(d, 'temp_c', 'C')} voltage {_fmt(d, 'voltage_v', 'V')} "
                f"status {_status_text(d.get('status'))} protection current raw {g['Protection_Current']}"
            )
        lines += _raw_lines(a.get("raw_dump"))
        if a.get("sync_read_present_position"):
            lines += _sync_read_lines(a)
        if a.get("calibration_vs_eeprom"):
            lines.append(f"    calibration file vs motors: {_compare_text(a['calibration_vs_eeprom'])}")
        if "eeprom_matches" in a:
            carry = _text(a["eeprom_matches"]) if a["eeprom_matches"] else "no file found"
            lines.append(f"    motors carry the calibration of: {carry}")
        be = a.get("bus_errors") or {}
        if be.get("errors"):
            lines.append(f"    bus errors: {_bus_errors_text(be)}")
    lines += ["", _log_line(len(report["log_tail"])), ""]
    lines += send_instructions(report, target)
    return redact("\n".join(lines))


def _sync_read_lines(a: dict[str, Any]) -> list[str]:
    """The timed sync reads and :func:`bus_verdict`'s conclusion, the same words as LIKELY PROBLEMS."""
    s = a["sync_read_present_position"]
    verdict = bus_verdict(a) or {}
    reads, failed = s.get("reads"), s.get("failed") or 0
    ok = s["ok"] if s.get("ok") is not None else (reads or 0) - failed
    if s.get("ms_per_read") is None:
        speed = "no read succeeded"
    elif failed:
        speed = f"{ok} worked, {s['ms_per_read']} ms each"
    else:
        speed = f"{s['ms_per_read']} ms each"
    detail = f" ({failures_text(s)})" if failed else ""
    lines = [f"    sync read: {failed}/{reads} failed{detail}, {speed}"]
    if verdict.get("kind") == "unreliable":
        lines.append(f"    ! {str(verdict['problem']).split('; ')[0]}")
    est = verdict.get("estimate")
    if est:
        lines.append(
            f"    teleop estimate: ~{est['hz']} Hz, leader -> follower latency ~{est['latency_ms']} ms"
            + (f" ({verdict['estimate_of']})" if verdict.get("estimate_of") else "")
            + (f"  ! {est['warning']}" if est.get("warning") else "")
        )
    elif verdict.get("not_measured"):
        lines.append(f"    teleop estimate: not measured ({verdict['not_measured']})")
    return lines


def _text(v: Any) -> str:
    """A report value in plain words, never a Python literal (QD-11, QD-16): None is "-", a bool
    "yes" / "no", a list "a, b" ("none" when empty), a dict "key value, key value"."""
    if v is None:
        return "-"
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, (list, tuple, set, frozenset)):
        items = sorted(v, key=str) if isinstance(v, (set, frozenset)) else v
        return ", ".join(_text(x) for x in items) or "none"
    if isinstance(v, dict):
        return ", ".join(f"{k} {_text(x)}" for k, x in v.items()) or "none"
    return str(v)


def _ranges(ids: list[int]) -> str:
    """``[1, 2, 3, 5]`` -> ``"1-3, 5"``."""
    out: list[str] = []
    for i in sorted(ids):
        if out and out[-1].split("-")[-1] == str(i - 1):
            out[-1] = f"{out[-1].split('-')[0]}-{i}"
        else:
            out.append(str(i))
    return ", ".join(out)


def _scan_text(scan: Any) -> str:
    """``{"1": 777, ..., "6": 777}`` -> ``"1-6 (model 777)"``; a scan error stays a sentence."""
    if not isinstance(scan, dict):
        return "not scanned" if scan is None else f"scan failed ({scan})"
    if not scan:
        return "none"
    by_model: dict[str, list[int]] = {}
    for mid, model in scan.items():
        by_model.setdefault(_text(model), []).append(int(mid))
    return "; ".join(f"{_ranges(ids)} (model {model})" for model, ids in by_model.items())


def _compare_text(cmp: dict[str, Any]) -> str:
    """``{"shoulder_pan": "match", ...}`` -> ``"all 6 match"`` or ``"5 of 6 match; gripper: ..."``."""
    other = [f"{name}: {_text(v)}" for name, v in cmp.items() if v != "match"]
    if not other:
        return f"all {len(cmp)} match"
    return f"{len(cmp) - len(other)} of {len(cmp)} match; " + "; ".join(other)


def _status_text(status: Any) -> str:
    """Decoded status bits: ``[]`` is "ok", else the names of the bits that are set."""
    if status is None:
        return "-"
    if isinstance(status, (list, tuple)):
        return ", ".join(str(x) for x in status) or "ok"
    return _text(status)


def _stream_text(p: Any) -> str:
    """A camera's default stream as ``640x480 30 fps MJPG``."""
    if not isinstance(p, dict):
        return _text(p)
    fps = p.get("fps")
    fps_s = f"{fps:g}" if isinstance(fps, (int, float)) and not isinstance(fps, bool) else _text(fps)
    out = f"{_text(p.get('width'))}x{_text(p.get('height'))} {fps_s} fps"
    return out + (f" {str(p['fourcc']).strip()}" if str(p.get("fourcc") or "").strip() else "")


def _bus_errors_text(be: dict[str, Any]) -> str:
    """``bus.error_summary()`` as one sentence; the last error is the bus library's own words."""
    calls = ", ".join(f"{k} x{n}" for k, n in (be.get("by_call") or {}).items())
    out = f"{be.get('errors') or 0}, {be.get('retried_ok') or 0} retried ok"
    out += f" ({calls})" if calls else ""
    return out + (f"; last error: {be['last_error']}" if be.get("last_error") else "")


def _log_line(n: int) -> str:
    if n == 0:
        return "No Station log found (logs/station.log)."
    if n == 1:
        return "The last log line is in the zip."
    return f"The last {n} log lines are in the zip."


def _fmt(d: dict[str, Any], key: str, unit: str) -> str:
    if d.get(key) is None:
        return "-"
    return f"{d[key]} {unit}" + (
        "" if d.get(f"{key}_plausible", True) else " (IMPLAUSIBLE: shown as unknown)"
    )


def _raw_lines(dump: dict[str, Any] | None) -> list[str]:
    """The raw register dump, one line of bytes and one of decoded values per servo id."""
    if not dump:
        return []
    out = [f"    raw register dump (READ per block, {dump.get('baud')} baud, hex bytes):"]
    if dump.get("error"):
        out.append(f"      ! {dump['error']}")
    for mid, row in (dump.get("motors") or {}).items():
        blocks = "  ".join(
            f"[{rng}] {b.get('data') if b.get('answer') else 'no answer'}"
            + (f" err 0x{b['error_byte']:02x}" if b.get("error_byte") else "")
            for rng, b in row.get("blocks", {}).items()
        )
        out.append(f"      id {mid}: {blocks}")
        d = row.get("decoded")
        if d:
            g = {k: _text(v) for k, v in d.items()}  # "-" for a block that did not answer
            out.append(
                f"        -> fw {g.get('firmware')} model {g.get('model_number')} "
                f"temperature raw {g.get('temperature_raw')} = {_fmt(d, 'temp_c', 'C')} "
                f"(max limit {g.get('max_temperature_limit_c')} C) "
                f"voltage raw {g.get('voltage_raw')} = {_fmt(d, 'voltage_v', 'V')} "
                f"current raw {g.get('current_raw')} = {_fmt(d, 'current_a', 'A')} "
                f"load raw {g.get('load_raw')} = {_fmt(d, 'load_pct', '%')} "
                f"status raw {g.get('status_raw')} {_status_text(d.get('status'))}"
            )
    return out


def zip_target(out_dir: Path) -> Path:
    return out_dir / f"hibiscus-station-doctor-{time.strftime('%Y%m%d-%H%M%S')}.zip"


def _secrets(paths: StationPaths) -> list[str]:
    """The local login token as stored on disk: removed literally from every file in the zip, on top
    of :func:`redact` (which only finds it after ``t=`` / ``Bearer``)."""
    try:
        token = paths.token.read_text(encoding="utf-8").strip()
    except OSError:
        return []
    return [token] if len(token) >= 8 else []


def write_zip(report: dict[str, Any], paths: StationPaths, out_dir: Path, target: Path | None = None) -> Path:
    """The zip to send. The token file and ``server.json`` are never added; every text goes
    through :func:`redact` and loses the literal local token."""
    out_dir.mkdir(parents=True, exist_ok=True)
    target = target or zip_target(out_dir)
    secrets = _secrets(paths)

    def clean(text: str) -> str:
        text = redact(text)
        for secret in secrets:
            text = text.replace(secret, "[local token removed]")
        return text

    def read(f: Path) -> str:
        return clean(f.read_text(encoding="utf-8", errors="replace"))

    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("report.txt", clean(summary(report, target)))
        z.writestr("report.json", clean(json.dumps(report, indent=2, default=str)))
        z.writestr("station.log.tail", clean("\n".join(report["log_tail"])))
        for name in ("robots.yaml", "settings.yaml"):
            f = paths.home / name
            if f.is_file():
                z.writestr(name, read(f))
        for c in report["calibrations"]:
            p = Path(c["path"])
            if p.is_file() and p.stat().st_size < 64 * 1024:
                z.writestr(f"calibration/{c['arm']}/{c['dir']}/{p.name}", read(p))
        metas = sorted(paths.sessions.glob("*/session.json"), key=lambda f: f.stat().st_mtime)
        for f in metas[-5:] if paths.sessions.is_dir() else []:
            z.writestr(f"sessions/{f.parent.name}.json", read(f))
    return target


def run(
    home: Path,
    out_dir: Path,
    *,
    ping: bool = True,
    probe_cameras: bool = True,
    echo: Callable[[str], None] = print,
) -> tuple[str, Path]:
    paths = StationPaths(home)
    report = collect(paths, calibration_root(), ping=ping, probe_cameras=probe_cameras, echo=echo)
    target = write_zip(report, paths, out_dir, zip_target(out_dir))
    text = summary(report, target)
    for secret in _secrets(paths):
        text = text.replace(secret, "[local token removed]")
    return text, target
