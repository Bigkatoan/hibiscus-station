"""Policy vs robot compatibility check (spec §4.9). Shape mismatch is an error, never a silent resize."""

from __future__ import annotations

import importlib.util
from typing import Any

from hibiscus_station.models.registry import ModelEntry
from hibiscus_station.profiles import RobotProfile

ROBOT_TYPES_OK = {"so100_follower", "so101_follower", "so_follower", "hibiscus_mock_follower"}
EXTRA_FOR_POLICY = {
    "smolvla": ("transformers", "smolvla"),
    "pi0": ("transformers", "pi"),
    "pi05": ("transformers", "pi"),
    "diffusion": ("diffusers", "diffusion"),
}
IMAGE_PREFIX = "observation.images."


def default_camera_map(entry: ModelEntry, profile: RobotProfile) -> dict[str, str]:
    out = {}
    for key, ft in entry.input_features.items():
        if ft.type == "VISUAL" and key.startswith(IMAGE_PREFIX):
            name = key.removeprefix(IMAGE_PREFIX)
            if name in profile.cameras:
                out[key] = name
    return out


def check(
    entry: ModelEntry,
    profile: RobotProfile,
    camera_map: dict[str, str] | None = None,
    *,
    n_motors: int = 6,
    device: str = "cpu",
) -> dict[str, Any]:
    cmap = {**default_camera_map(entry, profile), **(camera_map or {})}
    checks: list[dict[str, Any]] = []
    warnings: list[str] = []

    state = entry.input_features.get("observation.state")
    if state is None:
        checks.append({"id": "state_dim", "ok": False, "code": "missing", "expected": [n_motors]})
    else:
        ok = state.shape == [n_motors]
        checks.append(
            {
                "id": "state_dim",
                "ok": ok,
                **({} if ok else {"code": "dim_mismatch", "expected": [n_motors], "actual": state.shape}),
            }
        )
    action = entry.output_features.get("action")
    if action is None:
        checks.append({"id": "action_dim", "ok": False, "code": "missing", "expected": [n_motors]})
    else:
        ok = action.shape == [n_motors]
        checks.append(
            {
                "id": "action_dim",
                "ok": ok,
                **({} if ok else {"code": "dim_mismatch", "expected": [n_motors], "actual": action.shape}),
            }
        )

    for key, ft in entry.input_features.items():
        if ft.type != "VISUAL":
            continue
        cam = cmap.get(key)
        cid = f"camera:{key}"
        if cam is None or cam not in profile.cameras:
            checks.append(
                {
                    "id": cid,
                    "ok": False,
                    "code": "camera_missing",
                    "expected": ft.shape,
                    "available": sorted(profile.cameras),
                }
            )
            continue
        cp = profile.cameras[cam]
        actual = [3, cp.height, cp.width]
        if ft.shape != actual:
            h, w = (ft.shape[1], ft.shape[2]) if len(ft.shape) == 3 else (cp.height, cp.width)
            checks.append(
                {
                    "id": cid,
                    "ok": False,
                    "code": "shape_mismatch",
                    "camera": cam,
                    "expected": ft.shape,
                    "actual": actual,
                    "fix": {"kind": "set_camera", "camera": cam, "width": w, "height": h},
                }
            )
        else:
            checks.append({"id": cid, "ok": True, "camera": cam})

    if entry.robot_type and entry.robot_type not in ROBOT_TYPES_OK:
        warnings.append(f"robot_type {entry.robot_type} in train config; profile is {profile.follower.type}")
    elif entry.robot_type:
        warnings.append(
            f"robot_type {entry.robot_type} in train config; profile is {profile.follower.type} (ok)"
        )

    extra = EXTRA_FOR_POLICY.get(entry.policy_type)
    if extra is not None and importlib.util.find_spec(extra[0]) is None:
        checks.append(
            {
                "id": "policy_extra",
                "ok": False,
                "code": "extra_missing",
                "hint": f"uv tool install 'hibiscus-station[{extra[1]}]'",
            }
        )
    else:
        checks.append({"id": "policy_extra", "ok": True})

    return {
        "ok": all(c["ok"] for c in checks),
        "policy_type": entry.policy_type,
        "device": device,
        "checks": checks,
        "warnings": warnings,
        "camera_map": cmap,
        "defaults": {"fps": entry.fps, "task": entry.task},
    }
