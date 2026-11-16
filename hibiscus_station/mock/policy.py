"""DummyPolicy: a tiny random-weight ACT checkpoint saved with lerobot's own ``save_pretrained``.

Loading, the compatibility check and ``predict_action`` then use real lerobot code paths on CPU in
well under a second (spec §9.1).
"""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path
from typing import Any

import numpy as np

MOTORS = ("shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll", "gripper")


def make_dummy_act(
    out_dir: Path,
    cameras: dict[str, tuple[int, int]],
    *,
    state_dim: int = 6,
    action_dim: int = 6,
    chunk_size: int = 5,
    fps: int = 30,
    task: str = "Pick the red cube",
    seed: int = 0,
    weights_format: str = "safetensors",
) -> Path:
    """Write ``out_dir`` as a lerobot ``pretrained_model`` directory; returns it."""
    import torch
    from lerobot.configs.types import FeatureType, PolicyFeature
    from lerobot.policies.act.configuration_act import ACTConfig
    from lerobot.policies.act.modeling_act import ACTPolicy
    from lerobot.policies.factory import make_pre_post_processors

    torch.manual_seed(seed)
    inputs = {"observation.state": PolicyFeature(FeatureType.STATE, (state_dim,))}
    for name, (h, w) in cameras.items():
        inputs[f"observation.images.{name}"] = PolicyFeature(FeatureType.VISUAL, (3, h, w))
    cfg = ACTConfig(
        input_features=inputs,
        output_features={"action": PolicyFeature(FeatureType.ACTION, (action_dim,))},
        dim_model=32,
        n_heads=2,
        dim_feedforward=64,
        n_encoder_layers=1,
        n_decoder_layers=1,
        chunk_size=chunk_size,
        n_action_steps=chunk_size,
        pretrained_backbone_weights=None,
        use_vae=False,
        device="cpu",
        push_to_hub=False,
    )
    policy = ACTPolicy(cfg)
    stats: dict[str, dict[str, np.ndarray[Any, Any]]] = {
        "observation.state": {"mean": np.zeros(state_dim), "std": np.full(state_dim, 30.0)},
        "action": {"mean": np.zeros(action_dim), "std": np.full(action_dim, 30.0)},
    }
    for name in cameras:
        stats[f"observation.images.{name}"] = {
            "mean": np.full((3, 1, 1), 0.5),
            "std": np.full((3, 1, 1), 0.25),
        }
    pre, post = make_pre_post_processors(cfg, dataset_stats=stats)
    out_dir.mkdir(parents=True, exist_ok=True)
    policy.save_pretrained(out_dir)
    pre.save_pretrained(out_dir)
    post.save_pretrained(out_dir)
    (out_dir / "train_config.json").write_text(
        json.dumps(
            {
                "dataset": {"repo_id": "local/dummy", "fps": fps, "task": task},
                "policy": {"type": "act"},
                "robot_type": "so_follower",
                "fps": fps,
                "task": task,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    if weights_format == "bin":  # pickle checkpoint (refused by Station)
        (out_dir / "model.safetensors").rename(out_dir / "pytorch_model.bin")
    return out_dir


def make_bundle(out_root: Path, bundle_name: str, cameras: dict[str, tuple[int, int]]) -> Path:
    """A Hibiscus bundle directory (docs/spec/bundle.md §2) around a dummy ACT checkpoint."""
    root = out_root / bundle_name
    make_dummy_act(root / "pretrained_model", cameras)
    (root / "MODEL_CARD.md").write_text(f"# {bundle_name}\n\nDummy ACT for tests.\n", encoding="utf-8")
    files = []
    for p in sorted(root.rglob("*")):
        if p.is_file():
            rel = p.relative_to(root).as_posix()
            data = p.read_bytes()
            files.append({"path": rel, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()})
    (root / "MANIFEST.json").write_text(
        json.dumps({"schema_version": "1", "bundle_name": bundle_name, "files": files}, indent=2),
        encoding="utf-8",
    )
    return root


def bundle_files(root: Path) -> dict[str, bytes]:
    """All files of a bundle (without MANIFEST.json), for FakeHibiscus.add_model."""
    return {
        p.relative_to(root).as_posix(): p.read_bytes()
        for p in sorted(root.rglob("*"))
        if p.is_file() and p.name != "MANIFEST.json"
    }


def zip_dir(src: Path, zpath: Path) -> Path:
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in sorted(src.rglob("*")):
            if p.is_file():
                zf.write(p, f"{src.name}/{p.relative_to(src).as_posix()}")
    return zpath
