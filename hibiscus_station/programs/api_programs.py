"""REST: block programs (station-programs.md §5, §6, §7).

Handlers never touch hardware: a real run starts through ``owner.call`` (``service.run`` →
``traj_service.start_program_session``); stores are file-backed and thread-safe, so the blocking
handlers run in FastAPI's thread pool.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Request, Response

from hibiscus_station.api import schemas as wire
from hibiscus_station.programs import schemas as ps
from hibiscus_station.programs import service as svc
from hibiscus_station.programs.api_common import PROBLEM, item_id, run_id
from hibiscus_station.programs.blocks import CATALOG
from hibiscus_station.programs.store import program_json

if TYPE_CHECKING:
    from hibiscus_station.station import Station


def _st(request: Request) -> Station:
    st: Station = request.app.state.station
    return st


def _program(p: ps.Program) -> Response:
    """A ``Program`` answer (``program_json``: deep editor documents exceed pydantic's serializer)."""
    return Response(program_json(p), media_type="application/json")


def build_programs_router() -> APIRouter:
    r = APIRouter(prefix="/api/v1", tags=["programs"], responses=PROBLEM)

    @r.get("/programs/blocks")
    def blocks(request: Request) -> ps.BlockCatalog:
        """The blocks the compiler accepts (normative for the editor)."""
        return CATALOG

    @r.get("/programs")
    def list_programs(request: Request) -> ps.Programs:
        """Programs of the active robot profile."""
        return svc.list_programs(_st(request))

    @r.get("/programs/{program_id}", response_model=ps.Program)
    def get_program(request: Request, program_id: str = item_id()) -> Response:
        return _program(svc.store(_st(request)).get(program_id))

    @r.put("/programs/{program_id}", response_model=ps.Program)
    def put_program(request: Request, body: ps.ProgramInput, program_id: str = item_id()) -> Response:
        """Save (version + 1) and compile. A program that does not compile is still saved
        (``ast: null``, ``issues``). Refused (409 busy) while this program runs."""
        return _program(svc.put(_st(request), program_id, body))

    @r.delete("/programs/{program_id}", status_code=204)
    def delete_program(request: Request, program_id: str = item_id()) -> Response:
        svc.delete(_st(request), program_id)
        return Response(status_code=204)

    @r.post("/programs/{program_id}/check")
    def check_program(request: Request, program_id: str = item_id()) -> ps.CheckReport:
        return svc.check(_st(request), program_id)

    @r.post("/programs/{program_id}/run")
    def run_program(
        request: Request, body: ps.RunProgramRequest, program_id: str = item_id()
    ) -> wire.Session:
        """idle → programming. 422 ``program_invalid`` (errors = the error/unconfirmed issues),
        409 ``dry_run_required``. Dead-man heartbeat on."""
        return wire.Session.model_validate(svc.run(_st(request), program_id, body))

    @r.get("/programs/{program_id}/state")
    def program_state(request: Request, program_id: str = item_id()) -> ps.ProgramState | None:
        """The running (or last ended) run of this program; ``null`` when it has not run since
        the Station started; 404 when there is no such program."""
        return svc.state(_st(request), program_id)

    @r.post("/programs/{program_id}/pause")
    def pause_program(request: Request, program_id: str = item_id()) -> ps.ProgramState:
        return svc.pause(_st(request), program_id)

    @r.post("/programs/{program_id}/resume")
    def resume_program(request: Request, program_id: str = item_id()) -> ps.ProgramState:
        return svc.resume(_st(request), program_id)

    @r.post("/programs/{program_id}/stop")
    def stop_program(request: Request, program_id: str = item_id()) -> ps.ProgramState:
        """Cancel the motion in flight (hold), then programming → stopping → idle."""
        return svc.stop(_st(request), program_id)

    @r.post("/programs/{program_id}/input")
    def program_input(
        request: Request, body: ps.OperatorInput, program_id: str = item_id()
    ) -> ps.ProgramState:
        """Operator button / key / answer (also WS ``program_input``)."""
        return _st(request).programs.runs.deliver(body, program_id)

    @r.post("/programs/{program_id}/fake")
    def fake_conditions(
        request: Request, body: ps.FakeConditions, program_id: str = item_id()
    ) -> ps.ProgramState:
        """Dry run only: fake camera labels / gripper holding (§5.2)."""
        return svc.fake(_st(request), program_id, body)

    @r.get("/programs/{program_id}/runs")
    def program_runs(request: Request, program_id: str = item_id()) -> ps.ProgramRuns:
        return svc.runs(_st(request), program_id)

    @r.get("/programs/{program_id}/runs/{run_id}")
    def program_run_log(
        request: Request, program_id: str = item_id(), run_id: str = run_id()
    ) -> ps.ProgramRunLog:
        return svc.run_log(_st(request), program_id, run_id)

    return r
