"""Program conditions (station-programs.md §4): camera, operator, robot state and external sources,
the ≤ 10 Hz wait loop, dry-run fakes, operator-input routing over REST and the control socket."""

from __future__ import annotations

import threading
import time
from dataclasses import replace
from typing import Any

import numpy as np
import pytest
from conftest import mock_profile, wait_for
from pydantic import TypeAdapter

from hibiscus_station.errors import StationError
from hibiscus_station.mock.camera import MockCamera, MockCameraConfig
from hibiscus_station.profiles import GripHold
from hibiscus_station.programs import schemas as ps
from hibiscus_station.programs.conditions import (
    ConditionEngine,
    ConditionError,
    OperatorLatches,
    calibrate_grip_hold,
    engine_for_run,
    gripper_reading,
)
from hibiscus_station.programs.detectors import ColorDetector
from hibiscus_station.programs.interfaces import RobotSnapshot
from hibiscus_station.programs.operator import RunRegistry
from hibiscus_station.programs.signals import SignalBus
from hibiscus_station.station import Station

COND: TypeAdapter[Any] = TypeAdapter(ps.CondExpr)
VALUE: TypeAdapter[Any] = TypeAdapter(ps.ValueExpr)
JOINTS = ["shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll", "gripper"]


def c(**kw: Any) -> Any:
    return COND.validate_python({"id": kw.pop("id", "c1"), **kw})


def v(**kw: Any) -> Any:
    return VALUE.validate_python({"id": kw.pop("id", "v1"), **kw})


def num(x: float, id: str = "n") -> dict[str, Any]:
    return {"id": id, "kind": "number", "value": x}


def text(s: str, id: str = "t") -> dict[str, Any]:
    return {"id": id, "kind": "text", "value": s}


def cube(color: str | None) -> np.ndarray:
    cam = MockCamera(MockCameraConfig(name="t", fps=30, width=128, height=96))
    cam.show_cube(color)  # type: ignore[arg-type]
    return cam._render(3)


def snap(**kw: Any) -> RobotSnapshot:
    base = RobotSnapshot(
        t=0.0,
        tick=10,
        positions={f"{j}.pos": 0.0 for j in JOINTS},
        goal={},
        load_pct={j: 0.0 for j in JOINTS},
        temp_c={j: 30.0 for j in JOINTS},
        frames={"wrist": cube("red")},
        frame_tick=10,
    )
    return replace(base, **kw)


CUBES = ps.ColorDetectorSpec(
    kind="color",
    camera="wrist",
    roi=ps.Roi(x=0.25, y=0.25, w=0.5, h=0.5),
    rules=[
        ps.ColorRule(label="red", h_min=170, h_max=10, s_min=120, v_min=80),
        ps.ColorRule(label="blue", h_min=100, h_max=130, s_min=120, v_min=80),
    ],
)


class CountingDetector:
    def __init__(self) -> None:
        self.inner = ColorDetector(CUBES, "cubes")
        self.calls = 0

    def evaluate(self, frame: Any, *, tick: int = -1) -> ps.DetectorResult:
        self.calls += 1
        return self.inner.evaluate(frame, tick=tick)

    def close(self) -> None:
        pass


class Rig:
    """A ConditionEngine on a settable snapshot, one detector and one pose."""

    def __init__(self, **kw: Any) -> None:
        self.snapshot = snap()
        self.bus = kw.pop("bus", SignalBus())
        self.det = CountingDetector()
        self.vars: dict[str, ps.Scalar] = {"n": 2.0, "name": "bob"}
        self.latches = OperatorLatches(buttons=["go"], keys=["1", "2"])
        self.changes: list[ps.ConditionValue] = []

        def detector(did: str) -> Any:
            if did != "cubes":
                raise StationError("not_found", "no detector")
            return self.det

        def camera(did: str) -> str:
            if did != "cubes":
                raise StationError("not_found", "no detector")
            return "wrist"

        def pose(name: str) -> dict[str, float]:
            if name != "home":
                raise StationError("not_found", "no pose")
            return {"shoulder_pan.pos": 10.0, "elbow_flex.pos": -5.0}

        self.engine = ConditionEngine(
            snapshot=lambda: self.snapshot,
            signals=self.bus,
            detector=detector,
            detector_camera=camera,
            pose=pose,
            grip_hold=GripHold(gap_min=3.0, load_min_pct=15.0),
            latches=self.latches,
            variables=lambda n: self.vars[n],
            on_value=lambda cv, changed: self.changes.append(cv) if changed else None,
            **kw,
        )


