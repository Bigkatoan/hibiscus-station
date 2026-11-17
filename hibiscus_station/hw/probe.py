"""A read-only Feetech STS probe for ``hibiscus-station doctor``: every answer is validated (QD-25).

The doctor used to read registers through lerobot's bus. A status packet that came later than the
bus timeout (a USB stall, a hub, an adapter with a long latency) then stayed in the receive buffer
and was taken as the answer of the *next* request: every later register of that servo was shifted
by one (``80 C``, ``341.3 V``, ``status overheat, overload``, limits ``44-684``) and the report told
the user to calibrate a correctly calibrated arm again.

Here every exchange is one request and its validated answers:

* the receive buffer is drained before each request; what was in it (a late answer) is counted as
  evidence that its servo answers, never used as a value;
* an answer is accepted only when its checksum is right, it comes from the servo that was asked,
  it is a status packet (not the adapter echoing the request) and it carries exactly the number of
  bytes that were asked for;
* the register blocks of one servo all have different lengths (and differ from a ping's 0 and a
  sync read's 2 bytes), so a late answer to another request of the same servo can never pass as
  this one's: only an answer to an identical request can, and it carries the same registers;
* a request without a validated answer is retried (bounded: :data:`TRIES`); a read that never
  validates is *unreadable*, and the caller reports it as such, never as a value;
* each late answer doubles the timeout (up to :data:`MAX_TIMEOUT_S`), so an adapter that is slow
  but steady is measured as a slow bus instead of losing every answer.

Only PING, READ and SYNC_READ instructions are sent: nothing is written to a servo.

Every frame the probe sees is also kept as per-servo evidence (:class:`Evidence`), so the doctor
can tell a servo that never answered from one that answers now and then (QD-27).
"""

from __future__ import annotations

import logging
import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger(__name__)

PING = 0x01
READ = 0x02
SYNC_READ = 0x82
BROADCAST = 0xFE
BAUD = 1_000_000
#: Time to wait for an answer, as lerobot's bus (50 ms); late answers raise it (see module doc).
TIMEOUT_S = 0.05
MAX_TIMEOUT_S = 0.25
#: Attempts per request (1 + 2 retries) before it counts as unanswered / unreadable.
TRIES = 3
#: The adapter's read timeout: the polling step while waiting for an answer.
POLL_S = 0.002

#: Why a request got no validated answer from a servo, in the report's words.
NO_ANSWER = "no_answer"
CORRUPT = "corrupt"
GARBLED = "garbled"
OUTCOME_WORDS: dict[str, str] = {
    NO_ANSWER: "no answer",
    CORRUPT: "corrupted answer (checksum)",
    GARBLED: "malformed answer (cut short or the wrong length)",
}


def checksum(body: bytes) -> int:
    return (~sum(body)) & 0xFF


def packet(motor_id: int, instr: int, params: bytes = b"") -> bytes:
    """``FF FF id len instr params checksum``."""
    body = bytes([motor_id, len(params) + 2, instr]) + params
    return b"\xff\xff" + body + bytes([checksum(body)])


def read_packet(motor_id: int, addr: int, length: int) -> bytes:
    """A READ instruction (never a write): ``FF FF id 4 0x02 addr length checksum``."""
    return packet(motor_id, READ, bytes([addr, length]))


@dataclass
class Frame:
    """One status packet from the wire: ``ok`` False when its checksum is wrong, ``cut`` True when
    it was cut short (another packet's header came before its end)."""

    id: int
    status: int
    params: bytes
    raw: bytes
    ok: bool = True
    cut: bool = False


def _whole_packet_at(buf: bytearray, i: int) -> bool:
    """A complete packet with a right checksum starts at ``buf[i]``."""
    if i < 0 or len(buf) < i + 6 or buf[i : i + 2] != b"\xff\xff" or buf[i + 2] == 0xFF:
        return False
    total = 4 + buf[i + 3]
    if buf[i + 3] < 2 or len(buf) < i + total:
        return False
    return checksum(bytes(buf[i + 2 : i + total - 1])) == buf[i + total - 1]


def _next_packet(buf: bytearray, end: int) -> int:
    """Where a complete, valid packet starts inside ``buf[2:end]`` (-1: none)."""
    i = buf.find(b"\xff\xff", 2, end)
    while i > 0:
        if _whole_packet_at(buf, i):
            return i
        i = buf.find(b"\xff\xff", i + 1, end)
    return -1


