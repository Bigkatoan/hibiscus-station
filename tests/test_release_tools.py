"""Release tooling (tools/release): version consistency (FR-76 / D-18)."""

from __future__ import annotations

import importlib.util
import shutil
import sys
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
        ("CHANGELOG.md", "compare/v{v}...HEAD", "compare/v0.2.2...HEAD", "[Unreleased]"),
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
