#!/usr/bin/env python3
"""FR-76 / D-18: one Station version everywhere.

The source of truth is ``hibiscus_station.__version__``. This fails when any of these differs:
package metadata (pyproject.toml, uv.lock, web/package.json, CITATION.cff), the Docker defaults
(deploy/install.sh, deploy/.env.example), every image tag / wheel URL / ``update`` example in the
README files and the user documentation, or the CHANGELOG (latest section and its compare links).

Usage: ``python3 tools/release/check_versions.py`` (Python 3.11+, standard library only). Exit 1
with one line per mismatch. Runs in CI (ci.yml) and in tests/test_release_tools.py.
"""

from __future__ import annotations

import itertools
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPO = "https://github.com/Bigkatoan/hibiscus-station"
#: a PEP 440 release or pre-release as the package writes it (0.2.8, 1.0.0a1, 1.0.0rc2, 1.0.0.dev3)
V = r"(\d+\.\d+\.\d+(?:(?:a|b|rc)\d+)?(?:\.(?:post|dev)\d+)?)"
#: documents for users: every Station version they name must be the current one
DOCS = [
    "README.md",
    "README.vi.md",
    "docs/deploy.md",
    "docs/first-boot-jetson.md",
    "docs/first-boot-pi5.md",
    "docs/user-guide/en/station.md",
    "docs/user-guide/vi/station.md",
]
#: where a Station version appears in those documents
TAG = V + r"-(?:cpu|cuda|jetson)\b"
DOC_PATTERNS = [
    re.compile(r"ghcr\.io/bigkatoan/hibiscus-station:" + TAG),
    re.compile(r"…:" + TAG),
    re.compile(r"hibiscus-station-ctl update " + TAG),
    re.compile(r"e\.g\. `" + TAG),
    re.compile(r"hibiscus-station/releases/download/v" + V + "/"),
    re.compile(r"hibiscus_station-" + V + r"-py3-none-any\.whl"),
    re.compile(r"install\.sh --version " + V),
]


def station_version(root: Path = ROOT) -> str:
    text = (root / "hibiscus_station" / "__init__.py").read_text(encoding="utf-8")
    m = re.search(r'^__version__ = "([^"]+)"$', text, re.M)
    if m is None:
        raise SystemExit("no __version__ in hibiscus_station/__init__.py")
    return m.group(1)


def _one(errors: list[str], where: str, pattern: str, text: str, want: str) -> None:
    m = re.search(pattern, text, re.M)
    if m is None:
        errors.append(f"{where}: no version found ({pattern})")
    elif m.group(1) != want:
        errors.append(f"{where}: {m.group(1)} != {want}")


def check_changelog(text: str, want: str) -> list[str]:
    """Latest released section == ``want``; compare links form an unbroken chain to HEAD."""
    errors: list[str] = []
    sections = [
        m.group(1)
        for m in re.finditer(r"^## \[([^\]]+)\][^\n]*$", text, re.M)
        if "(in the Hibiscus repository)" not in m.group(0)
    ]
    released = [s for s in sections if s != "Unreleased"]
    if not released or released[0] != want:
        errors.append(f"CHANGELOG.md: latest section is {released[:1]}, not [{want}]")
    links = dict(re.findall(r"^\[([^\]]+)\]: (\S+)$", text, re.M))
    if released:
        expect = {"Unreleased": f"{REPO}/compare/v{released[0]}...HEAD"} if "Unreleased" in sections else {}
        for newer, older in itertools.pairwise(released):
            expect[newer] = f"{REPO}/compare/v{older}...v{newer}"
        expect[released[-1]] = f"{REPO}/releases/tag/v{released[-1]}"
        for name, url in expect.items():
            if links.get(name) != url:
                errors.append(f"CHANGELOG.md: [{name}] link is {links.get(name)!r}, expected {url}")
    return errors


def check(root: Path = ROOT) -> list[str]:
    want = station_version(root)
    errors: list[str] = []

    def read(rel: str) -> str:
        return (root / rel).read_text(encoding="utf-8")

    _one(errors, "pyproject.toml", r'^version = "([^"]+)"', read("pyproject.toml"), want)
    _one(errors, "uv.lock", r'^name = "hibiscus-station"\nversion = "([^"]+)"', read("uv.lock"), want)
    _one(errors, "CITATION.cff", r'^version: "?([^"\s]+)"?', read("CITATION.cff"), want)
    pkg = json.loads(read("web/package.json")).get("version")
    if pkg != want:
        errors.append(f"web/package.json: {pkg} != {want}")
    _one(errors, "deploy/install.sh", r'^VERSION="([^"]+)"', read("deploy/install.sh"), want)
    _one(errors, "deploy/.env.example", r"^STATION_TAG=(.+)-cpu$", read("deploy/.env.example"), want)

    for rel in DOCS:
        path = root / rel
        if not path.is_file():
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for pat in DOC_PATTERNS:
                for m in pat.finditer(line):
                    if m.group(1) != want:
                        errors.append(f"{rel}:{lineno}: {m.group(0)} ({m.group(1)} != {want})")

    errors += check_changelog(read("CHANGELOG.md"), want)
    return errors


def main() -> int:
    errors = check()
    if errors:
        print(f"version {station_version()} is not used everywhere (FR-76):", file=sys.stderr)
        for e in errors:
            print(f"  {e}", file=sys.stderr)
        return 1
    print(f"version {station_version()}: consistent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
