"""Camera detectors (station-programs.md §4 "Camera"): colour-in-region rules and ONNX classifiers.

``load_detector(det, root)`` turns a stored :class:`Detector` into a :class:`DetectorRuntime`:

* **colour** — the ROI is converted to OpenCV HSV and every rule is an ``inRange`` mask (a rule with
  ``h_min > h_max`` wraps around red). A rule's score is the share of ROI pixels it matches; the label
  is the rule with the largest score that reaches its ``min_fraction``.
* **classifier** — the ROI (or the whole frame) is resized to ``input_size`` (INTER_AREA), scaled to
  0..1, normalised with ``mean``/``std`` and fed as ``1x3xSxS`` float32 RGB to onnxruntime on the CPU.
  The output is ``1 x len(labels)`` logits; scores are their softmax. A top score below
  ``min_confidence``, or the ``none_label``, gives ``label: null``.

``confidence`` is always the top score (also when ``label`` is null, so a UI can show "almost").

Detectors run in the program runner or an API worker thread, never in the hardware-owner thread, and
never keep a reference to the frame they were given. :class:`DetectorStore` keeps the per-robot
``detectors/<id>.json`` (+ ``<id>.onnx``) and caches one loaded runtime per detector version.
"""

from __future__ import annotations

import base64
import datetime as dt
import hashlib
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
import numpy.typing as npt
from pydantic import ValidationError

from hibiscus_station.errors import StationError
from hibiscus_station.programs.paths import RobotDataPaths
from hibiscus_station.programs.schemas import (
    ClassifierDetectorSpec,
    ColorDetectorSpec,
    ColorRule,
    Detector,
    DetectorInput,
    DetectorResult,
    DetectorSpec,
    Roi,
)
from hibiscus_station.settings import write_private

if TYPE_CHECKING:
    from hibiscus_station.programs.interfaces import DetectorRuntime, Frame

#: ``POST /detectors/{id}/model`` limit (spec: ≤ 200 MiB).
MAX_MODEL_BYTES = 200 * 1024 * 1024
ANNOTATE_WIDTH = 320


def _now() -> str:
    return dt.datetime.now(dt.UTC).isoformat()


def _frame(frame: Any) -> npt.NDArray[np.uint8]:
    arr = np.asarray(frame)
    if arr.ndim != 3 or arr.shape[2] != 3 or arr.dtype != np.uint8 or arr.shape[0] < 1 or arr.shape[1] < 1:
        raise StationError(
            "camera_unavailable", "frame is not an HxWx3 uint8 image", params={"shape": list(arr.shape)}
        )
    return arr


def roi_box(roi: Roi | None, h: int, w: int) -> tuple[int, int, int, int]:
    """``(x0, y0, x1, y1)`` in pixels, clamped to the frame and at least one pixel wide/high."""
    if roi is None:
        return 0, 0, w, h
    x0 = min(w - 1, max(0, round(roi.x * w)))
    y0 = min(h - 1, max(0, round(roi.y * h)))
    x1 = min(w, max(x0 + 1, round((roi.x + roi.w) * w)))
    y1 = min(h, max(y0 + 1, round((roi.y + roi.h) * h)))
    return x0, y0, x1, y1


def rule_mask(hsv: npt.NDArray[np.uint8], rule: ColorRule) -> npt.NDArray[np.bool_]:
    """Pixels of an OpenCV HSV image (H 0-179) inside ``rule`` (hue wraps when ``h_min > h_max``)."""
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    sv = (s >= rule.s_min) & (s <= rule.s_max) & (v >= rule.v_min) & (v <= rule.v_max)
    if rule.h_min <= rule.h_max:
        hue = (h >= rule.h_min) & (h <= rule.h_max)
    else:
        hue = (h >= rule.h_min) | (h <= rule.h_max)
    out: npt.NDArray[np.bool_] = hue & sv
    return out


def _check_spec(spec: DetectorSpec) -> None:
    labels = [r.label for r in spec.rules] if isinstance(spec, ColorDetectorSpec) else spec.labels
    if len(set(labels)) != len(labels):
        raise StationError("validation_failed", "labels must be unique", params={"labels": labels})
    if isinstance(spec, ClassifierDetectorSpec):
        if spec.none_label is not None and spec.none_label not in spec.labels:
            raise StationError(
                "validation_failed",
                "none_label must be one of labels",
                params={"none_label": spec.none_label},
            )
        if any(s <= 0 for s in spec.std):
            raise StationError("validation_failed", "std must be > 0", params={"std": spec.std})


