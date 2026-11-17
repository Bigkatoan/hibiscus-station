"""End-to-end: the built Station UI against a real ``hibiscus-station --mock`` process (spec §6, §9).

Drives Chromium (Playwright) through connect → calibrate → cameras → teleop → over-temperature
safe stop → record 2 episodes with the keyboard → LeRobotDataset loads → import the real ACT
checkpoint → run it with every camera, joints, temperatures and the Space e-stop. Screenshots go
to ``screenshots/e2e/`` (git-ignored; ``HIBISCUS_E2E_SHOTS`` overrides).

Needs ``web/dist`` (``pnpm build`` in ``web/``) and a Chromium for Playwright 1.63
(``uv run playwright install chromium``); skipped otherwise. ``HIBISCUS_E2E_CHECKPOINT`` may point
at a real ACT ``pretrained_model`` folder whose input features match a ``wrist_cam`` camera;
without it a random-weight ACT with the same features is used.

    uv run pytest tests/e2e -m e2e
"""

from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
import yaml

pytestmark = [pytest.mark.e2e, pytest.mark.timeout(600)]

REPO = Path(__file__).resolve().parents[2]
SPA = Path(os.environ.get("HIBISCUS_STATION_STATIC", REPO / "web" / "dist"))
SHOTS = Path(os.environ.get("HIBISCUS_E2E_SHOTS", REPO / "screenshots" / "e2e"))
CHECKPOINT = Path(os.environ.get("HIBISCUS_E2E_CHECKPOINT", "/nonexistent"))
DATASET = "e2e_picknplace"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _wait(pred: Callable[[], Any], timeout: float = 30.0, what: str = "condition") -> Any:
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


def _image_features(pdir: Path) -> dict[str, tuple[int, int]]:
    cfg = json.loads((pdir / "config.json").read_text(encoding="utf-8"))
    out = {}
    for key, ft in cfg["input_features"].items():
        if ft["type"] == "VISUAL":
            _, h, w = ft["shape"]
            out[key.removeprefix("observation.images.")] = (w, h)
    return out


@pytest.fixture(scope="module")
def checkpoint(tmp_path_factory: pytest.TempPathFactory) -> Path:
    if (CHECKPOINT / "config.json").is_file():
        return CHECKPOINT
    from hibiscus_station.mock.policy import make_dummy_act

    out = Path.home() / ".cache" / "hibiscus-station-e2e" / "pretrained_model"  # under an import root
    shutil.rmtree(out, ignore_errors=True)
    make_dummy_act(out, {"wrist_cam": (360, 640)})  # (height, width): same as the real checkpoint
    return out


@pytest.fixture(scope="module")
def browser() -> Iterator[Any]:
    if not (SPA / "index.html").is_file():
        pytest.skip(f"no built UI at {SPA}: run `pnpm build` in web/")
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        pytest.skip("playwright is not installed")
    with sync_playwright() as pw:
        try:
            b = pw.chromium.launch()
        except Exception as exc:
            pytest.skip(
                f"no Chromium for Playwright ({str(exc).splitlines()[0]}): playwright install chromium"
            )
        yield b
        b.close()


