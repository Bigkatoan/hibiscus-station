"""Camera detectors (station-programs.md §4 "Camera"): colour rules, ONNX classifiers, the store and
the REST surface, against the mock camera's fake red / blue cube."""

from __future__ import annotations

import base64
import os
import statistics
import time
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from conftest import mock_profile, wait_for

from hibiscus_station.errors import StationError
from hibiscus_station.mock.camera import MockCamera, MockCameraConfig
from hibiscus_station.programs import schemas as ps
from hibiscus_station.programs.detectors import (
    ClassifierDetector,
    ColorDetector,
    DetectorStore,
    annotate,
    build_runtime,
    load_detector,
    roi_box,
)
from hibiscus_station.programs.paths import RobotDataPaths
from hibiscus_station.station import Station

RED = ps.ColorRule(label="red", h_min=170, h_max=10, s_min=120, v_min=80)
BLUE = ps.ColorRule(label="blue", h_min=100, h_max=130, s_min=120, v_min=80)
CENTRE = ps.Roi(x=0.25, y=0.25, w=0.5, h=0.5)


def color_spec(**kw: Any) -> ps.ColorDetectorSpec:
    return ps.ColorDetectorSpec(
        kind="color", camera="wrist", roi=kw.pop("roi", CENTRE), rules=[RED, BLUE], **kw
    )


def scene(color: tuple[int, int, int] | None, *, h: int = 96, w: int = 128, side: int = 40) -> np.ndarray:
    f = np.full((h, w, 3), 60, dtype=np.uint8)
    if color is not None:
        y0, x0 = (h - side) // 2, (w - side) // 2
        f[y0 : y0 + side, x0 : x0 + side] = color
    return f


def cube_frame(color: str | None, **cfg: Any) -> np.ndarray:
    cam = MockCamera(MockCameraConfig(name="t", fps=30, width=cfg.get("w", 128), height=cfg.get("h", 96)))
    cam.show_cube(color)  # type: ignore[arg-type]
    return cam._render(7)


# --------------------------------------------------------------------------- colour rules
@pytest.mark.parametrize(("color", "label"), [("red", "red"), ("blue", "blue"), (None, None)])
def test_color_detector_sees_the_mock_cube(color: str | None, label: str | None) -> None:
    det = ColorDetector(color_spec(), "cubes")
    res = det.evaluate(cube_frame(color), tick=12)
    assert res.label == label
    assert res.detector == "cubes" and res.camera == "wrist" and res.tick == 12
    assert set(res.scores) == {"red", "blue"}
    if label is not None:
        # cube side 0.4*96 = 38 px in a 64x48 ROI -> 38*38 / (64*48)
        assert res.confidence == pytest.approx(38 * 38 / (64 * 48), abs=0.02)
        assert res.scores[label] == res.confidence
        other = "blue" if label == "red" else "red"
        assert res.scores[other] < 0.05  # the noisy background has a few saturated pixels
    else:
        assert res.confidence < 0.05


def test_color_rule_hue_wraps_around_red() -> None:
    # OpenCV hue of pure red is 0, of a pink-red ~174: a 170..10 rule matches both, a 0..10 rule one
    spec = ps.ColorDetectorSpec(
        kind="color",
        camera="c",
        roi=ps.Roi(x=0, y=0, w=1, h=1),
        rules=[ps.ColorRule(label="red", h_min=0, h_max=10, s_min=100, min_fraction=0.5)],
    )
    pink_red = np.full((10, 10, 3), (220, 30, 60), dtype=np.uint8)
    pure_red = np.full((10, 10, 3), (220, 30, 20), dtype=np.uint8)
    assert ColorDetector(spec).evaluate(pink_red).label is None
    assert ColorDetector(spec).evaluate(pure_red).label == "red"
    wrap = spec.model_copy(update={"rules": [spec.rules[0].model_copy(update={"h_min": 170})]})
    assert ColorDetector(wrap).evaluate(pink_red).label == "red"
    assert ColorDetector(wrap).evaluate(pure_red).label == "red"


