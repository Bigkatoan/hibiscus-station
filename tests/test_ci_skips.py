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


def test_macos_pty_emulator_skips_are_allowed_with_the_real_reason(tmp_path: Path) -> None:
    """QD-7: on macOS a pty refuses pyserial's 1 Mbps ioctl (ENOTTY), so the STS-emulator tests may
    skip there, with that reason; the doctor tests are not on the list (they must run, QD-4 / QD-7)."""
    junit = _junit(
        tmp_path,
        [
            ("", "tests.test_real_stack", "collection skipped"),
            ("tests.test_teleop_latency", "test_station_teleop_latency_matches_lelab", "pty at 1 Mbps"),
            (
                "tests.test_device_lost",
                "test_pty_closed_mid_teleop_then_back_under_a_new_name",
                "pty at 1 Mbps",
            ),
        ],
    )
    allowed = check_skips.load_allowed()
    assert check_skips.check("macos", [junit], allowed) == []
    assert len(check_skips.check("linux", [junit], allowed)) == 3
    for a in allowed:
        if "macos" in a.platforms and "windows" in a.platforms:
            assert "ENOTTY" in a.reason and not a.covered_by.startswith("Linux and macOS"), a.test
    doctor = _junit(tmp_path, [("", "tests.test_doctor", "collection skipped")])
    assert check_skips.check("macos", [doctor], allowed) and check_skips.check("windows", [doctor], allowed)


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


def test_the_emulated_e2e_flow_may_skip_on_windows_only(tmp_path: Path) -> None:
    junit = _junit(
        tmp_path,
        [
            ("tests.e2e.test_station_ui", "test_station_ui_end_to_end[mock-vi]", None),
            (
                "tests.e2e.test_station_ui",
                "test_station_ui_end_to_end[sts-vi]",
                "the STS emulator needs pseudo-terminals",
            ),
        ],
    )
    assert check_skips.check("windows", [junit], check_skips.load_allowed()) == []
    assert len(check_skips.check("linux", [junit], check_skips.load_allowed())) == 1


def test_ci_runs_the_e2e_suite_in_the_at2_browsers_and_fails_on_a_missing_browser() -> None:
    """AT-2 / QD-9: e2e in Chromium + Firefox on Linux and in Edge on windows-latest."""
    import yaml

    ci = yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"))
    job = ci["jobs"]["e2e"]
    assert job["env"]["HIBISCUS_E2E_REQUIRED"] == "1"
    assert job["env"]["HIBISCUS_E2E_BROWSER"] == "${{ matrix.browser }}"
    rows = {(r["platform"], r["browser"]): r for r in job["strategy"]["matrix"]["include"]}
    assert set(rows) == {("linux", "chromium"), ("linux", "firefox"), ("windows", "msedge")}
    assert rows["windows", "msedge"]["os"] == "windows-latest"
    assert all(rows[k]["os"].startswith("ubuntu") for k in [("linux", "chromium"), ("linux", "firefox")])
    assert rows["linux", "chromium"]["tests"] == "tests/e2e"  # the whole suite, screen matrix included
    assert rows["linux", "firefox"]["install"] == "--with-deps firefox"
    for r in rows.values():
        assert r["tests"].startswith("tests/e2e")
    steps = " ".join(str(s.get("run", "")) for s in job["steps"])
    assert "-m e2e" in steps and 'check_skips.py --platform "${{ matrix.platform }}"' in steps
    assert "pnpm install --frozen-lockfile" in steps  # axe-core for the screen matrix
    assert (
        "grep -q HIBISCUS_E2E_BROWSER tests/e2e/conftest.py" in steps
    )  # a browser the fixture ignores fails


def test_ci_runs_on_a_push_to_a_release_branch() -> None:
    """AT-2 is checked on the exact commit of the milestone build, which lives on release/* before main."""
    import yaml

    ci = yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"))
    on = ci.get("on", ci.get(True))  # PyYAML reads the bare key `on` as True
    assert "release/**" in on["push"]["branches"] and "main" in on["push"]["branches"]


def test_the_e2e_fixture_launches_the_browser_the_job_names() -> None:
    """QD-9: HIBISCUS_E2E_BROWSER picks the Playwright engine; Edge is Chromium on the msedge channel."""
    spec = importlib.util.spec_from_file_location("e2e_support", ROOT / "tests" / "e2e" / "e2e_support.py")
    assert spec and spec.loader
    support = importlib.util.module_from_spec(spec)
    sys.modules["e2e_support"] = support  # its dataclasses look their module up
    try:
        spec.loader.exec_module(support)
    finally:
        del sys.modules["e2e_support"]
    assert support.browser_engine("chromium") == ("chromium", {})
    assert support.browser_engine("firefox") == ("firefox", {})
    assert support.browser_engine("msedge") == ("chromium", {"channel": "msedge"})
    with pytest.raises(ValueError, match="webkit"):
        support.browser_engine("webkit")  # not an AT-2 browser: never a silent Chromium run
    conftest = (ROOT / "tests" / "e2e" / "conftest.py").read_text(encoding="utf-8")
    assert "browser_engine(BROWSER)" in conftest and "pw.chromium.launch()" not in conftest
