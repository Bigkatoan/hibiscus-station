"""Owner integration on mocks with real threads (spec §9.2): timing, ownership, e-stop, thermal stop."""

from __future__ import annotations

import time

import pytest
from conftest import Events, Heartbeat, calibrate, connect_calibrated, mock_profile, wait_for

from hibiscus_station.errors import StationError
from hibiscus_station.mock import get_world
from hibiscus_station.station import Station, TeleopRequest


def test_connect_reads_telemetry_and_limits(station: Station, events: Events) -> None:
    station.profiles.put(mock_profile())
    st = station.owner.call("connect", robot_id="desk", timeout=30)
    assert st["state"] == "idle"
    assert st["robot"]["connected"] is True
    tel = events.of("telemetry")
    assert {t["arm"] for t in tel} == {"follower", "leader"}
    f = [t for t in tel if t["arm"] == "follower"][-1]
    assert f["limits"]["max_temp_c"] == 70
    assert f["motors"]["elbow_flex"]["temp_c"] == pytest.approx(28, abs=2)
    assert station.status()["health"]["hottest"]["temp_c"] is not None


def test_calibration_files_are_loadable_by_lerobot(station: Station, tmp_path) -> None:  # type: ignore[no-untyped-def]
    from lerobot.robots.so_follower import SOFollower, SOFollowerRobotConfig
    from lerobot.teleoperators.so_leader import SOLeader, SOLeaderTeleopConfig

    station.profiles.put(mock_profile())
    station.owner.call("connect", robot_id="desk", timeout=30)
    out = calibrate(station, "follower")
    assert out["calibration"]["step"] == "done"
    calibrate(station, "leader")
    cal = tmp_path / "calibration"
    f = SOFollower(
        SOFollowerRobotConfig(
            port="/dev/null", id="desk_follower", calibration_dir=cal / "robots" / "so_follower"
        )
    )
    assert set(f.calibration) == {
        "shoulder_pan",
        "shoulder_lift",
        "elbow_flex",
        "wrist_flex",
        "wrist_roll",
        "gripper",
    }
    assert f.calibration["wrist_roll"].range_min == 0 and f.calibration["wrist_roll"].range_max == 4095
    assert f.calibration["elbow_flex"].range_max - f.calibration["elbow_flex"].range_min >= 100
    lead = SOLeader(
        SOLeaderTeleopConfig(
            port="/dev/null", id="desk_leader", calibration_dir=cal / "teleoperators" / "so_leader"
        )
    )
    assert lead.calibration
    st = station.status()
    assert st["robot"]["arms"]["follower"]["calibrated"] and st["robot"]["arms"]["leader"]["calibrated"]


def test_reconnect_reuses_calibration_file(station: Station) -> None:
    connect_calibrated(station)
    station.owner.call("disconnect")
    from hibiscus_station.mock import reset_worlds

    reset_worlds()  # fresh motors: EEPROM lost, the file must be written back
    station.owner.call("connect", robot_id="desk", timeout=30)
    st = station.status()
    assert st["robot"]["arms"]["follower"]["calibrated"] is True


def test_teleop_timing_ownership_and_telemetry(connected: Station, events: Events) -> None:
    st = connected
    st.start_teleop(TeleopRequest(fps=30))
    assert st.owner.state == "teleop"
    time.sleep(3.0)
    stats = st.owner.stats
    reads = st.owner.telemetry.reads
    ticks = stats.total_ticks
    st.owner.call("control", action="stop")
    assert st.owner.state == "idle"
    assert ticks >= 80
    assert stats.session_p95_ms() <= 36.0, stats.session_p95_ms()
    # 2 arms x (2 hot groups x 2 Hz + 3 cool groups x 1 Hz) = 14 reads/s, never more than one per tick
    assert 30 <= reads <= 14 * 3 + 8, reads
    assert reads <= ticks
    for port in ("mock://follower", "mock://leader"):
        assert not get_world(port).owner_violations
    joints = [j for j in events.of("joints") if "action" in j]
    assert joints and "fps" in joints[-1]["loop"]


def test_foreign_thread_bus_access_is_detected(connected: Station) -> None:
    world = get_world("mock://follower")
    with pytest.raises(AssertionError):
        connected.owner.follower.bus.sync_read("Present_Temperature", normalize=False)
    assert world.owner_violations
    world.owner_violations.clear()


def test_estop_freezes_within_one_tick_then_relaxes(connected: Station) -> None:
    st = connected
    world = get_world("mock://follower")
    st.start_teleop(TeleopRequest(fps=30))
    time.sleep(0.6)
    world.record_calls = True
    t_press = time.monotonic()
    st.owner.press_estop("user")
    wait_for(lambda: st.owner.state == "estopped", 2)
    writes = [t for t, _ in world.goal_writes() if t > t_press]
    # at most the freeze write (Goal := Present) and one in-flight tick write
    assert len(writes) <= 2, writes
    assert all(t - t_press < 1 / 30 + 0.05 for t in writes)
    assert world.any_torque()  # freeze: the arm does not fall
    assert st.owner.reason == "user"
    st.owner.press_estop("user")  # second press within 2 s: torque off
    wait_for(lambda: not world.any_torque(), 2)
    st.owner.call("estop_reset")
    assert st.owner.state == "idle"


