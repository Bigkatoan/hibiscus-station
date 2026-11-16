"""Compiler (Blockly JSON → AST) and validator (station-programs.md §5, §6, §12.4).

Pure tests: no Station. The validator gets a ValidationContext made of small fakes.
"""

from __future__ import annotations

from typing import Any

import pytest
from blocks_dsl import (
    ab_program,
    arith,
    ask,
    blk,
    boolean,
    change,
    compare,
    forever,
    go_home,
    if_,
    join,
    key,
    keys_program,
    log,
    move,
    num,
    play,
    program,
    relax,
    repeat,
    run_model_until,
    sees,
    set_signal,
    set_var,
    stop,
    text,
    var,
    wait,
    wait_until,
    while_,
)

from hibiscus_station.errors import StationError
from hibiscus_station.programs import schemas as ps
from hibiscus_station.programs.compiler import compile_program, iter_exprs, iter_stmts
from hibiscus_station.programs.validator import ValidationContext, blocking, check_program, validate_ast

A = "t_20261116_120000_aaaa"
B = "t_20261116_120000_bbbb"


def codes(result: Any) -> dict[str, str]:
    return {i.id: i.severity for i in result.issues}


def ok(doc: dict[str, Any], **kw: Any) -> ps.ProgramAst:
    r = compile_program(doc, **kw)
    assert r.ast is not None, r.issues
    assert not [i for i in r.issues if i.severity == "error"], r.issues
    return r.ast


# =========================================================================== structure
def test_the_ab_program_compiles_with_block_ids() -> None:
    r = compile_program(ab_program(A, B))
    assert r.issues == [] and r.ast is not None
    (loop,) = r.ast.body
    assert isinstance(loop, ps.ForeverStmt) and loop.id == "loop"
    wu, if_ab = loop.body
    assert isinstance(wu, ps.WaitUntilStmt) and wu.id == "wait_cube" and wu.timeout_s == 60
    assert isinstance(wu.cond, ps.Logic) and wu.cond.op == "or"
    assert isinstance(if_ab, ps.IfStmt) and [b.body[0].id for b in if_ab.branches] == ["play_a", "play_b"]
    cond = if_ab.branches[0].cond
    assert isinstance(cond, ps.CameraSees) and cond.camera is None and cond.label == "red"
    assert r.refs.trajectories == [A, B] and r.refs.detectors == ["cubes"]


def test_keys_are_collected_for_the_run_screen() -> None:
    ast = ok(keys_program(A, B))
    assert ast.keys == ["1", "2"]


@pytest.mark.parametrize(
    ("doc", "issue"),
    [
        ({"blocks": {"blocks": []}}, "no_start_block:-"),
        ({"blocks": {"blocks": [blk("hb_start", "s1"), blk("hb_start", "s2")]}}, "many_start_blocks:s2"),
        (program(blk("hb_teleport", "x")), "unknown_block:x"),
        (program(blk("hb_wait", "w")), "missing_input:w"),
        (program(play(A, speed=500, id_="p")), "bad_field:p"),
        (program(play("../etc", id_="p")), "bad_field:p"),
        (program(blk("hb_gripper", "g", fields={"ACTION": "set"})), "bad_field:g"),
        (program(blk("hb_gripper", "g", fields={"ACTION": "squeeze"})), "bad_field:g"),
        (program(blk("hb_wait", "w", inputs={"SECONDS": text("soon", id_="x")})), "type_mismatch:x"),
        (program(blk("hb_wait", "w", inputs={"SECONDS": boolean(True, id_="x")})), "type_mismatch:x"),
        (program(if_([(num(1, id_="x"), [])])), "type_mismatch:x"),
        (program(num(1, id_="x")), "type_mismatch:x"),
        (program(log(var("nope", id_="l"))), "unknown_variable:l"),
        (program(forever(log(text("hi")), id_="f")), "busy_loop:f"),
        (program(while_(boolean(True), log(text("hi")), id_="w")), "busy_loop:w"),
        (program(while_(boolean(False), log(text("hi")), mode="UNTIL", id_="w")), "busy_loop:w"),
        (
            program(if_([(key("1"), [])]), if_([(blk("hb_key_pressed", "k", fields={"KEY": " "}), [])])),
            "bad_field:k",
        ),
        (program(if_([(blk("hb_button_pressed", "b", fields={"BUTTON": "go"}), [])])), "unknown_button:b"),
        (program(compare("LT", text("a"), num(1), id_="c")), "type_mismatch:c"),
        (program(ask("Which?", "", "v", id_="a"), variables=[("v", "answer", "String")]), "bad_field:a"),
        (program(ask("Which?", "a,b", "v", id_="a"), variables=[("v", "n", "Number")]), "type_mismatch:a"),
        (program(set_var("v", text("x"), id_="s"), variables=[("v", "n", "Number")]), "type_mismatch:s"),
        (program(change("v", num(1), id_="c"), variables=[("v", "t", "String")]), "type_mismatch:c"),
        (program(blk("hb_start", "inner")), "unknown_block:inner"),
    ],
)
def test_errors(doc: dict[str, Any], issue: str) -> None:
    r = compile_program(doc)
    assert issue in codes(r), r.issues
    assert codes(r)[issue] == "error" and r.ast is None and not r.ok


