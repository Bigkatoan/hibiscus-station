"""Block programs through the REST API on the mock Station (station-programs.md §5-§7, §10 P2/P4, §11).

* CRUD, check, the 422/409 refusals, run logs;
* the A/B program with keys 1/2: dry run first (required), then a real run in ``programming`` with a
  trace;
* the owner's example end to end: record trajectories A and B with the leader, define a red/blue
  colour detector, program "repeat forever: wait until the camera sees a cube; red → play A, blue →
  play B", show a red then a blue cube to the mock camera, check A then B were played, then the
  e-stop aborts the program within one tick;
* a dry run never leaves ``idle`` and is aborted by the e-stop.
"""

from __future__ import annotations

import time
from typing import Any

import pytest
from blocks_dsl import ab_program, keys_program, num, program, relax, repeat, wait
from conftest import Events, Heartbeat, fast_hand, mock_profile, press_estop_frozen_within_one_tick, wait_for

from hibiscus_station.mock import get_world
from hibiscus_station.programs import schemas as ps
from hibiscus_station.programs.interpreter import Interpreter
from hibiscus_station.station import Station

API = "/api/v1"
CUBES = {
    "name": "Cubes",
    "spec": {
        "kind": "color",
        "camera": "wrist",
        "roi": {"x": 0.25, "y": 0.25, "w": 0.5, "h": 0.5},
        "rules": [
            {"label": "red", "h_min": 170, "h_max": 10, "s_min": 120, "v_min": 80},
            {"label": "blue", "h_min": 100, "h_max": 130, "s_min": 120, "v_min": 80},
        ],
    },
}


def _phase(st: Station) -> str | None:
    s = st.owner.session
    return s.episode.phase if s is not None else None


def _take(client: Any, st: Station, name: str, seconds: float) -> ps.Trajectory:
    """Record a take with the leader, save it (ready)."""
    r = client.post(f"{API}/trajectories/record", json={"name": name, "countdown_s": 0.2})
    assert r.status_code == 200, r.text
    get_world("mock://leader").hand = fast_hand(amplitude=120.0, hz=0.7)
    wait_for(lambda: _phase(st) == "capture", 6)
    time.sleep(seconds)
    r = client.post(f"{API}/trajectories/record/stop")
    assert r.status_code == 200, r.text
    tid = r.json()["id"]
    r = client.put(f"{API}/trajectories/{tid}", json={"save": True, "trim": {"start_s": 0, "end_s": 0}})
    assert r.status_code == 200, r.text
    get_world("mock://leader").hand = None
    return ps.TrajectoryDetail.model_validate(r.json())


def _put(client: Any, doc: dict[str, Any], pid: str = "ab", **kw: Any) -> ps.Program:
    r = client.put(f"{API}/programs/{pid}", json={"name": "A/B", "editor": doc, **kw})
    assert r.status_code == 200, r.text
    return ps.Program.model_validate(r.json())


def _run(client: Any, pid: str = "ab", **body: Any) -> Any:
    return client.post(f"{API}/programs/{pid}/run", json=body)


def _runtime(st: Station, pid: str = "ab") -> Interpreter:
    rt = st.programs.runs.get(pid)
    assert isinstance(rt, Interpreter)
    return rt


def _key(client: Any, k: str, pid: str = "ab") -> None:
    r = client.post(f"{API}/programs/{pid}/input", json={"kind": "key", "value": k})
    assert r.status_code == 200, r.text


def _log(client: Any, run_id: str, pid: str = "ab") -> list[ps.ProgramLogLine]:
    r = client.get(f"{API}/programs/{pid}/runs/{run_id}")
    assert r.status_code == 200, r.text
    return ps.ProgramRunLog.model_validate(r.json()).lines


def _motions(lines: list[ps.ProgramLogLine], outcome: str) -> list[str]:
    return [
        str(ln.data.get("trajectory"))
        for ln in lines
        if ln.kind == "motion" and ln.data.get("outcome") == outcome
    ]


