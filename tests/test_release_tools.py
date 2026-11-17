"""Release tooling (tools/release): version consistency (FR-76 / D-18) and the pinned installer
assets (ADR-13 / P-1). Fast, offline; the full build + install runs in tools/release/dry_run.sh."""

from __future__ import annotations

import importlib.util
import os
import re
import shutil
import sys
import zipfile
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools" / "release"


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, TOOLS / f"{name}.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


check_versions = _load("check_versions")
build_release = _load("build_release")


# =========================================================================== FR-76 / D-18
def test_the_repository_uses_one_version_everywhere() -> None:
    assert check_versions.check() == []


def _tree(tmp_path: Path) -> Path:
    files = [
        "hibiscus_station/__init__.py",
        "pyproject.toml",
        "uv.lock",
        "CITATION.cff",
        "web/package.json",
        "deploy/install.sh",
        "deploy/.env.example",
        "CHANGELOG.md",
        *check_versions.DOCS,
    ]
    for rel in files:
        src = ROOT / rel
        if src.is_file():
            (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, tmp_path / rel)
    return tmp_path


@pytest.mark.parametrize(
    ("rel", "old", "new", "needle"),
    [
        ("README.md", "hibiscus-station:{v}-cpu", "hibiscus-station:0.2.1-cpu", "README.md:"),
        ("README.vi.md", "…:{v}-jetson", "…:0.2.1-jetson", "README.vi.md:"),
        (
            "docs/deploy.md",
            "download/v{v}/hibiscus_station-{v}",
            "download/v0.2.1/hibiscus_station-0.2.1",
            "deploy.md",
        ),
        ("deploy/install.sh", 'VERSION="{v}"', 'VERSION="0.2.1"', "deploy/install.sh"),
        ("deploy/.env.example", "STATION_TAG={v}-cpu", "STATION_TAG=0.2.1-cpu", ".env.example"),
        ("web/package.json", '"version": "{v}"', '"version": "0.2.1"', "web/package.json"),
        ("CITATION.cff", 'version: "{v}"', 'version: "0.2.1"', "CITATION.cff"),
        ("CHANGELOG.md", "...HEAD\n", "...main\n", "[Unreleased]"),
    ],
)
def test_a_stale_version_anywhere_fails(tmp_path: Path, rel: str, old: str, new: str, needle: str) -> None:
    root = _tree(tmp_path)
    v = check_versions.station_version(root)
    path = root / rel
    text = path.read_text(encoding="utf-8")
    assert old.format(v=v) in text, (rel, old)
    path.write_text(text.replace(old.format(v=v), new, 1), encoding="utf-8")
    errors = check_versions.check(root)
    assert errors and any(needle in e for e in errors), errors


def test_changelog_needs_a_section_and_links_for_the_version() -> None:
    repo = check_versions.REPO
    text = (
        "## [Unreleased]\n\n## [1.0.0] - x\n\n## [0.9.0] - x\n\n"
        f"[Unreleased]: {repo}/compare/v1.0.0...HEAD\n"
        f"[1.0.0]: {repo}/compare/v0.9.0...v1.0.0\n"
        f"[0.9.0]: {repo}/releases/tag/v0.9.0\n"
    )
    assert check_versions.check_changelog(text, "1.0.0") == []
    assert check_versions.check_changelog(text, "1.0.1")  # no section for the package version
    broken = text.replace(f"[1.0.0]: {repo}/compare/v0.9.0...v1.0.0\n", "")
    assert any("[1.0.0] link" in e for e in check_versions.check_changelog(broken, "1.0.0"))


# =========================================================================== ADR-13 assets
def test_export_splits_pins_from_git_dependencies() -> None:
    export = (
        "fastapi==0.163.1\n"
        "nvidia-cublas==13.4.1.3 ; sys_platform == 'linux'\n"
        "hibiscus @ git+https://github.com/Bigkatoan/Hibiscus.git@" + "a" * 40 + "#subdirectory=cli\n"
        "lerobot @ git+https://github.com/huggingface/lerobot.git@" + "b" * 40 + "\n"
    )
    pins, git = build_release.split_export(export)
    assert pins == ["fastapi==0.163.1", "nvidia-cublas==13.4.1.3 ; sys_platform == 'linux'"]
    assert [(d.name, d.rev, d.subdirectory) for d in git] == [
        ("hibiscus", "a" * 40, "cli"),
        ("lerobot", "b" * 40, None),
    ]
    with pytest.raises(SystemExit):
        build_release.split_export("lerobot @ git+https://github.com/x/y.git@main\n")  # not a full commit
    with pytest.raises(SystemExit):
        build_release.split_export("fastapi>=0.115\n")  # not pinned


