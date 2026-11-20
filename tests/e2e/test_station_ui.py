"""End-to-end: the built Station UI against a real ``hibiscus-station`` process (spec §6, §9).

Drives Chromium (Playwright) through the novice flow: connect → guided calibration (follower,
leader, pose check) → cameras → teleop → over-temperature safe stop → record 2 episodes with the
keyboard → the LeRobotDataset loads → import the ACT checkpoint → run it with every camera, joints,
temperatures → Space e-stop → reset → Programs, with the 0.2.9 checks: motor health fits beside
Robot 3D at 1280 / 1440 px (QD-6), the record end card at 390 px (QD-11), an e-stop in episode 1
keeps nothing (QD-18), the critical banner goes with the reset (QD-23) and the dead-man stop during
a replay reads in words in both languages (QD-19), and every camera of a recorded episode plays in the
dataset viewer, also when the browser refuses AV1 / H.264 (F-72, AT-99). A guard fails the run on any uncaught page error,
console error or HTTP error answer the flow did not provoke (QD-18). Controls are found by their UI string keys, so
one flow runs as ``mock-en`` (thermal safe stop), ``mock-vi`` and ``sts-vi`` (Space e-stop, relax,
reset; ``sts`` = the real serial stack against two STS3215 chains on pseudo-terminals, POSIX only,
also marked ``slow``). Screenshots go to ``screenshots/e2e/`` (git-ignored;
``HIBISCUS_E2E_SHOTS`` overrides). See ``conftest.py`` for what the tests need.

    uv run pytest tests/e2e -m e2e
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path
from typing import Any

import pytest

from .e2e_support import ARMS, UI, Driver, launch_station, wait_for

pytestmark = [pytest.mark.e2e, pytest.mark.timeout(900)]

DATASET = "e2e_picknplace"
#: the slowest joint of the demo hand sweeps its whole range in about 5.6 s (0.18 Hz): a user moves
#: every joint end to end, so both arms record the same, centred ranges and the pose check agrees
FULL_SWEEP_S = 6.0


def _image_features(pdir: Path) -> dict[str, tuple[int, int]]:
    cfg = json.loads((pdir / "config.json").read_text(encoding="utf-8"))
    out = {}
    for key, ft in cfg["input_features"].items():
        if ft["type"] == "VISUAL":
            _, h, w = ft["shape"]
            out[key.removeprefix("observation.images.")] = (w, h)
    return out


def calibrate_both_arms(d: Driver) -> None:
    """The guided calibration (0.2.7+): stepper follower → leader → pose check."""
    from playwright.sync_api import expect

    page = d.page
    d.go("/calibrate")
    for arm in ARMS:
        expect(page.get_by_test_id(f"cal-step-{arm}")).to_have_attribute("aria-current", "step")
        needs = page.get_by_test_id(f"cal-needs-{arm}")
        expect(needs).to_be_visible(timeout=20000)
        expect(needs).to_contain_text(d.t("calibrate.needs_title", arm=d.t(f"arm.{arm}")))
        d.button("calibrate.start", needs).click()
        wizard = page.get_by_test_id(f"wizard-{arm}")
        expect(wizard.get_by_test_id("cal-home")).to_be_visible()
        d.button("calibrate.set_home", wizard).click()
        expect(wizard.get_by_test_id("cal-ranges")).to_be_visible()
        # the hand sweeps every joint; rows turn green once the range is big enough
        for motor in ("shoulder_pan", "wrist_roll", "gripper"):
            expect(wizard.get_by_test_id(f"range-{motor}")).to_have_attribute(
                "data-ok", "true", timeout=30000
            )
        save = d.button("calibrate.finish", wizard)
        expect(save).to_be_enabled(timeout=30000)
        time.sleep(FULL_SWEEP_S)
        if arm == "follower":
            d.shot("02-calibrate-ranges", dark=True)
        save.click()
        st = wait_for(
            lambda a=arm: (s := d.status())["state"] == "idle" and s["robot"]["arms"][a]["calibrated"] and s,
            30,
            f"{arm} calibrated",
        )
        assert st["robot"]["arms"][arm]["calibrated"]
        if arm == "follower":  # the flow moves on to the leader by itself
            expect(page.get_by_test_id("cal-now-leader")).to_be_visible()
    # step 3: hold the leader like the follower, then Check
    expect(page.get_by_test_id("cal-step-check")).to_have_attribute("aria-current", "step")
    check = page.get_by_test_id("pose-check")
    expect(check).to_be_visible()
    d.station.leader_follows()
    try:
        time.sleep(0.5)
        d.button("calibrate.check_run", check).click()
        expect(page.get_by_test_id("pose-ok")).to_be_visible(timeout=20000)
        expect(page.get_by_test_id("pose-table")).to_be_visible()
    finally:
        d.station.leader_sweeps()
    d.shot("03-calibrate-done")


def add_cameras(d: Driver, wanted: list[tuple[str, str]]) -> None:
    """Cameras page: add each discovered mock device under a name and a resolution."""
    from playwright.sync_api import expect

    page = d.page
    d.go("/cameras")
    for i, (name, res) in enumerate(wanted):
        dev = page.get_by_test_id(f"discovered-mock://camera{i}")
        d.button("cameras.add", dev).click()
        dev.get_by_label(d.t("cameras.name"), exact=True).fill(name)
        dev.get_by_label(d.t("cameras.resolution"), exact=True).select_option(res)
        d.button("cameras.probe", dev).click()
        expect(dev.get_by_test_id("probe-result")).to_be_visible(timeout=20000)
        d.button("cameras.add", dev).last.click()
        wait_for(lambda n=name: n in d.api("GET", "/robots")["robots"][0]["cameras"], 15, f"camera {name}")


def thermal_safe_stop(d: Driver) -> None:
    """Over-temperature on the follower → safe stop with torque off → cool down → reset."""
    from playwright.sync_api import expect

    page = d.page
    d.api("POST", "/mock/inject", {"port": "mock://follower", "motor": "elbow_flex", "temp_c": 67})
    banner = page.get_by_test_id("critical-banner")
    expect(banner).to_be_visible(timeout=20000)
    expect(banner).to_contain_text("elbow_flex")
    st = d.wait_state("estopped", timeout=20)
    assert st["reason"] == "thermal" and st["session"] is None
    assert st["robot"]["follower_torque"] is False
    expect(banner).to_contain_text(d.t("banner.support_arm"))
    d.shot("06-thermal-stop")
    d.api("POST", "/mock/inject", {"port": "mock://follower", "motor": "elbow_flex", "temp_c": 35})
    time.sleep(1.5)  # two cool samples
    d.api("POST", "/mock/inject", {"port": "mock://follower", "clear_temp": True})
    d.button("estop.reset").click()
    d.wait_state("idle")
    # QC 0.2.9 QD-23: the same open page drops the critical banner as soon as the reset is
    # accepted (no reload), and what it shows matches a fresh GET /status.
    expect(banner).to_have_count(0, timeout=3000)
    assert not [a for a in d.status()["alerts"] if a["level"] == "critical"], d.status()["alerts"]
    expect(page.get_by_role("alert").filter(has_text=re.compile(r"\b6[67] °C"))).to_have_count(0)
    d.no_errors("thermal stop → cool → reset")
    d.api("POST", "/robots/torque", {"arm": "follower", "enabled": True})


def motor_health_fits(d: Driver) -> None:
    """QC 0.2.9 QD-6: with Robot 3D shown (the default) the motor health tables fit at 1280 / 1440."""
    from playwright.sync_api import expect

    page = d.page
    expect(page.get_by_test_id("motor-leader-gripper")).to_be_visible(timeout=15000)
    size = page.viewport_size
    for width in (1280, 1440):
        page.set_viewport_size({"width": width, "height": 1000})
        page.wait_for_timeout(300)
        overflow = page.evaluate(
            """() => [...document.querySelectorAll('[data-testid="motor-health"] table')]
                .map((t) => [t.parentElement.scrollWidth, t.parentElement.clientWidth])
                .filter(([s, c]) => s > c + 1)"""
        )
        assert overflow == [], f"motor health scrolls sideways at {width} px: {overflow}"
    if size:
        page.set_viewport_size(size)


def record_done_at_390(d: Driver, dataset_path: Path) -> None:
    """QC 0.2.9 QD-11: at 390 px the end card's text wraps above the buttons (never a one-word column
    under "Upload"), and the local path only shows on request."""
    from playwright.sync_api import expect

    page = d.page
    done = page.get_by_test_id("record-done")
    size = page.viewport_size
    page.set_viewport_size({"width": 390, "height": 844})
    page.wait_for_timeout(300)
    card_box = done.bounding_box()
    text_box = page.get_by_test_id("record-done-text").bounding_box()
    up_box = done.get_by_role("link", name=d.ui.exact("record.upload")).bounding_box()
    assert card_box and text_box and up_box
    assert text_box["width"] >= 0.75 * card_box["width"], (card_box, text_box)  # a line of its own
    assert up_box["y"] >= text_box["y"] + text_box["height"] - 1, (text_box, up_box)
    expect(done.get_by_text(str(dataset_path))).to_be_hidden()
    d.shot("08-record-done-390")
    if size:
        page.set_viewport_size(size)


def estop_in_episode_1_keeps_nothing(d: Driver, phase: Any) -> None:
    """QC 0.2.9 QD-18: an e-stop in episode 1 keeps no episode, offers no Upload and never asks
    for the removed dataset (the guard sees any 404)."""
    from playwright.sync_api import expect

    page = d.page
    d.go("/record")
    page.get_by_label(re.compile("^" + re.escape(d.t("record.dataset")))).fill("e2e_estop_ep1")
    page.get_by_label(re.compile("^" + re.escape(d.t("record.task")))).fill("Pick the red cube")
    d.start_with_leader("record.start", "/sessions/record")
    d.wait_state("recording")
    d.focus_body()
    wait_for(lambda: phase() == "episode", 20, "episode 1 of the e-stop run")
    time.sleep(1.0)
    page.keyboard.press("Space")
    st = d.wait_state("estopped", timeout=10)
    assert st["reason"] == "user"
    none = page.get_by_test_id("record-none")
    expect(none).to_be_visible(timeout=20000)
    expect(none).to_contain_text(d.t("record.none_title"))
    expect(none.get_by_role("link", name=d.ui.exact("record.upload"))).to_have_count(0)
    page.wait_for_timeout(1500)  # a late refetch of the removed dataset would show up here
    d.shot("09b-record-estop-episode-1")
    d.no_errors("e-stop in episode 1")
    d.button("estop.reset").first.click()
    d.wait_state("idle")


def deadman_stop_in_words(d: Driver, base: str) -> None:
    """QC 0.2.9 QD-19: the page goes away mid-replay, the Station stops the robot by itself; the stop
    reads in words in Vietnamese and in English, never as the server's "heartbeat" line."""
    from playwright.sync_api import expect

    d.api("POST", "/sessions/replay", {"dataset": DATASET, "episode": 0})
    d.wait_state("replaying", timeout=20)
    d.page.close()  # no heartbeat from the UI
    st = d.wait_state("estopped", timeout=15)
    assert st["reason"] == "ui_lost", st
    d.no_errors("dead-man stop")
    for lang in ("vi", "en"):
        ui = UI(lang)
        page = d.new_page(lang)
        page.goto(f"{base}/teleop")
        banner = page.get_by_test_id("state-banner")
        expect(banner).to_contain_text(ui.t("banner.estopped", reason=ui.t("reasons.ui_lost")), timeout=15000)
        sign = ui.t("server_text.ui_lost", s=1)
        expect(banner).to_contain_text(sign)
        expect(page.get_by_test_id("lock-gate")).to_contain_text(sign)
        assert "heartbeat" not in page.locator("body").inner_text().lower()
        d.shot(f"09c-deadman-{lang}")
    d.new_page(d.ui.lang)
    d.go("/teleop")
    d.button("estop.reset").first.click()
    d.wait_state("idle")
    d.no_errors("after the dead-man stop")