def parse(buf: bytearray) -> list[Frame]:
    """The complete packets at the start of ``buf`` (consumed); bytes before a header are skipped
    and an incomplete packet at the end stays in ``buf`` for the next read. A packet that a valid
    packet interrupts was cut short (``cut``)."""
    out: list[Frame] = []
    while True:
        start = buf.find(b"\xff\xff")
        if start < 0:
            del buf[: max(0, len(buf) - 1)]  # keep a trailing 0xFF: it may start a header
            return out
        del buf[:start]
        if len(buf) < 4:
            return out
        if buf[2] == 0xFF:  # FF FF FF: the header starts one byte later
            del buf[:1]
            continue
        length = buf[3]
        if length < 2:
            del buf[:2]
            continue
        total = 4 + length
        nxt = _next_packet(buf, min(total, len(buf)))
        if nxt > 0:  # a whole packet began before this one ended: this one was cut short
            out.append(Frame(buf[2], buf[4] if nxt > 4 else 0, b"", bytes(buf[:nxt]), ok=False, cut=True))
            del buf[:nxt]
            continue
        if len(buf) < total:
            return out
        raw = bytes(buf[:total])
        ok = checksum(raw[2:-1]) == raw[-1]
        out.append(Frame(raw[2], raw[4], raw[5:-1], raw, ok=ok))
        del buf[:total]


@dataclass
class Evidence:
    """Every packet a servo sent while the doctor listened."""

    valid: int = 0  # validated answers to the request being made
    late: int = 0  # well-formed answers that came too late or were not asked for (discarded)
    corrupt: int = 0  # answers with a wrong checksum
    garbled: int = 0  # answers cut short

    @property
    def answered(self) -> bool:
        """At least one well-formed answer: the servo is powered and on the bus."""
        return self.valid + self.late > 0

    @property
    def heard(self) -> bool:
        """Any packet at all, even a corrupt one."""
        return self.answered or self.corrupt + self.garbled > 0


@dataclass
class Exchange:
    """One request: the validated answer of each servo asked (``frames``), why the others have none
    (``failed``: a key of :data:`OUTCOME_WORDS`) and the time until the last answer."""

    frames: dict[int, Frame] = field(default_factory=dict)
    failed: dict[int, str] = field(default_factory=dict)
    ms: float | None = None


