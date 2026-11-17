"""Shared helpers of the browser tests (``tests/e2e``): the UI strings, a Station process, a driver.

* :class:`UI` reads the UI's own string tables (``web/src/station/i18n/*.json`` and
  ``web/src/i18n/*/translation.json``), so a test names a control by its key and runs unchanged in
  ``en`` and ``vi``.
* :func:`launch_station` starts a real ``hibiscus-station`` (``--mock``, or the real serial stack
  against two STS3215 chains emulated on pseudo-terminals, ``tests/sts_emulator.py``) on a port of
  ``HIBISCUS_E2E_PORTS`` (default 18310-18329) and yields a :class:`StationProc`.
* :class:`Driver` is one browser context logged in to that Station, with the API and status helpers
  the flows need.
"""

from __future__ import annotations

import contextlib
import json
import math
import os
import re
import shutil
import socket
import subprocess
import sys
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parents[2]
WEB = REPO / "web"
SPA = Path(os.environ.get("HIBISCUS_STATION_STATIC", WEB / "dist"))
SHOTS = Path(os.environ.get("HIBISCUS_E2E_SHOTS", REPO / "screenshots" / "e2e"))
ARMS = ("follower", "leader")
#: CI: a missing UI build, Chromium or axe-core fails the tests instead of skipping them
REQUIRED = os.environ.get("HIBISCUS_E2E_REQUIRED") == "1"


def unavailable(reason: str) -> None:
    """Skip a test whose tooling is missing, or fail it where the tooling must exist (CI)."""
    import pytest

    if REQUIRED:
        pytest.fail(f"{reason} (HIBISCUS_E2E_REQUIRED=1)")
    pytest.skip(reason)


# ---------------------------------------------------------------------------------------- strings
def _flatten(d: dict[str, Any], prefix: str = "") -> dict[str, str]:
    out: dict[str, str] = {}
    for k, v in d.items():
        if isinstance(v, dict):
            out.update(_flatten(v, f"{prefix}{k}."))
        else:
            out[f"{prefix}{k}"] = str(v)
    return out


@cache
def _table(lang: str) -> dict[str, str]:
    station = json.loads((WEB / "src" / "station" / "i18n" / f"{lang}.json").read_text(encoding="utf-8"))
    app = json.loads((WEB / "src" / "i18n" / lang / "translation.json").read_text(encoding="utf-8"))
    return {**{f"app:{k}": v for k, v in _flatten(app).items()}, **_flatten(station)}


class UI:
    """The UI strings of one language. ``t("calibrate.start")``; ``t("record.done", n=2)``."""

    def __init__(self, lang: str) -> None:
        self.lang = lang
        self.table = _table(lang)
        #: what the browser is told, so the UI picks the language itself (no stored preference)
        self.locale = {"en": "en-US", "vi": "vi-VN"}[lang]

    def t(self, key: str, **values: object) -> str:
        """The string, with ``{{name}}`` replaced; an unfilled placeholder cuts the string there."""
        s = self.table[key]
        for name, value in values.items():
            s = s.replace("{{" + name + "}}", str(value))
        return s.split("{{", 1)[0].rstrip()

    def exact(self, key: str, **values: object) -> re.Pattern[str]:
        """An accessible-name pattern: the string alone (icons carry no name), spacing allowed."""
        return re.compile(r"^\s*" + re.escape(self.t(key, **values)) + r"\s*$")

    def first_words(self, key: str) -> str:
        """The string up to its first ellipsis / full stop (a banner's stable head)."""
        return re.split(r"[…:.]", self.table[key], maxsplit=1)[0].strip()


def english_only_strings(min_len: int = 12) -> set[str]:
    """English strings that the Vietnamese table translates: seeing one in ``vi`` is a leak.

    Short ones and ones with placeholders are left out (they also occur inside other words and
    sentences, or are not the whole visible text)."""
    en, vi = _table("en"), _table("vi")
    return {
        v
        for k, v in en.items()
        if v != vi.get(k) and "{{" not in v and " " in v and len(v) >= min_len and v not in vi.values()
    }


