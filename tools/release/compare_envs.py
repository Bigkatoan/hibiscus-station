#!/usr/bin/env python3
"""AT-1 step 3 / ADR-13: the libraries of an installed Station equal the tested set, 100 %.

    python tools/release/compare_envs.py INSTALLED_PYTHON REFERENCE_PYTHON VERSION

INSTALLED_PYTHON is the interpreter of the tool environment the installer made
(``<uv tool dir>/hibiscus-station/{bin/python,Scripts/python.exe}``); REFERENCE_PYTHON one of
``uv sync --locked --no-dev --no-install-project`` (the set the test suite runs on). Package names
and versions must be identical; the installed environment must also hold hibiscus-station VERSION.
Needs uv on PATH. Standard library only.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys


def packages(python: str) -> dict[str, str]:
    out = subprocess.run(  # noqa: S603
        ["uv", "pip", "list", "--python", python, "--format", "json"],  # noqa: S607
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return {re.sub(r"[-_.]+", "-", p["name"]).lower(): p["version"] for p in json.loads(out)}


def compare(installed: dict[str, str], reference: dict[str, str], version: str) -> list[str]:
    inst = dict(installed)
    station = inst.pop("hibiscus-station", None)
    ref = {k: v for k, v in reference.items() if k != "hibiscus-station"}
    errors = [f"hibiscus-station {station} installed, expected {version}"] if station != version else []
    for name in sorted(set(inst) | set(ref)):
        if inst.get(name) != ref.get(name):
            errors.append(f"{name}: installed {inst.get(name)}, tested {ref.get(name)}")
    return errors


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2
    installed, reference = packages(argv[0]), packages(argv[1])
    errors = compare(installed, reference, argv[2])
    print(f"installed: {len(installed)} packages; tested set: {len(reference)}")
    if errors:
        print("FAIL: the installed libraries differ from the tested set:", file=sys.stderr)
        for e in errors:
            print(f"  {e}", file=sys.stderr)
        return 1
    print("OK: 100 % identical to the tested set")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
