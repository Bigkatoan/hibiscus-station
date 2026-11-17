#!/usr/bin/env python3
"""Build the release assets of Hibiscus Station (ADR-13, P-1, decision 3 = A).

The one-line installer must give every user the dependency set QC tested, with no git on the user's
PC. ``uv tool install <wheel>`` alone resolves the version ranges of ``pyproject.toml`` again on the
day of the install and fetches ``lerobot`` and ``hibiscus`` from git, so this script ships, next to
the Station wheel:

* ``constraints.txt``: every package of ``uv.lock`` (runtime, no dev group) pinned to its exact
  version, with the lock's platform markers (``uv export``);
* one wheel per git dependency of the lock, built from the locked commit, and ``overrides.txt``
  pointing each of them at its release asset (``name[extras] @ <url>#sha256=<hash>``), so uv never
  calls git;
* ``install.ps1`` (from ``install.ps1.in``): installs a pinned uv (checked by SHA-256) when needed,
  then ``uv tool install`` of this release with the two files above;
* ``SHA256SUMS`` of every asset.

Usage (repository root, ``web/dist`` built)::

    uv run python tools/release/build_release.py --out dist/release
    uv run python tools/release/build_release.py --out DIR --base-url URL  # assets hosted elsewhere

Needs ``uv`` and ``git`` (and the network for the git dependencies and the uv checksum).
Standard library only.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
REPO_URL = "https://github.com/Bigkatoan/hibiscus-station"
#: uv used by the installer. Keep in step with UV_VERSION in .github/workflows/ci.yml.
UV_VERSION = "0.13.8"
UV_WINDOWS_ASSET = "uv-x86_64-pc-windows-msvc.zip"
PYTHON_VERSION = "3.12"
TEMPLATE = Path(__file__).with_name("install.ps1.in")
#: the runtime set of uv.lock, pinned, with platform markers
EXPORT = [
    "uv", "export", "--frozen", "--no-dev", "--no-hashes", "--no-emit-project",
    "--no-header", "--no-annotate", "--format", "requirements-txt",
]  # fmt: skip


@dataclass(frozen=True)
class GitDep:
    name: str
    repo: str
    rev: str
    subdirectory: str | None


def run(cmd: list[str], *, cwd: Path | None = None, capture: bool = False) -> str:
    print("+", " ".join(cmd), file=sys.stderr)
    # uv does not fetch Git LFS objects for git dependencies either (lerobot keeps test images there)
    env = {**os.environ, "GIT_LFS_SKIP_SMUDGE": "1"}
    res = subprocess.run(  # noqa: S603
        cmd, cwd=cwd, check=True, text=True, env=env, stdout=subprocess.PIPE if capture else None
    )
    return res.stdout if capture else ""


def station_version() -> str:
    text = (ROOT / "hibiscus_station" / "__init__.py").read_text(encoding="utf-8")
    m = re.search(r'^__version__ = "([^"]+)"$', text, re.M)
    if m is None:
        raise SystemExit("no __version__ in hibiscus_station/__init__.py")
    return m.group(1)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


_GIT_LINE = re.compile(r"^(?P<name>[A-Za-z0-9._-]+) @ git\+(?P<url>[^\s;]+)")


def parse_git_line(line: str) -> GitDep | None:
    """``lerobot @ git+https://host/repo.git@<sha>[#subdirectory=x]`` -> GitDep."""
    m = _GIT_LINE.match(line.strip())
    if m is None:
        return None
    url = m.group("url")
    subdirectory = None
    if "#" in url:
        url, frag = url.split("#", 1)
        for part in frag.split("&"):
            if part.startswith("subdirectory="):
                subdirectory = part.split("=", 1)[1]
    repo, rev = url.rsplit("@", 1)
    if not re.fullmatch(r"[0-9a-f]{40}", rev):
        raise SystemExit(f"{m.group('name')}: the lock must pin a full commit, got {rev!r}")
    return GitDep(m.group("name"), repo, rev, subdirectory)


