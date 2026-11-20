"""Release hygiene (QC 0.2.9 QD-1): the fixed build must say its own version.

Every file the release flow bumps names the version in ``pyproject.toml``, the install URLs point
at that release, and the CHANGELOG's newest release section is that version, with a date. A
pre-release (``1.0.0a1``, the M0 test build) keeps its changes under ``[Unreleased]``, which names
it (FR-76, ``tools/release/check_versions.py``, also run by tests/test_release_tools.py).
"""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

import hibiscus_station

ROOT = Path(__file__).resolve().parents[1]
INSTALL_DOCS = (
    "README.md",
    "README.vi.md",
    "docs/user-guide/en/station.md",
    "docs/user-guide/vi/station.md",
)


def _text(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _version() -> str:
    v: str = tomllib.loads(_text("pyproject.toml"))["project"]["version"]
    return v


def test_every_release_file_names_the_package_version() -> None:
    v = _version()
    found = {
        "hibiscus_station/__init__.py": hibiscus_station.__version__,
        "openapi.json": json.loads(_text("openapi.json"))["info"]["version"],
        "web/package.json": json.loads(_text("web/package.json"))["version"],
    }
    m = re.search(r'^version: "([^"]+)"$', _text("CITATION.cff"), re.M)
    found["CITATION.cff"] = m.group(1) if m else None
    m = re.search(r'name = "hibiscus-station"\nversion = "([^"]+)"', _text("uv.lock"))
    found["uv.lock"] = m.group(1) if m else None
    assert found == dict.fromkeys(found, v)


def test_install_urls_point_at_this_release() -> None:
    v = _version()
    for doc in INSTALL_DOCS:
        urls = re.findall(r"releases/download/v([^/\s]+)/hibiscus_station-([^-\s]+)-py3", _text(doc))
        assert urls, f"{doc}: no wheel install URL"
        assert set(urls) == {(v, v)}, f"{doc}: {urls}"


def _is_pre_release(v: str) -> bool:
    return re.fullmatch(r"\d+\.\d+\.\d+", v) is None


def test_the_changelog_dates_this_version() -> None:
    v = _version()
    if _is_pre_release(v):  # its notes are under [Unreleased] until it is a release (FR-76)
        notes = re.search(r"^## \[Unreleased\][^\n]*\n(.*?)(?=^## \[)", _text("CHANGELOG.md"), re.M | re.S)
        assert notes and v in notes.group(1), "[Unreleased] does not name the pre-release"
        return
    first = re.search(r"^## \[(\d[^\]]*)\] - (.+)$", _text("CHANGELOG.md"), re.M)
    assert first, "no release section in CHANGELOG.md"
    assert first.group(1) == _version()
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", first.group(2)), first.group(0)


# QC 0.2.9 QD-13: the Docker route (install.sh, image tags, .env.example) and the systemd / wheel
# docs were left at 0.2.1 because the hygiene check only looked at the wheel URLs. Every install
# route must name the release being shipped.
DEPLOY_DOCS = (
    "README.md",
    "README.vi.md",
    "deploy/install.sh",
    "deploy/.env.example",
    "deploy/compose.yml",
    "deploy/hibiscus-station-ctl",
    "deploy/systemd/hibiscus-station.service",
    "docs/deploy.md",
    "docs/first-boot-jetson.md",
    "docs/first-boot-pi5.md",
)
# Files that must carry at least one versioned reference (so a rewrite cannot silently drop it).
MUST_NAME_VERSION = (
    "README.md",
    "README.vi.md",
    "deploy/install.sh",
    "deploy/.env.example",
    "deploy/systemd/hibiscus-station.service",
    "docs/deploy.md",
)
_IMAGE_TAG = re.compile(r"(?<![\w.])v?(\d+\.\d+\.\d+(?:(?:a|b|rc)\d+)?)-(?:cpu|cuda|jetson)\b")
_WHEEL_URL = re.compile(r"releases/download/v([^/\s]+)/hibiscus_station-([^-\s]+)-py3")
_SCRIPT_VERSION = re.compile(r'^VERSION="([^"]+)"$', re.M)


def _versions_named(text: str) -> list[str]:
    found = [m.group(1) for m in _IMAGE_TAG.finditer(text)]
    for a, b in _WHEEL_URL.findall(text):
        found += [a, b]
    found += _SCRIPT_VERSION.findall(text)
    return found


def test_every_install_route_names_this_release() -> None:
    v = _version()
    for doc in DEPLOY_DOCS:
        named = _versions_named(_text(doc))
        if doc in MUST_NAME_VERSION:
            assert named, f"{doc}: names no release version"
        stale = sorted({x for x in named if x != v})
        assert not stale, f"{doc}: names {stale}, not {v}"


def test_the_install_script_defaults_to_this_release() -> None:
    m = _SCRIPT_VERSION.search(_text("deploy/install.sh"))
    assert m and m.group(1) == _version()