def test_override_names_the_whole_self_extra_closure(tmp_path: Path) -> None:
    """An override replaces every requirement on the package, its own self-references too: with only
    ``[feetech,dataset]`` the dry run installed lerobot without av, pyserial and rustypot."""
    wheel = tmp_path / "lerobot-0.7.1-py3-none-any.whl"
    meta = "\n".join(
        [
            "Metadata-Version: 2.4",
            "Name: lerobot",
            "Version: 0.7.1",
            'Requires-Dist: lerobot[av-dep]; extra == "dataset"',
            'Requires-Dist: datasets<6,>=4.8; extra == "dataset"',
            'Requires-Dist: lerobot[serial-motors]; extra == "feetech"',
            'Requires-Dist: lerobot[pyserial-dep,rustypot-dep]; extra == "serial-motors"',
            'Requires-Dist: av<16,>=15; extra == "av-dep"',
            'Requires-Dist: lerobot[pi]; extra == "all"',
        ]
    )
    with zipfile.ZipFile(wheel, "w") as z:
        z.writestr("lerobot-0.7.1.dist-info/METADATA", meta)
    closure = build_release.extras_closure(wheel, ["feetech", "dataset"])
    assert closure == ["feetech", "dataset", "serial-motors", "av-dep", "pyserial-dep", "rustypot-dep"]
    assert build_release.extras_spec(closure).startswith("[feetech,dataset,")
    assert build_release.requested_extras("lerobot") == ["feetech", "dataset"]


def test_packages_from_another_index_are_pinned_by_url_per_platform() -> None:
    lock = {
        "package": [
            {"name": "fastapi", "version": "1", "source": {"registry": build_release.PYPI}},
            {
                "name": "torchcodec",
                "version": "0.17.0",
                "source": {"registry": build_release.PYPI},
                "resolution-markers": ["sys_platform == 'win32'"],
            },
            {
                "name": "torchcodec",
                "version": "0.17.0+cpu",
                "source": {"registry": "https://download.pytorch.org/whl/cpu"},
                "wheels": [
                    {
                        "url": "https://download.pytorch.org/whl/cpu/torchcodec-0.17.0%2Bcpu-cp312-cp312-manylinux_2_28_x86_64.whl",
                        "hash": "sha256:" + "c" * 64,
                    },
                    {
                        "url": "https://download.pytorch.org/whl/cpu/torchcodec-0.17.0%2Bcpu-cp313-cp313-manylinux_2_28_x86_64.whl",
                        "hash": "sha256:" + "d" * 64,
                    },
                ],
            },
        ]
    }
    lines, names = build_release.index_overrides(lock)
    assert names == {"torchcodec"}
    assert lines == [
        "torchcodec==0.17.0 ; (sys_platform == 'win32')",
        "torchcodec @ https://download.pytorch.org/whl/cpu/torchcodec-0.17.0%2Bcpu-cp312-cp312-manylinux_2_28_x86_64.whl"
        "#sha256=" + "c" * 64 + " ; sys_platform == 'linux' and platform_machine == 'x86_64'",
    ]


def test_installer_is_ascii_and_keeps_vietnamese_text() -> None:
    text = build_release.render_installer(
        version="9.9.9", base_url="https://example.invalid/r", uv_sha256="e" * 64
    )
    assert text.isascii()
    assert "$Version = '9.9.9'" in text and "$UvSha256 = '" + "e" * 64 + "'" in text
    assert "$([char]0x0110)ang c$([char]0x00E0)i" in text  # "Đang cài" survives Windows PowerShell 5.1
    assert "--constraints" in text and "--overrides" in text and "--force" in text
    assert "--torch-backend" not in text  # the lock's torch, not a re-resolved one
    with pytest.raises(SystemExit):
        build_release.ps_ascii("# Hiệu chỉnh\n")  # non-ASCII outside a string