def split_export(text: str) -> tuple[list[str], list[GitDep]]:
    """``uv export`` output -> (constraint lines, git dependencies)."""
    constraints: list[str] = []
    git: list[GitDep] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        dep = parse_git_line(line)
        if dep is not None:
            git.append(dep)
            continue
        if " @ " in line or line.startswith(("-e ", "./", "file:")):
            raise SystemExit(f"unexpected non-index requirement in the lock: {line}")
        if "==" not in line:
            raise SystemExit(f"unpinned requirement in the export: {line}")
        constraints.append(line)
    return constraints, git


def _norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def requested_extras(name: str) -> list[str]:
    """Extras the Station requests for ``name`` in pyproject.toml (``["feetech", "dataset"]``)."""
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    for spec in data["project"]["dependencies"]:
        m = re.match(r"^([A-Za-z0-9._-]+)(?:\[([^\]]*)\])?", spec)
        if m and _norm(m.group(1)) == _norm(name):
            return [e.strip() for e in (m.group(2) or "").split(",") if e.strip()]
    return []


def extras_closure(wheel: Path, extras: list[str]) -> list[str]:
    """``extras`` plus every extra they pull in through self-references
    (lerobot: ``dataset`` -> ``lerobot[av-dep]``). An override replaces *every* requirement on the
    package, the self-references too, so the override line must name the whole closure."""
    with zipfile.ZipFile(wheel) as z:
        meta_name = next(n for n in z.namelist() if n.endswith(".dist-info/METADATA"))
        meta = z.read(meta_name).decode("utf-8")
    name = _norm(re.search(r"^Name: (.+)$", meta, re.M).group(1).strip())  # type: ignore[union-attr]
    edges: dict[str, set[str]] = {}
    for m in re.finditer(r"^Requires-Dist: ([A-Za-z0-9._-]+)\[([^\]]+)\][^;\n]*;(.*)$", meta, re.M):
        if _norm(m.group(1)) != name:
            continue
        for extra in re.findall(r"extra == [\"']([^\"']+)[\"']", m.group(3)):
            edges.setdefault(_norm(extra), set()).update(_norm(e) for e in m.group(2).split(","))
    seen: list[str] = []
    todo = [_norm(e) for e in extras]
    while todo:
        e = todo.pop(0)
        if e not in seen:
            seen.append(e)
            todo.extend(sorted(edges.get(e, ())))
    return seen


def extras_spec(extras: list[str]) -> str:
    return f"[{','.join(extras)}]" if extras else ""


PYPI = "https://pypi.org/simple"
_TAG_MARKERS = (
    ("win_amd64", "sys_platform == 'win32' and platform_machine == 'AMD64'"),
    ("x86_64", None),  # linux or macOS, below
    ("aarch64", "sys_platform == 'linux' and platform_machine == 'aarch64'"),
    ("arm64", "sys_platform == 'darwin' and platform_machine == 'arm64'"),
)


def wheel_marker(filename: str) -> str:
    """Environment marker of a wheel's platform tag (only the tags the lock uses)."""
    stem = filename.removesuffix(".whl")
    name_ver_py_abi, plat = stem.rsplit("-", 1)
    py = name_ver_py_abi.split("-")[-2]
    if not ({"cp312", "py3", "py312"} & set(py.split("."))):
        raise ValueError(f"{filename}: not a Python 3.12 wheel")
    if plat == "any":
        return ""
    for key, marker in _TAG_MARKERS:
        if key in plat:
            if marker is None:
                system = "darwin" if plat.startswith("macosx") else "linux"
                return f"sys_platform == '{system}' and platform_machine == 'x86_64'"
            return marker
    raise SystemExit(f"{filename}: unknown platform tag {plat}")


