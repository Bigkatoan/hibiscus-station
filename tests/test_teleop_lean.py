"""Teleop's lean tick (0.2.6 field report: "the follower lags behind the leader, LeLab's does not").

The leader -> follower path must carry what LeLab's loop carries (one leader read, one goal write
per tick); follower observation, cameras and telemetry ride along at a lower rate without ever
delaying it, and the relative-target cap must not make the follower chase a normal human move.
"""

from __future__ import annotations

import time
from typing import Any

import pytest
from conftest import Events, wait_for

from hibiscus_station.hw.loop import TELEOP_FPS, LoopStats
from hibiscus_station.hw.owner import LEAN_OBS_HZ
from hibiscus_station.mock import get_world
from hibiscus_station.station import Station, TeleopRequest


def _rates(calls: list[tuple[float, int, str, str]], op: str, reg: str, span: float) -> float:
    return sum(1 for _, _, o, r in calls if o == op and r == reg) / span


def test_teleop_defaults_to_the_fast_lean_loop(connected: Station) -> None:
    st = connected
    assert TeleopRequest().fps == TELEOP_FPS >= 200
    st.start_teleop(TeleopRequest(fps=120))
    assert st.owner.session is not None and st.owner.session.lean
    assert st.owner.safety.max_rel == st.settings.safety.teleop_max_relative_target == 30.0
    time.sleep(0.5)
    fol, lead = get_world("mock://follower"), get_world("mock://leader")
    fol.calls.clear()
    lead.calls.clear()
    fol.record_calls = lead.record_calls = True
    t0 = time.monotonic()
    time.sleep(2.0)
    fol.record_calls = lead.record_calls = False
    span = time.monotonic() - t0
    loop = st.owner.stats.snapshot()
    st.owner.call("control", action="stop")
    leader_hz = _rates(lead.calls, "sync_read", "present_position", span)
    goal_hz = _rates(fol.calls, "sync_write", "goal_position", span)
    obs_hz = _rates(fol.calls, "sync_read", "present_position", span)
    assert leader_hz > 90, leader_hz
    assert goal_hz > 90 and abs(goal_hz - leader_hz) < 5, (goal_hz, leader_hz)
    assert obs_hz <= LEAN_OBS_HZ + 3, obs_hz  # the follower observation is decimated
    # telemetry: a handful of reads per second, never the bulk of the bus
    tel = sum(1 for _, _, o, r in fol.calls + lead.calls if o == "sync_read" and r != "present_position")
    assert tel / span <= 16, tel / span
    assert loop["fps"] > 90
    assert 0 < float(loop["latency_ms_p50"]) < 20, loop
    summary = st.owner.last_session_summary
    assert summary is not None and summary["loop"]["latency_ms_p50"] is not None
    assert summary["loop"]["fps"] > 90


def test_lean_tick_never_reads_telemetry_and_observation_in_one_tick(connected: Station) -> None:
    st = connected
    fol, lead = get_world("mock://follower"), get_world("mock://leader")
    st.start_teleop(TeleopRequest(fps=250))
    time.sleep(0.3)
    marks: list[tuple[float, int]] = []
    orig = st.owner.stats.tick

    def tick(start: float, duration: float, period: float) -> None:
        marks.append((start, st.owner.tick))
        orig(start, duration, period)

    st.owner.stats.tick = tick  # type: ignore[method-assign]
    fol.record_calls = lead.record_calls = True
    time.sleep(2.0)
    fol.record_calls = lead.record_calls = False
    st.owner.call("control", action="stop")
    # bucket every follower/leader read between two tick starts
    starts = [m[0] for m in marks]
    per_tick: dict[int, int] = {}
    import bisect

    for t, _, op, _reg in fol.calls + lead.calls:
        if op != "sync_read":
            continue
        k = bisect.bisect_right(starts, t)
        per_tick[k] = per_tick.get(k, 0) + 1
    # leader read + at most one more transaction (observation OR telemetry)
    assert per_tick and max(per_tick.values()) <= 2, sorted(per_tick.values())[-5:]


def test_estop_in_the_lean_loop_freezes_within_one_tick(connected: Station) -> None:
    st = connected
    world = get_world("mock://follower")
    st.start_teleop(TeleopRequest())
    time.sleep(0.5)
    world.record_calls = True
    t_press = time.monotonic()
    st.owner.press_estop("user")
    wait_for(lambda: st.owner.state == "estopped", 2)
    writes = [t for t, _ in world.goal_writes() if t > t_press]
    assert len(writes) <= 2, writes
    assert all(t - t_press < 0.05 for t in writes)
    assert world.any_torque()


def test_lean_loop_clamps_to_the_calibrated_range(connected: Station) -> None:
    """The range clamp needs no observation: a leader beyond the follower's range is clamped."""
    st = connected
    st.start_teleop(TeleopRequest())
    time.sleep(0.4)
    rng = st.owner.safety.ranges["shoulder_pan.pos"]
    safe, clipped = st.owner.safety.apply(
        {"shoulder_pan.pos": rng[1] + 20.0}, {"shoulder_pan.pos": rng[1] - 5.0}
    )
    st.owner.call("control", action="stop")
    assert safe["shoulder_pan.pos"] == rng[1] and clipped == ["shoulder_pan"]


def test_follower_chasing_the_leader_warns(
    connected: Station, events: Events, monkeypatch: pytest.MonkeyPatch
) -> None:
    from hibiscus_station.hw.safety import SafetyFilter

    st = connected
    monkeypatch.setattr(SafetyFilter, "clipped_fraction", lambda self, window_s=2.0: 0.6)
    monkeypatch.setattr("hibiscus_station.hw.owner.HardwareOwner.session_now", lambda self: 10.0)

    def alerts() -> list[dict[str, Any]]:
        return [a for a in events.of("alert") if a["kind"] == "teleop_clipping"]

    st.start_teleop(TeleopRequest(fps=60))
    wait_for(lambda: any(a["active"] for a in alerts()), 4)
    a = next(x for x in alerts() if x["active"])
    assert a["message_key"] == "safety.leader_clipping" and a["params"]["max_deg"] == 30.0
    st.owner.call("control", action="stop")
    wait_for(lambda: alerts()[-1]["active"] is False, 4)
    assert not [x for x in events.of("alert") if x["kind"] == "policy_clipping"]


def test_loop_stats_latency_adds_half_a_tick() -> None:
    s = LoopStats()
    s.tick(10.0, 0.002, 0.004)
    s.latency_ms(10.004, 2.0)  # 4 ms after the previous tick: +2 ms
    s.tick(10.004, 0.002, 0.004)
    snap = s.snapshot()
    assert snap["latency_ms_p50"] == 4.0
    assert s.session_summary()["latency_ms_p50"] == 4.0


def test_doctor_estimates_teleop_from_the_bus_speed() -> None:
    from hibiscus_station.doctor import teleop_estimate

    fast = teleop_estimate(2.4)
    assert fast is not None and fast["hz"] >= 200 and fast["latency_ms"] < 6 and "warning" not in fast
    slow = teleop_estimate(17.0)  # FTDI's 16 ms latency timer
    assert slow is not None and slow["hz"] < 50 and "latency timer" in slow["warning"]
    assert teleop_estimate(None) is None
