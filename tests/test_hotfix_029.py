"""Field report 0.2.8 → 0.2.9 (Windows, real SO-101 pair, 2026-11-17): the 0.2.9 hotfix.

Named ``tests/test_field_029.py`` on main (v0.2.9, v0.2.10); renamed when 0.2.10 was merged into
release/v1, where ``tests/test_field_029.py`` is the field report *on* 0.2.9 (D-24, D-25).

1. Record: "pressed Stop but it still ran to the end, cameras stopped" — Stop during an episode
   blocked the control loop while the episode was encoded: no session message, no camera frame,
   the UI timer kept counting to the limit with every control greyed out.
2. Cameras: frames older than two camera periods were "stale" (a Windows webcam that delivers fewer
   frames than configured flickered "No fresh frames" and dropped dataset frames).
3. CR-1: a user STOP holds the follower where it is (Goal := Present, torque on), then offers
   "Return Home" / "Relax".
"""

from __future__ import annotations

import math
import threading
import time
from typing import Any

import pytest
from blocks_dsl import play, program
from conftest import Heartbeat, connect_calibrated, fast_hand, mock_profile, wait_for

from hibiscus_station.mock import get_world
from hibiscus_station.station import RecordRequest, Station, TeleopRequest

SAVE_DELAY_S = 2.0  # what encoding an episode costs on a slow Windows laptop (11 s measured here)


def _phase(st: Station) -> str | None:
    s = st.owner.session
    return s.episode.phase if s is not None else None


def _slow_saves(st: Station, delay: float = SAVE_DELAY_S) -> None:
    """Every save_episode of the running record session takes ``delay`` more seconds."""
    rec = st.owner.session.recorder  # type: ignore[union-attr]
    real = rec.dataset.save_episode

    def slow(*a: Any, **kw: Any) -> Any:
        time.sleep(delay)
        return real(*a, **kw)

    rec.dataset.save_episode = slow


class _Watch:
    """Samples the latest published camera tick and the session messages while it runs."""

    def __init__(self, st: Station) -> None:
        self.st = st
        self.samples: list[tuple[float, int | None, str]] = []
        self._stop = threading.Event()
        self._t = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        while not self._stop.is_set():
            fs = self.st.hub._latest
            self.samples.append((time.monotonic(), fs.tick if fs else None, self.st.owner.state))
            self._stop.wait(0.05)

    def __enter__(self) -> _Watch:
        self._t.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self._stop.set()
        self._t.join(2)


def test_stop_during_episode_answers_at_once_and_the_loop_keeps_running(
    connected: Station,
) -> None:
    """Defect 1: Stop returns within a tick, the session shows "saving" (not a running episode),
    camera frames keep flowing while the episode is encoded, and the episode is saved."""
    st = connected
    st.start_record(
        RecordRequest(dataset="stopme", task="t", fps=30, countdown_s=0.2, episode_time_s=30, num_episodes=1)
    )
    wait_for(lambda: _phase(st) == "episode", 4)
    _slow_saves(st)
    time.sleep(1.0)
    with _Watch(st) as w:
        t0 = time.monotonic()
        view = st.owner.call("control", action="stop", timeout=30)
        answered = time.monotonic() - t0
        wait_for(lambda: st.owner.session is None, SAVE_DELAY_S + 20)
    assert answered < 0.5, f"Stop blocked the control loop for {answered:.2f} s"
    assert view["episode"]["phase"] == "saving"
    during = [tick for t, tick, _ in w.samples if t0 + 0.2 < t < t0 + SAVE_DELAY_S - 0.2]
    assert len(set(during)) > 10, f"camera frames froze while saving: ticks {sorted(set(during))}"
    summary = st.owner.last_session_summary
    assert summary is not None
    assert summary["outcome"] == "stopped" and summary["summary"]["saved"] == 1


def test_stop_while_a_previous_episode_saves_keeps_both(connected: Station) -> None:
    st = connected
    st.start_record(
        RecordRequest(dataset="two", task="t", fps=30, countdown_s=0.2, episode_time_s=0.6, num_episodes=3)
    )
    wait_for(lambda: _phase(st) == "episode", 4)
    _slow_saves(st, 1.0)
    st.owner.call("control", action="next")  # buffered, saved at the end of the reset
    wait_for(lambda: _phase(st) == "reset", 4)
    st.owner.call("control", action="next")  # end the reset: saving starts
    wait_for(lambda: _phase(st) == "saving", 4)
    t0 = time.monotonic()
    st.owner.call("control", action="stop", timeout=30)
    assert time.monotonic() - t0 < 0.5
    wait_for(lambda: st.owner.session is None, 20)
    summary = st.owner.last_session_summary
    assert summary is not None and summary["outcome"] == "stopped"
    assert summary["summary"]["saved"] == 1


