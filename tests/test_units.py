"""Unit tests of pure logic (spec §9.2 "Unit" layer)."""

from __future__ import annotations

import random
import time
import zipfile
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from conftest import is_private

from hibiscus_station.errors import StationError
from hibiscus_station.hw import feetech
from hibiscus_station.hw.cameras import (
    CameraHub,
    FrameSet,
    PreviewEncoder,
    VideoClient,
    encode_preview,
    pack_frame,
    unpack_frame,
)
from hibiscus_station.hw.locks import DeviceBusyError, DeviceLock
from hibiscus_station.hw.safety import EStop, SafetyFilter, Watchdog
from hibiscus_station.hw.telemetry import TelemetryRead, TelemetryScheduler, ThermalGuard
from hibiscus_station.logs import redact
from hibiscus_station.mock import decode_counter, encode_counter, get_world
from hibiscus_station.models import importer
from hibiscus_station.models.registry import ModelRegistry
from hibiscus_station.profiles import ProfileStore
from hibiscus_station.settings import Settings, TelemetrySettings, Thresholds, threshold_problems

MOTORS = ["shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll", "gripper"]


# ----------------------------------------------------------------------------------- feetech
def test_feetech_units_and_sign_bit() -> None:
    assert feetech.decode_voltage(74) == 7.4
    assert feetech.decode_current(100) == pytest.approx(0.65)
    assert feetech.decode_temperature(52) == 52.0
    assert feetech.decode_load(315) == 31.5
    assert feetech.decode_load(315 | 1 << 10) == -31.5
    assert feetech.decode_load(-315) == -31.5  # rustypot may already sign it
    for pct in (-100.0, -12.3, 0.0, 55.5, 100.0):
        assert feetech.decode_load(feetech.encode_load(pct)) == pytest.approx(pct, abs=0.05)


def test_feetech_status_bits() -> None:
    assert feetech.decode_status(0) == []
    assert feetech.decode_status(0b100100) == ["overheat", "overload"]
    assert feetech.decode_status(0b1011) == ["voltage", "angle_sensor", "overcurrent"]
    assert feetech.encode_status(["overheat"]) == 4


def test_feetech_registers_exist_in_rustypot() -> None:
    import rustypot

    _, d = rustypot.find_model("sts3215")
    addr = {g.register: d.register(g.register.lower()).addr for g in feetech.GROUPS}
    assert addr == {
        "Present_Temperature": 63,
        "Status": 65,
        "Present_Voltage": 62,
        "Present_Current": 69,
        "Present_Load": 60,
    }
    assert d.register("present_load").sign_bit == feetech.LOAD_SIGN_BIT
    assert d.register("max_temperature_limit").addr == 13
    assert d.status_alarms_only


# ----------------------------------------------------------------------------------- thresholds
def test_threshold_rules() -> None:
    assert threshold_problems(Thresholds(), 70) == []
    assert threshold_problems(Thresholds(), 66)  # critical 65 > 66 - 3
    with pytest.raises(ValueError):
        Thresholds(temp_hot_c=63)
    with pytest.raises(ValueError):
        Thresholds(temp_warn_c=56)


def _read(group: str, values: dict[str, Any], t: float = 0.0, arm: str = "follower") -> TelemetryRead:
    return TelemetryRead(arm, group, t, True, values)


def test_guard_levels_hysteresis_and_consecutive_critical() -> None:
    from hibiscus_station.hw.telemetry import ArmLimits

    g = ThermalGuard(Thresholds())
    lim = ArmLimits()
    seq = [
        (45, "ok"),
        (51, "warn"),
        (49, "warn"),
        (47, "warn"),
        (46, "ok"),
        (61, "hot"),
        (66, "hot"),
        (66, "critical"),
        (63, "critical"),
        (61, "hot"),
        (58, "hot"),
        (56, "warn"),
    ]
    for temp, want in seq:
        g.update(_read("temp_c", {"elbow_flex": float(temp)}), lim)
        assert g.temp_level[("follower", "elbow_flex")] == want, (temp, want)
    crit = g.take_critical()
    assert len(crit) == 1 and crit[0].reason == "thermal" and not crit[0].immediate_torque_off