# --------------------------------------------------------------------------- values
def test_numbers_texts_and_arithmetic() -> None:
    e = Rig().engine
    assert e.value(v(kind="number", value=3)) == 3.0
    assert e.value(v(kind="var", name="n")) == 2.0
    ops = {"add": 5.0, "sub": -1.0, "mul": 6.0, "div": 2 / 3, "pow": 8.0, "mod": 2.0}
    for op, want in ops.items():
        assert e.value(v(kind="arith", op=op, left=num(2), right=num(3))) == pytest.approx(want)
    assert e.value(v(kind="arith", op="mod", left=num(-7), right=num(3))) == -1.0  # like Blockly (JS %)
    for op, right in (("div", 0), ("mod", 0)):
        with pytest.raises(ConditionError) as ei:
            e.value(v(kind="arith", op=op, left=num(1), right=num(right)))
        assert ei.value.code == "bad_value"
    with pytest.raises(ConditionError):
        e.value(v(kind="arith", op="pow", left=num(-8), right=num(1 / 3)))  # complex
    with pytest.raises(ConditionError):
        e.value(v(kind="arith", op="pow", left=num(10), right=num(400)))  # overflow
    assert e.value(v(kind="arith", op="add", left=text("2"), right=num(1))) == 3.0
    with pytest.raises(ConditionError) as ei:
        e.value(v(kind="arith", op="add", left=text("abc"), right=num(1)))
    assert ei.value.code == "type_mismatch"
    join = v(kind="join", parts=[text("n="), {"id": "x", "kind": "var", "name": "n"}, text("!")])
    assert e.value(join) == "n=2!"
    with pytest.raises(ConditionError) as ei:
        e.value(v(kind="var", name="ghost"))
    assert ei.value.code == "unknown_variable"


def test_random_int_is_inclusive_and_seeded() -> None:
    import random

    e = Rig(rng=random.Random(4)).engine
    seen = {e.value(v(kind="random_int", low=num(1), high=num(3))) for _ in range(200)}
    assert seen == {1.0, 2.0, 3.0}
    assert e.value(v(kind="random_int", low=num(5), high=num(5))) == 5.0
    with pytest.raises(ConditionError):
        e.value(v(kind="random_int", low=num(1.2), high=num(1.8)))


def test_compare_numbers_and_texts() -> None:
    e = Rig().engine
    for op, want in {"eq": False, "ne": True, "lt": True, "le": True, "gt": False, "ge": False}.items():
        assert e.cond(c(kind="compare", op=op, left=num(1), right=num(2))) is want
    assert e.cond(c(kind="compare", op="eq", left=num(0.3), right=num(0.1 + 0.2)))
    assert e.cond(
        c(kind="compare", op="eq", left=text("bob"), right={"id": "x", "kind": "var", "name": "name"})
    )
    assert e.cond(c(kind="compare", op="ne", left=text("a"), right=text("b")))
    with pytest.raises(ConditionError) as ei:
        e.cond(c(kind="compare", op="lt", left=text("a"), right=text("b")))
    assert ei.value.code == "type_mismatch"


def test_logic_short_circuits() -> None:
    rig = Rig()
    e = rig.engine
    stale = {"id": "cam", "kind": "camera_sees", "detector": "ghost", "label": "red"}  # would raise
    assert not e.cond(
        c(kind="logic", op="and", left={"id": "f", "kind": "bool", "value": False}, right=stale)
    )
    assert e.cond(c(kind="logic", op="or", left={"id": "t", "kind": "bool", "value": True}, right=stale))
    assert e.cond(c(kind="not", operand={"id": "f", "kind": "bool", "value": False}))


# --------------------------------------------------------------------------- robot state
def test_joint_value_and_compare() -> None:
    rig = Rig()
    rig.snapshot = snap(positions={**snap().positions, "elbow_flex.pos": 42.5})
    e = rig.engine
    assert e.value(v(kind="joint_value", joint="elbow_flex")) == 42.5
    assert e.cond(
        c(
            kind="compare",
            op="gt",
            left={"id": "j", "kind": "joint_value", "joint": "elbow_flex"},
            right=num(40),
        )
    )
    with pytest.raises(ConditionError) as ei:
        e.value(v(kind="joint_value", joint="tail"))
    assert ei.value.code == "unknown_joint"


