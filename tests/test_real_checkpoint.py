"""Opt-in (``-m slow``): a real ACT checkpoint runs on the mock robot.

Point ``HIBISCUS_ACT_CHECKPOINT`` at a LeRobot ACT ``pretrained_model`` folder trained with one
640x360 camera named ``wrist_cam`` (e.g. one trained on a Hibiscus server); skipped otherwise.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from conftest import Heartbeat, connect_calibrated, mock_profile, wait_for

from hibiscus_station.models.importer import import_dir
from hibiscus_station.station import RunRequest, Station

ACT = Path(os.environ.get("HIBISCUS_ACT_CHECKPOINT", "/nonexistent"))


@pytest.mark.slow
@pytest.mark.skipif(not ACT.is_dir(), reason="set HIBISCUS_ACT_CHECKPOINT to an ACT pretrained_model folder")
def test_real_act_checkpoint_runs_on_mock_robot(station: Station) -> None:
    station.import_roots = [ACT.parent]
    profile = mock_profile(cameras=0)
    from hibiscus_station.profiles import CameraProfile

    profile.cameras = {"wrist_cam": CameraProfile(type="mock", width=640, height=360, fps=30)}
    connect_calibrated(station, profile)
    entry = import_dir(
        station.registry, ACT, station.paths.staging, station.import_roots, name="act_picknplace"
    )
    assert station.compat(entry.key, profile.id)["ok"]
    job = station.load_model(entry.key, "cpu")
    station.jobs.wait(job.id, timeout=300)
    assert job.status == "succeeded", job.error
    with Heartbeat(station):
        station.start_run(RunRequest(model=entry.key, countdown_s=0.1, episode_time_s=2.0, fps=10))
        wait_for(lambda: station.owner.state == "idle", 120)
    assert station.owner.last_session_summary["outcome"] == "completed"  # type: ignore[index]