# ---------------------------------------------------------------------------------------- process
def free_port() -> int:
    """A free port of ``HIBISCUS_E2E_PORTS`` (``lo-hi``, default 18310-18329; ``0`` = any)."""
    spec = os.environ.get("HIBISCUS_E2E_PORTS", "18310-18329")
    if spec == "0":
        candidates: list[int] = [0]
    else:
        lo, _, hi = spec.partition("-")
        candidates = list(range(int(lo), int(hi or lo) + 1))
    for port in candidates:
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", port))
            except OSError:
                continue
            return int(s.getsockname()[1])
    raise RuntimeError(f"no free port in HIBISCUS_E2E_PORTS={spec}")


def wait_for(pred: Callable[[], Any], timeout: float = 30.0, what: str = "condition") -> Any:
    deadline = time.monotonic() + timeout
    last: Any = None
    while time.monotonic() < deadline:
        try:
            last = pred()
        except Exception as exc:  # retry on transient errors
            last = exc
        else:
            if last:
                return last
        time.sleep(0.2)
    raise AssertionError(f"timed out waiting for {what} (last: {str(last)[:300]})")


def sweep(emu: Any) -> None:
    """An STS emulator "hand" that moves every torque-off joint (calibration ranges, teleop)."""
    emu.hand = lambda i, t: 2048 + 400 * math.sin(2 * math.pi * 0.8 * t + i)


@dataclass
class StationProc:
    """A running ``hibiscus-station`` and the controls of its (mock or emulated) leader hand."""

    backend: str  # "mock" | "sts"
    base: str
    login: str
    home: Path
    log: Path
    emulators: dict[str, Any] = field(default_factory=dict)
    _api: Callable[[str, str, Any], Any] | None = None

    @property
    def mock(self) -> bool:
        return self.backend == "mock"

    def bind_api(self, api: Callable[[str, str, Any], Any]) -> None:
        self._api = api

    def leader_follows(self) -> None:
        """The leader "hand" holds the follower's pose (a deterministic teleop / record start)."""
        if self.mock:
            assert self._api
            self._api("POST", "/mock/inject", {"port": "mock://leader", "hand": "follow"})
        else:
            f, ld = self.emulators["follower"], self.emulators["leader"]
            ld.hand = lambda i, _t: f.servos[i].actual - f.servos[i].offset

    def leader_sweeps(self) -> None:
        """Back to the demo hand: the leader moves every joint, so the follower visibly follows."""
        if self.mock:
            assert self._api
            self._api("POST", "/mock/inject", {"port": "mock://leader", "hand": "default"})
        else:
            sweep(self.emulators["leader"])

    def log_tail(self, n: int = 4000) -> str:
        return self.log.read_text(encoding="utf-8", errors="replace")[-n:]


def _profile(backend: str, ports: dict[str, str], cameras: dict[str, Any]) -> dict[str, Any]:
    kind = {"mock": "hibiscus_mock", "sts": "so101"}[backend]
    return {
        "id": "desk",
        "name": "Desk SO-101 (mock)" if backend == "mock" else "Desk SO-101 (emulated bus)",
        "follower": {
            "type": f"{kind}_follower",
            "port": ports["follower"],
            "calibration_id": "desk_follower",
        },
        "leader": {"type": f"{kind}_leader", "port": ports["leader"], "calibration_id": "desk_leader"},
        "cameras": cameras,
        "safety_ack": True,
    }