class Probe:
    """One serial port opened read-only for the doctor (see the module doc)."""

    def __init__(self, port: str, *, timeout_s: float = TIMEOUT_S, label: str = "") -> None:
        import serial

        self.port = port
        self.label = label or port
        self.timeout_s = timeout_s
        self.ser: Any = serial.Serial(port, BAUD, timeout=POLL_S, write_timeout=1)
        self.evidence: dict[int, Evidence] = {}
        self.errors: Counter[str] = Counter()
        self.retried = 0  # requests that failed at least once and then got a valid answer
        self.late = 0  # late answers discarded
        self.last_error: str | None = None

    # ------------------------------------------------------------------ plumbing
    def close(self) -> None:
        try:
            self._drain()  # a late answer still on its way is evidence too
        except Exception:  # noqa: S110 - best effort
            pass
        try:
            self.ser.close()
        except Exception:  # noqa: S110 - best effort close
            pass

    def _ev(self, motor_id: int) -> Evidence:
        return self.evidence.setdefault(motor_id, Evidence())

    def _slower(self) -> None:
        """A late answer: wait longer from now on (a slow adapter is slow every time)."""
        self.late += 1
        if self.timeout_s < MAX_TIMEOUT_S:
            self.timeout_s = min(MAX_TIMEOUT_S, self.timeout_s * 2)
            log.debug("%s: late answer, waiting up to %.0f ms from now on", self.label, self.timeout_s * 1000)

    def _note(self, frame: Frame) -> None:
        """A packet nobody asked for (now): evidence about its servo, never a value."""
        ev = self._ev(frame.id)
        if frame.cut:
            ev.garbled += 1
        elif not frame.ok:
            ev.corrupt += 1
        else:
            ev.late += 1
            self._slower()

    def _drain(self) -> None:
        """Empty the receive buffer before a request (what is in it answers an earlier one)."""
        n = self.ser.in_waiting
        data = self.ser.read(n) if n else b""
        self.ser.reset_input_buffer()
        for frame in parse(bytearray(data)):
            self._note(frame)

    def exchange(self, request: bytes, expect: dict[int, int] | None) -> Exchange:
        """Send ``request`` and wait for the answers ``expect`` names (servo id -> number of data
        bytes); ``expect`` None (a broadcast ping) takes every servo's answer without data until
        the timeout. Nothing that fails validation becomes a value."""
        self._drain()
        t0 = time.perf_counter()  # the round trip includes sending the request
        self.ser.write(request)
        self.ser.flush()
        deadline = t0 + self.timeout_s
        buf = bytearray()
        out = Exchange()
        last = t0
        while time.perf_counter() < deadline:
            chunk = self.ser.read(self.ser.in_waiting or 1)
            if chunk:
                buf += chunk
            for f in parse(buf):
                if self._take(f, request, expect, out):
                    last = time.perf_counter()
            if expect is not None and len(out.frames) == len(expect):
                break
        if buf:  # a packet arriving right at the deadline: the rest of it that is already here
            n = self.ser.in_waiting
            if n:
                buf += self.ser.read(n)
            for f in parse(buf):
                if self._take(f, request, expect, out):
                    last = time.perf_counter()
        if expect is not None:
            for mid in expect:
                if mid not in out.frames and mid not in out.failed:
                    out.failed[mid] = GARBLED if buf else NO_ANSWER
            if not out.failed:
                out.ms = (last - t0) * 1000
        return out

    def _take(self, f: Frame, request: bytes, expect: dict[int, int] | None, out: Exchange) -> bool:
        """Validate one packet against the request: True when it is the answer asked for; anything
        else is only evidence (and, from a servo asked, the reason it has no answer yet)."""
        if f.raw == request:
            return False  # the adapter echoed our own request
        wanted = 0 if expect is None else expect.get(f.id)
        if f.ok and not f.cut and wanted is not None and f.id != BROADCAST and f.id not in out.frames:
            if len(f.params) == wanted:
                out.frames[f.id] = f
                out.failed.pop(f.id, None)
                self._ev(f.id).valid += 1
                return True
        self._note(f)
        if wanted is not None and f.id not in out.frames and not f.ok:
            out.failed[f.id] = GARBLED if f.cut else CORRUPT
        return False

    def _failed(self, op: str, ids: str, why: str) -> None:
        self.errors[f"{op} [{ids}]"] += 1
        self.last_error = f"{self.label}: {op} motor id(s) {ids}: {OUTCOME_WORDS.get(why, why)}"
        log.debug("bus error %s", self.last_error)

    # ------------------------------------------------------------------ requests
    def scan(self) -> list[int]:
        """The ids that answer one broadcast ping (one try, as lerobot's scan)."""
        got = self.exchange(packet(BROADCAST, PING), None)
        return sorted(got.frames)

    def ping(self, motor_id: int, tries: int = TRIES) -> tuple[bool, int]:
        """(answered, attempts made): a PING with up to ``tries`` attempts."""
        for i in range(tries):
            got = self.exchange(packet(motor_id, PING), {motor_id: 0})
            if motor_id in got.frames:
                if i:
                    self.retried += 1
                return True, i + 1
            self._failed("ping", str(motor_id), got.failed.get(motor_id, NO_ANSWER))
        return False, tries

    def read(
        self, motor_id: int, addr: int, length: int, tries: int = TRIES
    ) -> tuple[Frame | None, list[str]]:
        """The validated answer to READ ``addr``/``length`` (None when no attempt validated) and why
        each failed attempt failed."""
        why: list[str] = []
        for i in range(tries):
            got = self.exchange(read_packet(motor_id, addr, length), {motor_id: length})
            frame = got.frames.get(motor_id)
            if frame is not None:
                if i:
                    self.retried += 1
                return frame, why
            reason = got.failed.get(motor_id, NO_ANSWER)
            why.append(reason)
            self._failed(f"read {addr}-{addr + length - 1}", str(motor_id), reason)
        return None, why

    def sync_read(self, ids: list[int], addr: int, length: int) -> Exchange:
        """One SYNC_READ, no retry (a timed read)."""
        req = packet(BROADCAST, SYNC_READ, bytes([addr, length, *ids]))
        got = self.exchange(req, dict.fromkeys(ids, length))
        if got.failed:
            first = min(got.failed)
            self._failed(f"sync_read {addr}-{addr + length - 1}", str(first), got.failed[first])
        return got

    def error_summary(self) -> dict[str, Any]:
        """The shape of ``StationMotorsBus.error_summary()``, plus the late answers discarded."""
        return {
            "errors": sum(self.errors.values()),
            "retried_ok": self.retried,
            "late_discarded": self.late,
            "by_call": dict(self.errors.most_common(10)),
            "last_error": self.last_error,
        }