# =========================================================================== CRUD + refusals
def test_program_crud_check_and_refusals(station: Station, client: Any) -> None:
    a, b = "t_20261116_120000_aaaa", "t_20261116_120000_bbbb"
    assert client.get(f"{API}/programs").json() == {"programs": []}
    p1 = _put(client, keys_program(a, b))
    assert p1.version == 1 and p1.ast is not None and p1.issues == [] and p1.refs.trajectories == [a, b]
    assert p1.robot == station.programs.robot_id()
    p2 = _put(client, keys_program(a, b))
    assert p2.version == 2 and p2.created_at == p1.created_at
    report = ps.CheckReport.model_validate(client.post(f"{API}/programs/ab/check").json())
    assert not report.ok and report.dry_run_required and report.version == 2
    assert {i.id for i in report.issues} == {"unknown_trajectory:play_a", "unknown_trajectory:play_b"}
    r = _run(client, dry_run=True)
    assert r.status_code == 422 and r.json()["code"] == "program_invalid"
    assert {e["id"] for e in r.json()["errors"]} == {"unknown_trajectory:play_a", "unknown_trajectory:play_b"}
    # a program that does not compile is still saved
    bad = _put(client, {"blocks": {"blocks": []}}, pid="empty")
    assert bad.ast is None and [i.code for i in bad.issues] == ["no_start_block"]
    listed = {p["id"]: p for p in client.get(f"{API}/programs").json()["programs"]}
    assert listed["ab"]["ok"] and not listed["empty"]["ok"] and listed["ab"]["last_run"] is None
    assert client.get(f"{API}/programs/empty").json()["version"] == 1
    # never ran: state null (QC 0.2.9 QD-10: a 404 here was a console error on every Programs tab
    # load), an unknown program 404; controls 409
    never = client.get(f"{API}/programs/ab/state")
    assert never.status_code == 200 and never.json() is None
    assert client.get(f"{API}/programs/nope/state").status_code == 404
    assert client.post(f"{API}/programs/ab/pause").status_code == 409
    assert client.post(f"{API}/programs/ab/fake", json={"gripper_holding": True}).status_code == 409
    assert client.get(f"{API}/programs/ab/runs").json() == {"runs": []}
    assert client.get(f"{API}/programs/ab/runs/r_20261116_120000_abcd").status_code == 404
    assert client.delete(f"{API}/programs/empty").status_code == 204
    assert client.get(f"{API}/programs/empty").status_code == 404
    assert client.delete(f"{API}/programs/empty").status_code == 404
    assert client.put(f"{API}/programs/Bad Id", json={"name": "x", "editor": {}}).status_code in (404, 422)
    dup = [{"name": "go", "label": "Go"}, {"name": "go", "label": "Again"}]
    r = client.put(f"{API}/programs/ab", json={"name": "x", "editor": {}, "buttons": dup})
    assert r.status_code == 422


def test_confirmations_and_a_dry_run_without_a_robot(station: Station, client: Any) -> None:
    profile = mock_profile()
    profile.follower.rest_pose = {"shoulder_lift.pos": -90.0, "elbow_flex.pos": 90.0}
    station.profiles.put(profile)
    station.profiles.set_active(profile.id)
    p = _put(client, program(repeat(num(2), relax(id_="r"), id_="rep")))
    assert [i.id for i in p.issues] == ["relax_in_loop:r"]
    r = _run(client, dry_run=True)
    assert r.status_code == 422 and [e["id"] for e in r.json()["errors"]] == ["relax_in_loop:r"]
    r = _run(client, dry_run=True, confirm=["relax_in_loop:r"])
    assert r.status_code == 200, r.text
    sess = wire_session(r.json())
    assert sess["kind"] == "program" and sess["program"] == "ab" and sess["outcome"] == "running"
    assert station.owner.state == "disconnected"  # a dry run never touches the owner
    rt = _runtime(station)
    assert rt.dry_run and rt.join(20) and rt.outcome == "completed", rt.state()
    assert client.get(f"{API}/programs/ab").json()["dry_run_version"] == p.version
    runs = client.get(f"{API}/programs/ab/runs").json()["runs"]
    assert len(runs) == 1 and runs[0]["dry_run"] and runs[0]["outcome"] == "completed"


def test_a_finished_run_keeps_its_duration(station: Station, client: Any) -> None:
    """QC 0.2.9 QD-16: a run that completed in 3.3 s read "360.7 s" minutes later, because the
    state's ``t`` kept counting from the start. It must freeze when the run ends."""
    _put(client, program(wait(0.3)))
    assert _run(client, dry_run=True).status_code == 200
    rt = _runtime(station)
    assert rt.join(20) and rt.outcome == "completed", rt.state()
    first = client.get(f"{API}/programs/ab/state").json()
    assert first["status"] == "completed" and 0.3 <= first["t"] < 5, first
    time.sleep(0.6)
    assert client.get(f"{API}/programs/ab/state").json()["t"] == first["t"]


def wire_session(body: dict[str, Any]) -> dict[str, Any]:
    from hibiscus_station.api.schemas import Session

    return Session.model_validate(body).model_dump()


def test_a_dry_run_is_aborted_by_the_estop(connected: Station, client: Any, events: Events) -> None:
    st = connected
    _put(client, program(repeat(num(1000), wait(0.1))))
    r = _run(client, dry_run=True)
    assert r.status_code == 200, r.text
    rt = _runtime(st)
    wait_for(lambda: rt.state().status == "waiting", 3)
    assert st.owner.state == "idle" and st.status()["program"]["dry_run"]
    assert _run(client, dry_run=True).status_code == 409  # one run at a time
    st.owner.press_estop("user")
    assert rt.join(2) and rt.outcome == "estopped"
    wait_for(lambda: st.owner.state == "estopped", 2)
    assert client.get(f"{API}/programs/ab").json()["dry_run_version"] is None  # an e-stop is no pass
    assert _run(client, dry_run=True).json()["code"] == "estopped"
    assert client.post(f"{API}/estop/reset").status_code == 200
    states = [m for m in events.of("program_state") if m["run_id"] == rt.run_id]
    assert all(m["dry_run"] for m in states) and states[-1]["status"] == "estopped"