def test_other_top_level_stacks_are_unreachable_warnings() -> None:
    doc = program(wait(0.1), tops=[play(A, id_="loose"), text("orphan", id_="t")])
    r = compile_program(doc)
    assert codes(r) == {"unreachable:loose": "warning", "unreachable:t": "warning"}
    assert r.ast is not None and len(r.ast.body) == 1  # the loose motion is not part of the program


def test_relax_arm_in_a_loop_needs_confirmation() -> None:
    r = compile_program(program(repeat(num(3), relax(id_="r"), id_="rep"), relax(id_="r2")))
    assert codes(r) == {"relax_in_loop:r": "confirm"} and r.ast is not None


def test_too_many_blocks() -> None:
    doc = program(*[wait(0.1) for _ in range(30)])
    r = compile_program(doc, max_blocks=20)
    assert codes(r) == {"too_many_blocks:-": "error"} and r.ast is None


def test_a_loop_that_waits_or_moves_is_not_busy() -> None:
    ok(program(forever(if_([(key("1"), [play(A)])]), wait(0.1))))
    ok(program(forever(wait_until(key("1")))))
    ok(program(forever(if_([(key("1"), [])], else_=[play(A)]))))
    ok(program(while_(key("q"), log(text("not busy: the condition may change")))))


def test_values_and_variables() -> None:
    doc = program(
        set_var("n", arith("MULTIPLY", num(2), num(21)), id_="s1"),
        change("n", num(-2), id_="c1"),
        set_var("t", join(text("n="), var("n")), id_="s2"),
        log(var("t"), id_="l1"),
        set_signal("door", var("n"), id_="sig"),
        tops=[blk("math_modulo", "orphan_mod", inputs={"DIVIDEND": num(5), "DIVISOR": num(3)})],
        variables=[("n", "count", "Number"), ("t", "msg", "String")],
    )
    r = compile_program(doc)
    assert r.ast is not None and codes(r) == {"unreachable:orphan_mod": "warning"}
    assert [v.model_dump() for v in r.ast.variables] == [
        {"name": "count", "type": "number", "initial": 0.0},
        {"name": "msg", "type": "text", "initial": ""},
    ]
    s1, c1, s2, _l1, sig = r.ast.body
    assert isinstance(s1, ps.SetVarStmt) and s1.name == "count" and isinstance(s1.value, ps.Arith)
    assert isinstance(c1, ps.ChangeVarStmt) and isinstance(sig, ps.SetSignalStmt)
    assert isinstance(s2, ps.SetVarStmt) and isinstance(s2.value, ps.Join) and len(s2.value.parts) == 2
    assert r.refs.signals == ["door"]


def test_one_block_conditions_compile_to_compare() -> None:
    doc = program(
        if_(
            [
                (
                    blk("hb_joint_compare", "jc", fields={"JOINT": "elbow_flex", "OP": "GT", "DEG": 40}),
                    [wait(1)],
                ),
                (
                    blk("hb_motor_temp_compare", "mt", fields={"MOTOR": "any", "OP": "GT", "TEMP": 55}),
                    [wait(1)],
                ),
                (blk("hb_signal_equals", "se", fields={"NAME": "door", "VALUE": "1"}), [wait(1)]),
                (
                    blk("hb_message_received", "mr", fields={"SOURCE": "mqtt", "NAME": "line/start"}),
                    [wait(1)],
                ),
                (blk("hb_near_pose", "np", fields={"POSE": "home", "TOLERANCE": 5}), [wait(1)]),
            ]
        )
    )
    ast = ok(doc)
    br = ast.body[0].branches  # type: ignore[union-attr]
    jc = br[0].cond
    assert isinstance(jc, ps.Compare) and jc.op == "gt" and jc.id == "jc"
    assert isinstance(jc.left, ps.JointValue) and jc.left.joint == "elbow_flex" and jc.left.id == "jc:joint"
    mt = br[1].cond
    assert isinstance(mt, ps.Compare) and isinstance(mt.left, ps.MotorTemp) and mt.left.motor is None
    se = br[2].cond
    assert isinstance(se, ps.SignalEquals) and se.value == 1.0
    mr = br[3].cond
    assert isinstance(mr, ps.MessageReceived) and mr.name == "line/start"
    assert isinstance(br[4].cond, ps.NearPose) and br[4].cond.tolerance_deg == 5


