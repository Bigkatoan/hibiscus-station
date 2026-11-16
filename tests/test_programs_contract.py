"""Contract of trajectories / poses / detectors / signals / programs (docs/spec/station-programs.md).

These pin the shapes the three teams build against: the AST, the block catalogue, the new states,
the WebSocket messages and the REST surface (501 stubs until each team lands its part).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, get_args

import pytest
from conftest import STATION_DIR, contract_errors
from pydantic import TypeAdapter, ValidationError

from hibiscus_station.api import schemas as wire
from hibiscus_station.errors import StationError
from hibiscus_station.programs import schemas as ps
from hibiscus_station.programs.blocks import BLOCK_TYPES, CATALOG
from hibiscus_station.programs.paths import RobotDataPaths, program_run_log

TRAJ = "t_20261116_101500_ab12"
RUN = "r_20261116_101500_cd34"

#: The owner's demo: when the camera sees red run A, blue run B; key 1/2 also work; repeat.
AB_PROGRAM: dict[str, Any] = {
    "variables": [{"name": "picks", "type": "number", "initial": 0}],
    "buttons": [{"name": "go", "label": "Go"}],
    "keys": ["1", "2"],
    "body": [
        {"kind": "move_to_pose", "id": "b0", "pose": "home"},
        {
            "kind": "forever",
            "id": "b1",
            "body": [
                {
                    "kind": "wait_until",
                    "id": "b2",
                    "cond": {
                        "kind": "logic",
                        "id": "b3",
                        "op": "or",
                        "left": {"kind": "camera_sees", "id": "b4", "detector": "cubes", "label": "red"},
                        "right": {"kind": "camera_sees", "id": "b5", "detector": "cubes", "label": "blue"},
                    },
                    "timeout_s": 120,
                    "on_timeout": [
                        {"kind": "log", "id": "b6", "text": {"kind": "text", "id": "b7", "value": "idle"}}
                    ],
                },
                {
                    "kind": "if",
                    "id": "b8",
                    "branches": [
                        {
                            "cond": {
                                "kind": "logic",
                                "id": "b9",
                                "op": "or",
                                "left": {
                                    "kind": "camera_sees",
                                    "id": "b10",
                                    "detector": "cubes",
                                    "label": "red",
                                },
                                "right": {"kind": "key_pressed", "id": "b11", "key": "1"},
                            },
                            "body": [{"kind": "play_trajectory", "id": "b12", "trajectory": TRAJ}],
                        },
                        {
                            "cond": {
                                "kind": "compare",
                                "id": "b13",
                                "op": "gt",
                                "left": {
                                    "kind": "detector_confidence",
                                    "id": "b14",
                                    "detector": "cubes",
                                    "label": "blue",
                                },
                                "right": {"kind": "number", "id": "b15", "value": 0.5},
                            },
                            "body": [
                                {"kind": "play_trajectory", "id": "b16", "trajectory": TRAJ, "speed_pct": 50},
                                {"kind": "gripper", "id": "b17", "action": "open"},
                            ],
                        },
                    ],
                    "else_body": [
                        {"kind": "wait", "id": "b18", "seconds": {"kind": "number", "id": "b19", "value": 1}}
                    ],
                },
                {
                    "kind": "change_var",
                    "id": "b20",
                    "name": "picks",
                    "by": {"kind": "number", "id": "b21", "value": 1},
                },
                {
                    "kind": "run_model",
                    "id": "b22",
                    "model": "act-r1",
                    "until": {"kind": "gripper_holding", "id": "b23"},
                    "timeout_s": 20,
                    "on_timeout": [{"kind": "stop", "id": "b24"}],
                },
                {
                    "kind": "set_signal",
                    "id": "b25",
                    "name": "picks",
                    "value": {"kind": "var", "id": "b26", "name": "picks"},
                },
            ],
        },
    ],
}


def _kinds(union: Any) -> set[str]:
    members = get_args(get_args(union)[0])
    return {get_args(m.model_fields["kind"].annotation)[0] for m in members}


# --------------------------------------------------------------------------- AST
def test_ab_program_round_trips() -> None:
    ast = ps.ProgramAst.model_validate(AB_PROGRAM)
    again = ps.ProgramAst.model_validate_json(ast.model_dump_json())
    assert again == ast
    forever = ast.body[1]
    assert isinstance(forever, ps.ForeverStmt)
    branch = forever.body[1]
    assert isinstance(branch, ps.IfStmt) and len(branch.branches) == 2
    assert isinstance(branch.branches[0].body[0], ps.PlayTrajectoryStmt)
    assert branch.branches[0].body[0].speed_pct == 100.0


@pytest.mark.parametrize(
    "bad",
    [
        {"kind": "teleport", "id": "x"},  # unknown kind
        {"kind": "wait", "id": "x", "seconds": {"kind": "number", "id": "y", "value": 1}, "extra": 1},
        {"kind": "play_trajectory", "id": "x", "trajectory": TRAJ, "speed_pct": 200},  # > 150 %
        {"kind": "play_trajectory", "id": "x", "trajectory": "../etc"},
        {"kind": "wait_until", "id": "x", "cond": {"kind": "number", "id": "y", "value": 1}},  # value as cond
        {"kind": "key_pressed", "id": "x", "key": " "},  # not a statement, and space is the e-stop
    ],
)
def test_ast_rejects_bad_nodes(bad: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        ps.ProgramAst.model_validate({"variables": [], "buttons": [], "keys": [], "body": [bad]})


def test_space_is_never_an_operator_key() -> None:
    with pytest.raises(ValidationError):
        ps.KeyPressed.model_validate({"kind": "key_pressed", "id": "k", "key": " "})
    ps.KeyPressed.model_validate({"kind": "key_pressed", "id": "k", "key": "a"})


def test_motion_kinds_match_motion_statements() -> None:
    assert {
        get_args(m.model_fields["kind"].annotation)[0] for m in get_args(ps.MotionStmt)
    } == ps.MOTION_KINDS
    assert ps.MOTION_KINDS <= _kinds(ps.Stmt)


# --------------------------------------------------------------------------- block catalogue
def test_block_catalogue_compiles_to_known_ast_kinds() -> None:
    types = [b.type for b in CATALOG.blocks]
    assert len(types) == len(set(types)) == len(BLOCK_TYPES)
    stmt, value, cond = _kinds(ps.Stmt), _kinds(ps.ValueExpr), _kinds(ps.CondExpr)
    for b in CATALOG.blocks:
        target = {"statement": stmt, "number": value, "text": value, "boolean": cond, "hat": {"program"}}
        assert b.ast in target[b.output], (b.type, b.ast)
    covered = {b.ast for b in CATALOG.blocks}
    # every AST kind is reachable from some block
    assert (stmt | value | cond) - covered == set()
    assert {"hb_start", "controls_if", "hb_play_trajectory", "hb_camera_sees"} <= BLOCK_TYPES


def test_blocks_endpoint_serves_the_catalogue(client: Any) -> None:
    r = client.get("/api/v1/programs/blocks")
    assert r.status_code == 200
    assert ps.BlockCatalog.model_validate(r.json()) == CATALOG


# --------------------------------------------------------------------------- REST stubs
# Every contract route is implemented now; the lists stay for the openapi check and the "no 501" check.
# Team A (tests/test_traj_sessions.py):
IMPLEMENTED: list[tuple[str, str, dict[str, Any] | None]] = [
    ("post", "/trajectories/record", {}),
    ("post", "/trajectories/record/stop", None),
    ("get", "/trajectories", None),
    ("get", f"/trajectories/{TRAJ}", None),
    ("put", f"/trajectories/{TRAJ}", {"name": "A"}),
    ("delete", f"/trajectories/{TRAJ}", None),
    ("post", f"/trajectories/{TRAJ}/play", {"speed_pct": 50}),
    ("post", f"/trajectories/{TRAJ}/confirm", None),
    ("get", f"/trajectories/{TRAJ}/keyframes/wrist/0", None),
    ("get", "/poses", None),
    ("put", "/poses", {"poses": []}),
    ("post", "/poses/capture", {"name": "home"}),
]
#: The integrator's programs service (tests/test_programs_api.py, test_interpreter.py, test_compiler.py).
PROGRAMS: list[tuple[str, str, dict[str, Any] | None]] = [
    ("get", "/programs", None),
    ("get", "/programs/ab", None),
    ("put", "/programs/ab", {"name": "A/B", "editor": {}}),
    ("delete", "/programs/ab", None),
    ("post", "/programs/ab/check", None),
    ("post", "/programs/ab/run", {"dry_run": True}),
    ("get", "/programs/ab/state", None),
    ("post", "/programs/ab/pause", None),
    ("post", "/programs/ab/resume", None),
    ("post", "/programs/ab/stop", None),
    ("post", "/programs/ab/fake", {"gripper_holding": True}),
    ("get", "/programs/ab/runs", None),
    ("get", f"/programs/ab/runs/{RUN}", None),
]


#: Landed by team B (detectors, signals, operator input): tested in test_detectors / test_signals /
#: test_conditions; still part of the contract surface below.
LANDED: list[tuple[str, str, dict[str, Any] | None]] = [
    ("get", "/detectors", None),
    ("get", "/detectors/cubes", None),
    (
        "put",
        "/detectors/cubes",
        {
            "name": "Cubes",
            "spec": {
                "kind": "color",
                "camera": "wrist",
                "roi": {"x": 0, "y": 0, "w": 1, "h": 1},
                "rules": [{"label": "red", "h_min": 170, "h_max": 10}],
            },
        },
    ),
    ("delete", "/detectors/cubes", None),
    ("post", "/detectors/cubes/test", {}),
    ("get", "/signals", None),
    ("post", "/signals/door", {"value": 1}),
    ("post", "/programs/ab/input", {"kind": "key", "value": "1"}),
]


@pytest.mark.parametrize(("method", "path", "body"), IMPLEMENTED + PROGRAMS + LANDED)
def test_no_route_answers_not_implemented(client: Any, method: str, path: str, body: Any) -> None:
    kwargs = {"json": body} if body is not None else {}
    r = (
        getattr(client, method)(f"/api/v1{path}", **kwargs)
        if method != "delete"
        else client.delete(f"/api/v1{path}")
    )
    assert r.status_code != 501, (path, r.status_code, r.text)
    if r.status_code >= 400 and r.headers.get("content-type", "").startswith("application/"):
        wire.Problem.model_validate(r.json())


def test_stub_routes_validate_bodies_first(client: Any) -> None:
    r = client.post(f"/api/v1/trajectories/{TRAJ}/play", json={"speed_pct": 500})
    assert r.status_code == 422 and r.json()["code"] == "validation_failed"
    r = client.get("/api/v1/trajectories/not-an-id")
    assert r.status_code == 422
    r = client.post("/api/v1/signals/bad name", json={"value": 1})
    assert r.status_code in (404, 422)


def test_every_stub_is_in_openapi() -> None:
    doc = json.loads((STATION_DIR / "openapi.json").read_text())
    paths = {p.removeprefix("/api/v1") for p in doc["paths"]}
    for _, path, _ in IMPLEMENTED + PROGRAMS + LANDED:
        templ = (
            path.replace(TRAJ, "{trajectory_id}")
            .replace(RUN, "{run_id}")
            .replace("/detectors/cubes", "/detectors/{detector_id}")
            .replace("/programs/ab", "/programs/{program_id}")
            .replace("/signals/door", "/signals/{name}")
            .replace("/keyframes/wrist/0", "/keyframes/{camera}/{index}")
        )
        assert templ in paths, templ
    assert "/programs/blocks" in paths
    assert "/detectors/{detector_id}/model" in paths


# --------------------------------------------------------------------------- states and messages
def test_new_states_are_wired() -> None:
    from hibiscus_station.hw.owner import MOTION_STATES

    states = set(get_args(wire.StationState))
    assert {"recording_traj", "playing", "programming"} <= states
    assert MOTION_STATES["traj_record"] == "recording_traj"
    assert MOTION_STATES["traj_play"] == "playing"
    assert MOTION_STATES["program"] == "programming"
    assert {"traj_record", "traj_play", "program"} <= set(get_args(wire.SessionKind))
    assert {"capture", "running", "waiting", "paused"} <= set(get_args(wire.Phase))


def test_new_states_have_ui_text() -> None:
    i18n = STATION_DIR / "web" / "src" / "station" / "i18n"
    if not i18n.is_dir():
        pytest.skip("web sources not available")
    for lang in ("en", "vi"):
        strings = json.loads((i18n / f"{lang}.json").read_text())["state"]
        missing = sorted(set(get_args(wire.StationState)) - set(strings))
        assert not missing, f"{lang}.json state.* missing {missing}"


PROGRAM_STATE: dict[str, Any] = {
    "run_id": RUN,
    "program_id": "ab",
    "version": 3,
    "dry_run": True,
    "status": "waiting",
    "block_id": "b2",
    "block_kind": "wait_until",
    "t": 4.2,
    "steps": 7,
    "variables": {"picks": 2, "answer": "yes"},
    "conditions": [{"block_id": "b4", "value": False, "t": 4.1}],
    "waiting": {"kind": "wait_until", "block_id": "b2", "since_s": 3.0, "timeout_s": 120},
    "ask": None,
    "buttons": [{"name": "go", "label": "Go"}],
    "keys": ["1", "2"],
    "message": None,
}

MESSAGES: list[tuple[str, dict[str, Any]]] = [
    ("program_state", PROGRAM_STATE),
    (
        "program_log",
        {
            "run_id": RUN,
            "seq": 1,
            "t": 0.0,
            "level": "info",
            "kind": "start",
            "block_id": None,
            "message": "start",
            "data": {"version": 3},
        },
    ),
    (
        "trajectory_record",
        {
            "session_id": "s_20261116_101500_a1b2",
            "phase": "done",
            "elapsed_s": 12.0,
            "limit_s": 60.0,
            "samples": 360,
            "trajectory_id": TRAJ,
            "ended": True,
        },
    ),
    ("signal", {"name": "door", "value": "open", "source": "http", "at": "2026-11-16T10:15:00Z", "seq": 4}),
]


@pytest.mark.parametrize(("kind", "payload"), MESSAGES)
def test_new_ws_messages_match_the_contract(kind: str, payload: dict[str, Any]) -> None:
    assert contract_errors(kind, payload) == []


def test_program_input_is_a_client_message() -> None:
    msg = wire.CLIENT_MESSAGE.validate_python({"type": "program_input", "kind": "button", "value": "go"})
    assert isinstance(msg, ps.ClientProgramInput)


def test_status_carries_the_program(station: Any) -> None:
    st = station.status()
    st.update(state="programming", sub="waiting", program=PROGRAM_STATE)
    assert wire.Status.model_validate(st).program is not None


def test_program_ws_message_round_trips_through_union() -> None:
    adapter: TypeAdapter[Any] = wire.SERVER_MESSAGE
    msg = adapter.validate_python({**PROGRAM_STATE, "type": "program_state"})
    assert isinstance(msg, ps.ProgramStateMsg)


# --------------------------------------------------------------------------- persisted models
def test_old_settings_and_profiles_load_with_program_defaults(tmp_path: Path) -> None:
    from hibiscus_station.profiles import RobotProfile
    from hibiscus_station.settings import Settings

    p = tmp_path / "settings.yaml"
    p.write_text("device: cpu\n")
    s = Settings.load(p)
    assert s.programs.require_dry_run is True and s.programs.condition_hz == 10
    prof = RobotProfile.model_validate(
        {"id": "desk", "follower": {"port": "/dev/ttyACM0", "calibration_id": "desk_follower"}}
    )
    assert prof.follower.allow_fast_replay is False
    assert prof.follower.grip_hold.load_min_pct == 15


def test_detector_specs_are_a_tagged_union() -> None:
    det = ps.DetectorInput.model_validate(
        {
            "name": "Cubes",
            "spec": {
                "kind": "classifier",
                "camera": "wrist",
                "labels": ["red", "blue", "none"],
                "none_label": "none",
            },
        }
    )
    assert isinstance(det.spec, ps.ClassifierDetectorSpec)
    with pytest.raises(ValidationError):
        ps.ColorRule.model_validate({"label": "red", "h_min": 0, "h_max": 200})


# --------------------------------------------------------------------------- storage layout
def test_robot_data_paths_layout(tmp_path: Path) -> None:
    p = RobotDataPaths(tmp_path, "desk")
    assert p.trajectory_samples(TRAJ) == tmp_path / "robots/desk/trajectories" / TRAJ / "samples.parquet"
    assert p.keyframe(TRAJ, "wrist", 3).name == "0003.jpg"
    assert p.poses == tmp_path / "robots/desk/poses.json"
    assert p.detector_model("cubes") == tmp_path / "robots/desk/detectors/cubes.onnx"
    assert p.program_json("ab") == tmp_path / "robots/desk/programs/ab/program.json"
    assert program_run_log(tmp_path, RUN) == tmp_path / "runs/programs" / f"{RUN}.jsonl"
    p.ensure()
    assert (p.root.stat().st_mode & 0o777) == 0o700


@pytest.mark.parametrize(
    "call",
    [
        lambda p: p.trajectory_dir("../x"),
        lambda p: p.trajectory_dir(TRAJ + "\n"),
        lambda p: p.program_json("A/B"),
        lambda p: p.detector_json(".."),
        lambda p: p.keyframe(TRAJ, "../x", 0),
        lambda p: program_run_log(p.home, "r_../../x"),
    ],
)
def test_robot_data_paths_reject_traversal(tmp_path: Path, call: Any) -> None:
    with pytest.raises(StationError):
        call(RobotDataPaths(tmp_path, "desk"))
    with pytest.raises(StationError):
        RobotDataPaths(tmp_path, "../desk")


def test_hub_resolves_the_robot_and_caches_the_stores(station: Any) -> None:
    from conftest import mock_profile

    for p in station.profiles.list():  # the --mock demo profile
        station.profiles.delete(p.id)
    with pytest.raises(StationError) as e:
        station.programs.robot_paths()
    assert e.value.code == "not_connected"
    station.profiles.put(mock_profile())
    paths = station.programs.robot_paths()
    assert paths.root == station.paths.home / "robots" / "desk" and paths.trajectories.is_dir()
    assert station.programs.detectors().robot_id == "desk"
    assert (
        station.programs.programs() is station.programs.programs() and station.programs.programs().all() == []
    )
    assert station.programs.trajectories() is station.programs.trajectories()  # cached per robot
    assert station.programs.trajectories().all() == [] and station.programs.poses().all() == []
    assert station.programs.calibration_hash() == "none"  # no follower calibration file yet
    with pytest.raises(StationError) as e:
        station.programs.calibration_hash("nobody")
    assert e.value.code == "not_found"