def test_wheel_platform_markers() -> None:
    m = build_release.wheel_marker
    assert m("x-1-cp312-cp312-win_amd64.whl") == "sys_platform == 'win32' and platform_machine == 'AMD64'"
    assert (
        m("x-1-cp312-cp312-macosx_14_0_arm64.whl")
        == "sys_platform == 'darwin' and platform_machine == 'arm64'"
    )
    assert m("x-1-py3-none-any.whl") == ""
    with pytest.raises(ValueError):
        m("x-1-cp311-cp311-win_amd64.whl")


def test_pre_release_versions_are_matched_whole(tmp_path: Path) -> None:
    """A pre-release (1.0.0a1, the M0 build) and its release number (1.0.0) are different versions."""
    root = _tree(tmp_path)
    v = check_versions.station_version(root)
    other = v.split("a")[0] if check_versions.is_pre_release(v) else f"{v}a1"
    readme = root / "README.md"
    readme.write_text(
        readme.read_text(encoding="utf-8").replace(f":{v}-cpu", f":{other}-cpu", 1), encoding="utf-8"
    )
    assert any("README.md" in e and f"{other} != {v}" in e for e in check_versions.check(root))


def test_compare_envs_requires_the_exact_tested_set() -> None:
    compare_envs = _load("compare_envs")
    ref = {"torch": "2.15.0", "lerobot": "0.7.1", "hibiscus-station": "0.2.8"}
    assert compare_envs.compare({**ref}, ref, "0.2.8") == []
    assert compare_envs.compare({**ref, "torch": "2.16.0"}, ref, "0.2.8") == [
        "torch: installed 2.16.0, tested 2.15.0"
    ]
    assert compare_envs.compare({**ref, "six": "1"}, ref, "0.2.8") == ["six: installed 1, tested None"]
    assert compare_envs.compare({"torch": "2.15.0", "lerobot": "0.7.1"}, ref, "0.2.8")[0].startswith(
        "hibiscus-station None"
    )


def test_installer_uses_the_ci_uv_version() -> None:
    """The uv that install.ps1 downloads is the uv CI tests with."""
    for wf in ("ci.yml", "release.yml"):
        text = (ROOT / ".github" / "workflows" / wf).read_text(encoding="utf-8")
        assert f'UV_VERSION: "{build_release.UV_VERSION}"' in text, wf


def test_installer_never_redirects_native_stderr_under_stop() -> None:
    """Windows PowerShell 5.1 raises NativeCommandError on redirected stderr of a native command when
    $ErrorActionPreference is 'Stop': every redirected uv call runs under 'Continue'."""
    lines = (TOOLS / "install.ps1.in").read_text(encoding="utf-8").splitlines()
    eap = "Stop"
    for line in lines:
        code = line.split("#", 1)[0]
        if "$ErrorActionPreference = 'Continue'" in code:
            eap = "Continue"
        elif "$ErrorActionPreference = 'Stop'" in code:
            eap = "Stop"
        if "& $uv" in code and ("2>" in code or "*>" in code):
            assert eap == "Continue", line


def test_installer_reads_uv_output_without_colour() -> None:
    """QD-2: with FORCE_COLOR=1 (the CI runner, some terminals) uv colours a path even into a pipe;
    Windows PowerShell 5.1 then failed on Join-Path ("drive '<ESC>[36mC' does not exist"). Every uv
    call whose output the script reads, and the CI step that reads uv's tool dirs, asks for no colour."""
    code = [ln.split("#", 1)[0] for ln in (TOOLS / "install.ps1.in").read_text(encoding="utf-8").splitlines()]
    read = [c for c in code if "& $uv" in c and re.search(r"=\s*\(?\(?\s*& \$uv|& \$uv[^|]*\|", c)]
    assert read, "no uv output is read?"
    for c in read:
        assert "--color never" in c, c
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    for line in ci.splitlines():
        if "$(& $uv" in line:
            assert "--color never" in line, line


