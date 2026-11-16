"""Real-browser screenshots of Hibiscus Station (mock mode), day + night, at 1440 px and 390 px.

    web/scripts/node.sh pnpm build:mock
    web/scripts/node.sh pnpm preview:mock  # http://127.0.0.1:18212
    docker run --rm --network host -u "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD":/w -w /w \
      mcr.microsoft.com/playwright/python:v1.49.1-noble \
      sh -c "pip install -q playwright==1.49.1 && python web/scripts/station_screenshots.py [--out DIR]"

Drives the mock station through teleop, a model run (all cameras as policy input) and the thermal
safe stop, and reports any page wider than the viewport (no horizontal scroll at 390 px). Files:
``screenshots/mock/<screen>-<theme>-<width>.png`` (git-ignored).
"""

from __future__ import annotations

import argparse
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

ROOT = Path(__file__).resolve().parents[2]


def overflow(page: Page) -> int:
    return page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")


def shoot(page: Page, out: Path, name: str, width: int, problems: list[str]) -> None:
    page.wait_for_timeout(700)
    name = f"{name}-{page.evaluate('document.documentElement.dataset.theme')}"
    page.screenshot(path=str(out / f"{name}-{width}.png"), full_page=True)
    over = overflow(page)
    if over > 0:
        problems.append(f"{name}@{width}: horizontal overflow {over}px")


def run(base: str, out: Path, themes: list[str]) -> list[str]:
    out.mkdir(parents=True, exist_ok=True)
    problems: list[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for theme, width in [(th, w) for th in themes for w in (1440, 390)]:
            ctx = browser.new_context(
                viewport={"width": width, "height": 900},
                locale="en-US",
                color_scheme=theme,  # type: ignore[arg-type]
                reduced_motion="reduce",
            )
            page = ctx.new_page()
            page.goto(f"{base}/?mock_connected=1&mock_paired=1&mock_heat=1.5")
            page.wait_for_selector("text=Hibiscus Station")
            shoot(page, out, "welcome", width, problems)
            for route in ("robot", "calibrate", "cameras", "datasets/picknplace_red", "settings"):
                page.goto(f"{base}/{route}")
                shoot(page, out, route.replace("/", "_"), width, problems)
            page.goto(f"{base}/teleop")
            page.get_by_role("button", name="Start teleop").click()
            page.wait_for_timeout(2500)
            shoot(page, out, "teleop", width, problems)
            page.get_by_role("button", name="Stop").first.click()
            page.wait_for_timeout(500)
            page.goto(f"{base}/run")
            page.get_by_role("button", name="picknplace ACT").first.click()
            page.get_by_role("button", name="Load").click()
            page.wait_for_timeout(2600)
            shoot(page, out, "run-setup", width, problems)
            page.get_by_role("button", name="Run on the robot").click()
            page.wait_for_timeout(4500)
            shoot(page, out, "run-live", width, problems)
            # mock_heat=1.5 °C/s on elbow_flex: warm → hot → critical safe stop.
            page.wait_for_selector("[data-testid=critical-banner]", timeout=30000)
            page.wait_for_timeout(800)
            shoot(page, out, "run-thermal-stop", width, problems)
            ctx.close()
        browser.close()
    return problems


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:18212")
    ap.add_argument("--out", default=str(ROOT / "screenshots" / "mock"))
    ap.add_argument("--themes", default="light,dark")
    args = ap.parse_args()
    issues = run(args.base, Path(args.out), args.themes.split(","))
    print("\n".join(issues) if issues else "no horizontal overflow")
