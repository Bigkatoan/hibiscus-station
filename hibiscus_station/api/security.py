"""Local security (spec §8): per-launch token, HMAC session cookie, host allow-list, CSRF header."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from pathlib import Path

from hibiscus_station.settings import write_private

COOKIE = "hst"
WS_PROTOCOL = "hst.v1"


class LocalAuth:
    def __init__(
        self, token: str | None = None, port: int = 18210, extra_hosts: tuple[str, ...] = ()
    ) -> None:
        self.token = token or secrets.token_urlsafe(32)
        self._secret = secrets.token_bytes(32)
        self.port = port
        self.extra_hosts = extra_hosts

    def write_token(self, path: Path) -> None:
        write_private(path, self.token + "\n")

    # ------------------------------------------------------------------ cookie
    def new_cookie(self) -> str:
        sid = secrets.token_urlsafe(16)
        mac = hmac.new(self._secret, sid.encode(), hashlib.sha256).hexdigest()
        return f"{sid}.{mac}"

    def cookie_ok(self, value: str | None) -> bool:
        if not value or "." not in value:
            return False
        sid, mac = value.rsplit(".", 1)
        want = hmac.new(self._secret, sid.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(want, mac)

    def token_ok(self, value: str | None) -> bool:
        return bool(value) and hmac.compare_digest(str(value), self.token)

    def bearer_ok(self, header: str | None) -> bool:
        if not header or not header.lower().startswith("bearer "):
            return False
        return self.token_ok(header[7:].strip())

    # ------------------------------------------------------------------ hosts / origins
    @property
    def allowed_hosts(self) -> set[str]:
        p = self.port
        return {f"127.0.0.1:{p}", f"localhost:{p}", f"[::1]:{p}", *self.extra_hosts}

    def host_ok(self, host: str | None) -> bool:
        return (host or "").lower() in self.allowed_hosts

    def origin_ok(self, origin: str | None) -> bool:
        if origin is None:
            return True  # non-browser clients (scripts) send no Origin; they still need a token
        p = self.port
        allowed = {f"http://127.0.0.1:{p}", f"http://localhost:{p}", f"http://[::1]:{p}"}
        # LAN mode (cli --allow-host): the names the owner listed, plain or behind a TLS proxy.
        allowed |= {f"{scheme}://{h}" for h in self.extra_hosts for scheme in ("http", "https")}
        return origin.lower() in allowed

    def ws_protocol_token(self, protocols: list[str]) -> str | None:
        for p in protocols:
            if p.startswith("bearer."):
                return p[len("bearer.") :]
        return None
