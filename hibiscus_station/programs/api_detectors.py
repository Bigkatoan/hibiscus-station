"""REST: camera detectors and external signals (station-programs.md §4, §7). Owner: team B."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Request, Response, UploadFile

from hibiscus_station.errors import StationError
from hibiscus_station.programs import schemas as ps
from hibiscus_station.programs.api_common import PROBLEM, item_id, signal_name
from hibiscus_station.programs.detectors import MAX_MODEL_BYTES, annotate, build_runtime

if TYPE_CHECKING:
    from hibiscus_station.programs.interfaces import Frame
    from hibiscus_station.station import Station


def _station(request: Request) -> Station:
    st: Station = request.app.state.station
    return st


def live_frame(st: Station, camera: str) -> tuple[Frame, int]:
    """The latest frame of ``camera`` (the control loop's while it runs) and its tick."""
    fs = st.hub.latest()
    if fs is None or camera not in fs.frames or camera in fs.stale:
        known = sorted(fs.frames) if fs is not None else []
        raise StationError(
            "camera_unavailable",
            f"no live frame from camera {camera}",
            params={"camera": camera, "cameras": known},
        )
    return fs.frames[camera], fs.tick


def run_detector_test(st: Station, detector_id: str, body: ps.DetectorTestRequest) -> ps.DetectorResult:
    store = st.programs.detectors()
    if body.spec is None:
        det = store.get(detector_id)
        spec: ps.DetectorSpec = det.spec
        runtime = store.runtime(detector_id)
    else:
        spec = body.spec
        model = None
        if isinstance(spec, ps.ClassifierDetectorSpec):
            det = store.get(detector_id)  # an unsaved classifier spec still needs this id's model
            if det.model_file is not None:
                model = st.programs.robot_paths().detectors / det.model_file
        runtime = build_runtime(spec, detector_id=detector_id, model=model)
    camera = body.camera or spec.camera
    frame, tick = live_frame(st, camera)
    try:
        res = runtime.evaluate(frame, tick=tick)
    finally:
        if body.spec is not None:
            runtime.close()
    res = res.model_copy(update={"camera": camera, "detector": detector_id})
    if body.annotate:
        res = res.model_copy(update={"annotated_jpeg_b64": annotate(frame, spec, res)})
    return res


def build_detectors_router() -> APIRouter:
    r = APIRouter(prefix="/api/v1", tags=["detectors"], responses=PROBLEM)

    @r.get("/detectors")
    def list_detectors(request: Request) -> ps.Detectors:
        """Detectors of the active robot profile."""
        return ps.Detectors(detectors=_station(request).programs.detectors().all())

    @r.get("/detectors/{detector_id}")
    def get_detector(request: Request, detector_id: str = item_id()) -> ps.Detector:
        return _station(request).programs.detectors().get(detector_id)

    @r.put("/detectors/{detector_id}")
    def put_detector(request: Request, body: ps.DetectorInput, detector_id: str = item_id()) -> ps.Detector:
        """Create or replace. A classifier keeps its uploaded model while ``labels`` stay compatible."""
        return _station(request).programs.detectors().put(detector_id, body)

    @r.delete("/detectors/{detector_id}", status_code=204)
    def delete_detector(request: Request, detector_id: str = item_id()) -> Response:
        _station(request).programs.detectors().delete(detector_id)
        return Response(status_code=204)

    @r.post("/detectors/{detector_id}/test")
    def test_detector(
        request: Request, body: ps.DetectorTestRequest, detector_id: str = item_id()
    ) -> ps.DetectorResult:
        """Evaluate on the latest live frame (any state; never touches the bus)."""
        return run_detector_test(_station(request), detector_id, body)

    @r.post("/detectors/{detector_id}/model")
    def upload_model(request: Request, file: UploadFile, detector_id: str = item_id()) -> ps.Detector:
        """Multipart ``file``: the ONNX classifier (≤ 200 MiB; checked by loading it)."""
        data = file.file.read(MAX_MODEL_BYTES + 1)
        if len(data) > MAX_MODEL_BYTES:
            raise StationError("validation_failed", "model is larger than 200 MiB")
        if not data:
            raise StationError("validation_failed", "empty model file")
        return _station(request).programs.detectors().set_model(detector_id, data)

    # ------------------------------------------------------------------ signals
    @r.get("/signals", tags=["signals"])
    def list_signals(request: Request) -> ps.Signals:
        return ps.Signals(signals=_station(request).programs.signals.all())

    @r.post("/signals/{name}", tags=["signals"])
    def post_signal(request: Request, body: ps.SignalIn, name: str = signal_name()) -> ps.Signal:
        """External signal in (127.0.0.1 + token + ``X-Station: 1`` like every other call)."""
        return _station(request).programs.signals.set(name, body.value, "http")

    return r
