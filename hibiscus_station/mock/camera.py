"""MockCamera: a lerobot ``Camera`` that renders a little pixel scene with its frame counter drawn in.

The counter is drawn as 16 black/white blocks across the top band of the image, robust to JPEG and
video compression, so tests can assert *which* frame reached the policy, the dataset and the preview
(:func:`decode_counter`).

For the camera detectors (station-programs.md §4) a test or the ``--mock`` demo can put a solid
red or blue "cube" in the middle of the scene with :meth:`MockCamera.show_cube`; while a cube is
shown the moving hibiscus block is hidden, so a colour rule sees exactly one coloured object.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any, Literal

import numpy as np
from lerobot.cameras import Camera, CameraConfig
from numpy.typing import NDArray

BITS = 16
CubeColor = Literal["red", "blue", "green", "yellow"]
#: RGB of the fake cubes: saturated, bright, well inside one OpenCV hue band each.
CUBE_RGB: dict[str, tuple[int, int, int]] = {
    "red": (210, 25, 25),
    "blue": (30, 60, 210),
    "green": (30, 190, 50),
    "yellow": (225, 205, 30),
}


@CameraConfig.register_subclass("hibiscus_mock")
@dataclass(kw_only=True)
class MockCameraConfig(CameraConfig):  # type: ignore[misc]
    name: str = "mock"
    seed: int = 0


def encode_counter(frame: NDArray[np.uint8], counter: int) -> None:
    h, w = frame.shape[:2]
    band = max(4, h // 6)
    bw = w // BITS
    for bit in range(BITS):
        val = 255 if (counter >> bit) & 1 else 0
        frame[:band, bit * bw : (bit + 1) * bw, :] = val


def decode_counter(frame: NDArray[Any]) -> int:
    """Inverse of :func:`encode_counter`; accepts HWC uint8 or CHW float [0, 1]."""
    arr = np.asarray(frame)
    if arr.ndim == 3 and arr.shape[0] == 3 and arr.shape[2] != 3:
        arr = np.transpose(arr, (1, 2, 0))
    if arr.dtype != np.uint8:
        arr = (np.clip(arr, 0, 1) * 255).astype(np.uint8)
    h, w = arr.shape[:2]
    band = max(4, h // 6)
    bw = w // BITS
    out = 0
    for bit in range(BITS):
        block = arr[1 : band - 1, bit * bw + 1 : (bit + 1) * bw - 1, :]
        if float(block.mean()) > 127:
            out |= 1 << bit
    return out


class MockCamera(Camera):  # type: ignore[misc]
    """Frames are produced by a background thread at ``fps`` (like lerobot's read thread)."""

    def __init__(self, config: MockCameraConfig) -> None:
        super().__init__(config)
        self.config = config
        self.fps = config.fps or 30
        self.width = config.width or 128
        self.height = config.height or 96
        self._lock = threading.Lock()
        self._frame: NDArray[np.uint8] | None = None
        self._frame_t = 0.0
        self._new = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.counter = 0
        self.stalled = False
        self.fail_connect = False
        self._connected = False
        self.cube: CubeColor | None = None
        self.cube_size = 0.4  # side, as a share of the frame height
        rng = np.random.default_rng(config.seed)
        self._bg = rng.integers(40, 90, size=(self.height, self.width, 3), dtype=np.uint8)

    # --------------------------------------------------------------- fault injection
    def stall(self, stalled: bool = True) -> None:
        self.stalled = stalled

    def show_cube(self, color: CubeColor | None, size: float = 0.4) -> None:
        """Put a solid cube of ``color`` in the centre of the scene (``None`` removes it)."""
        if color is not None and color not in CUBE_RGB:
            raise ValueError(f"unknown cube colour {color!r}")
        self.cube_size = max(0.05, min(1.0, float(size)))
        self.cube = color

    # --------------------------------------------------------------- Camera API
    @property
    def is_connected(self) -> bool:
        return self._connected

    @staticmethod
    def find_cameras() -> list[dict[str, Any]]:
        return [
            {
                "type": "mock",
                "id": f"mock://camera{i}",
                "name": f"Mock camera {i}",
                "default_stream_profile": {"width": 128, "height": 96, "fps": 30, "format": "RGB"},
            }
            for i in range(2)
        ]

    def _render(self, n: int) -> NDArray[np.uint8]:
        f = self._bg.copy()
        h, w = self.height, self.width
        cube = self.cube
        if cube is None:
            size = max(6, h // 6)
            x = int((n * 2) % max(1, w - size))
            y = h // 2
            f[y : y + size, x : x + size] = (220, 60, 90)  # a hibiscus-red block moving right
        else:
            side = max(4, int(h * self.cube_size))
            x0, y0 = (w - side) // 2, (h - side) // 2
            f[y0 : y0 + side, x0 : x0 + side] = CUBE_RGB[cube]
        encode_counter(f, n)
        return f

    def _run(self) -> None:
        period = 1.0 / float(self.fps)
        nxt = time.perf_counter()
        while not self._stop.is_set():
            if not self.stalled:
                frame = self._render(self.counter)
                with self._lock:
                    self._frame = frame
                    self._frame_t = time.perf_counter()
                    self.counter += 1
                self._new.set()
            nxt += period
            delay = nxt - time.perf_counter()
            if delay > 0:
                time.sleep(delay)
            else:
                nxt = time.perf_counter()

    def connect(self, warmup: bool = True) -> None:
        if self.fail_connect:
            raise ConnectionError(f"{self.config.name}: cannot open mock camera")
        self._stop.clear()
        self._connected = True
        self._thread = threading.Thread(target=self._run, name=f"mockcam-{self.config.name}", daemon=True)
        self._thread.start()
        if warmup:
            self._new.wait(1.0)

    def read(self) -> NDArray[np.uint8]:
        return self.async_read()

    def async_read(self, timeout_ms: float = 200) -> NDArray[np.uint8]:
        if not self._connected:
            raise ConnectionError("not connected")
        self._new.clear()
        if not self._new.wait(timeout_ms / 1000):
            raise TimeoutError("no new frame")
        with self._lock:
            if self._frame is None:
                raise TimeoutError("no frame yet")
            return self._frame

    def read_latest(self, max_age_ms: int = 500) -> NDArray[np.uint8]:
        if not self._connected:
            raise ConnectionError("not connected")
        with self._lock:
            if self._frame is None:
                raise RuntimeError("no frame yet")
            age_ms = (time.perf_counter() - self._frame_t) * 1000
            if age_ms > max_age_ms:
                raise TimeoutError(f"frame is {age_ms:.0f} ms old")
            return self._frame

    def disconnect(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
        self._thread = None
        self._connected = False
