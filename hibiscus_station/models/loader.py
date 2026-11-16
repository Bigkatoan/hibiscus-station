"""Policy loading (jobs pool) and per-tick inference (spec §4.9), lerobot-rollout style."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np


def resolve_device(requested: str) -> str:
    import torch

    if requested != "auto":
        return requested
    if torch.cuda.is_available():
        return "cuda"
    mps = getattr(torch.backends, "mps", None)
    if mps is not None and mps.is_available():
        return "mps"
    return "cpu"


@dataclass
class LoadedPolicy:
    key: str
    path: Path
    policy: Any
    pre: Any
    post: Any
    cfg: Any
    device: str
    load_s: float
    warmup_ms: float
    loaded_at: float = field(default_factory=time.monotonic)
    last_used: float = field(default_factory=time.monotonic)

    def reset(self) -> None:
        self.policy.reset()
        for proc in (self.pre, self.post):
            reset = getattr(proc, "reset", None)
            if callable(reset):
                reset()

    def predict(self, frame: dict[str, Any], task: str, robot_type: str) -> Any:
        import torch
        from lerobot.common.control_utils import predict_action

        self.last_used = time.monotonic()
        return predict_action(
            frame,
            self.policy,
            torch.device(self.device),
            self.pre,
            self.post,
            use_amp=False,
            task=task,
            robot_type=robot_type,
        )

    def view(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "device": self.device,
            "policy_type": getattr(self.cfg, "type", None),
            "load_s": round(self.load_s, 3),
            "warmup_ms": round(self.warmup_ms, 2),
        }


def load_policy(key: str, pdir: Path, device: str = "auto") -> LoadedPolicy:
    from lerobot.configs.policies import PreTrainedConfig
    from lerobot.policies.factory import get_policy_class, make_pre_post_processors

    t0 = time.perf_counter()
    dev = resolve_device(device)
    cfg = PreTrainedConfig.from_pretrained(pdir)
    cfg.device = dev
    cfg.pretrained_path = pdir
    policy_cls = get_policy_class(cfg.type)
    if (pdir / "adapter_config.json").is_file():  # pragma: no cover - needs peft extra
        from peft import PeftConfig, PeftModel

        peft_cfg = PeftConfig.from_pretrained(pdir)
        base = policy_cls.from_pretrained(peft_cfg.base_model_name_or_path, config=cfg)
        policy = PeftModel.from_pretrained(base, pdir, config=peft_cfg)
    else:
        policy = policy_cls.from_pretrained(pdir, config=cfg)
    policy.eval()
    pre, post = make_pre_post_processors(
        cfg, pretrained_path=pdir, preprocessor_overrides={"device_processor": {"device": dev}}
    )
    load_s = time.perf_counter() - t0
    lp = LoadedPolicy(key, pdir, policy, pre, post, cfg, dev, load_s, 0.0)
    # warm-up: one forward pass on a zero observation
    frame: dict[str, Any] = {}
    for k, ft in cfg.input_features.items():
        shape = tuple(ft.shape)
        if len(shape) == 3:  # image (C, H, W) -> camera layout (H, W, C) uint8
            frame[k] = np.zeros((shape[1], shape[2], shape[0]), dtype=np.uint8)
        else:
            frame[k] = np.zeros(shape, dtype=np.float32)
    t1 = time.perf_counter()
    lp.predict(frame, task="", robot_type="so_follower")
    lp.warmup_ms = (time.perf_counter() - t1) * 1000.0
    lp.reset()
    return lp
