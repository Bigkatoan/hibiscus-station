"""Record and replay trajectories on the mock arms (station-programs.md §3, §10 P1, §11).

Record A and B with the leader, replay at 50 % / 100 %, approach to the start, e-stop mid-replay
within one tick, needs_check after a recalibration, fast replay, poses. Everything goes through the
REST API and the real HardwareOwner loop; every owner event is checked against the WS contract.
"""

from __future__ import annotations

import itertools
import time
from typing import Any

import numpy as np
import pytest
from conftest import Events, Heartbeat, fast_hand, press_estop_frozen_within_one_tick, wait_for

from hibiscus_station.mock import get_world
from hibiscus_station.programs.calibration_ref import calibration_file
from hibiscus_station.programs.schemas import Pose, Poses, Trajectories, Trajectory, TrajectoryDetail
from hibiscus_station.sessions.traj_play import TrajPlaySession
from hibiscus_station.station import Station

API = "/api/v1"


def _phase(st: Station) -> str | None:
    s = st.owner.session
    return s.episode.phase if s is not None else None


def _record(client: Any, st: Station, *, name: str, seconds: float, **kw: Any) -> TrajectoryDetail:
    """Record a take while the leader "hand" moves, then stop it through the API."""
    r = client.post(f"{API}/trajectories/record", json={"name": name, "countdown_s": 0.2, **kw})
    assert r.status_code == 200, r.text
    assert r.json()["kind"] == "traj_record" and st.owner.state == "recording_traj"
    get_world("mock://leader").hand = fast_hand(amplitude=120.0, hz=0.7)
    wait_for(lambda: _phase(st) == "capture", 6)
    # ``seconds`` of the take's own time (samples at its 30 fps), not of this thread's clock: a
    # runner that stalls the process would otherwise record a shorter or longer take
    session = st.owner.session
    wait_for(lambda: len(session.t) >= round(seconds * 30) + 1, 6 + 4 * seconds)  # type: ignore[union-attr]
    r = client.post(f"{API}/trajectories/record/stop")
    assert r.status_code == 200, r.text
    assert st.owner.state == "idle"
    return TrajectoryDetail.model_validate(r.json())


def _save(client: Any, tid: str, **kw: Any) -> TrajectoryDetail:
    r = client.put(f"{API}/trajectories/{tid}", json={"save": True, **kw})
    assert r.status_code == 200, r.text
    return TrajectoryDetail.model_validate(r.json())


def _to_start(st: Station, tr: Trajectory) -> None:
    """Park the follower on the take's first pose (so a replay needs no approach)."""
    world = get_world("mock://follower")
    world.hand = None
    deadline = time.monotonic() + 5
    settled = 0
    while time.monotonic() < deadline:
        pos = st.owner.call("read_positions")
        if all(abs(pos[k] - v) < 1.0 for k, v in tr.start_pose.items()):
            settled += 1
            if settled >= 2:  # two reads 0.1 s apart: there, not passing through
                return
            time.sleep(0.1)
            continue
        settled = 0
        # nudge the goal through the owner (idle: no session), like an operator would with teleop
        st.owner.call("run", fn=lambda o: o.follower.send_action(dict(tr.start_pose)))
        time.sleep(0.1)
    raise AssertionError("follower did not reach the start pose")


def _play(client: Any, tid: str, **body: Any) -> Any:
    return client.post(f"{API}/trajectories/{tid}/play", json=body)


def _session_span(events: Events, session_id: str, phase: str) -> float:
    """Seconds between the first ``session`` event in ``phase`` and the end of the session."""
    with events.lock:
        items = [(t, p) for t, k, p in events.items if k == "session" and p.get("id") == session_id]
    t0 = next(t for t, p in items if p["episode"]["phase"] == phase)
    t1 = next(t for t, p in items if p.get("ended"))
    return t1 - t0