def test_color_rule_saturation_and_value_bounds() -> None:
    dull = ps.ColorRule(label="red", h_min=170, h_max=10, s_min=200, min_fraction=0.5)
    spec = ps.ColorDetectorSpec(kind="color", camera="c", roi=ps.Roi(x=0, y=0, w=1, h=1), rules=[dull])
    greyish = np.full((8, 8, 3), (150, 110, 110), dtype=np.uint8)
    assert ColorDetector(spec).evaluate(greyish).label is None


def test_roi_restricts_the_search_and_min_fraction_applies() -> None:
    frame = scene((210, 25, 25), side=20)  # small red cube in the middle
    corner = color_spec(roi=ps.Roi(x=0, y=0, w=0.2, h=0.2))
    assert ColorDetector(corner).evaluate(frame).label is None
    strict = color_spec(roi=ps.Roi(x=0, y=0, w=1, h=1))
    strict.rules[0] = RED.model_copy(update={"min_fraction": 0.5})
    res = ColorDetector(strict).evaluate(frame)
    assert res.label is None and res.confidence == pytest.approx(400 / (96 * 128), abs=1e-3)


def test_largest_fraction_wins() -> None:
    f = scene(None)
    f[:, :40] = (210, 25, 25)
    f[:, 40:] = (30, 60, 210)
    spec = color_spec(roi=ps.Roi(x=0, y=0, w=1, h=1))
    assert ColorDetector(spec).evaluate(f).label == "blue"


def test_roi_box_clamps_and_keeps_one_pixel() -> None:
    assert roi_box(ps.Roi(x=1, y=1, w=0.01, h=0.01), 10, 10) == (9, 9, 10, 10)
    assert roi_box(ps.Roi(x=0.5, y=0, w=1, h=1), 10, 20) == (10, 0, 20, 10)
    assert roi_box(None, 4, 6) == (0, 0, 6, 4)


def test_color_detector_is_fast_on_vga() -> None:
    frame = cube_frame("red", w=640, h=480)
    det = ColorDetector(color_spec(roi=ps.Roi(x=0, y=0, w=1, h=1)))
    det.evaluate(frame)
    times = []
    for _ in range(20):
        t0 = time.perf_counter()
        det.evaluate(frame)
        times.append((time.perf_counter() - t0) * 1000)
    assert statistics.median(times) < 25.0  # spec: ~2 ms; generous for a loaded CI box


def test_bad_frames_and_specs_are_refused() -> None:
    det = ColorDetector(color_spec())
    with pytest.raises(StationError) as e:
        det.evaluate(np.zeros((4, 4), dtype=np.uint8))
    assert e.value.code == "camera_unavailable"
    with pytest.raises(StationError) as e:
        ColorDetector(color_spec().model_copy(update={"rules": [RED, RED]}))
    assert e.value.code == "validation_failed"


def test_annotated_preview_is_a_small_jpeg() -> None:
    import cv2

    frame = cube_frame("blue", w=640, h=480)
    spec = color_spec()
    res = ColorDetector(spec).evaluate(frame)
    before = frame.copy()
    jpeg = base64.b64decode(annotate(frame, spec, res))
    img = cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
    assert img.shape == (240, 320, 3)
    assert np.array_equal(frame, before)  # the input frame is never drawn on


# --------------------------------------------------------------------------- ONNX classifiers
def channel_model(n_labels: int = 3, size: int = 32, *, scale: float = 10.0) -> bytes:
    """A tiny ONNX classifier: logits = scale * mean(R, G, B) (labels r, g, b [, extra zeros])."""
    import onnx
    from onnx import TensorProto, helper

    w = np.zeros((3, n_labels), dtype=np.float32)
    for i in range(min(3, n_labels)):
        w[i, i] = scale
    graph = helper.make_graph(
        [
            helper.make_node("ReduceMean", ["x"], ["m"], axes=[2, 3], keepdims=0),
            helper.make_node("MatMul", ["m", "w"], ["logits"]),
        ],
        "channels",
        [helper.make_tensor_value_info("x", TensorProto.FLOAT, [1, 3, size, size])],
        [helper.make_tensor_value_info("logits", TensorProto.FLOAT, [1, n_labels])],
        initializer=[helper.make_tensor("w", TensorProto.FLOAT, w.shape, w.flatten().tolist())],
    )
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 13)])
    model.ir_version = 8
    onnx.checker.check_model(model)
    return model.SerializeToString()


