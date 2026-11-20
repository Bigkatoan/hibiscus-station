"""Station error codes (spec §5.1), rendered as RFC 9457 Problems by the API layer."""

from __future__ import annotations

from typing import Any

STATUS = {
    "unauthenticated": 401,
    "forbidden": 403,
    "forbidden_host": 403,
    "csrf": 403,
    "not_found": 404,
    "validation_failed": 422,
    "busy": 409,
    "port_busy": 409,
    "motor_hot": 409,
    "not_connected": 409,
    "not_calibrated": 409,
    "camera_unavailable": 409,
    "estopped": 409,
    "leader_far": 409,
    "model_not_loaded": 409,
    "model_incompatible": 422,
    "dataset_not_finalized": 409,
    "episode_saving": 409,
    "video_missing": 404,
    "video_unavailable": 422,
    "dataset_exists": 409,
    "dataset_incompatible": 422,
    "not_paired": 409,
    "server_url_invalid": 422,
    "server_url_file_share": 422,
    "server_not_hibiscus": 422,
    "server_url_insecure": 422,
    "server_unauthorized": 422,
    "token_format_invalid": 422,
    "token_missing_scope": 422,
    "workspace_required": 422,
    "server_error": 502,
    "hardware_timeout": 504,
    "bus_error": 502,
    "device_lost": 503,
    "demo_profile": 409,
    "internal_error": 500,
    # station-programs.md
    "not_implemented": 501,
    "program_invalid": 422,
    "needs_check": 409,
    "dry_run_required": 409,
    "fast_replay_not_allowed": 409,
    "detector_invalid": 422,
}

TITLES = {
    "unauthenticated": "Authentication required",
    "forbidden_host": "Host not allowed",
    "csrf": "Missing X-Station header",
    "not_found": "Not found",
    "validation_failed": "Validation failed",
    "busy": "Station is busy",
    "port_busy": "Serial port is in use",
    "motor_hot": "A motor is too hot",
    "not_connected": "Robot not connected",
    "not_calibrated": "Arm not calibrated",
    "camera_unavailable": "Camera unavailable",
    "estopped": "E-stop is latched",
    "leader_far": "Leader is far from the follower",
    "model_not_loaded": "Model not loaded",
    "model_incompatible": "Model is not compatible with this robot",
    "dataset_not_finalized": "Dataset is not finalized",
    "episode_saving": "This dataset is still being recorded and saved",
    "video_missing": "This camera has no video for this episode",
    "video_unavailable": "This camera's video cannot be read",
    "not_paired": "Not paired with a Hibiscus server",
    "server_url_invalid": "The server address is not an http(s) address",
    "server_url_file_share": "This is a file-sharing link, not a Hibiscus server address",
    "server_not_hibiscus": "This address did not answer as a Hibiscus server",
    "server_url_insecure": "Use an https:// address for a server on the internet",
    "server_unauthorized": "The server rejected this token",
    "token_format_invalid": "This is not a Hibiscus personal access token",
    "token_missing_scope": "The token lacks a scope Station needs",
    "workspace_required": "Choose a workspace",
    "server_error": "Hibiscus server error",
    "hardware_timeout": "Hardware did not answer in time",
    "bus_error": "A motor did not answer on the serial bus",
    "device_lost": "The serial device was lost (unplugged, reset or taken by another program)",
    "demo_profile": "This profile drives simulated arms",
    "internal_error": "Internal error",
    "not_implemented": "Not implemented yet",
    "program_invalid": "Program has errors",
    "needs_check": "Calibration changed: check this trajectory first",
    "dry_run_required": "Dry run required",
    "fast_replay_not_allowed": "Speed above 100 % is not allowed for this robot",
    "detector_invalid": "Detector is not usable",
}


class StationError(Exception):
    def __init__(
        self,
        code: str,
        detail: str = "",
        *,
        params: dict[str, Any] | None = None,
        errors: list[dict[str, Any]] | None = None,
        status: int | None = None,
    ) -> None:
        super().__init__(detail or code)
        self.code = code
        self.detail = detail or TITLES.get(code, code)
        self.params = params or {}
        self.errors = errors
        self.status = status or STATUS.get(code, 400)

    def problem(self, request_id: str = "") -> dict[str, Any]:
        body: dict[str, Any] = {
            "type": f"https://hibiscus.dev/problems/station/{self.code}",
            "title": TITLES.get(self.code, self.code.replace("_", " ").capitalize()),
            "status": self.status,
            "code": self.code,
            "detail": self.detail,
            "request_id": request_id,
        }
        if self.params:
            body["params"] = self.params
        if self.errors is not None:
            body["errors"] = self.errors
        return body