# =========================================================================== record
def test_record_a_and_b_with_the_leader(connected: Station, client: Any, events: Events) -> None:
    st = connected
    a = _record(client, st, name="A", seconds=1.5, keyframe_hz=4)
    assert a.status == "draft" and a.name == "A" and a.fps == 30
    assert a.joints == [f"{m}.pos" for m in st.owner.follower.bus.motors]
    # the take: the samples captured at 30 fps, its duration their span on the loop's own clock
    raw_a = st.programs.trajectories().samples(a.id, trimmed=False)
    assert a.samples == len(raw_a.t) >= 46 and a.raw_duration_s == pytest.approx(
        raw_a.t[-1] - raw_a.t[0], abs=1e-5
    )
    assert a.raw_duration_s >= (a.samples - 1) / 30 * 0.98  # never sampled faster than its fps
    assert a.keyframe_cameras == ["wrist"] and len(a.keyframe_times) >= 5
    assert len(a.series.t) == a.samples
    # every stored row is a goal the owner actually sent (after the SafetyFilter)
    raw = st.programs.trajectories().samples(a.id, trimmed=False)
    rows = {tuple(r) for r in raw.rows}
    sent = [
        tuple(p["sent"][n] for n in raw.names)
        for p in events.of("joints")
        if "sent" in p and st.owner.last_session_summary is not None
    ]
    matched = [s for s in sent if s in rows]
    assert len(matched) >= 5, (len(matched), len(sent))
    # progress messages: countdown, capture (<= 5 Hz), saving, done with the draft id
    msgs = [
        m for m in events.of("trajectory_record") if m["session_id"] == st.owner.last_session_summary["id"]
    ]  # type: ignore[index]
    phases = [m["phase"] for m in msgs]
    assert phases[0] == "countdown" and "capture" in phases and phases[-2:] == ["saving", "done"]
    assert msgs[-1]["ended"] and msgs[-1]["trajectory_id"] == a.id and msgs[-1]["samples"] == a.samples
    captures = [m for m in msgs if m["phase"] == "capture"]
    assert len(captures) <= 5 * a.raw_duration_s + 3
    # keyframes are small JPEGs of the take
    import cv2

    r = client.get(f"{API}/trajectories/{a.id}/keyframes/wrist/0")
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg"
    img = cv2.imdecode(np.frombuffer(r.content, np.uint8), cv2.IMREAD_COLOR)
    assert img.shape[1] <= 320
    assert client.get(f"{API}/trajectories/{a.id}/keyframes/wrist/999").status_code == 404
    assert client.get(f"{API}/trajectories/{a.id}/keyframes/..%2Fx/0").status_code in (404, 422)
    # B ends by the time limit; record/stop afterwards still answers that draft
    r = client.post(f"{API}/trajectories/record", json={"name": "B", "countdown_s": 0.1, "limit_s": 0.8})
    assert r.status_code == 200
    wait_for(lambda: st.owner.state == "idle", 8)
    assert st.owner.last_session_summary["outcome"] == "completed"  # type: ignore[index]
    b_id = st.owner.last_session_summary["id"]  # type: ignore[index]
    r = client.post(f"{API}/trajectories/record/stop")
    assert r.status_code == 200, r.text
    b = TrajectoryDetail.model_validate(r.json())
    # the limit ends the take at the first tick whose capture clock reached 0.8 s (the session's
    # own clock, in its "saving" message), and no tick after it is in the take (a sample is
    # stamped at the start of its tick, before that tick checks the limit)
    raw_b = st.programs.trajectories().samples(b.id, trimmed=False)
    saving = [m for m in events.of("trajectory_record") if m["session_id"] == b_id and m["phase"] == "saving"]
    assert b.name == "B" and saving and saving[0]["elapsed_s"] >= 0.8, saving
    assert raw_b.t[-2] < 0.8, raw_b.t[-3:]
    assert b.raw_duration_s == pytest.approx(raw_b.t[-1] - raw_b.t[0], abs=1e-5)
    listed = Trajectories.model_validate(client.get(f"{API}/trajectories").json()).trajectories
    assert {t.id for t in listed} == {a.id, b.id}
    assert all(len(v) == 64 for v in listed[0].preview.values())


def test_record_needs_idle_and_validates(connected: Station, client: Any) -> None:
    st = connected
    assert client.post(f"{API}/trajectories/record/stop").status_code == 409  # nothing recording
    r = client.post(f"{API}/trajectories/record", json={"limit_s": 601})
    assert r.status_code == 422
    st.settings.programs.traj_max_s = 5
    r = client.post(f"{API}/trajectories/record", json={"limit_s": 10})
    assert r.status_code == 422
    st.settings.programs.traj_max_s = 600
    r = client.post(f"{API}/trajectories/record", json={"countdown_s": 5})
    assert r.status_code == 200
    assert client.post(f"{API}/trajectories/record", json={}).json()["code"] == "busy"
    # stopped during the countdown: nothing captured, nothing saved
    r = client.post(f"{API}/trajectories/record/stop")
    assert r.status_code == 422 and st.owner.state == "idle"
    assert st.owner.last_session_summary["summary"]["trajectory"] is None  # type: ignore[index]
    assert client.get(f"{API}/trajectories").json() == {"trajectories": []}


