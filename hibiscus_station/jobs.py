"""Background jobs: uploads, pulls, model imports and loads (spec §4.2 jobs pool, §5.3 ``Job``)."""

from __future__ import annotations

import logging
import secrets
import threading
import time
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

from hibiscus_station.errors import StationError

log = logging.getLogger(__name__)


class JobCancelledError(Exception):
    pass


@dataclass
class Job:
    id: str
    kind: str
    subject: str | None = None  # dataset name (upload) or model key (load)
    status: str = "queued"
    progress: dict[str, Any] = field(
        default_factory=lambda: {"done": 0, "total": 0, "unit": "bytes", "phase": "queued"}
    )
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    created_at: float = field(default_factory=time.time)
    cancel: threading.Event = field(default_factory=threading.Event)
    future: Future[Any] | None = None
    _last_emit: float = 0.0

    def view(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "status": self.status,
            "subject": self.subject,
            "progress": dict(self.progress),
            "result": self.result,
            "error": self.error,
        }

    def check_cancel(self) -> None:
        if self.cancel.is_set():
            raise JobCancelledError()


Emit = Callable[[str, dict[str, Any]], None]


class JobManager:
    def __init__(self, emit: Emit, workers: int = 2) -> None:
        self.emit = emit
        self.jobs: dict[str, Job] = {}
        self._pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="job")
        self._lock = threading.Lock()

    def submit(
        self, kind: str, fn: Callable[[Job], dict[str, Any] | None], subject: str | None = None
    ) -> Job:
        job = Job(id=f"j_{secrets.token_hex(6)}", kind=kind, subject=subject)
        with self._lock:
            self.jobs[job.id] = job

        def run() -> None:
            job.status = "running"
            self._emit(job, force=True)
            try:
                job.result = fn(job)
                job.status = "succeeded"
            except JobCancelledError:
                job.status = "cancelled"
            except StationError as exc:
                job.status = "failed"
                job.error = exc.problem()
            except Exception as exc:
                log.exception("job %s failed", job.id)
                job.status = "failed"
                job.error = StationError("internal_error", f"{type(exc).__name__}: {exc}"[:500]).problem()
            self._emit(job, force=True)

        job.future = self._pool.submit(run)
        self._emit(job, force=True)
        return job

    def progress(
        self,
        job: Job,
        *,
        done: int | None = None,
        total: int | None = None,
        phase: str | None = None,
        unit: str | None = None,
        **extra: Any,
    ) -> None:
        if done is not None:
            job.progress["done"] = done
        if total is not None:
            job.progress["total"] = total
        if phase is not None:
            job.progress["phase"] = phase
        if unit is not None:
            job.progress["unit"] = unit
        job.progress.update(extra)
        self._emit(job)

    def _emit(self, job: Job, force: bool = False) -> None:
        now = time.monotonic()
        if force or now - job._last_emit >= 0.25:  # <= 4 Hz per job
            job._last_emit = now
            self.emit("job", job.view())

    def get(self, job_id: str) -> Job:
        job = self.jobs.get(job_id)
        if job is None:
            raise StationError("not_found", f"no job {job_id}")
        return job

    def cancel(self, job_id: str) -> Job:
        job = self.get(job_id)
        job.cancel.set()
        if job.future is not None and job.future.cancel():
            job.status = "cancelled"
            self._emit(job, force=True)
        return job

    def list(self) -> list[dict[str, Any]]:
        return [j.view() for j in sorted(self.jobs.values(), key=lambda j: j.created_at, reverse=True)]

    def wait(self, job_id: str, timeout: float = 60.0) -> Job:
        job = self.get(job_id)
        if job.future is not None:
            job.future.result(timeout=timeout)
        return job

    def busy(self, kind: str, key: str, value: Any) -> bool:
        return any(
            j.kind == kind and j.status in ("queued", "running") and (j.result or {}).get(key) == value
            for j in self.jobs.values()
        )

    def shutdown(self) -> None:
        for j in self.jobs.values():
            j.cancel.set()
        self._pool.shutdown(wait=False, cancel_futures=True)