def test_estop_while_an_episode_saves_never_blocks_the_relax(connected: Station) -> None:
    """An e-stop in the reset with a buffered episode: the second press (relax) takes effect
    at once, the episode is still saved and the dataset finalized in the background."""
    from hibiscus.recording import check_recording

    st = connected
    st.start_record(
        RecordRequest(dataset="halt", task="t", fps=30, countdown_s=0.2, episode_time_s=0.6, num_episodes=2)
    )
    wait_for(lambda: _phase(st) == "episode", 4)
    _slow_saves(st)
    wait_for(lambda: _phase(st) == "reset", 4)  # episode 0 buffered (pending)
    st.owner.press_estop("user")
    wait_for(lambda: st.owner.state == "estopped", 1.0)
    st.owner.press_estop("user", relax=True)
    wait_for(lambda: not st.owner.follower_torque, 1.0)
    root = st.paths.datasets / "halt"
    wait_for(lambda: check_recording(root).complete, SAVE_DELAY_S + 20)
    st.owner.call("estop_reset")


def test_a_new_record_on_the_same_dataset_waits_for_the_background_finalize(connected: Station) -> None:
    st = connected
    st.start_record(
        RecordRequest(dataset="again", task="t", fps=30, countdown_s=0.2, episode_time_s=0.6, num_episodes=2)
    )
    wait_for(lambda: _phase(st) == "episode", 4)
    _slow_saves(st, 1.0)
    wait_for(lambda: _phase(st) == "reset", 4)
    st.owner.press_estop("user")
    wait_for(lambda: st.owner.state == "estopped", 1.0)
    st.owner.call("estop_reset")
    st.start_record(
        RecordRequest(
            dataset="again",
            mode="append",
            task="t",
            fps=30,
            countdown_s=0.2,
            episode_time_s=0.4,
            num_episodes=1,
        )
    )
    wait_for(lambda: st.owner.state == "idle" and st.owner.session is None, 20)
    summary = st.owner.last_session_summary
    assert summary is not None and summary["outcome"] == "completed"
    from hibiscus_station.data import datasets as catalog

    assert catalog.summary(st.paths.datasets, "again")["episodes"] == 2  # type: ignore[index]


@pytest.fixture
def two_cams(station: Station) -> Station:
    connect_calibrated(station, mock_profile(cameras=2, size=(320, 240)))
    return station


def _steady_camera(cam: Any, fps: float) -> None:
    """``cam`` delivers exactly ``fps`` frames per second of its own clock: its latest frame is
    always the one of the last 1/fps step (never older than 1/fps). The mock's frame thread runs
    on the host's scheduler: a Windows runner left it without CPU for over 250 ms (9.3 fps of 12),
    and the product rightly called that 250 ms old frame stale."""
    t0 = time.perf_counter()
    frames: dict[int, Any] = {}

    def step() -> int:
        return math.floor((time.perf_counter() - t0) * fps)

    class Steady(type(cam)):  # type: ignore[misc]
        @property
        def latest_timestamp(self) -> float:
            return t0 + step() / fps

        def read_latest(self, max_age_ms: int = 500) -> Any:
            k = step()
            age_ms = (time.perf_counter() - (t0 + k / fps)) * 1000
            if age_ms > max_age_ms:
                raise TimeoutError(f"frame is {age_ms:.0f} ms old")
            if k not in frames:
                frames.clear()
                frames[k] = self._render(k)
            return frames[k]

    cam.__class__ = Steady


def test_a_camera_slower_than_configured_never_reads_as_stale(two_cams: Station) -> None:
    """Defect 1b: a webcam configured at 30 fps that delivers 12 fps (Windows MSMF in low light)
    is not "No fresh frames": every tick of the episode gets the latest frame, the clock runs."""
    st = two_cams
    _steady_camera(st.hub.camera("wrist"), 12)  # the device delivers fewer frames than the profile asks
    st.start_record(
        RecordRequest(
            dataset="slowcam", task="t", fps=30, countdown_s=0.2, episode_time_s=1.5, num_episodes=1
        )
    )
    wait_for(lambda: st.owner.session is None, 20)
    summary = st.owner.last_session_summary
    assert summary is not None and summary["outcome"] == "completed", summary
    cams = summary["summary"]["cameras"]["wrist"]
    assert cams["stale_ticks"] == 0, cams
    assert 8 <= cams["fps_measured"] <= 16, cams
    assert cams["fps_configured"] == 30


