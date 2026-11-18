"""Field report 0.2.9 (customer check_ver_2.9, 2026-11-18).

D-24: "the first motion starts far from the arm's pose" was a warning that stayed on the program
after the run. The player always approaches the first sample slowly (minimum-jerk), so this is
information, not a problem: the issue has the new severity ``info`` (never blocks, never needs a
confirmation, does not make a check "not ok") and disappears once the arm is within the limit.
"""

from __future__ import annotations

import json
from typing import Any

from blocks_dsl import play, program
from conftest import STATION_DIR
from test_compiler import A, _program, ctx

from hibiscus_station.programs import schemas as ps
from hibiscus_station.programs.validator import blocking, check_program

FAR = {"shoulder_pan.pos": 80.0, "elbow_flex.pos": 0.0, "gripper.pos": 0.0}
NEAR = {"shoulder_pan.pos": 10.0, "elbow_flex.pos": -5.0, "gripper.pos": 0.0}


def _check(positions: dict[str, float]) -> ps.CheckReport:
    return check_program(_program(program(play(A, id_="p"))), ctx(positions=positions))


def test_first_motion_far_is_information_not_a_warning() -> None:
    rep = _check(FAR)
    [far] = [i for i in rep.issues if i.code == "first_motion_far"]
    assert far.severity == "info"
    assert far.block_id == "p"
    assert far.params == {"deg": 80.0, "max_deg": 30.0}
    assert rep.ok
    assert blocking(rep, []) == []
    assert not [i for i in rep.issues if i.severity == "warning"]


def test_first_motion_info_goes_away_once_the_arm_is_near() -> None:
    assert [i.code for i in _check(FAR).issues] == ["first_motion_far"]
    assert _check(NEAR).issues == []
    assert _check({}).issues == []  # pose unknown (no robot): nothing to say


def test_info_severity_is_in_the_api_contract() -> None:
    doc: dict[str, Any] = json.loads((STATION_DIR / "openapi.json").read_text(encoding="utf-8"))
    severity = doc["components"]["schemas"]["CheckIssue"]["properties"]["severity"]
    assert "info" in severity["enum"]
    ps.CheckIssue.model_validate(
        {
            "id": "first_motion_far:p",
            "code": "first_motion_far",
            "severity": "info",
            "block_id": "p",
            "message_key": "programs.issues.first_motion_far",
            "params": {},
        }
    )