@pytest.mark.parametrize(
    ("doc", "needle"),
    [
        ("README.md", "it is only reachable by its versioned link, the line above"),
        ("README.vi.md", "nên chỉ cài được bằng liên kết có số phiên bản, tức là dòng ở trên"),
        ("docs/deploy.md", "so it is only reachable by its versioned link"),
    ],
)
def test_install_docs_say_a_pre_release_needs_its_versioned_link(doc: str, needle: str) -> None:
    """GitHub's releases/latest skips pre-releases: the M0 test build is installed by its own link."""
    assert needle in " ".join((ROOT / doc).read_text(encoding="utf-8").split())


# =========================================================================== QD-1
def test_the_m0_build_is_the_pre_release_1_0_0a1() -> None:
    """QD-1: the M0 candidate must not carry 0.2.8, which is already released (and has no installer)."""
    assert check_versions.station_version() == "1.0.0a1"
    assert check_versions.is_pre_release("1.0.0a1") and not check_versions.is_pre_release("1.0.0")


@pytest.mark.parametrize("doc", ["README.md", "README.vi.md", "docs/deploy.md"])
def test_a_pre_release_doc_never_points_at_releases_latest(tmp_path: Path, doc: str) -> None:
    """QD-1: releases/latest/download/install.ps1 was a 404 (latest = 0.2.8, which has no installer)
    and can never serve a pre-release."""
    root = _tree(tmp_path)
    v = check_versions.station_version(root)
    path = root / doc
    text = path.read_text(encoding="utf-8")
    line = f"releases/download/v{v}/install.ps1"
    assert line in text, doc
    path.write_text(text.replace(line, "releases/latest/download/install.ps1", 1), encoding="utf-8")
    assert any(doc in e and "releases/latest" in e for e in check_versions.check(root))


def test_a_pre_release_is_listed_under_unreleased() -> None:
    """QD-15 / QD-1: the pre-release's changes are in [Unreleased] (its compare link resolves before
    the tag exists) and name the version; an empty [Unreleased] fails."""
    repo = check_versions.REPO
    links = f"[Unreleased]: {repo}/compare/v0.2.8...HEAD\n[0.2.8]: {repo}/releases/tag/v0.2.8\n"
    good = (
        "## [Unreleased]\n\nIn the test build 1.0.0a1.\n\n### Added\n- a thing\n\n## [0.2.8] - x\n\n" + links
    )
    assert check_versions.check_changelog(good, "1.0.0a1") == []
    empty = "## [Unreleased]\n\n## [0.2.8] - x\n\n" + links
    assert any("lists no change" in e for e in check_versions.check_changelog(empty, "1.0.0a1"))
    unnamed = good.replace("In the test build 1.0.0a1.\n\n", "")
    assert any("does not name" in e for e in check_versions.check_changelog(unnamed, "1.0.0a1"))
    own = good.replace("## [0.2.8] - x", "## [1.0.0a1] - x\n\n## [0.2.8] - x")
    assert any("own section" in e for e in check_versions.check_changelog(own, "1.0.0a1"))


@pytest.mark.parametrize("version", ["1.0.0a1", "1.0.0"])
def test_installer_links_resolve_for_its_kind_of_release(version: str) -> None:
    """QD-1: the installer's update / roll-back lines: a pre-release never names releases/latest;
    roll back is always this version's own installer."""
    text = build_release.render_installer(
        version=version, base_url="https://example.invalid/r", uv_sha256="e" * 64
    )
    assert "releases/download/v$Version/install.ps1" in text
    assert f"releases/download/v{version}/install.ps1" in text  # the header names the versioned line
    pre = version != "1.0.0"
    assert f"$PreRelease = ${str(pre).lower()}" in text
    header = text.split("& {", 1)[0]
    assert ("releases/latest" in header) is (not pre)
    assert "run the same install command again" not in text  # a versioned line reinstalls the same build


