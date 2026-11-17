"""Screen matrix (FL-7; the tooling of AT-82 / NFR-11): every main page, in every state, language,
theme (light / dark) and width (1280 / 390 px), against one ``hibiscus-station --mock``.

On every screen:

* **horizontal scroll**: the *page* must not be wider than the viewport (wide tables and canvases
  scroll inside their own box);
* **text** (vi): no English UI string that the Vietnamese table translates, no raw string key, no
  ``undefined`` / ``NaN`` / ``[object``, never "Hiệu chuẩn" (SRS term: "Hiệu chỉnh"); the
  non-text checks run in en too;
* **axe-core** (WCAG 2.1 A / AA rules): serious and critical violations.

Findings are compared with ``screen_matrix_known.json``: the problems this suite found when it was
introduced in M0, each to be fixed in M1 as a defect. A finding that is not in that file fails the
test; a known finding that no longer occurs is reported (delete its line). A ``*`` field matches any
value (live screens, e.g. a table that overflows its box depending on the numbers in it). Every run writes
``screenshots/e2e/matrix/<state>/<page>-<lang>-<theme>-<width>.png`` and ``report.json`` with all
findings, the moderate / minor axe results included. ``HIBISCUS_E2E_MATRIX_UPDATE=1`` rewrites the
known file from the run (review the diff: every new line is a new defect).

axe-core comes from ``web/node_modules/axe-core`` (``pnpm install`` in ``web/``) or
``HIBISCUS_AXE_JS``; without it the axe part is skipped (failed under ``HIBISCUS_E2E_REQUIRED=1``).
"""

from __future__ import annotations

import contextlib
import json
import os
import re
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from .e2e_support import (
    REQUIRED,
    SHOTS,
    UI,
    WEB,
    Driver,
    StationProc,
    english_only_strings,
    launch_station,
)

pytestmark = [pytest.mark.e2e, pytest.mark.timeout(1800)]

#: name: (path, the key of a button to press there first, or None)
PAGES: dict[str, tuple[str, str | None]] = {
    "welcome": ("/", None),
    "robot": ("/robot", None),
    "robot-edit": ("/robot", "common.edit"),  # the profile form (ports, calibration files)
    "calibrate": ("/calibrate", None),
    "cameras": ("/cameras", None),
    "teleop": ("/teleop", None),
    "record": ("/record", None),
    "replay": ("/replay", None),
    "upload": ("/upload", None),
    "datasets": ("/datasets", None),
    "train": ("/train", None),
    "run": ("/run", None),
    "programs": ("/programs", None),
    "models": ("/models", None),
    "sessions": ("/sessions", None),
    "settings": ("/settings", None),
}
COMBOS = [
    (lang, theme, width) for lang in ("vi", "en") for theme in ("light", "dark") for width in (1280, 390)
]
KNOWN = Path(__file__).with_name("screen_matrix_known.json")
OUT = SHOTS / "matrix"
AXE_JS = Path(os.environ.get("HIBISCUS_AXE_JS", WEB / "node_modules" / "axe-core" / "axe.min.js"))
AXE_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]
GATED_IMPACT = {"serious", "critical"}
FORBIDDEN_VI = ("Hiệu chuẩn",)
GARBAGE = re.compile(r"\bundefined\b|\bNaN\b|\[object ")
KEYISH = re.compile(r"\b[a-z_]+(?:\.[a-z_0-9]+)+\b")

_report: dict[str, list[dict[str, Any]]] = {}

#: text a user can read, or a screen reader says: visible text plus labels, titles, placeholders
_READABLE_JS = """() => [document.body.innerText,
    ...[...document.querySelectorAll('[aria-label],[title],[placeholder],img[alt]')].flatMap(el =>
        ['aria-label', 'title', 'placeholder', 'alt'].map(a => el.getAttribute(a) || ''))].join('\\n')"""

#: texts cut by their box (text-overflow / overflow hidden), e.g. a chip "Chưa kế…" (D-14)
_CLIPPED_JS = """() => { const out = new Set();
    for (const el of document.body.querySelectorAll('*')) {
        const box = el.getBoundingClientRect();
        if (box.width <= 2 || box.height <= 2) continue;  // visually hidden (sr-only)
        const cs = getComputedStyle(el);
        if (cs.clip !== 'auto' || cs.clipPath !== 'none') continue;
        if (!['hidden', 'clip'].includes(cs.overflowX) && cs.textOverflow !== 'ellipsis') continue;
        if (el.scrollWidth <= el.clientWidth + 1) continue;
        const own = [...el.childNodes].filter(n => n.nodeType === 3).map(n => n.textContent.trim()).join(' ').trim();
        const txt = own || (el.children.length === 0 ? el.textContent.trim() : '');
        if (txt) out.add(txt.slice(0, 60)); }
    return [...out]; }"""

