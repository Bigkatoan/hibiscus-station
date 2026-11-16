"""Helpers shared by the programs routers (architect-owned; keep tiny)."""

from __future__ import annotations

from typing import Any

from fastapi import Path

from hibiscus_station.api.schemas import Problem
from hibiscus_station.errors import StationError
from hibiscus_station.programs.schemas import ITEM_ID_RE, RUN_ID_RE, SIGNAL_NAME_RE, TRAJECTORY_ID_RE


# FastAPI binds a ``Path()`` default to the first parameter name it meets: build one per use.
def trajectory_id() -> Any:
    return Path(pattern=TRAJECTORY_ID_RE.pattern, description="t_<yyyymmdd>_<hhmmss>_<hex4>")


def item_id() -> Any:
    return Path(pattern=ITEM_ID_RE.pattern)


def signal_name() -> Any:
    return Path(pattern=SIGNAL_NAME_RE.pattern)


def run_id() -> Any:
    return Path(pattern=RUN_ID_RE.pattern)


PROBLEM: dict[int | str, dict[str, Any]] = {
    "default": {"model": Problem, "description": "RFC 9457 problem (spec §5.1)"}
}


def not_implemented(feature: str) -> StationError:
    """The contract stubs answer ``501 not_implemented`` until the owning team lands the feature."""
    return StationError("not_implemented", f"{feature} is not implemented yet", params={"feature": feature})