def test_motor_temperature() -> None:
    rig = Rig()
    rig.snapshot = snap(temp_c={**snap().temp_c, "wrist_roll": 61.0, "gripper": None})
    e = rig.engine
    assert e.value(v(kind="motor_temp", motor=None)) == 61.0  # hottest
    assert e.value(v(kind="motor_temp", motor="elbow_flex")) == 30.0
    for motor, code in (("gripper", "no_telemetry"), ("tail", "unknown_joint")):
        with pytest.raises(ConditionError) as ei:
            e.value(v(kind="motor_temp", motor=motor))
        assert ei.value.code == code
    rig.snapshot = snap(temp_c={j: None for j in JOINTS})
    with pytest.raises(ConditionError):
        e.value(v(kind="motor_temp", motor=None))


def test_near_pose() -> None:
    rig = Rig()
    e = rig.engine
    pos = {**snap().positions, "shoulder_pan.pos": 11.0, "elbow_flex.pos": -6.5}
    rig.snapshot = snap(positions=pos)
    assert e.cond(c(kind="near_pose", pose="home", tolerance_deg=2.0))
    assert not e.cond(c(kind="near_pose", pose="home", tolerance_deg=1.0))
    with pytest.raises(ConditionError) as ei:
        e.cond(c(kind="near_pose", pose="ghost"))
    assert ei.value.code == "unknown_pose"
    assert e.check(c(kind="near_pose", pose="ghost")) is None


@pytest.mark.parametrize(
    ("goal", "pos", "load", "holding"),
    [
        (None, 30.0, 40.0, False),  # nothing commanded yet
        (0.0, 30.0, 40.0, True),  # closed on an object: stopped 30 short, loaded
        (0.0, 1.0, 40.0, False),  # closed fully: no gap
        (0.0, 30.0, 5.0, False),  # gap but no load (still moving)
        (0.0, 30.0, -40.0, True),  # load sign does not matter
        (100.0, 70.0, 40.0, True),  # the other calibration direction (100 = closed)
        (80.0, 78.5, 40.0, False),  # loaded but at its goal
    ],
)
def test_gripper_holding(goal: float | None, pos: float, load: float, holding: bool) -> None:
    rig = Rig()
    rig.snapshot = snap(
        goal={} if goal is None else {"gripper.pos": goal},
        positions={**snap().positions, "gripper.pos": pos},
        load_pct={**snap().load_pct, "gripper": load},
    )
    assert rig.engine.cond(c(kind="gripper_holding")) is holding


def test_gripper_holding_without_telemetry() -> None:
    rig = Rig()
    rig.snapshot = snap(goal={"gripper.pos": 0.0}, load_pct={})
    assert rig.engine.check(c(kind="gripper_holding")) is None
    assert rig.engine.values()[-1].message == "gripper load is not available yet"


def test_calibrate_grip_hold_from_a_test_grasp() -> None:
    empty = snap(goal={"gripper.pos": 0.0}, positions={"gripper.pos": 1.0}, load_pct={"gripper": 8.0})
    held = snap(goal={"gripper.pos": 0.0}, positions={"gripper.pos": 25.0}, load_pct={"gripper": -48.0})
    gh = calibrate_grip_hold(empty, held)
    assert gh.gap_min == 13.0 and gh.load_min_pct == 28.0
    assert gripper_reading(held) == (25.0, 48.0)
    with pytest.raises(StationError):
        calibrate_grip_hold(held, empty)
    with pytest.raises(StationError):
        calibrate_grip_hold(snap(), held)


