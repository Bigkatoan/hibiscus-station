"""CameraHub (one owner per camera) and PreviewEncoder (R2, spec §4.6, §5.4).

The control loop calls :meth:`CameraHub.read_latest_all` and then :meth:`CameraHub.publish` with
the *same* arrays it merged into the observation (no copy). The preview encoder only ever encodes
the latest published :class:`FrameSet`, so the UI shows exactly what the policy / dataset received,
tagged with the tick number.
"""

from __future__ import annotations

import asyncio
import json
import logging
import struct
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from hibiscus_station.hw.locks import DeviceBusyError, DeviceLock
from hibiscus_station.profiles import CameraProfile

log = logging.getLogger(__name__)

MAGIC = b"HSF1"


# --------------------------------------------------------------------------- wire format §5.4
def pack_frame(header: dict[str, Any], jpeg: bytes) -> bytes:
    h = json.dumps(header, separators=(",", ":")).encode()
    return MAGIC + struct.pack(">H", len(h)) + h + jpeg


def unpack_frame(msg: bytes) -> tuple[dict[str, Any], bytes]:
    if msg[:4] != MAGIC:
        raise ValueError("bad magic")
    (n,) = struct.unpack(">H", msg[4:6])
    header = json.loads(msg[6 : 6 + n])
    if not isinstance(header, dict):
        raise ValueError("bad header")
    return header, msg[6 + n :]


def encode_preview(frame: NDArray[Any], width: int, quality: int) -> tuple[bytes, int, int]:
    """Resize (INTER_AREA, aspect kept) and JPEG-encode an RGB frame."""
    import cv2

    h, w = frame.shape[:2]
    width = max(16, min(int(width), w))
    height = max(1, round(h * width / w))
    img = (
        frame
        if (width == w and height == h)
        else cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA)
    )
    ok, buf = cv2.imencode(
        ".jpg", cv2.cvtColor(img, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, int(quality)]
    )
    if not ok:  # pragma: no cover
        raise RuntimeError("jpeg encode failed")
    return bytes(buf), width, height


@dataclass
class FrameSet:
    tick: int
    t: float
    frames: dict[str, NDArray[Any]]
    policy_input: bool = False
    stale: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- hub
#: A frame is "fresh" for the control loop when it is at most this old (field report 0.2.9). Two
#: camera periods (66 ms at 30 fps) flagged most ticks of a Windows webcam that delivers fewer
#: frames than configured (MSMF / DirectShow in low light, a busy USB hub) as "No fresh frames"
#: and dropped them from the dataset. The latest frame of a slower camera is what the loop gets.
MIN_FRESH_MS = 250.0
FRESH_PERIODS = 3.0


def fresh_age_ms(camera_fps: float) -> float:
    return max(MIN_FRESH_MS, FRESH_PERIODS * 1000.0 / max(1.0, float(camera_fps)))


@dataclass
class CamStats:
    """What a camera really delivered during a session (session summary, doctor zip)."""

    ticks: int = 0
    stale_ticks: int = 0
    new_frames: int = 0
    first_t: float | None = None
    last_t: float | None = None
    last_frame_id: int = 0
    ages_ms: list[float] = field(default_factory=list)

    def note(self, frame: Any, age_ms: float | None, now: float) -> None:
        self.ticks += 1
        if id(frame) != self.last_frame_id:
            self.last_frame_id = id(frame)
            self.new_frames += 1
            if self.first_t is None:
                self.first_t = now
            self.last_t = now
        if age_ms is not None and len(self.ages_ms) < 20000:
            self.ages_ms.append(age_ms)


def _p(values: list[float], q: float) -> float | None:
    if not values:
        return None
    return round(float(np.percentile(np.asarray(values), q)), 1)


def camera_backend(camera: Any) -> str:
    """OpenCV backend (MSMF / DSHOW / V4L2 ...) of a lerobot OpenCVCamera, else the camera class."""
    cap = getattr(camera, "videocapture", None)
    if cap is not None:
        try:
            return str(cap.getBackendName())
        except Exception:  # noqa: S110 - a closed capture has no backend name
            pass
    return type(camera).__name__


def frame_age_ms(camera: Any, now_perf: float) -> float | None:
    ts = getattr(camera, "latest_timestamp", None)
    return (now_perf - float(ts)) * 1000.0 if isinstance(ts, (int, float)) else None


@dataclass
class _Cam:
    name: str
    profile: CameraProfile
    camera: Any
    lock: DeviceLock | None
    stale_since: float | None = None
    error: str | None = None
    stats: CamStats = field(default_factory=CamStats)


def device_key(p: CameraProfile) -> str:
    if p.type == "realsense":
        return f"realsense:{p.serial_number_or_name}"
    return str(p.index_or_path)


