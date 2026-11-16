"""Conditions and value expressions of block programs (station-programs.md §4, §5).

:class:`ConditionEngine` evaluates the ``CondExpr`` / ``ValueExpr`` nodes of the AST for one program
run. It runs in the program-runner thread (never in the hardware-owner thread, which it refuses) and
reads the robot only through ``MotionPort.snapshot()`` (a :class:`RobotSnapshot` copied after each
tick), so a condition can never delay the control loop.

Sources:

* **camera** — ``camera_sees`` / ``detector_confidence`` run the detector on the snapshot's latest
  frame of that camera. A result is cached per ``(detector, camera, frame_tick)``, so a detector runs at
  most once per frame however many blocks read it. A stale camera cannot be evaluated.
* **operator** — :class:`OperatorLatches`: a button or key press latches until a condition reads it
  (then it is consumed); ``ask`` answers are queued for the waiting ``ask`` statement.
* **robot state** — ``gripper_holding`` (the gripper was commanded but stopped short of its goal:
  ``|goal - present| ≥ grip_hold.gap_min`` with ``|load| ≥ grip_hold.load_min_pct``; the sign is not
  used because it depends on the gripper's calibration direction),
  ``joint_value`` (present position, degrees), ``near_pose`` (every joint of the pose within the
  tolerance), ``motor_temp`` (one motor, or the hottest).
* **external** — ``signal_equals`` / ``signal_value`` read the :class:`SignalBus`;
  ``message_received`` is true when a message arrived on ``(source, name)`` since the previous
  evaluation of that node (since the run started for the first one).

Dry runs (§5.2) may override detector results and ``gripper_holding`` with :class:`FakeConditions`.

``wait until`` and ``while`` checks go through :meth:`ConditionEngine.wait_until`, which evaluates at
most ``condition_hz`` (≤ 10 Hz, ``settings.programs.condition_hz``) and returns as soon as the run is
cancelled.

A node that cannot be evaluated (stale camera, unknown pose, unset signal, text compared with ``<``)
raises :class:`ConditionError`; :meth:`ConditionEngine.check` turns that into ``None`` (not true yet)
for the waiting forms. Every evaluated condition's last value is kept for ``ProgramState.conditions``.
"""

from __future__ import annotations

import math
import random
import threading
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from hibiscus_station.errors import StationError
from hibiscus_station.profiles import GripHold
from hibiscus_station.programs.schemas import (
    KEY_RE,
    Arith,
    AskPrompt,
    BoolLit,
    ButtonPressed,
    CameraSees,
    Compare,
    CondExpr,
    ConditionValue,
    DetectorConfidence,
    DetectorResult,
    FakeConditions,
    FakeDetector,
    GripperHolding,
    Join,
    JointValue,
    KeyPressed,
    Logic,
    MessageReceived,
    MotorTemp,
    NearPose,
    Not,
    NumberLit,
    OperatorInput,
    RandomInt,
    Scalar,
    SignalEquals,
    SignalValue,
    TextLit,
    ValueExpr,
    VarRef,
)
from hibiscus_station.programs.signals import values_equal

if TYPE_CHECKING:
    from hibiscus_station.programs.interfaces import DetectorRuntime, RobotSnapshot, SignalBus
    from hibiscus_station.station import Station

GRIPPER = "gripper"
MAX_TEXT = 500


