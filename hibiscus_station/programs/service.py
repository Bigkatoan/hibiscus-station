"""Station-level operations on block programs (station-programs.md §5, §6, §7, §11).

The REST handlers (``api_programs.py``) call these. A run is an :class:`Interpreter` driving

* a ``ProgramSession`` (state ``programming``, owner thread, every safety path) for a real run, or
* a ``SimMotionPort`` for a dry run, which never touches the owner and leaves the Station state as
  it is (the e-stop still aborts it).

Before a real run the saved version is checked (:func:`check`): errors and unacknowledged
confirmations answer ``422 program_invalid``; a version that has not passed a dry run answers
``409 dry_run_required`` (unless ``settings.programs.require_dry_run`` is off). A dry run passes when
it ends ``completed`` without a fault, or ``stopped`` by the operator without a fault after at least
one motion statement completed in the simulation (when the program has any): a dry run stopped
before anything moved proves nothing about the motions.
"""

from __future__ import annotations

import json
import logging
import threading
import urllib.request
from typing import TYPE_CHECKING, Any

from hibiscus_station.errors import StationError
from hibiscus_station.programs.compiler import iter_stmts
from hibiscus_station.programs.conditions import engine_for_run
from hibiscus_station.programs.interpreter import Interpreter
from hibiscus_station.programs.runlog import RunLog, list_runs, new_run_id, now_iso, read_run
from hibiscus_station.programs.schemas import (
    MOTION_KINDS,
    CheckReport,
    FakeConditions,
    Program,
    ProgramInput,
    ProgramRunLog,
    ProgramRuns,
    Programs,
    ProgramState,
    RunProgramRequest,
)
from hibiscus_station.programs.sim_port import sim_port_for_station
from hibiscus_station.programs.store import ProgramStore
from hibiscus_station.programs.traj_service import start_program_session
from hibiscus_station.programs.validator import blocking, check_program, context_for

if TYPE_CHECKING:
    from collections.abc import Callable

    from hibiscus_station.profiles import RobotProfile
    from hibiscus_station.programs.conditions import ConditionEngine, OperatorLatches
    from hibiscus_station.programs.interfaces import RobotSnapshot
    from hibiscus_station.programs.schemas import ConditionValue, Scalar
    from hibiscus_station.programs.sim_port import SimMotionPort
    from hibiscus_station.station import Station

log = logging.getLogger(__name__)

WEBHOOK_TIMEOUT_S = 5.0
DRY_RUN_PASSES = ("completed", "stopped")


def store(station: Station) -> ProgramStore:
    s = station.programs.programs()
    if not isinstance(s, ProgramStore):  # pragma: no cover - the hub always builds this class
        raise StationError("internal_error", "unexpected program store")
    return s


def _profile(station: Station) -> RobotProfile:
    owner = station.owner
    if owner.profile is not None:
        return owner.profile
    profile = station.profiles.get(station.programs.robot_id())
    if profile is None:
        raise StationError("not_connected", "add a robot profile first")
    return profile


def _refuse_if_running(station: Station, program_id: str) -> None:
    rt = station.programs.runs.get(program_id)
    if rt is not None and not rt.finished:
        raise StationError("busy", "this program is running", params={"program": program_id})


# =========================================================================== CRUD
def list_programs(station: Station) -> Programs:
    return Programs(programs=store(station).all())


def put(station: Station, program_id: str, body: ProgramInput) -> Program:
    _refuse_if_running(station, program_id)
    return store(station).put(program_id, body)


def delete(station: Station, program_id: str) -> None:
    _refuse_if_running(station, program_id)
    store(station).delete(program_id)


def check(station: Station, program_id: str) -> CheckReport:
    p = store(station).get(program_id)
    return check_program(p, context_for(station, _profile(station)))


# =========================================================================== runs
def _dry_session(run_id: str, program_id: str, fps: int) -> dict[str, Any]:
    """The ``Session`` answer of a dry run (no owner session exists: the Station state is unchanged)."""
    return {
        "id": run_id,
        "kind": "program",
        "started_at": now_iso(),
        "fps": fps,
        "episode": {"index": 0, "of": 1, "saved": 0, "phase": "running", "elapsed_s": 0.0, "limit_s": None},
        "dataset": None,
        "model": None,
        "task": "",
        "controls": {"next": False, "rerecord": False, "stop": True},
        "outcome": "running",
        "program": program_id,
    }


def _webhook(url: str | None, program_id: str, run_id: str) -> Callable[[str], None] | None:
    if not url or not url.startswith(("http://", "https://")):
        return None

    def post(text: str) -> None:
        body = json.dumps({"program": program_id, "run_id": run_id, "text": text}).encode()
        req = urllib.request.Request(  # noqa: S310 - scheme checked above (http/https only)
            url, data=body, headers={"content-type": "application/json"}, method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=WEBHOOK_TIMEOUT_S):  # noqa: S310
                pass
        except Exception as exc:
            log.warning("notify webhook failed: %s", exc)

    def send(text: str) -> None:
        threading.Thread(target=post, args=(text,), name="program-notify", daemon=True).start()

    return send


