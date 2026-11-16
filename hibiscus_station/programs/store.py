"""Program storage: ``robots/<robot>/programs/<id>/program.json`` (station-programs.md §2, §12.2).

``put`` saves the editor document as version + 1 and compiles it in the same step, so the stored
``ast``/``issues``/``refs`` always belong to the stored ``editor``. ``dry_run_version`` remembers the
last version that passed a dry run (§5.2). Files 0600, dirs 0700, atomic writes; thread-safe.
"""

from __future__ import annotations

import json
import shutil
import threading
from collections.abc import Callable
from pathlib import Path

from pydantic import ValidationError

from hibiscus_station.errors import StationError
from hibiscus_station.programs.compiler import compile_program
from hibiscus_station.programs.paths import RobotDataPaths
from hibiscus_station.programs.runlog import list_runs, now_iso
from hibiscus_station.programs.schemas import (
    ITEM_ID_RE,
    Program,
    ProgramInput,
    ProgramSummary,
)
from hibiscus_station.settings import ProgramSettings, write_private


def program_json(p: Program) -> str:
    """``Program`` as JSON text. ``editor`` goes through the stdlib encoder: a Blockly document nests
    two levels per chained block, so a program of a hundred statements is deeper than pydantic's JSON
    parse and serialization limits (it was saved, then read back as missing)."""
    doc = p.model_dump(mode="json", exclude={"editor"})
    doc["editor"] = p.editor
    return json.dumps(doc, ensure_ascii=False, separators=(",", ":"))


class ProgramStore:
    """``programs.interfaces.ProgramStore`` for one robot profile."""

    def __init__(
        self,
        paths: RobotDataPaths,
        settings: Callable[[], ProgramSettings],
        runs_home: Path | None = None,
    ) -> None:
        self.paths = paths
        self.robot_id = paths.robot_id
        self._settings = settings
        self._runs_home = runs_home
        self._lock = threading.RLock()

    # ------------------------------------------------------------------ reads
    def _read(self, path: Path) -> Program | None:
        try:
            return Program.model_validate(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValidationError, ValueError, RecursionError):
            return None

    def get(self, program_id: str) -> Program:
        path = self.paths.program_json(program_id)
        with self._lock:
            p = self._read(path) if path.is_file() else None
        if p is None:
            raise StationError("not_found", f"no program {program_id}", params={"program": program_id})
        return p

    def exists(self, program_id: str) -> bool:
        return self.paths.program_json(program_id).is_file()

    def all(self) -> list[ProgramSummary]:
        out: list[ProgramSummary] = []
        root = self.paths.programs
        if not root.is_dir():
            return out
        with self._lock:
            programs = [
                p
                for d in sorted(root.iterdir())
                if d.is_dir() and ITEM_ID_RE.fullmatch(d.name)
                for p in [self._read(d / "program.json")]
                if p is not None
            ]
        for p in programs:
            runs = list_runs(self._runs_home, p.id, limit=1) if self._runs_home is not None else []
            out.append(
                ProgramSummary(
                    id=p.id,
                    name=p.name,
                    version=p.version,
                    updated_at=p.updated_at,
                    ok=p.ast is not None and not any(i.severity == "error" for i in p.issues),
                    refs=p.refs,
                    dry_run_version=p.dry_run_version,
                    last_run=runs[0] if runs else None,
                )
            )
        return out

    # ------------------------------------------------------------------ writes
    def _write(self, p: Program) -> None:
        path = self.paths.program_json(p.id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.parent.chmod(0o700)
        write_private(path, program_json(p))

    def put(self, program_id: str, body: ProgramInput) -> Program:
        names = [b.name for b in body.buttons]
        if len(set(names)) != len(names):
            raise StationError("validation_failed", "operator button names must be unique")
        cfg = self._settings()
        result = compile_program(
            body.editor, body.buttons, max_blocks=cfg.max_blocks, wait_timeout_s=cfg.wait_timeout_s
        )
        with self._lock:
            path = self.paths.program_json(program_id)
            old = self._read(path) if path.is_file() else None
            now = now_iso()
            p = Program(
                id=program_id,
                name=body.name,
                robot=self.robot_id,
                version=(old.version + 1) if old is not None else 1,
                created_at=old.created_at if old is not None else now,
                updated_at=now,
                editor=body.editor,
                buttons=body.buttons,
                ast=result.ast,
                issues=result.issues,
                refs=result.refs,
                dry_run_version=old.dry_run_version if old is not None else None,
            )
            self._write(p)
        return p

    def delete(self, program_id: str) -> None:
        with self._lock:
            path = self.paths.program_json(program_id)
            if not path.is_file():
                raise StationError("not_found", f"no program {program_id}", params={"program": program_id})
            shutil.rmtree(path.parent)

    def mark_dry_run(self, program_id: str, version: int) -> None:
        """Remember that ``version`` passed a dry run (ignored when the program changed since)."""
        with self._lock:
            p = self.get(program_id)
            if p.version != version:
                return
            self._write(p.model_copy(update={"dry_run_version": version}))