def camera_target(index_or_path: int | str | None) -> int | Path:
    """OpenCV target of a profile: an index (``0``, or ``"0"`` as the UI sends it; the only kind on
    Windows and macOS) or a device path (``/dev/v4l/by-id/...``). A digit string opened as a path
    would be read as a file name and fail."""
    if isinstance(index_or_path, int):
        return index_or_path
    text = str(index_or_path).strip()
    return int(text) if text.isdigit() else Path(text)


def build_camera(name: str, p: CameraProfile) -> Any:
    if p.type == "mock":
        from hibiscus_station.mock.camera import MockCamera, MockCameraConfig

        return MockCamera(MockCameraConfig(name=name, fps=p.fps, width=p.width, height=p.height))
    if p.type == "realsense":  # pragma: no cover - needs pyrealsense2
        from lerobot.cameras.realsense import RealSenseCamera, RealSenseCameraConfig

        return RealSenseCamera(
            RealSenseCameraConfig(
                serial_number_or_name=str(p.serial_number_or_name), fps=p.fps, width=p.width, height=p.height
            )
        )
    from lerobot.cameras import Cv2Rotation
    from lerobot.cameras.opencv import OpenCVCamera, OpenCVCameraConfig

    return OpenCVCamera(
        OpenCVCameraConfig(
            index_or_path=camera_target(p.index_or_path),
            fps=p.fps,
            width=p.width,
            height=p.height,
            rotation=Cv2Rotation(p.rotation),
            fourcc=p.fourcc,
        )
    )


#: Windows / macOS cameras are OpenCV indices (no ``/dev/video*``). They are numbered without gaps,
#: so the scan stops after a few missing ones instead of trying lerobot's 60 (slow on MSMF).
MAX_CAMERA_INDEX = 16
MAX_MISSES = 3
VIDEO_DIR = Path("/dev")


def _probe_index(target: int | str) -> dict[str, Any] | None:
    import cv2

    cap = cv2.VideoCapture(target)  # CAP_ANY: MSMF then DSHOW on Windows, like lerobot's cameras
    try:
        if not cap.isOpened():
            return None
        code = int(cap.get(cv2.CAP_PROP_FOURCC))
        return {
            "name": f"OpenCV Camera @ {target}",
            "type": "OpenCV",
            "id": target,
            "backend_api": cap.getBackendName(),
            "default_stream_profile": {
                "format": cap.get(cv2.CAP_PROP_FORMAT),
                "fourcc": "".join(chr((code >> 8 * i) & 0xFF) for i in range(4)),
                "width": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                "height": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
                "fps": cap.get(cv2.CAP_PROP_FPS),
            },
        }
    finally:
        cap.release()


def quiet_opencv() -> None:
    """Keep OpenCV's backend probing warnings (Windows dshow / MSMF listing) off the console;
    Station reports a camera that does not open on its own."""
    try:
        import cv2

        cv2.utils.logging.setLogLevel(cv2.utils.logging.LOG_LEVEL_ERROR)
    except Exception:  # noqa: S110 - an OpenCV build without the logging module: keep its default
        pass


def find_opencv_cameras(
    skip: set[str] | frozenset[str] = frozenset(), *, platform: str = sys.platform
) -> list[dict[str, Any]]:
    """OpenCV cameras in lerobot's ``find_cameras`` format, never opening an id in ``skip`` (the
    ones Station streams). Linux probes ``/dev/video*``; other systems probe indices 0, 1, 2...
    until ``MAX_MISSES`` in a row fail."""
    import lerobot.cameras.opencv  # noqa: F401 - sets lerobot's MSMF environment before cv2 opens

    quiet_opencv()
    found: list[dict[str, Any]] = []
    if platform == "linux":
        for dev in sorted(VIDEO_DIR.glob("video*"), key=lambda p: p.name):
            if str(dev) not in skip and (info := _probe_index(str(dev))) is not None:
                found.append(info)
        return found
    misses = 0
    for index in range(MAX_CAMERA_INDEX):
        if str(index) in skip:
            misses = 0
            continue
        info = _probe_index(index)
        if info is None:
            misses += 1
            if misses >= MAX_MISSES:
                break
            continue
        misses = 0
        found.append(info)
    return found