class ConditionError(Exception):
    """A node that cannot be evaluated now (``code`` is a short machine reason)."""

    def __init__(self, code: str, message: str, block_id: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.block_id = block_id


# --------------------------------------------------------------------------- operator input
class OperatorLatches:
    """Operator buttons, keys and ``ask`` answers of one run. Thread-safe (API/WS threads push, the
    runner consumes). Space is the e-stop and never reaches a program."""

    def __init__(self, buttons: Iterable[str] = (), keys: Iterable[str] = ()) -> None:
        self.buttons = list(dict.fromkeys(buttons))
        self.keys = list(dict.fromkeys(keys))
        self._lock = threading.Lock()
        self._pressed: set[tuple[str, str]] = set()
        self._ask: AskPrompt | None = None
        self._answer: str | None = None
        self.changed = threading.Event()

    def push(self, ev: OperatorInput) -> None:
        """Latch a press / store an answer; ``validation_failed`` for what the program cannot take."""
        with self._lock:
            if ev.kind == "button":
                if ev.value not in self.buttons:
                    raise StationError(
                        "validation_failed",
                        f"this program has no button {ev.value!r}",
                        params={"button": ev.value},
                    )
                self._pressed.add(("button", ev.value))
            elif ev.kind == "key":
                key = ev.value.lower()
                if not KEY_RE.fullmatch(key):
                    raise StationError(
                        "validation_failed",
                        "keys are 0-9 and a-z (Space is the e-stop)",
                        params={"key": ev.value},
                    )
                if key not in self.keys:
                    raise StationError(
                        "validation_failed", f"this program does not read key {key!r}", params={"key": key}
                    )
                self._pressed.add(("key", key))
            else:
                ask = self._ask
                if ask is None:
                    raise StationError("validation_failed", "the program is not asking anything")
                if ev.value not in ask.choices:
                    raise StationError(
                        "validation_failed", "not one of the choices", params={"choices": ask.choices}
                    )
                self._answer = ev.value
        self.changed.set()

    def take(self, kind: Literal["button", "key"], value: str) -> bool:
        """True once per press (the latch is consumed)."""
        with self._lock:
            key = (kind, value)
            if key in self._pressed:
                self._pressed.discard(key)
                return True
            return False

    def ask(self, prompt: AskPrompt) -> None:
        with self._lock:
            self._ask, self._answer = prompt, None

    def take_answer(self) -> str | None:
        """The answer to the open ``ask`` (closing it), or ``None`` while unanswered."""
        with self._lock:
            ans = self._answer
            if ans is not None:
                self._ask, self._answer = None, None
            return ans

    def cancel_ask(self) -> None:
        with self._lock:
            self._ask, self._answer = None, None

    @property
    def prompt(self) -> AskPrompt | None:
        with self._lock:
            return self._ask

    def clear(self) -> None:
        with self._lock:
            self._pressed.clear()


# --------------------------------------------------------------------------- engine
DetectorLookup = Callable[[str], "DetectorRuntime"]
DetectorCamera = Callable[[str], str]
PoseLookup = Callable[[str], dict[str, float]]
Variables = Callable[[str], Scalar]
WaitOutcome = Literal["true", "timeout", "cancelled"]


@dataclass
class _Cached:
    frame_tick: int
    result: DetectorResult


class ConditionEngine:
    """Evaluates conditions and values for one run (see the module docstring)."""

    def __init__(
        self,
        *,
        snapshot: Callable[[], RobotSnapshot],
        signals: SignalBus,
        detector: DetectorLookup,
        detector_camera: DetectorCamera,
        pose: PoseLookup,
        grip_hold: GripHold,
        latches: OperatorLatches | None = None,
        variables: Variables | None = None,
        condition_hz: float = 10.0,
        dry_run: bool = False,
        forbidden_thread: int | None = None,
        clock: Callable[[], float] = time.monotonic,
        rng: random.Random | None = None,
        on_value: Callable[[ConditionValue, bool], None] | None = None,
    ) -> None:
        self._snapshot = snapshot
        self.signals = signals
        self._detector = detector
        self._detector_camera = detector_camera
        self._pose = pose
        self.grip_hold = grip_hold
        self.latches = latches or OperatorLatches()
        self._variables = variables
        self.period_s = 1.0 / min(10.0, max(0.1, float(condition_hz)))
        self.dry_run = dry_run
        self.forbidden_thread = forbidden_thread
        self._clock = clock
        self._t0 = clock()
        self._rng = rng or random.Random()  # noqa: S311 - the `random` block, not security
        self._on_value = on_value
        self._lock = threading.Lock()
        self._fakes = FakeConditions()
        self._seen: dict[str, int] = {}
        self._start_seq = signals.seq
        self._values: dict[str, ConditionValue] = {}
        self._cache: dict[tuple[str, str], _Cached] = {}
        self._snap: RobotSnapshot | None = None
        self.wake = threading.Event()
        self.evaluations = 0

    # ------------------------------------------------------------------ fakes (dry runs)
    def fake(self, fakes: FakeConditions) -> None:
        if not self.dry_run:
            raise StationError("validation_failed", "fake conditions are for dry runs only")
        with self._lock:
            base = FakeConditions() if fakes.clear else self._fakes
            dets = {**base.detectors, **fakes.detectors}
            holding = fakes.gripper_holding if fakes.gripper_holding is not None else base.gripper_holding
            self._fakes = FakeConditions(detectors=dets, gripper_holding=holding)
        self.wake.set()

    @property
    def fakes(self) -> FakeConditions:
        with self._lock:
            return self._fakes

    # ------------------------------------------------------------------ public API
    def check(self, expr: CondExpr) -> bool | None:
        """Evaluate a condition; ``None`` when it cannot be evaluated now (recorded with a message)."""
        try:
            return self.cond(expr)
        except ConditionError:
            return None

    def cond(self, expr: CondExpr) -> bool:
        """Evaluate a condition (raises :class:`ConditionError`). One fresh snapshot per call."""
        self._guard()
        self._snap = None
        self.evaluations += 1
        try:
            return self._cond(expr)
        finally:
            self._snap = None

    def value(self, expr: ValueExpr) -> Scalar:
        """Evaluate a number/text expression (raises :class:`ConditionError`)."""
        self._guard()
        self._snap = None
        try:
            return self._value(expr)
        finally:
            self._snap = None

    def wait_until(
        self,
        expr: CondExpr,
        *,
        timeout_s: float | None,
        cancelled: Callable[[], bool],
        on_tick: Callable[[], None] | None = None,
    ) -> WaitOutcome:
        """Poll ``expr`` at most ``condition_hz`` until it is true, the timeout passes or ``cancelled()``.

        ``wake`` (set by a stop/abort, a fake change) only makes the runner re-check ``cancelled``
        early; evaluations stay at least one period apart."""
        deadline = None if timeout_s is None else self._clock() + timeout_s
        last = -math.inf
        while True:
            if cancelled():
                return "cancelled"
            now = self._clock()
            if now - last >= self.period_s:
                last = now
                if self.check(expr):
                    return "true"
                if on_tick is not None:
                    on_tick()
            now = self._clock()
            if deadline is not None and now >= deadline:
                return "timeout"
            delay = last + self.period_s - now
            if deadline is not None:
                delay = min(delay, deadline - now)
            self.wake.wait(max(0.0, delay))
            self.wake.clear()

    def values(self) -> list[ConditionValue]:
        """The last value of each evaluated condition node (``ProgramState.conditions``)."""
        with self._lock:
            return list(self._values.values())

    def elapsed(self) -> float:
        return self._clock() - self._t0

    # ------------------------------------------------------------------ internals
    def _guard(self) -> None:
        if self.forbidden_thread is not None and threading.get_ident() == self.forbidden_thread:
            raise StationError("internal_error", "conditions are never evaluated in the control tick")

    def _robot(self) -> RobotSnapshot:
        if self._snap is None:
            self._snap = self._snapshot()
        return self._snap

    def _record(self, block_id: str, value: bool | float | str | None, message: str | None = None) -> None:
        cv = ConditionValue(block_id=block_id, value=value, t=round(self.elapsed(), 3), message=message)
        with self._lock:
            old = self._values.get(block_id)
            self._values[block_id] = cv
        changed = old is None or old.value != cv.value or old.message != cv.message
        if self._on_value is not None:
            self._on_value(cv, changed)

    def _cond(self, e: CondExpr) -> bool:
        try:
            v = self._cond_inner(e)
        except ConditionError as exc:
            if exc.block_id is None:
                exc.block_id = e.id
            if exc.block_id == e.id:
                self._record(e.id, None, exc.message)
            raise
        if not isinstance(e, BoolLit | Not | Logic):
            self._record(e.id, v)
        return v

    def _cond_inner(self, e: CondExpr) -> bool:
        if isinstance(e, BoolLit):
            return e.value
        if isinstance(e, Not):
            return not self._cond(e.operand)
        if isinstance(e, Logic):
            left = self._cond(e.left)
            if e.op == "and":
                return left and self._cond(e.right)
            return left or self._cond(e.right)
        if isinstance(e, Compare):
            return self._compare(e)
        if isinstance(e, CameraSees):
            return self._detect(e.detector, e.camera, e.id).label == e.label
        if isinstance(e, ButtonPressed):
            return self.latches.take("button", e.button)
        if isinstance(e, KeyPressed):
            return self.latches.take("key", e.key)
        if isinstance(e, GripperHolding):
            return self._holding(e.id)
        if isinstance(e, NearPose):
            return self._near(e)
        if isinstance(e, SignalEquals):
            sig = self.signals.get(e.name)
            return sig is not None and values_equal(sig.value, e.value)
        if isinstance(e, MessageReceived):
            return self._received(e)
        raise ConditionError("unknown_condition", f"unknown condition {type(e).__name__}", e.id)

    def _compare(self, e: Compare) -> bool:
        a, b = self._value(e.left), self._value(e.right)
        if isinstance(a, float) and isinstance(b, float):
            return {
                "eq": math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-9),
                "ne": not math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-9),
                "lt": a < b,
                "le": a <= b,
                "gt": a > b,
                "ge": a >= b,
            }[e.op]
        if e.op == "eq":
            return values_equal(a, b)
        if e.op == "ne":
            return not values_equal(a, b)
        raise ConditionError("type_mismatch", "texts can only be compared with = and ≠", e.id)

    # robot state
    def _holding(self, block_id: str) -> bool:
        fake = self.fakes.gripper_holding
        if fake is not None:
            return fake
        snap = self._robot()
        key = f"{GRIPPER}.pos"
        goal, pos = snap.goal.get(key), snap.positions.get(key)
        if pos is None:
            raise ConditionError("unknown_joint", "the robot has no gripper", block_id)
        if goal is None:
            return False  # nothing commanded yet: not after a close
        load = snap.load_pct.get(GRIPPER)
        if load is None:
            raise ConditionError("no_telemetry", "gripper load is not available yet", block_id)
        # |goal - present|: the sign depends on the calibration direction of the gripper, and a free
        # gripper reaches its goal within a tick or two, so only a blocked one keeps a gap under load
        gap = abs(goal - pos)
        return gap >= self.grip_hold.gap_min and abs(load) >= self.grip_hold.load_min_pct

    def _near(self, e: NearPose) -> bool:
        try:
            target = self._pose(e.pose)
        except StationError as exc:
            raise ConditionError("unknown_pose", f"no pose {e.pose}", e.id) from exc
        pos = self._robot().positions
        for joint, want in target.items():
            have = pos.get(joint)
            if have is None:
                raise ConditionError("unknown_joint", f"the robot has no joint {joint}", e.id)
            if abs(have - want) > e.tolerance_deg:
                return False
        return True

    def _joint(self, joint: str, block_id: str) -> float:
        key = joint if joint.endswith(".pos") else f"{joint}.pos"
        v = self._robot().positions.get(key)
        if v is None:
            raise ConditionError("unknown_joint", f"the robot has no joint {joint}", block_id)
        return float(v)

    def _temp(self, motor: str | None, block_id: str) -> float:
        temps = self._robot().temp_c
        if motor is not None:
            if motor not in temps:
                raise ConditionError("unknown_joint", f"the robot has no motor {motor}", block_id)
            t = temps[motor]
            if t is None:
                raise ConditionError("no_telemetry", f"no temperature for {motor} yet", block_id)
            return float(t)
        known = [float(v) for v in temps.values() if v is not None]
        if not known:
            raise ConditionError("no_telemetry", "no motor temperature yet", block_id)
        return max(known)

    # external
    def _received(self, e: MessageReceived) -> bool:
        seq = self.signals.last_seq(e.name, e.source)
        with self._lock:
            seen = self._seen.get(e.id, self._start_seq)
            self._seen[e.id] = max(seen, seq)
        return seq > seen

    # camera
    def _detect(self, detector_id: str, camera: str | None, block_id: str) -> DetectorResult:
        fake: FakeDetector | None = self.fakes.detectors.get(detector_id)
        try:
            cam = camera or self._detector_camera(detector_id)
        except StationError as exc:
            if fake is None:
                raise ConditionError("unknown_detector", f"no detector {detector_id}", block_id) from exc
            cam = camera or ""
        if fake is not None:
            scores = {fake.label: fake.confidence} if fake.label is not None else {}
            return DetectorResult(
                detector=detector_id,
                camera=cam,
                label=fake.label,
                confidence=fake.confidence,
                scores=scores,
                ms=0.0,
                tick=-1,
                annotated_jpeg_b64=None,
            )
        snap = self._robot()
        frame = snap.frames.get(cam)
        if frame is None or cam in snap.stale_cameras:
            raise ConditionError("camera_stale", f"no fresh frame from camera {cam}", block_id)
        key = (detector_id, cam)
        with self._lock:
            hit = self._cache.get(key)
        if hit is not None and hit.frame_tick == snap.frame_tick:
            return hit.result
        try:
            res = self._detector(detector_id).evaluate(frame, tick=snap.frame_tick)
        except StationError as exc:
            raise ConditionError(exc.code, exc.detail, block_id) from exc
        if res.camera != cam:
            res = res.model_copy(update={"camera": cam})
        with self._lock:
            self._cache[key] = _Cached(snap.frame_tick, res)
        return res

    # values
    def _value(self, e: ValueExpr) -> Scalar:
        if isinstance(e, NumberLit):
            return float(e.value)
        if isinstance(e, TextLit):
            return e.value
        if isinstance(e, VarRef):
            if self._variables is None:
                raise ConditionError("unknown_variable", f"no variable {e.name}", e.id)
            try:
                return self._variables(e.name)
            except KeyError as exc:
                raise ConditionError("unknown_variable", f"no variable {e.name}", e.id) from exc
        if isinstance(e, Arith):
            return self._arith(e)
        if isinstance(e, RandomInt):
            lo, hi = self._number(e.low), self._number(e.high)
            lo_i, hi_i = math.ceil(min(lo, hi)), math.floor(max(lo, hi))
            if lo_i > hi_i:
                raise ConditionError("bad_value", "no whole number in that range", e.id)
            return float(self._rng.randint(lo_i, hi_i))
        if isinstance(e, Join):
            return "".join(_text(self._value(p)) for p in e.parts)[:MAX_TEXT]
        if isinstance(e, JointValue):
            return self._joint(e.joint, e.id)
        if isinstance(e, MotorTemp):
            return self._temp(e.motor, e.id)
        if isinstance(e, DetectorConfidence):
            res = self._detect(e.detector, e.camera, e.id)
            v = res.confidence if e.label is None else res.scores.get(e.label, 0.0)
            self._record(e.id, float(v))
            return float(v)
        if isinstance(e, SignalValue):
            sig = self.signals.get(e.name)
            if sig is None:
                raise ConditionError("signal_unset", f"signal {e.name} has no value yet", e.id)
            return sig.value
        raise ConditionError("unknown_value", f"unknown value {type(e).__name__}", e.id)

    def _number(self, e: ValueExpr) -> float:
        v = self._value(e)
        if isinstance(v, float):
            return v
        try:
            f = float(v)
        except ValueError as exc:
            raise ConditionError("type_mismatch", f"{v!r} is not a number", e.id) from exc
        if not math.isfinite(f):
            raise ConditionError("type_mismatch", f"{v!r} is not a number", e.id)
        return f

    def _arith(self, e: Arith) -> float:
        a, b = self._number(e.left), self._number(e.right)
        out: float | complex
        try:
            if e.op == "add":
                out = a + b
            elif e.op == "sub":
                out = a - b
            elif e.op == "mul":
                out = a * b
            elif e.op == "div":
                out = a / b
            elif e.op == "mod":
                out = math.fmod(a, b)  # sign of the dividend, like Blockly's JavaScript %
            else:
                out = a**b
        except (ZeroDivisionError, OverflowError, ValueError) as exc:
            raise ConditionError("bad_value", f"cannot compute {e.op}: {exc}", e.id) from exc
        if isinstance(out, complex) or not math.isfinite(out):
            raise ConditionError("bad_value", f"{e.op} gives no finite number", e.id)
        return float(out)


