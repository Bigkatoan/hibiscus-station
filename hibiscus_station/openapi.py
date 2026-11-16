"""OpenAPI export (spec §5.1: committed at ``station/openapi.json``; a contract test checks it)."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

EXPORT_TOKEN = "openapi-export"  # noqa: S105 - placeholder, the app is never served


def export() -> str:
    from hibiscus_station.api.security import LocalAuth
    from hibiscus_station.app import create_app
    from hibiscus_station.station import Station

    with tempfile.TemporaryDirectory() as d:
        st = Station(Path(d), mock=False, cal_root=Path(d) / "cal")
        app = create_app(
            st, LocalAuth(token=EXPORT_TOKEN), static_dir=Path(d) / "nostatic", manage_lifecycle=False
        )
        doc = app.openapi()
    return json.dumps(doc, indent=2, sort_keys=True) + "\n"
