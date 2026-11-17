#!/usr/bin/env python3
"""Check a folder of release assets made by build_release.py (ADR-13).

* every asset matches ``SHA256SUMS``; ``install.ps1`` is ASCII and installs this version;
* for each target platform, what ``uv tool install --constraints --overrides <wheel>`` resolves
  (``uv pip compile --python-platform``, so no Windows or Mac is needed) is exactly the ``uv.lock``
  set for that platform (the ``uv export`` lines whose marker holds there): name and version, 100 %.

Usage: ``uv run python tools/release/verify_assets.py DIR``. Needs uv, git and the network.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import unquote

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_release

ROOT = Path(__file__).resolve().parents[2]
REPO_URL = "https://github.com/Bigkatoan/hibiscus-station"
#: (uv --python-platform, MACOSX_DEPLOYMENT_TARGET or None). Windows x64 is the acceptance platform
#: (decision 2 = A); Linux x86_64 is tested; macOS arm64 is a preview, its resolution is still checked.
PLATFORMS = (
    ("x86_64-pc-windows-msvc", None),
    ("x86_64-unknown-linux-gnu", None),
    ("aarch64-apple-darwin", "14.0"),
)
_PY = {
    "python_version": "3.12",
    "python_full_version": "3.12.12",
    "implementation_name": "cpython",
    "platform_python_implementation": "CPython",
}
MARKER_ENV = {
    "x86_64-pc-windows-msvc": {
        **_PY,
        "sys_platform": "win32",
        "platform_system": "Windows",
        "platform_machine": "AMD64",
        "os_name": "nt",
    },
    "x86_64-unknown-linux-gnu": {
        **_PY,
        "sys_platform": "linux",
        "platform_system": "Linux",
        "platform_machine": "x86_64",
        "os_name": "posix",
    },
    "aarch64-apple-darwin": {
        **_PY,
        "sys_platform": "darwin",
        "platform_system": "Darwin",
        "platform_machine": "arm64",
        "os_name": "posix",
    },
}


def lock_set(export: str, platform: str) -> dict[str, str]:
    """The uv.lock runtime set for ``platform``: the export lines whose marker holds there."""
    from packaging.markers import Marker  # in uv.lock; run through `uv run`

    pins: dict[str, str] = {}
    lock = (ROOT / "uv.lock").read_text(encoding="utf-8")
    for raw in export.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        req, _, marker = line.partition(" ; ")
        if marker and not Marker(marker).evaluate(MARKER_ENV[platform]):
            continue
        m = re.match(r"^([A-Za-z0-9._-]+)==(\S+)$", req.strip())
        if m is None:
            g = re.match(r"^([A-Za-z0-9._-]+) @ git\+", req)
            if g is None:
                raise SystemExit(f"unexpected export line: {line}")
            vm = re.search(rf'^name = "{re.escape(g.group(1))}"\nversion = "([^"]+)"', lock, re.M)
            if vm is None:
                raise SystemExit(f"{g.group(1)}: not in uv.lock")
            m_name, m_ver = g.group(1), vm.group(1)
        else:
            m_name, m_ver = m.group(1), m.group(2)
        pins[re.sub(r"[-_.]+", "-", m_name).lower()] = m_ver
    return {k: v for k, v in pins.items() if k not in SKIP}


SKIP = {"hibiscus-station"}


def station_version() -> str:
    text = (ROOT / "hibiscus_station" / "__init__.py").read_text(encoding="utf-8")
    m = re.search(r'^__version__ = "([^"]+)"$', text, re.M)
    if m is None:
        raise SystemExit("no __version__")
    return m.group(1)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compile_set(args: list[str], platform: str, macos: str | None, out: Path) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("UV_") or k == "UV_CACHE_DIR"}
    env.pop("PYTHONPATH", None)
    if macos:
        env["MACOSX_DEPLOYMENT_TARGET"] = macos
    cmd = ["uv", "pip", "compile", "-q", "--no-config", "--python-platform", platform]
    cmd += ["--python-version", "3.12", "--no-header", "--no-annotate", "-o", str(out), *args]
    subprocess.run(cmd, check=True, env=env)  # noqa: S603
    pins: dict[str, str] = {}
    for line in out.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^([A-Za-z0-9._-]+)==(\S+)", line)
        if m:
            pins[re.sub(r"[-_.]+", "-", m.group(1)).lower()] = m.group(2)
            continue
        m = re.match(r"^([A-Za-z0-9._-]+) @ \S*/[A-Za-z0-9_.]+-([^-/]+)-[^-/]+-[^-/]+-[^-/]+\.whl", line)
        if m:  # a wheel by URL (lerobot / hibiscus of the release, torchcodec +cpu): its file name
            pins[re.sub(r"[-_.]+", "-", m.group(1)).lower()] = unquote(m.group(2))
            continue
        if line.endswith(".whl"):
            continue  # the Station wheel itself (a path)
        raise SystemExit(f"unexpected line in {out.name}: {line}")
    return {k: v for k, v in pins.items() if k not in SKIP}


#: What the source archive may hold below its top folder: the package and the root files the
#: sdist include list names. Anything else (web/node_modules, tests/**) means an unanchored pattern.
SDIST_ALLOWED = (
    "hibiscus_station/",
    "README.md",
    "pyproject.toml",
    "hatch_build.py",
    "openapi.json",
    "LICENSE",
    "ASSETS-LICENSE",
    "NOTICE",
    "PKG-INFO",
    ".gitignore",
)


def sdist_strays(sdist: Path) -> list[str]:
    """Members of a ``.tar.gz`` sdist outside :data:`SDIST_ALLOWED` (QD-20)."""
    import tarfile

    strays = []
    with tarfile.open(sdist) as tar:
        for name in tar.getnames():
            rel = name.split("/", 1)[1] if "/" in name else ""
            if rel and not any(rel == a or (a.endswith("/") and rel.startswith(a)) for a in SDIST_ALLOWED):
                strays.append(rel)
    return strays


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("dir", type=Path)
    args = ap.parse_args(argv)
    rel: Path = args.dir.resolve()
    version = station_version()
    errors: list[str] = []

    sums = {}
    for line in (rel / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        digest, name = line.split(maxsplit=1)
        sums[name.lstrip("*")] = digest
    files = {
        p.name for p in rel.iterdir() if p.is_file() and p.name != "SHA256SUMS" and not p.name.startswith(".")
    }
    if files != set(sums):
        errors.append(f"SHA256SUMS lists {sorted(sums)}, folder has {sorted(files)}")
    for name, digest in sums.items():
        if (rel / name).is_file() and sha256(rel / name) != digest:
            errors.append(f"{name}: SHA-256 differs from SHA256SUMS")
    wheel = rel / f"hibiscus_station-{version}-py3-none-any.whl"
    for need in (wheel.name, "constraints.txt", "overrides.txt", "install.ps1"):
        if need not in files:
            errors.append(f"missing asset {need}")
    for sd in sorted(rel.glob("hibiscus_station-*.tar.gz")):
        strays = sdist_strays(sd)
        if strays:
            errors.append(f"{sd.name}: {len(strays)} files outside the package, e.g. {strays[:3]}")
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    ps1 = (rel / "install.ps1").read_bytes()
    if any(b > 127 for b in ps1):
        errors.append("install.ps1 is not ASCII")
    if f"$Version = '{version}'".encode() not in ps1:
        errors.append(f"install.ps1 does not install {version}")

    release_url = f"{REPO_URL}/releases/download/v{version}"
    with tempfile.TemporaryDirectory(prefix="station-verify-") as tmp:
        t = Path(tmp)
        overrides = t / "overrides.txt"
        overrides.write_text(
            (rel / "overrides.txt").read_text(encoding="utf-8").replace(release_url, rel.as_uri()),
            encoding="utf-8",
        )
        req = t / "station.in"
        req.write_text(f"{wheel}\n", encoding="utf-8")
        export = build_release.run(build_release.EXPORT, cwd=ROOT, capture=True)
        for platform, macos in PLATFORMS:
            got = compile_set(
                ["-c", str(rel / "constraints.txt"), "--overrides", str(overrides), str(req)],
                platform,
                macos,
                t / f"release-{platform}.txt",
            )
            want = lock_set(export, platform)
            diff = sorted(set(got.items()) ^ set(want.items()))
            if diff:
                errors.append(
                    f"{platform}: release set != uv.lock: "
                    + ", ".join(
                        f"{n}=={v} ({'release' if got.get(n) == v else 'lock'} only)" for n, v in diff
                    )
                )
            else:
                print(f"{platform}: {len(got)} packages, identical to uv.lock")
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(f"release assets of {version} OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