# =========================================================================== P2: keys 1/2
def test_ab_program_with_keys_dry_run_then_real_run(connected: Station, client: Any, events: Events) -> None:
    st = connected
    a = _take(client, st, "A", 1.0)
    b = _take(client, st, "B", 1.0)
    p = _put(client, keys_program(a.id, b.id))
    report = client.post(f"{API}/programs/ab/check").json()
    assert report["ok"] and report["dry_run_required"], report
    r = _run(client)
    assert r.status_code == 409 and r.json()["code"] == "dry_run_required"

    # dry run: the sim arm plays, the Station stays idle
    r = _run(client, dry_run=True)
    assert r.status_code == 200, r.text
    dry = _runtime(st)
    wait_for(lambda: dry.state().status == "waiting", 3)
    assert st.owner.state == "idle"
    _key(client, "1")
    wait_for(lambda: a.id in dry.played, 3)
    _key(client, "2")
    wait_for(lambda: b.id in dry.played, 15)
    assert st.owner.state == "idle"
    r = client.post(f"{API}/programs/ab/stop")
    assert r.status_code == 200 and r.json()["status"] == "stopped", r.json()
    assert client.get(f"{API}/programs/ab").json()["dry_run_version"] == p.version

    # real run: programming, on the owner thread, dead-man on
    with Heartbeat(st):
        r = _run(client, fps=30)
        assert r.status_code == 200, r.text
        assert r.json()["kind"] == "program" and r.json()["program"] == "ab"
        assert st.owner.state == "programming"
        rt = _runtime(st)
        assert rt is not dry and not rt.dry_run
        # By the time the run is answered, a WS `state` already carries `Status.program` (the
        # session's own `state` went out before the run was registered): a UI that only gets a
        # few `program_state` messages during a long motion must still see the run.
        programs = [m["program"] for m in events.of("state") if m["state"] == "programming"]
        assert programs and programs[-1] is not None and programs[-1]["run_id"] == rt.run_id
        assert client.put(f"{API}/programs/ab", json={"name": "x", "editor": {}}).status_code == 409
        assert client.delete(f"{API}/programs/ab").status_code == 409
        assert _run(client, dry_run=True).status_code == 409
        wait_for(lambda: rt.state().status == "waiting", 3)
        status = client.get(f"{API}/status").json()
        assert status["program"]["run_id"] == rt.run_id and not status["program"]["dry_run"]
        wait_for(lambda: client.get(f"{API}/status").json()["sub"] == "waiting", 3)  # Hibi sleeps
        _key(client, "1")
        wait_for(lambda: a.id in _motions(_log(client, rt.run_id), "completed"), 15)
        _key(client, "2")
        wait_for(lambda: b.id in _motions(_log(client, rt.run_id), "completed"), 15)
        r = client.post(f"{API}/programs/ab/pause")
        assert r.status_code == 200 and r.json()["status"] in ("pausing", "paused")
        wait_for(lambda: rt.state().status == "paused", 3)
        wait_for(lambda: _phase(st) == "paused", 2)
        assert client.post(f"{API}/programs/ab/resume").json()["status"] in ("running", "waiting")
        r = client.post(f"{API}/programs/ab/fake", json={"gripper_holding": True})
        assert r.status_code == 422  # fakes are for dry runs
        r = client.post(f"{API}/programs/ab/stop")
        assert r.status_code == 200
        wait_for(lambda: st.owner.state == "idle", 5)
    assert rt.outcome == "stopped" and st.status()["program"] is None
    summary = st.owner.last_session_summary
    assert summary is not None and summary["kind"] == "program" and summary["summary"]["program"] == "ab"
    assert summary["summary"]["motions"] >= 2
    lines = _log(client, rt.run_id)
    assert (
        lines[0].kind == "start" and not lines[0].data["dry_run"] and lines[-1].data["outcome"] == "stopped"
    )
    assert _motions(lines, "completed")[:2] == [a.id, b.id]
    assert {"loop", "if_keys", "play_a", "play_b", "tick"} <= {
        ln.block_id for ln in lines if ln.kind == "block"
    }
    runs = client.get(f"{API}/programs/ab/runs").json()["runs"]
    assert [r["dry_run"] for r in runs] == [False, True] or [r["dry_run"] for r in runs] == [True, False]
    assert {r["run_id"] for r in runs} == {rt.run_id, dry.run_id}
    assert client.get(f"{API}/programs").json()["programs"][0]["last_run"] is not None
    assert client.get(f"{API}/programs/ab/state").json()["status"] == "stopped"
    assert any(m["run_id"] == rt.run_id for m in events.of("program_log"))