def test_record_summary_carries_camera_evidence(connected: Station) -> None:
    st = connected
    st.start_record(
        RecordRequest(dataset="ev", task="t", fps=30, countdown_s=0.2, episode_time_s=0.8, num_episodes=1)
    )
    wait_for(lambda: st.owner.session is None, 20)
    summary = st.owner.last_session_summary
    assert summary is not None
    cam = summary["summary"]["cameras"]["wrist"]
    assert {"backend", "fps_configured", "fps_measured", "age_ms_p95", "stale_ticks", "last_error"} <= set(
        cam
    )
    assert summary["summary"]["save_s"] and all(s >= 0 for s in summary["summary"]["save_s"])
    meta = (st.paths.sessions / summary["id"] / "session.json").read_text(encoding="utf-8")
    assert '"fps_measured"' in meta


# =========================================================================== CR-1: Stop = hold
def _far_rest_and_relax_on_end(st: Station) -> dict[str, float]:
    """A profile that parks + relaxes at session end, with a rest pose 20° away: a user Stop must
    do neither (CR-1)."""
    p = st.owner.profile
    assert p is not None
    p.follower.on_session_end = "relax"
    p.follower.rest_pose = {k: v + 20.0 for k, v in st.owner.last_obs.items() if k != "gripper.pos"}
    return dict(p.follower.rest_pose)


def _assert_holding(st: Station) -> None:
    world = get_world("mock://follower")
    time.sleep(0.4)
    with world.lock:
        servos = list(world.servos.values())
        assert all(s.torque for s in servos), "the arm was relaxed"
        off = {world.names[s.id]: round(s.goal - s.actual, 1) for s in servos if abs(s.goal - s.actual) > 4}
    assert not off, f"goal is not the present position: {off}"
    assert st.owner.follower_torque
    assert st.owner.interrupted, "Return Home / Relax are not offered"
    assert st.owner.status()["interrupted"] is True


def _moving_leader() -> None:
    get_world("mock://leader").hand = fast_hand(amplitude=150.0, hz=1.0)


def test_teleop_stop_holds_the_follower_where_it_is(connected: Station) -> None:
    st = connected
    st.start_teleop(TeleopRequest())
    _moving_leader()
    time.sleep(1.2)
    rest = _far_rest_and_relax_on_end(st)
    st.owner.call("control", action="stop")
    assert st.owner.state == "idle"
    _assert_holding(st)
    here = st.owner.call("read_positions")
    assert abs(here["shoulder_pan.pos"] - rest["shoulder_pan.pos"]) > 10  # never parked


def test_record_stop_holds_while_saving_and_after(connected: Station) -> None:
    st = connected
    st.start_record(
        RecordRequest(dataset="hold", task="t", fps=30, countdown_s=0.2, episode_time_s=30, num_episodes=1)
    )
    wait_for(lambda: _phase(st) == "episode", 4)
    _slow_saves(st, 1.5)
    _moving_leader()
    time.sleep(1.0)
    _far_rest_and_relax_on_end(st)
    world = get_world("mock://follower")
    world.calls.clear()
    world.record_calls = True
    t = time.monotonic()
    st.owner.call("control", action="stop")
    time.sleep(0.6)
    assert _phase(st) == "saving"
    writes = [w for w, _ in world.goal_writes() if w > t]
    assert len(writes) <= 2, f"{len(writes)} goal writes after Stop (expected only the hold)"
    wait_for(lambda: st.owner.session is None, 20)
    _assert_holding(st)


def test_program_stop_holds_and_offers_home(connected: Station, client: Any) -> None:
    from test_programs_safety import _put, _run, _traj

    st = connected
    st.settings.programs.require_dry_run = False
    tid = _traj(st, seconds=6.0)
    _put(client, program(play(tid, id_="pl")))
    _far_rest_and_relax_on_end(st)
    with Heartbeat(st):
        assert _run(client).status_code == 200
        wait_for(lambda: _phase(st) == "replay", 3)
        time.sleep(1.5)
        assert client.post("/api/v1/programs/p/stop").status_code == 200
        wait_for(lambda: st.owner.state == "idle", 5)
    _assert_holding(st)


def test_danger_stops_keep_their_safe_behaviour(connected: Station) -> None:
    """Thermal / electrical stops still park and cut torque (unchanged by CR-1)."""
    st = connected
    p = st.owner.profile
    assert p is not None
    p.follower.rest_pose = dict(st.owner.last_obs)
    st.start_teleop(TeleopRequest())
    time.sleep(0.5)
    world = get_world("mock://follower")
    world.inject("elbow_flex", temp_c=66.0)
    wait_for(lambda: st.owner.state == "estopped", 8)  # detection (2 reads) + 1.5 s park
    assert st.owner.reason == "thermal"
    assert not world.any_torque()
    world.inject("elbow_flex", temp_c=40.0)