# --------------------------------------------------------------------------- camera
def test_camera_sees_runs_the_detector_once_per_frame() -> None:
    rig = Rig()
    e = rig.engine
    red = c(id="sees_red", kind="camera_sees", detector="cubes", label="red")
    blue = c(id="sees_blue", kind="camera_sees", detector="cubes", label="blue")
    assert e.cond(red) and not e.cond(blue)
    assert rig.det.calls == 1  # same frame_tick: cached
    rig.snapshot = snap(frames={"wrist": cube("blue")}, frame_tick=11)
    assert e.cond(blue) and not e.cond(red)
    assert rig.det.calls == 2
    conf = v(id="conf", kind="detector_confidence", detector="cubes")
    assert 0.4 < float(e.value(conf)) < 0.6
    assert e.value(v(id="conf_red", kind="detector_confidence", detector="cubes", label="red")) < 0.05
    assert {cv.block_id: cv.value for cv in e.values()} == {
        "sees_red": False,
        "sees_blue": True,
        "conf": pytest.approx(e.value(conf)),
        "conf_red": pytest.approx(
            e.value(v(id="x", kind="detector_confidence", detector="cubes", label="red"))
        ),
    }


def test_camera_conditions_fail_cleanly() -> None:
    rig = Rig()
    e = rig.engine
    rig.snapshot = snap(stale_cameras=["wrist"])
    sees = c(id="s", kind="camera_sees", detector="cubes", label="red")
    assert e.check(sees) is None
    assert e.values()[0].value is None and "no fresh frame" in (e.values()[0].message or "")
    rig.snapshot = snap()
    assert e.check(c(id="s2", kind="camera_sees", detector="cubes", camera="front", label="red")) is None
    with pytest.raises(ConditionError) as ei:
        e.cond(c(id="s3", kind="camera_sees", detector="ghost", label="red"))
    assert ei.value.code == "unknown_detector" and ei.value.block_id == "s3"


def test_red_blue_cube_picks_a_branch() -> None:
    """The owner's example, at condition level: red -> A, blue -> B, nothing -> wait."""
    rig = Rig()
    e = rig.engine
    red = c(id="r", kind="camera_sees", detector="cubes", label="red")
    blue = c(id="b", kind="camera_sees", detector="cubes", label="blue")
    picked = []
    for i, color in enumerate(["red", "blue", None, "red"]):
        rig.snapshot = snap(frames={"wrist": cube(color)}, frame_tick=100 + i)
        picked.append("A" if e.cond(red) else "B" if e.cond(blue) else "-")
    assert picked == ["A", "B", "-", "A"]


# --------------------------------------------------------------------------- dry-run fakes
def test_fakes_override_detectors_and_gripper_in_dry_runs() -> None:
    rig = Rig(dry_run=True)
    e = rig.engine
    sees_blue = c(kind="camera_sees", detector="cubes", label="blue")
    assert not e.cond(sees_blue)
    e.fake(ps.FakeConditions(detectors={"cubes": ps.FakeDetector(label="blue", confidence=0.8)}))
    assert e.cond(sees_blue)
    assert e.value(v(kind="detector_confidence", detector="cubes")) == 0.8
    e.fake(ps.FakeConditions(gripper_holding=True))
    assert e.cond(sees_blue) and e.cond(c(kind="gripper_holding"))  # fakes accumulate
    e.fake(ps.FakeConditions(detectors={"ghost": ps.FakeDetector(label=None)}))
    assert not e.cond(c(kind="camera_sees", detector="ghost", label="red"))  # fake of an unknown id
    e.fake(ps.FakeConditions(clear=True))
    assert not e.cond(sees_blue) and not e.cond(c(kind="gripper_holding"))
    hw = Rig().engine
    with pytest.raises(StationError) as ei:
        hw.fake(ps.FakeConditions(gripper_holding=True))
    assert ei.value.code == "validation_failed"


# --------------------------------------------------------------------------- operator
def test_button_and_key_presses_latch_once() -> None:
    rig = Rig()
    e, lat = rig.engine, rig.latches
    btn, key = c(kind="button_pressed", button="go"), c(kind="key_pressed", key="1")
    assert not e.cond(btn) and not e.cond(key)
    lat.push(ps.OperatorInput(kind="button", value="go"))
    lat.push(ps.OperatorInput(kind="button", value="go"))  # two presses before a read: one latch
    lat.push(ps.OperatorInput(kind="key", value="1"))
    assert e.cond(btn) and not e.cond(btn)
    assert not e.cond(c(kind="key_pressed", key="2")) and e.cond(key) and not e.cond(key)
    lat.push(ps.OperatorInput(kind="key", value="2"))
    lat.clear()
    assert not e.cond(c(kind="key_pressed", key="2"))