def clf_spec(**kw: Any) -> ps.ClassifierDetectorSpec:
    base: dict[str, Any] = {
        "kind": "classifier",
        "camera": "wrist",
        "labels": ["r", "g", "b"],
        "input_size": 32,
        "mean": [0.0, 0.0, 0.0],
        "std": [1.0, 1.0, 1.0],
        "min_confidence": 0.5,
    }
    return ps.ClassifierDetectorSpec.model_validate({**base, **kw})


def test_classifier_runs_onnx_on_the_cpu() -> None:
    det = ClassifierDetector(clf_spec(roi=CENTRE), channel_model(), "clf")
    red = det.evaluate(cube_frame("red"), tick=3)
    assert red.label == "r" and red.confidence > 0.9 and red.tick == 3
    assert sum(red.scores.values()) == pytest.approx(1.0, abs=1e-5)
    assert det.evaluate(cube_frame("blue")).label == "b"
    x = det.preprocess(cube_frame("red"))
    assert x.shape == (1, 3, 32, 32) and x.dtype == np.float32


def test_classifier_min_confidence_and_none_label() -> None:
    flat = np.full((32, 32, 3), 128, dtype=np.uint8)  # equal channels -> uniform softmax
    det = ClassifierDetector(clf_spec(), channel_model(), "clf")
    res = det.evaluate(flat)
    assert res.label is None and res.confidence == pytest.approx(1 / 3, abs=1e-3)
    nothing = ClassifierDetector(clf_spec(none_label="g"), channel_model(), "clf")
    green = np.full((32, 32, 3), (20, 230, 20), dtype=np.uint8)
    assert nothing.evaluate(green).label is None


def test_classifier_normalisation_uses_mean_and_std() -> None:
    # a mean that cancels the red channel makes a red frame read as "nothing special"
    det = ClassifierDetector(clf_spec(mean=[0.82, 0.0, 0.0], std=[1.0, 1.0, 1.0]), channel_model(), "clf")
    red = np.full((32, 32, 3), (210, 0, 0), dtype=np.uint8)
    assert det.evaluate(red).label is None


@pytest.mark.parametrize(
    ("model", "why"),
    [
        (lambda: channel_model(n_labels=4), "4 scores"),
        (lambda: channel_model(size=64), "input"),
        (lambda: b"not an onnx file", "cannot load"),
    ],
)
def test_classifier_refuses_unusable_models(model: Any, why: str) -> None:
    with pytest.raises(StationError) as e:
        ClassifierDetector(clf_spec(), model(), "clf")
    assert e.value.code == "detector_invalid" and why in e.value.detail


def test_classifier_spec_checks() -> None:
    with pytest.raises(StationError):
        ClassifierDetector(clf_spec(none_label="x"), channel_model())
    with pytest.raises(StationError):
        ClassifierDetector(clf_spec(std=[1.0, 0.0, 1.0]), channel_model())
    with pytest.raises(StationError) as e:
        build_runtime(clf_spec(), detector_id="clf")
    assert e.value.code == "detector_invalid"


# --------------------------------------------------------------------------- store
@pytest.fixture
def store(tmp_path: Path) -> DetectorStore:
    paths = RobotDataPaths(tmp_path, "desk")
    paths.ensure()
    return DetectorStore(paths)


def test_store_crud_and_private_files(store: DetectorStore) -> None:
    assert store.all() == []
    det = store.put("cubes", ps.DetectorInput(name="Cubes", spec=color_spec()))
    assert det.robot == "desk" and det.labels == ["red", "blue"] and det.model_file is None
    path = store.paths.detector_json("cubes")
    assert oct(os.stat(path).st_mode & 0o777) == "0o600"
    assert store.get("cubes") == det and [d.id for d in store.all()] == ["cubes"]
    again = store.put("cubes", ps.DetectorInput(name="Cubes 2", spec=color_spec()))
    assert again.created_at == det.created_at and again.name == "Cubes 2"
    rt = store.runtime("cubes")
    assert store.runtime("cubes") is rt  # cached
    store.put("cubes", ps.DetectorInput(name="Cubes 3", spec=color_spec()))
    assert store.runtime("cubes") is not rt  # reloaded after a change
    store.delete("cubes")
    assert store.all() == []
    for call in (lambda: store.get("cubes"), lambda: store.delete("cubes"), lambda: store.runtime("cubes")):
        with pytest.raises(StationError) as e:
            call()
        assert e.value.code == "not_found"
    with pytest.raises(StationError):
        store.get("../x")


