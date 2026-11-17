"""Field report 0.2.8 → 0.2.9 (Windows, real SO-101 pair, 2026-11-17).

1. Record: "pressed Stop but it still ran to the end, cameras stopped" — Stop during an episode
   blocked the control loop while the episode was encoded: no session message, no camera frame,
   the UI timer kept counting to the limit with every control greyed out.
2. Cameras: frames older than two camera periods were "stale" (a Windows webcam that delivers fewer
   frames than configured flickered "No fresh frames" and dropped dataset frames).
3. CR-1: a user STOP holds the follower where it is (Goal := Present, torque on), then offers
   "Return Home" / "Relax".
"""

from __future__ import annotations

import threading
import time
from typing import Any

from conftest import wait_for

from hibiscus_station.station import RecordRequest, Station

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