def test_estop_during_record_keeps_the_draft(connected: Station, client: Any) -> None:
    st = connected
    client.post(f"{API}/trajectories/record", json={"name": "E", "countdown_s": 0.1})
    wait_for(lambda: _phase(st) == "capture", 6)
    time.sleep(0.5)
    st.owner.press_estop("user")
    wait_for(lambda: st.owner.state == "estopped", 3)
    summary = st.owner.last_session_summary
    assert summary is not None and summary["outcome"] == "user" and summary["summary"]["trajectory"]
    assert st.programs.trajectories().get(summary["summary"]["trajectory"]).status == "draft"
    st.owner.call("estop_reset")


# =========================================================================== replay
@pytest.mark.parametrize("slow_loop", [False, True], ids=["normal", "slow-runner"])
def test_replay_at_50_and_100_percent(
    connected: Station, client: Any, events: Events, slow_loop: bool
) -> None:
    """50 % plays every sample twice as long as 100 %, measured in control-loop ticks.

    The player sends one resampled row per tick, so the replay length in wall-clock seconds is
    ``ticks / loop rate``. A loaded CI runner (Windows) runs the loop below 30 Hz, which made the old
    wall-clock assertions flaky. ``slow-runner`` reproduces that: every follower read takes longer
    than one 30 Hz period.
    """
    st = connected
    a = _save(client, _record(client, st, name="A", seconds=1.5).id, trim={"start_s": 0, "end_s": 0})
    world = get_world("mock://follower")
    rows: dict[int, int] = {}
    writes: dict[int, list[float]] = {}
    with Heartbeat(st):
        for speed in (100, 50):
            _to_start(st, a)
            world.calls.clear()
            world.record_calls = True
            r = _play(client, a.id, speed_pct=speed)
            assert r.status_code == 200, r.text
            sess = r.json()
            assert sess["kind"] == "traj_play" and sess["trajectory"] == a.id
            session = st.owner.session
            assert isinstance(session, TrajPlaySession) and session.player is not None
            assert session.player.approach is None  # already at the start: straight to replay
            rows[speed] = len(session.player.rows)
            if slow_loop:  # from the first replay tick on: > 1/30 s per read, every tick overruns (~20 Hz)
                world.read_latency_s = 0.045
            wait_for(lambda: st.owner.state == "idle", 30)
            world.record_calls = False
            world.read_latency_s = 0.0015
            summary = st.owner.last_session_summary
            assert summary is not None and summary["outcome"] == "completed", summary
            assert summary["summary"]["progress"] == 1.0
            assert any(
                p["episode"]["phase"] == "replay" for p in events.of("session") if p.get("id") == sess["id"]
            )
            writes[speed] = [t for t, _ in world.goal_writes()]
            end = st.owner.call("read_positions")
            assert all(abs(end[k] - v) < 3.0 for k, v in a.end_pose.items() if k != "gripper.pos"), end
    # samples: the take resampled at the session fps, stretched x2 at 50 % (deterministic)
    assert abs((rows[100] - 1) - a.duration_s * a.fps) <= 1.0, (rows, a.duration_s)
    assert (rows[50] - 1) / (rows[100] - 1) == pytest.approx(2.0, abs=0.05), rows
    for speed, ts in writes.items():
        # one goal per tick: every resampled row was sent, none skipped, none repeated
        assert rows[speed] <= len(ts) <= rows[speed] + 2, (speed, len(ts), rows[speed])
        # never faster than the session fps (a timer bug would play the take too fast) ...
        span = ts[-1] - ts[0]
        assert span >= (len(ts) - 1) / a.fps * 0.9, (speed, span, len(ts))
        # ... and paced by the loop, not stalled: the span is ticks x the measured tick period
        gaps = sorted(b - t for t, b in itertools.pairwise(ts))
        median = gaps[len(gaps) // 2]
        assert span <= (len(ts) - 1) * median * 1.5 + 0.5, (speed, span, median)


def test_replay_approaches_the_start_first(connected: Station, client: Any, events: Events) -> None:
    st = connected
    a = _save(client, _record(client, st, name="A", seconds=1.0).id)
    get_world("mock://follower").hand = None
    st.owner.call(
        "run",
        fn=lambda o: o.follower.send_action(
            {k: v + 25.0 for k, v in a.start_pose.items() if k != "gripper.pos"}
        ),
    )
    time.sleep(0.5)
    with Heartbeat(st):
        r = _play(client, a.id, approach_speed_deg_s=60)
        assert r.status_code == 200
        assert _phase(st) == "approach"
        wait_for(lambda: st.owner.state == "idle", 10)
    subs = [p["sub"] for p in events.of("state") if p["state"] == "playing"]
    assert subs[0] == "approach"
    sess_phases = [p["episode"]["phase"] for p in events.of("session") if p.get("id") == r.json()["id"]]
    assert sess_phases.index("approach") < sess_phases.index("replay")
    assert st.owner.last_session_summary["outcome"] == "completed"  # type: ignore[index]


def test_estop_mid_replay_stops_within_one_tick(connected: Station, client: Any) -> None:
    st = connected
    a = _save(client, _record(client, st, name="A", seconds=2.0).id, trim={"start_s": 0, "end_s": 0})
    _to_start(st, a)
    world = get_world("mock://follower")
    with Heartbeat(st):
        assert _play(client, a.id, speed_pct=50).status_code == 200
        wait_for(lambda: _phase(st) == "replay", 4)
        time.sleep(0.5)
        session = st.owner.session
        assert isinstance(session, TrajPlaySession) and session.player is not None
        press_estop_frozen_within_one_tick(st, world)  # the freeze write and at most one in-flight tick
    assert world.any_torque()  # frozen, not dropped
    assert session.player.done and session.player.progress < 1.0  # the player was dropped
    summary = st.owner.last_session_summary
    assert summary is not None and summary["outcome"] == "user" and not summary["summary"]["checked"]
    assert client.post(f"{API}/estop/reset").status_code == 200
    assert st.owner.state == "idle"


def test_stop_and_deadman_end_a_replay(connected: Station, client: Any) -> None:
    st = connected
    a = _save(client, _record(client, st, name="A", seconds=1.5).id, trim={"start_s": 0, "end_s": 0})
    with Heartbeat(st):
        assert _play(client, a.id, speed_pct=10).status_code == 200
        time.sleep(0.4)
        # editing or deleting the trajectory that plays is refused
        assert client.put(f"{API}/trajectories/{a.id}", json={"name": "x"}).json()["code"] == "busy"
        assert client.delete(f"{API}/trajectories/{a.id}").json()["code"] == "busy"
        assert client.post(f"{API}/trajectories/{a.id}/confirm").json()["code"] == "busy"
        assert client.post(f"{API}/poses/capture", json={"name": "p"}).json()["code"] == "busy"
        assert client.post(f"{API}/trajectories/record", json={}).json()["code"] == "busy"
        r = client.post(f"{API}/sessions/current/control", json={"action": "stop"})
        assert r.status_code == 200 and st.owner.state == "idle"
    assert st.owner.last_session_summary["outcome"] == "stopped"  # type: ignore[index]
    # no heartbeat: the dead-man trips the replay
    assert _play(client, a.id, speed_pct=10).status_code == 200
    wait_for(lambda: st.owner.state == "estopped", 4)
    assert st.owner.reason == "ui_lost"
    st.owner.call("estop_reset")


def test_fast_replay_needs_the_profile_flag(connected: Station, client: Any) -> None:
    st = connected
    a = _save(client, _record(client, st, name="A", seconds=0.8).id)
    r = _play(client, a.id, speed_pct=150)
    assert r.status_code == 409 and r.json()["code"] == "fast_replay_not_allowed"
    assert _play(client, a.id, speed_pct=151).status_code == 422
    assert _play(client, a.id, speed_pct=9).status_code == 422
    st.owner.profile.follower.allow_fast_replay = True  # type: ignore[union-attr]
    with Heartbeat(st):
        r = _play(client, a.id, speed_pct=150)
        assert r.status_code == 200, r.text
        wait_for(lambda: st.owner.state == "idle", 10)
    assert st.owner.last_session_summary["summary"]["speed_pct"] == 150  # type: ignore[index]


def test_calibration_change_needs_a_check_replay(connected: Station, client: Any) -> None:
    st = connected
    a = _save(client, _record(client, st, name="A", seconds=0.8).id)
    assert a.status == "ready"
    f = calibration_file(st.cal_root, st.owner.profile)  # type: ignore[arg-type]
    f.write_text(f.read_text(encoding="utf-8") + "\n")  # what a recalibration does: a new file
    got = TrajectoryDetail.model_validate(client.get(f"{API}/trajectories/{a.id}").json())
    assert got.status == "needs_check"
    r = _play(client, a.id, speed_pct=100)
    assert r.status_code == 409 and r.json()["code"] == "needs_check"
    assert r.json()["params"]["check_speed_pct"] == 25
    r = client.post(f"{API}/trajectories/{a.id}/confirm")
    assert r.status_code == 409 and r.json()["code"] == "needs_check"  # not before the check replay
    with Heartbeat(st):
        r = _play(client, a.id, check=True, speed_pct=100)
        assert r.status_code == 200, r.text
        assert st.owner.session.speed_pct == 25  # type: ignore[union-attr]
        wait_for(lambda: st.owner.state == "idle", 15)
    summary = st.owner.last_session_summary
    assert summary is not None and summary["summary"]["checked"] and summary["summary"]["speed_pct"] == 25
    r = client.post(f"{API}/trajectories/{a.id}/confirm")
    assert r.status_code == 200, r.text
    ok = Trajectory.model_validate(r.json())
    assert ok.status == "ready" and ok.checked_at is not None
    assert _play(client, a.id, speed_pct=100).status_code == 200
    st.owner.call("control", action="stop")


# =========================================================================== list / edit / poses
def test_trim_rename_delete_through_the_api(connected: Station, client: Any) -> None:
    st = connected
    a = _record(client, st, name="A", seconds=1.0)
    r = client.put(
        f"{API}/trajectories/{a.id}", json={"name": "Pick", "trim": {"start_s": 0.2, "end_s": 0.1}}
    )
    assert r.status_code == 200, r.text
    d = TrajectoryDetail.model_validate(r.json())
    # the trim keeps the samples from 0.2 s after the first to 0.1 s before the last: the duration
    # is the span of those samples (on the loop's clock; a stalled tick next to a cut moves it by
    # that gap, macOS run: 0.601 against 0.957 - 0.3)
    t = st.programs.trajectories().samples(a.id, trimmed=False).t
    kept = [x for x in t if t[0] + 0.2 - 1e-6 <= x <= t[-1] - 0.1 + 1e-6]
    assert d.name == "Pick" and d.status == "draft", d
    assert d.duration_s == pytest.approx(kept[-1] - kept[0], abs=1e-5), (d.duration_s, t)
    assert d.duration_s <= a.raw_duration_s - 0.3 + 1e-5
    r = client.put(f"{API}/trajectories/{a.id}", json={"trim": {"start_s": 5, "end_s": 5}})
    assert r.status_code == 422
    assert client.put(f"{API}/trajectories/{a.id}", json={"bogus": 1}).status_code == 422
    assert client.get(f"{API}/trajectories/t_20200101_000000_abcd").status_code == 404
    assert client.delete(f"{API}/trajectories/{a.id}").status_code == 204
    assert client.get(f"{API}/trajectories/{a.id}").status_code == 404


def test_poses_capture_list_replace(connected: Station, client: Any) -> None:
    st = connected
    r = client.post(f"{API}/poses/capture", json={"name": "home"})
    assert r.status_code == 200, r.text
    home = Pose.model_validate(r.json())
    pos = st.owner.call("read_positions")
    assert home.source == "live" and home.positions.keys() == pos.keys() and not home.needs_check
    r = client.put(
        f"{API}/poses",
        json={
            "poses": [
                {"name": "home", "positions": home.positions, "source": "live"},
                {"name": "above_bin", "positions": {"shoulder_pan.pos": 30.0}},
            ]
        },
    )
    assert r.status_code == 200, r.text
    poses = Poses.model_validate(r.json()).poses
    assert [p.name for p in poses] == ["home", "above_bin"]
    assert next(p for p in poses if p.name == "home").created_at == home.created_at
    assert Poses.model_validate(client.get(f"{API}/poses").json()) == Poses(poses=poses)
    dup = {"poses": [{"name": "a", "positions": {"x.pos": 1}}, {"name": "a", "positions": {"x.pos": 2}}]}
    assert client.put(f"{API}/poses", json=dup).status_code == 422
    assert client.post(f"{API}/poses/capture", json={"name": "Bad Name"}).status_code == 422
