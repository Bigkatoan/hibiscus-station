"""Field report 0.2.8 (Windows, real SO-101 pair, 0.2.5-0.2.7).

1. E-stop during "Run on the robot": the next run must start from the beginning (no goal of the
   interrupted run survives), calibration is never touched by e-stop / reset, "Return to rest pose"
   after the reset, and "Align follower to leader" when teleop refuses a far leader.
2. Leader telemetry: ~6.5 A on every leader motor (raw ~1000 at Present_Current), 0 °C temperatures:
   implausible values are unknown (never an alert, never "reads are failing"), the leader never
   raises current / load / status alerts and never stops the robot; follower protections stay.
"""

from __future__ import annotations

import json
import time
from typing import Any, ClassVar

import pytest
from blocks_dsl import blk, play, program
from conftest import (
    Events,
    Heartbeat,
    connect_calibrated,
    fast_hand,
    gentle_hand,
    press_estop_frozen_within_one_tick,
    wait_for,
)
from test_programs_safety import _phase, _put, _rt, _run, _traj

from hibiscus_station.errors import StationError
from hibiscus_station.hw import calibration, feetech
from hibiscus_station.hw.telemetry import TelemetryRead, TelemetryScheduler, ThermalGuard
from hibiscus_station.mock import get_world
from hibiscus_station.settings import TelemetrySettings, Thresholds
from hibiscus_station.station import Station, TeleopRequest

API = "/api/v1"
MOTORS = ("shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll", "gripper")


@pytest.fixture
def real(connected: Station) -> Station:
    connected.settings.programs.require_dry_run = False
    return connected


def _calibrate_wide(st: Station, arm: str) -> None:
    """Calibrate through ±1400 steps (±123°), like a real arm, so far poses stay in range (the mock
    servo clamps goals to the calibrated position limits, as a real one does).

    Deterministic on any machine speed (QD-6): the home is set with every joint held at the
    centre, and the sweep runs until the recorded ranges cover the whole ±1400 steps. With the
    home taken at a random point of the sweep, the rest pose of a later test could sit at the
    edge of the range, where "60° away" was clamped to 5°."""
    world = get_world(f"mock://{arm}")
    world.hand = lambda _m, _t: 2048.0
    st.owner.call("calibration_start", arm=arm)
    time.sleep(0.1)
    st.owner.call("calibration_step", action="set_home")
    world.hand = fast_hand(amplitude=1400.0)

    def covered() -> bool:
        proc = st.owner.calibration
        if proc is None:
            return False
        lo, hi = dict(proc.mins), dict(proc.maxes)
        return all(
            m in calibration.FULL_TURN_MOTORS
            or (lo.get(m, 2048) <= 2048 - 1380 and hi.get(m, 0) >= 2048 + 1380)
            for m in MOTORS
        )

    wait_for(covered, 30)
    st.owner.call("calibration_step", action="finish_ranges")
    world.hand = None if arm == "follower" else gentle_hand
    world.place_all(2048.0)


@pytest.fixture
def wide(connected: Station) -> Station:
    _calibrate_wide(connected, "follower")
    _calibrate_wide(connected, "leader")
    connected.settings.programs.require_dry_run = False
    time.sleep(0.2)
    return connected


# =========================================================================== 2. leader telemetry
class _FieldLeaderBus:
    """What the field leader answered: 5.3 V, 0 °C, Present_Current ~1000 (6.4-6.5 A), load 0."""

    motors: ClassVar[dict[str, None]] = dict.fromkeys(MOTORS)

    def sync_read(self, reg: str, normalize: bool = False, num_retry: int = 0) -> dict[str, int]:
        if reg == feetech.REG_TEMPERATURE:
            return dict.fromkeys(self.motors, 0)
        if reg == feetech.REG_VOLTAGE:
            return dict.fromkeys(self.motors, 53)
        if reg == feetech.REG_CURRENT:
            return {m: 988 + i * 2 for i, m in enumerate(self.motors)}
        if reg == feetech.REG_MAX_TEMPERATURE:
            return dict.fromkeys(self.motors, 0)
        if reg == feetech.REG_MAX_VOLTAGE:
            return dict.fromkeys(self.motors, 80)
        if reg == feetech.REG_MIN_VOLTAGE:
            return dict.fromkeys(self.motors, 40)
        if reg == feetech.REG_PROTECTION_CURRENT:
            return dict.fromkeys(self.motors, 250)
        return dict.fromkeys(self.motors, 0)


