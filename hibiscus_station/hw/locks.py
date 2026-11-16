"""OS-level device locks (spec §4.3): one lock file per serial port / camera device.

POSIX takes ``flock`` on the whole file. Windows takes ``msvcrt.locking`` on one byte far past the
end of the file: Windows byte-range locks are mandatory, so the locked byte must not cover the
``pid\\ndevice\\n`` header that a second process reads to report who holds the device. Both locks
belong to the open file and go away when the process exits or dies.
"""

from __future__ import annotations

import hashlib
import os
import re
import sys
from pathlib import Path

if sys.platform == "win32":
    import msvcrt
else:
    import fcntl

#: Byte locked on Windows (1 GiB): past any header; Windows allows locking beyond the end of file.
WIN_LOCK_OFFSET = 1 << 30
_O_BINARY: int = getattr(os, "O_BINARY", 0)  # Windows os.open defaults to text mode
_WIN_DEVICE = re.compile(r"^(?:\\\\[.?]\\)?((?:COM|LPT)[0-9]+)$", re.IGNORECASE)


class DeviceBusyError(Exception):
    def __init__(self, device: str, holder: int | None) -> None:
        super().__init__(f"{device} is locked by pid {holder}")
        self.device = device
        self.holder = holder


def normalize_device(device: str) -> str:
    """One spelling per device, so two names of the same port share one lock.

    ``/dev`` symlinks are resolved (``/dev/serial/by-id/...`` -> ``/dev/ttyACM0``); Windows port
    names are upper-cased without the ``\\\\.\\`` prefix (``com3``, ``\\\\.\\COM10`` -> ``COM3``,
    ``COM10``). Anything else (camera indices, ``realsense:...``) is kept as given.
    """
    if m := _WIN_DEVICE.match(device.strip()):
        return m.group(1).upper()
    if device.startswith("/"):
        try:
            return os.path.realpath(device)
        except OSError:  # pragma: no cover
            return device
    return device


def lock_key(device: str) -> str:
    return hashlib.sha1(normalize_device(device).encode(), usedforsecurity=False).hexdigest()


def _try_lock(fd: int) -> bool:
    """Non-blocking exclusive lock; False when another open file holds it."""
    if sys.platform == "win32":
        os.lseek(fd, WIN_LOCK_OFFSET, os.SEEK_SET)
        try:
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        except OSError:  # EACCES / EDEADLOCK: another handle holds the byte
            return False
        return True
    else:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return False
        return True


def _unlock(fd: int) -> None:
    if sys.platform == "win32":
        os.lseek(fd, WIN_LOCK_OFFSET, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    else:
        fcntl.flock(fd, fcntl.LOCK_UN)


def _read_head(fd: int) -> bytes:
    """The holder's ``pid\\ndevice\\n`` (seek + read: there is no ``os.pread`` on Windows)."""
    os.lseek(fd, 0, os.SEEK_SET)
    return os.read(fd, 64)


def _write_head(fd: int, data: bytes) -> None:
    os.ftruncate(fd, 0)
    os.lseek(fd, 0, os.SEEK_SET)
    os.write(fd, data)


class DeviceLock:
    def __init__(self, locks_dir: Path, device: str) -> None:
        self.device = device
        self.path = locks_dir / f"{lock_key(device)}.lock"
        self._fd: int | None = None

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.path, os.O_RDWR | os.O_CREAT | _O_BINARY, 0o600)
        if not _try_lock(fd):
            holder: int | None = None
            try:
                holder = int((_read_head(fd).decode().split() or ["0"])[0]) or None
            except (OSError, ValueError):
                holder = None
            os.close(fd)
            raise DeviceBusyError(self.device, holder) from None
        try:
            _write_head(fd, f"{os.getpid()}\n{self.device}\n".encode())
        except BaseException:
            try:
                _unlock(fd)
            finally:
                os.close(fd)
            raise
        self._fd = fd

    def release(self) -> None:
        if self._fd is not None:
            try:
                _unlock(self._fd)
            finally:
                os.close(self._fd)
                self._fd = None

    @property
    def held(self) -> bool:
        return self._fd is not None

    def __enter__(self) -> DeviceLock:
        self.acquire()
        return self

    def __exit__(self, *exc: object) -> None:
        self.release()


class InstanceLock(DeviceLock):
    """Single Station instance per home (``station.lock`` + ``station.pid``)."""

    def __init__(self, lock_path: Path, pid_path: Path) -> None:
        super().__init__(lock_path.parent, "station")
        self.path = lock_path
        self.pid_path = pid_path

    def acquire(self) -> None:
        super().acquire()
        self.pid_path.write_text(f"{os.getpid()}\n", encoding="utf-8")

    def release(self) -> None:
        super().release()
        self.pid_path.unlink(missing_ok=True)
