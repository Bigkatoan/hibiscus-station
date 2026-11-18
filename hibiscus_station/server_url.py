"""Is this a Hibiscus server address? (field reports 0.2.9: D-25, QD-35)

A customer pasted a OneDrive link into "Server URL". The pairing form refuses such links, and the
Station refuses them again on ``POST /server/pair`` (defence in depth: nothing, and no token, is
ever sent to a file-sharing site). The web form has the same rules
(``web/src/station/components/PairForm.tsx``); both are tested on ``tests/server_urls.json``.
"""

from __future__ import annotations

import re
from typing import Literal
from urllib.parse import parse_qsl, unquote, urlsplit

ServerUrlProblem = Literal["not_url", "file_share"]

#: File-sharing / office sites: the domain itself or any subdomain of it.
FILE_SHARE_DOMAINS = (
    # Microsoft 365 / OneDrive / SharePoint
    "cloud.microsoft",
    "officeapps.live.com",
    "office.com",
    "office.net",
    "office365.com",
    "sharepoint.com",
    "sharepoint-df.com",
    "onedrive.com",
    "onedrive.live.com",
    "skydrive.live.com",
    "storage.live.com",
    "1drv.ms",
    "1drv.com",
    "microsoftpersonalcontent.com",
    # Google
    "drive.google.com",
    "docs.google.com",
    "googleusercontent.com",
    # Dropbox, Box, WeTransfer, iCloud, others
    "dropbox.com",
    "dropboxusercontent.com",
    "db.tt",
    "box.com",
    "box.net",
    "boxcloud.com",
    "wetransfer.com",
    "we.tl",
    "icloud.com",
    "mega.nz",
    "mediafire.com",
)

#: Query parameters of share links (OneDrive / Office / SharePoint), compared in lower case.
SHARE_PARAMS = frozenset({"docid", "driveid", "resid", "authkey", "redeem", "sourcedoc", "cid"})

#: Paths of share links: /open/onedrive, SharePoint "/:w:/", Google "/file/d/", "/drive/folders/",
#: SharePoint "/_layouts/", Dropbox "/scl/fi/", and a document file name at the end.
SHARE_PATH = re.compile(
    r"/open/onedrive|/:[a-z]{1,2}:/|/file/d/|/drive/folders/|/_layouts/|/scl/f[io]/"
    r"|\.(docx?|xlsx?|pptx?|pdf|zip|rar|7z|txt|csv|odt|ods)$",
    re.IGNORECASE,
)


def server_url_problem(raw: str) -> ServerUrlProblem | None:
    """Why ``raw`` cannot be a Hibiscus server address, or None when it can."""
    text = raw.strip()
    try:
        u = urlsplit(text)
        host = (u.hostname or "").rstrip(".").lower()
    except ValueError:
        return "not_url"
    if u.scheme.lower() not in ("http", "https") or not host or " " in text:
        return "not_url"
    if any(host == d or host.endswith(f".{d}") for d in FILE_SHARE_DOMAINS):
        return "file_share"
    if host.endswith(".live.com") and re.search(r"onedrive|skydrive|redeem|resid", text, re.IGNORECASE):
        return "file_share"
    if any(k.lower() in SHARE_PARAMS for k, _ in parse_qsl(u.query, keep_blank_values=True)):
        return "file_share"
    if SHARE_PATH.search(unquote(u.path)):
        return "file_share"
    return None
