"""Fixtures of the browser tests: Chromium, the ACT checkpoint, the Station launcher.

Every test module here is marked ``e2e`` (deselected by default; ``pytest -m e2e tests/e2e`` or ``make e2e``).
They need ``web/dist`` (``pnpm build`` in ``web/``) and a Chromium for the pinned Playwright
(``uv run playwright install chromium``); without them they skip, unless ``HIBISCUS_E2E_REQUIRED=1``
(CI) turns the skip into a failure.
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from e2e_support import SPA, unavailable

CHECKPOINT = Path(os.environ.get("HIBISCUS_E2E_CHECKPOINT", "/nonexistent"))


@pytest.fixture(scope="session")
def browser() -> Iterator[Any]:
    if not (SPA / "index.html").is_file():
        unavailable(f"no built UI at {SPA}: run `pnpm build` in web/")
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        unavailable("playwright is not installed")
    with sync_playwright() as pw:
        try:
            b = pw.chromium.launch()
        except Exception as exc:
            unavailable(
                f"no Chromium for Playwright ({str(exc).splitlines()[0]}): playwright install chromium"
            )
        yield b
        b.close()


@pytest.fixture(scope="session")
def checkpoint() -> Path:
    """A real ACT ``pretrained_model`` (``HIBISCUS_E2E_CHECKPOINT``) or a random-weight one with the
    same features: one ``wrist_cam`` camera, 640x360."""
    if (CHECKPOINT / "config.json").is_file():
        return CHECKPOINT
    from hibiscus_station.mock.policy import make_dummy_act

    out = Path.home() / ".cache" / "hibiscus-station-e2e" / "pretrained_model"  # under an import root
    shutil.rmtree(out, ignore_errors=True)
    make_dummy_act(out, {"wrist_cam": (360, 640)})  # (height, width): same as the real checkpoint
    return out