def test_shadow_blocks_fill_empty_inputs() -> None:
    w = blk("hb_wait", "w", shadow={"SECONDS": num(0.5)})
    ast = ok(program(w))
    assert isinstance(ast.body[0], ps.WaitStmt) and isinstance(ast.body[0].seconds, ps.NumberLit)


def test_wait_until_defaults_and_on_timeout() -> None:
    ast = ok(program(wait_until(key("1"), id_="w")), wait_timeout_s=12)
    assert ast.body[0].timeout_s == 12 and ast.body[0].on_timeout is None  # type: ignore[union-attr]
    ast = ok(program(wait_until(key("1"), timeout=2, on_timeout=[log(text("late"))], id_="w")))
    assert ast.body[0].timeout_s == 2 and len(ast.body[0].on_timeout or []) == 1  # type: ignore[union-attr]


def test_ask_run_model_and_stop() -> None:
    doc = program(
        ask("Which bin?", "left, right,left", "v", timeout=5, id_="a"),
        run_model_until("act", sees("cubes", "red"), timeout=8, on_timeout=[stop()], id_="rm"),
        stop(id_="s"),
        variables=[("v", "bin", "String")],
    )
    ast = ok(doc)
    a, rm, s = ast.body
    assert isinstance(a, ps.AskStmt) and a.choices == ["left", "right"] and a.var == "bin"
    assert isinstance(rm, ps.RunModelStmt) and rm.timeout_s == 8 and rm.until is not None
    assert isinstance(s, ps.StopStmt)


def test_iterators_cover_nested_bodies() -> None:
    ast = ok(ab_program(A, B))
    kinds = [s.kind for s, _ in iter_stmts(ast.body)]
    assert kinds == ["forever", "wait_until", "if", "play_trajectory", "play_trajectory"]
    depths = {s.id: d for s, d in iter_stmts(ast.body)}
    assert depths["loop"] == 0 and depths["play_a"] == 1
    assert {e.kind for e in iter_exprs(ast.body)} == {"logic", "camera_sees"}


# =========================================================================== validator
def _tr(tid: str, status: str = "ready") -> ps.Trajectory:
    pose = {"shoulder_pan.pos": 0.0, "elbow_flex.pos": 0.0, "gripper.pos": 50.0}
    return ps.Trajectory(
        id=tid,
        name=tid[-4:],
        robot="desk",
        created_at="",
        updated_at="",
        fps=30,
        joints=list(pose),
        samples=10,
        raw_duration_s=1.0,
        trim=ps.TrimRange(start_s=0, end_s=0),
        suggested_trim=ps.TrimRange(start_s=0, end_s=0),
        duration_s=1.0,
        start_pose=pose,
        end_pose=pose,
        max_speed_deg_s=10.0,
        calibration_hash="x",
        status=status,  # type: ignore[arg-type]
        checked_at=None,
        keyframe_cameras=[],
        keyframe_times=[],
    )


CUBES = ps.Detector(
    id="cubes",
    robot="desk",
    name="Cubes",
    created_at="",
    updated_at="",
    model_file=None,
    model_sha256=None,
    labels=["red", "blue"],
    spec=ps.ColorDetectorSpec(
        kind="color",
        camera="wrist",
        roi=ps.Roi(x=0, y=0, w=1, h=1),
        rules=[
            ps.ColorRule(label="red", h_min=170, h_max=10),
            ps.ColorRule(label="blue", h_min=100, h_max=130),
        ],
    ),
)
CLASSIFIER = CUBES.model_copy(
    update={
        "id": "clf",
        "spec": ps.ClassifierDetectorSpec(kind="classifier", camera="wrist", labels=["a", "b"]),
        "labels": ["a", "b"],
    }
)


def ctx(**kw: Any) -> ValidationContext:
    trs = {
        A: _tr(A),
        B: _tr(B, "draft"),
        "t_20261116_120000_cccc": _tr("t_20261116_120000_cccc", "needs_check"),
    }
    poses = {
        "home": ps.Pose(
            name="home",
            positions={"elbow_flex.pos": 0.0},
            calibration_hash="x",
            created_at="",
            needs_check=False,
        ),
        "old": ps.Pose(
            name="old",
            positions={"elbow_flex.pos": 0.0},
            calibration_hash="y",
            created_at="",
            needs_check=True,
        ),
    }
    dets = {"cubes": CUBES, "clf": CLASSIFIER}

    def lookup(table: dict[str, Any]) -> Any:
        def get(key: str) -> Any:
            if key not in table:
                raise StationError("not_found", key)
            return table[key]

        return get

    base: dict[str, Any] = {
        "trajectory": lookup(trs),
        "pose": lookup(poses),
        "detector": lookup(dets),
        "model_exists": lambda k: k == "act",
        "motors": ["shoulder_pan", "elbow_flex", "gripper"],
        "cameras": ["wrist"],
        "rest_pose": None,
        "allow_fast_replay": False,
        "max_approach_deg": 30.0,
    }
    base.update(kw)
    return ValidationContext(**base)