def test_guard_status_and_voltage_critical() -> None:
    from hibiscus_station.hw.telemetry import ArmLimits

    g = ThermalGuard(Thresholds())
    lim = ArmLimits(min_voltage_v=4.5, nominal_voltage_v=7.4)
    # overload on a joint: critical once it is seen on two consecutive reads (one byte can be a glitch)
    g.update(_read("status", {"elbow_flex": ["overload"]}), lim)
    assert not g.take_critical()
    assert g.status_level[("follower", "elbow_flex")] == "warn"
    g.update(_read("status", {"elbow_flex": ["overload"]}), lim)
    ev = g.take_critical()
    assert ev and ev[0].reason == "thermal" and ev[0].kind == "status"
    # overheat: the servo already cut its torque, no confirmation needed
    g.update(_read("status", {"gripper": ["overheat"]}), lim)
    g.update(_read("status", {"gripper": []}), lim)
    g.update(_read("status", {"gripper": ["overheat"]}), lim)
    assert g.take_critical()[-1].immediate_torque_off
    alerts = g.update(_read("voltage_v", {"gripper": 6.0}), lim)
    assert alerts and alerts[0].level == "warn"  # < 85 % of nominal
    g.update(_read("voltage_v", {"gripper": 4.2}), lim)
    assert not g.take_critical()  # one low sample: warn only
    g.update(_read("voltage_v", {"gripper": 4.2}), lim)
    assert g.take_critical()[0].reason == "electrical"


def test_gripper_overload_is_a_grasp_not_a_fault() -> None:
    """lerobot gives the SO-101 gripper Overload_Torque 25 %: squeezing an object sets the overload
    bit by design. Station must not e-stop a teleop / record session for it."""
    from hibiscus_station.hw.telemetry import ArmLimits

    g = ThermalGuard(Thresholds())
    lim = ArmLimits(min_voltage_v=4.0, nominal_voltage_v=5.0)
    for _ in range(5):
        g.update(_read("status", {"gripper": ["overload"]}), lim)
    assert not g.take_critical()
    assert g.status_level[("follower", "gripper")] == "warn"
    assert not g.hot_motors()


def test_guard_load_stall_and_current() -> None:
    from hibiscus_station.hw.telemetry import ArmLimits

    g = ThermalGuard(Thresholds())
    lim = ArmLimits(protection_current_a={"gripper": 1.625})
    assert not g.update(_read("load_pct", {"gripper": 95.0}, t=0.0), lim)
    alerts = g.update(_read("load_pct", {"gripper": -96.0}, t=2.5), lim)
    assert alerts and alerts[0].kind == "load"
    alerts = g.update(_read("current_a", {"gripper": 1.5}), lim)
    assert alerts and alerts[0].kind == "current"


# ----------------------------------------------------------------------------------- scheduler
class FakeBus:
    def __init__(self, clock: list[float], fail: set[str] | None = None) -> None:
        self.motors = {m: None for m in MOTORS}
        self.calls: list[tuple[float, str]] = []
        self.clock = clock
        self.fail = fail or set()

    def sync_read(self, reg: str, normalize: bool = True, num_retry: int = 0) -> dict[str, int]:
        self.calls.append((self.clock[0], reg))
        if reg in self.fail:
            raise ConnectionError("timeout")
        return dict.fromkeys(self.motors, 40 if reg == "Present_Temperature" else 0)


def _sched(clock: list[float]) -> tuple[TelemetryScheduler, FakeBus, FakeBus]:
    s = TelemetryScheduler(TelemetrySettings(), clock=lambda: clock[0])
    f, lead = FakeBus(clock), FakeBus(clock)
    s.add_arm("follower", f)
    s.add_arm("leader", lead)
    return s, f, lead


def test_scheduler_rates_and_one_read_per_tick() -> None:
    clock = [100.0]
    s, f, lead = _sched(clock)
    reads = 0
    for _ in range(30 * 10):  # 10 s at 30 fps with plenty of slack
        clock[0] += 1 / 30
        before = len(f.calls) + len(lead.calls)
        if s.maybe_read(slack_s=0.02) is not None:
            reads += 1
        assert len(f.calls) + len(lead.calls) - before <= 1
    assert 135 <= reads <= 145, reads  # 14 reads/s
    temps = [c for c in f.calls if c[1] == "Present_Temperature"]
    volts = [c for c in f.calls if c[1] == "Present_Voltage"]
    assert 19 <= len(temps) <= 21 and 9 <= len(volts) <= 11