def dry_run_passed(outcome: str | None, runlog: RunLog, *, moves: bool) -> bool:
    """§5.2: ``completed`` without a fault, or ``stopped`` without a fault once a motion completed
    (``moves``: the program has motion statements)."""
    if outcome not in DRY_RUN_PASSES or runlog.faults or runlog.steps == 0:
        return False
    return outcome == "completed" or not moves or runlog.motions_completed > 0


def run(station: Station, program_id: str, req: RunProgramRequest) -> dict[str, Any]:
    hub = station.programs
    with hub.run_lock:
        try:
            current = hub.runs.running()
        except StationError:
            current = None
        if current is not None:
            raise StationError(
                "busy", "a program is already running", params={"program": current.state().program_id}
            )
        profile = _profile(station)
        programs = store(station)
        p = programs.get(program_id)
        report = check_program(p, context_for(station, profile))
        stop = blocking(report, req.confirm)
        if report.ast is None or stop:
            raise StationError(
                "program_invalid",
                "the program has errors or unconfirmed issues",
                params={"issues": [i.id for i in stop]},
                errors=[i.model_dump(mode="json") for i in stop],
            )
        if not req.dry_run and report.dry_run_required:
            raise StationError(
                "dry_run_required",
                "run this version as a dry run first",
                params={"version": p.version, "dry_run_version": p.dry_run_version},
            )
        if req.dry_run and station.owner.estop.is_set:
            raise StationError("estopped", "reset the e-stop first")
        run_id = new_run_id()
        runlog = RunLog(
            station.paths.home,
            run_id,
            program_id=p.id,
            version=p.version,
            dry_run=req.dry_run,
            emit=station.owner.emit,
        )
        dry = req.dry_run

        def engine(
            snapshot: Callable[[], RobotSnapshot],
            latches: OperatorLatches,
            variables: Callable[[str], Scalar],
            on_value: Callable[[ConditionValue, bool], None],
        ) -> ConditionEngine:
            return engine_for_run(
                station,
                snapshot=snapshot,
                latches=latches,
                variables=variables,
                dry_run=dry,
                robot_id=profile.id,
                on_value=on_value,
            )

        port: SimMotionPort | None = None
        has_motion = report.ast is not None and any(
            stmt.kind in MOTION_KINDS for stmt, _ in iter_stmts(report.ast.body)
        )

        def finished(rt: Interpreter) -> None:
            if port is not None:
                port.close()
                if dry_run_passed(rt.outcome, runlog, moves=has_motion):
                    try:
                        programs.mark_dry_run(p.id, p.version)
                    except StationError:  # deleted meanwhile
                        pass

        interp = Interpreter(
            program=p,
            run_id=run_id,
            dry_run=dry,
            runlog=runlog,
            engine_factory=engine,
            signals=hub.signals,
            emit=station.owner.emit,
            estopped=lambda: station.owner.estop.is_set,
            notify=_webhook(station.settings.programs.notify_webhook, p.id, run_id),
            on_finished=finished,
            condition_hz=station.settings.programs.condition_hz,
        )
        if dry:
            try:
                port = sim_port_for_station(station, req.fps)
            except BaseException:
                runlog.discard()
                raise
            hub.runs.register(p.id, interp)
            interp.start(port)
            return _dry_session(run_id, p.id, req.fps)
        try:
            session = start_program_session(station, program_id=p.id, runtime=interp, fps=req.fps)
        except BaseException:
            runlog.discard()
            raise
        hub.runs.register(p.id, interp)
        # The session's `state` (idle → programming) went out before the run was registered, so
        # its `Status.program` was null; send the status again so a UI sees the run straight away.
        station.owner.emit("state", station.status())
        return session


def _active(station: Station, program_id: str) -> Interpreter:
    rt = station.programs.runs.get(program_id)
    if rt is None or rt.finished or not isinstance(rt, Interpreter):
        raise StationError("busy", "this program is not running", params={"program": program_id})
    return rt


def state(station: Station, program_id: str) -> ProgramState | None:
    """The running (or last ended) run; ``None`` when the program has not run since the Station
    started (the normal state of a program, never an error); ``not_found`` for no such program."""
    rt = station.programs.runs.get(program_id)
    if rt is None:
        store(station).get(program_id)
        return None
    return rt.state()


def pause(station: Station, program_id: str) -> ProgramState:
    rt = _active(station, program_id)
    rt.pause()
    return rt.state()


def resume(station: Station, program_id: str) -> ProgramState:
    rt = _active(station, program_id)
    rt.resume()
    return rt.state()


def stop(station: Station, program_id: str) -> ProgramState:
    rt = _active(station, program_id)
    rt.stop("stopped")
    rt.join(5.0)
    return rt.state()


def fake(station: Station, program_id: str, fakes: FakeConditions) -> ProgramState:
    rt = _active(station, program_id)
    rt.fake(fakes)
    return rt.state()


def runs(station: Station, program_id: str) -> ProgramRuns:
    return ProgramRuns(runs=list_runs(station.paths.home, program_id))


def run_log(station: Station, program_id: str, run_id: str) -> ProgramRunLog:
    return read_run(station.paths.home, program_id, run_id)
