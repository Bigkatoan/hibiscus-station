"""A serial device that went away while connected (field report 0.2.5: "Access is denied" on COM8).

On Windows the USB-serial driver answers every ``ReadFile`` / ``WriteFile`` / ``ClearCommError``
on a handle whose device was unplugged, reset by the hub, browned out (a current spike when the
follower's torque comes on or it jumps to a far pose) or put to sleep by USB selective suspend
with ``ERROR_ACCESS_DENIED`` (5), ``ERROR_BAD_COMMAND`` (22), ``ERROR_GEN_FAILURE`` (31),
``ERROR_DEVICE_NOT_CONNECTED`` (1167) and friends. Linux says ``EIO`` / ``ENODEV`` / ``ENXIO``.
None of these heal by retrying the same handle: :func:`is_device_lost` tells them apart from a
lost or corrupted packet (a timeout, a bad checksum), :class:`StationMotorsBus` stops retrying at
the first one, and the owner offers to reconnect once the port is back (:func:`find_port`), maybe
under a new COM number.

rustypot reports OS errors as plain ``RuntimeError`` / ``OSError`` text (``"I/O error"``,
``"Access is denied."``), pyserial as ``SerialException("ClearCommError failed
(PermissionError(13, 'Access is denied.', None, 5))")``: both the exception types and the messages
are checked, along the whole ``__cause__`` / ``__context__`` chain.
"""

from __future__ import annotations

import errno
import re
from collections.abc import Callable
from typing import Any

#: errno values of a device that is gone (Linux / macOS).
LOST_ERRNOS = frozenset({errno.EIO, errno.ENODEV, errno.ENXIO, errno.EBADF, errno.EPIPE})
#: Windows system error codes of a USB-serial device that is gone or was reset.
LOST_WINERRORS = frozenset({5, 6, 21, 22, 31, 433, 995, 1167})

_LOST_TEXT = re.compile(
    "|".join(
        (
            r"access is denied",
            r"clearcommerror",
            r"device (is )?not ready",
            r"the device does not recognize the command",
            r"a device attached to the system is not functioning",
            r"a device which does not exist was specified",
            r"the device is not connected",
            r"device (was )?disconnected",
            r"device reports readiness to read but returned no data",
            r"the handle is invalid",
            r"input/output error",
            r"\bi/o error\b",
            r"no such device",
            r"device not configured",
            r"bad file (descriptor|number)",
            r"broken pipe",
        )
    ),
    re.IGNORECASE,
)


class DeviceLostError(ConnectionError):
    """The serial device of ``arm`` on ``port`` is gone: no retry can help (reconnect instead)."""

    def __init__(self, arm: str, port: str, cause: str) -> None:
        super().__init__(f"{arm or 'arm'}: the serial device {port} was lost ({cause})")
        self.arm = arm
        self.port = port
        self.cause = cause


def _chain(exc: BaseException) -> list[BaseException]:
    out: list[BaseException] = []
    cur: BaseException | None = exc
    while cur is not None and cur not in out and len(out) < 8:
        out.append(cur)
        cur = cur.__cause__ or cur.__context__
    return out


def is_device_lost(exc: BaseException) -> bool:
    """Does ``exc`` (or its cause) say the serial device itself is gone, not just one packet?"""
    for e in _chain(exc):
        if isinstance(e, DeviceLostError | PermissionError):
            return True
        if isinstance(e, OSError):
            if getattr(e, "winerror", None) in LOST_WINERRORS:
                return True
            if e.errno in LOST_ERRNOS:
                return True
        # pyserial nests the OSError repr inside its message: "(PermissionError(13, ...))"
        if _LOST_TEXT.search(str(e)) or "PermissionError" in str(e):
            return True
    return False


# ------------------------------------------------------------------------------- finding it again
def port_identity(port: str, rows: list[dict[str, Any]] | None = None) -> dict[str, Any] | None:
    """What identifies ``port``'s USB adapter (``list_ports`` row: stable path, VID:PID, serial
    number), to find it again after a re-plug. ``None`` for ``mock://`` ports and unknown ones."""
    if port.startswith("mock://"):
        return None
    from hibiscus_station.hw.locks import normalize_device

    if rows is None:
        from hibiscus_station.hw.ports import list_ports

        try:
            rows = list_ports(usb_only=False)
        except Exception:
            return None
    want = normalize_device(port)
    for r in rows:
        if normalize_device(str(r["device"])) == want or (r.get("stable_path") and r["stable_path"] == port):
            return {
                "device": r["device"],
                "stable_path": r.get("stable_path"),
                "vid_pid": r.get("vid_pid"),
                "serial_number": r.get("serial_number"),
                "description": r.get("description") or "",
            }
    return None


def find_port(
    port: str,
    identity: dict[str, Any] | None,
    rows: list[dict[str, Any]],
    exclude: set[str] | None = None,
) -> str | None:
    """The device name of the lost adapter in ``rows`` (a fresh ``list_ports``), or ``None``.

    In order: the same serial number (+ VID:PID); the same ``/dev/serial/by-id`` path; then, among
    the ports that are not another arm's (``exclude``), the old name if it is listed again, or the
    only adapter with the same VID:PID. Two identical adapters without serial numbers stay
    ambiguous: ``None``.
    """
    from hibiscus_station.hw.locks import normalize_device

    excl = {normalize_device(p) for p in (exclude or set())}
    free = [r for r in rows if normalize_device(str(r["device"])) not in excl]
    ident = identity or {}
    sn, vp = ident.get("serial_number"), ident.get("vid_pid")
    if sn:
        for r in rows:
            if r.get("serial_number") == sn and (not vp or r.get("vid_pid") == vp):
                return str(r["device"])
    stable = ident.get("stable_path") or (port if port.startswith("/dev/serial/by-id/") else None)
    if stable:
        for r in rows:
            if r.get("stable_path") == stable:
                return str(r["device"])
    for r in free:
        if normalize_device(str(r["device"])) == normalize_device(port) and (
            not vp or not r.get("vid_pid") or r.get("vid_pid") == vp
        ):
            return str(r["device"])
    if vp and not sn:
        same = [r for r in free if r.get("vid_pid") == vp]
        if len(same) == 1:
            return str(same[0]["device"])
    return None


def wait_for_ports(
    wanted: dict[str, tuple[str, dict[str, Any] | None]],
    lister: Callable[[], list[dict[str, Any]]],
    timeout_s: float,
    poll_s: float = 0.5,
    sleep: Callable[[float], None] | None = None,
    clock: Callable[[], float] | None = None,
) -> dict[str, str] | None:
    """Poll until every arm's adapter (``{arm: (old port, identity)}``) is listed again; returns
    ``{arm: device name now}`` or ``None`` after ``timeout_s``."""
    import time

    sleep = sleep or time.sleep
    clock = clock or time.monotonic
    deadline = clock() + timeout_s
    while True:
        rows = lister()
        found: dict[str, str] = {}
        for arm, (port, ident) in wanted.items():
            others = set(found.values()) | {p for a, (p, _i) in wanted.items() if a != arm}
            dev = find_port(port, ident, rows, exclude=others - {port})
            if dev is None:
                break
            found[arm] = dev
        else:
            return found
        if clock() >= deadline:
            return None
        sleep(poll_s)