def spec_labels(spec: DetectorSpec) -> list[str]:
    """Every label the detector can return (``Detector.labels``)."""
    if isinstance(spec, ColorDetectorSpec):
        return [r.label for r in spec.rules]
    return [lb for lb in spec.labels if lb != spec.none_label]


# --------------------------------------------------------------------------- colour
class ColorDetector:
    def __init__(self, spec: ColorDetectorSpec, detector_id: str | None = None) -> None:
        _check_spec(spec)
        self.spec = spec
        self.detector_id = detector_id

    def evaluate(self, frame: Frame, *, tick: int = -1, camera: str | None = None) -> DetectorResult:
        import cv2

        t0 = time.perf_counter()
        img = _frame(frame)
        x0, y0, x1, y1 = roi_box(self.spec.roi, img.shape[0], img.shape[1])
        hsv = np.asarray(
            cv2.cvtColor(np.ascontiguousarray(img[y0:y1, x0:x1]), cv2.COLOR_RGB2HSV), dtype=np.uint8
        )
        total = float(hsv.shape[0] * hsv.shape[1])
        scores = {r.label: float(np.count_nonzero(rule_mask(hsv, r))) / total for r in self.spec.rules}
        label: str | None = None
        best = 0.0
        for r in self.spec.rules:
            sc = scores[r.label]
            if sc >= r.min_fraction and (label is None or sc > best):
                label, best = r.label, sc
        top = max(scores.values()) if scores else 0.0
        return DetectorResult(
            detector=self.detector_id,
            camera=camera or self.spec.camera,
            label=label,
            confidence=round(min(1.0, best if label is not None else top), 6),
            scores={k: round(v, 6) for k, v in scores.items()},
            ms=round((time.perf_counter() - t0) * 1000, 3),
            tick=tick,
            annotated_jpeg_b64=None,
        )

    def close(self) -> None:
        return None