def test_impossible_current_is_unknown_not_an_alert_and_not_a_failed_read() -> None:
    sched = TelemetryScheduler(TelemetrySettings())
    sched.add_arm("leader", _FieldLeaderBus())
    lim = sched.read_limits("leader")
    guard = ThermalGuard(Thresholds())
    reads = [r for _ in range(5) for r in sched.read_all()]
    alerts = [a for r in reads for a in guard.update(r, lim)]
    at = sched.arms["leader"]
    assert all(r.ok for r in reads), [r.error for r in reads if not r.ok]
    assert not any(r.degraded for r in reads)  # no "Motor telemetry reads are failing"
    assert at.stale_groups() == []
    view = at.motor_view("gripper", guard.level("leader", "gripper"))
    assert view["current_a"] is None and view["temp_c"] is None  # unknown, shown as a dash
    assert view["voltage_v"] == pytest.approx(5.3)
    assert view["stale"] is False
    assert not alerts
    assert not guard.take_critical()


def test_current_bounds_and_sign_bit() -> None:
    assert feetech.decode_current(100) == pytest.approx(0.65)
    assert feetech.decode_current(0x8000 | 100) == pytest.approx(0.65)  # direction bit, not 213 A
    assert feetech.plausible("current_a", 1.6)
    assert not feetech.plausible("current_a", 6.5)
    assert not feetech.plausible("load_pct", 250.0)
    assert feetech.plausible("load_pct", -80.0)
    assert not feetech.plausible("voltage_v", 0.0)
    assert feetech.plausible("voltage_v", 12.1)


def _read(arm: str, group: str, values: dict[str, Any], t: float = 0.0) -> TelemetryRead:
    return TelemetryRead(arm, group, t, True, values)


def test_leader_telemetry_never_alerts_and_never_stops_the_robot() -> None:
    from hibiscus_station.hw.telemetry import ArmLimits

    guard = ThermalGuard(Thresholds())
    lim = ArmLimits(min_voltage_v=6.0, protection_current_a={"gripper": 1.0})
    alerts = []
    for i in range(5):
        alerts += guard.update(_read("leader", "current_a", {"gripper": 2.9}, i), lim)
        alerts += guard.update(_read("leader", "load_pct", {"gripper": 99.0}, i * 10.0), lim)
        alerts += guard.update(_read("leader", "status", {"gripper": ["overload", "overcurrent"]}, i), lim)
        alerts += guard.update(_read("leader", "voltage_v", {"gripper": 4.0}, i), lim)
        alerts += guard.update(_read("leader", "temp_c", {"gripper": 95.0}, i), lim)
    assert [a.kind for a in alerts if a.kind != "temperature"] == []
    assert all(a.level != "critical" for a in alerts)
    assert not guard.take_critical()
    assert guard.hot_motors() == [] and not guard.any_motor_at_or_above_hot()


def test_follower_protections_are_kept() -> None:
    from hibiscus_station.hw.telemetry import ArmLimits

    guard = ThermalGuard(Thresholds())
    lim = ArmLimits(protection_current_a={"elbow_flex": 1.0})
    alerts = guard.update(_read("follower", "current_a", {"elbow_flex": 2.9}), lim)
    assert [a.kind for a in alerts] == ["current"]
    for i in range(3):
        guard.update(_read("follower", "status", {"elbow_flex": ["overload"]}, i), lim)
    assert [e.arm for e in guard.take_critical()] == ["follower"]


def test_field_leader_on_the_owner_raises_nothing(station: Station, events: Events) -> None:
    connect_calibrated(station)
    leader = get_world("mock://leader")
    leader.inject(current_raw=1000, temp_c=0)
    time.sleep(2.5)
    st = station.status()
    kinds = {(a["kind"], a.get("arm")) for a in st["alerts"]}
    assert ("current", "leader") not in kinds
    assert not any(k == "telemetry_degraded" for k, _ in kinds), kinds
    assert st["state"] == "idle"
    lt = [t for t in events.of("telemetry") if t["arm"] == "leader" and t["group"] == "current_a"][-1]
    assert lt["motors"]["gripper"]["current_a"] is None
    assert lt["motors"]["gripper"]["stale"] is False


