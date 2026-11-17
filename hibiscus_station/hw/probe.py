"""A read-only Feetech STS probe for ``hibiscus-station doctor``: every answer is validated (QD-25).

The doctor used to read registers through lerobot's bus. A status packet that came later than the
bus timeout (a USB stall, a hub, an adapter with a long latency) then stayed in the receive buffer
and was taken as the answer of the *next* request: every later register of that servo was shifted
by one (``80 C``, ``341.3 V``, ``status overheat, overload``, limits ``44-684``) and the report told
the user to calibrate a correctly calibrated arm again.

Here every request gets only its own validated answers:

* an answer is accepted only when its checksum is right, it is a status packet (not the adapter
  echoing a request) and it carries exactly the number of bytes asked for;
* every well-formed answer is matched, when it arrives, to the oldest request still waiting for an
  answer of that servo with that length (the bus answers in order, QD-30): a late answer is its
  own request's answer, never the next request's, and its delay is measured from its own request;
  an answer to an earlier request also tells that every request before it got all it will get.
  Answers that come as fast as answers usually come are the request being made's own when the
  earlier identical request's answers were lost (no shift of every later request by one);
* the register blocks of one servo all have different lengths (and differ from a ping's 0 and a
  sync read's 2 bytes), so only an answer to an identical request can be matched to a read, and it
  carries the same registers: a late answer to a read (or a ping) is that read's answer;
* a request that got nothing at all in its timeout waits once more as long for a late answer (when
  the servo asked has answered before; the scan, the first request, waits up to twice the longest
  timeout, as nobody knows yet how slow the adapter is);
  a request without a validated answer is retried (bounded: :data:`TRIES`); a read that never
  validates is *unreadable*, and the caller reports it as such, never as a value;
* a late answer raises the timeout to its delay and a half (up to :data:`MAX_TIMEOUT_S`), so an
  adapter that is slow but steady is measured as a slow bus instead of losing every answer;
* a damaged packet (wrong checksum, cut short, still incomplete at the timeout) cannot say who sent
  it, its id byte may be the damaged one (QD-28): it counts for the one servo asked (a ping or a
  read), never for the id it carries; on a broadcast or a sync read it counts for the bus.

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
#: How long the last bytes of a packet that started before the timeout may still take.
GRACE_S = 0.005
#: A scan that got its first answer late stops listening after this long without a new one.
QUIET_S = 0.02
#: How long a request may still get a late answer (a USB stall of a few hundred ms, QD-30).
LATE_HORIZON_S = 2.0

#: Why a request got no validated answer from a servo, in the report's words.
NO_ANSWER = "no_answer"
CORRUPT = "corrupt"
GARBLED = "garbled"
LATE = "late"
OUTCOME_WORDS: dict[str, str] = {
    NO_ANSWER: "no answer",
    CORRUPT: "corrupted answer (checksum)",
    GARBLED: "malformed answer (cut short or the wrong length)",
    LATE: "answer came after the timeout",
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


def _header_inside(buf: bytearray, end: int) -> int:
    """Where a packet header (``FF FF`` and an id) starts inside the damaged packet ``buf[:end]``
    (-1: none): the packet was cut short and the next one began."""
    j = buf.find(b"\xff\xff", 4, end)
    while j > 0 and len(buf) > j + 2 and buf[j + 2] == 0xFF:
        j = buf.find(b"\xff\xff", j + 1, end)
    return j


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
        cut = -1 if ok else _header_inside(buf, total)
        if cut > 0:  # cut short, the next packet's header came before its end (QD-29)
            out.append(Frame(raw[2], raw[4] if cut > 4 else 0, b"", raw[:cut], ok=False, cut=True))
            del buf[:cut]
            continue
        out.append(Frame(raw[2], raw[4], raw[5:-1], raw, ok=ok))
        del buf[:total]


@dataclass
class Evidence:
    """Every packet a servo sent while the doctor listened."""

    valid: int = 0  # validated answers to the request being made, in time
    late: int = 0  # well-formed answers that came after their request's timeout (or unmatched)
    corrupt: int = 0  # damaged answers (wrong checksum) to a request made to this servo alone
    garbled: int = 0  # answers cut short, to a request made to this servo alone

    @property
    def answered(self) -> bool:
        """At least one well-formed answer: the servo is powered and on the bus."""
        return self.valid + self.late > 0

    @property
    def heard(self) -> bool:
        """Any packet at all, even a corrupt one."""
        return self.answered or self.corrupt + self.garbled > 0


@dataclass
class Request:
    """One request sent and the well-formed answers matched to it (QD-30): ``want`` maps each servo
    asked to the number of data bytes asked for (None: a broadcast ping, any servo, no data)."""

    seq: int
    raw: bytes
    want: dict[int, int] | None
    sent: float
    got: dict[int, Frame] = field(default_factory=dict)
    at: dict[int, float] = field(default_factory=dict)  # arrival time of each answer
    damage: str | None = None  # a damaged packet came while it was the request being made
    mine: bool = False  # ... and it counts for the one servo asked (:meth:`Probe._damage`)
    #: a scan that nothing answered in time: an answer goes to it only when no other request
    #: waits for that answer (a scan's late answers look like the pings' answers that follow)
    weak: bool = False

    def accepts(self, f: Frame) -> bool:
        if f.id in self.got or f.id == BROADCAST:
            return False
        if self.want is None:
            return len(f.params) == 0
        return self.want.get(f.id) == len(f.params)

    @property
    def complete(self) -> bool:
        return self.want is not None and len(self.got) == len(self.want)

    @property
    def single(self) -> int | None:
        """The one servo asked (a ping or a read), None for a broadcast or a sync read."""
        return next(iter(self.want)) if self.want is not None and len(self.want) == 1 else None


@dataclass
class Exchange:
    """One request: the validated answer of each servo asked that came in time (``frames``), why
    the others have none (``failed``: a key of :data:`OUTCOME_WORDS`; :data:`LATE` when the
    answer came, matched to this request, after the timeout) and the time until the last answer."""

    request: Request
    frames: dict[int, Frame] = field(default_factory=dict)
    failed: dict[int, str] = field(default_factory=dict)
    ms: float | None = None
    damage: str | None = None  # a damaged packet came while waiting (whoever it counts for)


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
        self.late = 0  # answers that came after their request's timeout
        self.late_ms: list[float] = []  # ... and how long after their request was sent
        #: damaged packets no servo can be named for (a broadcast or sync read was answered)
        self.damaged: Counter[str] = Counter()
        self.last_error: str | None = None
        self.rx = bytearray()
        self.open: list[Request] = []  # requests still waiting for an answer, oldest first
        self._seq = 0
        self._sent: set[bytes] = set()
        self._fast: list[float] = []  # how long answers in time took (s), the latest ones

    # ------------------------------------------------------------------ plumbing
    def close(self) -> None:
        try:
            self._collect()  # a late answer still on its way is evidence too
        except Exception:  # noqa: S110 - best effort
            pass
        try:
            self.ser.close()
        except Exception:  # noqa: S110 - best effort close
            pass

    def _ev(self, motor_id: int) -> Evidence:
        return self.evidence.setdefault(motor_id, Evidence())

    def _answered(self, motor_id: int) -> bool:
        ev = self.evidence.get(motor_id)
        return ev is not None and ev.answered

    def _learn(self, seconds: float) -> None:
        """An answer took ``seconds``, longer than the timeout: wait that long (and a half) from
        now on (a slow adapter is slow every time), up to :data:`MAX_TIMEOUT_S`."""
        wait = min(MAX_TIMEOUT_S, seconds * 1.5 + 0.005)
        if wait > self.timeout_s:
            self.timeout_s = wait
            log.debug("%s: late answer, waiting up to %.0f ms from now on", self.label, wait * 1000)

    def _pull(self, block: bool) -> list[tuple[Frame, float]]:
        """New complete packets (``block``: wait up to :data:`POLL_S` for a byte)."""
        n = self.ser.in_waiting
        if n or block:
            chunk = self.ser.read(n or 1)
            if chunk:
                self.rx += chunk
        now = time.perf_counter()
        return [(f, now) for f in parse(self.rx)]

    def _collect(self) -> None:
        """What arrived while no request was being made: matched to the request it answers."""
        for f, t in self._pull(False):
            self._take(f, t, None, None)

    def _expire(self) -> None:
        now = time.perf_counter()
        self.open = [r for r in self.open if now - r.sent < LATE_HORIZON_S]

    def _take(
        self, f: Frame, t: float, cur: Request | None, pending: list[tuple[Frame, Request, float]] | None
    ) -> None:
        """One packet: a well-formed one is matched to the oldest open request it can answer (the
        bus answers in order); a damaged one is evidence only (:meth:`_damage`)."""
        if f.raw in self._sent:
            return  # the adapter echoed one of our requests
        if not f.ok or f.cut:
            self._damage(GARBLED if f.cut else CORRUPT, cur)
            return
        r = next((r for r in self.open if not r.weak and r.accepts(f)), None)
        r = r or next((r for r in self.open if r.weak and r.accepts(f)), None)
        if r is None:  # nothing waits for it any more (its request expired): still a sign of life
            self._ev(f.id).late += 1
            self.late += 1
            return
        r.got[f.id] = f
        r.at[f.id] = t
        if pending is not None:
            pending.append((f, r, t))  # decided when the request being made is done
        else:
            self._settle(f, r, t, None, 0.0)

    def _damage(self, kind: str, cur: Request | None) -> None:
        """A damaged packet (QD-28, QD-29): its id byte may be the damaged byte, so it counts for
        the one servo the request being made went to, and only when no earlier request may still
        be answered late; otherwise for the bus."""
        if cur is None:
            self.damaged[kind] += 1
            return
        cur.damage = cur.damage or kind
        waiting = any(not r.got and r.damage is None for r in self.open if r.seq < cur.seq)
        if cur.single is None or waiting:
            self.damaged[kind] += 1
            return
        cur.mine = True
        ev = self._ev(cur.single)
        if kind == GARBLED:
            ev.garbled += 1
        else:
            ev.corrupt += 1

    def _settle(self, f: Frame, r: Request, t: float, cur: Request | None, deadline: float) -> None:
        """An answer is final: evidence, its delay, and the requests it closes."""
        ev = self._ev(f.id)
        if r is cur and t <= deadline:
            ev.valid += 1
            self._fast = [*self._fast[-19:], t - r.sent]
        else:
            ev.late += 1
            self.late += 1
            self.late_ms.append(round((t - r.sent) * 1000, 2))
            self._learn(t - r.sent)
        # the bus answers in order: a request sent before ``r`` has had every answer it will get
        self.open = [x for x in self.open if (x.seq >= r.seq or x.weak) and not (x is r and r.complete)]

    def _listen(
        self, cur: Request, until: float, pending: list[tuple[Frame, Request, float]], settle: bool = False
    ) -> None:
        """Take packets until ``until`` or every answer asked for is here (``settle``: or, once an
        answer came, the line has been quiet for :data:`QUIET_S`)."""
        quiet = until
        while time.perf_counter() < min(until, quiet) and not cur.complete:
            for f, t in self._pull(True):
                self._take(f, t, cur, pending)
                if settle and cur.got:
                    quiet = t + QUIET_S

    def exchange(self, request: bytes, expect: dict[int, int] | None) -> Exchange:
        """Send ``request`` and wait for the answers ``expect`` names (servo id -> number of data
        bytes); ``expect`` None (a broadcast ping) takes every servo's answer without data until
        the timeout. Every well-formed answer is matched to the request it answers, even when it
        comes late; nothing that fails validation becomes a value."""
        self._expire()
        self._collect()
        self._seq += 1
        t0 = time.perf_counter()  # the round trip includes sending the request
        self.ser.write(request)
        self.ser.flush()
        # the timeout runs from when the request is out: an adapter that blocks the write as long
        # as its answer takes has the answer ready by then (QD-31)
        sent = time.perf_counter()
        cur = Request(self._seq, request, dict(expect) if expect is not None else None, t0)
        self._sent.add(request)
        self.open.append(cur)
        pending: list[tuple[Frame, Request, float]] = []
        deadline = sent + self.timeout_s
        self._listen(cur, deadline, pending)
        self._prefer_current(cur, pending)
        if not cur.got and cur.damage is None:  # nothing yet: on its way? (a slow adapter, a stall)
            if expect is None:  # the first request: how slow the adapter is, nobody knows yet
                self._listen(cur, t0 + 2 * MAX_TIMEOUT_S, pending, settle=True)
            elif any(self._answered(m) for m in expect):  # (a servo that never answered: no wait)
                self._listen(cur, deadline + self.timeout_s, pending)
        out = Exchange(request=cur)
        self._finish(cur, out, pending, deadline)
        return out

    def _prefer_current(self, cur: Request, pending: list[tuple[Frame, Request, float]]) -> None:
        """Answers matched to an earlier, identical request that came as fast as answers usually
        come are this request's own (the earlier one's answers were lost): oldest-first matching
        would otherwise shift every later identical request by one."""
        if cur.want is None or cur.complete or not self._fast:
            return
        typical = sorted(self._fast)[len(self._fast) // 2]
        limit = max(3 * typical, typical + 0.005)
        for i, (f, r, t) in enumerate(pending):
            if r is not cur and cur.accepts(f) and t - cur.sent <= limit:
                del r.got[f.id], r.at[f.id]
                cur.got[f.id], cur.at[f.id] = f, t
                pending[i] = (f, cur, t)

    def _finish(
        self, cur: Request, out: Exchange, pending: list[tuple[Frame, Request, float]], deadline: float
    ) -> None:
        if len(self.rx) > 1:  # a packet still incomplete: wait for its last bytes a moment
            end = time.perf_counter() + GRACE_S
            while time.perf_counter() < end and len(self.rx) > 1:
                for f, t in self._pull(True):
                    self._take(f, t, cur, pending)
            if len(self.rx) > 1:  # cut short (QD-29): a malformed answer, never nothing
                self.rx.clear()
                self._damage(GARBLED, cur)
        self._prefer_current(cur, pending)
        for f, r, t in pending:
            self._settle(f, r, t, cur, deadline)
        out.damage = cur.damage
        if cur.want is None:
            out.frames = dict(cur.got)
            cur.weak = not cur.got
            return
        for mid in cur.want:
            if mid in cur.got and cur.at[mid] <= deadline:
                out.frames[mid] = cur.got[mid]
            elif mid in cur.got:
                out.failed[mid] = LATE
            elif cur.damage is not None and (cur.mine or cur.single is None):
                out.failed[mid] = cur.damage
            else:
                out.failed[mid] = NO_ANSWER
        if not out.failed:
            out.ms = (max(cur.at.values()) - cur.sent) * 1000

    def _failed(self, op: str, ids: str, why: str) -> None:
        self.errors[f"{op} [{ids}]"] += 1
        self.last_error = f"{self.label}: {op} motor id(s) {ids}: {OUTCOME_WORDS.get(why, why)}"
        log.debug("bus error %s", self.last_error)

    # ------------------------------------------------------------------ requests
    def scan(self) -> list[int]:
        """The ids that answer one broadcast ping (one try, as lerobot's scan)."""
        got = self.exchange(packet(BROADCAST, PING), None)
        return sorted(got.frames)

    def _first(self, reqs: list[Request], motor_id: int) -> tuple[Frame | None, int]:
        """The answer of ``motor_id`` to one of ``reqs`` (identical requests: tries), in time or
        late, and the number of the try it answers."""
        for i, r in enumerate(reqs):
            if motor_id in r.got:
                if i:
                    self.retried += 1
                return r.got[motor_id], i + 1
        return None, 0

    def ping(self, motor_id: int, tries: int = TRIES) -> tuple[bool, int]:
        """(answered, attempts made): a PING with up to ``tries`` attempts. A late answer matched to
        one of them is an answer (QD-30): the servo is there, the bus was slow."""
        reqs: list[Request] = []
        for _ in range(tries):
            got = self.exchange(packet(motor_id, PING), {motor_id: 0})
            reqs.append(got.request)
            frame, n = self._first(reqs, motor_id)
            if frame is not None:
                return True, n
            self._failed("ping", str(motor_id), got.failed.get(motor_id, NO_ANSWER))
        return False, tries

    def read(
        self, motor_id: int, addr: int, length: int, tries: int = TRIES
    ) -> tuple[Frame | None, list[str]]:
        """The validated answer to READ ``addr``/``length`` (None when no attempt validated) and why
        each failed attempt failed. A late answer matched to one of the tries is that read's answer
        (the same registers of the same servo), never another read's (QD-25, QD-30)."""
        why: list[str] = []
        reqs: list[Request] = []
        for _ in range(tries):
            got = self.exchange(read_packet(motor_id, addr, length), {motor_id: length})
            reqs.append(got.request)
            frame, _n = self._first(reqs, motor_id)
            if frame is not None:
                return frame, why
            reason = got.failed.get(motor_id, NO_ANSWER)
            why.append(reason)
            self._failed(f"read {addr}-{addr + length - 1}", str(motor_id), reason)
        return None, why

    def _drain_late(self) -> None:
        """Before a timed request: wait (up to the timeout) for the answers an earlier request still
        expects from servos that do answer, so that a late answer to an earlier identical request is
        matched and gone before this one is timed (QD-31)."""
        end = time.perf_counter() + self.timeout_s

        def waiting() -> bool:
            return any(
                mid not in r.got and self._answered(mid)
                for r in self.open
                if not r.weak and r.want is not None
                for mid in r.want
            )

        while waiting() and time.perf_counter() < end:
            for f, t in self._pull(True):
                self._take(f, t, None, None)

    def sync_read(self, ids: list[int], addr: int, length: int) -> Exchange:
        """One SYNC_READ, no retry (a timed read): only answers in time count as read, timed from
        this request (an earlier one's late answers are matched to it first)."""
        self._expire()
        self._drain_late()
        req = packet(BROADCAST, SYNC_READ, bytes([addr, length, *ids]))
        got = self.exchange(req, dict.fromkeys(ids, length))
        if got.failed:
            first = min(got.failed)
            self._failed(f"sync_read {addr}-{addr + length - 1}", str(first), got.failed[first])
        return got

    def error_summary(self) -> dict[str, Any]:
        """The shape of ``StationMotorsBus.error_summary()``, plus the late answers (matched to the
        request they answer) with their delays, and the damaged packets no servo can be named for."""
        return {
            "errors": sum(self.errors.values()),
            "retried_ok": self.retried,
            "late_answers": self.late,
            "late_ms": self.late_ms[:200],
            "timeout_ms": round(self.timeout_s * 1000),
            "damaged_unattributed": sum(self.damaged.values()),
            "by_call": dict(self.errors.most_common(10)),
            "last_error": self.last_error,
        }
