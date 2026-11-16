"""The real entry point on a real socket: ``hibiscus-station --mock --no-browser`` (spec §10 A1)."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def test_serve_mock_single_instance_and_url(tmp_path: Path) -> None:
    port = _free_port()
    home = tmp_path / "home"
    env = {**os.environ, "HF_LEROBOT_CALIBRATION": str(tmp_path / "cal")}
    cmd = [
        sys.executable,
        "-m",
        "hibiscus_station.cli",
        "--mock",
        "--no-browser",
        "--port",
        str(port),
        "--home",
        str(home),
    ]
    proc = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)  # noqa: S603
    try:
        token_file = home / "token"
        base = f"http://127.0.0.1:{port}"
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            if token_file.is_file():
                try:
                    r = httpx.get(
                        f"{base}/api/v1/status",
                        headers={"Authorization": f"Bearer {token_file.read_text().strip()}"},
                    )
                    if r.status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
            time.sleep(0.3)
        token = token_file.read_text().strip()
        assert oct(token_file.stat().st_mode & 0o777) == "0o600"
        r = httpx.get(f"{base}/api/v1/status", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200 and r.json()["station"]["mock"] is True
        assert httpx.get(f"{base}/api/v1/status").status_code == 401
        assert httpx.get(f"{base}/api/v1/status", headers={"Host": f"evil.example:{port}"}).status_code == 403
        robots = httpx.get(f"{base}/api/v1/robots", headers={"Authorization": f"Bearer {token}"}).json()
        assert robots["robots"][0]["id"] == "demo_so101"
        # bootstrap link -> cookie session
        with httpx.Client(base_url=base) as c:
            r = c.get("/auth", params={"t": token})
            assert r.status_code in (200, 303)
            assert c.get("/api/v1/status").status_code == 200
        # a second launch prints the running instance's URL and exits 0
        out = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=60)  # noqa: S603
        assert out.returncode == 0 and "already running" in out.stdout and str(port) in out.stdout
        url = subprocess.run(  # noqa: S603
            [sys.executable, "-m", "hibiscus_station.cli", "url", "--home", str(home)],
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert f"127.0.0.1:{port}/auth?t={token}" in url.stdout
        assert json.loads((home / "station.pid").read_text())["port"] == port
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            proc.kill()


def _cli(*args: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        [sys.executable, "-m", "hibiscus_station.cli", *args],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


@pytest.mark.parametrize(
    ("token", "hosts"),
    [
        (None, "robot.example"),
        ("x" * 40, None),
        ("short", "robot.example"),
        ("bad token " * 5, "robot.example"),
    ],
)
def test_lan_mode_needs_a_fixed_token_and_allowed_hosts(
    tmp_path: Path, token: str | None, hosts: str | None
) -> None:
    env = {k: v for k, v in os.environ.items() if not k.startswith("HIBISCUS_STATION_")}
    env["HF_LEROBOT_CALIBRATION"] = str(tmp_path / "cal")
    if token is not None:
        env["HIBISCUS_STATION_TOKEN"] = token
    if hosts is not None:
        env["HIBISCUS_STATION_ALLOWED_HOSTS"] = hosts
    out = _cli("--mock", "--no-browser", "--host", "0.0.0.0", "--home", str(tmp_path / "h"), env=env)
    assert out.returncode == 2
    assert not (tmp_path / "h" / "token").exists()


def test_health_without_a_running_station_fails(tmp_path: Path) -> None:
    out = _cli("health", "--home", str(tmp_path / "nothing"), env=dict(os.environ))
    assert out.returncode == 1 and "not running" in out.stderr


def test_lan_mode_fixed_token_allowed_hosts_and_health(tmp_path: Path) -> None:
    """127.0.0.2 is not a loopback name Station knows, so it takes the LAN path but stays on lo."""
    port = _free_port()
    home = tmp_path / "home"
    token = "t0k3n-" + "a" * 40
    env = {
        **{k: v for k, v in os.environ.items() if not k.startswith("HIBISCUS_STATION_")},
        "HF_LEROBOT_CALIBRATION": str(tmp_path / "cal"),
        "HIBISCUS_STATION_TOKEN": token,
        "HIBISCUS_STATION_ALLOWED_HOSTS": "robot.example, 10.0.0.7",
    }
    cmd = [sys.executable, "-m", "hibiscus_station.cli", "--mock", "--no-browser", "--home", str(home)]
    cmd += ["--host", "127.0.0.2", "--port", str(port), "--allow-host", "station.example:8443"]
    proc = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)  # noqa: S603
    base = f"http://127.0.0.2:{port}"
    auth = {"Authorization": f"Bearer {token}"}
    try:
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            try:
                if httpx.get(f"{base}/api/v1/status", headers=auth).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.3)
        assert (home / "token").read_text().strip() == token
        for host in (
            f"robot.example:{port}",
            f"10.0.0.7:{port}",
            "station.example:8443",
            f"127.0.0.1:{port}",
        ):
            r = httpx.get(f"{base}/api/v1/status", headers={**auth, "Host": host})
            assert r.status_code == 200, host
        assert (
            httpx.get(f"{base}/api/v1/status", headers={**auth, "Host": f"evil.example:{port}"}).status_code
            == 403
        )
        assert (
            httpx.get(f"{base}/api/v1/status", headers={"Host": f"robot.example:{port}"}).status_code == 401
        )
        # the login link works from an allowed name; the cookie session follows
        with httpx.Client(base_url=base, headers={"Host": f"robot.example:{port}"}) as c:
            assert c.get("/auth", params={"t": token}).status_code in (200, 303)
            assert c.get("/api/v1/status").status_code == 200
        url = _cli("url", "--home", str(home), env=env)
        assert f"http://station.example:8443/auth?t={token}" in url.stdout  # the first --allow-host
        healthy = _cli("health", "--home", str(home), env=env)
        assert healthy.returncode == 0 and "healthy" in healthy.stdout
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            proc.kill()