def test_store_skips_broken_files(store: DetectorStore) -> None:
    store.put("cubes", ps.DetectorInput(name="Cubes", spec=color_spec()))
    store.paths.detector_json("broken").write_text("{nope")
    assert [d.id for d in store.all()] == ["cubes"]
    with pytest.raises(StationError) as e:
        store.get("broken")
    assert e.value.code == "detector_invalid"


def test_store_classifier_model_lifecycle(store: DetectorStore) -> None:
    store.put("clf", ps.DetectorInput(name="Clf", spec=clf_spec(none_label="g")))
    assert store.get("clf").labels == ["r", "b"]  # the none label is never returned
    with pytest.raises(StationError) as e:
        store.runtime("clf")
    assert e.value.code == "detector_invalid"  # no model yet
    with pytest.raises(StationError) as e:
        store.set_model("clf", channel_model(n_labels=2))
    assert e.value.code == "detector_invalid"
    assert not store.paths.detector_model("clf").exists()
    det = store.set_model("clf", channel_model())
    assert det.model_file == "clf.onnx" and det.model_sha256 and len(det.model_sha256) == 64
    assert oct(os.stat(store.paths.detector_model("clf")).st_mode & 0o777) == "0o600"
    assert store.runtime("clf").evaluate(cube_frame("red")).label == "r"
    # compatible edit (same label count and input size) keeps the model
    kept = store.put("clf", ps.DetectorInput(name="Clf", spec=clf_spec(labels=["x", "y", "z"])))
    assert kept.model_file == "clf.onnx"
    # incompatible edit drops it
    dropped = store.put("clf", ps.DetectorInput(name="Clf", spec=clf_spec(labels=["x", "y"])))
    assert dropped.model_file is None and not store.paths.detector_model("clf").exists()
    store.put("cubes", ps.DetectorInput(name="Cubes", spec=color_spec()))
    with pytest.raises(StationError) as e:
        store.set_model("cubes", channel_model())
    assert e.value.code == "validation_failed"


def test_load_detector_needs_the_model_file(store: DetectorStore) -> None:
    store.put("clf", ps.DetectorInput(name="Clf", spec=clf_spec()))
    det = store.set_model("clf", channel_model())
    store.paths.detector_model("clf").unlink()
    with pytest.raises(StationError) as e:
        load_detector(det, store.paths.detectors)
    assert e.value.code == "detector_invalid"


# --------------------------------------------------------------------------- REST + mock camera
CUBES = {
    "name": "Cubes",
    "spec": {
        "kind": "color",
        "camera": "wrist",
        "roi": {"x": 0.25, "y": 0.25, "w": 0.5, "h": 0.5},
        "rules": [
            {"label": "red", "h_min": 170, "h_max": 10, "s_min": 120, "v_min": 80},
            {"label": "blue", "h_min": 100, "h_max": 130, "s_min": 120, "v_min": 80},
        ],
    },
}


@pytest.fixture
def cam_client(client: Any, station: Station) -> Any:
    station.profiles.put(mock_profile())
    r = client.post("/api/v1/robots/desk/connect")
    assert r.status_code == 200, r.text
    wait_for(lambda: station.hub.latest() is not None and "wrist" in station.hub.latest().frames)  # type: ignore[union-attr]
    return client


def test_detectors_rest_crud(client: Any, station: Station) -> None:
    station.profiles.put(mock_profile())
    assert client.get("/api/v1/detectors").json() == {"detectors": []}
    r = client.put("/api/v1/detectors/cubes", json=CUBES)
    assert r.status_code == 200, r.text
    det = ps.Detector.model_validate(r.json())
    assert det.id == "cubes" and det.labels == ["red", "blue"]
    assert client.get("/api/v1/detectors/cubes").json() == r.json()
    assert [d["id"] for d in client.get("/api/v1/detectors").json()["detectors"]] == ["cubes"]
    bad = {**CUBES, "spec": {**CUBES["spec"], "rules": [CUBES["spec"]["rules"][0]] * 2}}  # type: ignore[index]
    assert client.put("/api/v1/detectors/cubes", json=bad).json()["code"] == "validation_failed"
    assert client.delete("/api/v1/detectors/cubes").status_code == 204
    assert client.get("/api/v1/detectors/cubes").status_code == 404
    assert client.delete("/api/v1/detectors/cubes").status_code == 404