#: text still under the floating STOP button with the page scrolled to its end, so no scrolling
#: uncovers it (D-13)
_COVERED_JS = """() => { const dock = document.querySelector('[data-testid=estop-dock]'); if (!dock) return [];
    window.scrollTo(0, document.documentElement.scrollHeight);
    const d = dock.getBoundingClientRect(); const out = new Set();
    const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    while (w.nextNode()) { const n = w.currentNode;
        if (!n.textContent.trim() || dock.contains(n)) continue;
        const r = document.createRange(); r.selectNodeContents(n);
        for (const b of r.getClientRects())
            if (b.width >= 1 && b.right > d.left && b.left < d.right && b.bottom > d.top && b.top < d.bottom) {
                out.add(n.textContent.trim().slice(0, 60)); break; } }
    window.scrollTo(0, 0); return [...out]; }"""


# ---------------------------------------------------------------------------------------- checks
def _axe(d: Driver) -> list[dict[str, Any]]:
    if not AXE_JS.is_file():
        return []
    d.page.add_script_tag(path=str(AXE_JS))
    return d.page.evaluate(  # type: ignore[no-any-return]
        """async (tags) => {
            const r = await axe.run(document, {runOnly: {type: "tag", values: tags}, resultTypes: ["violations"]});
            return r.violations.map(v => ({id: v.id, impact: v.impact, help: v.help,
                nodes: v.nodes.slice(0, 5).map(n => n.target.join(" ")), count: v.nodes.length}));
        }""",
        AXE_TAGS,
    )


def _settle(d: Driver) -> None:
    with contextlib.suppress(Exception):  # a stream keeps the network busy: the pause below is enough
        d.page.wait_for_load_state("networkidle", timeout=5000)
    d.page.wait_for_timeout(400)


def audit(d: Driver, name: str, state: str, theme: str, width: int) -> list[dict[str, Any]]:
    """Every finding of the screen now on ``d.page`` (and its screenshot)."""
    lang = d.ui.lang
    _settle(d)
    where = {"page": name, "state": state, "lang": lang, "theme": theme, "width": width}
    out: list[dict[str, Any]] = []
    shot = OUT / state / f"{name}-{lang}-{theme}-{width}.png"
    shot.parent.mkdir(parents=True, exist_ok=True)
    d.page.screenshot(path=str(shot), full_page=True)

    over = d.page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
    if over > 1:
        widest = d.page.evaluate(
            """() => { const vw = document.documentElement.clientWidth; let best = null, right = vw;
                for (const el of document.body.querySelectorAll('*')) {
                  const r = el.getBoundingClientRect();
                  if (r.right > right + 1) { right = r.right; best = el; } }
                if (!best) return null;
                const id = best.getAttribute('data-testid');
                return best.tagName.toLowerCase() + (id ? `[data-testid=${id}]` : '') +
                  (best.className && typeof best.className === 'string' ? '.' + best.className.split(' ').slice(0, 3).join('.') : ''); }"""
        )
        out.append({**where, "kind": "overflow", "detail": "", "px": over, "element": widest})

    for txt in d.page.evaluate(_CLIPPED_JS):
        out.append({**where, "kind": "clipped", "detail": txt})
    for txt in d.page.evaluate(_COVERED_JS):
        out.append({**where, "kind": "under-stop-button", "detail": txt})

    text = d.page.evaluate(_READABLE_JS)
    for m in sorted(set(GARBAGE.findall(text))):
        out.append({**where, "kind": "garbage", "detail": m.strip()})
    for m in sorted(set(KEYISH.findall(text))):
        if m in d.ui.table:
            out.append({**where, "kind": "raw-key", "detail": m})
    if lang == "vi":
        for s in sorted(_ENGLISH_ONLY):
            if s in text:
                out.append({**where, "kind": "english-in-vi", "detail": s})
        for s in FORBIDDEN_VI:
            if s in text:
                out.append({**where, "kind": "forbidden-term", "detail": s})

    for v in _axe(d):
        gated = v["impact"] in GATED_IMPACT
        out.append(
            {**where, "kind": "axe" if gated else "axe-info", "detail": v["id"], "impact": v["impact"]}
            | {"help": v["help"], "nodes": v["nodes"], "count": v["count"]}
        )
    return out