@contextlib.contextmanager
def launch_station(
    tmp_path: Path, backend: str = "mock", cameras: dict[str, Any] | None = None
) -> Iterator[StationProc]:
    """``hibiscus-station`` with one SO-101 profile (follower + leader), uncalibrated."""
    home = tmp_path / "home"
    home.mkdir(parents=True)
    emulators: dict[str, Any] = {}
    if backend == "sts":
        if sys.platform == "win32":  # pragma: no cover
            import pytest

            pytest.skip("the STS emulator needs pseudo-terminals (POSIX)")
        from sts_emulator import STSEmulator

        emulators = {"follower": STSEmulator(seed=1), "leader": STSEmulator(seed=2)}
        for emu in emulators.values():
            sweep(emu)
        ports = {arm: emu.port for arm, emu in emulators.items()}
    else:
        ports = {arm: f"mock://{arm}" for arm in ARMS}
    profile = _profile(backend, ports, cameras or {})
    (home / "robots.yaml").write_text(yaml.safe_dump({"version": 1, "active": "desk", "robots": [profile]}))
    port = free_port()
    exe = shutil.which("hibiscus-station", path=str(Path(sys.executable).parent)) or shutil.which(
        "hibiscus-station"
    )
    assert exe, "hibiscus-station is not installed in this environment"
    env = {
        **os.environ,
        "HIBISCUS_STATION_STATIC": str(SPA),
        "HF_LEROBOT_CALIBRATION": str(tmp_path / "calibration"),
        "HIBISCUS_STATION_HOME": str(home),
    }
    log_path = tmp_path / "station.log"
    log = log_path.open("w+", encoding="utf-8")
    args = [exe, "--no-browser", "--port", str(port), "--home", str(home)]
    if backend == "mock":
        args.insert(1, "--mock")
    proc = subprocess.Popen(args, stdout=log, stderr=subprocess.STDOUT, env=env)  # noqa: S603 - our script

    def login_url() -> str | None:
        log.seek(0)
        m = re.search(r"http://127\.0\.0\.1:\d+/auth\?t=\S+", log.read())
        if proc.poll() is not None:
            raise RuntimeError("hibiscus-station exited")
        return m.group(0) if m else None

    try:
        url = wait_for(login_url, 120, "the login URL")
        wait_for(lambda: socket.create_connection(("127.0.0.1", port), 1).close() or True, 30, "the port")
        yield StationProc(backend, f"http://127.0.0.1:{port}", url, home, log_path, emulators)
    finally:
        proc.terminate()
        try:
            proc.wait(20)
        except subprocess.TimeoutExpired:
            proc.kill()
        log.close()
        for emu in emulators.values():
            emu.close()
        print("---- hibiscus-station log tail ----\n" + log_path.read_text(errors="replace")[-4000:])