def test_scheduler_skips_without_slack_but_forces_old_temperature() -> None:
    clock = [100.0]
    s, f, _ = _sched(clock)
    for _ in range(30):
        clock[0] += 1 / 30
        assert s.maybe_read(slack_s=0.001) is None or s.forced > 0
    # temperature never read yet: older than max_age -> forced even without slack
    assert s.forced >= 1 and any(c[1] == "Present_Temperature" for c in f.calls)
    forced_before = s.forced
    for _ in range(int(30 * 0.8)):
        clock[0] += 1 / 30
        s.maybe_read(slack_s=0.0)
    assert s.forced == forced_before  # fresh enough: nothing more forced
    for _ in range(30 * 3):
        clock[0] += 1 / 30
        s.maybe_read(slack_s=0.0)
    assert s.forced > forced_before  # anti-starvation kicked in again


def test_scheduler_failure_marks_stale_and_degrades_once() -> None:
    clock = [0.0]
    s = TelemetryScheduler(TelemetrySettings(), clock=lambda: clock[0])
    s.add_arm("follower", FakeBus(clock, fail={"Present_Current"}))
    degraded = 0
    for _ in range(60 * 5):
        clock[0] += 1 / 60
        r = s.maybe_read(0.02)
        if r is not None and r.degraded:
            degraded += 1
    assert degraded == 1
    assert s.arms["follower"].stale_groups() == ["current_a"]


# ----------------------------------------------------------------------------------- safety
def test_safety_filter_matches_lerobot_ensure_safe_goal_position() -> None:
    from lerobot.robots.utils import ensure_safe_goal_position

    rng = random.Random(1)
    for _ in range(200):
        cap = rng.uniform(0.5, 10)
        obs = {f"{m}.pos": rng.uniform(-90, 90) for m in MOTORS}
        goal = {k: v + rng.uniform(-30, 30) for k, v in obs.items()}
        mine, _ = SafetyFilter(cap).apply(goal, obs)
        ref = ensure_safe_goal_position({k.removesuffix(".pos"): (goal[k], obs[k]) for k in goal}, cap)
        for k, v in ref.items():
            assert mine[f"{k}.pos"] == pytest.approx(v)


def test_safety_filter_per_joint_and_range() -> None:
    f = SafetyFilter({"gripper": 1.0, "elbow_flex": 2.0}, ranges={"elbow_flex.pos": (-10.0, 10.0)})
    safe, clipped = f.apply(
        {"gripper.pos": 50.0, "elbow_flex.pos": 15.0, "wrist_roll.pos": 3.0},
        {"gripper.pos": 40.0, "elbow_flex.pos": 9.5, "wrist_roll.pos": 0.0},
    )
    assert safe == {"gripper.pos": 41.0, "elbow_flex.pos": 10.0, "wrist_roll.pos": 3.0}
    assert set(clipped) == {"gripper", "elbow_flex"}
    assert isinstance(SafetyFilter(5).max_rel, float)  # lerobot rejects an int


def test_estop_double_press_and_watchdog() -> None:
    t = [0.0]
    e = EStop(2.0, clock=lambda: t[0])
    assert not e.press().relax and e.is_set and not e.relax_event.is_set()
    t[0] = 1.5
    assert e.press().relax and e.relax_event.is_set()
    e.clear()
    e.press()
    t[0] = 5.0
    assert not e.press().relax  # too late for a double press
    w = Watchdog(1.0, clock=lambda: t[0])
    t[0] = 5.9
    assert not w.expired()
    t[0] = 6.1
    assert w.expired()
    w.beat()
    assert not w.expired()


# ----------------------------------------------------------------------------------- profiles, settings
def test_robots_yaml_round_trip(tmp_path: Path) -> None:
    from conftest import mock_profile

    store = ProfileStore(tmp_path / "robots.yaml")
    p = mock_profile(cameras=2)
    p.follower.rest_pose = {"shoulder_pan.pos": 0.0}
    store.put(p)
    again = ProfileStore(tmp_path / "robots.yaml")
    assert again.get("desk") == p and again.active == "desk"
    assert is_private(tmp_path / "robots.yaml")
    with pytest.raises(ValueError):
        type(p).model_validate({**p.model_dump(), "id": "Bad Id"})
    assert again.delete("desk") and again.active is None


def test_settings_round_trip(tmp_path: Path) -> None:
    s = Settings()
    s.thresholds.temp_warn_c = 45
    s.save(tmp_path / "s.yaml")
    assert Settings.load(tmp_path / "s.yaml").thresholds.temp_warn_c == 45