# =========================================================================== the owner's example, end to end
@pytest.mark.timeout(240)
def test_red_blue_cube_program_end_to_end(connected: Station, client: Any, events: Events) -> None:
    st = connected
    a = _take(client, st, "A", 1.5)
    b = _take(client, st, "B", 1.5)
    assert client.put(f"{API}/detectors/cubes", json=CUBES).status_code == 200
    cam = st.hub.camera("wrist")
    cam.show_cube("green")  # a cube no rule matches (show_cube(None) shows the moving red block)
    p = _put(client, ab_program(a.id, b.id))
    assert p.issues == [] and p.refs.detectors == ["cubes"]
    report = client.post(f"{API}/programs/ab/check").json()
    assert report["ok"] and report["issues"] == [], report

    # dry run with faked camera labels (§5.2): red → A in the simulation
    assert _run(client, dry_run=True).status_code == 200
    dry = _runtime(st)
    wait_for(lambda: dry.state().status == "waiting", 3)
    r = client.post(f"{API}/programs/ab/fake", json={"detectors": {"cubes": {"label": "red"}}})
    assert r.status_code == 200, r.text
    wait_for(lambda: a.id in dry.played, 5)
    wait_for(lambda: a.id in _motions(_log(client, dry.run_id), "completed"), 15)  # §5.2: a motion ran
    assert client.post(f"{API}/programs/ab/stop").json()["status"] == "stopped"
    assert dry.played and set(dry.played) == {a.id} and st.owner.state == "idle"

    # real run on the mock arm; the mock camera shows a red, then a blue cube
    world = get_world("mock://follower")
    with Heartbeat(st):
        r = _run(client)
        assert r.status_code == 200, r.text
        rt = _runtime(st)
        wait_for(lambda: rt.state().waiting is not None and rt.state().waiting.kind == "wait_until", 5)  # type: ignore[union-attr]
        time.sleep(0.3)
        assert rt.played == []  # no red or blue cube yet
        cam.show_cube("red")
        wait_for(lambda: a.id in rt.played, 5)
        wait_for(lambda: a.id in _motions(_log(client, rt.run_id), "completed"), 20)
        cam.show_cube("blue")
        wait_for(lambda: b.id in rt.played, 25)
        first_b = rt.played.index(b.id)
        assert rt.played[:first_b] and set(rt.played[:first_b]) == {a.id}  # A (maybe again), then B
        # e-stop while B moves: frozen within one tick, the program is aborted and never resumes
        wait_for(lambda: st.owner.session is not None and _phase(st) in ("approach", "replay"), 5)
        time.sleep(0.3)
        press_estop_frozen_within_one_tick(st, world)
        assert rt.join(3) and rt.outcome == "estopped"
    assert world.any_torque()  # frozen, not dropped
    played = list(rt.played)
    time.sleep(0.5)
    assert rt.played == played  # nothing more after the e-stop
    summary = st.owner.last_session_summary
    assert (
        summary is not None
        and summary["kind"] == "program"
        and summary["summary"]["program_outcome"] == "estopped"
    )
    lines = _log(client, rt.run_id)
    assert lines[-1].kind == "end" and lines[-1].data["outcome"] == "estopped"
    started = [
        str(ln.data["trajectory"]) for ln in lines if ln.kind == "motion" and ln.message.endswith("start")
    ]
    assert started == played
    assert any(
        ln.kind == "condition" and ln.block_id == "sees_red" and ln.data["value"] is True for ln in lines
    )
    assert any(
        ln.kind == "condition" and ln.block_id == "sees_blue" and ln.data["value"] is True for ln in lines
    )
    state = client.get(f"{API}/programs/ab/state").json()
    assert state["status"] == "estopped" and state["message"] == "e-stop"
    assert client.post(f"{API}/estop/reset").status_code == 200
    assert st.owner.state == "idle" and rt.finished
    cam.show_cube(None)


def test_status_program_is_none_when_nothing_runs(connected: Station, client: Any) -> None:
    assert client.get(f"{API}/status").json()["program"] is None


def test_shutdown_stops_a_dry_run(station: Station, client: Any) -> None:
    _put(client, program(repeat(num(1000), wait(0.1))))
    assert _run(client, dry_run=True).status_code == 200
    rt = _runtime(station)
    wait_for(lambda: rt.state().status == "waiting", 3)
    assert station.programs.runs.unfinished() == [rt]
    station.programs.shutdown()
    assert rt.finished and rt.outcome == "stopped" and station.programs.runs.unfinished() == []
