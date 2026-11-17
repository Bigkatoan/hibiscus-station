#!/usr/bin/env python3
"""NFR-18 / AT-2: fail when pytest skipped a test that tools/ci/allowed-skips.toml does not allow
on this platform, or when the run had no tests at all.

    python tools/ci/check_skips.py --platform linux|windows|macos junit.xml [more.xml ...]

Prints every skip with its reason and the AT / UAT that covers it, for the job log (QC reads it for
AT-2). Python 3.11+, standard library only.
"""

from __future__ import annotations

import argparse
import os
import sys
import tomllib
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

ALLOWED = Path(__file__).with_name("allowed-skips.toml")
PLATFORMS = ("linux", "windows", "macos")


@dataclass(frozen=True)
class Allowed:
    test: str
    platforms: tuple[str, ...]
    reason: str
    covered_by: str

    @property
    def dotted(self) -> str:
        module, _, rest = self.test.partition("::")
        dotted = module.removesuffix(".py").replace("/", ".").replace("\\", ".")
        return f"{dotted}.{rest.replace('::', '.')}" if rest else dotted

    def matches(self, key: str) -> bool:
        d = self.dotted
        return key == d or key.startswith((d + ".", d + "["))


def load_allowed(path: Path = ALLOWED) -> list[Allowed]:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    out = []
    for e in data.get("skip", []):
        bad = set(e["platforms"]) - set(PLATFORMS)
        if bad or not e.get("reason") or not e.get("covered_by"):
            raise SystemExit(f"{path.name}: bad entry {e}")
        out.append(Allowed(e["test"], tuple(e["platforms"]), e["reason"], e["covered_by"]))
    return out


def skipped(junit: Path) -> tuple[int, list[tuple[str, str]]]:
    """(number of test cases, [(dotted key, message)] of the skipped ones)."""
    root = ET.parse(junit).getroot()  # noqa: S314
    total = 0
    skips = []
    for tc in root.iter("testcase"):
        total += 1
        s = tc.find("skipped")
        if s is None:
            continue
        cls, name = tc.get("classname") or "", tc.get("name") or ""
        key = f"{cls}.{name}" if cls else name.removesuffix(".py").replace("/", ".")
        skips.append((key, s.get("message") or ""))
    return total, skips


def check(platform: str, files: list[Path], allowed: list[Allowed]) -> list[str]:
    errors: list[str] = []
    mine = [a for a in allowed if platform in a.platforms]
    total = 0
    for f in files:
        n, skips = skipped(f)
        total += n
        for key, msg in skips:
            hit = next((a for a in mine if a.matches(key)), None)
            if hit is None:
                errors.append(f"SKIPPED, not in tools/ci/allowed-skips.toml for {platform}: {key} ({msg})")
            else:
                print(f"allowed skip [{platform}] {key}: {hit.reason}; covered by {hit.covered_by}")
    if total == 0:
        errors.append("no test cases in the JUnit report(s)")
    return errors


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--platform", required=True, choices=PLATFORMS)
    ap.add_argument("junit", nargs="+", type=Path)
    args = ap.parse_args(argv)
    errors = check(args.platform, args.junit, load_allowed())
    for e in errors:
        print(f"::error::{e}" if "GITHUB_ACTIONS" in os.environ else e, file=sys.stderr)
    if not errors:
        print(f"skips on {args.platform}: all in the published list")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
