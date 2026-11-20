"""Shared fixtures: an isolated Station in mock mode, an authenticated API client, helpers.

Remote tests use ``FakeHibiscus`` (``tests/fake_server.py``, vendored from the Hibiscus CLI at v0.1.1)
which checks every request against the server contract snapshot in ``tests/contract/``.
"""

from __future__ import annotations

import json
import math
import stat
import sys
import threading
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from keyring.backend import KeyringBackend as _KeyringBackend

from hibiscus_station.mock import get_world, reset_worlds
from hibiscus_station.profiles import CameraProfile, FollowerProfile, LeaderProfile, RobotProfile
from hibiscus_station.station import Station

PORT = 18210

if sys.platform == "darwin":
    # A native trap (EXC_BREAKPOINT, e.g. libdispatch, ADR-15) kills the run with exit 133 and no
    # Python trace: pytest's faulthandler does not watch SIGTRAP, and it captures fd 2 during each
    # test, so the stacks go to a file of their own (HIBISCUS_TRAP_LOG), then the signal kills the run.
    import faulthandler
    import os
    import signal

    _trap_log = open(  # open for the whole session; written only on a crash
        os.environ.get("HIBISCUS_TRAP_LOG", os.devnull), "w", encoding="utf-8"
    )
    faulthandler.register(signal.SIGTRAP, file=_trap_log, all_threads=True, chain=True)


def deep_json(obj: Any) -> str:
    """``json.dumps`` without recursion, for documents nested deeper than the C encoder allows."""
    out: list[str] = []
    stack: list[Any] = [obj]
    raw = object()
    while stack:
        item = stack.pop()
        if isinstance(item, tuple) and item and item[0] is raw:
            out.append(item[1])
        elif isinstance(item, dict):
            parts: list[Any] = [(raw, "{")]
            for i, (k, v) in enumerate(item.items()):
                parts += [(raw, ("," if i else "") + json.dumps(k) + ":"), v]
            parts.append((raw, "}"))
            stack.extend(reversed(parts))
        elif isinstance(item, list):
            parts = [(raw, "[")]
            for i, v in enumerate(item):
                parts += ([(raw, ",")] if i else []) + [v]
            parts.append((raw, "]"))
            stack.extend(reversed(parts))
        else:
            out.append(json.dumps(item))
    return "".join(out)


def is_private(path: Path, mode: int = 0o600) -> bool:
    """POSIX: ``path`` has exactly ``mode``. Windows has no POSIX modes (NTFS ACLs: the user's
    profile directory is private already), so it is always True there."""
    return sys.platform == "win32" or stat.S_IMODE(path.stat().st_mode) == mode


BASE = f"http://127.0.0.1:{PORT}"


@pytest.fixture(autouse=True)
def isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    monkeypatch.setenv("HIBISCUS_CONFIG_DIR", str(tmp_path / "cli-config"))
    monkeypatch.setenv("HIBISCUS_STATE_DIR", str(tmp_path / "cli-state"))
    monkeypatch.setenv("HIBISCUS_KEYRING", "0")
    monkeypatch.setenv("HF_LEROBOT_CALIBRATION", str(tmp_path / "calibration"))
    monkeypatch.setenv("HIBISCUS_STATION_HOME", str(tmp_path / "station-home"))
    for var in ("HIBISCUS_TOKEN", "HIBISCUS_SERVER", "HIBISCUS_WORKSPACE_ID"):
        monkeypatch.delenv(var, raising=False)
    if sys.platform == "win32":
        # Windows stores the PAT in the Credential Manager (keyring). The CLI's file fallback checks
        # POSIX modes and refuses any file on Windows, so the tests use an in-memory keyring.
        import keyring

        monkeypatch.setenv("HIBISCUS_KEYRING", "1")
        previous = keyring.get_keyring()
        keyring.set_keyring(_MemoryKeyring())
    reset_worlds()
    yield tmp_path
    reset_worlds()
    if sys.platform == "win32":
        keyring.set_keyring(previous)