class CameraHub:
    def __init__(
        self, locks_dir: Path, *, factory: Callable[[str, CameraProfile], Any] = build_camera
    ) -> None:
        self.locks_dir = locks_dir
        self.factory = factory
        self._cams: dict[str, _Cam] = {}
        self._lock = threading.RLock()
        self._latest: FrameSet | None = None
        self._latest_lock = threading.Lock()
        self.loop_active = False  # the control loop publishes; otherwise previews read themselves
        self._idle_tick = 0

    # ------------------------------------------------------------------ lifecycle
    def configure(self, cams: dict[str, CameraProfile]) -> dict[str, str]:
        """Open every configured camera (keeping the ones already open); returns errors by name."""
        errors: dict[str, str] = {}
        with self._lock:
            for name in list(self._cams):
                c = self._cams[name]
                if name not in cams or cams[name] != c.profile:
                    self._close(name)
            for name, p in cams.items():
                if name in self._cams:
                    continue
                err = self._open(name, p)
                if err:
                    errors[name] = err
        return errors

    def _open(self, name: str, p: CameraProfile) -> str | None:
        lock = None
        if p.type != "mock":
            lock = DeviceLock(self.locks_dir, device_key(p))
            try:
                lock.acquire()
            except DeviceBusyError as exc:
                return f"camera_busy: held by pid {exc.holder}"
        try:
            cam = self.factory(name, p)
            cam.connect(warmup=True)
        except Exception as exc:
            if lock:
                lock.release()
            log.warning("camera %s failed to open: %s", name, exc)
            return f"camera_unavailable: {exc}"[:300]
        self._cams[name] = _Cam(name, p, cam, lock)
        return None

    def _close(self, name: str) -> None:
        c = self._cams.pop(name, None)
        if c is None:
            return
        try:
            c.camera.disconnect()
        except Exception as exc:  # pragma: no cover
            log.warning("camera %s disconnect: %s", name, exc)
        if c.lock:
            c.lock.release()

    def close_all(self) -> None:
        with self._lock:
            for name in list(self._cams):
                self._close(name)
        with self._latest_lock:
            self._latest = None

    # ------------------------------------------------------------------ access
    @property
    def names(self) -> list[str]:
        return list(self._cams)

    def camera(self, name: str) -> Any:
        return self._cams[name].camera

    def shapes(self) -> dict[str, tuple[int, int, int]]:
        return {n: (c.profile.height, c.profile.width, 3) for n, c in self._cams.items()}

    def holders(self) -> dict[str, str]:
        return {device_key(c.profile): n for n, c in self._cams.items()}

    def has_cameras(self) -> bool:
        return bool(self._cams)

    def read_latest_all(
        self, max_age_ms: float, now: float | None = None
    ) -> tuple[dict[str, Any], list[str]]:
        """``{name: HxWx3 RGB}`` + names of stale cameras (their last good frame is NOT returned)."""
        now = time.monotonic() if now is None else now
        frames: dict[str, Any] = {}
        stale: list[str] = []
        perf = time.perf_counter()
        for name, c in list(self._cams.items()):
            try:
                frames[name] = c.camera.read_latest(max_age_ms=int(max(1, max_age_ms)))
                c.stale_since = None
                c.error = None
                c.stats.note(frames[name], frame_age_ms(c.camera, perf), now)
            except (TimeoutError, RuntimeError, ConnectionError, OSError) as exc:
                if c.stale_since is None:
                    c.stale_since = now
                c.error = str(exc)[:200]
                c.stats.ticks += 1
                c.stats.stale_ticks += 1
                stale.append(name)
        return frames, stale

    def reset_stats(self) -> None:
        for c in list(self._cams.values()):
            c.stats = CamStats()

    def stats(self) -> dict[str, dict[str, Any]]:
        """Per camera: backend, configured vs measured fps, frame age, stale ticks, last error."""
        out: dict[str, dict[str, Any]] = {}
        for n, c in list(self._cams.items()):
            st = c.stats
            span = (st.last_t - st.first_t) if st.first_t is not None and st.last_t is not None else 0.0
            measured = round((st.new_frames - 1) / span, 1) if span > 0 and st.new_frames > 1 else None
            out[n] = {
                "backend": camera_backend(c.camera),
                "size": [c.profile.width, c.profile.height],
                "fps_configured": c.profile.fps,
                "fps_measured": measured,
                "age_ms_p50": _p(st.ages_ms, 50),
                "age_ms_p95": _p(st.ages_ms, 95),
                "ticks": st.ticks,
                "stale_ticks": st.stale_ticks,
                "last_error": c.error,
            }
        return out

    def stale_for(self, name: str, now: float | None = None) -> float:
        c = self._cams.get(name)
        if c is None or c.stale_since is None:
            return 0.0
        return (time.monotonic() if now is None else now) - c.stale_since

    def publish(self, fs: FrameSet) -> None:
        with self._latest_lock:
            self._latest = fs

    def latest(self) -> FrameSet | None:
        """Latest FrameSet: the control loop's when it runs, else a fresh idle read."""
        if not self.loop_active and self._cams:
            frames, stale = self.read_latest_all(max_age_ms=1000)
            self._idle_tick += 1
            fs = FrameSet(tick=-1, t=time.monotonic(), frames=frames, stale=stale)
            with self._latest_lock:
                self._latest = fs
            return fs
        with self._latest_lock:
            return self._latest

    def status(self) -> list[dict[str, Any]]:
        out = []
        for n, c in self._cams.items():
            out.append(
                {
                    "name": n,
                    "type": c.profile.type,
                    "streaming": bool(getattr(c.camera, "is_connected", False)) and c.stale_since is None,
                    "width": c.profile.width,
                    "height": c.profile.height,
                    "fps": c.profile.fps,
                    "stale": c.stale_since is not None,
                    "error": c.error,
                }
            )
        return out


