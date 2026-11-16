"""``hibiscus-station doctor``: one report a user can send when the arm does not work.

Collects versions, serial ports (VID:PID, stable path, who holds them), cameras, calibration files,
robot profiles and the calibration each one expects, the running Station's status, the last log
lines, and (when the port is free) a read-only ping of every motor on each configured arm: model,
firmware, voltage, temperature, status, EEPROM calibration compared with the file. Nothing is
written to a motor and no torque is switched on.

The report is printed and saved with copies of the files into ``hibiscus-station-doctor-<ts>.zip``.
Login tokens and Hibiscus PATs never go in: the token file and ``server.json`` are skipped and every
text goes through :func:`hibiscus_station.logs.redact`.
"""

from __future__ import annotations

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
    "Status",
    "Torque_Enable",
    "Lock",
    "Return_Delay_Time",
    "Operating_Mode",
)


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
) -> dict[str, Any]:
    """Read-only check of an SO-101 arm on ``port``: which ids answer, and their registers."""
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
            model = bus.ping(name, num_retry=2)
            row["model_number"] = model
            if model is None:
                row["error"] = "no answer"
                out["motors"][str(m.id)] = row
                continue
            for reg in PING_REGISTERS:
                try:
                    row[reg] = bus.read(reg, name, normalize=False, num_retry=1)
                except Exception as exc:
                    row[reg] = f"error: {exc}"
            out["motors"][str(m.id)] = row
        t = time.perf_counter()
        n = 20
        fails = 0
        for _ in range(n):
            try:
                bus.sync_read("Present_Position", normalize=False, num_retry=0)
            except Exception:
                fails += 1
        out["sync_read_present_position"] = {
            "reads": n,
            "failed": fails,
            "ms_per_read": round((time.perf_counter() - t) * 1000 / n, 2),
        }
        if calibration:
            out["calibration_vs_eeprom"] = _compare(calibration, out["motors"])
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
    out["seconds"] = round(time.perf_counter() - t0, 2)
    return out