@pytest.mark.parametrize(
    "ev",
    [
        ps.OperatorInput(kind="button", value="stop_all"),  # not one of this program's buttons
        ps.OperatorInput(kind="key", value="9"),  # not read by the program
        ps.OperatorInput(kind="key", value=" "),  # Space is the e-stop
        ps.OperatorInput(kind="key", value="ab"),
        ps.OperatorInput(kind="answer", value="yes"),  # nothing asked
    ],
)
def test_operator_input_is_validated(ev: ps.OperatorInput) -> None:
    with pytest.raises(StationError) as ei:
        Rig().latches.push(ev)
    assert ei.value.code == "validation_failed"


def test_ask_answers() -> None:
    lat = OperatorLatches()
    lat.ask(ps.AskPrompt(block_id="ask1", question="Which bin?", choices=["left", "right"]))
    assert lat.prompt is not None and lat.take_answer() is None
    with pytest.raises(StationError):
        lat.push(ps.OperatorInput(kind="answer", value="middle"))
    lat.push(ps.OperatorInput(kind="answer", value="right"))
    assert lat.changed.is_set()
    assert lat.take_answer() == "right" and lat.prompt is None and lat.take_answer() is None
    lat.ask(ps.AskPrompt(block_id="ask2", question="?", choices=["a"]))
    lat.cancel_ask()
    assert lat.prompt is None


def test_upper_case_keys_are_accepted() -> None:
    rig = Rig()
    rig.latches.push(ps.OperatorInput(kind="key", value="1"))
    lat = OperatorLatches(keys=["a"])
    lat.push(ps.OperatorInput(kind="key", value="A"))
    assert lat.take("key", "a")


# --------------------------------------------------------------------------- external
def test_signal_conditions() -> None:
    bus = SignalBus()
    bus.set("early", 1, "http")  # before the run: not "received" by it
    rig = Rig(bus=bus)
    e = rig.engine
    eq = c(kind="signal_equals", name="door", value="open")
    assert not e.cond(eq)
    with pytest.raises(ConditionError) as ei:
        e.value(v(kind="signal_value", name="door"))
    assert ei.value.code == "signal_unset"
    bus.set("door", "open", "http")
    assert e.cond(eq) and e.value(v(kind="signal_value", name="door")) == "open"
    bus.set("count", 5, "http")
    assert e.cond(c(kind="signal_equals", name="count", value="5"))
    assert e.cond(
        c(kind="compare", op="ge", left={"id": "s", "kind": "signal_value", "name": "count"}, right=num(5))
    )


def test_message_received_is_per_node_and_since_the_run_start() -> None:
    bus = SignalBus()
    bus.set("door", 1, "http")
    rig = Rig(bus=bus)
    e = rig.engine
    a = c(id="a", kind="message_received", source="http", name="door")
    b = c(id="b", kind="message_received", source="http", name="door")
    m = c(id="m", kind="message_received", source="mqtt", name="factory/door")
    assert not e.cond(a)
    bus.set("door", 2, "http")
    assert e.cond(a) and not e.cond(a)  # consumed by node a...
    assert e.cond(b)  # ...but node b has its own view
    bus.set("door", 3, "program")  # not an HTTP message
    assert not e.cond(a)
    assert not e.cond(m)
    bus.message("factory/door", "open", "mqtt")
    assert e.cond(m) and not e.cond(m)


# --------------------------------------------------------------------------- waiting
def test_wait_until_is_paced_at_condition_hz() -> None:
    rig = Rig(condition_hz=10.0)
    e = rig.engine
    t0 = time.monotonic()
    out = e.wait_until(c(kind="key_pressed", key="1"), timeout_s=0.55, cancelled=lambda: False)
    took = time.monotonic() - t0
    assert out == "timeout" and 0.5 <= took < 0.9
    assert 5 <= e.evaluations <= 7  # ≤ 10 Hz, never a busy loop


def test_wait_until_rate_is_capped_at_10_hz() -> None:
    e = Rig(condition_hz=10.0).engine
    assert e.period_s == pytest.approx(0.1)
    assert ConditionEngine(
        snapshot=snap,
        signals=SignalBus(),
        detector=lambda d: None,  # type: ignore[arg-type,return-value]
        detector_camera=lambda d: "wrist",
        pose=lambda p: {},
        grip_hold=GripHold(),
        condition_hz=50.0,
    ).period_s == pytest.approx(0.1)