# =========================================================================== 1. e-stop and next run
def test_estop_relax_then_next_run_never_drives_back_to_the_old_goal(real: Station, client: Any) -> None:
    """A motion that targets only some joints held the others at the last goal of the run the
    e-stop interrupted: after a relax e-stop the arm drove back there ("continues the previous turn")."""
    st = real
    tid = _traj(st, seconds=6.0, start_offset=0.0)
    _put(client, program(play(tid, id_="pl")))
    world = get_world("mock://follower")
    with Heartbeat(st):
        assert _run(client).status_code == 200
        wait_for(lambda: _phase(st) == "replay", 3)
        time.sleep(2.0)
        st.owner.press_estop("user")
        st.owner.press_estop("user", relax=True)  # second press: torque off, the arm is limp
        wait_for(lambda: st.owner.state == "estopped" and not st.owner.follower_torque, 2)
    assert st.owner.last_sent == {}  # nothing of the interrupted run survives
    # the limp arm is moved by hand (or falls): shoulder_lift goes 150 steps (13°) away, inside the
    # calibrated range (the servo clamps goals to its position limits)
    world.set_hand("shoulder_lift", world.present_raw("shoulder_lift") + 150)
    time.sleep(0.3)
    assert client.post(f"{API}/estop/reset").status_code == 200
    here = dict(st.owner.call("read_positions"))
    _put(client, program(blk("hb_gripper", "g", fields={"ACTION": "open"})), pid="g")
    with Heartbeat(st):
        assert _run(client, pid="g").status_code == 200
        rt = _rt(st, "g")
        assert rt.join(10) and rt.outcome == "completed"
    after = st.owner.call("read_positions")
    assert abs(here["shoulder_lift.pos"]) > 10.0
    assert after["shoulder_lift.pos"] == pytest.approx(here["shoulder_lift.pos"], abs=2.0)


def test_estop_and_reset_never_touch_the_calibration(real: Station, client: Any, tmp_path: Any) -> None:
    st = real
    files = sorted((tmp_path / "calibration").rglob("*.json"))
    before = {p: p.read_text() for p in files}
    regs = {
        port: {m: dict(s.regs) for m, s in get_world(port).servos.items()}
        for port in ("mock://follower", "mock://leader")
    }
    tid = _traj(st, seconds=4.0)
    _put(client, program(play(tid, id_="pl")))
    with Heartbeat(st):
        assert _run(client).status_code == 200
        wait_for(lambda: _phase(st) == "replay", 3)
        st.owner.press_estop("user")
        st.owner.press_estop("user", relax=True)
        wait_for(lambda: st.owner.state == "estopped", 2)
    assert client.post(f"{API}/estop/reset").status_code == 200
    assert {p: p.read_text() for p in files} == before
    for port, by_id in regs.items():
        for m, r in by_id.items():
            now = get_world(port).servos[m].regs
            for k in ("homing_offset", "min_position_limit", "max_position_limit"):
                assert now[k] == r[k], (port, m, k)
    s = st.status()
    assert s["robot"]["arms"]["follower"]["calibrated"] and s["robot"]["arms"]["leader"]["calibrated"]


def _set_rest(st: Station) -> dict[str, float]:
    rest = st.owner.call("set_rest_pose")["rest_pose"]
    return {k: float(v) for k, v in rest.items()}