# --------------------------------------------------------------------------- ONNX classifier
def _softmax(x: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
    z = x - np.max(x)
    e = np.exp(z)
    out: npt.NDArray[np.float64] = e / np.sum(e)
    return out


class ClassifierDetector:
    """onnxruntime on the CPU; one session per loaded model (``run`` is thread-safe)."""

    def __init__(
        self, spec: ClassifierDetectorSpec, model: Path | bytes, detector_id: str | None = None
    ) -> None:
        _check_spec(spec)
        self.spec = spec
        self.detector_id = detector_id
        try:
            import onnxruntime as ort

            opts = ort.SessionOptions()
            opts.intra_op_num_threads = 2
            opts.inter_op_num_threads = 1
            opts.log_severity_level = 3
            src = str(model) if isinstance(model, Path) else model
            self._session: Any = ort.InferenceSession(
                src, sess_options=opts, providers=["CPUExecutionProvider"]
            )
        except Exception as exc:
            raise StationError(
                "detector_invalid",
                f"cannot load the ONNX model: {exc}"[:300],
                params={"detector": detector_id},
            ) from exc
        inputs = self._session.get_inputs()
        outputs = self._session.get_outputs()
        if len(inputs) != 1 or not outputs:
            raise StationError(
                "detector_invalid", "the model needs exactly one input", params={"inputs": len(inputs)}
            )
        self._input = str(inputs[0].name)
        self._output = str(outputs[0].name)
        shape = list(inputs[0].shape)
        want = [1, 3, spec.input_size, spec.input_size]
        if len(shape) != 4 or any(isinstance(d, int) and d != w for d, w in zip(shape, want, strict=True)):
            raise StationError(
                "detector_invalid",
                f"model input is {shape}, expected {want}",
                params={"input_shape": [str(d) for d in shape]},
            )
        # one dry inference: catches a wrong output size before a program relies on it
        self._infer(np.zeros((1, 3, spec.input_size, spec.input_size), dtype=np.float32))

    def _infer(self, x: npt.NDArray[np.float32]) -> npt.NDArray[np.float64]:
        session = self._session
        if session is None:
            raise StationError("detector_invalid", "detector was reloaded, evaluate again")
        try:
            out = session.run([self._output], {self._input: x})[0]
        except Exception as exc:
            raise StationError("detector_invalid", f"inference failed: {exc}"[:300]) from exc
        logits = np.asarray(out, dtype=np.float64).reshape(-1)
        if logits.shape[0] != len(self.spec.labels):
            raise StationError(
                "detector_invalid",
                f"model returns {logits.shape[0]} scores for {len(self.spec.labels)} labels",
                params={"outputs": int(logits.shape[0]), "labels": len(self.spec.labels)},
            )
        return logits

    def preprocess(self, frame: Frame) -> npt.NDArray[np.float32]:
        import cv2

        img = _frame(frame)
        x0, y0, x1, y1 = roi_box(self.spec.roi, img.shape[0], img.shape[1])
        crop = np.ascontiguousarray(img[y0:y1, x0:x1])
        s = self.spec.input_size
        resized = cv2.resize(crop, (s, s), interpolation=cv2.INTER_AREA)
        x = resized.astype(np.float32) / np.float32(255.0)
        x = (x - np.asarray(self.spec.mean, dtype=np.float32)) / np.asarray(self.spec.std, dtype=np.float32)
        out: npt.NDArray[np.float32] = np.ascontiguousarray(
            np.transpose(x, (2, 0, 1))[None], dtype=np.float32
        )
        return out

    def evaluate(self, frame: Frame, *, tick: int = -1, camera: str | None = None) -> DetectorResult:
        t0 = time.perf_counter()
        probs = _softmax(self._infer(self.preprocess(frame)))
        scores = {lb: float(p) for lb, p in zip(self.spec.labels, probs, strict=True)}
        i = int(np.argmax(probs))
        top = float(probs[i])
        label: str | None = self.spec.labels[i]
        if top < self.spec.min_confidence or label == self.spec.none_label:
            label = None
        return DetectorResult(
            detector=self.detector_id,
            camera=camera or self.spec.camera,
            label=label,
            confidence=round(min(1.0, max(0.0, top)), 6),
            scores={k: round(v, 6) for k, v in scores.items()},
            ms=round((time.perf_counter() - t0) * 1000, 3),
            tick=tick,
            annotated_jpeg_b64=None,
        )

    def close(self) -> None:
        self._session = None


def build_runtime(
    spec: DetectorSpec, *, detector_id: str | None = None, model: Path | bytes | None = None
) -> ColorDetector | ClassifierDetector:
    if isinstance(spec, ColorDetectorSpec):
        return ColorDetector(spec, detector_id)
    if model is None:
        raise StationError(
            "detector_invalid", "upload the ONNX model first", params={"detector": detector_id}
        )
    return ClassifierDetector(spec, model, detector_id)


def load_detector(det: Detector, root: Path) -> DetectorRuntime:
    """``root`` = the robot's ``detectors/`` dir (where ``det.model_file`` lives)."""
    model = None
    if isinstance(det.spec, ClassifierDetectorSpec) and det.model_file is not None:
        model = root / det.model_file
        if not model.is_file():
            raise StationError("detector_invalid", "the model file is missing", params={"detector": det.id})
    return build_runtime(det.spec, detector_id=det.id, model=model)


# --------------------------------------------------------------------------- preview
def annotate(frame: Frame, spec: DetectorSpec, result: DetectorResult, *, quality: int = 80) -> str:
    """JPEG (≤ 320 px wide, base64) of ``frame`` with the ROI, the matched pixels and the label."""
    import cv2

    img = _frame(frame).copy()
    h, w = img.shape[:2]
    x0, y0, x1, y1 = roi_box(spec.roi, h, w)
    if isinstance(spec, ColorDetectorSpec) and result.label is not None:
        rule = next(r for r in spec.rules if r.label == result.label)
        roi = np.ascontiguousarray(img[y0:y1, x0:x1])
        mask = rule_mask(np.asarray(cv2.cvtColor(roi, cv2.COLOR_RGB2HSV), dtype=np.uint8), rule)
        tint = roi.copy()
        tint[mask] = (255, 255, 255)
        img[y0:y1, x0:x1] = cv2.addWeighted(roi, 0.5, tint, 0.5, 0)
    scale = min(1.0, ANNOTATE_WIDTH / w)
    if scale < 1.0:
        size = (max(1, round(w * scale)), max(1, round(h * scale)))
        img = np.asarray(cv2.resize(img, size, interpolation=cv2.INTER_AREA), dtype=np.uint8)
        x0, y0, x1, y1 = (round(v * scale) for v in (x0, y0, x1, y1))
    color = (255, 236, 64) if result.label is not None else (200, 200, 200)
    cv2.rectangle(img, (x0, y0), (max(x0, x1 - 1), max(y0, y1 - 1)), color, 1)
    text = f"{result.label or '-'} {result.confidence:.2f}"
    cv2.putText(img, text, (x0 + 2, min(img.shape[0] - 2, y0 + 12)), cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)
    ok, buf = cv2.imencode(".jpg", cv2.cvtColor(img, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:  # pragma: no cover
        raise StationError("internal_error", "jpeg encode failed")
    return base64.b64encode(buf.tobytes()).decode("ascii")


# --------------------------------------------------------------------------- store
class DetectorStore:
    """``robots/<robot_id>/detectors/``: one JSON per detector (+ ONNX for classifiers). Thread-safe."""

    def __init__(self, paths: RobotDataPaths) -> None:
        self.paths = paths
        self._lock = threading.RLock()
        self._cache: dict[str, tuple[str, DetectorRuntime]] = {}

    @property
    def robot_id(self) -> str:
        return self.paths.robot_id

    def _read(self, path: Path) -> Detector:
        try:
            return Detector.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValidationError, ValueError) as exc:
            raise StationError(
                "detector_invalid", f"unreadable detector file {path.name}", params={"file": path.name}
            ) from exc

    def all(self) -> list[Detector]:
        with self._lock:
            d = self.paths.detectors
            if not d.is_dir():
                return []
            out = []
            for p in sorted(d.glob("*.json")):
                try:
                    out.append(self._read(p))
                except StationError:
                    continue  # a broken file never hides the others
            return out

    def get(self, detector_id: str) -> Detector:
        path = self.paths.detector_json(detector_id)
        with self._lock:
            if not path.is_file():
                raise StationError(
                    "not_found", f"no detector {detector_id}", params={"detector": detector_id}
                )
            return self._read(path)

    def _write(self, det: Detector) -> None:
        self.paths.detectors.mkdir(parents=True, exist_ok=True)
        write_private(self.paths.detector_json(det.id), det.model_dump_json(indent=2) + "\n")

    def put(self, detector_id: str, body: DetectorInput) -> Detector:
        _check_spec(body.spec)
        path = self.paths.detector_json(detector_id)
        with self._lock:
            old = self._read(path) if path.is_file() else None
            now = _now()
            model_file: str | None = None
            model_sha: str | None = None
            if (
                old is not None
                and isinstance(old.spec, ClassifierDetectorSpec)
                and isinstance(body.spec, ClassifierDetectorSpec)
                and len(old.spec.labels) == len(body.spec.labels)
                and old.spec.input_size == body.spec.input_size
            ):
                model_file, model_sha = old.model_file, old.model_sha256  # still compatible
            elif old is not None and old.model_file is not None:
                self.paths.detector_model(detector_id).unlink(missing_ok=True)
            det = Detector(
                id=detector_id,
                robot=self.robot_id,
                name=body.name,
                spec=body.spec,
                created_at=old.created_at if old else now,
                updated_at=now,
                model_file=model_file,
                model_sha256=model_sha,
                labels=spec_labels(body.spec),
            )
            self._write(det)
            self._evict(detector_id)
            return det

    def delete(self, detector_id: str) -> None:
        path = self.paths.detector_json(detector_id)
        with self._lock:
            if not path.is_file():
                raise StationError(
                    "not_found", f"no detector {detector_id}", params={"detector": detector_id}
                )
            path.unlink()
            self.paths.detector_model(detector_id).unlink(missing_ok=True)
            self._evict(detector_id)

    def set_model(self, detector_id: str, onnx: bytes) -> Detector:
        if len(onnx) > MAX_MODEL_BYTES:
            raise StationError(
                "validation_failed", "model is larger than 200 MiB", params={"bytes": len(onnx)}
            )
        with self._lock:
            det = self.get(detector_id)
            if not isinstance(det.spec, ClassifierDetectorSpec):
                raise StationError(
                    "validation_failed",
                    "only classifier detectors take a model",
                    params={"kind": det.spec.kind},
                )
            ClassifierDetector(det.spec, onnx, detector_id).close()  # detector_invalid if unusable
            target = self.paths.detector_model(detector_id)
            write_private(target, onnx)
            det = det.model_copy(
                update={
                    "model_file": target.name,
                    "model_sha256": hashlib.sha256(onnx).hexdigest(),
                    "updated_at": _now(),
                }
            )
            self._write(det)
            self._evict(detector_id)
            return det

    def runtime(self, detector_id: str) -> DetectorRuntime:
        with self._lock:
            det = self.get(detector_id)
            key = f"{det.updated_at}|{det.model_sha256}"
            hit = self._cache.get(detector_id)
            if hit is not None and hit[0] == key:
                return hit[1]
            rt = load_detector(det, self.paths.detectors)
            self._evict(detector_id)
            self._cache[detector_id] = (key, rt)
            return rt

    def _evict(self, detector_id: str) -> None:
        hit = self._cache.pop(detector_id, None)
        if hit is not None:
            hit[1].close()

    def close(self) -> None:
        with self._lock:
            for did in list(self._cache):
                self._evict(did)
