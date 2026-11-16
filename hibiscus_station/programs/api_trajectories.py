"""REST: trajectories and poses (station-programs.md §7). Owner: team A.

Handlers never touch hardware: sessions start through ``owner.call`` (``traj_service``); stores are
file-backed and thread-safe, so blocking handlers run in FastAPI's thread pool.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request, Response

from hibiscus_station.api import schemas as wire
from hibiscus_station.programs import schemas as ps
from hibiscus_station.programs import traj_service as svc
from hibiscus_station.programs.api_common import PROBLEM, trajectory_id
from hibiscus_station.station import Station

JPEG: dict[int | str, dict[str, Any]] = {200: {"content": {"image/jpeg": {}}, "description": "keyframe JPEG"}}


def _st(request: Request) -> Station:
    st: Station = request.app.state.station
    return st


def build_trajectories_router() -> APIRouter:
    r = APIRouter(prefix="/api/v1", tags=["trajectories"], responses=PROBLEM)

    # Declared before /trajectories/{id}/... so "record" is never read as an id.
    @r.post("/trajectories/record")
    def record_start(request: Request, body: ps.RecordTrajectoryRequest) -> wire.Session:
        """idle → recording_traj (countdown → capture). Same start checks as teleop (leader needed)."""
        return wire.Session.model_validate(svc.start_record(_st(request), body))

    @r.post("/trajectories/record/stop")
    def record_stop(request: Request) -> ps.TrajectoryDetail:
        """End the take; answers the new draft once the state is back to idle."""
        return svc.stop_record(_st(request))

    @r.get("/trajectories")
    def list_trajectories(request: Request) -> ps.Trajectories:
        """Trajectories of the active robot profile."""
        return ps.Trajectories(trajectories=svc.store(_st(request)).all())

    @r.get("/trajectories/{trajectory_id}")
    def get_trajectory(request: Request, trajectory_id: str = trajectory_id()) -> ps.TrajectoryDetail:
        return svc.store(_st(request)).detail(trajectory_id)

    @r.put("/trajectories/{trajectory_id}")
    def put_trajectory(
        request: Request, body: ps.TrajectoryUpdate, trajectory_id: str = trajectory_id()
    ) -> ps.TrajectoryDetail:
        """Rename, trim, save a draft. Refused (409 busy) while that trajectory is playing."""
        return svc.update(_st(request), trajectory_id, body)

    @r.delete("/trajectories/{trajectory_id}", status_code=204)
    def delete_trajectory(request: Request, trajectory_id: str = trajectory_id()) -> Response:
        svc.delete(_st(request), trajectory_id)
        return Response(status_code=204)

    @r.post("/trajectories/{trajectory_id}/play")
    def play_trajectory(
        request: Request, body: ps.PlayTrajectoryRequest, trajectory_id: str = trajectory_id()
    ) -> wire.Session:
        """idle → playing (approach → replay). Dead-man heartbeat on."""
        return wire.Session.model_validate(svc.play(_st(request), trajectory_id, body))

    @r.post("/trajectories/{trajectory_id}/confirm")
    def confirm_trajectory(request: Request, trajectory_id: str = trajectory_id()) -> ps.Trajectory:
        """needs_check → ready, only after a completed ``check`` replay of the current calibration."""
        return svc.confirm(_st(request), trajectory_id)

    @r.get(
        "/trajectories/{trajectory_id}/keyframes/{camera}/{index}", response_class=Response, responses=JPEG
    )
    def keyframe(request: Request, camera: str, index: int, trajectory_id: str = trajectory_id()) -> Response:
        data = svc.store(_st(request)).keyframe(trajectory_id, camera, index)
        return Response(
            content=data, media_type="image/jpeg", headers={"cache-control": "private, max-age=3600"}
        )

    # ------------------------------------------------------------------ poses
    @r.get("/poses", tags=["poses"])
    def get_poses(request: Request) -> ps.Poses:
        return ps.Poses(poses=_st(request).programs.poses().all())

    @r.put("/poses", tags=["poses"])
    def put_poses(request: Request, body: ps.PosesUpdate) -> ps.Poses:
        """Replace the whole list (names unique)."""
        return ps.Poses(poses=_st(request).programs.poses().replace(body.poses))

    @r.post("/poses/capture", tags=["poses"])
    def capture_pose(request: Request, body: ps.CapturePoseRequest) -> ps.Pose:
        """Store the follower's present position as ``name`` (idle only)."""
        return svc.capture_pose(_st(request), body.name)

    return r
