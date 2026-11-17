"""Release hygiene (QC 0.2.9 QD-1): the fixed build must say its own version.

Every file the release flow bumps names the version in ``pyproject.toml``, the install URLs point
at that release, and the CHANGELOG's newest release section is that version, with a date.
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


def test_the_changelog_dates_this_version() -> None:
    first = re.search(r"^## \[(\d[^\]]*)\] - (.+)$", _text("CHANGELOG.md"), re.M)
    assert first, "no release section in CHANGELOG.md"
    assert first.group(1) == _version()
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", first.group(2)), first.group(0)
