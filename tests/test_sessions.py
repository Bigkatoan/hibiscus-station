"""Session flows (spec §9.2): lerobot data correctness, replay, run with a tiny ACT policy (R2)."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from conftest import Events, Heartbeat, connect_calibrated, mock_profile, wait_for

from hibiscus_station.data import datasets as catalog
from hibiscus_station.data.sidecar import episode_file, read_lines
from hibiscus_station.errors import StationError
from hibiscus_station.hw.cameras import unpack_frame
from hibiscus_station.mock import decode_counter, get_world
from hibiscus_station.mock.policy import make_dummy_act
from hibiscus_station.models.importer import import_dir
from hibiscus_station.station import RecordRequest, ReplayRequest, RunRequest, Station

FPS = 15


def _record(st: Station, **kw: object) -> None:
    req = RecordRequest(
        dataset=str(kw.pop("dataset", "pick")),
        task="Pick the red cube",
        fps=FPS,
        countdown_s=float(kw.pop("countdown_s", 0.3)),  # type: ignore[arg-type]
        **kw,  # type: ignore[arg-type]
    )
    st.start_record(req)


def _phase(st: Station) -> str | None:
    s = st.owner.session
    return s.episode.phase if s is not None else None


def test_record_next_rerecord_timeout(connected: Station) -> None:
    from hibiscus.recording import check_recording
    from lerobot.datasets import LeRobotDataset

    st = connected
    _record(st, num_episodes=3, episode_time_s=1.0, reset_time_s=0.4, on_timeout="save")
    # episode 0: ends by timeout (saved by default)
    wait_for(lambda: _phase(st) == "reset", 6)
    # rerecord during reset discards the pending episode 0
    st.owner.call("control", action="rerecord")
    wait_for(lambda: _phase(st) == "episode", 4)
    time.sleep(0.5)
    st.owner.call("control", action="next")  # episode ended early, kept
    wait_for(lambda: _phase(st) == "episode" and st.owner.session.episode.saved == 1, 8)  # type: ignore[union-attr]
    # wait for the remaining two timeouts
    wait_for(lambda: st.owner.state == "idle", 20)
    summary = st.owner.last_session_summary
    assert summary is not None and summary["outcome"] == "completed"
    root = st.paths.datasets / "pick"
    ds = LeRobotDataset("local/pick", root=root)
    assert ds.num_episodes == 3
    lengths = [int(ds.meta.episodes[i]["length"]) for i in range(3)]
    assert lengths[1] == FPS * 1 and lengths[2] == FPS * 1, lengths  # timeouts: fps x duration
    assert 3 <= lengths[0] <= FPS  # the "next" one
    st_rec = check_recording(root)
    assert st_rec.complete, st_rec.reasons
    # camera frames of an episode are consecutive camera frames (one per tick at 15 fps of a 30 fps cam)
    frames = [
        ds[i]["observation.images.wrist"]
        for i in range(
            int(ds.meta.episodes[1]["dataset_from_index"]), int(ds.meta.episodes[1]["dataset_to_index"])
        )
    ]
    counters = [decode_counter(f.numpy()) for f in frames]
    diffs = np.diff(counters)
    assert (diffs > 0).all() and (diffs <= 4).all(), counters
    # sidecars: one per saved episode, nothing for the discarded one, never inside the dataset root
    for i in range(3):
        lines = read_lines(episode_file(st.paths.datasets, "pick", i))
        assert lines and all("frame_index" in ln for ln in lines)
        assert {"temp_c", "voltage_v", "current_a", "load_pct"} <= set(lines[0])
    assert not episode_file(st.paths.datasets, "pick", 3).exists()
    assert not list(root.rglob("*.jsonl.gz"))
    detail = catalog.detail(st.paths.datasets, "pick")
    assert detail["episodes"] == 3 and detail["finalized"]
    assert detail["episode_list"][0]["max_temp_c"]["follower"]


def test_record_timeout_discard_and_sidecar_line_count(connected: Station) -> None:
    st = connected
    _record(st, dataset="disc", num_episodes=1, episode_time_s=0.8, reset_time_s=0.2, on_timeout="discard")
    wait_for(lambda: _phase(st) == "episode", 4)
    wait_for(lambda: _phase(st) == "reset", 4)  # timeout -> discarded, re-record
    assert st.owner.session.discarded == 1  # type: ignore[union-attr]
    wait_for(lambda: _phase(st) == "episode", 4)
    time.sleep(0.3)
    st.owner.call("control", action="next")
    wait_for(lambda: st.owner.state == "idle", 10)
    lines = read_lines(episode_file(st.paths.datasets, "disc", 0))
    assert lines
    # every telemetry read logged during the episode is in the sidecar (one line per read)
    reads_in_episode = {(ln["tick"], ln["arm"], ln["group"]) for ln in lines}
    assert len(reads_in_episode) == len(lines)


def test_record_append_and_incompatible(connected: Station) -> None:
    st = connected
    _record(st, dataset="app", num_episodes=1, episode_time_s=0.5, reset_time_s=0.1)
    wait_for(lambda: st.owner.state == "idle" and st.owner.last_session_summary is not None, 10)
    _record(st, dataset="app", mode="append", num_episodes=1, episode_time_s=0.5, reset_time_s=0.1)
    wait_for(lambda: st.owner.state == "idle" and st.owner.last_session_summary["summary"]["saved"] == 1, 10)  # type: ignore[index]
    assert catalog.summary(st.paths.datasets, "app")["episodes"] == 2  # type: ignore[index]
    with pytest.raises(StationError) as ei:
        st.start_record(RecordRequest(dataset="app", mode="append", task="x", fps=FPS + 1))
    assert ei.value.code == "dataset_incompatible"
    with pytest.raises(StationError) as ei:
        st.start_record(RecordRequest(dataset="app", task="x", fps=FPS))
    assert ei.value.code == "dataset_exists"


def test_estop_during_recording_finalizes_dataset(connected: Station) -> None:
    from hibiscus.recording import check_recording

    st = connected
    _record(st, dataset="halt", num_episodes=3, episode_time_s=0.6, reset_time_s=2.0)
    wait_for(lambda: _phase(st) == "reset", 6)
    st.owner.press_estop("user")
    wait_for(lambda: st.owner.state == "estopped", 6)
    root = st.paths.datasets / "halt"
    # the buffered episode is saved and the dataset finalized off the control loop (0.2.9)
    wait_for(lambda: check_recording(root).complete, 20)
    assert catalog.summary(st.paths.datasets, "halt")["episodes"] == 1  # type: ignore[index]
    st.owner.call("estop_reset")


def test_a_session_that_keeps_no_episode_says_so(connected: Station) -> None:
    """QC 0.2.9 QD-12. An e-stop in episode 1 drops the episode in progress: the summary counts it
    as discarded and says the new, empty dataset was removed (there is nothing to upload). A Stop in
    the countdown records nothing and also leaves no dataset behind."""
    st = connected
    _record(st, dataset="halt0", num_episodes=2, episode_time_s=5.0, reset_time_s=1.0)
    wait_for(lambda: _phase(st) == "episode" and st.owner.session.recorder.frames_in_episode > 3, 6)  # type: ignore[union-attr]
    st.owner.press_estop("user")
    wait_for(lambda: st.owner.state == "estopped" and st.owner.last_session_summary is not None, 6)
    end = st.owner.last_session_summary
    assert end is not None and end["outcome"] == "user"
    assert end["summary"]["saved"] == 0 and end["summary"]["discarded"] == 1, end["summary"]
    assert end["summary"]["dropped_in_progress"] is True
    assert end["summary"]["dataset_kept"] is False
    assert not (st.paths.datasets / "halt0").exists()
    st.owner.call("estop_reset")

    _record(st, dataset="halt1", num_episodes=1, countdown_s=5.0)
    wait_for(lambda: _phase(st) == "countdown", 3)
    st.owner.call("control", action="stop")
    wait_for(
        lambda: (
            st.owner.state == "idle" and st.owner.last_session_summary["summary"].get("dataset") == "halt1"
        ),
        6,
    )  # type: ignore[index]
    end = st.owner.last_session_summary
    assert end["outcome"] == "stopped"
    assert end["summary"]["saved"] == 0 and end["summary"]["discarded"] == 0
    assert end["summary"]["dropped_in_progress"] is False and end["summary"]["dataset_kept"] is False


def test_camera_stale_pauses_then_stops_recording(connected: Station, events: Events) -> None:
    st = connected
    st.settings.safety.camera_lost_stop_s = 1.0
    _record(st, dataset="stale", num_episodes=1, episode_time_s=10, reset_time_s=0.1)
    wait_for(lambda: _phase(st) == "episode", 4)
    time.sleep(0.3)
    st.hub.camera("wrist").stall(True)
    time.sleep(0.6)
    frames_paused = st.owner.session.recorder.frames_in_episode  # type: ignore[union-attr]
    time.sleep(0.2)
    s = st.owner.session
    if s is not None:
        assert s.recorder.frames_in_episode == frames_paused  # type: ignore[union-attr]
    wait_for(lambda: st.owner.state == "idle", 6)
    assert st.owner.last_session_summary["outcome"] == "camera_lost"  # type: ignore[index]
    assert any(a["kind"] == "camera" for a in events.of("alert"))
    st.hub.camera("wrist").stall(False)


def test_replay_runs_and_stops_within_a_tick(connected: Station) -> None:
    st = connected
    _record(st, dataset="rep", num_episodes=1, episode_time_s=1.0, reset_time_s=0.1)
    wait_for(lambda: st.owner.state == "idle" and st.owner.last_session_summary is not None, 10)
    st.settings.safety.deadman_replay = False
    st.start_replay(ReplayRequest(dataset="rep", episode=0))
    assert st.owner.state == "replaying"
    time.sleep(0.6)
    world = get_world("mock://follower")
    world.record_calls = True
    t = time.monotonic()
    st.owner.call("control", action="stop")
    assert st.owner.state == "idle"
    late = [w for w, _ in world.goal_writes() if w > t + 1 / FPS + 0.05]
    assert not late
    st.start_replay(ReplayRequest(dataset="rep", episode=0))
    wait_for(lambda: st.owner.state == "idle", 6)
    assert st.owner.last_session_summary["outcome"] == "completed"  # type: ignore[index]


def _dummy_model(st: Station, tmp_path: Path, cams: dict[str, tuple[int, int]]) -> str:
    src = make_dummy_act(tmp_path / "act_dummy" / "pretrained_model", cams)
    entry = import_dir(st.registry, src, st.paths.staging, [tmp_path])
    job = st.load_model(entry.key, "cpu")
    st.jobs.wait(job.id)
    assert st.jobs.get(job.id).status == "succeeded", st.jobs.get(job.id).error
    return entry.key


def test_run_policy_preview_is_policy_input(tmp_path: Path, station: Station, events: Events) -> None:
    from hibiscus_station.hw.cameras import VideoClient

    st = station
    connect_calibrated(st, mock_profile(cameras=2))
    key = _dummy_model(st, tmp_path, {"wrist": (96, 128), "front": (96, 128)})
    client = VideoClient()
    client.subscribe(["wrist", "front"], 160, 30)
    st.encoder.add(client)
    with Heartbeat(st):
        st.start_run(
            RunRequest(
                model=key, countdown_s=0.2, episode_time_s=0.8, num_episodes=2, reset_time_s=0.3, record=True
            )
        )
        matched = 0
        deadline = time.monotonic() + 6
        while time.monotonic() < deadline and st.owner.session is not None:
            s = st.owner.session
            got, _ = client.take()
            for msg in got.values():
                header, jpeg = unpack_frame(msg)
                if header["tick"] < 0 or not header["policy_input"]:
                    continue
                import cv2

                img = cv2.cvtColor(
                    cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR), cv2.COLOR_BGR2RGB
                )
                if s is not None and header["tick"] == s.last_policy_tick:  # type: ignore[attr-defined]
                    policy_frame = s.last_policy_frames[header["cam"]]  # type: ignore[attr-defined]
                    assert decode_counter(img) == decode_counter(policy_frame)
                    assert (header["src_w"] == 128 and header["w"] == 160) or header["w"] == 128
                    matched += 1
            time.sleep(0.01)
        wait_for(lambda: st.owner.state == "idle", 8)
    st.encoder.remove(client)
    assert matched >= 3
    summary = st.owner.last_session_summary
    assert summary is not None and summary["outcome"] == "completed", summary
    assert summary["summary"]["inferences"] >= 2 * 0.8 * 30 - 4
    run = [e for e in events.of("session") if e.get("ended")][-1]
    assert run["summary"]["episodes"] == 2
    # policy.reset() per episode, eval dataset recorded with the eval_ prefix
    ds_name = summary["dataset"]
    assert ds_name.startswith("eval_")
    assert catalog.summary(st.paths.datasets, ds_name)["episodes"] == 2  # type: ignore[index]
    joints = [j for j in events.of("joints") if "action" in j]
    assert joints and "inference_ms_p50" in joints[-1]["loop"]


def test_run_actions_are_clipped_by_safety_filter(tmp_path: Path, connected: Station, events: Events) -> None:
    st = connected
    key = _dummy_model(st, tmp_path, {"wrist": (96, 128)})
    with Heartbeat(st):
        st.start_run(RunRequest(model=key, countdown_s=0.1, episode_time_s=0.6, max_relative_target=0.5))
        wait_for(lambda: st.owner.state == "idle", 6)
    sent = [j for j in events.of("joints") if "sent" in j]
    assert sent
    for j in sent:
        for k, v in j["sent"].items():
            assert abs(v - j["arms"]["follower"][k]) <= 0.5 + 1e-6
    s = [e for e in events.of("session") if e.get("ended")][-1]
    assert s["outcome"] == "completed"


def test_policy_clipping_warning_only_for_runs_and_cleared_at_the_end(
    tmp_path: Path, connected: Station, events: Events, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Release QA: recording with a fast leader showed "the policy is fighting the safety limiter",
    and the warning stayed on screen after the session ended."""
    from hibiscus_station.hw.safety import SafetyFilter

    st = connected
    monkeypatch.setattr(SafetyFilter, "clipped_fraction", lambda self, window_s=2.0: 1.0)

    def clip_alerts() -> list[dict[str, Any]]:
        return [a for a in events.of("alert") if a["kind"] == "policy_clipping"]

    _record(st, dataset="clip", countdown_s=0.0, episode_time_s=2.6, reset_time_s=0.0, num_episodes=1)
    wait_for(lambda: st.owner.state == "idle", 15)
    assert not clip_alerts()  # the leader drives the arm: no "policy" warning

    key = _dummy_model(st, tmp_path, {"wrist": (96, 128)})
    with Heartbeat(st):
        st.start_run(RunRequest(model=key, countdown_s=0.0, episode_time_s=3.0))
        wait_for(lambda: any(a["active"] for a in clip_alerts()), 8)
        wait_for(lambda: st.owner.state == "idle", 10)
    assert clip_alerts()[-1]["active"] is False  # cleared when the run ended


def test_run_refuses_incompatible_or_unloaded(tmp_path: Path, connected: Station) -> None:
    st = connected
    src = make_dummy_act(tmp_path / "big" / "pretrained_model", {"wrist": (480, 640)})
    entry = import_dir(st.registry, src, st.paths.staging, [tmp_path])
    with pytest.raises(StationError) as ei:
        st.start_run(RunRequest(model=entry.key))
    assert ei.value.code == "model_not_loaded"
    st.jobs.wait(st.load_model(entry.key, "cpu").id)
    with pytest.raises(StationError) as ei:
        st.start_run(RunRequest(model=entry.key))
    assert ei.value.code == "model_incompatible"
    assert ei.value.errors and ei.value.errors[0]["code"] == "shape_mismatch"
    assert ei.value.errors[0]["fix"] == {"kind": "set_camera", "camera": "wrist", "width": 640, "height": 480}