def index_overrides(lock: dict[str, Any]) -> tuple[list[str], set[str]]:
    """Packages that uv.lock takes from another index than PyPI (torchcodec ``+cpu`` from the
    PyTorch index on Linux, a ``tool.uv.sources`` of lerobot): a wheel built from git loses that
    source, so each locked wheel is pinned by URL + hash, and the package's PyPI versions by their
    lock markers. Returns (override lines, normalized names)."""
    packages: list[dict[str, Any]] = lock["package"]
    other = {p["name"] for p in packages if p.get("source", {}).get("registry", PYPI) != PYPI}
    lines: list[str] = []
    for p in packages:
        if p["name"] not in other or "registry" not in p.get("source", {}):
            continue
        markers = " or ".join(f"({m})" for m in p.get("resolution-markers", []))
        if p["source"]["registry"] == PYPI:
            lines.append(f"{p['name']}=={p['version']}" + (f" ; {markers}" if markers else ""))
            continue
        for w in p.get("wheels", []):
            fname = w["url"].rsplit("/", 1)[1].replace("%2B", "+")
            try:
                marker = wheel_marker(fname)
            except ValueError:
                continue
            lines.append(
                f"{p['name']} @ {w['url']}#{w['hash'].replace(':', '=')}" + (f" ; {marker}" if marker else "")
            )
    return lines, {_norm(n) for n in other}


def build_git_wheel(dep: GitDep, out: Path, work: Path) -> Path:
    src = work / dep.name
    src.mkdir(parents=True)
    run(["git", "init", "-q"], cwd=src)
    run(["git", "fetch", "-q", "--depth", "1", dep.repo, dep.rev], cwd=src)
    run(["git", "checkout", "-q", "FETCH_HEAD"], cwd=src)
    pkg = src / dep.subdirectory if dep.subdirectory else src
    tmp_out = work / f"{dep.name}-wheel"
    run(["uv", "build", "--wheel", "--out-dir", str(tmp_out), str(pkg)])
    wheels = list(tmp_out.glob("*.whl"))
    if len(wheels) != 1:
        raise SystemExit(f"{dep.name}: expected one wheel, got {wheels}")
    dest = out / wheels[0].name
    shutil.copy2(wheels[0], dest)
    return dest


def fetch_uv_sha256(version: str) -> str:
    url = f"https://github.com/astral-sh/uv/releases/download/{version}/{UV_WINDOWS_ASSET}.sha256"
    with urllib.request.urlopen(url, timeout=60) as r:
        text: str = r.read().decode()
    digest = text.split()[0].lower()
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise SystemExit(f"bad uv checksum file at {url}: {text[:80]!r}")
    return digest


def ps_ascii(text: str) -> str:
    """Make the script pure ASCII: Windows PowerShell 5.1 decodes ``irm`` output of an
    ``application/octet-stream`` asset as Latin-1. Non-ASCII characters (Vietnamese messages) are
    only allowed inside double-quoted strings and become ``$([char]0x....)`` subexpressions."""
    out: list[str] = []
    for lineno, line in enumerate(text.splitlines(keepends=True), 1):
        in_dq = False
        for ch in line:
            if ch == '"':
                in_dq = not in_dq
            if ord(ch) < 128:
                out.append(ch)
                continue
            if not in_dq:
                raise SystemExit(f'install.ps1.in:{lineno}: non-ASCII character outside a "string"')
            if ord(ch) > 0xFFFF:
                raise SystemExit(f"install.ps1.in:{lineno}: character outside the BMP")
            out.append(f"$([char]0x{ord(ch):04X})")
    return "".join(out)