def estop_relax_reset(d: Driver) -> None:
    """Space during teleop → e-stop latched → relax (torque off) → reset → idle."""
    from playwright.sync_api import expect

    page = d.page
    d.focus_body()
    page.keyboard.press("Space")
    st = d.wait_state("estopped", timeout=10)
    assert st["reason"] == "user" and st["session"] is None
    dock = page.get_by_test_id("estop-dock")
    expect(dock).to_contain_text(d.t("estop.latched", reason=d.t("reasons.user")))
    d.button("estop.relax", dock).click()
    # 0.2.9 (CR-1): Relax asks to support the arm first
    d.button("relax.confirm_ok").click()
    wait_for(lambda: d.status()["robot"]["follower_torque"] is False, 15, "follower torque off")
    d.shot("06-estop-relaxed")
    d.button("estop.reset", dock).click()
    d.wait_state("idle")
    d.api("POST", "/robots/torque", {"arm": "follower", "enabled": True})


FLOWS = [
    pytest.param("mock", "en", id="mock-en"),
    # the customer's flow (BR-1): Vietnamese, as a vi-VN browser opens it
    pytest.param("mock", "vi", id="mock-vi"),
    # the real serial stack (rustypot, lerobot SO-101 types) against emulated STS3215 chains
    pytest.param(
        "sts",
        "vi",
        id="sts-vi",
        marks=[
            pytest.mark.slow,
            pytest.mark.skipif(sys.platform == "win32", reason="the STS emulator needs pseudo-terminals"),
        ],
    ),
]