def test_interrupted_motion_offers_the_rest_pose_and_returns_there(real: Station, client: Any) -> None:
    st = real
    rest = _set_rest(st)
    tid = _traj(st, seconds=6.0, start_offset=0.0)
    _put(client, program(play(tid, id_="pl")))
    assert client.get(f"{API}/status").json()["interrupted"] is False
    with Heartbeat(st):
        assert _run(client).status_code == 200
        wait_for(lambda: _phase(st) == "replay", 3)
        time.sleep(2.5)
        st.owner.press_estop("user")
        wait_for(lambda: st.owner.state == "estopped", 2)
    assert client.get(f"{API}/status").json()["interrupted"] is True
    # refused while the e-stop is latched
    r = client.post(f"{API}/robots/rest")
    assert r.status_code == 409 and r.json()["code"] == "estopped"
    assert client.post(f"{API}/estop/reset").status_code == 200
    s = client.get(f"{API}/status").json()
    assert s["state"] == "idle" and s["interrupted"] is True
    away = st.owner.last_obs["shoulder_pan.pos"]
    assert abs(away - rest["shoulder_pan.pos"]) > 3.0
    with Heartbeat(st):
        r = client.post(f"{API}/robots/rest")
        assert r.status_code == 200, r.text
        assert r.json()["kind"] == "rest"
        wait_for(lambda: st.owner.state == "idle", 15)
    last = st.owner.last_session_summary
    assert last is not None and last["kind"] == "rest" and last["outcome"] == "completed"
    pos = st.owner.call("read_positions")
    for k, v in rest.items():
        assert pos[k] == pytest.approx(v, abs=3.0), k
    assert client.get(f"{API}/status").json()["interrupted"] is False


def test_rest_move_is_slow_cancellable_and_needs_the_heartbeat(wide: Station, client: Any) -> None:
    st = wide
    world = get_world("mock://follower")
    rest = _set_rest(st)
    # put the arm 60° away from the rest pose on shoulder_pan
    st.owner.call("torque", arm="follower", enabled=False, confirm=True)
    world.set_hand("shoulder_pan", world.present_raw("shoulder_pan") + 683)
    time.sleep(0.3)
    world.hand = None
    wait_for(lambda: abs(st.owner.last_obs["shoulder_pan.pos"] - rest["shoulder_pan.pos"]) > 55.0, 3)
    with Heartbeat(st):
        r = client.post(f"{API}/robots/rest")
        assert r.status_code == 200, r.text
        lim = r.json()["episode"]["limit_s"]
        speed = st.settings.programs.approach_speed_deg_s
        assert lim >= 1.875 * 55.0 / speed  # min-jerk at the capped peak speed: >= 3.4 s for 60°
        # Stop once the move is under way (not after a fixed sleep: on a loaded machine 0.5 s of
        # sleep can last long enough for the arm to get near Home; QC 0.2.9 r2 saw 7.9°).
        start = st.owner.last_obs["shoulder_pan.pos"]
        wait_for(lambda: abs(st.owner.last_obs["shoulder_pan.pos"] - start) > 2.0, 5)
        assert client.post(f"{API}/sessions/current/control", json={"action": "stop"}).status_code == 200
        wait_for(lambda: st.owner.state == "idle", 3)
    assert st.owner.last_session_summary["outcome"] == "stopped"
    assert abs(st.owner.last_obs["shoulder_pan.pos"] - rest["shoulder_pan.pos"]) > 20.0
    # dead-man: without the UI heartbeat the move e-stops
    st.owner.heartbeat()
    client.post(f"{API}/robots/rest")
    wait_for(lambda: st.owner.state == "estopped", 5)
    assert st.owner.estop.reason == "ui_lost"
    st.owner.call("estop_reset")


def test_rest_without_a_rest_pose_is_refused(real: Station, client: Any) -> None:
    st = real
    assert st.owner.profile is not None
    st.owner.profile.follower.rest_pose = None
    r = client.post(f"{API}/robots/rest")
    assert r.status_code == 422, r.text
    assert r.json()["params"]["code"] == "no_rest_pose"


def _leader_far(st: Station) -> None:
    """The leader hangs folded while the follower stays where the e-stop froze it (field case)."""
    leader = get_world("mock://leader")
    off = {"shoulder_lift": 900.0, "elbow_flex": -900.0}  # ~79° each, inside the calibrated range
    leader.hand = lambda m, _t: 2048.0 + off.get(m, 0.0)
    time.sleep(0.3)


