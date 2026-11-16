"""Leader / follower identification (0.2.6 field report: the first arm that moved became the
follower). The role is the slot the user is filling, never the move order; the supply voltage is
offered as a hint only."""

from __future__ import annotations

from typing import Any

import pytest
from conftest import mock_profile

from hibiscus_station.hw import ports
from hibiscus_station.mock import get_world
from hibiscus_station.station import Station


@pytest.mark.parametrize(
    ("volts", "hint"),
    [(None, None), (4.9, "leader"), (5.2, "leader"), (6.2, None), (7.4, "follower"), (12.1, "follower")],
)
def test_role_hint_from_voltage(volts: float | None, hint: str | None) -> None:
    assert ports.role_hint(volts) == hint


def test_probe_reads_voltage_model_and_firmware_read_only() -> None:
    lead = ports.probe_arm("mock://leader", mock=True)
    fol = ports.probe_arm("mock://follower", mock=True)
    assert lead["voltage_v"] == 5.0 and lead["role_hint"] == "leader" and lead["motors"] == 6
    assert fol["voltage_v"] == 7.4 and fol["role_hint"] == "follower"
    assert fol["model_number"] == 777 and fol["firmware"] is not None
    assert not get_world("mock://follower").any_torque()


def test_probe_of_a_dead_port_reports_an_error() -> None:
    out = ports.probe_arm("/dev/ttyNOPE7")
    assert out["error"] and out["voltage_v"] is None and out["role_hint"] is None


def test_motion_detection_skips_the_port_given_to_the_other_arm(
    client: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Identifying the leader while the user (wrongly) moves the follower: the follower's port is
    already in the follower slot, so it is excluded and the moving-arm search times out instead of
    swapping roles."""
    rows = [
        {
            "device": d,
            "stable_path": None,
            "vid_pid": "1a86:55d3",
            "serial_number": None,
            "description": "",
            "in_use_by": None,
        }
        for d in ("mock://follower", "mock://leader")
    ]
    monkeypatch.setattr(ports, "list_ports", lambda in_use=None, usb_only=True: rows)
    seen: list[list[str]] = []

    def fake_detect(candidates: list[str], read: Any, timeout_s: float = 10.0) -> str | None:
        seen.append(list(candidates))
        return candidates[0] if candidates else None

    monkeypatch.setattr(ports, "detect_motion", fake_detect)
    r = client.post(
        "/api/v1/ports/detect", json={"method": "motion", "exclude": ["mock://follower"], "timeout_s": 1}
    )
    assert r.status_code == 200, r.text
    assert seen[-1] == ["mock://leader"]
    assert r.json()["port"]["device"] == "mock://leader"


def test_probe_endpoint_hints_roles_and_skips_ports_in_use(client: Any, station: Station) -> None:
    r = client.post("/api/v1/ports/probe", json={"ports": ["mock://leader", "mock://follower"]})
    assert r.status_code == 200, r.text
    by = {p["device"]: p for p in r.json()["ports"]}
    assert by["mock://leader"]["role_hint"] == "leader" and by["mock://leader"]["voltage_v"] == 5.0
    assert by["mock://follower"]["role_hint"] == "follower"
    station.profiles.put(mock_profile(cameras=0))
    station.owner.call("connect", robot_id="desk", timeout=30)
    r = client.post("/api/v1/ports/probe", json={"ports": ["mock://follower"]})
    p = r.json()["ports"][0]
    assert p["in_use_by"] and p["voltage_v"] is None  # never opened while a robot holds it


def test_calibration_ids_stay_with_the_role_slot() -> None:
    """Swapping ports in the form keeps each calibration id on its role (the UI swaps ports only);
    the profile is the contract: follower id <-> follower port."""
    p = mock_profile(cameras=0)
    assert p.leader is not None
    swapped = p.model_copy(
        update={
            "follower": p.follower.model_copy(update={"port": p.leader.port}),
            "leader": p.leader.model_copy(update={"port": p.follower.port}),
        }
    )
    assert swapped.follower.calibration_id == "desk_follower" and swapped.follower.port == "mock://leader"
    assert swapped.leader is not None and swapped.leader.calibration_id == "desk_leader"
