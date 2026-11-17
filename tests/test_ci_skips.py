"""NFR-18 / AT-2: the published skip list (tools/ci/allowed-skips.toml) and its CI check."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("check_skips", ROOT / "tools" / "ci" / "check_skips.py")
assert _spec is not None and _spec.loader is not None
check_skips = importlib.util.module_from_spec(_spec)
sys.modules["check_skips"] = check_skips
_spec.loader.exec_module(check_skips)


def _junit(tmp_path: Path, cases: list[tuple[str, str, str | None]]) -> Path:
    rows = []
    for cls, name, skip in cases:
        inner = f'<skipped type="pytest.skip" message="{skip}"/>' if skip is not None else ""
        rows.append(f'<testcase classname="{cls}" name="{name}" time="0.1">{inner}</testcase>')
    path = tmp_path / "junit.xml"
    path.write_text(
        f'<?xml version="1.0"?><testsuites><testsuite name="pytest">{"".join(rows)}</testsuite></testsuites>',
        encoding="utf-8",
    )
    return path


def test_every_entry_is_complete_and_names_a_real_test() -> None:
    allowed = check_skips.load_allowed()
    assert allowed
    for a in allowed:
        module, _, name = a.test.partition("::")
        src = (ROOT / module).read_text(encoding="utf-8")
        assert not name or f"def {name.split('[')[0]}(" in src, a.test
        assert a.reason and a.covered_by


def test_windows_pty_skips_are_allowed_and_nothing_else(tmp_path: Path) -> None:
    junit = _junit(
        tmp_path,
        [
            ("", "tests.test_calib_simple", "collection skipped"),  # module-level skip
            (
                "tests.test_device_lost",
                "test_bus_stops_retrying_a_lost_device",
                "pseudo-terminals are POSIX only",
            ),
            ("tests.test_traj_sessions", "test_replay_at_50_and_100_percent[normal]", None),
        ],
    )
    assert check_skips.check("windows", [junit], check_skips.load_allowed()) == []
    # the same skips on Linux are not allowed: the emulator runs there
    errors = check_skips.check("linux", [junit], check_skips.load_allowed())
    assert len(errors) == 2 and all("not in tools/ci/allowed-skips.toml" in e for e in errors)


@pytest.mark.parametrize(
    ("cls", "name"),
    [
        ("tests.test_traj_sessions", "test_replay_at_50_and_100_percent[slow-runner]"),
        ("tests.test_device_lost", "test_bus_stops_retrying_a_lost_device_extra"),  # prefix of another name
        ("", "tests.test_api"),
    ],
)
def test_an_unlisted_skip_fails(tmp_path: Path, cls: str, name: str) -> None:
    junit = _junit(tmp_path, [(cls, name, "flaky on CI")])
    assert check_skips.check("windows", [junit], check_skips.load_allowed())


def test_an_empty_report_fails(tmp_path: Path) -> None:
    assert check_skips.check("linux", [_junit(tmp_path, [])], check_skips.load_allowed())
