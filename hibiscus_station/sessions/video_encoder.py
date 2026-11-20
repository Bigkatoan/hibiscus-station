"""Episode video encoding in a child process (ADR-15).

LeRobot 0.7.1 encodes each recorded episode with SVT-AV1 (``libsvtav1``, ``libSvtAv1Enc`` 3.0.0 in
the PyAV 15.1 wheels; LeRobot pins ``av<16``) inside the calling process. On macOS, SVT-AV1 keeps
its internal semaphores as libdispatch semaphores, and when the encoder is freed while one of them
is below its initial count libdispatch stops the process: ``EXC_BREAKPOINT`` / SIGTRAP, "BUG IN CLIENT
OF LIBDISPATCH: Semaphore object deallocated while in use" (stack: PyAV ``Stream`` dealloc ->
``svt_av1_enc_deinit_handle`` -> ``svt_destroy_semaphore`` -> ``dispatch_release``). It happens on a
fraction of encoder teardowns, so a long recording session on a Mac took the whole Station down.
Linux and Windows semaphores do not check, which is why only macOS crashed.

On macOS, Station therefore runs LeRobot's own encode function (``dataset_writer._encode_video_worker``: same
codec, options and output as before) in one long-lived ``spawn`` worker process. SVT-AV1 is never
loaded in the Station process. If the worker dies (that trap, or any other native crash in FFmpeg),
the pool is replaced and the episode is encoded again from its frames, which LeRobot deletes only
after a successful encode. Linux and Windows keep the in-process encode (no such check there, and
the Windows close-window path, P-6, stays as QC'd); ``force=True`` runs the isolation anywhere (tests).
"""

from __future__ import annotations

import logging
import multiprocessing
import os
import signal
import sys
import threading
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

#: tries per episode video: a worker that died is replaced and the encode runs again
ATTEMPTS = 3
#: tests only: the worker kills itself once (SIGTRAP, like the macOS trap) if this file is absent
CRASH_ONCE_ENV = "HIBISCUS_TEST_ENCODER_CRASH_ONCE"

_pool: ProcessPoolExecutor | None = None
_pool_lock = threading.Lock()
_original: Any = None  # LeRobot's in-process ``_encode_video_worker``


def _child_encode(*args: Any) -> Path:
    """Runs in the worker process: LeRobot's own encode, unchanged."""
    from lerobot.datasets import dataset_writer

    marker = os.environ.get(CRASH_ONCE_ENV)
    if marker and not os.path.exists(marker):
        Path(marker).write_text(str(os.getpid()), encoding="utf-8")
        os.kill(os.getpid(), getattr(signal, "SIGTRAP", signal.SIGTERM))

    path: Path = dataset_writer._encode_video_worker(*args)
    return path


def _child_warm() -> None:
    """Runs in the worker process: load LeRobot's writer before the first episode needs it."""
    from lerobot.datasets import dataset_writer  # noqa: F401


def _executor() -> ProcessPoolExecutor:
    global _pool
    with _pool_lock:
        if _pool is None:
            # spawn: a fresh interpreter (no fork of a threaded process; the default on macOS and
            # Windows already). One worker: Station encodes an episode's cameras one after another.
            _pool = ProcessPoolExecutor(max_workers=1, mp_context=multiprocessing.get_context("spawn"))
        return _pool


def _drop(pool: ProcessPoolExecutor) -> None:
    global _pool
    with _pool_lock:
        if _pool is pool:
            _pool = None
    pool.shutdown(wait=False, cancel_futures=True)


def encode_isolated(*args: Any) -> Path:
    """``_encode_video_worker(*args)`` in the worker process; a dead worker is replaced and retried."""
    last: BaseException | None = None
    for attempt in range(1, ATTEMPTS + 1):
        pool = _executor()
        try:
            return pool.submit(_child_encode, *args).result()
        except BrokenProcessPool as exc:  # the worker died (native crash), not an encoding error
            log.warning("video encoder process died (attempt %d of %d): %s", attempt, ATTEMPTS, exc)
            _drop(pool)
            last = exc
    raise RuntimeError(f"video encoding failed: the encoder process died {ATTEMPTS} times") from last


def warm_up() -> None:
    """Start the worker and load LeRobot in it now (spawn + import take seconds on a Mac), so the
    first saved episode, and a Stop that waits for it, does not pay for that."""
    _executor().submit(_child_warm)


def isolate_video_encoding(force: bool = False) -> bool:
    """Route LeRobot's per-episode encode through :func:`encode_isolated` (idempotent). macOS only
    unless ``force``; returns whether the isolation is on (also when an earlier call forced it).

    LeRobot calls the module-level ``_encode_video_worker`` by name from
    ``DatasetWriter._encode_temporary_episode_video`` (``save_episode(parallel_encoding=False)``,
    Station's path). The pin is exact (ADR-3); ``tests/test_video_encoder.py`` fails if that seam moves.
    """
    global _original
    from lerobot.datasets import dataset_writer

    if dataset_writer._encode_video_worker is _isolated_worker:
        return True  # already on (macOS, or forced)
    if not (force or sys.platform == "darwin"):
        return False

    current = dataset_writer._encode_video_worker
    if current is not _isolated_worker:
        _original = current
        dataset_writer._encode_video_worker = _isolated_worker
    return True


def restore() -> None:
    """Undo :func:`isolate_video_encoding` (tests)."""
    from lerobot.datasets import dataset_writer

    if _original is not None and dataset_writer._encode_video_worker is _isolated_worker:
        dataset_writer._encode_video_worker = _original


def _isolated_worker(*args: Any) -> Path:
    return encode_isolated(*args)


def shutdown() -> None:
    """Stop the worker process (tests). Station keeps it for the life of the process: it is started
    once and the executor's own exit hook stops it."""
    global _pool
    with _pool_lock:
        pool, _pool = _pool, None
    if pool is not None:
        pool.shutdown(wait=True, cancel_futures=True)
