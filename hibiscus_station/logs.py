"""Log redaction (spec §8): PATs (``hbp_`` + 4 chars kept) and the local token never reach a log file."""

from __future__ import annotations

import logging
import re

PAT = re.compile(r"hbp_([A-Za-z0-9]{4})[A-Za-z0-9]{4}_[A-Za-z0-9_-]{43}")
LOCAL = re.compile(r"(\bt=|bearer[. ])([A-Za-z0-9_-]{20,})", re.IGNORECASE)


def redact(text: str) -> str:
    text = PAT.sub(r"hbp_\1…", text)
    return LOCAL.sub(r"\1…", text)


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        red = redact(msg)
        if red != msg:
            record.msg = red
            record.args = ()
        return True