@pytest.mark.parametrize(("backend", "lang"), FLOWS)
def test_station_ui_end_to_end(
    browser: Any, tmp_path: Path, checkpoint: Path, backend: str, lang: str
) -> None:
    from playwright.sync_api import expect

    cams = _image_features(checkpoint)
    wanted = [(name, f"{w}x{h}") for name, (w, h) in cams.items()]
    extra = "front" if "front" not in cams else "side"
    wanted.append((extra, "320x240"))
    # the emulated bus has no camera discovery: the profile carries mock cameras from the start
    preset = (
        {
            n: {"type": "mock", "width": int(r.split("x")[0]), "height": int(r.split("x")[1])}
            for n, r in wanted
        }
        if backend == "sts"
        else {}
    )
    with launch_station(tmp_path, backend, cameras=preset) as station:
        d = Driver(browser, station, lang)
        page = d.page
        d.shots = d.shots / backend

        # ------------------------------------------------------------ login (one-time link → cookie)
        d.login()

        # ------------------------------------------------------------ 1. connect
        d.go("/robot")
        d.button("robot.connect").click()
        d.wait_state("idle", timeout=60)
        expect(page.get_by_text(d.t("robot.connected"), exact=True).first).to_be_visible()
        d.shot("01-robot-connected", dark=True)
        motor_health_fits(d)

        # ------------------------------------------------------------ 2. calibrate both arms
        calibrate_both_arms(d)

        # ------------------------------------------------------------ 3. cameras (the policy's own key first)
        if station.mock:
            add_cameras(d, wanted)
        else:
            d.go("/cameras")
        wait_for(lambda: len(d.status()["cameras"]) == len(wanted), 30, "cameras streaming")
        for name, _ in wanted:
            tile = page.get_by_test_id(f"camera-{name}")
            expect(tile).to_be_visible()
            expect(tile).not_to_have_attribute("data-tick", "", timeout=20000)  # frames arrive
        d.shot("04-cameras-previews")

        # ------------------------------------------------------------ 4. teleop
        d.go("/teleop")
        d.start_with_leader("teleop.start", "/sessions/teleop")
        d.wait_state("teleop")
        cell = page.get_by_test_id("joint-shoulder_pan")
        expect(cell).to_be_visible(timeout=15000)
        first = cell.inner_text()
        wait_for(lambda: cell.inner_text() != first, 15, "joints to move")
        expect(page.get_by_test_id("motor-follower-elbow_flex")).to_contain_text("°C", timeout=15000)
        expect(page.get_by_test_id("motor-leader-gripper")).to_contain_text("°C", timeout=15000)
        for name, _ in wanted:
            expect(page.get_by_test_id(f"camera-{name}")).not_to_have_attribute("data-tick", "")
        d.shot("05-teleop", dark=True)

        # ------------------------------------------------------------ 5. stop: thermal (mock-en) or Space + relax
        if station.mock and lang == "en":
            thermal_safe_stop(d)
        else:
            estop_relax_reset(d)

        # ------------------------------------------------------------ 6. record 2 episodes: → ← → Esc
        d.go("/record")
        page.get_by_label(re.compile("^" + re.escape(d.t("record.dataset")))).fill(DATASET)
        page.get_by_label(re.compile("^" + re.escape(d.t("record.task")))).fill(
            "Pick the red cube and place it in the bowl"
        )
        page.get_by_label(d.t("record.reset_time"), exact=True).fill("30")
        d.start_with_leader("record.start", "/sessions/record")
        d.wait_state("recording")

        def phase() -> str | None:
            s = d.status()["session"]
            return s["episode"]["phase"] if s else None

        def saved() -> int:
            s = d.status()["session"]
            return int(s["episode"]["saved"]) if s else -1

        d.focus_body()
        wait_for(lambda: phase() == "episode", 20, "episode 1")
        time.sleep(1.5)
        d.shot("07-record-episode")
        page.keyboard.press("ArrowRight")  # keep episode 1 (saved when the reset ends, like lerobot)
        wait_for(lambda: phase() == "reset", 20, "reset after episode 1")
        page.keyboard.press("ArrowRight")  # end the reset: episode 1 is written
        wait_for(lambda: phase() == "episode" and saved() == 1, 30, "episode 1 saved, episode 2 running")
        time.sleep(1.0)
        page.keyboard.press("ArrowLeft")  # re-record episode 2
        wait_for(lambda: phase() == "reset", 20, "episode 2 discarded")
        assert saved() == 1
        page.keyboard.press("ArrowRight")
        wait_for(lambda: phase() == "episode", 20, "episode 2 again")
        time.sleep(1.5)
        page.keyboard.press("Escape")  # stop: the recorded episode 2 is kept
        d.wait_state("idle", timeout=60)
        done = page.get_by_test_id("record-done")
        expect(done).to_be_visible(timeout=20000)
        expect(done).to_contain_text(d.t("record.done_other", count=2, name=DATASET))  # 0.2.9: real plurals
        d.shot("08-record-done")
        record_done_at_390(d, station.home / "datasets" / DATASET)

        # ------------------------------------------------------------ 7. the dataset is a valid LeRobotDataset
        detail = d.api("GET", f"/datasets/{DATASET}")
        assert detail["finalized"], detail["finalize_reasons"]
        assert detail["episodes"] == 2 and len(detail["episode_list"]) == 2
        from lerobot.datasets.lerobot_dataset import LeRobotDataset

        ds = LeRobotDataset(DATASET, root=station.home / "datasets" / DATASET)
        assert ds.meta.total_episodes == 2
        assert ds.num_frames == detail["frames"] > 0
        item = ds[0]
        for name, _ in wanted:
            assert f"observation.images.{name}" in item
        assert tuple(item["observation.state"].shape) == (6,)
        d.go(f"/datasets/{DATASET}")
        expect(page.get_by_text("#2").first).to_be_visible()
        d.shot("09-dataset")
        d.no_errors("golden path up to the dataset")

        # ------------------------------------------------------------ 7b. e-stop in episode 1: nothing kept
        estop_in_episode_1_keeps_nothing(d, phase)

        # ------------------------------------------------------------ 7c. dead-man stop during a replay
        deadman_stop_in_words(d, station.base)
        page = d.page

        # ------------------------------------------------------------ 7d. F-72 / AT-99: every camera's video plays here
        # (CI: Chromium and Firefox on Linux, Microsoft Edge on windows-latest). The browser picks the
        # first format it says it plays (AV1 as recorded, else H.264, else VP9, ADR-14).
        d.go(f"/datasets/{DATASET}")
        expect(page.get_by_text("#2").first).to_be_visible()
        page.get_by_role("button", name="#1", exact=True).click()
        for name, _ in wanted:
            expect(page.get_by_test_id(f"episode-video-{name}")).to_have_attribute(
                "data-state", "ready", timeout=120000
            )
        page.get_by_test_id("episode-play").click()
        played = (
            "Math.min(...[...document.querySelectorAll('[data-testid^=\"episode-video-\"] video')]"
            ".map((v) => v.currentTime))"
        )
        wait_for(lambda: float(page.evaluate(played)) > 0.3, 30, "every camera to play")
        probe = {
            m: page.evaluate(f"document.createElement('video').canPlayType({json.dumps(t)})")
            for m, t in {
                "av1": 'video/mp4; codecs="av01.0.05M.08"',
                "h264": 'video/mp4; codecs="avc1.42E01E"',
                "vp9": 'video/webm; codecs="vp9"',
            }.items()
        }
        formats = {
            n: page.get_by_test_id(f"episode-video-{n}").get_attribute("data-format") for n, _ in wanted
        }
        d.shots.mkdir(parents=True, exist_ok=True)
        (d.shots / f"f72-video-{d.ui.lang}.json").write_text(
            json.dumps(
                {
                    "browser": browser.browser_type.name,
                    "version": browser.version,
                    "canPlayType": probe,
                    "formats": formats,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        if probe["av1"] == "":  # Edge without the AV1 Video Extension: a converted cut plays
            assert all(f in ("h264", "vp9") for f in formats.values()), formats
        d.shot("09b-episode-video")

        # The converted cuts in this very browser: what a stock Windows 11 Edge (no AV1 Video Extension)
        # and a Windows "N" edition (no Media Foundation: no H.264 either) are offered (REG-27).
        fallbacks: dict[str, dict[str, str | None]] = {}
        for case, refuse, episode in (("no-av1", ["av01"], "#2"), ("no-av1-no-h264", ["av01", "avc1"], "#1")):
            page.evaluate(
                """(refuse) => {
                  const proto = HTMLMediaElement.prototype;
                  proto.__canPlayType = proto.__canPlayType || proto.canPlayType;
                  proto.canPlayType = function (t) {
                    return refuse.some((r) => t.includes(r)) ? "" : proto.__canPlayType.call(this, t);
                  };
                }""",
                refuse,
            )
            page.get_by_role("button", name=episode, exact=True).click()
            for name, _ in wanted:
                expect(page.get_by_test_id(f"episode-video-{name}")).to_have_attribute(
                    "data-state", "ready", timeout=180000
                )
            page.get_by_test_id("episode-play").click()
            try:
                wait_for(lambda: float(page.evaluate(played)) > 0.3, 30, f"every camera to play ({case})")
            except AssertionError:
                state = "[...document.querySelectorAll('video')].map((v) => [v.src, v.currentTime, v.paused, v.readyState, v.error && v.error.code, v.duration])"
                raise AssertionError(f"{case}: {page.evaluate(state)}") from None
            fallbacks[case] = {
                n: page.get_by_test_id(f"episode-video-{n}").get_attribute("data-format") for n, _ in wanted
            }
            assert all(f in ("h264", "vp9") for f in fallbacks[case].values()), (case, fallbacks)
            d.shot(f"09c-episode-video-{case}")
        assert all(f == "vp9" for f in fallbacks["no-av1-no-h264"].values()), fallbacks
        (d.shots / f"f72-video-{d.ui.lang}.json").write_text(
            json.dumps(
                {
                    "browser": browser.browser_type.name,
                    "version": browser.version,
                    "canPlayType": probe,
                    "formats": formats,
                    "fallbacks": fallbacks,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        d.no_errors("episode video viewer (F-72)")

        # ------------------------------------------------------------ 8. import the ACT checkpoint
        d.go("/run")
        page.get_by_label(re.compile(re.escape(d.t("run.import_path").lstrip("…")))).fill(str(checkpoint))
        d.button("run.import").click()
        entry = wait_for(lambda: (m := d.api("GET", "/models")["models"]) and m[0], 120, "the import")
        assert entry["policy_type"] == "act"
        page.get_by_role("button", name=re.compile(re.escape(entry["name"]))).first.click()
        expect(page.get_by_test_id("compat")).to_be_visible(timeout=20000)
        page.get_by_role("button", name=re.compile(f"^({d.t('run.load')}|{d.t('run.reload')})$")).click()
        expect(page.get_by_test_id("load-result")).to_be_visible(timeout=180000)
        d.shot("10-model-loaded")

        # ------------------------------------------------------------ 9. run: cameras, joints, temps, Space
        start = d.button("run.start")
        expect(start).to_be_enabled(timeout=20000)
        start.click()
        d.wait_state("inferring")
        wait_for(lambda: phase() == "episode", 30, "the run episode")
        expect(page.get_by_test_id("camera-grid")).to_be_visible()
        for name, _ in wanted:
            tile = page.get_by_test_id(f"camera-{name}")
            expect(tile).not_to_have_attribute("data-tick", "", timeout=20000)
        for name in cams:  # the policy's camera shows the exact frames it was fed
            expect(page.get_by_test_id(f"camera-{name}")).to_contain_text(
                d.t("camera.policy_input"), timeout=20000
            )
        joints = page.get_by_test_id("joint-panel")
        expect(joints.get_by_role("columnheader", name=d.t("joints.action"))).to_be_visible(timeout=20000)
        expect(page.get_by_test_id("motor-follower-elbow_flex")).to_contain_text("°C")
        wait_for(lambda: (s := d.status()["session"]) and s["policy"]["inferences"] > 3, 60, "inferences")
        time.sleep(1.0)
        d.shot("11-run-model", dark=True)
        d.focus_body()
        page.keyboard.press("Space")
        st = d.wait_state("estopped", timeout=10)
        assert st["reason"] == "user"
        expect(d.button("estop.reset")).to_be_visible()
        expect(page.get_by_test_id("run-summary")).to_be_visible(timeout=20000)
        d.shot("12-run-estop")
        d.button("estop.reset").click()
        d.wait_state("idle")

        # ------------------------------------------------------------ 10. programs (last novice step)
        d.go("/programs")
        expect(page.get_by_role("heading", level=1)).to_contain_text(d.t("nav.programs"))

        d.no_errors("end of the run")
        d.close()
