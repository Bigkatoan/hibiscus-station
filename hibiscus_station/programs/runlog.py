"""Program run logs: ``runs/programs/<run_id>.jsonl`` (station-programs.md §6, implementation map §2).

One :class:`~hibiscus_station.programs.schemas.ProgramLogLine` per line: the first is ``kind=start``
(program id, version, dry run), the last ``kind=end`` (outcome, steps, faults). Every line is also
emitted as a ``program_log`` control-socket message. Files are 0600 in a 0700 directory, appended
and flushed line by line so a crash keeps everything up to the fault.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import secrets
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

from hibiscus_station.errors import StationError
from hibiscus_station.programs.paths import program_run_log, program_runs_dir
from hibiscus_station.programs.schemas import (
    RUN_ID_RE,
    ProgramLogKind,
    ProgramLogLine,
    ProgramRunLog,
    ProgramRunSummary,
)

Emit = Callable[[str, dict[str, Any]], None]
MAX_MESSAGE = 500
MAX_LINES_READ = 20000
#: Lines kept in one run file. A long loop that logs (or sets variables) every iteration would grow
#: the file without end; past this, one warning line is written and later lines only reach the
#: control socket. ``end`` and ``fault`` lines are always kept, so the summary stays right.
MAX_FILE_LINES = 19000
KEEP_KINDS = frozenset({"end", "fault"})


def now_iso() -> str:
    return dt.datetime.now(dt.UTC).isoformat()


def new_run_id() -> str:
    now = dt.datetime.now(dt.UTC)
    return f"r_{now:%Y%m%d_%H%M%S}_{secrets.token_hex(2)}"


class RunLog:
    """``programs.interfaces.RunLog``: the writer of one run. Thread-safe."""

    def __init__(
        self,
        home: Path,
        run_id: str,
        *,
        program_id: str,
        version: int,
        dry_run: bool,
        emit: Emit | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.run_id = run_id
        self.program_id = program_id
        self.version = version
        self.dry_run = dry_run
        self.path = program_run_log(home, run_id)
        d = program_runs_dir(home)
        d.mkdir(parents=True, exist_ok=True)
        os.chmod(d, 0o700)
        fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_BINARY", 0), 0o600)
        self._fh = os.fdopen(fd, "a", encoding="utf-8")
        self._emit = emit
        self._clock = clock
        self._t0 = clock()
        self._lock = threading.Lock()
        self._seq = 0
        self.steps = 0
        self.faults = 0
        self.closed = False
        self.max_lines = MAX_FILE_LINES
        self.written = 0
        self.truncated = False
        self.motions_completed = 0

    def write(
        self,
        kind: ProgramLogKind | str,
        message: str,
        *,
        level: Literal["info", "warn", "error"] = "info",
        block_id: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> ProgramLogLine:
        with self._lock:
            self._seq += 1
            line = ProgramLogLine.model_validate(
                {
                    "run_id": self.run_id,
                    "seq": self._seq,
                    "t": round(self._clock() - self._t0, 3),
                    "level": level,
                    "kind": kind,
                    "block_id": block_id,
                    "message": message[:MAX_MESSAGE],
                    "data": data or {},
                }
            )
            if kind == "fault":
                self.faults += 1
            if kind == "motion" and (data or {}).get("outcome") == "completed":
                self.motions_completed += 1
            payload = line.model_dump(mode="json")
            if not self.closed:
                if self.written < self.max_lines or kind in KEEP_KINDS:
                    self._put(payload)
                elif not self.truncated:
                    self.truncated = True
                    self._put(
                        {
                            **payload,
                            "level": "warn",
                            "kind": "log",
                            "block_id": None,
                            "message": "the run log is full: later lines are only shown live",
                            "data": {"max_lines": self.max_lines},
                        }
                    )
        if self._emit is not None:
            self._emit("program_log", payload)
        return line

    def _put(self, payload: dict[str, Any]) -> None:
        self._fh.write(json.dumps(payload, separators=(",", ":"), default=str) + "\n")
        self._fh.flush()
        self.written += 1

    def start(self) -> ProgramLogLine:
        return self.write(
            "start",
            f"program {self.program_id} v{self.version}" + (" (dry run)" if self.dry_run else ""),
            data={
                "program_id": self.program_id,
                "version": self.version,
                "dry_run": self.dry_run,
                "started_at": now_iso(),
            },
        )

    def close(self, outcome: str, message: str | None = None) -> None:
        if self.closed:
            return
        level: Literal["info", "warn", "error"] = (
            "info"
            if outcome in ("completed", "stopped")
            else "error"
            if outcome in ("failed", "estopped")
            else "warn"
        )
        self.write(
            "end",
            message or outcome,
            level=level,
            data={"outcome": outcome, "steps": self.steps, "faults": self.faults, "ended_at": now_iso()},
        )
        with self._lock:
            self.closed = True
            self._fh.close()

    def discard(self) -> None:
        """The run never started (start checks failed): drop the empty file."""
        with self._lock:
            if not self.closed:
                self.closed = True
                self._fh.close()
        if self._seq == 0:
            self.path.unlink(missing_ok=True)


# =========================================================================== reading
def _lines(path: Path) -> list[ProgramLogLine]:
    out: list[ProgramLogLine] = []
    try:
        with path.open(encoding="utf-8") as fh:
            for i, raw in enumerate(fh):
                if i >= MAX_LINES_READ:
                    break
                try:
                    out.append(ProgramLogLine.model_validate_json(raw))
                except ValueError:
                    continue  # a torn last line after a crash
    except FileNotFoundError as exc:
        raise StationError("not_found", "no such run") from exc
    return out


def _summary(lines: list[ProgramLogLine]) -> ProgramRunSummary | None:
    if not lines or lines[0].kind != "start":
        return None
    start = lines[0].data
    end = lines[-1] if lines[-1].kind == "end" else None
    steps = sum(1 for ln in lines if ln.kind == "block")
    faults = sum(1 for ln in lines if ln.kind == "fault")
    outcome = end.data.get("outcome") if end is not None else None
    return ProgramRunSummary.model_validate(
        {
            "run_id": lines[0].run_id,
            "program_id": str(start.get("program_id", "")),
            "version": int(start.get("version", 1)),
            "started_at": str(start.get("started_at", "")),
            "ended_at": str(end.data.get("ended_at", "")) if end is not None else None,
            "outcome": outcome
            if outcome in ("completed", "stopped", "failed", "estopped", "timeout")
            else None,
            "dry_run": bool(start.get("dry_run", False)),
            "steps": int(end.data.get("steps", steps)) if end is not None else steps,
            "faults": int(end.data.get("faults", faults)) if end is not None else faults,
        }
    )


def _first_line(path: Path) -> ProgramLogLine | None:
    try:
        with path.open(encoding="utf-8") as fh:
            return ProgramLogLine.model_validate_json(fh.readline())
    except (OSError, ValueError):
        return None


def list_runs(home: Path, program_id: str, *, limit: int = 50) -> list[ProgramRunSummary]:
    """Runs of one program, newest first (``runs/programs/*.jsonl``)."""
    d = program_runs_dir(home)
    if not d.is_dir():
        return []
    out: list[ProgramRunSummary] = []
    for path in sorted(d.glob("r_*.jsonl"), reverse=True):
        if not RUN_ID_RE.fullmatch(path.stem):
            continue
        first = _first_line(path)
        if first is None or first.kind != "start" or first.data.get("program_id") != program_id:
            continue
        summary = _summary(_lines(path))
        if summary is not None:
            out.append(summary)
        if len(out) >= limit:
            break
    return out


def read_run(home: Path, program_id: str, run_id: str) -> ProgramRunLog:
    lines = _lines(program_run_log(home, run_id))
    summary = _summary(lines)
    if summary is None or summary.program_id != program_id:
        raise StationError("not_found", "no such run of this program", params={"run": run_id})
    return ProgramRunLog(summary=summary, lines=lines)