def _docker_tags(ref: str, tmp_path: Path) -> dict[str, str]:
    """Run the ``version`` step of docker.yml as GitHub would for ``ref``; return its outputs."""
    import subprocess

    import yaml

    wf = yaml.safe_load((ROOT / ".github" / "workflows" / "docker.yml").read_text(encoding="utf-8"))
    step = next(s for s in wf["jobs"]["image"]["steps"] if s.get("id") == "version")
    out = tmp_path / "out"
    out.write_text("", encoding="utf-8")
    env = {
        **os.environ,
        "GITHUB_REF": ref,
        "GITHUB_REF_NAME": ref.rsplit("/", 1)[-1],
        "GITHUB_SHA": "0123456789abcdef",
        "GITHUB_OUTPUT": str(out),
    }
    bash = shutil.which("bash")
    assert bash, "bash runs the workflow step (Git Bash on Windows)"
    subprocess.run([bash, "-euo", "pipefail", "-c", step["run"]], env=env, check=True)  # noqa: S603 - the repo's own workflow
    return dict(line.split("=", 1) for line in out.read_text(encoding="utf-8").splitlines())


def test_docker_image_tags_follow_the_pep440_version(tmp_path: Path) -> None:
    """QD-1: the image of v1.0.0a1 is :1.0.0a1-cpu (what README / install.sh pull), and a
    pre-release never moves the floating :cpu or :1.0-cpu tags."""
    pre = _docker_tags("refs/tags/v1.0.0a1", tmp_path)
    assert pre == {"version": "1.0.0a1", "tagged": "true", "stable": "false", "minor": "1.0"}
    stable = _docker_tags("refs/tags/v1.0.2", tmp_path)
    assert stable == {"version": "1.0.2", "tagged": "true", "stable": "true", "minor": "1.0"}
    dev = _docker_tags("refs/heads/main", tmp_path)
    assert dev["tagged"] == "false" and dev["stable"] == "false"
    text = (ROOT / ".github" / "workflows" / "docker.yml").read_text(encoding="utf-8")
    assert "type=semver" not in text  # semver would tag 1.0.0-a1
    assert "value=${{ matrix.variant }},enable=${{ steps.version.outputs.stable }}" in text


@pytest.mark.parametrize(
    "change",
    [
        "one line in PowerShell",  # P-1
        "current (A) and load (%)",  # K-11 / SP-1
        "raw register",  # K-11
        "WHAT TO SEND / CẦN GỬI",  # F-63
        "Station is not running",  # D-15
        "port held by another program",  # D-15
        "CH340 / CH343",  # D-21
        "Version 1.0.0a1",  # QD-1
    ],
)
def test_changelog_lists_the_m0_changes_for_users(change: str) -> None:
    """QD-15: [Unreleased] was empty; it lists what the 1.0.0a1 build changes for its users."""
    notes = check_versions.unreleased_notes((ROOT / "CHANGELOG.md").read_text(encoding="utf-8"))
    assert change in " ".join(notes.split())


def _release_notes(tmp_path: Path, version: str, pre: bool) -> str:
    """Run release.yml's "Release notes" step on this repository's CHANGELOG.md."""
    import subprocess

    import yaml

    wf = yaml.safe_load((ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8"))
    step = next(
        s
        for j in wf["jobs"].values()
        for s in j["steps"]
        if s.get("name") == "Release notes from CHANGELOG.md"
    )
    shutil.copy2(ROOT / "CHANGELOG.md", tmp_path / "CHANGELOG.md")
    env = {**os.environ, "VERSION": version, "PRERELEASE": "true" if pre else "false"}
    bash = shutil.which("bash")
    assert bash, "bash runs the workflow step (Git Bash on Windows)"
    cmd = [bash, "-euo", "pipefail", "-c", step["run"]]
    subprocess.run(cmd, env=env, cwd=tmp_path, check=True, capture_output=True)  # noqa: S603 - the repo's own workflow
    return (tmp_path / "RELEASE_NOTES.md").read_text(encoding="utf-8")


def test_release_notes_of_the_pre_release_and_their_install_lines(tmp_path: Path) -> None:
    """QD-1 / QD-15: the draft of 1.0.0a1 takes its notes from [Unreleased] (it has no section of its
    own), and its install text never says the same line updates (a versioned line reinstalls it)."""
    notes = _release_notes(tmp_path, "1.0.0a1", pre=True)
    assert "Version 1.0.0a1" in notes and "## [0.2.8]" not in notes
    assert "releases/download/v1.0.0a1/install.ps1 | iex" in notes
    assert "The same command updates" not in notes and "test build (pre-release)" in notes
    stable = _release_notes(tmp_path, "0.2.8", pre=False)
    assert "Return to rest pose" in stable and "test build" not in stable
