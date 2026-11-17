"""Latency budget: Station's teleop vs LeLab's loop on emulated SO-101 arms with real wire timing
(1 Mbaud, return delays, 1 ms USB latency timer, ~300 deg/s servos). POSIX only.

0.2.4 measured here: 30 Hz, every tick clipped by the 5 deg relative cap, the follower 127 ms
behind the leader (LeLab: 54 ms, the servo's own lag). See ``tests/teleop_bench.py``.

Robust to a loaded machine (QC 0.2.9: one run on a shared runner measured 65 ms against LeLab's
54 + 6 while QC servers, emulators and another workflow ran). Both loops are timed back to back
as one *pair*, so they see the same load, and every budget below must hold inside one pair: no
limit is relaxed, and LeLab's and Station's numbers are never taken from different pairs. A pair
that misses is measured again (fresh emulated arms, the order of the two loops swapped), up to
``ATTEMPTS`` pairs. A real regression such as 0.2.4's (127 ms behind, every tick clipped) misses
in every pair; load only makes a pair miss now and then.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

if sys.platform == "win32":  # pragma: no cover
    pytest.skip("pseudo-terminals are POSIX only", allow_module_level=True)

from teleop_bench import NORMAL, Arms, Result, run_lelab, run_station

DURATION_S = 2.0
ATTEMPTS = 3


def _run(root: Path, which: str) -> Result:
    arms = Arms(NORMAL)
    try:
        if which == "lelab":
            return run_lelab(arms, root / "cal-lelab", DURATION_S, settle_s=0.6)
        return run_station(arms, root / "home", root / "cal", DURATION_S, settle_s=0.8)
    finally:
        arms.close()


def budget_misses(lelab: Result, station: Result) -> list[str]:
    """Every budget the pair misses (empty: Station is as fast as LeLab in this pair)."""
    shown = station.extra.get("station_latency_ms_p50")
    checks = [
        # a normal human move is never clipped
        (station.clip_fraction <= 0.02, f"clipped {station.clip_fraction:.3f} > 0.02"),
        # the follower trails the leader by the servo's own lag, like LeLab's
        (station.lag_ms <= lelab.lag_ms + 6, f"lag {station.lag_ms:.1f} > LeLab {lelab.lag_ms:.1f} + 6 ms"),
        (station.lag_ms <= 70, f"lag {station.lag_ms:.1f} > 70 ms"),
        # the goal the follower is sent is as fresh as LeLab's (budget: +3 ms, and 10 ms absolute)
        (
            station.p(50) <= lelab.p(50) + 3.0,
            f"goal age p50 {station.p(50):.2f} > LeLab {lelab.p(50):.2f} + 3 ms",
        ),
        (station.p(50) <= 10.0, f"goal age p50 {station.p(50):.2f} > 10 ms"),
        (station.loop_hz >= 150, f"loop {station.loop_hz:.0f} Hz < 150 Hz"),
        # what the Teleop screen shows is what was measured
        (
            shown is not None and abs(float(shown) - station.p(50)) <= 3.0,
            f"shown latency {shown} vs measured {station.p(50):.2f} ms",
        ),
    ]
    return [why for ok, why in checks if not ok]


def test_budget_misses_names_every_broken_budget() -> None:
    """The pair check itself: 0.2.4's numbers miss, LeLab-like numbers pass."""
    lelab = Result("lelab", "normal", latency_ms=[4.0] * 10, loop_hz=250, lag_ms=54)
    good = Result(
        "station",
        "normal",
        latency_ms=[4.6] * 10,
        loop_hz=229,
        lag_ms=55,
        extra={"station_latency_ms_p50": 5.0},
    )
    assert budget_misses(lelab, good) == []
    old = Result(
        "station",
        "normal",
        latency_ms=[19.5] * 10,
        loop_hz=30,
        lag_ms=127,
        clip_fraction=1.0,
        extra={"station_latency_ms_p50": 19.5},
    )
    assert len(budget_misses(lelab, old)) == 6  # every budget but the shown value


def test_station_teleop_latency_matches_lelab(tmp_path: Path) -> None:
    pairs = []
    for attempt in range(ATTEMPTS):
        root = tmp_path / f"pair{attempt}"
        order = ("lelab", "station") if attempt % 2 == 0 else ("station", "lelab")
        got = {which: _run(root, which) for which in order}
        lelab, station = got["lelab"], got["station"]
        misses = budget_misses(lelab, station)
        pairs.append({"lelab": lelab.row(), "station": station.row(), "misses": misses})
        if not misses:
            return
    pytest.fail(f"Station missed the latency budget in all {ATTEMPTS} measured pairs: {pairs}")
