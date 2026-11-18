"""Field report 0.2.9 (customer check_ver_2.9, 2026-11-18).

D-24: "the first motion starts far from the arm's pose" was a warning that stayed on the program
after the run. The player always approaches the first sample slowly (minimum-jerk), so this is
information, not a problem: the issue has the new severity ``info`` (never blocks, never needs a
confirmation, does not make a check "not ok") and disappears once the arm is within the limit.

D-25 / QD-35: the Station itself refuses a server address that is not http(s) or is a file-share
link (OneDrive in all its forms, SharePoint, Google Drive, Dropbox, Box, WeTransfer, iCloud).
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from blocks_dsl import play, program
from conftest import STATION_DIR
from test_compiler import A, _program, ctx

from hibiscus_station.programs import schemas as ps
from hibiscus_station.programs.validator import blocking, check_program

API = "/api/v1"
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


# =========================================================================== D-25 / QD-35: server address
CASES: list[list[Any]] = json.loads((STATION_DIR / "tests" / "server_urls.json").read_text(encoding="utf-8"))[
    "cases"
]


@pytest.mark.parametrize(("url", "problem"), CASES)
def test_server_url_problem(url: str, problem: str | None) -> None:
    from hibiscus_station.server_url import server_url_problem

    assert server_url_problem(url) == problem


CUSTOMER_ONEDRIVE = "https://word.cloud.microsoft/open/onedrive/?docId=0123456789ABCDEF%21s1a2b3c4d5e6f&driveId=0123456789ABCDEF"


@pytest.mark.parametrize(
    ("url", "code"),
    [
        (CUSTOMER_ONEDRIVE, "server_url_file_share"),
        ("https://contoso-my.sharepoint.com/:f:/g/personal/x/EabC?e=1", "server_url_file_share"),
        ("ftp://hibiscus.example.org", "server_url_invalid"),
        ("hibiscus server", "server_url_invalid"),
    ],
)
def test_pair_refuses_a_file_share_or_non_http_address(client: Any, url: str, code: str) -> None:
    """Defence in depth: the Station refuses before any request leaves it (no token sent anywhere)."""
    r = client.post(f"{API}/server/pair", json={"url": url, "token": "hbp_" + "x" * 40})
    assert r.status_code == 422, r.text
    assert r.json()["code"] == code
    assert not client.get(f"{API}/server").json()["paired"]