def render_installer(*, version: str, base_url: str, uv_sha256: str) -> str:
    text = TEMPLATE.read_text(encoding="utf-8")
    pre = re.fullmatch(r"\d+\.\d+\.\d+", version) is None
    values = {
        "@VERSION@": version,
        "@BASE_URL@": base_url,
        "@UV_VERSION@": UV_VERSION,
        "@UV_ASSET@": UV_WINDOWS_ASSET,
        "@UV_SHA256@": uv_sha256,
        "@PYTHON_VERSION@": PYTHON_VERSION,
        "@REPO_URL@": REPO_URL,
        "@PRE_RELEASE@": "true" if pre else "false",
        # GitHub's releases/latest never serves a pre-release (QD-1)
        "@LATEST_LINE@": (
            '#   (a pre-release: GitHub\'s "latest" link never serves it: use the line above)'
            if pre
            else f"#   irm {REPO_URL}/releases/latest/download/install.ps1 | iex       # the latest release"
        ),
    }
    for k, v in values.items():
        text = text.replace(k, v)
    left = re.findall(r"@[A-Z0-9_]+@", text)
    if left:
        raise SystemExit(f"install.ps1.in: unknown placeholders {sorted(set(left))}")
    return ps_ascii(text)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", type=Path, default=ROOT / "dist" / "release")
    ap.add_argument(
        "--base-url", help="where the assets will be downloaded from (default: the GitHub release)"
    )
    ap.add_argument(
        "--uv-sha256", help="SHA-256 of the uv Windows zip (default: fetched from the uv release)"
    )
    ap.add_argument("--skip-station-wheel", action="store_true", help="reuse the wheel already in --out")
    args = ap.parse_args(argv)

    version = station_version()
    base = (args.base_url or f"{REPO_URL}/releases/download/v{version}").rstrip("/")
    out: Path = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)

    # 1. the Station wheel + sdist (the hatch hook ships web/dist as the UI)
    if not args.skip_station_wheel:
        for old in [*out.glob("hibiscus_station-*.whl"), *out.glob("hibiscus_station-*.tar.gz")]:
            old.unlink()
        run(["uv", "build", "--out-dir", str(out)], cwd=ROOT)
    station_wheels = sorted(out.glob(f"hibiscus_station-{version}-py3-none-any.whl"))
    if len(station_wheels) != 1:
        raise SystemExit(f"expected hibiscus_station-{version}-py3-none-any.whl in {out}")

    # 2. the exact runtime set of uv.lock
    exported = run(EXPORT, cwd=ROOT, capture=True)
    constraints, git_deps = split_export(exported)
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    overrides, by_url = index_overrides(lock)
    constraints = [c for c in constraints if _norm(re.split(r"[=<>!~ ;\[]", c, maxsplit=1)[0]) not in by_url]

    # 3. git dependencies -> wheels served by the release, pinned by hash in overrides.txt
    with tempfile.TemporaryDirectory(prefix="station-release-") as tmp:
        for dep in git_deps:
            for old in out.glob(f"{dep.name.replace('-', '_')}-*.whl"):
                old.unlink()
            wheel = build_git_wheel(dep, out, Path(tmp))
            overrides.append(
                f"{dep.name}{extras_spec(extras_closure(wheel, requested_extras(dep.name)))}"
                f" @ {base}/{wheel.name}#sha256={sha256(wheel)}"
            )

    header = (
        f"# Hibiscus Station {version}: {{}} generated from uv.lock by tools/release/build_release.py.\n"
        "# Used by install.ps1 (uv tool install --constraints constraints.txt --overrides overrides.txt).\n"
    )
    (out / "constraints.txt").write_text(
        header.format("exact runtime versions") + "\n".join(constraints) + "\n", encoding="utf-8"
    )
    (out / "overrides.txt").write_text(
        header.format("git dependencies as prebuilt wheels") + "\n".join(overrides) + "\n", encoding="utf-8"
    )

    # 4. the installer
    uv_sha = args.uv_sha256 or fetch_uv_sha256(UV_VERSION)
    (out / "install.ps1").write_text(
        render_installer(version=version, base_url=base, uv_sha256=uv_sha), encoding="ascii", newline="\r\n"
    )

    # 5. checksums of everything the release carries
    assets = sorted(
        p for p in out.iterdir() if p.is_file() and p.name != "SHA256SUMS" and not p.name.startswith(".")
    )
    (out / "SHA256SUMS").write_text("".join(f"{sha256(p)}  {p.name}\n" for p in assets), encoding="utf-8")
    print(f"release assets for {version} in {out}:", file=sys.stderr)
    for p in assets:
        print(f"  {p.name}  {p.stat().st_size / 1e6:.1f} MB", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