def test_detector_test_on_the_live_mock_frame(cam_client: Any, station: Station) -> None:
    c = cam_client
    c.put("/api/v1/detectors/cubes", json=CUBES)
    for color in ("red", "blue"):
        assert c.post("/api/v1/mock/inject", json={"camera": "wrist", "cube": color}).status_code == 200
        time.sleep(0.1)
        r = c.post("/api/v1/detectors/cubes/test", json={})
        assert r.status_code == 200, r.text
        res = ps.DetectorResult.model_validate(r.json())
        assert res.label == color and res.camera == "wrist" and res.detector == "cubes"
        assert res.annotated_jpeg_b64 and base64.b64decode(res.annotated_jpeg_b64)[:2] == b"\xff\xd8"
    c.post("/api/v1/mock/inject", json={"camera": "wrist", "cube": "none"})
    time.sleep(0.1)
    r = c.post("/api/v1/detectors/cubes/test", json={"annotate": False})
    assert r.json()["label"] in (None, "red")  # the moving hibiscus block may pass through the ROI
    assert r.json()["annotated_jpeg_b64"] is None
    # an unsaved spec on another id
    blue_only = {**CUBES["spec"], "rules": [CUBES["spec"]["rules"][1]]}  # type: ignore[index]
    c.post("/api/v1/mock/inject", json={"camera": "wrist", "cube": "blue"})
    time.sleep(0.1)
    r = c.post("/api/v1/detectors/draft/test", json={"spec": blue_only})
    assert r.status_code == 200 and r.json()["label"] == "blue" and r.json()["detector"] == "draft"
    # unknown camera / unknown detector
    r = c.post("/api/v1/detectors/cubes/test", json={"camera": "nope"})
    assert r.status_code == 409 and r.json()["code"] == "camera_unavailable"
    assert c.post("/api/v1/detectors/ghost/test", json={}).status_code == 404


def test_mock_cube_injection_is_checked(cam_client: Any) -> None:
    r = cam_client.post("/api/v1/mock/inject", json={"camera": "ghost", "cube": "red"})
    assert r.status_code == 404


def test_classifier_model_upload_over_rest(cam_client: Any, station: Station) -> None:
    c = cam_client
    spec = clf_spec(roi=CENTRE).model_dump(mode="json")
    assert c.put("/api/v1/detectors/clf", json={"name": "Clf", "spec": spec}).status_code == 200
    r = c.post("/api/v1/detectors/clf/test", json={})
    assert r.status_code == 422 and r.json()["code"] == "detector_invalid"
    r = c.post(
        "/api/v1/detectors/clf/model", files={"file": ("m.onnx", b"garbage", "application/octet-stream")}
    )
    assert r.status_code == 422 and r.json()["code"] == "detector_invalid"
    r = c.post("/api/v1/detectors/clf/model", files={"file": ("m.onnx", b"", "application/octet-stream")})
    assert r.status_code == 422
    r = c.post(
        "/api/v1/detectors/clf/model", files={"file": ("m.onnx", channel_model(), "application/octet-stream")}
    )
    assert r.status_code == 200, r.text
    assert r.json()["model_file"] == "clf.onnx"
    c.post("/api/v1/mock/inject", json={"camera": "wrist", "cube": "blue"})
    time.sleep(0.1)
    r = c.post("/api/v1/detectors/clf/test", json={"annotate": True})
    assert r.status_code == 200 and r.json()["label"] == "b"
    # an unsaved classifier spec reuses this id's uploaded model
    r = c.post(
        "/api/v1/detectors/clf/test",
        json={"spec": clf_spec(roi=CENTRE, labels=["x", "y", "z"]).model_dump(mode="json")},
    )
    assert r.status_code == 200 and r.json()["label"] == "z"
