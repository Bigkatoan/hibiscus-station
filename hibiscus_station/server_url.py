"""Is this a Hibiscus server, and may it receive the token? (D-25; QC F029: QD-35, QD-40, QD-41)

A customer pasted a OneDrive link into "Server URL". Two layers:

1. :func:`server_url_problem`: a friendly early hint, shared with the pairing form
   (``web/src/station/components/PairForm.tsx``, same cases in ``tests/server_urls.json``). It
   knows only the share-link families the customer named (OneDrive / SharePoint / Office /
   ``cloud.microsoft``, Google Drive / Docs / usercontent, Dropbox), unwraps Outlook Safe Links and
   Google redirect links, and never judges an unknown host: such a list can never be complete and
   generic rules refuse real servers (QD-41).
2. :func:`probe_hibiscus`: what keeps the token safe (QD-40). Before the token is sent anywhere,
   ``POST /server/pair`` asks the candidate for the public Hibiscus login configuration
   (``GET /api/v1/auth/config``, no credentials, in the released server's API) and checks that the
   answer is a Hibiscus identity: status 200, ``application/json``, the ``AuthConfig`` shape. No
   redirect is followed and the probe has a short timeout. Anything else: ``server_not_hibiscus``.
"""

from __future__ import annotations

import asyncio
import ipaddress
import json
import threading
from typing import Any, Literal
from urllib.parse import parse_qsl, urlsplit

ServerUrlProblem = Literal["not_url", "file_share", "insecure"]

#: Share-link families the customer named: the domain itself or any subdomain of it.
FILE_SHARE_DOMAINS = (
    # Microsoft 365 / OneDrive / SharePoint / Office / Teams
    "cloud.microsoft",
    "officeapps.live.com",
    "office.com",
    "office.net",
    "office365.com",
    "sharepoint.com",
    "onedrive.com",
    "onedrive.live.com",
    "skydrive.live.com",
    "docs.live.net",
    "1drv.ms",
    "teams.microsoft.com",
    # Google
    "drive.google.com",
    "docs.google.com",
    "usercontent.google.com",
    "googleusercontent.com",
    # Dropbox
    "dropbox.com",
    "dropboxusercontent.com",
    "db.tt",
)

#: Link wrappers whose real target is in a query parameter: unwrapped and checked.
WRAPPERS: dict[str, tuple[str, ...]] = {
    "safelinks.protection.outlook.com": ("url",),
    "google.com": ("q", "url"),
}


def _on(host: str, domain: str) -> bool:
    return host == domain or host.endswith(f".{domain}")


#: Networks a plain http:// server may be on (QD-45): loopback, private (RFC 1918, ULA),
#: link-local, CGNAT (100.64/10, e.g. Tailscale).
LOCAL_NETWORKS = tuple(
    ipaddress.ip_network(n)
    for n in (
        "127.0.0.0/8",
        "10.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "169.254.0.0/16",
        "100.64.0.0/10",
        "::1/128",
        "fc00::/7",
        "fe80::/10",
    )
)


def is_local_host(host: str) -> bool:
    """A host on this computer or the local network: localhost, private / link-local / CGNAT
    addresses, ``*.local``, ``*.lan`` and single-label names. Plain http is only allowed there."""
    host = host.strip("[]").rstrip(".").lower()
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return "." not in host or _on(host, "localhost") or host.endswith(".local") or host.endswith(".lan")
    return any(ip in n for n in LOCAL_NETWORKS if n.version == ip.version)


def server_url_problem(raw: str, _depth: int = 0) -> ServerUrlProblem | None:
    """Why ``raw`` cannot be a Hibiscus server address, or None when the hint has nothing to say."""
    text = raw.strip()
    try:
        u = urlsplit(text)
        host = (u.hostname or "").rstrip(".").lower()
    except ValueError:
        return "not_url"
    if u.scheme.lower() not in ("http", "https") or not host or any(c.isspace() for c in text):
        return "not_url"
    if any(_on(host, d) for d in FILE_SHARE_DOMAINS):
        return "file_share"
    for wrapper, keys in WRAPPERS.items():
        if _on(host, wrapper) and _depth < 3:
            inner = [v for k, v in parse_qsl(u.query) if k.lower() in keys and "://" in v]
            if inner and server_url_problem(inner[0], _depth + 1) == "file_share":
                return "file_share"
    # The token must never cross the internet in clear text (QD-45).
    if u.scheme.lower() == "http" and not is_local_host(host):
        return "insecure"
    return None


# ----------------------------------------------------------------------------- identity probe
#: The probe never waits longer than this (connect, read, whole answer).
PROBE_TIMEOUT_S = 5.0
#: A login configuration is a few hundred bytes; never read more than this.
PROBE_MAX_BYTES = 64 * 1024


def is_hibiscus_identity(body: Any) -> bool:
    """The ``AuthConfig`` answer of the Hibiscus API (``GET /auth/config``, contract v0.1.1).

    Tolerant (QD-43): the key fields must be there with their types; new fields, new languages and
    other values are fine. ``supported_locales`` must name Vietnamese or English.
    """
    if not isinstance(body, dict):
        return False
    key = body.get("turnstile_site_key", 0)
    locales = body.get("supported_locales")
    return (
        (key is None or isinstance(key, str))
        and isinstance(body.get("email_delivery_enabled"), bool)
        and type(body.get("password_min_length")) is int
        and isinstance(locales, list)
        and all(isinstance(x, str) for x in locales)
        and bool({"vi", "en"} & set(locales))
    )


async def _probe(base: str) -> str | None:
    import httpx

    async with (
        httpx.AsyncClient(timeout=PROBE_TIMEOUT_S, follow_redirects=False) as c,
        c.stream("GET", f"{base}/auth/config", headers={"Accept": "application/json"}) as r,
    ):
        if r.is_redirect:
            return f"redirects to {r.headers.get('location', '?')[:120]}"
        if r.status_code != 200:
            return f"HTTP {r.status_code}"
        ctype = r.headers.get("content-type", "").split(";")[0].strip().lower()
        if ctype != "application/json":
            return f"answers {ctype or 'no content type'}, not JSON"
        data = b""
        async for chunk in r.aiter_bytes():
            data += chunk
            if len(data) > PROBE_MAX_BYTES:
                return "answer too large"
    try:
        body = json.loads(data)
    except ValueError:
        return "invalid JSON"
    return None if is_hibiscus_identity(body) else "not a Hibiscus identity"


async def _probe_with_deadline(base: str) -> str | None:
    import httpx

    try:
        # One deadline over the whole exchange: connect, headers and body (QD-42: a server that
        # drips one byte every few seconds never trips a per-read timeout).
        return await asyncio.wait_for(_probe(base), PROBE_TIMEOUT_S)
    except TimeoutError:
        return f"no answer within {PROBE_TIMEOUT_S:g} s"
    except httpx.TimeoutException:
        return f"no answer within {PROBE_TIMEOUT_S:g} s"
    except httpx.HTTPError as exc:
        return f"cannot reach it ({type(exc).__name__})"


def probe_hibiscus(base: str) -> str | None:
    """Ask ``base`` (``…/api/v1``) who it is, without credentials. None = a Hibiscus server, else why not."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(_probe_with_deadline(base))
    # Called from inside an event loop: run the probe on its own loop in a worker thread.
    out: list[str | None] = []
    t = threading.Thread(target=lambda: out.append(asyncio.run(_probe_with_deadline(base))), daemon=True)
    t.start()
    t.join(PROBE_TIMEOUT_S + 2)
    return out[0] if out else f"no answer within {PROBE_TIMEOUT_S:g} s"