def test_wait_until_returns_on_input_and_on_cancel() -> None:
    rig = Rig()
    e = rig.engine
    threading.Timer(0.25, lambda: rig.latches.push(ps.OperatorInput(kind="key", value="2"))).start()
    t0 = time.monotonic()
    assert e.wait_until(c(kind="key_pressed", key="2"), timeout_s=5, cancelled=lambda: False) == "true"
    assert time.monotonic() - t0 < 0.6
    stop = threading.Event()

    def cancel() -> None:
        stop.set()
        e.wake.set()

    threading.Timer(0.2, cancel).start()
    t0 = time.monotonic()
    ticks: list[int] = []
    assert (
        e.wait_until(
            c(kind="bool", value=False),
            timeout_s=None,
            cancelled=stop.is_set,
            on_tick=lambda: ticks.append(1),
        )
        == "cancelled"
    )
    assert time.monotonic() - t0 < 0.4 and ticks
    # a condition that cannot be evaluated keeps waiting (not true) until the timeout
    assert (
        e.wait_until(c(kind="near_pose", pose="ghost"), timeout_s=0.15, cancelled=lambda: False) == "timeout"
    )


def test_conditions_are_never_evaluated_in_the_owner_thread() -> None:
    rig = Rig(forbidden_thread=threading.get_ident())
    with pytest.raises(StationError) as ei:
        rig.engine.cond(c(kind="bool", value=True))
    assert ei.value.code == "internal_error"
    out: list[bool] = []
    t = threading.Thread(target=lambda: out.append(rig.engine.cond(c(kind="bool", value=True))))
    t.start()
    t.join()
    assert out == [True]


def test_value_changes_are_reported_once() -> None:
    rig = Rig()
    e = rig.engine
    eq = c(id="eq", kind="signal_equals", name="door", value=1)
    e.cond(eq)
    e.cond(eq)
    rig.bus.set("door", 1, "http")
    e.cond(eq)
    assert [(cv.block_id, cv.value) for cv in rig.changes] == [("eq", False), ("eq", True)]


# --------------------------------------------------------------------------- wiring to the Station
def test_engine_for_run_uses_the_station_stores_and_live_camera(station: Station) -> None:
    from hibiscus_station.hw.cameras import FrameSet

    profile = mock_profile()
    profile.follower.grip_hold = GripHold(gap_min=7.0, load_min_pct=20.0)
    station.profiles.put(profile)
    station.owner.call("connect", robot_id="desk", timeout=30)
    wait_for(lambda: (fs := station.hub.latest()) is not None and "wrist" in fs.frames)
    station.programs.detectors().put("cubes", ps.DetectorInput(name="Cubes", spec=CUBES))

    def live() -> RobotSnapshot:
        fs = station.hub.latest()
        assert isinstance(fs, FrameSet)
        return snap(
            frames=dict(fs.frames), frame_tick=fs.tick if fs.tick >= 0 else int(time.monotonic() * 1000)
        )

    e = engine_for_run(
        station, snapshot=live, latches=OperatorLatches(), variables=lambda n: 0.0, dry_run=False
    )
    assert (
        e.grip_hold.gap_min == 7.0
        and e.forbidden_thread == station.owner.ident
        and e.period_s == pytest.approx(0.1)
    )
    station.hub.camera("wrist").show_cube("blue")
    blue = c(kind="camera_sees", detector="cubes", label="blue")
    assert e.wait_until(blue, timeout_s=3, cancelled=lambda: False) == "true"
    station.hub.camera("wrist").show_cube("red")
    red = c(kind="camera_sees", detector="cubes", label="red")
    assert e.wait_until(red, timeout_s=3, cancelled=lambda: False) == "true"
    assert e.check(c(kind="near_pose", pose="home")) is None  # no "home" pose saved
    station.programs.signals.set("door", 1, "http")
    assert e.cond(c(kind="signal_equals", name="door", value=1))