@pytest.fixture
def station_proc(tmp_path: Path) -> Iterator[tuple[str, str, Path]]:
    """A real ``hibiscus-station --mock`` with a mock follower + leader profile and no cameras yet."""
    home = tmp_path / "home"
    home.mkdir()
    profile = {
        "id": "desk",
        "name": "Desk SO-101 (mock)",
        "follower": {
            "type": "hibiscus_mock_follower",
            "port": "mock://follower",
            "calibration_id": "desk_follower",
        },
        "leader": {"type": "hibiscus_mock_leader", "port": "mock://leader", "calibration_id": "desk_leader"},
        "cameras": {},
        "safety_ack": True,
    }
    (home / "robots.yaml").write_text(yaml.safe_dump({"version": 1, "active": "desk", "robots": [profile]}))
    port = _free_port()
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
    log = (tmp_path / "station.log").open("w+")
    proc = subprocess.Popen(  # noqa: S603 - our own console script
        [exe, "--mock", "--no-browser", "--port", str(port), "--home", str(home)],
        stdout=log,
        stderr=subprocess.STDOUT,
        env=env,
    )

    def login_url() -> str | None:
        log.seek(0)
        m = re.search(r"http://127\.0\.0\.1:\d+/auth\?t=\S+", log.read())
        if proc.poll() is not None:
            raise RuntimeError("hibiscus-station exited")
        return m.group(0) if m else None

    try:
        url = _wait(login_url, 120, "the login URL")
        _wait(lambda: socket.create_connection(("127.0.0.1", port), 1).close() or True, 30, "the port")
        yield f"http://127.0.0.1:{port}", url, home
    finally:
        proc.terminate()
        try:
            proc.wait(20)
        except subprocess.TimeoutExpired:
            proc.kill()
        log.seek(0)
        tail = log.read()[-4000:]
        log.close()
        print("---- hibiscus-station log tail ----\n" + tail)


