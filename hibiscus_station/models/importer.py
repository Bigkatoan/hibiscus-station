"""Model import: Hibiscus bundle (zip or dir) or plain lerobot ``pretrained_model`` dir (spec §4.9, §8).

Imports are *copied* under ``models/<key>/`` so a later change to the source cannot change a model
while it runs. Zips are extracted with path-traversal, symlink and zip-bomb guards.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import shutil
import stat
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

from hibiscus_station.errors import StationError
from hibiscus_station.models.registry import FeatureSpec, ModelEntry, ModelRegistry

MAX_UNCOMPRESSED = 20 * 1024**3
MAX_RATIO = 200
UNSAFE_SUFFIXES = (".bin", ".pt", ".pth", ".pkl", ".ckpt")
KEY_RE = re.compile(r"[^a-z0-9_-]+")


def _slug(name: str) -> str:
    s = KEY_RE.sub("-", name.lower()).strip("-")
    return (s or "model")[:64]


def safe_member(name: str) -> PurePosixPath:
    p = PurePosixPath(name)
    if (
        not name
        or "\\" in name
        or "\0" in name
        or p.is_absolute()
        or ".." in p.parts
        or (p.parts and ":" in p.parts[0])
    ):
        raise StationError(
            "validation_failed", f"unsafe path in zip: {name!r}", params={"code": "unsafe_path"}
        )
    return p


def extract_zip(zpath: Path, dest: Path) -> Path:
    """Extract into ``dest`` (created); returns the single top-level dir, or ``dest``."""
    try:
        zf = zipfile.ZipFile(zpath)
    except zipfile.BadZipFile as exc:
        raise StationError("validation_failed", f"not a zip file: {exc}") from exc
    with zf:
        infos = zf.infolist()
        total = sum(i.file_size for i in infos)
        packed = max(1, zpath.stat().st_size)
        if total > MAX_UNCOMPRESSED or total / packed > MAX_RATIO:
            raise StationError(
                "validation_failed", "zip too large or compression ratio too high (zip bomb guard)"
            )
        for info in infos:
            safe_member(info.filename)
            mode = (info.external_attr >> 16) & 0o170000
            if mode == stat.S_IFLNK:
                raise StationError("validation_failed", f"symlink in zip: {info.filename}")
        dest.mkdir(parents=True, exist_ok=True)
        for info in infos:
            rel = safe_member(info.filename)
            target = dest.joinpath(*rel.parts)
            if not str(target.resolve()).startswith(str(dest.resolve())):
                raise StationError("validation_failed", f"path escapes target: {info.filename}")
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, open(target, "wb") as out:
                shutil.copyfileobj(src, out, 1024 * 1024)
    tops = [p for p in dest.iterdir() if not p.name.startswith(".")]
    if len(tops) == 1 and tops[0].is_dir():
        return tops[0]
    return dest


def _link_or_copy(src: str, dst: str) -> None:
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


def find_pretrained(root: Path) -> Path:
    for cand in (root / "pretrained_model", root):
        if (cand / "config.json").is_file():
            return cand
    found = sorted(
        p.parent for p in root.rglob("config.json") if (p.parent / "policy_preprocessor.json").exists()
    )
    if found:
        return found[0]
    raise StationError(
        "model_incompatible",
        "no lerobot pretrained_model (config.json) found",
        errors=[{"code": "no_pretrained_model"}],
    )


def check_weights(pdir: Path) -> None:
    has_safe = any(p.suffix == ".safetensors" for p in pdir.iterdir())
    unsafe = [p.name for p in pdir.iterdir() if p.suffix in UNSAFE_SUFFIXES]
    if (
        unsafe
        and not (pdir / "model.safetensors").is_file()
        and not (pdir / "adapter_model.safetensors").is_file()
    ):
        raise StationError(
            "model_incompatible",
            "pickle checkpoints are refused; export safetensors",
            errors=[{"code": "unsafe_weights", "files": unsafe}],
        )
    if not has_safe:
        raise StationError("model_incompatible", "no safetensors weights", errors=[{"code": "no_weights"}])


def _features(raw: dict[str, Any]) -> dict[str, FeatureSpec]:
    out = {}
    for k, v in (raw or {}).items():
        if isinstance(v, dict):
            out[k] = FeatureSpec(type=str(v.get("type", "")), shape=[int(x) for x in v.get("shape", [])])
    return out


def describe(pdir: Path) -> dict[str, Any]:
    cfg = json.loads((pdir / "config.json").read_text(encoding="utf-8"))
    out: dict[str, Any] = {
        "policy_type": str(cfg.get("type", "unknown")),
        "input_features": _features(cfg.get("input_features", {})),
        "output_features": _features(cfg.get("output_features", {})),
        "fps": None,
        "task": None,
        "robot_type": None,
    }
    tc_path = pdir / "train_config.json"
    if tc_path.is_file():
        try:
            tc = json.loads(tc_path.read_text(encoding="utf-8"))
        except ValueError:
            tc = {}
        ds = tc.get("dataset") if isinstance(tc.get("dataset"), dict) else {}
        fps = tc.get("fps") or (ds or {}).get("fps")
        out["fps"] = int(fps) if isinstance(fps, (int, float)) else None
        task = tc.get("task") or (ds or {}).get("task")
        out["task"] = str(task) if task else None
        rt = tc.get("robot_type") or (ds or {}).get("robot_type")
        out["robot_type"] = str(rt) if rt else None
    return out


def _size(root: Path) -> int:
    return sum(p.stat().st_size for p in root.rglob("*") if p.is_file())


def register_tree(
    registry: ModelRegistry,
    staged: Path,
    *,
    name: str,
    source: str,
    server_model_id: str | None = None,
) -> ModelEntry:
    """Move an extracted / copied tree under ``models/<key>`` and register it."""
    from hibiscus.pull import verify_manifest

    verified = False
    if (staged / "MANIFEST.json").is_file():
        _checked, problems = verify_manifest(staged)
        if problems:
            raise StationError(
                "model_incompatible",
                "bundle MANIFEST verification failed",
                errors=[{"code": "manifest", "problems": problems[:20]}],
            )
        verified = True
        kind = "bundle" if source != "server" else "server"
    else:
        kind = "pretrained_dir" if source != "server" else "server"
    pdir = find_pretrained(staged)
    check_weights(pdir)
    info = describe(pdir)
    key = registry.unique_key(_slug(name))
    final = registry.model_dir(key)
    final.parent.mkdir(parents=True, exist_ok=True)
    rel = pdir.relative_to(staged).as_posix()
    shutil.move(str(staged), str(final))
    entry = ModelEntry(
        key=key,
        name=name,
        source=kind,
        server_model_id=server_model_id,
        verified=verified,
        imported_at=dt.datetime.now(dt.UTC).isoformat(),
        size_bytes=_size(final),
        pretrained_path=rel,
        **info,
    )
    return registry.add(entry)


def import_zip(registry: ModelRegistry, zpath: Path, staging: Path, name: str | None = None) -> ModelEntry:
    tmp = staging / f"import-{os.getpid()}-{zpath.stem}-{dt.datetime.now().timestamp():.0f}"
    shutil.rmtree(tmp, ignore_errors=True)
    try:
        top = extract_zip(zpath, tmp)
        return register_tree(
            registry, top, name=name or (top.name if top != tmp else zpath.stem), source="zip"
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def allowed(path: Path, roots: list[Path]) -> bool:
    rp = path.resolve()
    return any(rp == r.resolve() or r.resolve() in rp.parents for r in roots)


def import_dir(
    registry: ModelRegistry, src: Path, staging: Path, roots: list[Path], name: str | None = None
) -> ModelEntry:
    if not src.is_dir():
        raise StationError("not_found", f"no directory at {src}")
    if not allowed(src, roots):
        raise StationError("forbidden", f"path must be under {', '.join(str(r) for r in roots)}", status=403)
    for p in src.rglob("*"):
        if p.is_symlink():
            raise StationError("validation_failed", f"symlink in model dir: {p}")
    tmp = staging / f"import-{os.getpid()}-{src.name}-{dt.datetime.now().timestamp():.0f}"
    shutil.rmtree(tmp, ignore_errors=True)
    try:
        shutil.copytree(src, tmp, copy_function=_link_or_copy)
        label = name or (src.parent.name if src.name == "pretrained_model" else src.name)
        return register_tree(registry, tmp, name=label, source="dir")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