# --------------------------------------------------------------------------- operator routing
class FakeRuntime:
    """Just enough of ProgramRuntime for input routing."""

    def __init__(self, program_id: str, buttons: list[str], keys: list[str]) -> None:
        self.program_id = program_id
        self.latches = OperatorLatches(buttons, keys)
        self.finished = False
        self.inputs: list[ps.OperatorInput] = []

    def input(self, ev: ps.OperatorInput) -> None:
        self.latches.push(ev)
        self.inputs.append(ev)

    def state(self) -> ps.ProgramState:
        return ps.ProgramState(
            run_id="r_20261116_120000_abcd",
            program_id=self.program_id,
            version=1,
            dry_run=True,
            status="waiting",
            block_id=None,
            block_kind=None,
            t=0.0,
            steps=0,
            variables={},
            conditions=[],
            waiting=None,
            ask=None,
            buttons=[ps.OperatorButton(name=b, label=b) for b in self.latches.buttons],
            keys=self.latches.keys,
            message=None,
        )


def test_run_registry_routes_input() -> None:
    reg = RunRegistry()
    with pytest.raises(StationError) as ei:
        reg.deliver(ps.OperatorInput(kind="key", value="1"))
    assert ei.value.code == "not_found"
    a, b = FakeRuntime("a", ["go"], ["1"]), FakeRuntime("b", [], ["2"])
    reg.register("a", a)  # type: ignore[arg-type]
    reg.register("b", b)  # type: ignore[arg-type]
    reg.deliver(ps.OperatorInput(kind="key", value="2"))  # newest run
    assert b.inputs and not a.inputs
    st = reg.deliver(ps.OperatorInput(kind="button", value="go"), "a")
    assert st.program_id == "a" and a.latches.take("button", "go")
    b.finished = True
    reg.deliver(ps.OperatorInput(kind="key", value="1"))  # b finished: a is current
    assert len(a.inputs) == 2
    with pytest.raises(StationError) as ei:
        reg.deliver(ps.OperatorInput(kind="key", value="1"), "b")
    assert ei.value.code == "not_found"
    assert reg.get("b") is b
    with pytest.raises(StationError) as ei:
        reg.deliver(ps.OperatorInput(kind="key", value=" "))
    assert ei.value.code == "validation_failed"
    reg.register("a", a)  # type: ignore[arg-type]  # re-register keeps one entry
    assert reg.running() is a


def test_program_input_over_rest(client: Any, station: Station) -> None:
    r = client.post("/api/v1/programs/ab/input", json={"kind": "key", "value": "1"})
    assert r.status_code == 404 and r.json()["code"] == "not_found"
    rt = FakeRuntime("ab", ["go"], ["1", "2"])
    station.programs.runs.register("ab", rt)  # type: ignore[arg-type]
    r = client.post("/api/v1/programs/ab/input", json={"kind": "key", "value": "2"})
    assert r.status_code == 200, r.text
    assert ps.ProgramState.model_validate(r.json()).program_id == "ab"
    assert rt.latches.take("key", "2")
    r = client.post("/api/v1/programs/ab/input", json={"kind": "button", "value": "nope"})
    assert r.status_code == 422 and r.json()["code"] == "validation_failed"
    assert client.post("/api/v1/programs/ab/input", json={"kind": "key"}).status_code == 422


def test_program_input_over_the_control_socket(client: Any, station: Station) -> None:
    auth = {"authorization": client.headers["Authorization"]}
    with client.websocket_connect("/api/v1/ws", headers=auth) as ws:
        assert ws.receive_json()["type"] == "hello"
        ws.send_json({"type": "hello", "v": 1, "client": "test"})
        ws.send_json({"type": "program_input", "kind": "key", "value": "1"})
        err = ws.receive_json()
        assert err == {"type": "error", "action": "program_input", "detail": "no program is running"}
        rt = FakeRuntime("ab", ["go"], ["1"])
        station.programs.runs.register("ab", rt)  # type: ignore[arg-type]
        ws.send_json({"type": "program_input", "kind": "button", "value": "go"})
        ws.send_json({"type": "program_input", "kind": "weird", "value": "x"})
        err = ws.receive_json()
        assert err["type"] == "error" and err["detail"] == "bad program_input"
        assert wait_for(lambda: rt.latches.take("button", "go"), timeout=2)
        ws.send_json({"type": "program_input", "kind": "key", "value": "7"})
        err = ws.receive_json()
        assert err["type"] == "error" and "does not read key" in err["detail"]