# ---------------------------------------------------------------------------------------- browser
class Driver:
    """One browser context (language, theme, width) logged in to a Station."""

    def __init__(
        self,
        browser: Any,
        station: StationProc,
        lang: str = "en",
        *,
        width: int = 1440,
        height: int = 1000,
        color_scheme: str = "light",
        storage_state: Any = None,
        shots: Path = SHOTS,
    ) -> None:
        self.ui = UI(lang)
        self.station = station
        self.base = station.base
        self.shots = shots
        self.ctx = browser.new_context(
            locale=self.ui.locale,
            viewport={"width": width, "height": height},
            color_scheme=color_scheme,
            reduced_motion="reduce",
            bypass_csp=True,  # axe-core is injected as an inline script; the app's own CSP is unchanged
            storage_state=storage_state,
        )
        self.page = self.ctx.new_page()
        self.errors: list[str] = []
        self.page.on("pageerror", lambda e: self.errors.append(str(e)))
        station.bind_api(self.api)

    def t(self, key: str, **values: object) -> str:
        return self.ui.t(key, **values)

    def login(self) -> None:
        from playwright.sync_api import expect

        self.page.goto(self.station.login)
        expect(self.page).to_have_url(f"{self.base}/")

    def close(self) -> None:
        self.ctx.close()

    # ------------------------------------------------------------------ API
    def api(self, method: str, path: str, data: Any = None, *, ok: bool = True) -> Any:
        r = self.ctx.request.fetch(
            f"{self.base}/api/v1{path}",
            method=method,
            headers={"X-Station": "1", "Content-Type": "application/json"},
            data=json.dumps(data) if data is not None else None,
        )
        if ok:
            assert r.ok, f"{method} {path}: {r.status} {r.text()[:300]}"
        return r.json() if r.status != 204 else None

    def status(self) -> dict[str, Any]:
        return self.api("GET", "/status")  # type: ignore[no-any-return]

    def wait_state(self, *states: str, timeout: float = 30.0) -> dict[str, Any]:
        try:
            return wait_for(  # type: ignore[no-any-return]
                lambda: (s := self.status())["state"] in states and s, timeout, f"state in {states}"
            )
        except AssertionError as exc:
            alerts = [a.inner_text() for a in self.page.get_by_role("alert").all()]
            raise AssertionError(
                f"{exc}; status={json.dumps(self.status())[:800]}; alerts={alerts}"
            ) from None

    # ------------------------------------------------------------------ page
    def go(self, path: str) -> None:
        from playwright.sync_api import expect

        self.page.goto(f"{self.base}{path}")
        expect(self.page.get_by_role("heading", level=1)).to_be_visible()
        # the control socket is open (no "Reconnecting…" banner)
        expect(self.page.get_by_text(self.ui.first_words("banner.reconnecting"))).to_have_count(
            0, timeout=15000
        )

    def button(self, key: str, scope: Any = None, **values: object) -> Any:
        return (scope or self.page).get_by_role("button", name=self.ui.exact(key, **values))

    def shot(self, name: str, *, dark: bool = False) -> None:
        self.shots.mkdir(parents=True, exist_ok=True)
        tag = f"{name}-{self.ui.lang}"
        self.page.screenshot(path=str(self.shots / f"{tag}.png"), full_page=False)
        if dark:  # the same screen in the night theme (theme preference "system" follows the OS)
            self.page.emulate_media(color_scheme="dark")
            self.page.wait_for_timeout(300)
            self.page.screenshot(path=str(self.shots / f"{tag}-dark.png"), full_page=False)
            self.page.emulate_media(color_scheme="light")

    def focus_body(self) -> None:
        """Focus outside any field, so Space / arrows / Esc reach the page shortcuts."""
        self.page.locator("body").click(position={"x": 5, "y": 5})

    def start_with_leader(self, key: str, endpoint: str) -> None:
        """Press a start button with the leader "hand" holding the follower pose.

        The demo hand sweeps every joint, so waiting for the sweep to pass the follower pose is a
        matter of luck on a slow runner (D-8, M1). The hand mirrors the follower for the start only
        (the start check itself is unchanged; ``leader_far`` is covered by tests/test_owner.py) and
        sweeps again afterwards, so the follower visibly follows it.
        """
        self.station.leader_follows()
        try:
            for _ in range(20):
                with self.page.expect_response(lambda r: r.url.endswith(endpoint)) as resp:
                    self.button(key).click()
                if resp.value.ok:
                    return
                assert resp.value.json()["code"] == "leader_far", resp.value.text()
                time.sleep(0.5)
            raise AssertionError(f"{key}: the leader never came close to the follower")
        finally:
            self.station.leader_sweeps()

    # ------------------------------------------------------------------ API-only setup (screen matrix)
    def connect_and_calibrate(self) -> None:
        """Connect and calibrate both arms through the API (the UI flow has its own test)."""
        st = self.status()
        if not (st.get("robot") or {}).get("connected"):
            self.api("POST", "/robots/desk/connect")
            st = self.wait_state("idle", timeout=60)
        for arm in ARMS:
            if st["robot"]["arms"][arm]["calibrated"]:
                continue
            self.api("POST", "/calibration/start", {"arm": arm, "id": f"desk_{arm}", "keep_existing": False})
            self.api("POST", "/calibration/step", {"action": "set_home"})
            time.sleep(2.5)  # the hand sweeps every joint through a big enough range
            wait_for(
                lambda: (
                    self.api("POST", "/calibration/step", {"action": "finish_ranges"}, ok=False)
                    and self.status()["state"] == "idle"
                ),
                30,
                f"{arm} calibration saved",
            )
            st = self.wait_state("idle")
        assert all(st["robot"]["arms"][a]["calibrated"] for a in ARMS), st
