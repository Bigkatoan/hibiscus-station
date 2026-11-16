"""Operator input routing (station-programs.md §4 "Operator", §7).

The program runs of this launch register here (``Station.programs.runs``) so that operator input
reaches the right :class:`ProgramRuntime` from either door:

* REST ``POST /programs/{id}/input`` — to the run of that program;
* control WS ``program_input`` — to the current run (the newest one that has not finished).

The runtime validates the input against its program (buttons, keys, the open ``ask``) through
:class:`~hibiscus_station.programs.conditions.OperatorLatches`.
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

from hibiscus_station.errors import StationError
from hibiscus_station.programs.schemas import KEY_RE, OperatorInput, ProgramState

if TYPE_CHECKING:
    from hibiscus_station.programs.interfaces import ProgramRuntime


class RunRegistry:
    """program id -> its latest runtime this launch (finished runs stay for ``/state``). Thread-safe."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._runs: dict[str, ProgramRuntime] = {}
        self._order: list[str] = []

    def register(self, program_id: str, runtime: ProgramRuntime) -> None:
        with self._lock:
            self._runs[program_id] = runtime
            if program_id in self._order:
                self._order.remove(program_id)
            self._order.append(program_id)

    def get(self, program_id: str) -> ProgramRuntime | None:
        with self._lock:
            return self._runs.get(program_id)

    def unfinished(self) -> list[ProgramRuntime]:
        with self._lock:
            return [rt for rt in self._runs.values() if not rt.finished]

    def running(self, program_id: str | None = None) -> ProgramRuntime:
        """The unfinished run of ``program_id`` (or the newest unfinished run); ``not_found`` if none."""
        with self._lock:
            ids = [program_id] if program_id is not None else list(reversed(self._order))
            for pid in ids:
                rt = self._runs.get(pid)
                if rt is not None and not rt.finished:
                    return rt
        what = f"program {program_id}" if program_id else "no program"
        raise StationError(
            "not_found",
            f"{what} is not running" if program_id else f"{what} is running",
            params={"program": program_id} if program_id else None,
        )

    def deliver(self, ev: OperatorInput, program_id: str | None = None) -> ProgramState:
        if ev.kind == "key" and not KEY_RE.fullmatch(ev.value.lower()):
            raise StationError(
                "validation_failed", "keys are 0-9 and a-z (Space is the e-stop)", params={"key": ev.value}
            )
        rt = self.running(program_id)
        rt.input(ev)
        return rt.state()