def _compare(cal: dict[str, Any], motors: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for name, v in cal.items():
        row = motors.get(str(v.get("id")), {})
        diffs = []
        for key, reg in (
            ("homing_offset", "Homing_Offset"),
            ("range_min", "Min_Position_Limit"),
            ("range_max", "Max_Position_Limit"),
        ):
            if row.get(reg) != v.get(key):
                diffs.append(f"{key}: file {v.get(key)} motor {row.get(reg)}")
        out[name] = "match" if not diffs else "; ".join(diffs)
    return out


# ------------------------------------------------------------------------------------- the report
def running_status(paths: StationPaths) -> dict[str, Any] | None:
    """``GET /api/v1/status`` of the running Station (None when none runs)."""
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
        cal_by_path = {c["path"]: c.get("motors") for c in report["calibrations"]}
        seen: set[str] = set()
        for robot in report["profiles"].get("robots", []):
            for arm, a in robot["arms"].items():
                port = str(a["port"])
                if port.startswith("mock://") or port in seen:
                    continue
                seen.add(port)
                row: dict[str, Any] = {"robot": robot["id"], "arm": arm, "port": port}
                holder = station_lock_holder(paths, port)
                others = port_holders(port)
                if holder is not None:
                    row["skipped"] = f"in use by Station (pid {holder}); stop it to ping the motors"
                elif others:
                    row["skipped"] = "in use by " + "; ".join(others)
                elif not Path(port).exists() and os.name != "nt":
                    row["skipped"] = "port not found (unplugged? another name now?)"
                else:
                    echo(f"pinging {arm} on {port}...")
                    same_arm = {c["path"]: c.get("motors") for c in report["calibrations"] if c["arm"] == arm}
                    row.update(ping_arm(port, cal_by_path.get(a["expects"]), same_arm))
                arms.append(row)
    report["arms"] = arms
    report["warnings"] = warnings(report)
    report["log_tail"] = log_tail(paths)
    return report


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
                found = [c["id"] for c in report["calibrations"] if c["arm"] == arm]
                out.append(
                    f"{r['id']} {arm}: no calibration '{a['calibration_id']}'"
                    + (f" (files found: {', '.join(found)} - Calibrate > Use this file)" if found else "")
                )
    for a in report.get("arms", []):
        if a.get("error"):
            out.append(f"{a['robot']} {a['arm']} on {a['port']}: {a['error']}")
        missing = [k for k, m in a.get("motors", {}).items() if m.get("error")]
        if missing:
            out.append(
                f"{a['robot']} {a['arm']}: motor id(s) {', '.join(missing)} do not answer (power? cable?)"
            )
    for p in report["ports"]:
        if p.get("open_by"):
            out.append(f"{p['device']} is open by another program: {'; '.join(p['open_by'])}")
    return out


def summary(report: dict[str, Any]) -> str:
    """Human-readable lines (what the terminal shows)."""
    v = report["versions"]
    lines = [
        f"Hibiscus Station {v['hibiscus_station']} · Python {v['python']} · lerobot {v['lerobot']} · "
        f"rustypot {v['rustypot']}",
        f"OS: {v['os']} ({v['machine']})",
        f"Data: {report['home']}",
        f"Calibration folder: {report['calibration_root']}",
        "",
    ]
    if report.get("warnings"):
        lines += ["LIKELY PROBLEMS:", *[f"  ! {w}" for w in report["warnings"]], ""]
    lines += ["Serial ports:"]
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
        lines.append(f"  {c['arm']:<8} {c['id']:<24} {c['dir']:<15} {c['modified_at'][:19]}  {c['path']}")
        if c.get("error"):
            lines.append(f"     ! {c['error']}")
    lines += ["", "Robot profiles:"]
    prof = report["profiles"]
    if prof.get("error"):
        lines.append(f"  ! {prof['error']}")
    for r in prof.get("robots", []):
        lines.append(
            f"  {r['id']}{' (active)' if r['id'] == prof.get('active') else ''}: cameras {r['cameras']}"
        )
        for arm, a in r["arms"].items():
            ok = "found" if a["file_exists"] else "MISSING"
            lines.append(f"    {arm}: {a['type']} on {a['port']}, calibration '{a['calibration_id']}' {ok}")
    run = report.get("running")
    lines += ["", "Running Station:"]
    if not run:
        lines.append("  not running")
    elif run.get("error"):
        lines.append(f"  pid {run.get('pid')}: {run['error']}")
    else:
        st = run["status"]
        robot = st.get("robot") or {}
        lines.append(
            f"  pid {run.get('pid')}: mode {'MOCK' if (st.get('station') or {}).get('mock') else 'real'}, "
            f"state {st.get('state')} reason {st.get('reason')} detail {st.get('detail')}"
        )
        if robot:
            lines.append(
                f"  connected profile {robot.get('id')}"
                + (" [DEMO: simulated arms]" if robot.get("mock") else " (real arms)")
            )
        for arm, a in (robot.get("arms") or {}).items():
            if a:
                lines.append(
                    f"    {arm}: calibrated {a.get('calibrated')} issue {a.get('issue')} "
                    f"bus errors {a.get('bus_errors')} last {a.get('last_bus_error')}"
                )
        for al in st.get("alerts", []):
            lines.append(f"    alert {al.get('level')} {al.get('message_key')} {al.get('params')}")
    cams = report.get("cameras")
    if cams is not None:
        lines += ["", "Cameras:"]
        if isinstance(cams, str):
            lines.append(f"  ! {cams}")
        else:
            lines += [
                f"  {c.get('id')}  {c.get('backend_api')}  {c.get('default_stream_profile')}" for c in cams
            ] or ["  (none)"]
    lines += ["", "Motor check (read only):"]
    if not report["arms"]:
        lines.append("  no real arm in the profiles (or --no-ping)")
    for a in report["arms"]:
        head = f"  {a['robot']} {a['arm']} on {a['port']}"
        if a.get("skipped"):
            lines.append(f"{head}: skipped, {a['skipped']}")
            continue
        if a.get("error"):
            lines.append(f"{head}: {a['error']}")
            continue
        lines.append(f"{head}: ids answering at 1 Mbps {a.get('scan_1mbps')}")
        for mid, m in a.get("motors", {}).items():
            if m.get("error"):
                lines.append(f"    id {mid}: {m['error']}")
                continue
            lines.append(
                f"    id {mid}: model {m.get('model_number')} fw {m.get('Firmware_Major_Version')}."
                f"{m.get('Firmware_Minor_Version')} pos {m.get('Present_Position')} "
                f"{m.get('Present_Voltage')}x0.1V "
                f"(min {m.get('Min_Voltage_Limit')} max {m.get('Max_Voltage_Limit')}) "
                f"{m.get('Present_Temperature')}C (max {m.get('Max_Temperature_Limit')}) "
                f"status {m.get('Status')} "
                f"torque {m.get('Torque_Enable')} lock {m.get('Lock')} offset {m.get('Homing_Offset')} "
                f"limits {m.get('Min_Position_Limit')}-{m.get('Max_Position_Limit')}"
            )
        if a.get("sync_read_present_position"):
            s = a["sync_read_present_position"]
            lines.append(f"    sync read: {s['failed']}/{s['reads']} failed, {s['ms_per_read']} ms each")
        if a.get("calibration_vs_eeprom"):
            lines.append(f"    calibration file vs motors: {a['calibration_vs_eeprom']}")
        if "eeprom_matches" in a:
            lines.append(f"    motors carry the calibration of: {a['eeprom_matches'] or 'no file found'}")
        be = a.get("bus_errors") or {}
        if be.get("errors"):
            lines.append(f"    bus errors: {be}")
    lines += ["", f"Last {len(report['log_tail'])} log lines are in the zip."]
    return redact("\n".join(lines))


def write_zip(report: dict[str, Any], paths: StationPaths, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d-%H%M%S")
    target = out_dir / f"hibiscus-station-doctor-{ts}.zip"
    text = summary(report)
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("report.txt", text)
        z.writestr("report.json", redact(json.dumps(report, indent=2, default=str)))
        z.writestr("station.log.tail", "\n".join(report["log_tail"]))
        for name in ("robots.yaml", "settings.yaml"):
            f = paths.home / name
            if f.is_file():
                z.writestr(name, redact(f.read_text(encoding="utf-8", errors="replace")))
        for c in report["calibrations"]:
            p = Path(c["path"])
            if p.is_file() and p.stat().st_size < 64 * 1024:
                z.writestr(
                    f"calibration/{c['arm']}/{c['dir']}/{p.name}",
                    p.read_text(encoding="utf-8", errors="replace"),
                )
        metas = sorted(paths.sessions.glob("*/session.json"), key=lambda f: f.stat().st_mtime)
        for f in metas[-5:] if paths.sessions.is_dir() else []:
            z.writestr(
                f"sessions/{f.parent.name}.json", redact(f.read_text(encoding="utf-8", errors="replace"))
            )
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
    target = write_zip(report, paths, out_dir)
    return summary(report), target
