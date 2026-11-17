"""The UI's cached view equals a fresh GET /status after every scripted step (QC 0.2.9 QD-23).

The web UI never polls: it keeps the last ``state`` message as its status and the active alerts
from ``alert`` messages (``web/src/station/ws/store.ts``). Any change the Station makes without
an event stays wrong on every open page until a reload (QD-23: the thermal-stop banner stayed after
the motor cooled and the e-stop was reset). ``UiMirror`` replays the owner's events exactly as the
store does, and each step compares it with ``Station.status()``.
"""

from __future__ import annotations

import time
from types import SimpleNamespace
from typing import Any

import pytest
from conftest import connect_calibrated, wait_for
from fastapi.testclient import TestClient

from hibiscus_station.mock import get_world
from hibiscus_station.station import Station, TeleopRequest


class UiMirror:
    """The web store's reducer for ``state`` / ``hello`` and ``alert`` (store.ts ``handle``)."""

    def __init__(self, hello: dict[str, Any]) -> None:
        self.status: dict[str, Any] = hello
        self.alerts: dict[str, dict[str, Any]] = {a["id"]: a for a in hello["alerts"]}

    def __call__(self, kind: str, payload: dict[str, Any]) -> None:
        if kind == "state":
            self.status = payload
        elif kind == "alert":
            if payload["active"]:
                self.alerts[payload["id"]] = payload
            else:
                self.alerts.pop(payload["id"], None)


def view(status: dict[str, Any], alerts: list[dict[str, Any]]) -> dict[str, Any]:
    """What the UI shows from the status and alerts (volatile telemetry left out)."""
    robot = status["robot"]
    return {
        "state": status["state"],
        "reason": status["reason"],
        "detail": status["detail"],
        "connected": robot["connected"] if robot else None,
        "torque": robot["follower_torque"] if robot else None,
        "calibrated": {a: v["calibrated"] for a, v in robot["arms"].items()} if robot else None,
        "issues": {a: v["issue"] for a, v in robot["arms"].items()} if robot else None,
        "session": status["session"] is not None,
        "interrupted": status["interrupted"],
        "lost": status["lost"] is not None,
        "loaded_model": status["loaded_model"],
        "paired": status["server"]["paired"],
        "alerts": sorted((a["id"], a["level"]) for a in alerts),
    }


def matches(station: Station, ui: UiMirror, step: str, timeout: float = 3.0) -> None:
    def same() -> bool:
        return view(ui.status, list(ui.alerts.values())) == view(station.status(), station.status()["alerts"])

    try:
        wait_for(same, timeout)
    except AssertionError:
        fresh = view(station.status(), station.status()["alerts"])
        cached = view(ui.status, list(ui.alerts.values()))
        diff = {k: (cached[k], fresh[k]) for k in fresh if cached[k] != fresh[k]}
        raise AssertionError(f"after {step}: the UI keeps {diff} (cached, fresh GET /status)") from None


@pytest.fixture
def ui(station: Station) -> UiMirror:
    mirror = UiMirror(station.status())
    station.owner.add_listener(mirror)
    return mirror


def _thermal_stop_and_cool(st: Station) -> None:
    world = get_world("mock://follower")
    st.start_teleop(TeleopRequest(fps=30))
    time.sleep(0.3)
    world.inject("elbow_flex", temp_c=66.0)
    wait_for(lambda: st.owner.state == "estopped", 5)
    world.inject("elbow_flex", temp_c=40.0)
    wait_for(lambda: st.owner.guard.temps.get(("follower", "elbow_flex"), 99) < 45, 4)
    wait_for(lambda: not st.owner.guard.any_motor_at_or_above_hot(), 4)


def test_thermal_stop_cool_reset_drops_the_critical_alert(station: Station, ui: UiMirror) -> None:
    """QD-23: the reset removes the critical alert; every open page must hear it at once."""
    connect_calibrated(station)
    matches(station, ui, "connect + calibrate")
    _thermal_stop_and_cool(station)
    assert any(a["level"] == "critical" for a in ui.alerts.values())
    matches(station, ui, "thermal stop, cooled")
    station.owner.call("estop_reset")
    assert not any(a["level"] == "critical" for a in station.status()["alerts"])
    matches(station, ui, "e-stop reset after cooling")
    station.start_teleop(TeleopRequest(fps=30))
    time.sleep(0.3)
    matches(station, ui, "teleop again")
    station.owner.call("control", action="stop")
    matches(station, ui, "stop")


def test_disconnect_drops_every_alert_on_open_pages(station: Station, ui: UiMirror) -> None:
    """QD-23 (same cause): disconnect cleared ``alerts`` without one event."""
    connect_calibrated(station)
    _thermal_stop_and_cool(station)
    get_world("mock://follower").inject("gripper", temp_c=52.0)  # a warm motor: a warn alert
    wait_for(lambda: len(station.status()["alerts"]) >= 2, 4)
    matches(station, ui, "thermal stop + warm gripper")
    station.owner.call("disconnect")
    assert station.status()["alerts"] == []
    matches(station, ui, "disconnect")


def test_device_lost_then_reconnect_keeps_no_alert_of_the_gone_bus(station: Station, ui: UiMirror) -> None:
    """Class sweep (QD-23): closing the devices forgets every motor level (``guard.reset_arm``),
    so a warn alert raised before an unplug could never clear again: after the reconnect the motor
    reads cool and nothing ever says so. The Station and the page kept "gripper 52 °C" for good."""
    connect_calibrated(station)
    world = get_world("mock://follower")
    world.inject("gripper", temp_c=52.0)
    wait_for(lambda: any(a["motor"] == "gripper" for a in station.status()["alerts"]), 4)
    station.start_teleop(TeleopRequest(fps=30))
    time.sleep(0.3)
    world.inject(disconnect_after_s=0.1)
    wait_for(lambda: station.owner.state == "error", 4)
    matches(station, ui, "device lost")
    assert not any(a["motor"] == "gripper" for a in station.status()["alerts"])
    world.faults.disconnect_at = None  # plugged back in
    world.inject("gripper", temp_c=30.0)
    station.reconnect(timeout_s=2)
    wait_for(lambda: station.owner.state == "idle", 5)
    time.sleep(1.0)  # a few telemetry rounds
    assert not any(a["motor"] == "gripper" for a in station.status()["alerts"])
    matches(station, ui, "reconnect")