# ----------------------------------------------------------------------------------- import guards
def _zip(tmp_path: Path, entries: dict[str, bytes], name: str = "m.zip", symlink: str | None = None) -> Path:
    z = tmp_path / name
    with zipfile.ZipFile(z, "w") as zf:
        for n, b in entries.items():
            zf.writestr(n, b)
        if symlink:
            info = zipfile.ZipInfo(symlink)
            info.external_attr = (0o120777) << 16
            zf.writestr(info, "/etc/passwd")
    return z


def test_zip_traversal_symlink_and_unsafe_weights(tmp_path: Path) -> None:
    reg = ModelRegistry(tmp_path / "models")
    for bad in ("../evil", "/abs/path", "a/../../b", "C:/x"):
        with pytest.raises(StationError):
            importer.import_zip(reg, _zip(tmp_path, {bad: b"x"}), tmp_path / "staging")
    with pytest.raises(StationError):
        importer.import_zip(
            reg, _zip(tmp_path, {"m/config.json": b"{}"}, symlink="m/link"), tmp_path / "staging"
        )
    with pytest.raises(StationError) as ei:
        importer.import_zip(
            reg,
            _zip(
                tmp_path,
                {
                    "m/config.json": b'{"type": "act"}',
                    "m/policy_preprocessor.json": b"{}",
                    "m/pytorch_model.bin": b"pickle",
                },
            ),
            tmp_path / "staging",
        )
    assert ei.value.errors and ei.value.errors[0]["code"] == "unsafe_weights"
    assert not reg.list()


def test_zip_bomb_guard(tmp_path: Path) -> None:
    z = tmp_path / "bomb.zip"
    with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("m/zeros", b"\0" * (50 * 1024 * 1024))
    with pytest.raises(StationError, match="zip bomb"):
        importer.import_zip(ModelRegistry(tmp_path / "models"), z, tmp_path / "staging")


def test_bundle_manifest_is_verified(tmp_path: Path) -> None:
    from hibiscus_station.mock.policy import make_bundle, zip_dir

    b = make_bundle(tmp_path / "b", "demo_act-r1-step5", {"wrist": (96, 128)})
    reg = ModelRegistry(tmp_path / "models")
    entry = importer.import_zip(reg, zip_dir(b, tmp_path / "ok.zip"), tmp_path / "staging")
    assert entry.source == "bundle" and entry.verified and entry.policy_type == "act"
    assert entry.input_features["observation.images.wrist"].shape == [3, 96, 128]
    assert entry.fps == 30 and entry.task == "Pick the red cube"
    (b / "pretrained_model" / "config.json").write_text("{}")  # tamper
    with pytest.raises(StationError) as ei:
        importer.import_zip(reg, zip_dir(b, tmp_path / "bad.zip"), tmp_path / "staging")
    assert ei.value.errors and ei.value.errors[0]["code"] == "manifest"


# ----------------------------------------------------------------------------------- cameras / preview
def test_frame_wire_format_and_preview_resize() -> None:
    frame = np.zeros((480, 640, 3), np.uint8)
    encode_counter(frame, 1834)
    jpeg, w, h = encode_preview(frame, 320, 70)
    assert (w, h) == (320, 240)
    msg = pack_frame({"cam": "wrist", "tick": 1834}, jpeg)
    assert msg[:4] == b"HSF1"
    header, body = unpack_frame(msg)
    assert header == {"cam": "wrist", "tick": 1834} and body == jpeg
    import cv2

    img = cv2.cvtColor(cv2.imdecode(np.frombuffer(body, np.uint8), cv2.IMREAD_COLOR), cv2.COLOR_BGR2RGB)
    assert decode_counter(img) == 1834


def test_video_latest_frame_wins(tmp_path: Path) -> None:
    hub = CameraHub(tmp_path)
    hub.loop_active = True
    enc = PreviewEncoder(hub)
    c = VideoClient()
    c.subscribe(["wrist"], 160, 30)
    enc.add(c)
    for tick in range(5):
        f = np.zeros((96, 128, 3), np.uint8)
        encode_counter(f, tick)
        hub.publish(FrameSet(tick, time.monotonic(), {"wrist": f}))
        enc.step(now=time.monotonic() + tick)  # nobody flushes the client in between
    got, _ = c.take()
    header, _ = unpack_frame(got["wrist"])
    assert header["tick"] == 4 and c.replaced == 4