def _text(v: Scalar) -> str:
    if isinstance(v, float) and v.is_integer() and abs(v) < 1e15:
        return str(int(v))
    return str(v)


# --------------------------------------------------------------------------- wiring
def gripper_reading(snap: RobotSnapshot) -> tuple[float, float] | None:
    """``(|goal - present|, |load|)`` of the gripper in ``snap``, ``None`` when unknown."""
    key = f"{GRIPPER}.pos"
    goal, pos, load = snap.goal.get(key), snap.positions.get(key), snap.load_pct.get(GRIPPER)
    if goal is None or pos is None or load is None:
        return None
    return abs(goal - pos), abs(load)


def calibrate_grip_hold(empty: RobotSnapshot, holding: RobotSnapshot) -> GripHold:
    """Thresholds from a test grasp: one snapshot after closing on nothing, one after closing on the
    object. Each threshold sits halfway between the two readings (``validation_failed`` when the
    grasp does not separate them)."""
    a, b = gripper_reading(empty), gripper_reading(holding)
    if a is None or b is None:
        raise StationError("validation_failed", "both snapshots need the gripper goal, position and load")
    if b[0] <= a[0] or b[1] <= a[1]:
        raise StationError(
            "validation_failed",
            "the grasp did not stop the gripper: no gap or load difference",
            params={"empty": list(a), "holding": list(b)},
        )
    return GripHold(gap_min=round((a[0] + b[0]) / 2, 2), load_min_pct=round((a[1] + b[1]) / 2, 2))


def engine_for_run(
    station: Station,
    *,
    snapshot: Callable[[], RobotSnapshot],
    latches: OperatorLatches,
    variables: Variables,
    dry_run: bool,
    robot_id: str | None = None,
    on_value: Callable[[ConditionValue, bool], None] | None = None,
) -> ConditionEngine:
    """A :class:`ConditionEngine` wired to the Station's stores for one run (the interpreter's)."""
    hub = station.programs
    rid = robot_id or hub.robot_id()
    detectors = hub.detectors(rid)

    def detector_camera(detector_id: str) -> str:
        return detectors.get(detector_id).spec.camera

    def pose(name: str) -> dict[str, float]:
        return dict(hub.poses(rid).get(name).positions)

    profile = station.owner.profile if station.owner.profile is not None else station.profiles.get(rid)
    return ConditionEngine(
        snapshot=snapshot,
        signals=hub.signals,
        detector=detectors.runtime,
        detector_camera=detector_camera,
        pose=pose,
        grip_hold=profile.follower.grip_hold if profile is not None else GripHold(),
        latches=latches,
        variables=variables,
        condition_hz=station.settings.programs.condition_hz,
        dry_run=dry_run,
        forbidden_thread=station.owner.ident,
        on_value=on_value,
    )