_ENGLISH_ONLY = english_only_strings()


def key_of(f: dict[str, Any]) -> str:
    """The identity of a finding (stable between runs: no pixel counts, no node lists, no live numbers)."""
    f = {**f, "detail": re.sub(r"\d+(?:[.,]\d+)?", "#", str(f["detail"]))}
    return "|".join(str(f[k]) for k in ("kind", "page", "state", "lang", "theme", "width", "detail"))


# ---------------------------------------------------------------------------------------- station
@pytest.fixture(scope="module")
def matrix_station(tmp_path_factory: pytest.TempPathFactory) -> Iterator[StationProc]:
    with launch_station(tmp_path_factory.mktemp("matrix"), "mock") as station:
        yield station


@pytest.fixture(scope="module")
def session_state(browser: Any, matrix_station: StationProc) -> Any:
    """One login, shared by every browser context of the matrix (the link is one-time)."""
    d = Driver(browser, matrix_station, "en")
    d.login()
    state = d.ctx.storage_state()
    d.close()
    return state


def _driver(browser: Any, station: StationProc, state: Any, lang: str, theme: str, width: int) -> Driver:
    return Driver(browser, station, lang, width=width, height=900, color_scheme=theme, storage_state=state)


# ---------------------------------------------------------------------------------------- tests
def _check(state: str, findings: list[dict[str, Any]]) -> None:
    _report[state] = findings
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "report.json").write_text(json.dumps(_report, indent=1, ensure_ascii=False), encoding="utf-8")
    gated = [f for f in findings if f["kind"] != "axe-info"]
    found = {key_of(f): f for f in gated}
    known_all: dict[str, str] = json.loads(KNOWN.read_text(encoding="utf-8")) if KNOWN.is_file() else {}
    known = {k: v for k, v in known_all.items() if k.split("|")[2] == state}

    def matched(key: str) -> bool:
        return any(_matches(key, p) for p in known)

    if os.environ.get("HIBISCUS_E2E_MATRIX_UPDATE") == "1":
        keep = {k: v for k, v in known_all.items() if k.split("|")[2] != state}
        keep.update({p: v for p, v in known.items() if any(_matches(k, p) for k in found)})
        keep.update({k: "M1: found by the M0 screen matrix" for k in found if not matched(k)})
        KNOWN.write_text(
            json.dumps(dict(sorted(keep.items())), indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        return
    gone = sorted(p for p in known if not any(_matches(k, p) for k in found))
    if gone:
        print(f"{len(gone)} known finding(s) no longer occur; delete them from {KNOWN.name}:")
        print("\n".join(gone))
    new = sorted(k for k in found if not matched(k))
    assert not new, f"{len(new)} new screen problem(s) ({state}):\n" + "\n".join(
        f"{k}  {json.dumps({x: found[k][x] for x in ('px', 'element', 'help', 'nodes') if x in found[k]}, ensure_ascii=False)}"
        for k in new
    )


def _matches(key: str, pattern: str) -> bool:
    """A known entry names one finding, or several with ``*`` fields (live screens vary a little)."""
    if "*" not in pattern:
        return key == pattern
    parts, pats = key.split("|"), pattern.split("|")
    return len(parts) == len(pats) and all(p in ("*", k) for k, p in zip(parts, pats, strict=True))


def _require_axe() -> None:
    if not AXE_JS.is_file():
        msg = f"axe-core not found at {AXE_JS}: `pnpm install` in web/ or set HIBISCUS_AXE_JS"
        if REQUIRED:
            pytest.fail(msg)
        print(f"WARNING: {msg}; the axe checks are skipped")


def _all_pages(browser: Any, station: StationProc, state: str, session: Any) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for lang, theme, width in COMBOS:
        d = _driver(browser, station, session, lang, theme, width)
        try:
            for name, (path, press) in PAGES.items():
                d.go(path)
                if press:
                    d.button(press).first.click()
                findings += audit(d, name, state, theme, width)
            assert not d.errors, d.errors
        finally:
            d.close()
    return findings


@pytest.mark.slow
def test_matrix_disconnected(browser: Any, matrix_station: StationProc, session_state: Any) -> None:
    """No robot connected: every step shows why it is locked (the "disabled with a reason" state)."""
    _require_axe()
    d = _driver(browser, matrix_station, session_state, "en", "light", 1280)
    if (d.status().get("robot") or {}).get("connected"):
        d.api("POST", "/robots/disconnect")
        d.wait_state("disconnected")
    d.close()
    _check("disconnected", _all_pages(browser, matrix_station, "disconnected", session_state))


@pytest.mark.slow
def test_matrix_ready(browser: Any, matrix_station: StationProc, session_state: Any) -> None:
    """Connected and calibrated, idle, nothing recorded yet (the "empty" lists)."""
    _require_axe()
    d = _driver(browser, matrix_station, session_state, "en", "light", 1280)
    d.connect_and_calibrate()
    d.close()
    _check("ready", _all_pages(browser, matrix_station, "ready", session_state))


@pytest.mark.slow
def test_matrix_teleop_and_estop(browser: Any, matrix_station: StationProc, session_state: Any) -> None:
    """Teleop running (live joints, STOP button over the page), then the latched e-stop."""
    _require_axe()
    findings: list[dict[str, Any]] = []
    for lang, theme, width in COMBOS:
        d = _driver(browser, matrix_station, session_state, lang, theme, width)
        try:
            d.connect_and_calibrate()
            d.go("/teleop")
            d.start_with_leader("teleop.start", "/sessions/teleop")
            d.wait_state("teleop")
            d.page.get_by_test_id("joint-shoulder_pan").wait_for(timeout=15000)
            findings += audit(d, "teleop", "teleop", theme, width)
            d.focus_body()
            d.page.keyboard.press("Space")
            d.wait_state("estopped", timeout=10)
            d.page.get_by_test_id("estop-dock").wait_for(timeout=10000)
            findings += audit(d, "teleop", "estopped", theme, width)
            d.go("/robot")
            findings += audit(d, "robot", "estopped", theme, width)
            d.button("estop.reset").click()
            d.wait_state("idle")
            d.api("POST", "/robots/torque", {"arm": "follower", "enabled": True})
            assert not d.errors, d.errors
        finally:
            d.close()
    _check("teleop", [f for f in findings if f["state"] == "teleop"])
    _check("estopped", [f for f in findings if f["state"] == "estopped"])


SELFTEST_HTML = """<!doctype html><html lang="vi"><body style="margin:0;font:16px sans-serif">
<h1>Trang thử</h1>
<div style="width:2000px">rộng hơn màn hình</div>
<span style="display:inline-block;width:40px;overflow:hidden;white-space:nowrap;text-overflow:ellipsis">Chưa kết nối robot</span>
<p>Start calibration</p><p>Hiệu chuẩn</p><p>calibrate.start</p><p>NaN</p>
<button aria-label="Use current pose as rest pose">x</button>
<p style="color:#808080;background:#8a8a8a">chữ khó đọc</p>
<div data-testid="estop-dock" style="position:fixed;right:0;bottom:0;width:200px;height:100px"></div>
<p style="position:fixed;right:20px;bottom:20px;margin:0">dưới nút dừng</p>
</body></html>"""


def test_audit_finds_each_kind_of_problem(browser: Any) -> None:
    """The matrix's own checks, on a page with one problem of each kind (no Station needed)."""
    ctx = browser.new_context(locale="vi-VN", viewport={"width": 390, "height": 600}, bypass_csp=True)
    try:
        page = ctx.new_page()
        page.set_content(SELFTEST_HTML)
        d = SimpleNamespace(page=page, ui=UI("vi"))
        found = audit(d, "selftest", "selftest", "light", 390)  # type: ignore[arg-type]
    finally:
        ctx.close()
    got = {(f["kind"], f["detail"]) for f in found}
    expected = {
        ("overflow", ""),
        ("clipped", "Chưa kết nối robot"),
        ("english-in-vi", "Start calibration"),
        ("english-in-vi", "Use current pose as rest pose"),  # an aria-label counts: a screen reader says it
        ("forbidden-term", "Hiệu chuẩn"),
        ("raw-key", "calibrate.start"),
        ("garbage", "NaN"),
        ("under-stop-button", "dưới nút dừng"),
    }
    if AXE_JS.is_file():
        expected.add(("axe", "color-contrast"))
    assert expected <= got, sorted(expected - got)
