"""Pairing, upload and pull against the CLI's contract-checked FakeHibiscus, and the whole flow (spec §9.2).

detect -> calibrate -> cameras -> teleop -> record N episodes -> dataset valid with LeRobotDataset ->
upload to a fake Hibiscus server -> pull the bundle -> run the inference loop with a tiny ACT policy.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import respx
from conftest import Heartbeat, calibrate, gentle_hand, mock_profile, wait_for

from hibiscus_station.errors import StationError
from hibiscus_station.hw import ports
from hibiscus_station.mock import get_world
from hibiscus_station.mock.policy import bundle_files, make_bundle
from hibiscus_station.station import RecordRequest, RunRequest, Station, TeleopRequest, UploadRequest


@pytest.fixture
def fake(tmp_path: Path) -> Iterator[Any]:
    from fake_server import BASE, FakeHibiscus

    server = FakeHibiscus(tmp_path / "server")
    with respx.mock(assert_all_called=False, assert_all_mocked=True) as router:
        # The public login configuration (contract v0.1.1 getAuthConfig, no credentials): the identity
        # probe of pairing (QD-40). The vendored fake has no handler for it.
        router.get(f"{BASE}/auth/config").respond(
            200,
            json={
                "turnstile_site_key": None,
                "email_delivery_enabled": False,
                "password_min_length": 12,
                "supported_locales": ["vi", "en"],
            },
        )
        server.mount(router)
        yield server


def _pair(st: Station, fake: Any) -> None:
    from fake_server import BASE, TOKEN

    view = st.server.pair(BASE.removesuffix("/api/v1"), TOKEN)
    assert view["paired"] and view["workspace"] == "lab"
    assert "x" * 10 not in str(view)  # the PAT never leaves the server side


def test_pair_and_missing_scope(station: Station, fake: Any) -> None:
    _pair(station, fake)
    assert station.server.view()["token_prefix"].startswith("hbp_AbCd")
    assert station.server.runs() == []  # runs:write implies runs:read
    station.server.data["scopes"] = ["datasets:write", "models:read"]
    with pytest.raises(StationError) as ei:
        station.server.runs()
    assert ei.value.code == "not_paired" and ei.value.params["missing_scope"] == "runs:read"
    station.server.unpair()
    assert not station.server.paired


def test_pair_rejects_non_pat(station: Station, fake: Any) -> None:
    with pytest.raises(StationError) as ei:
        station.server.pair("https://hibiscus.test", "not-a-token")
    assert ei.value.code == "validation_failed"


def test_upload_refuses_unfinalized(station: Station, fake: Any, tmp_path: Path) -> None:
    _pair(station, fake)
    root = station.paths.datasets / "broken" / "meta"
    root.mkdir(parents=True)
    (root / "info.json").write_text('{"codebase_version": "v3.0", "total_episodes": 0, "features": {}}')
    job = station.upload("broken", UploadRequest(new_dataset_name="broken"))
    station.jobs.wait(job.id)
    assert job.status == "failed" and job.error is not None
    assert job.error["code"] == "dataset_not_finalized"


def test_detect_by_motion_finds_the_moving_arm() -> None:
    get_world("mock://leader").hand = lambda m, t: 2048 + 400 * (t % 1.0)
    get_world("mock://follower").hand = None
    found = ports.detect_motion(
        ["mock://follower", "mock://leader"], lambda p: ports.read_raw_positions(p, mock=True), timeout_s=5
    )
    assert found == "mock://leader"


def test_full_flow_without_hardware(station: Station, fake: Any, tmp_path: Path) -> None:
    from lerobot.datasets import LeRobotDataset

    st = station
    # detect (cameras) + profile
    from hibiscus_station.mock.camera import MockCamera

    assert len(MockCamera.find_cameras()) == 2
    profile = mock_profile(cameras=2)
    get_world("mock://leader").hand = gentle_hand
    st.profiles.put(profile)
    st.owner.call("connect", robot_id=profile.id, timeout=30)
    assert {c["name"] for c in st.status()["cameras"] if c["streaming"]} == {"wrist", "front"}
    # calibrate both arms
    calibrate(st, "follower")
    calibrate(st, "leader")
    get_world("mock://follower").place_all(2048)
    time.sleep(0.15)
    # teleop
    st.start_teleop(TeleopRequest(fps=20))
    time.sleep(1.0)
    st.owner.call("control", action="stop")
    # record N episodes
    st.start_record(
        RecordRequest(
            dataset="flow",
            task="Pick the red cube",
            num_episodes=2,
            episode_time_s=0.8,
            reset_time_s=0.2,
            fps=15,
            countdown_s=0.2,
        )
    )
    wait_for(lambda: st.owner.state == "idle" and st.owner.last_session_summary is not None, 20)
    ds = LeRobotDataset("local/flow", root=st.paths.datasets / "flow")
    assert ds.num_episodes == 2 and ds.num_frames == 2 * 12
    assert set(ds.meta.camera_keys) == {"observation.images.wrist", "observation.images.front"}
    item = ds[0]
    assert tuple(item["observation.images.front"].shape) == (3, 96, 128)
    # upload to the fake Hibiscus server
    _pair(st, fake)
    job = st.upload("flow", UploadRequest(new_dataset_name="flow"))
    st.jobs.wait(job.id, timeout=60)
    assert job.status == "succeeded", job.error
    assert job.result and job.result["version"] == 1
    assert "/runs/new?version=" in job.result["train_url"]
    uploaded = list(fake.versions.values())
    assert uploaded and fake.datasets
    # the sidecar was not uploaded: the tar holds only the LeRobot root
    import tarfile

    obj = fake.assembled(next(iter(fake.uploads)))
    with tarfile.open(obj) as tf:
        names = tf.getnames()
    assert any(n.endswith("meta/info.json") for n in names) and not any(".hibiscus" in n for n in names)
    # pull the trained bundle from the server
    bundle = make_bundle(tmp_path / "trained", "flow_act-r1-step10", {"wrist": (96, 128), "front": (96, 128)})
    model = fake.add_model(bundle_files(bundle), bundle_name="flow_act-r1-step10")
    assert any(m["id"] == model["id"] for m in st.server.models())
    pull = st.pull_model(model["id"])
    st.jobs.wait(pull.id, timeout=60)
    assert pull.status == "succeeded", pull.error
    key = pull.result["model"]  # type: ignore[index]
    entry = st.registry.get(key)
    assert entry is not None and entry.source == "server" and entry.verified
    report = st.compat(key, profile.id)
    assert report["ok"], report
    # run the inference loop for a few steps
    load = st.load_model(key, "cpu")
    st.jobs.wait(load.id, timeout=60)
    assert load.status == "succeeded", load.error
    with Heartbeat(st):
        st.start_run(RunRequest(model=key, countdown_s=0.1, episode_time_s=0.5, fps=20))
        wait_for(lambda: st.owner.state == "idle", 10)
    summary = st.owner.last_session_summary
    assert summary is not None and summary["outcome"] == "completed"
    assert summary["summary"]["inferences"] >= 8
