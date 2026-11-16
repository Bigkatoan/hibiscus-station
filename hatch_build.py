"""Hatch build hook: ship the built Station UI inside the wheel and the sdist (spec §10 A8).

The UI is built by ``web/`` (``pnpm build`` -> ``web/dist``). At build time it is force-included as
``hibiscus_station/static``, so an sdist carries the built UI and a wheel built from that sdist
still has it. A pre-populated ``hibiscus_station/static`` (e.g. inside an sdist) is used when
``web/dist`` is absent. The build fails when neither exists, unless
``HIBISCUS_STATION_ALLOW_NO_WEB=1`` is set (API-only wheel).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class CustomBuildHook(BuildHookInterface):  # type: ignore[type-arg]
    def initialize(self, version: str, build_data: dict[str, Any]) -> None:
        if version == "editable":  # `uv sync` dev install: the UI is optional
            return
        root = Path(self.root)
        static = root / "hibiscus_station" / "static"
        dist = root / "web" / "dist"
        if (dist / "index.html").is_file():
            # Ship the fresh UI build without copying it into the source tree.
            build_data["force_include"][str(dist)] = "hibiscus_station/static"
            return
        if (static / "index.html").is_file():  # sdist / pre-populated tree
            return
        if os.environ.get("HIBISCUS_STATION_ALLOW_NO_WEB") == "1":
            return
        raise RuntimeError(
            "web/dist is missing: build the UI first (web: pnpm build) "
            "or set HIBISCUS_STATION_ALLOW_NO_WEB=1 for an API-only wheel"
        )
