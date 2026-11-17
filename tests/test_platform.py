"""Cross-platform pieces (Linux, macOS, Windows 10/11): device locks, port names, camera scan, the
Windows workarounds in ``oscompat``. Every test here runs on every OS in CI unless marked."""

from __future__ import annotations

import mimetypes
import os
import subprocess
import sys
import textwrap
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from hibiscus_station import oscompat
from hibiscus_station.hw import cameras, ports
from hibiscus_station.hw.locks import DeviceBusyError, DeviceLock, InstanceLock, lock_key, normalize_device

windows_only = pytest.mark.skipif(sys.platform != "win32", reason="Windows byte-range lock semantics")
posix_only = pytest.mark.skipif(sys.platform == "win32", reason="/dev paths and symlinks")


# --------------------------------------------------------------------------- lock keys
@pytest.mark.parametrize("name", ["COM3", "com3", "Com3", "\\\\.\\COM3", "\\\\?\\com3", " COM3 "])
def test_windows_port_names_share_one_lock(name: str) -> None:
    assert normalize_device(name) == "COM3"
    assert lock_key(name) == lock_key("COM3")


def test_windows_port_numbers_are_distinct() -> None:
    assert normalize_device("\\\\.\\COM10") == "COM10"
    assert lock_key("COM1") != lock_key("COM10")
    assert normalize_device("0") == "0"  # camera index kept
    assert normalize_device("realsense:123") == "realsense:123"


@posix_only
def test_dev_symlinks_resolve_to_one_lock(tmp_path: Path) -> None:
    real = tmp_path / "ttyACM0"
    real.touch()
    link = tmp_path / "usb-Feetech-if00"
    link.symlink_to(real)
    assert lock_key(str(link)) == lock_key(str(real))


# --------------------------------------------------------------------------- device locks
def test_lock_is_exclusive_in_process_and_reports_holder(tmp_path: Path) -> None:
    a = DeviceLock(tmp_path, "COM3")
    a.acquire()
    assert a.held
    with pytest.raises(DeviceBusyError) as ei:
        DeviceLock(tmp_path, "com3").acquire()
    assert ei.value.holder == os.getpid()
    assert ei.value.device == "com3"
    a.release()
    assert not a.held
    with DeviceLock(tmp_path, "\\\\.\\COM3") as b:
        assert b.held
    a.release()  # idempotent


def test_lock_file_names_the_holder(tmp_path: Path) -> None:
    with DeviceLock(tmp_path, "COM7") as lk:
        head = lk.path.read_bytes()  # a second handle can read it while it is locked (Windows too)
        assert head.split(b"\n")[:2] == [str(os.getpid()).encode(), b"COM7"]
        assert b"\r" not in head  # binary mode on Windows


def test_reacquire_after_release_rewrites_holder(tmp_path: Path) -> None:
    for _ in range(3):
        with DeviceLock(tmp_path, "COM4") as lk:
            assert lk.path.read_text(encoding="utf-8").startswith(f"{os.getpid()}\n")


_HOLDER = textwrap.dedent(
    """
    import os, sys
    from pathlib import Path
    from hibiscus_station.hw.locks import DeviceLock
    lk = DeviceLock(Path(sys.argv[1]), sys.argv[2])
    lk.acquire()
    print("locked", os.getpid(), flush=True)
    sys.stdin.readline()
    if sys.argv[3] == "release":
        lk.release()
        print("released", flush=True)
        sys.stdin.readline()
    """
)


def _holder(tmp_path: Path, device: str, mode: str) -> tuple[subprocess.Popen[str], int]:
    """A second process holding ``device``, and its pid (a venv ``python.exe`` on Windows is a
    launcher: the interpreter is its child, with another pid)."""
    proc = subprocess.Popen(  # noqa: S603 - our own interpreter
        [sys.executable, "-c", _HOLDER, str(tmp_path), device, mode],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
        cwd=Path(__file__).resolve().parents[1],
    )
    assert proc.stdout is not None
    word, pid = proc.stdout.readline().split()
    assert word == "locked"
    return proc, int(pid)