def test_thermal_critical_safe_stop_and_reset_refused(connected: Station, events: Events) -> None:
    st = connected
    world = get_world("mock://follower")
    st.start_teleop(TeleopRequest(fps=30))
    time.sleep(0.3)
    t0 = time.monotonic()
    world.inject("elbow_flex", temp_c=66.0)
    wait_for(lambda: st.owner.state == "estopped", 4)
    assert time.monotonic() - t0 <= 2.5
    assert st.owner.reason == "thermal"
    assert not world.any_torque()
    crit = [a for a in events.of("alert") if a["level"] == "critical"]
    assert any(a["motor"] == "elbow_flex" for a in crit)
    with pytest.raises(StationError) as ei:
        st.owner.call("estop_reset")
    assert ei.value.code == "motor_hot"
    with pytest.raises(StationError):
        st.start_teleop(TeleopRequest())
    world.inject("elbow_flex", temp_c=40.0)
    wait_for(lambda: st.owner.guard.temps.get(("follower", "elbow_flex"), 99) < 45, 4)
    st.owner.call("estop_reset")
    assert st.owner.state == "idle"


def test_single_hot_sample_is_not_critical(connected: Station) -> None:
    st = connected
    world = get_world("mock://follower")
    world.inject("gripper", temp_c=61.0)
    wait_for(lambda: st.owner.guard.temp_level.get(("follower", "gripper")) == "hot", 4)
    assert st.owner.state == "idle"
    with pytest.raises(StationError) as ei:
        st.start_teleop(TeleopRequest())
    assert ei.value.code == "motor_hot"


def test_overheat_status_bit_cuts_torque_at_once(connected: Station) -> None:
    st = connected
    world = get_world("mock://follower")
    st.start_teleop(TeleopRequest(fps=30))
    time.sleep(0.3)
    world.record_calls = True
    world.inject("wrist_flex", status_bits=["overheat"])
    wait_for(lambda: st.owner.state == "estopped", 3)
    assert not world.any_torque()
    assert st.owner.reason == "thermal"


def test_leader_critical_stops_session_keeps_follower_held(connected: Station) -> None:
    st = connected
    st.start_teleop(TeleopRequest(fps=30))
    time.sleep(0.3)
    get_world("mock://leader").inject("shoulder_pan", temp_c=67.0)
    wait_for(lambda: st.owner.state == "estopped", 4)
    assert st.owner.session is None
    assert get_world("mock://follower").any_torque()  # the leader has no torque to cut


def test_critical_with_rest_pose_parks_before_torque_off(connected: Station) -> None:
    st = connected
    st.owner.call("set_rest_pose")
    st.start_teleop(TeleopRequest(fps=30))
    time.sleep(0.3)
    get_world("mock://follower").inject("elbow_flex", temp_c=66.0)
    wait_for(lambda: st.owner.state == "estopped", 5)
    crit = [a for a in st.owner.alerts.values() if a.message_key == "motor.critical.stopped"]
    assert crit and crit[0].params["parked"] is True and crit[0].params["torque_off"] is True


def test_bus_disconnect_goes_to_error(connected: Station) -> None:
    st = connected
    st.start_teleop(TeleopRequest(fps=30))
    get_world("mock://follower").inject(disconnect_after_s=0.2)
    wait_for(lambda: st.owner.state == "error", 4)
    assert st.owner.reason == "bus_lost"


def test_telemetry_failure_is_not_fatal(connected: Station, events: Events) -> None:
    st = connected
    get_world("mock://follower").inject(fail_registers={"present_current"})
    st.start_teleop(TeleopRequest(fps=30))
    time.sleep(4.0)
    assert st.owner.state == "teleop"
    st.owner.call("control", action="stop")
    assert any(a["kind"] == "telemetry_degraded" for a in events.of("alert"))


def test_start_refused_when_busy_or_uncalibrated(station: Station) -> None:
    station.profiles.put(mock_profile())
    station.owner.call("connect", robot_id="desk", timeout=30)
    with pytest.raises(StationError) as ei:
        station.start_teleop(TeleopRequest())
    assert ei.value.code == "not_calibrated"
    with pytest.raises(StationError) as ei:
        station.owner.call("connect", robot_id="desk")
    assert ei.value.code == "busy"


def test_leader_far_is_refused(connected: Station) -> None:
    get_world("mock://leader").hand = lambda m, t: 2048.0 + 600.0  # ~53 degrees away
    time.sleep(0.2)
    with pytest.raises(StationError) as ei:
        connected.start_teleop(TeleopRequest())
    assert ei.value.code == "leader_far"


def test_deadman_without_heartbeat_estops_run(connected: Station, tmp_path) -> None:  # type: ignore[no-untyped-def]
    from hibiscus_station.mock.policy import make_dummy_act
    from hibiscus_station.models.importer import import_dir
    from hibiscus_station.station import RunRequest

    st = connected
    src = make_dummy_act(tmp_path / "act" / "pretrained_model", {"wrist": (96, 128)})
    entry = import_dir(st.registry, src, st.paths.staging, [tmp_path])
    st.jobs.wait(st.load_model(entry.key, "cpu").id)
    with Heartbeat(st):
        st.start_run(RunRequest(model=entry.key, countdown_s=0.2, episode_time_s=5))
        time.sleep(0.5)
    wait_for(lambda: st.owner.state == "estopped", 3)
    assert st.owner.reason == "ui_lost"
