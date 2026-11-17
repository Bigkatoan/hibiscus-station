"""Field report 0.2.1 (Windows, real SO-101): Station "saw" the arm but nothing moved it, while LeLab
did. The ``-v`` log showed ``demo_follower MockFollower read state``: the active profile was the demo
profile an earlier ``--mock`` run had left in ``~/.hibiscus/station``, so every command drove the
simulated arm."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from hibiscus_station.errors import StationError
from hibiscus_station.profiles import FollowerProfile, ProfileStore, RobotProfile
from hibiscus_station.station import Station, demo_profile


def _leftover_demo(home: Path) -> None:
    """What ``hibiscus-station --mock`` 0.2.1 left behind in the real data dir."""
    store = ProfileStore(home / "robots.yaml")
    store.put(demo_profile())
    store.set_active("demo_so101")


def test_real_run_never_drives_a_leftover_demo_profile(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    home = tmp_path / "home"
    _leftover_demo(home)
    with caplog.at_level(logging.INFO):
        st = Station(home, mock=False, cal_root=tmp_path / "cal")
        st.start()
    try:
        assert st.profiles.active is None  # no longer active...
        assert st.profiles.get("demo_so101") is not None  # ...but the user's data is kept
        with pytest.raises(StationError) as ei:
            st.owner.call("connect", robot_id="demo_so101", timeout=10)
        assert ei.value.code == "demo_profile"
        assert "SIMULATED" in str(ei.value) and "New robot" in str(ei.value)
        assert st.owner.state == "disconnected"
        assert any(
            "real hardware mode" in r.getMessage() and "demo profiles: demo_so101" in r.getMessage()
            for r in caplog.records
        )
    finally:
        st.shutdown()


def test_a_real_profile_becomes_active_instead(tmp_path: Path) -> None:
    home = tmp_path / "home"
    _leftover_demo(home)
    ProfileStore(home / "robots.yaml").put(
        RobotProfile(id="desk", follower=FollowerProfile(port="COM3", calibration_id="desk_follower"))
    )
    store = ProfileStore(home / "robots.yaml")
    store.set_active("demo_so101")
    st = Station(home, mock=False, cal_root=tmp_path / "cal")
    assert st.profiles.active == "desk"
    assert "active profile desk (so101_follower on COM3" in st.describe()
    assert "real arms" in st.describe()


def test_mock_mode_still_connects_the_demo_and_flags_it(tmp_path: Path) -> None:
    st = Station(tmp_path / "home", mock=True, cal_root=tmp_path / "cal")
    st.start()
    try:
        s = st.owner.call("connect", robot_id="demo_so101", timeout=30)
        assert s["robot"]["mock"] is True
        assert "MOCK (demo) mode" in st.describe() and "SIMULATED arms" in st.describe()
    finally:
        st.shutdown()


def test_mock_runs_keep_their_data_apart(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from hibiscus_station.cli import demo_home
    from hibiscus_station.settings import station_home

    monkeypatch.delenv("HIBISCUS_STATION_HOME", raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    assert demo_home() == tmp_path / ".hibiscus" / "station-demo"
    assert demo_home() != station_home()
    # QD-8: an explicit home (Docker: /data) keeps the demo inside it, never next to it
    monkeypatch.setenv("HIBISCUS_STATION_HOME", str(tmp_path / "station"))
    assert demo_home() == tmp_path / "station" / "demo"
    assert demo_home() != station_home()


def test_doctor_flags_a_demo_profile_while_a_real_port_is_present(tmp_path: Path) -> None:
    from hibiscus_station import doctor

    report = {
        "profiles": {
            "active": "demo_so101",
            "robots": [
                {
                    "id": "demo_so101",
                    "mock": True,
                    "arms": {"follower": {"calibration_id": "demo_follower", "file_exists": False}},
                }
            ],
        },
        "ports": [{"device": "COM3", "vid_pid": "1a86:55d3", "open_by": []}],
        "calibrations": [{"arm": "follower", "id": "my_follower"}],
        "running": None,
        "arms": [],
    }
    w = doctor.warnings(report)
    assert w[0].startswith("MOCK PROFILE ACTIVE: 'demo_so101' drives SIMULATED arms")
    assert "COM3" in w[0]
    assert any("no profile for a real arm" in x for x in w)
