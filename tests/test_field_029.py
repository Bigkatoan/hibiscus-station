"""Field report 0.2.9 (customer check_ver_2.9, 2026-11-18).

D-24: "the first motion starts far from the arm's pose" was a warning that stayed on the program
after the run. The player always approaches the first sample slowly (minimum-jerk), so this is
information, not a problem: the issue has the new severity ``info`` (never blocks, never needs a
confirmation, does not make a check "not ok") and disappears once the arm is within the limit.

D-25 / QD-35: the Station itself refuses a server address that is not http(s) or is a file-share
link (OneDrive in all its forms, SharePoint, Google Drive, Dropbox, Box, WeTransfer, iCloud).
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from blocks_dsl import play, program
from conftest import STATION_DIR
from test_compiler import A, _program, ctx

from hibiscus_station.programs import schemas as ps
from hibiscus_station.programs.validator import blocking, check_program

API = "/api/v1"
FAR = {"shoulder_pan.pos": 80.0, "elbow_flex.pos": 0.0, "gripper.pos": 0.0}
NEAR = {"shoulder_pan.pos": 10.0, "elbow_flex.pos": -5.0, "gripper.pos": 0.0}


def _check(positions: dict[str, float]) -> ps.CheckReport:
    return check_program(_program(program(play(A, id_="p"))), ctx(positions=positions))


def test_first_motion_far_is_information_not_a_warning() -> None:
    rep = _check(FAR)
    [far] = [i for i in rep.issues if i.code == "first_motion_far"]
    assert far.severity == "info"
    assert far.block_id == "p"
    assert far.params == {"deg": 80.0, "max_deg": 30.0}
    assert rep.ok
    assert blocking(rep, []) == []
    assert not [i for i in rep.issues if i.severity == "warning"]


def test_first_motion_info_goes_away_once_the_arm_is_near() -> None:
    assert [i.code for i in _check(FAR).issues] == ["first_motion_far"]
    assert _check(NEAR).issues == []
    assert _check({}).issues == []  # pose unknown (no robot): nothing to say


def test_info_severity_is_in_the_api_contract() -> None:
    doc: dict[str, Any] = json.loads((STATION_DIR / "openapi.json").read_text(encoding="utf-8"))
    severity = doc["components"]["schemas"]["CheckIssue"]["properties"]["severity"]
    assert "info" in severity["enum"]
    ps.CheckIssue.model_validate(
        {
            "id": "first_motion_far:p",
            "code": "first_motion_far",
            "severity": "info",
            "block_id": "p",
            "message_key": "programs.issues.first_motion_far",
            "params": {},
        }
    )


# =========================================================================== D-25 / QD-35: server address
CASES: list[list[Any]] = json.loads((STATION_DIR / "tests" / "server_urls.json").read_text(encoding="utf-8"))[
    "cases"
]


@pytest.mark.parametrize(("url", "problem"), CASES)
def test_server_url_problem(url: str, problem: str | None) -> None:
    from hibiscus_station.server_url import server_url_problem

    assert server_url_problem(url) == problem


CUSTOMER_ONEDRIVE = "https://word.cloud.microsoft/open/onedrive/?docId=0123456789ABCDEF%21s1a2b3c4d5e6f&driveId=0123456789ABCDEF"


@pytest.mark.parametrize(
    ("url", "code"),
    [
        (CUSTOMER_ONEDRIVE, "server_url_file_share"),
        ("https://contoso-my.sharepoint.com/:f:/g/personal/x/EabC?e=1", "server_url_file_share"),
        ("ftp://hibiscus.example.org", "server_url_invalid"),
        ("hibiscus server", "server_url_invalid"),
    ],
)
def test_pair_refuses_a_file_share_or_non_http_address(client: Any, url: str, code: str) -> None:
    """Defence in depth: the Station refuses before any request leaves it (no token sent anywhere)."""
    r = client.post(f"{API}/server/pair", json={"url": url, "token": "hbp_" + "x" * 40})
    assert r.status_code == 422, r.text
    assert r.json()["code"] == code
    assert not client.get(f"{API}/server").json()["paired"]


# =========================================================================== QD-40: identity probe before the token
HIBISCUS_CONFIG = {
    "turnstile_site_key": None,
    "email_delivery_enabled": False,
    "password_min_length": 12,
    "supported_locales": ["vi", "en"],
}
PAT = "hbp_AbCd1234_" + "x" * 43


class _Seen:
    def __init__(self) -> None:
        self.requests: list[tuple[str, str, str | None]] = []  # (server, path, Authorization)

    def with_token(self) -> list[tuple[str, str, str | None]]:
        return [r for r in self.requests if r[2]]


def _serve(name: str, seen: _Seen, reply: Any) -> Any:
    """A real local HTTP server; ``reply(handler)`` answers every GET / POST."""
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    class H(BaseHTTPRequestHandler):
        def _any(self) -> None:
            seen.requests.append((name, self.path, self.headers.get("Authorization")))
            reply(self)

        def do_GET(self) -> None:
            self._any()

        def do_POST(self) -> None:
            self._any()

        def log_message(self, *_a: Any) -> None:
            pass

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def _send(h: Any, status: int, body: bytes, ctype: str, headers: dict[str, str] | None = None) -> None:
    h.send_response(status)
    h.send_header("Content-Type", ctype)
    h.send_header("Content-Length", str(len(body)))
    for k, v in (headers or {}).items():
        h.send_header(k, v)
    h.end_headers()
    h.wfile.write(body)


def _hibiscus_like(h: Any) -> None:
    if h.path == "/api/v1/auth/config":
        _send(h, 200, json.dumps(HIBISCUS_CONFIG).encode(), "application/json")
    else:  # /auth/me with this token: rejected (enough to see the token went here, and only here)
        body = b'{"type":"x","title":"Unauthorized","status":401,"code":"unauthenticated"}'
        _send(h, 401, body, "application/problem+json")


def _url(srv: Any) -> str:
    return f"http://127.0.0.1:{srv.server_address[1]}"


def _pair(client: Any, url: str) -> Any:
    return client.post(f"{API}/server/pair", json={"url": url, "token": PAT})


@pytest.fixture
def seen() -> _Seen:
    return _Seen()


@pytest.fixture(autouse=True)
def _no_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    for k in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        monkeypatch.delenv(k, raising=False)


def test_a_hibiscus_server_gets_the_token_only_after_it_proved_itself(client: Any, seen: _Seen) -> None:
    srv = _serve("hibiscus", seen, _hibiscus_like)
    try:
        r = _pair(client, _url(srv))
    finally:
        srv.shutdown()
    # The fake rejects the token: the pairing fails, but the token was sent there, after the probe.
    assert r.status_code == 422 and r.json()["code"] == "validation_failed", r.text
    assert seen.requests[0] == ("hibiscus", "/api/v1/auth/config", None)
    assert [p for _n, p, a in seen.requests if a] == ["/api/v1/auth/me"]


@pytest.mark.parametrize(
    "reply",
    [
        # a web site: HTML for everything
        lambda h: _send(h, 200, b"<html><body>Files</body></html>", "text/html; charset=utf-8"),
        # JSON, but not a Hibiscus identity (a generic health endpoint)
        lambda h: _send(h, 200, b'{"status":"ok"}', "application/json"),
        # the right shape served as text
        lambda h: _send(h, 200, json.dumps(HIBISCUS_CONFIG).encode(), "text/plain"),
        # not found
        lambda h: _send(h, 404, b"not found", "text/plain"),
    ],
    ids=["html", "other-json", "wrong-content-type", "404"],
)
def test_a_server_that_is_not_hibiscus_never_sees_the_token(client: Any, seen: _Seen, reply: Any) -> None:
    srv = _serve("other", seen, reply)
    try:
        r = _pair(client, _url(srv) + "/share/abc")
    finally:
        srv.shutdown()
    assert r.status_code == 422, r.text
    assert r.json()["code"] == "server_not_hibiscus"
    assert seen.requests, "the probe went out"
    assert seen.with_token() == []
    assert not client.get(f"{API}/server").json()["paired"]


def test_a_redirect_to_another_host_is_not_followed(client: Any, seen: _Seen) -> None:
    good = _serve("hibiscus", seen, _hibiscus_like)
    target = _url(good).replace("127.0.0.1", "localhost")  # another host
    redirector = _serve(
        "redirector",
        seen,
        lambda h: _send(h, 302, b"", "text/plain", {"Location": target + h.path}),
    )
    try:
        r = _pair(client, _url(redirector))
    finally:
        redirector.shutdown()
        good.shutdown()
    assert r.status_code == 422 and r.json()["code"] == "server_not_hibiscus", r.text
    assert [n for n, _p, _a in seen.requests] == ["redirector"]
    assert seen.with_token() == []


def test_a_server_that_does_not_answer_in_time_is_refused(
    client: Any, seen: _Seen, monkeypatch: pytest.MonkeyPatch
) -> None:
    import time

    from hibiscus_station import server_url

    monkeypatch.setattr(server_url, "PROBE_TIMEOUT_S", 0.5)
    srv = _serve("slow", seen, lambda h: (time.sleep(2.0), _hibiscus_like(h)))
    try:
        t0 = time.monotonic()
        r = _pair(client, _url(srv))
        took = time.monotonic() - t0
    finally:
        srv.shutdown()
    assert r.status_code == 422 and r.json()["code"] == "server_not_hibiscus", r.text
    assert took < 1.8
    assert seen.with_token() == []


@pytest.mark.parametrize(
    "url",
    [
        # usercontent-style download host (a host the share-link hint does not know)
        "https://files.usercontent.example.test/download?id=1AbC&export=download",
        "https://www.fshare.vn/file/ABCDEF123",
        "https://www.terabox.com/s/1AbC",
        "https://sites.google.com/view/lab-files",
        "https://app.box.com/s/abc123",
    ],
)
def test_share_sites_the_hint_does_not_know_never_get_the_token(client: Any, url: str) -> None:
    import respx

    with respx.mock(assert_all_mocked=False, assert_all_called=False) as router:
        route = router.route(host__regex=r".*").respond(
            200, html="<html><body>Download</body></html>", headers={"content-type": "text/html"}
        )
        r = _pair(client, url)
    assert r.status_code == 422 and r.json()["code"] == "server_not_hibiscus", r.text
    assert route.calls, "the probe went out"
    assert all("authorization" not in c.request.headers for c in route.calls)


@pytest.mark.parametrize(
    "url",
    [
        "https://drive.usercontent.google.com/download?id=1AbC&export=download",
        "https://nam12.safelinks.protection.outlook.com/?url=https%3A%2F%2F1drv.ms%2Fw%2Fs%21AmPle&data=05",
        "https://teams.microsoft.com/l/file/ABC?tenantId=x&objectUrl=https%3A%2F%2Fcontoso.sharepoint.com%2Fx.docx",
        "https://d.docs.live.net/0123456789abcdef/Documents",
    ],
)
def test_known_share_links_are_refused_before_any_request(client: Any, url: str) -> None:
    import respx

    with respx.mock(assert_all_mocked=True, assert_all_called=False) as router:
        route = router.route(host__regex=r".*").respond(500)
        r = _pair(client, url)
    assert r.status_code == 422 and r.json()["code"] == "server_url_file_share", r.text
    assert not route.calls