class _MemoryKeyring(_KeyringBackend):  # type: ignore[misc,valid-type]
    priority = 1  # type: ignore[assignment]

    def __init__(self) -> None:
        super().__init__()
        self.store: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self.store.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self.store[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        from keyring.errors import PasswordDeleteError

        if self.store.pop((service, username), None) is None:
            raise PasswordDeleteError(username)


def mock_profile(
    cameras: int = 1, *, leader: bool = True, size: tuple[int, int] = (128, 96), fps: int = 30
) -> RobotProfile:
    names = ["wrist", "front", "side"][:cameras]
    return RobotProfile(
        id="desk",
        name="Desk mock",
        follower=FollowerProfile(
            type="hibiscus_mock_follower", port="mock://follower", calibration_id="desk_follower"
        ),
        leader=LeaderProfile(type="hibiscus_mock_leader", port="mock://leader", calibration_id="desk_leader")
        if leader
        else None,
        cameras={n: CameraProfile(type="mock", width=size[0], height=size[1], fps=fps) for n in names},
    )


def fast_hand(amplitude: float = 220.0, hz: float = 2.0) -> Callable[[str, float], float]:
    idx = {
        "shoulder_pan": 1,
        "shoulder_lift": 2,
        "elbow_flex": 3,
        "wrist_flex": 4,
        "wrist_roll": 5,
        "gripper": 6,
    }

    def hand(motor: str, t: float) -> float:
        return 2048.0 + amplitude * math.sin(2 * math.pi * hz * t + idx[motor])

    return hand


def gentle_hand(motor: str, t: float) -> float:
    return 2048.0 + 25.0 * math.sin(2 * math.pi * 0.5 * t)


def wait_for(pred: Callable[[], Any], timeout: float = 10.0, interval: float = 0.02) -> Any:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        v = pred()
        if v:
            return v
        time.sleep(interval)
    raise AssertionError(f"condition not met within {timeout}s")


class ManualClock:
    """A clock only the test moves (e.g. the dead-man watchdog's, NFR-4)."""

    def __init__(self) -> None:
        self.t = time.monotonic()

    def __call__(self) -> float:
        return self.t


def estop_ticks(st: Station) -> list[int]:
    """The loop tick at which the owner enters ``estopped``, recorded by the owner thread itself."""
    ticks: list[int] = []

    def on_event(kind: str, payload: dict[str, Any]) -> None:
        if kind == "state" and payload["state"] == "estopped":
            ticks.append(st.owner.tick)

    st.owner.add_listener(on_event)
    return ticks


def ticks_pass(st: Station, n: int) -> None:
    """Wait until the owner loop has run ``n`` more ticks."""
    t0 = st.owner.tick
    wait_for(lambda: st.owner.tick >= t0 + n, 10)


def press_estop_frozen_within_one_tick(st: Station, world: Any) -> None:
    """NFR-3a: from the press to no new position goal <= 1 tick (+ the inference in flight when a
    model runs), measured as NFR-3a says: by counting the goals written to the bus after the press
    (the hold write + at most the tick in flight) and the loop ticks until the owner is estopped
    (by the owner thread's own count), never with this thread's clock. A loaded CI runner wakes the
    test thread late: "one tick + 50 ms" failed there while the loop had stopped on time."""
    at = estop_ticks(st)
    world.record_calls = True
    t_press = time.monotonic()
    st.owner.press_estop("user")
    tick = st.owner.tick  # the tick in flight at the press is at most this one
    wait_for(lambda: at, 10)  # the owner thread sets the state, then tells its listeners
    writes = [t for t, _ in world.goal_writes() if t > t_press]
    assert len(writes) <= 2, writes  # the hold write (+ at most the tick in flight)
    assert at and at[0] <= tick + 1, (at, tick)


STATION_DIR = Path(__file__).resolve().parents[1]


def _ws_validator() -> Any:
    """JSON-schema validator for control-socket messages, from the committed openapi.json."""
    import json

    import jsonschema

    doc = json.loads((STATION_DIR / "openapi.json").read_text(encoding="utf-8"))
    schema = {"$ref": "#/components/schemas/ServerMessage", "components": doc["components"]}
    return jsonschema.Draft202012Validator(schema)


WS_VALIDATOR = _ws_validator()


def contract_errors(kind: str, payload: dict[str, Any]) -> list[str]:
    """Why a control-socket message (as the hub sends it) breaks the contract (§5.3), if it does."""
    import json

    from pydantic import ValidationError

    from hibiscus_station.api.schemas import SERVER_MESSAGE

    msg = json.loads(json.dumps({**payload, "type": kind}, default=str))
    out = [f"{kind}: {e.message} at {list(e.absolute_path)}" for e in WS_VALIDATOR.iter_errors(msg)][:3]
    try:
        SERVER_MESSAGE.validate_python(msg)
    except ValidationError as exc:
        out.append(f"{kind}: {str(exc)[:600]}")
    return out


class Events:
    """Records owner events and checks each one against the WebSocket contract."""

    def __init__(self) -> None:
        self.items: list[tuple[float, str, dict[str, Any]]] = []
        self.violations: list[str] = []
        self.lock = threading.Lock()

    def __call__(self, kind: str, payload: dict[str, Any]) -> None:
        errs = contract_errors(kind, payload)
        with self.lock:
            self.items.append((time.monotonic(), kind, payload))
            self.violations.extend(errs)

    def of(self, kind: str) -> list[dict[str, Any]]:
        with self.lock:
            return [p for _, k, p in self.items if k == kind]


class Heartbeat:
    """Plays the UI's dead-man heartbeat (every 250 ms) while a run session is active."""

    def __init__(self, station: Station) -> None:
        self.station = station
        self._stop = threading.Event()
        self._t = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        while not self._stop.is_set():
            self.station.owner.heartbeat()
            self._stop.wait(0.25)

    def __enter__(self) -> Heartbeat:
        self._t.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self._stop.set()
        self._t.join(1)


@pytest.fixture
def events() -> Events:
    return Events()


def make_station(tmp_path: Path, *, mock: bool = True) -> Station:
    st = Station(tmp_path / "station-home", mock=mock, cal_root=tmp_path / "calibration")
    st.settings.safety.smooth_approach_s = 0.3
    st.import_roots = [tmp_path]
    return st


@pytest.fixture
def station(tmp_path: Path, events: Events) -> Iterator[Station]:
    st = make_station(tmp_path)
    st.owner.add_listener(events)
    st.start()
    yield st
    st.shutdown()
    for port in ("mock://follower", "mock://leader"):
        assert not get_world(port).owner_violations, get_world(port).owner_violations
    assert not events.violations, "WebSocket contract violations:\n" + "\n".join(events.violations[:10])


def calibrate(st: Station, arm: str) -> dict[str, Any]:
    port = "mock://follower" if arm == "follower" else "mock://leader"
    world = get_world(port)
    world.hand = fast_hand()
    st.owner.call("calibration_start", arm=arm)
    time.sleep(0.1)
    st.owner.call("calibration_step", action="set_home")
    time.sleep(0.8)  # the "hand" sweeps every joint through > 100 steps
    out = st.owner.call("calibration_step", action="finish_ranges")
    world.hand = None if arm == "follower" else gentle_hand
    world.place_all(2048.0)
    return out  # type: ignore[no-any-return]


def connect_calibrated(st: Station, profile: RobotProfile | None = None) -> RobotProfile:
    profile = profile or mock_profile()
    get_world("mock://leader").hand = gentle_hand
    st.profiles.put(profile)
    st.owner.call("connect", robot_id=profile.id, timeout=30)
    calibrate(st, "follower")
    if profile.leader is not None:
        calibrate(st, "leader")
    get_world("mock://follower").place_all(2048.0)
    time.sleep(0.15)
    return profile


@pytest.fixture
def connected(station: Station) -> Station:
    connect_calibrated(station)
    return station


@pytest.fixture
def client(station: Station) -> Iterator[Any]:
    from fastapi.testclient import TestClient

    from hibiscus_station.api.security import LocalAuth
    from hibiscus_station.app import create_app

    auth = LocalAuth(token="test-token-" + "a" * 32, port=PORT, extra_hosts=("testserver",))  # WS test host
    app = create_app(station, auth, manage_lifecycle=False, static_dir=station.paths.home / "nostatic")
    with TestClient(app, base_url=BASE) as c:
        c.headers.update({"Authorization": f"Bearer {auth.token}", "X-Station": "1"})
        c.auth_obj = auth  # type: ignore[attr-defined]
        yield c
