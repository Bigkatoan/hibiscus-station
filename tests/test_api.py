"""API contract (spec §5, §8): security, Problem errors, REST flows, control WS, video WS, openapi.json."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import pytest
from conftest import BASE, calibrate, gentle_hand, mock_profile, wait_for
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from hibiscus_station.hw.cameras import unpack_frame
from hibiscus_station.mock import get_world
from hibiscus_station.station import Station

STATION_DIR = Path(__file__).resolve().parents[1]


def _raw(client: TestClient, **headers: str) -> TestClient:
    c = TestClient(client.app, base_url=BASE)
    c.headers.update(headers)
    return c


def test_status_requires_auth_and_host(client: TestClient) -> None:
    assert client.get("/api/v1/status").status_code == 200
    anon = _raw(client)
    r = anon.get("/api/v1/status")
    assert r.status_code == 401 and r.json()["code"] == "unauthenticated"
    assert r.headers["content-type"].startswith("application/problem+json")
    evil = TestClient(client.app, base_url="http://evil.example:18210")
    evil.headers.update(client.headers)
    r = evil.get("/api/v1/status")
    assert r.status_code == 403 and r.json()["code"] == "forbidden_host"


def test_non_get_needs_x_station(client: TestClient) -> None:
    c = _raw(client, Authorization=client.headers["Authorization"])
    r = c.post("/api/v1/estop/reset")
    assert r.status_code == 403 and r.json()["code"] == "csrf"


def test_bootstrap_sets_httponly_cookie(client: TestClient) -> None:
    auth = client.auth_obj  # type: ignore[attr-defined]
    c = _raw(client)
    assert c.get("/auth", params={"t": "wrong"}, follow_redirects=False).status_code == 401
    r = c.get("/auth", params={"t": auth.token}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/"
    cookie = r.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=strict" in cookie
    assert auth.token not in cookie  # the cookie holds an HMAC session id, not the token
    assert c.get("/api/v1/status").status_code == 200
    assert c.post("/api/v1/estop/reset", headers={"X-Station": "1"}).json()["code"] == "busy"


def test_problem_shapes(client: TestClient) -> None:
    r = client.post("/api/v1/robots/nope/connect")
    body = r.json()
    assert r.status_code == 404 and body["code"] == "not_found"
    assert {"type", "title", "status", "code", "detail", "request_id"} <= set(body)
    r = client.put("/api/v1/robots/x", json={"id": "x"})
    assert r.status_code == 422 and r.json()["code"] == "validation_failed" and r.json()["errors"]
    r = client.post("/api/v1/sessions/teleop", json={})
    assert r.status_code == 409 and r.json()["code"] == "not_connected"


def test_settings_validation(client: TestClient) -> None:
    s = client.get("/api/v1/settings").json()
    assert s["thresholds"]["temp_critical_c"] == 65
    s["thresholds"]["temp_hot_c"] = 64  # hot must be <= critical - 3
    r = client.put("/api/v1/settings", json=s)
    assert r.status_code == 422
    s["thresholds"]["temp_hot_c"] = 58
    s["thresholds"]["temp_warn_c"] = 50
    r = client.put("/api/v1/settings", json=s)
    assert r.status_code == 200 and r.json()["thresholds"]["temp_hot_c"] == 58


def test_robot_crud_connect_calibrate_over_rest(client: TestClient, station: Station) -> None:
    prof = mock_profile().model_dump(mode="json")
    assert client.put("/api/v1/robots/desk", json=prof).status_code == 200
    assert "desk" in {r["id"] for r in client.get("/api/v1/robots").json()["robots"]}
    get_world("mock://leader").hand = gentle_hand
    r = client.post("/api/v1/robots/desk/connect")
    assert r.status_code == 200 and r.json()["state"] == "idle"
    assert client.delete("/api/v1/robots/desk").json()["code"] == "busy"
    r = client.post("/api/v1/calibration/start", json={"arm": "follower"})
    assert r.json()["state"] == "calibrating"
    get_world("mock://follower").hand = lambda m, t: 2048 + 200 * __import__("math").sin(12 * t)
    client.post("/api/v1/calibration/step", json={"action": "set_home"})
    time.sleep(0.7)
    r = client.post("/api/v1/calibration/step", json={"action": "finish_ranges"})
    assert r.status_code == 200, r.text
    assert r.json()["calibration"]["path"].endswith("desk_follower.json")
    files = client.get("/api/v1/calibrations").json()["files"]
    assert any(f["id"] == "desk_follower" for f in files)
    r = client.post("/api/v1/robots/torque", json={"arm": "follower", "enabled": False})
    assert r.status_code == 422  # no rest pose: confirm required
    r = client.post("/api/v1/robots/torque", json={"arm": "follower", "enabled": False, "confirm": True})
    assert r.json()["robot"]["follower_torque"] is False
    r = client.post("/api/v1/robots/disconnect", json={})
    assert r.json()["state"] == "disconnected"


def _auth(client: TestClient) -> dict[str, str]:
    return {"authorization": client.headers["Authorization"]}


def _ws_hello(ws: Any) -> dict[str, Any]:
    hello = ws.receive_json()
    assert hello["type"] == "hello" and hello["v"] == 1
    ws.send_json({"type": "hello", "v": 1, "client": "test", "heartbeat": True})
    return hello  # type: ignore[no-any-return]


def test_control_ws_auth_and_hello_timeout(client: TestClient) -> None:
    with pytest.raises(WebSocketDisconnect) as ei, _raw(client).websocket_connect("/api/v1/ws") as ws:
        ws.receive_json()
    assert ei.value.code == 4401
    with (
        pytest.raises(WebSocketDisconnect),
        client.websocket_connect(
            "/api/v1/ws", headers={**_auth(client), "origin": "http://evil.example"}
        ) as ws,
    ):
        ws.receive_json()
    with client.websocket_connect("/api/v1/ws", headers=_auth(client)) as ws:
        ws.receive_json()
        with pytest.raises(WebSocketDisconnect) as ei:
            ws.receive_json()  # no client hello within 2 s
        assert ei.value.code == 4401


def test_control_ws_subprotocol_auth(client: TestClient) -> None:
    tok = client.auth_obj.token  # type: ignore[attr-defined]
    with _raw(client).websocket_connect("/api/v1/ws", subprotocols=["hst.v1", f"bearer.{tok}"]) as ws:
        assert ws.accepted_subprotocol == "hst.v1"
        _ws_hello(ws)


def test_control_ws_streams_and_estop(client: TestClient, station: Station) -> None:
    station.profiles.put(mock_profile())
    get_world("mock://leader").hand = gentle_hand
    with client.websocket_connect("/api/v1/ws", headers=_auth(client)) as ws:
        _ws_hello(ws)
        client.post("/api/v1/robots/desk/connect")
        calibrate(station, "follower")
        calibrate(station, "leader")
        get_world("mock://follower").place_all(2048)
        r = client.post("/api/v1/sessions/teleop", json={"fps": 30})
        assert r.status_code == 200, r.text
        kinds: set[str] = set()
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and not {"joints", "telemetry", "session", "state"} <= kinds:
            kinds.add(ws.receive_json()["type"])
        assert {"joints", "telemetry", "session", "state"} <= kinds
        ws.send_json({"type": "estop"})
        deadline = time.monotonic() + 3
        estopped = False
        while time.monotonic() < deadline and not estopped:
            m = ws.receive_json()
            estopped = m["type"] == "state" and m["state"] == "estopped"
        assert estopped
    r = client.post("/api/v1/estop/reset")
    assert r.json()["state"] == "idle"


def test_video_ws_binary_frames(client: TestClient, station: Station) -> None:
    station.profiles.put(mock_profile(cameras=2, leader=False))
    client.post("/api/v1/robots/desk/connect")
    with client.websocket_connect("/api/v1/ws/video", headers=_auth(client)) as ws:
        ws.send_json({"type": "subscribe", "cameras": ["wrist", "front"], "width": 160, "fps": 12})
        seen = set()
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and seen != {"wrist", "front"}:
            msg = ws.receive_bytes()
            header, jpeg = unpack_frame(msg)
            assert jpeg[:2] == b"\xff\xd8"
            assert header["src_w"] == 128 and header["w"] == 128  # never upscaled
            seen.add(header["cam"])
        assert seen == {"wrist", "front"}


def test_camera_probe_and_discover(client: TestClient, station: Station) -> None:
    r = client.post(
        "/api/v1/cameras/probe",
        json={"type": "mock", "width": 128, "height": 96, "fps": 30, "duration_s": 0.5},
    )
    body = r.json()
    assert body["ok"] and body["snapshot_jpeg_b64"] and body["measured_fps"] > 15
    cams = client.get("/api/v1/cameras/discover").json()["cameras"]
    assert any(c["type"] == "mock" for c in cams)


def test_models_import_compat_load_over_rest(client: TestClient, station: Station, tmp_path: Path) -> None:
    from hibiscus_station.mock.policy import make_dummy_act, zip_dir

    src = make_dummy_act(tmp_path / "zipme" / "pretrained_model", {"wrist": (96, 128)})
    z = zip_dir(src.parent, tmp_path / "model.zip")
    with z.open("rb") as fh:
        r = client.post("/api/v1/models/import", files={"file": ("model.zip", fh, "application/zip")})
    assert r.status_code == 200, r.text
    job = r.json()
    wait_for(lambda: client.get(f"/api/v1/jobs/{job['id']}").json()["status"] in ("succeeded", "failed"), 20)
    job = client.get(f"/api/v1/jobs/{job['id']}").json()
    assert job["status"] == "succeeded", job
    key = job["result"]["model"]
    station.profiles.put(mock_profile())
    rep = client.get(f"/api/v1/models/{key}/compat", params={"robot": "desk"}).json()
    assert rep["ok"] and rep["camera_map"] == {"observation.images.wrist": "wrist"}
    r = client.post(f"/api/v1/models/{key}/load", json={"device": "cpu"})
    wait_for(lambda: client.get("/api/v1/models").json()["loaded"] is not None, 30)
    assert client.get("/api/v1/status").json()["loaded_model"] == key
    # local path import is limited to allowed roots
    r = client.post("/api/v1/models/import", json={"path": "/etc"})
    jid = r.json()["id"]
    wait_for(lambda: client.get(f"/api/v1/jobs/{jid}").json()["status"] == "failed", 10)
    assert client.delete(f"/api/v1/models/{key}").status_code == 204


def test_openapi_json_is_up_to_date() -> None:
    from hibiscus_station.openapi import export

    committed = (STATION_DIR / "openapi.json").read_text()
    assert json.loads(committed) == json.loads(export()), "run: hibiscus-station openapi openapi.json"


def test_static_spa_is_served(tmp_path: Path, station: Station) -> None:
    from hibiscus_station.api.security import LocalAuth
    from hibiscus_station.app import create_app

    static = tmp_path / "static"
    (static / "assets").mkdir(parents=True)
    (static / "index.html").write_text("<!doctype html><title>Hibiscus Station</title>")
    (static / "assets" / "app.js").write_text("console.log(1)")
    app = create_app(station, LocalAuth(port=18210), static_dir=static, manage_lifecycle=False)
    c = TestClient(app, base_url=BASE)
    assert "Hibiscus Station" in c.get("/").text
    assert "Hibiscus Station" in c.get("/run-model").text  # SPA fallback
    assert c.get("/assets/app.js").text == "console.log(1)"
    assert c.get("/api/v1/status").status_code == 401


def test_every_error_code_has_ui_text() -> None:
    """Problem codes (spec §5.1) are shown by code, never by detail: the UI needs a string for each."""
    from hibiscus_station.errors import STATUS

    i18n = STATION_DIR / "web" / "src" / "station" / "i18n"
    if not i18n.is_dir():
        pytest.skip("web sources not available")
    for lang in ("en", "vi"):
        errors = json.loads((i18n / f"{lang}.json").read_text())["errors"]
        missing = sorted(set(STATUS) - set(errors))
        assert not missing, f"{lang}.json errors.* missing {missing}"


def test_every_alert_message_key_has_ui_text() -> None:
    """Alert ``message_key`` values (spec §5.3) resolve to ``alerts.<key>`` in the UI strings."""
    import re

    i18n = STATION_DIR / "web" / "src" / "station" / "i18n"
    if not i18n.is_dir():
        pytest.skip("web sources not available")
    src = "\n".join(p.read_text() for p in (STATION_DIR / "hibiscus_station").rglob("*.py"))
    keys = set(re.findall(r'"((?:motor|camera|record|run|safety|telemetry)\.[a-z_]+(?:\.[a-z_]+)?)"', src))
    for group in re.findall(r'f"motor\.([a-z]+)\.\{lvl\}"', src):
        keys |= {f"motor.{group}.ok", f"motor.{group}.warn"}
    keys |= {f"motor.{g}.critical" for g in ("temp", "status", "voltage")} | {"motor.temp.hot"}
    keys = {k for k in keys if not k.startswith("telemetry.jsonl")}  # a file name, not a key
    assert len(keys) > 10, keys
    for lang in ("en", "vi"):
        alerts = json.loads((i18n / f"{lang}.json").read_text())["alerts"]
        for key in keys:
            node: Any = alerts
            for part in key.split("."):
                node = node.get(part) if isinstance(node, dict) else None
            assert isinstance(node, str), f"{lang}.json alerts.{key} missing"
