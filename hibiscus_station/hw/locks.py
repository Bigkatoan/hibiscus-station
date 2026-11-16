"""OS-level device locks (spec §4.3): one ``flock`` file per serial port / camera device."""

from __future__ import annotations

import fcntl
import hashlib
import os
from pathlib import Path


class DeviceBusyError(Exception):
    def __init__(self, device: str, holder: int | None) -> None:
        super().__init__(f"{device} is locked by pid {holder}")
        self.device = device
        self.holder = holder


def lock_key(device: str) -> str:
    try:
        real = os.path.realpath(device) if device.startswith("/") else device
    except OSError:  # pragma: no cover
        real = device
    return hashlib.sha1(real.encode(), usedforsecurity=False).hexdigest()


class DeviceLock:
    def __init__(self, locks_dir: Path, device: str) -> None:
        self.device = device
        self.path = locks_dir / f"{lock_key(device)}.lock"
        self._fd: int | None = None

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            holder: int | None = None
            try:
                holder = int((os.pread(fd, 64, 0).decode().split() or ["0"])[0]) or None
            except (OSError, ValueError):
                holder = None
            os.close(fd)
            raise DeviceBusyError(self.device, holder) from None
        os.ftruncate(fd, 0)
        os.pwrite(fd, f"{os.getpid()}\n{self.device}\n".encode(), 0)
        self._fd = fd

    def release(self) -> None:
        if self._fd is not None:
            try:
                fcntl.flock(self._fd, fcntl.LOCK_UN)
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
        self.pid_path.write_text(f"{os.getpid()}\n")

    def release(self) -> None:
        super().release()
        self.pid_path.unlink(missing_ok=True)