def issues_of(doc: dict[str, Any], c: ValidationContext | None = None) -> dict[str, str]:
    ast = ok(doc)
    return {i.id: i.severity for i in validate_ast(ast, c or ctx())}


def test_validator_accepts_the_ab_program() -> None:
    assert issues_of(ab_program(A, A)) == {}


@pytest.mark.parametrize(
    ("stmt", "issue"),
    [
        (play("t_20261116_120000_ffff", id_="p"), "unknown_trajectory:p"),
        (play(B, id_="p"), "trajectory_draft:p"),
        (play("t_20261116_120000_cccc", id_="p"), "trajectory_needs_check:p"),
        (play(A, speed=120, id_="p"), "fast_replay_not_allowed:p"),
        (move("nowhere", id_="m"), "unknown_pose:m"),
        (move("old", id_="m"), "pose_needs_check:m"),
        (go_home(id_="h"), "no_rest_pose:h"),
        (run_model_until("ghost", key("1"), 5, id_="rm"), "unknown_model:rm"),
        (wait_until(sees("nope", "red", id_="c")), "unknown_detector:c"),
        (wait_until(sees("cubes", "green", id_="c")), "unknown_label:c"),
        (wait_until(sees("cubes", "red", camera="top", id_="c")), "unknown_camera:c"),
        (wait_until(sees("clf", "a", id_="c")), "detector_no_model:c"),
        (
            wait_until(blk("hb_joint_compare", "jc", fields={"JOINT": "knee", "OP": "LT", "DEG": 1})),
            "unknown_joint:jc",
        ),
        (
            wait_until(blk("hb_near_pose", "np", fields={"POSE": "nowhere", "TOLERANCE": 3})),
            "unknown_pose:np",
        ),
    ],
)
def test_validator_errors(stmt: dict[str, Any], issue: str) -> None:
    found = issues_of(program(stmt))
    assert found.get(issue) == "error", found


def test_fast_replay_needs_confirmation_when_the_profile_allows_it() -> None:
    assert issues_of(program(play(A, speed=120, id_="p")), ctx(allow_fast_replay=True)) == {
        "fast_replay:p": "confirm"
    }


def test_first_motion_far_from_the_arm_is_a_warning() -> None:
    doc = program(play(A, id_="p"))
    near = ctx(positions={"shoulder_pan.pos": 10.0, "elbow_flex.pos": -5.0, "gripper.pos": 0.0})
    far = ctx(positions={"shoulder_pan.pos": 80.0, "elbow_flex.pos": 0.0, "gripper.pos": 0.0})
    assert issues_of(doc, near) == {}
    assert issues_of(doc, far) == {"first_motion_far:p": "warning"}


def _program(doc: dict[str, Any], **kw: Any) -> ps.Program:
    r = compile_program(doc)
    return ps.Program(
        id="ab",
        name="A/B",
        robot="desk",
        version=kw.pop("version", 2),
        created_at="",
        updated_at="",
        editor=doc,
        buttons=[],
        ast=r.ast,
        issues=r.issues,
        refs=r.refs,
        dry_run_version=kw.pop("dry_run_version", None),
    )


def test_check_report_and_blocking_issues() -> None:
    p = _program(program(repeat(num(2), relax(id_="r")), play(A, speed=120, id_="p")))
    rep = check_program(p, ctx(allow_fast_replay=True, rest_pose={"elbow_flex.pos": 0.0}))
    assert (
        rep.ok and rep.dry_run_required and {i.id for i in rep.issues} == {"relax_in_loop:r", "fast_replay:p"}
    )
    assert {i.id for i in blocking(rep, [])} == {"relax_in_loop:r", "fast_replay:p"}
    assert blocking(rep, ["relax_in_loop:r", "fast_replay:p"]) == []
    done = _program(program(wait(1)), version=3, dry_run_version=3)
    assert not check_program(done, ctx()).dry_run_required
    assert not check_program(_program(program(wait(1))), ctx(require_dry_run=False)).dry_run_required
    bad = _program(program(blk("hb_wait", "w")))
    rep = check_program(bad, ctx())
    assert not rep.ok and rep.ast is None and [i.id for i in blocking(rep, [])] == ["missing_input:w"]