def test_mock_camera_counter_and_stall() -> None:
    from hibiscus_station.mock.camera import MockCamera, MockCameraConfig

    cam = MockCamera(MockCameraConfig(name="t", fps=60, width=128, height=96))
    cam.connect()
    try:
        a = decode_counter(cam.read_latest())
        time.sleep(0.1)
        b = decode_counter(cam.read_latest())
        assert b > a
        cam.stall()
        time.sleep(0.15)
        with pytest.raises(TimeoutError):
            cam.read_latest(max_age_ms=100)
    finally:
        cam.disconnect()


# ----------------------------------------------------------------------------------- mocks, misc
def test_mock_bus_physics_heats_under_stall(tmp_path: Path) -> None:
    from hibiscus_station.mock.robots import make_mock_follower

    f = make_mock_follower("mock://heat", "h", tmp_path)
    f.connect(calibrate=False)
    world = get_world("mock://heat")
    world.k1 = 0.5  # fast heating for the test
    world.inject("gripper", blocked=True)
    bus = f.bus
    bus.sync_write("Goal_Position", {"gripper": 3000}, normalize=False)
    t0 = bus.sync_read("Present_Temperature", normalize=False)["gripper"]
    time.sleep(0.5)
    t1 = bus.sync_read("Present_Temperature", normalize=False)["gripper"]
    load = bus.sync_read("Present_Load", normalize=False)["gripper"]
    assert t1 > t0 and feetech.decode_load(load) == 100.0
    world.inject("gripper", temp_c=71)
    assert feetech.decode_status(bus.sync_read("Status", normalize=False)["gripper"]) == ["overheat"]
    assert not world.torque_on("gripper")  # the servo's own protection cut torque
    f.disconnect()


def test_device_lock_is_exclusive(tmp_path: Path) -> None:
    a = DeviceLock(tmp_path, "/dev/ttyACM0")
    a.acquire()
    with pytest.raises(DeviceBusyError) as ei:
        DeviceLock(tmp_path, "/dev/ttyACM0").acquire()
    import os

    assert ei.value.holder == os.getpid()
    a.release()
    DeviceLock(tmp_path, "/dev/ttyACM0").acquire()


def test_logs_redact_tokens() -> None:
    pat = "hbp_AbCd1234_" + "x" * 43
    out = redact(f"token {pat} url http://127.0.0.1:18210/auth?t={'k' * 43}")
    assert pat not in out and "hbp_AbCd…" in out and "k" * 43 not in out


def test_cli_refuses_remote_host(monkeypatch: pytest.MonkeyPatch) -> None:
    """A non-loopback --host without the LAN-mode token and allowed hosts is refused (spec §8.1)."""
    from typer.testing import CliRunner

    from hibiscus_station.cli import app

    monkeypatch.delenv("HIBISCUS_STATION_TOKEN", raising=False)
    monkeypatch.delenv("HIBISCUS_STATION_ALLOWED_HOSTS", raising=False)
    r = CliRunner().invoke(app, ["--host", "0.0.0.0"])
    assert r.exit_code == 2 and "127.0.0.1 or ::1 only, unless LAN mode" in r.output


def test_session_retention(tmp_path: Path) -> None:
    import os

    from hibiscus_station.data.sessions import prune

    for i, age in enumerate([40, 1, 0]):
        d = tmp_path / f"s{i}"
        d.mkdir()
        (d / "session.json").write_text("{}")
        old = time.time() - age * 86400
        os.utime(d, (old, old))
    assert prune(tmp_path, 30, 10**9) == ["s0"]


def test_mock_leader_hand_can_mirror_the_follower() -> None:
    from hibiscus_station.mock import MockArmWorld

    follower = MockArmWorld("mock://f-mirror")
    leader = MockArmWorld("mock://l-mirror", auto_sweep=True)
    follower.place_all(1500.0)
    leader.follow(follower)
    leader.step()
    assert {round(s.actual) for s in leader.servos.values()} == {1500}
    follower.place_all(2600.0)
    leader.step()
    assert {round(s.actual) for s in leader.servos.values()} == {2600}
    leader.follow(None)  # the sweep is back
    time.sleep(0.05)
    leader.step()
    assert {round(s.actual) for s in leader.servos.values()} != {2600}
