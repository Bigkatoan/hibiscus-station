"""D-26 (customer report 2026-11-20, against F-8 "robot profile: create / edit / delete"): users
could not remove a duplicate robot profile. ``DELETE /robots/{id}`` removes the profile from
robots.yaml only, is refused while the robot is in use, and never makes a demo profile the active
one on real arms.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from conftest import make_station, mock_profile

from hibiscus_station.profiles import FollowerProfile, RobotProfile
from hibiscus_station.station import Station, demo_profile


def _real(rid: str, port: str) -> RobotProfile:
    return RobotProfile(
        id=rid, name=rid, follower=FollowerProfile(type="so101_follower", port=port, calibration_id=rid)
    )


def test_deleting_the_active_real_profile_never_activates_the_demo(tmp_path: Path) -> None:
    st = make_station(tmp_path, mock=False)
    st.profiles.put(demo_profile())
    st.profiles.put(_real("so_101", "COM8"))
    st.profiles.put(_real("so-101-1", "COM7"))
    st.profiles.set_active("so_101")
    st.delete_robot("so_101")
    assert st.profiles.active == "so-101-1"
    st.delete_robot("so-101-1")
    assert st.profiles.active is None  # only the demo is left: never active on real arms
    assert [p.id for p in st.profiles.list()] == ["demo_so101"]
    st.delete_robot("demo_so101")
    assert st.profiles.list() == []
    # a real Station never re-creates the demo; --mock seeds it only into an empty robots.yaml
    assert make_station(tmp_path, mock=False).profiles.list() == []
    assert [p.id for p in make_station(tmp_path, mock=True).profiles.list()] == ["demo_so101"]


def test_deleting_while_connecting_or_waiting_for_a_lost_adapter_is_refused(tmp_path: Path) -> None:
    from hibiscus_station.errors import StationError

    st = make_station(tmp_path, mock=False)
    prof = _real("so_101", "COM8")
    st.profiles.put(prof)
    st.owner.profile = prof
    for state, lost in (("connecting", None), ("error", {"follower": "COM8"})):
        st.owner.state = state
        st.owner.lost = lost
        try:
            st.delete_robot("so_101")
        except StationError as exc:
            assert exc.code == "busy" and exc.params["robot"] == "so_101", exc
        else:
            raise AssertionError(f"deleted while {state}")
    assert st.profiles.get("so_101") is not None


def test_delete_keeps_calibration_and_datasets(connected: Station, client: Any) -> None:
    st = connected
    cal = sorted(Path(st.owner.cal_root).rglob("*.json"))
    assert cal, "calibration files written by connect_calibrated"
    ds = st.paths.datasets / "kept" / "meta"
    ds.mkdir(parents=True)
    (ds / "info.json").write_text("{}", encoding="utf-8")
    r = client.delete("/api/v1/robots/desk")
    assert r.status_code == 409 and r.json()["code"] == "busy"  # connected
    st.owner.call("disconnect", timeout=10)
    assert client.delete("/api/v1/robots/desk").status_code == 204
    assert "desk" not in {p["id"] for p in client.get("/api/v1/robots").json()["robots"]}
    assert all(p.is_file() for p in cal)
    assert (ds / "info.json").is_file()
    # the deleted profile cannot be connected; a new profile with the same calibration id finds
    # its calibration files again
    assert client.post("/api/v1/robots/desk/connect").json()["code"] == "not_found"
    st.profiles.put(mock_profile())
    s = client.post("/api/v1/robots/desk/connect").json()
    assert s["robot"]["arms"]["follower"]["calibrated"], s