def _acquire_eventually(lock: DeviceLock, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while True:
        try:
            lock.acquire()
            return
        except DeviceBusyError:
            if time.monotonic() > deadline:
                raise
            time.sleep(0.05)


def test_lock_across_processes_reports_the_other_pid(tmp_path: Path) -> None:
    proc, pid = _holder(tmp_path, "COM5", "release")
    try:
        with pytest.raises(DeviceBusyError) as ei:
            DeviceLock(tmp_path, "\\\\.\\com5").acquire()
        assert ei.value.holder == pid != os.getpid()
        assert proc.stdin is not None and proc.stdout is not None
        proc.stdin.write("\n")
        proc.stdin.flush()
        assert proc.stdout.readline().strip() == "released"
        lk = DeviceLock(tmp_path, "COM5")
        lk.acquire()  # released explicitly: free at once
        lk.release()
    finally:
        proc.kill()
        proc.wait(timeout=20)


def test_lock_is_freed_when_the_holder_dies(tmp_path: Path) -> None:
    proc, _pid = _holder(tmp_path, "COM6", "hold")
    with pytest.raises(DeviceBusyError):
        DeviceLock(tmp_path, "COM6").acquire()
    proc.kill()  # TerminateProcess on Windows: no cleanup code runs
    proc.wait(timeout=20)
    lk = DeviceLock(tmp_path, "COM6")
    _acquire_eventually(lk)
    assert lk.path.read_text(encoding="utf-8").startswith(f"{os.getpid()}\n")
    lk.release()


def test_instance_lock_writes_and_removes_pid(tmp_path: Path) -> None:
    lock = InstanceLock(tmp_path / "station.lock", tmp_path / "station.pid")
    lock.acquire()
    assert (tmp_path / "station.pid").read_text(encoding="utf-8").strip() == str(os.getpid())
    with pytest.raises(DeviceBusyError):
        InstanceLock(tmp_path / "station.lock", tmp_path / "station.pid").acquire()
    lock.release()
    assert not (tmp_path / "station.pid").exists()


@windows_only
def test_windows_lock_is_a_byte_past_the_header(tmp_path: Path) -> None:
    import msvcrt

    from hibiscus_station.hw.locks import WIN_LOCK_OFFSET

    with DeviceLock(tmp_path, "COM8") as lk:
        fd = os.open(lk.path, os.O_RDWR | os.O_BINARY)  # type: ignore[attr-defined,unused-ignore]
        try:
            assert os.read(fd, 64).startswith(str(os.getpid()).encode())  # header not locked
            os.lseek(fd, WIN_LOCK_OFFSET, os.SEEK_SET)
            with pytest.raises(OSError):
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)  # type: ignore[attr-defined,unused-ignore]
        finally:
            os.close(fd)


# --------------------------------------------------------------------------- serial ports
def _comports(*devices: str) -> list[SimpleNamespace]:
    return [
        SimpleNamespace(device=d, vid=0x1A86, pid=0x55D3, serial_number=f"SN{i}", description="USB Serial")
        for i, d in enumerate(devices)
    ]


def test_list_ports_windows_names_and_holders(monkeypatch: pytest.MonkeyPatch) -> None:
    from serial.tools import list_ports as lp

    monkeypatch.setattr(lp, "comports", lambda: _comports("COM4", "COM3", "COM12"))
    rows = ports.list_ports({"com3": "follower", "\\\\.\\COM12": "leader"})
    assert [r["device"] for r in rows] == ["COM12", "COM3", "COM4"]
    by = {r["device"]: r for r in rows}
    assert by["COM3"]["in_use_by"] == "follower"
    assert by["COM12"]["in_use_by"] == "leader"
    assert by["COM4"]["in_use_by"] is None
    assert by["COM3"]["vid_pid"] == "1a86:55d3" and by["COM3"]["stable_path"] is None


def test_detect_unplug_with_com_ports() -> None:
    seq = iter([["COM3", "COM4"], ["COM3", "COM4"], ["COM4"]])
    port = ports.detect_unplug(["COM3", "COM4"], lambda: next(seq), timeout_s=5, sleep=lambda _s: None)
    assert port == "COM3"


# --------------------------------------------------------------------------- cameras
def test_camera_index_scan_stops_after_misses_and_skips_held(monkeypatch: pytest.MonkeyPatch) -> None:
    present = {0, 1, 2}
    probed: list[int | str] = []

    def probe(target: int | str) -> dict[str, Any] | None:
        probed.append(target)
        return {"id": target, "name": f"cam {target}"} if target in present else None

    monkeypatch.setattr(cameras, "_probe_index", probe)
    found = cameras.find_opencv_cameras({"1"}, platform="win32")
    assert [c["id"] for c in found] == [0, 2]
    assert 1 not in probed  # the held camera is never opened
    assert probed == [0, 2, 3, 4, 5]  # stops after MAX_MISSES missing indices