def test_station_ui_end_to_end(browser: Any, station_proc: tuple[str, str, Path], checkpoint: Path) -> None:
    from playwright.sync_api import expect

    base, login, home = station_proc
    SHOTS.mkdir(parents=True, exist_ok=True)
    ctx = browser.new_context(locale="en-US", viewport={"width": 1440, "height": 1000})
    page = ctx.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))

    def api(method: str, path: str, data: Any = None) -> Any:
        r = ctx.request.fetch(
            f"{base}/api/v1{path}",
            method=method,
            headers={"X-Station": "1", "Content-Type": "application/json"},
            data=json.dumps(data) if data is not None else None,
        )
        assert r.ok, f"{method} {path}: {r.status} {r.text()[:300]}"
        return r.json() if r.status != 204 else None

    def status() -> dict[str, Any]:
        return api("GET", "/status")  # type: ignore[no-any-return]

    def wait_state(*states: str, timeout: float = 30.0) -> dict[str, Any]:
        try:
            return _wait(  # type: ignore[no-any-return]
                lambda: (s := status())["state"] in states and s, timeout, f"state in {states}"
            )
        except AssertionError as exc:
            alerts = [a.inner_text() for a in page.get_by_role("alert").all()]
            raise AssertionError(f"{exc}; status={json.dumps(status())[:800]}; alerts={alerts}") from None

    def start_with_leader(button: str, endpoint: str) -> None:
        """Press a start button with the mock leader "hand" holding the follower pose.

        The demo hand sweeps every joint at its own frequency, so waiting for the sweep to pass the
        follower pose is a matter of luck on a slow runner. The hand mirrors the follower for the
        start only (the start check itself is unchanged; ``leader_far`` is covered by
        tests/test_owner.py) and sweeps again afterwards, so the follower visibly follows it.
        """
        leader = {"port": "mock://leader"}
        api("POST", "/mock/inject", {**leader, "hand": "follow", "follow_port": "mock://follower"})
        try:
            for _ in range(20):
                with page.expect_response(lambda r: r.url.endswith(endpoint)) as resp:
                    page.get_by_role("button", name=button).click()
                if resp.value.ok:
                    return
                assert resp.value.json()["code"] == "leader_far", resp.value.text()
                time.sleep(0.5)
            raise AssertionError(f"{button}: the leader never came close to the follower")
        finally:
            api("POST", "/mock/inject", {**leader, "hand": "default"})

    def shot(name: str, *, dark: bool = False) -> None:
        page.screenshot(path=str(SHOTS / f"{name}.png"), full_page=False)
        if dark:  # the same screen in the night theme (theme preference "system" follows the OS)
            page.emulate_media(color_scheme="dark")
            page.wait_for_timeout(300)
            page.screenshot(path=str(SHOTS / f"{name}-dark.png"), full_page=False)
            page.emulate_media(color_scheme="light")

    def go(path: str) -> None:
        page.goto(f"{base}{path}")
        expect(page.get_by_role("heading", level=1)).to_be_visible()
        expect(page.get_by_text("Reconnecting")).to_have_count(0, timeout=15000)  # control socket open

    # ---------------------------------------------------------------- login (one-time link → cookie)
    page.goto(login)
    expect(page).to_have_url(f"{base}/")

    # ---------------------------------------------------------------- 1. connect
    go("/robot")
    page.get_by_role("button", name="Connect", exact=True).click()
    wait_state("idle")
    expect(page.get_by_text("connected", exact=True).first).to_be_visible()
    shot("01-robot-connected", dark=True)
    # QC 0.2.9 QD-6: with Robot 3D shown (the default) the motor health tables fit at 1280 / 1440
    expect(page.get_by_test_id("motor-leader-gripper")).to_be_visible(timeout=15000)
    for width in (1280, 1440):
        page.set_viewport_size({"width": width, "height": 1000})
        page.wait_for_timeout(300)
        overflow = page.evaluate(
            """() => [...document.querySelectorAll('[data-testid="motor-health"] table')]
                .map((t) => [t.parentElement.scrollWidth, t.parentElement.clientWidth])
                .filter(([s, c]) => s > c + 1)"""
        )
        assert overflow == [], f"motor health scrolls sideways at {width} px: {overflow}"
    page.set_viewport_size({"width": 1440, "height": 1000})

    # ---------------------------------------------------------------- 2. calibrate both arms
    go("/calibrate")
    for arm in ("follower", "leader"):
        page.get_by_test_id(f"cal-step-{arm}").click()  # the wizard stepper (0.2.7 calibration)
        page.get_by_role("button", name=re.compile("Start calibration|Recalibrate")).first.click()
        expect(page.get_by_test_id("cal-home")).to_be_visible()
        page.get_by_role("button", name="Set middle").click()
        expect(page.get_by_test_id("cal-ranges")).to_be_visible()
        # the mock "hand" sweeps every joint; rows turn green once the range is big enough
        expect(page.get_by_test_id("range-shoulder_pan")).to_have_attribute("data-ok", "true", timeout=20000)
        expect(page.get_by_test_id("range-gripper")).to_have_attribute("data-ok", "true", timeout=20000)
        if arm == "follower":
            shot("02-calibrate-ranges")
        page.get_by_role("button", name=re.compile("^Save")).click()
        _wait(lambda a=arm: status()["robot"]["arms"][a]["calibrated"], 20, f"{arm} calibrated")
    st = wait_state("idle")
    assert st["robot"]["arms"]["follower"]["calibrated"] and st["robot"]["arms"]["leader"]["calibrated"]
    shot("03-calibrate-done")

    # ---------------------------------------------------------------- 3. cameras (the policy's own key first)
    cams = _image_features(checkpoint)
    wanted = [(name, f"{w}x{h}") for name, (w, h) in cams.items()]
    extra = "front" if "front" not in cams else "side"
    wanted.append((extra, "320x240"))
    go("/cameras")
    for i, (name, res) in enumerate(wanted):
        dev = page.get_by_test_id(f"discovered-mock://camera{i}")
        dev.get_by_role("button", name="Add").click()
        dev.get_by_label("Name").fill(name)
        dev.get_by_label("Resolution").select_option(res)
        dev.get_by_role("button", name="Test").click()
        expect(dev.get_by_test_id("probe-result")).to_be_visible(timeout=20000)
        dev.get_by_role("button", name="Add").last.click()
        _wait(lambda n=name: n in api("GET", "/robots")["robots"][0]["cameras"], 15, f"camera {name}")
    _wait(lambda: len(status()["cameras"]) == len(wanted), 20, "cameras streaming")
    for name, _ in wanted:
        tile = page.get_by_test_id(f"camera-{name}")
        expect(tile).to_be_visible()
        expect(tile).not_to_have_attribute("data-tick", "", timeout=20000)  # frames arrive
    shot("04-cameras-previews")

    # ---------------------------------------------------------------- 4. teleop
    go("/teleop")
    start_with_leader("Start teleop", "/sessions/teleop")
    wait_state("teleop")
    cell = page.get_by_test_id("joint-shoulder_pan")
    expect(cell).to_be_visible(timeout=15000)
    first = cell.inner_text()
    _wait(lambda: cell.inner_text() != first, 15, "joints to move")
    expect(page.get_by_test_id("motor-follower-elbow_flex")).to_contain_text("°C", timeout=15000)
    expect(page.get_by_test_id("motor-leader-gripper")).to_contain_text("°C", timeout=15000)
    for name, _ in wanted:
        expect(page.get_by_test_id(f"camera-{name}")).not_to_have_attribute("data-tick", "")
    shot("05-teleop", dark=True)

    # ---------------------------------------------------------------- 5. over-temperature → safe stop
    api("POST", "/mock/inject", {"port": "mock://follower", "motor": "elbow_flex", "temp_c": 67})
    banner = page.get_by_test_id("critical-banner")
    expect(banner).to_be_visible(timeout=20000)
    expect(banner).to_contain_text("elbow_flex")
    st = wait_state("estopped", timeout=20)
    assert st["reason"] == "thermal" and st["session"] is None
    assert st["robot"]["follower_torque"] is False
    expect(banner).to_contain_text("Torque is off")
    shot("06-thermal-stop")
    api("POST", "/mock/inject", {"port": "mock://follower", "motor": "elbow_flex", "temp_c": 35})
    time.sleep(1.5)  # two cool samples
    api("POST", "/mock/inject", {"port": "mock://follower", "clear_temp": True})
    page.get_by_role("button", name="I'm clear, reset").click()
    wait_state("idle")
    api("POST", "/robots/torque", {"arm": "follower", "enabled": True})

    # ---------------------------------------------------------------- 6. record 2 episodes: → ← → Esc
    go("/record")
    page.get_by_label(re.compile("^Dataset name")).fill(DATASET)
    page.get_by_label(re.compile("^Task")).fill("Pick the red cube and place it in the bowl")
    page.get_by_label("Reset time (s)").fill("30")
    start_with_leader("Start recording", "/sessions/record")
    wait_state("recording")

    def phase() -> str | None:
        s = status()["session"]
        return s["episode"]["phase"] if s else None

    def saved() -> int:
        s = status()["session"]
        return int(s["episode"]["saved"]) if s else -1

    page.locator("body").click(position={"x": 5, "y": 5})  # focus outside any field
    _wait(lambda: phase() == "episode", 20, "episode 1")
    time.sleep(1.5)
    shot("07-record-episode")
    page.keyboard.press("ArrowRight")  # keep episode 1 (saved when the reset ends, like lerobot)
    _wait(lambda: phase() == "reset", 20, "reset after episode 1")
    page.keyboard.press("ArrowRight")  # end the reset: episode 1 is written
    _wait(lambda: phase() == "episode" and saved() == 1, 30, "episode 1 saved, episode 2 running")
    time.sleep(1.0)
    page.keyboard.press("ArrowLeft")  # re-record episode 2
    _wait(lambda: phase() == "reset", 20, "episode 2 discarded")
    assert saved() == 1
    page.keyboard.press("ArrowRight")
    _wait(lambda: phase() == "episode", 20, "episode 2 again")
    time.sleep(1.5)
    page.keyboard.press("Escape")  # stop: the recorded episode 2 is kept
    wait_state("idle", timeout=60)
    done = page.get_by_test_id("record-done")
    expect(done).to_be_visible(timeout=20000)
    expect(done).to_contain_text("2 episodes saved")
    shot("08-record-done")
    # QC 0.2.9 QD-11: at 390 px the text wraps above the buttons (never a one-word column under
    # "Upload"), and the local path only shows on request
    page.set_viewport_size({"width": 390, "height": 844})
    page.wait_for_timeout(300)
    text_box = page.get_by_test_id("record-done-text").bounding_box()
    up_box = done.get_by_role("link", name="Upload").bounding_box()
    assert text_box and up_box
    assert text_box["width"] >= 200, text_box
    assert up_box["y"] >= text_box["y"] + text_box["height"] - 1, (text_box, up_box)
    expect(done.get_by_text(str(home / "datasets" / DATASET))).to_be_hidden()
    shot("08-record-done-390")
    page.set_viewport_size({"width": 1440, "height": 1000})

    # ---------------------------------------------------------------- 7. the dataset is a valid LeRobotDataset
    detail = api("GET", f"/datasets/{DATASET}")
    assert detail["finalized"], detail["finalize_reasons"]
    assert detail["episodes"] == 2 and len(detail["episode_list"]) == 2
    from lerobot.datasets.lerobot_dataset import LeRobotDataset

    ds = LeRobotDataset(DATASET, root=home / "datasets" / DATASET)
    assert ds.meta.total_episodes == 2
    assert ds.num_frames == detail["frames"] > 0
    item = ds[0]
    for name, _ in wanted:
        assert f"observation.images.{name}" in item
    assert tuple(item["observation.state"].shape) == (6,)
    go(f"/datasets/{DATASET}")
    expect(page.get_by_text("#2").first).to_be_visible()
    shot("09-dataset")

    # ---------------------------------------------------------------- 8. import the ACT checkpoint
    go("/run")
    page.get_by_label(re.compile("folder on this machine")).fill(str(checkpoint))
    page.get_by_role("button", name="Import", exact=True).click()
    entry = _wait(lambda: (m := api("GET", "/models")["models"]) and m[0], 120, "the import")
    assert entry["policy_type"] == "act"
    page.get_by_role("button", name=re.compile(re.escape(entry["name"]))).first.click()
    expect(page.get_by_test_id("compat")).to_be_visible(timeout=20000)
    page.get_by_role("button", name=re.compile("^(Load|Reload)$")).click()
    expect(page.get_by_test_id("load-result")).to_be_visible(timeout=180000)
    shot("10-model-loaded")

    # ---------------------------------------------------------------- 9. run: both cameras, joints, temps, Space
    start = page.get_by_role("button", name="Run on the robot")
    expect(start).to_be_enabled(timeout=20000)
    start.click()
    wait_state("inferring")
    _wait(lambda: phase() == "episode", 30, "the run episode")
    expect(page.get_by_test_id("camera-grid")).to_be_visible()
    for name, _ in wanted:
        tile = page.get_by_test_id(f"camera-{name}")
        expect(tile).not_to_have_attribute("data-tick", "", timeout=20000)
    for name in cams:  # the policy's camera shows the exact frames it was fed
        expect(page.get_by_test_id(f"camera-{name}")).to_contain_text("policy input", timeout=20000)
    joints = page.get_by_test_id("joint-panel")
    expect(joints.get_by_role("columnheader", name="Action")).to_be_visible(timeout=20000)
    expect(page.get_by_test_id("motor-follower-elbow_flex")).to_contain_text("°C")
    _wait(lambda: (s := status()["session"]) and s["policy"]["inferences"] > 3, 60, "inferences")
    time.sleep(1.0)
    shot("11-run-model", dark=True)
    page.locator("body").click(position={"x": 5, "y": 5})
    page.keyboard.press("Space")
    st = wait_state("estopped", timeout=10)
    assert st["reason"] == "user"
    expect(page.get_by_role("button", name="I'm clear, reset")).to_be_visible()
    expect(page.get_by_test_id("run-summary")).to_be_visible(timeout=20000)
    shot("12-run-estop")
    page.get_by_role("button", name="I'm clear, reset").click()
    wait_state("idle")

    assert not errors, errors
    ctx.close()