def test_far_leader_is_refused_then_aligned(wide: Station, client: Any) -> None:
    st = wide
    _leader_far(st)
    with pytest.raises(StationError) as e:
        st.start_teleop(TeleopRequest())
    assert e.value.code == "leader_far"
    assert set(e.value.params["joints"]) & {"shoulder_lift", "elbow_flex"}
    assert e.value.params["can_align"] is True
    t0 = time.monotonic()
    with Heartbeat(st):
        r = client.post(f"{API}/sessions/teleop", json={"align": True})
        assert r.status_code == 200, r.text
        assert r.json()["episode"]["phase"] == "align"
        assert st.owner.session is not None and st.owner.session.deadman
        try:
            wait_for(lambda: st.status()["sub"] == "teleop", 60)  # the slow align is ~5 s; headroom for load
        except AssertionError:
            s_ = st.status()
            raise AssertionError(
                f"align: state={s_['state']} sub={s_['sub']} reason={s_['reason']} detail={s_['detail']} "
                f"obs={st.owner.last_obs} leader={st.owner.last_leader} sent={st.owner.last_sent}"
            ) from None
        took = time.monotonic() - t0

        def tracking_gap() -> float:
            lead, fol = st.owner.last_leader, st.owner.last_obs
            return abs(lead["shoulder_lift.pos"] - fol["shoulder_lift.pos"])

        # Right after the hand-over the follower may still be catching up for a few ticks (the blend
        # is timed by the clock, the follower by its per-tick limit): wait for it to track, with
        # headroom for a loaded machine (QC 0.2.9 round 3: 29.36 on the first tick under load 3-4).
        wait_for(lambda: tracking_gap() < 10.0, 10)
        assert st.owner.session is not None and not st.owner.session.deadman  # plain teleop again
        client.post(f"{API}/sessions/current/control", json={"action": "stop"})
        wait_for(lambda: st.owner.state == "idle", 3)
    gap = max(abs(v) for v in e.value.params["joints"].values())
    assert took >= 1.875 * (gap - 30.0) / st.settings.programs.approach_speed_deg_s  # capped peak speed


def test_align_honours_the_estop(wide: Station, client: Any) -> None:
    st = wide
    _leader_far(st)
    world = get_world("mock://follower")
    with Heartbeat(st):
        assert client.post(f"{API}/sessions/teleop", json={"align": True}).status_code == 200
        time.sleep(0.6)
        press_estop_frozen_within_one_tick(st, world)
    st.owner.call("estop_reset")


def test_status_carries_interrupted_in_the_ws_contract(real: Station, events: Events) -> None:
    st = real
    st.owner.press_estop("user")
    wait_for(lambda: st.owner.state == "estopped", 2)
    st.owner.call("estop_reset")
    states = events.of("state")
    assert states and all("interrupted" in s for s in states[-2:])
    assert json.dumps(states[-1])  # serialisable


# =========================================================================== 4. programs list
def test_programs_list_never_waits_for_the_hardware_owner(connected: Station, client: Any) -> None:
    """``GET /programs`` (the "New program" screen) answers from the store, never through the owner
    thread: it stays fast while the owner is busy, e-stopped or in error."""
    import threading

    st = connected
    busy = threading.Event()

    def block(_owner: Any) -> None:
        busy.set()
        time.sleep(3.0)

    t = threading.Thread(target=lambda: st.owner.call("run", fn=block, timeout=10.0), daemon=True)
    t.start()
    assert busy.wait(2)
    t0 = time.monotonic()
    r = client.get(f"{API}/programs")
    assert r.status_code == 200 and time.monotonic() - t0 < 1.0
    r = client.put(f"{API}/programs/new_one", json={"name": "New one", "editor": program(), "buttons": []})
    assert r.status_code == 200 and time.monotonic() - t0 < 1.5
    t.join(5)
    st.owner.press_estop("user")
    wait_for(lambda: st.owner.state == "estopped", 2)
    assert [p["id"] for p in client.get(f"{API}/programs").json()["programs"]] == ["new_one"]
    st.owner.call("estop_reset")


def test_record_never_offers_align(connected: Station) -> None:
    from hibiscus_station.station import RecordRequest

    st = connected
    _leader_far(st)
    with pytest.raises(StationError) as e:
        st.start_record(RecordRequest(dataset="d1", task="t"))
    assert e.value.code == "leader_far" and e.value.params["can_align"] is False