def test_camera_scan_linux_uses_dev_video(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(cameras, "_probe_index", lambda t: {"id": t})
    monkeypatch.setattr(cameras, "VIDEO_DIR", tmp_path)
    for n in ("video2", "video0", "media0"):
        (tmp_path / n).touch()
    found = cameras.find_opencv_cameras({str(tmp_path / "video2")}, platform="linux")
    assert [c["id"] for c in found] == [str(tmp_path / "video0")]


# --------------------------------------------------------------------------- oscompat
def test_web_mimetypes_are_pinned(monkeypatch: pytest.MonkeyPatch) -> None:
    mimetypes.add_type("text/plain", ".js")  # what a Windows registry often says
    oscompat.register_web_mimetypes()
    assert mimetypes.guess_type("index-abc.js")[0] == "text/javascript"
    assert mimetypes.guess_type("index.css")[0] == "text/css"
    assert mimetypes.guess_type("favicon.svg")[0] == "image/svg+xml"


def test_replace_file_overwrites(tmp_path: Path) -> None:
    dst = tmp_path / "a.json"
    dst.write_text("old", encoding="utf-8")
    src = tmp_path / ".a.json.tmp"
    src.write_text("new", encoding="utf-8")
    oscompat.replace_file(src, dst)
    assert dst.read_text(encoding="utf-8") == "new" and not src.exists()


def test_import_roots_include_home() -> None:
    roots = oscompat.import_roots()
    assert roots[0] == Path.home()
    if sys.platform == "win32":
        assert all(r.drive for r in roots[1:])
    else:
        assert Path("/media") in roots and Path("/mnt") in roots


def test_utf8_console_and_timer_do_not_fail() -> None:
    oscompat.utf8_console()
    oscompat.high_resolution_timer()


def test_vietnamese_log_line_through_a_pipe(tmp_path: Path) -> None:
    """The CLI's console (pipe -> cp1252 on Windows without the fix) takes Vietnamese text."""
    code = (
        "from hibiscus_station.oscompat import utf8_console; utf8_console(); "
        "import sys; print('Đã kết nối cánh tay … ✓'); sys.stderr.write('lỗi cổng COM3\\n')"
    )
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONUTF8", "PYTHONIOENCODING")}
    out = subprocess.run(  # noqa: S603
        [sys.executable, "-c", code], capture_output=True, env=env, timeout=60, check=True
    )
    assert "Đã kết nối cánh tay … ✓" in out.stdout.decode("utf-8")
    assert "lỗi cổng COM3" in out.stderr.decode("utf-8")


# --------------------------------------------------------------------------- Windows path separators
def test_keyframe_camera_rejects_windows_separators(tmp_path: Path) -> None:
    from hibiscus_station.errors import StationError
    from hibiscus_station.programs.paths import RobotDataPaths

    paths = RobotDataPaths(tmp_path, "desk")
    for bad in ("..\\..\\x", "a\\b", "C:x", "a/b"):
        with pytest.raises(StationError):
            paths.keyframe("t_20260101_000000_abcd", bad, 0)


@pytest.mark.parametrize(
    ("given", "want"),
    [(0, 0), ("0", 0), (" 2 ", 2), ("/dev/video0", Path("/dev/video0"))],
)
def test_camera_index_from_the_ui_opens_as_an_index(given: int | str, want: int | Path) -> None:
    assert cameras.camera_target(given) == want


def test_a_browser_closing_its_socket_is_not_logged_as_an_error(caplog: pytest.LogCaptureFixture) -> None:
    """QD-3: on Windows the Proactor loop logs ``ERROR:asyncio: Exception in callback
    _ProactorBasePipeTransport._call_connection_lost`` with ``ConnectionResetError: [WinError 10054]``
    each time the browser drops a connection (page change, tab closed). The peer is gone, nothing
    is lost: it must not reach the log as an error. Any other loop error still does."""
    import asyncio
    import logging

    loop = asyncio.new_event_loop()
    try:
        oscompat.quiet_peer_resets(loop)
        caplog.set_level(logging.DEBUG, logger="asyncio")
        for exc in (
            ConnectionResetError(10054, "An existing connection was forcibly closed by the remote host"),
            ConnectionAbortedError(10053, "An established connection was aborted"),
        ):
            loop.call_exception_handler(
                {
                    "message": "Exception in callback _ProactorBasePipeTransport._call_connection_lost(None)",
                    "exception": exc,
                }
            )
        assert not [r for r in caplog.records if r.levelno >= logging.WARNING]
        loop.call_exception_handler(
            {"message": "Task exception was never retrieved", "exception": ValueError("x")}
        )
        assert [r for r in caplog.records if r.levelno >= logging.ERROR]
    finally:
        loop.close()