# --------------------------------------------------------------------------- preview encoder
class VideoClient:
    """One ``/ws/video`` subscriber. Latest frame wins per camera: video never queues."""

    def __init__(self, loop: asyncio.AbstractEventLoop | None = None) -> None:
        self.loop = loop
        self.cameras: list[str] = []
        self.width = 320
        self.fps = 12.0
        self._slot: dict[str, bytes] = {}
        self._errors: dict[str, str] = {}
        self._lock = threading.Lock()
        self.event = asyncio.Event() if loop else None
        self.next_due = 0.0
        self.last_tick: dict[str, int] = {}
        self.replaced = 0

    def subscribe(self, cameras: list[str], width: int, fps: float) -> None:
        with self._lock:
            self.cameras = list(cameras)
            self.width = max(160, min(640, int(width)))
            self.fps = max(1.0, min(30.0, float(fps)))
            self._slot = {k: v for k, v in self._slot.items() if k in self.cameras}

    def offer(self, cam: str, msg: bytes) -> None:
        with self._lock:
            if cam in self._slot:
                self.replaced += 1
            self._slot[cam] = msg
        self._notify()

    def offer_error(self, cam: str, code: str) -> None:
        with self._lock:
            self._errors[cam] = code
        self._notify()

    def _notify(self) -> None:
        if self.loop is not None and self.event is not None:
            try:
                self.loop.call_soon_threadsafe(self.event.set)
            except RuntimeError:  # loop closed
                pass

    def take(self) -> tuple[dict[str, bytes], dict[str, str]]:
        with self._lock:
            out, self._slot = self._slot, {}
            errs, self._errors = self._errors, {}
            return out, errs


class PreviewEncoder:
    """One thread: resize + JPEG at each client's fps, from the latest FrameSet only."""

    def __init__(self, hub: CameraHub, quality: int = 70, max_fps: float = 30.0) -> None:
        self.hub = hub
        self.quality = quality
        self.max_fps = max_fps
        self.clients: set[VideoClient] = set()
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.encoded = 0
        self.t0 = time.monotonic()

    def add(self, c: VideoClient) -> None:
        with self._lock:
            self.clients.add(c)

    def remove(self, c: VideoClient) -> None:
        with self._lock:
            self.clients.discard(c)

    def start(self) -> None:
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, name="preview-encoder", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
        self._thread = None

    def _run(self) -> None:
        while not self._stop.is_set():
            self.step()
            self._stop.wait(1.0 / self.max_fps)

    def step(self, now: float | None = None) -> int:
        """Encode for every due client. Returns the number of messages offered."""
        now = time.monotonic() if now is None else now
        with self._lock:
            clients = [c for c in self.clients if c.cameras and now >= c.next_due]
        if not clients:
            return 0
        fs = self.hub.latest()
        if fs is None:
            return 0
        cache: dict[tuple[str, int], tuple[bytes, int, int]] = {}
        sent = 0
        for c in clients:
            c.next_due = now + 1.0 / c.fps
            for cam in c.cameras:
                frame = fs.frames.get(cam)
                if frame is None:
                    if cam in fs.stale or cam in self.hub.names:
                        c.offer_error(cam, "camera_stale")
                    continue
                if fs.tick >= 0 and c.last_tick.get(cam) == fs.tick:
                    continue  # nothing new for this client
                key = (cam, c.width)
                if key not in cache:
                    cache[key] = encode_preview(np.asarray(frame), c.width, self.quality)
                    self.encoded += 1
                jpeg, w, h = cache[key]
                src_h, src_w = frame.shape[:2]
                header = {
                    "cam": cam,
                    "tick": fs.tick,
                    "t": round(fs.t - self.t0, 3),
                    "w": w,
                    "h": h,
                    "src_w": int(src_w),
                    "src_h": int(src_h),
                    "policy_input": fs.policy_input,
                    "stale": cam in fs.stale,
                }
                c.last_tick[cam] = fs.tick
                c.offer(cam, pack_frame(header, jpeg))
                sent += 1
        return sent
