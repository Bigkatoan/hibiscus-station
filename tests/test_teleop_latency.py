"""Latency budget: Station's teleop vs LeLab's loop on emulated SO-101 arms with real wire timing
(1 Mbaud, return delays, 1 ms USB latency timer, ~300 deg/s servos). POSIX only.

0.2.4 measured here: 30 Hz, every tick clipped by the 5 deg relative cap, the follower 127 ms
behind the leader (LeLab: 54 ms, the servo's own lag). See ``tests/teleop_bench.py``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sts_emulator import pty_unavailable

if reason := pty_unavailable():  # pragma: no cover
    pytest.skip(reason, allow_module_level=True)

from teleop_bench import NORMAL, Arms, Result, run_lelab, run_station

DURATION_S = 2.0


def _run(tmp_path: Path, which: str) -> Result:
    arms = Arms(NORMAL)
    try:
        if which == "lelab":
            return run_lelab(arms, tmp_path / "cal-lelab", DURATION_S, settle_s=0.6)
        return run_station(arms, tmp_path / "home", tmp_path / "cal", DURATION_S, settle_s=0.8)
    finally:
        arms.close()


def test_station_teleop_latency_matches_lelab(tmp_path: Path) -> None:
    lelab = _run(tmp_path, "lelab")
    station = _run(tmp_path, "station")
    report = {"lelab": lelab.row(), "station": station.row()}
    # a normal human move is never clipped
    assert station.clip_fraction <= 0.02, report
    # the follower trails the leader by the servo's own lag, like LeLab's
    assert station.lag_ms <= lelab.lag_ms + 6, report
    assert station.lag_ms <= 70, report
    # the goal the follower is sent is as fresh as LeLab's (budget: +3 ms, and 10 ms absolute)
    assert station.p(50) <= lelab.p(50) + 3.0, report
    assert station.p(50) <= 10.0, report
    assert station.loop_hz >= 150, report
    # what the Teleop screen shows is what was measured
    shown = station.extra["station_latency_ms_p50"]
    assert shown is not None and abs(float(shown) - station.p(50)) <= 3.0, report
