"""The few places where Windows needs something POSIX does not (Station runs on Linux, macOS and
Windows 10/11 from the wheel; Docker images are Linux only).

Everything here is a no-op on POSIX unless stated.
"""

from __future__ import annotations

import io
import mimetypes
import os
import string
import sys
import time
from pathlib import Path

WINDOWS = sys.platform == "win32"

#: Extensions the UI bundle serves. Windows maps them from the registry, where ``.js`` is often
#: ``text/plain``: browsers then refuse the module scripts and the page stays blank.
WEB_TYPES = {
    ".js": "text/javascript",
    ".mjs": "text/javascript",
    ".css": "text/css",
    ".json": "application/json",
    ".map": "application/json",
    ".svg": "image/svg+xml",
    ".wasm": "application/wasm",
    ".woff2": "font/woff2",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".html": "text/html",
}


def register_web_mimetypes() -> None:
    """Pin the MIME types of the UI files, whatever the OS registry says (all platforms)."""
    for ext, mime in WEB_TYPES.items():
        mimetypes.add_type(mime, ext)


def utf8_console() -> None:
    """Make stdout/stderr UTF-8 on Windows when they are pipes or files (cp1252 otherwise, where a
    Vietnamese log line or ``…`` would raise). A real console already writes UTF-16 and is kept."""
    if not WINDOWS:
        return
    for stream in (sys.stdout, sys.stderr):
        if not isinstance(stream, io.TextIOWrapper):
            continue
        if (stream.encoding or "").lower().replace("-", "") in ("utf8", "utf8sig"):
            continue
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):  # pragma: no cover - detached / closed stream
            pass


def high_resolution_timer() -> None:
    """Windows: 1 ms system timer for this process (``timeBeginPeriod``). The control loop waits on
    a queue with a timeout; at the default 15.6 ms resolution a 30 Hz tick would jitter by half a
    tick. Python's ``time.sleep`` is already precise; lock and queue waits are not."""
    if sys.platform == "win32":
        import ctypes

        try:
            ctypes.WinDLL("winmm").timeBeginPeriod(1)
        except OSError:  # pragma: no cover - no winmm (Server Core)
            pass


def replace_file(src: str | os.PathLike[str], dst: str | os.PathLike[str], attempts: int = 20) -> None:
    """``os.replace`` that survives Windows sharing violations: while another thread or a virus
    scanner has ``dst`` open, Windows refuses the rename with ``PermissionError``. Retries for
    about one second there; on POSIX it is a single ``os.replace``."""
    if not WINDOWS:
        os.replace(src, dst)
        return
    for i in range(attempts):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if i == attempts - 1:
                raise
            time.sleep(0.05)


def import_roots() -> list[Path]:
    """Where a model may be imported from by path (besides uploads): the home directory and the
    removable / data mounts (``/media``, ``/mnt``; on Windows the other drive letters)."""
    roots = [Path.home()]
    if WINDOWS:
        system = os.environ.get("SystemDrive", "C:").rstrip("\\").upper()
        for letter in string.ascii_uppercase[2:]:  # A: and B: are floppy drives
            drive = f"{letter}:"
            if drive != system and Path(f"{drive}\\").exists():
                roots.append(Path(f"{drive}\\"))
    else:
        roots += [Path("/media"), Path("/mnt")]
    return roots
