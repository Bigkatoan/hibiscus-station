"""Stateful fake Hibiscus API mounted on respx, derived from and checked against the server contract.

Vendored from the Hibiscus repository (``cli/tests/fake_server.py`` at tag v0.1.1, AGPL-3.0, same
author) together with the contract snapshot in ``tests/contract/hibiscus-v0.1.1/``: Station talks to
a Hibiscus server only through the pinned ``hibiscus`` CLI package, and these tests check that
conversation against the API version that CLI was released with. Refresh both when the CLI pin moves.


Every request is matched to an OpenAPI operation (unknown method/path -> test failure), JSON
request bodies and required headers are validated against the contract, and every JSON response the
fake produces is validated against the documented response schema for its status code. Upload
parts are hashed and stored on disk exactly like the real API streams them to S3, so tests can
check the re-assembled object byte for byte.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import uuid
import zipfile
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import unquote

import httpx
import respx
from openapi_contract import ContractError, OpenApiContract

BASE = "https://hibiscus.test/api/v1"
TOKEN = "hbp_AbCd1234_" + "x" * 43
MIB = 1024 * 1024

_CONTRACT: OpenApiContract | None = None


def contract() -> OpenApiContract:
    global _CONTRACT
    if _CONTRACT is None:
        _CONTRACT = OpenApiContract()
    return _CONTRACT


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def uid() -> str:
    return str(uuid.uuid4())


@dataclass
class Fault:
    """Injected failure for one request matching (operation_id, part_number)."""

    operation_id: str
    kind: str  # connect | read_timeout | status:<code> | lost_response | corrupt | drop_stream:<bytes>
    part_number: int | None = None
    times: int = 1
    retry_after: int | None = None


@dataclass
class SseConnection:
    """What the fake streams on one /events connection after replaying persisted events."""

    live: list[tuple[str, dict[str, Any], bool]] = field(default_factory=list)  # (event, data, persist)
    drop_after: int | None = None  # raise ReadError after this many live messages
    status: int = 200
    end: bool = False


@dataclass
class Recorded:
    method: str
    path: str
    operation_id: str
    headers: dict[str, str]
    body_size: int


class FakeHibiscus:
    def __init__(self, tmp: Path, *, token: str = TOKEN, server_part_size: int | None = None) -> None:
        self.tmp = tmp
        self.token = token
        self.server_part_size = server_part_size
        self.c = contract()
        self.workspace_id = uid()
        self.user = {"id": uid(), "display_name": "Collector"}
        self.datasets: dict[str, dict[str, Any]] = {}
        self.versions: dict[str, dict[str, Any]] = {}
        self.uploads: dict[str, dict[str, Any]] = {}
        self.part_dir = tmp / "fake-s3"
        self.part_dir.mkdir(parents=True, exist_ok=True)
        self.idem: dict[str, dict[str, Any]] = {}
        self.runs: dict[str, dict[str, Any]] = {}
        self.run_events: dict[str, list[dict[str, Any]]] = {}
        self.run_logs: dict[str, bytes] = {}
        self.sse_scripts: dict[str, list[SseConnection]] = {}
        self.models: dict[str, dict[str, Any]] = {}
        self.model_zip: dict[str, bytes] = {}
        self.model_manifest: dict[str, dict[str, Any]] = {}
        self.model_files: dict[str, dict[str, bytes]] = {}
        self.faults: list[Fault] = []
        self.requests: list[Recorded] = []
        self.policies = self._load_policies()
        self.preflight_ok = True
        self._handlers: dict[str, Callable[[httpx.Request, dict[str, str]], httpx.Response]] = {
            name[3:]: getattr(self, name) for name in dir(self) if name.startswith("op_")
        }

    # ------------------------------------------------------------------ mounting
    def mount(self, router: respx.MockRouter) -> None:
        router.route(url__startswith=BASE).mock(side_effect=self.dispatch)

    def dispatch(self, request: httpx.Request) -> httpx.Response:
        path = request.url.raw_path.decode().split("?")[0]
        if not path.startswith("/api/v1"):
            raise ContractError(f"request outside base path: {path}")
        rel = path[len("/api/v1") :]
        op, params = self.c.match(request.method, rel)
        self.requests.append(
            Recorded(request.method, rel, op.operation_id, dict(request.headers), len(request.content))
        )
        self._check_request(op, request)
        fault = self._take_fault(op.operation_id, params)
        if fault is not None:
            resp = self._apply_fault(fault, request, op, params)
            if resp is not None:
                return resp
        if request.headers.get("authorization") != f"Bearer {self.token}" and op.operation_id != "healthz":
            return self._problem(op, 401, "unauthenticated", "missing or invalid token")
        handler = self._handlers.get(op.operation_id)
        if handler is None:
            raise ContractError(f"fake has no handler for {op.operation_id}")
        resp = handler(request, params)
        self._check_response(op, resp)
        return resp

    def _check_request(self, op: Any, request: httpx.Request) -> None:
        for p in self.c.header_params(op):
            if p.get("required") and p["name"].lower() not in request.headers:
                raise ContractError(f"{op.operation_id}: required header {p['name']} missing")
            value = request.headers.get(p["name"])
            schema = p.get("schema", {})
            if value is not None and "pattern" in schema and not re.match(schema["pattern"], value):
                raise ContractError(f"{op.operation_id}: header {p['name']}={value!r} !~ {schema['pattern']}")
        ctype = request.headers.get("content-type", "").split(";")[0].strip()
        if request.content and ctype == "application/json":
            ptr = self.c.request_body_pointer(op, "application/json")
            if ptr is None:
                raise ContractError(f"{op.operation_id} takes no body")
            self.c.validate(ptr, json.loads(request.content), f"{op.operation_id} request")

    def _check_response(self, op: Any, resp: httpx.Response) -> None:
        ctype = resp.headers.get("content-type", "").split(";")[0].strip()
        documented = str(resp.status_code) in self.c.resolve(op.pointer)["responses"]
        if not documented and (resp.status_code >= 500 or resp.status_code == 429):
            return  # proxy / Cloudflare / global rate-limit responses can hit any operation
        ptr = self.c.response_pointer(op, resp.status_code, ctype or "application/json") if ctype else None
        if ptr is not None and ctype in ("application/json", "application/problem+json"):
            self.c.validate(ptr, json.loads(resp.content), f"{op.operation_id} {resp.status_code} response")

    def _take_fault(self, operation_id: str, params: dict[str, str]) -> Fault | None:
        for f in self.faults:
            if f.operation_id != operation_id or f.times <= 0:
                continue
            if f.part_number is not None and params.get("part_number") != str(f.part_number):
                continue
            f.times -= 1
            return f
        return None

    def _apply_fault(
        self, f: Fault, request: httpx.Request, op: Any, params: dict[str, str]
    ) -> httpx.Response | None:
        if f.kind == "connect":
            raise httpx.ConnectError("injected connect failure", request=request)
        if f.kind == "read_timeout":
            raise httpx.ReadTimeout("injected read timeout", request=request)
        if f.kind.startswith("status:"):
            status = int(f.kind.split(":")[1])
            headers = {"Retry-After": str(f.retry_after)} if f.retry_after else {}
            if status in (429,):
                resp = self._problem(op, status, "rate_limited", "slow down", headers=headers)
                return resp
            return httpx.Response(
                status, text="<html>bad gateway</html>", headers={"content-type": "text/html"}
            )
        if f.kind == "lost_response":
            handler = self._handlers[op.operation_id]
            handler(request, params)  # server stored the part, client never sees the answer
            raise httpx.RemoteProtocolError("injected: connection closed before response", request=request)
        if f.kind == "corrupt":
            body = bytearray(request.content)
            body[0] ^= 0xFF
            bad = httpx.Request(request.method, request.url, headers=request.headers, content=bytes(body))
            return self._handlers[op.operation_id](bad, params)
        return None

    # ------------------------------------------------------------------ helpers
    def _json(self, status: int, body: Any, headers: dict[str, str] | None = None) -> httpx.Response:
        return httpx.Response(
            status, json=body, headers={"X-Request-Id": "req-" + uid()[:8], **(headers or {})}
        )

    def _problem(
        self, op: Any, status: int, code: str, detail: str, headers: dict[str, str] | None = None, **ext: Any
    ) -> httpx.Response:
        body = {
            "type": f"https://hibiscus.example.com/problems/{code}",
            "title": code.replace("_", " "),
            "status": status,
            "code": code,
            "detail": detail,
            "request_id": "req-" + uid()[:8],
            **ext,
        }
        resp = httpx.Response(
            status,
            content=json.dumps(body).encode(),
            headers={"content-type": "application/problem+json", **(headers or {})},
        )
        ptr = self.c.response_pointer(op, status, "application/problem+json")
        if ptr:
            self.c.validate(ptr, body, f"{op.operation_id} {status} problem")
        return resp

    def _op(self, operation_id: str) -> Any:
        return next(o for o in self.c.operations if o.operation_id == operation_id)

    def _load_policies(self) -> dict[str, dict[str, Any]]:
        root = Path(__file__).resolve().parent / "contract" / "hibiscus-v0.1.1" / "policy-schemas"
        train = json.loads((root / "train.json").read_text())
        presets = json.loads((root / "presets.json").read_text())["presets"]
        out: dict[str, dict[str, Any]] = {}
        for p in ("act", "diffusion"):
            out[p] = {
                "type": p,
                "display_name": p.upper(),
                "trainable": True,
                "onnx": "full" if p == "act" else "split",
                "onnx_reason_key": None,
                "requires_peft": False,
                "requires_reward": False,
                "requires_language": False,
                "gpu_support": {"cuda0": "supported", "cuda1": "supported"},
                "schema_etag": "etag-" + p,
                "experimental": False,
                "policy_schema": json.loads((root / f"{p}.json").read_text()),
                "train_schema": train,
                "presets": [
                    {
                        k: v
                        for k, v in pr.items()
                        if k in ("id", "label_key", "train", "policy", "requires_init_from")
                    }
                    for pr in presets
                ],
            }
        return out

    # ------------------------------------------------------------------ fixtures
    def add_dataset(self, name: str, *, versions: int = 1, status: str = "ready") -> dict[str, Any]:
        ds_id = uid()
        ds = {
            "id": ds_id,
            "workspace_id": self.workspace_id,
            "name": name,
            "slug": name.lower().replace("_", "-")[:40],
            "description": "",
            "created_by": self.user,
            "version_count": 0,
            "latest_version": None,
            "created_at": now(),
            "updated_at": now(),
        }
        self.datasets[ds_id] = ds
        for _ in range(versions):
            self._new_version(ds, status=status)
        return ds

    def _new_version(
        self, ds: dict[str, Any], *, status: str = "pending", size: int | None = None
    ) -> dict[str, Any]:
        ds["version_count"] += 1
        v = {
            "id": uid(),
            "dataset_id": ds["id"],
            "version": ds["version_count"],
            "status": status,
            "source": "upload",
            "total_episodes": 20,
            "total_frames": 11277,
            "fps": 30,
            "size_bytes": size or 148148220,
            "created_at": now(),
            "content_hash": None,
            "codebase_version": "v3.0",
            "robot_type": "so_follower",
            "camera_keys": ["observation.images.wrist_cam"],
            "features": None,
            "state_dim": 6,
            "action_dim": 6,
            "joint_names": ["shoulder_pan.pos"],
            "tasks": ["pick and place"],
            "validation_summary": {"result": "passed", "errors": 0, "warnings": 0}
            if status == "ready"
            else None,
            "error_code": None,
            "ready_at": now() if status == "ready" else None,
        }
        self.versions[v["id"]] = v
        ds["latest_version"] = self._version_summary(v)
        ds["updated_at"] = now()
        return v

    @staticmethod
    def _version_summary(v: dict[str, Any]) -> dict[str, Any]:
        keys = (
            "id",
            "dataset_id",
            "version",
            "status",
            "source",
            "total_episodes",
            "total_frames",
            "fps",
            "size_bytes",
            "created_at",
        )
        return {k: v[k] for k in keys}

    def add_run(self, number: int = 42, status: str = "running", log: bytes = b"") -> dict[str, Any]:
        ds = next(iter(self.datasets.values()), None) or self.add_dataset("so101_picknplace")
        ver = self.versions[ds["latest_version"]["id"]]
        run = self._run_obj(number, ds, ver, "act", {"policy": {}, "train": {"steps": 300}}, status)
        self.runs[run["id"]] = run
        self.run_events[run["id"]] = []
        self.run_logs[run["id"]] = log
        return run

    def _run_obj(
        self,
        number: int,
        ds: dict[str, Any],
        ver: dict[str, Any],
        policy: str,
        config: dict[str, Any],
        status: str,
    ) -> dict[str, Any]:
        return {
            "id": uid(),
            "workspace_id": self.workspace_id,
            "number": number,
            "name": f"{ds['name']}-{policy}-{number}",
            "status": status,
            "policy_type": policy,
            "preset": None,
            "dataset_version_id": ver["id"],
            "dataset": {"id": ds["id"], "name": ds["name"], "version": ver["version"]},
            "config": config,
            "progress": {"current_step": 0, "total_steps": int(config.get("train", {}).get("steps", 100000))},
            "latest_metrics": {"loss": 0.5},
            "gpu_id": None,
            "requested_gpu": "auto",
            "priority": 0,
            "attempt": 0,
            "created_by": self.user,
            "created_at": now(),
            "updated_at": now(),
        }

    def persist_event(self, run_id: str, event: str, data: dict[str, Any]) -> int:
        evs = self.run_events[run_id]
        seq = len(evs) + 1
        evs.append({"seq": seq, "event": event, "data": data})
        return seq

    def add_model(
        self,
        files: dict[str, bytes],
        *,
        bundle_name: str = "so101_picknplace_act-r42-step300",
        tamper: str | None = None,
    ) -> dict[str, Any]:
        model_id = uid()
        manifest = {
            "schema_version": "1",
            "bundle_name": bundle_name,
            "files": [
                {"path": p, "size": len(b), "sha256": hashlib.sha256(b).hexdigest()}
                for p, b in sorted(files.items())
            ],
        }
        stored = dict(files)
        if tamper:
            stored[tamper] = stored[tamper] + b"tampered"
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(f"{bundle_name}/", "")
            for p, b in sorted(stored.items()):
                zi = zipfile.ZipInfo(f"{bundle_name}/{p}")
                zi.external_attr = (0o100755 if p.endswith(".sh") else 0o100644) << 16
                zf.writestr(
                    zi,
                    b,
                    compress_type=zipfile.ZIP_STORED if p.endswith(".safetensors") else zipfile.ZIP_DEFLATED,
                )
            zf.writestr(f"{bundle_name}/MANIFEST.json", json.dumps(manifest, indent=2))
        data = buf.getvalue()
        run = next(iter(self.runs.values()), None) or self.add_run(status="succeeded")
        model = {
            "id": model_id,
            "workspace_id": self.workspace_id,
            "name": bundle_name.replace("-r42", "-42"),
            "policy_type": "act",
            "run_id": run["id"],
            "run_number": run["number"],
            "step": 300,
            "status": "ready",
            "verified": True,
            "onnx_status": "passed",
            "bundle_size_bytes": len(data),
            "bundle_sha256": hashlib.sha256(data).hexdigest(),
            "created_at": now(),
        }
        self.models[model_id] = model
        self.model_zip[model_id] = data
        self.model_manifest[model_id] = manifest
        self.model_files[model_id] = {**stored, "MANIFEST.json": json.dumps(manifest).encode()}
        return model

    def assembled(self, upload_id: str) -> Path:
        return self.part_dir / f"{upload_id}.object"

    def puts(self, upload_id: str | None = None) -> list[Recorded]:
        return [
            r
            for r in self.requests
            if r.operation_id == "uploadPart" and (upload_id is None or f"/uploads/{upload_id}/" in r.path)
        ]

    # ------------------------------------------------------------------ auth
    def op_getMe(self, req: httpx.Request, p: dict[str, str]) -> httpx.Response:
        return self._json(
            200,
            {
                "user": {
                    "id": self.user["id"],
                    "email": "collector@example.com",
                    "display_name": "Collector",
                    "locale": "vi",
                    "email_verified": True,
                    "mfa_enabled": False,
                    "is_platform_admin": False,
                    "created_at": now(),
                },
                "memberships": [
                    {
                        "workspace_id": self.workspace_id,
                        "workspace_slug": "lab",
                        "workspace_name": "Lab",
                        "role": "member",
                    }
                ],
                "auth_method": "pat",
                "session_id": None,
                "mfa_verified": False,
                "mfa_enrollment_required": False,
                "token": {
                    "id": uid(),
                    "name": "collect-pc",
                    "prefix": "AbCd1234",
                    "workspace_id": self.workspace_id,
                    "scopes": ["datasets:write", "runs:write", "models:read"],
                    "created_at": now(),
                    "expires_at": None,
                    "last_used_at": None,
                    "last_used_ip": None,
                    "revoked_at": None,
                },
            },
        )

    # ------------------------------------------------------------------ datasets
    def op_listDatasets(self, req: httpx.Request, p: dict[str, str]) -> httpx.Response:
        q = (req.url.params.get("q") or "").lower()
        items = [d for d in self.datasets.values() if q in d["name"].lower()]
        return self._json(200, {"items": items, "next_cursor": None})

    def op_getDataset(self, req: httpx.Request, p: dict[str, str]) -> httpx.Response:
        ds = self.datasets.get(p["dataset_id"])
        if ds is None:
            return self._problem(self._op("getDataset"), 404, "not_found", "no such dataset")
        return self._json(200, ds)

    def op_listDatasetVersions(self, req: httpx.Request, p: dict[str, str]) -> httpx.Response:
        items = sorted(
            (self._version_summary(v) for v in self.versions.values() if v["dataset_id"] == p["dataset_id"]),
            key=lambda v: -int(v["version"]),
        )
        return self._json(200, {"items": items, "next_cursor": None})

    def op_getDatasetVersion(self, req: httpx.Request, p: dict[str, str]) -> httpx.Response:
        v = self.versions.get(p["version_id"])
        if v is None:
            return self._problem(self._op("getDatasetVersion"), 404, "not_found", "no such version")
        return self._json(200, v)

    # ------------------------------------------------------------------ uploads
    def _session_view(self, s: dict[str, Any]) -> dict[str, Any]:
        parts = [
            {"part_number": n, "size": info["size"], "sha256": info["sha256"], "received_at": info["at"]}
            for n, info in sorted(s["parts"].items())
        ]
        view = {k: v for k, v in s.items() if k != "parts"}
        view["parts"] = parts
        view["bytes_received"] = sum(pp["size"] for pp in parts)
        return view

    def op_initUpload(self, req: httpx.Request, p: dict[str, str]) -> httpx.Response:
        body = json.loads(req.content)
        key = req.headers.get("idempotency-key")
        if key and key in self.idem:
            return self._json(201, self._session_view(self.uploads[self.idem[key]["id"]]))
        for s in self.uploads.values():
            if s["status"] == "active" and s["sha256"] == body["sha256"] and s["size"] == body["size"]:
                return self._json(200, self._session_view(s))
        name = body.get("new_dataset_name")
        if name and any(d["name"] == name for d in self.datasets.values()):
            return self._problem(self._op("initUpload"), 409, "dataset_name_taken", f"{name} exists")
        part_size = int(body.get("part_size", 64 * MIB))
        part_size = max(5 * MIB, min(64 * MIB, self.server_part_size or part_size))
        sid = uid()
        s = {
            "id": sid,
            "workspace_id": body["workspace_id"],
            "dataset_id": body.get("dataset_id"),
            "new_dataset_name": body.get("new_dataset_name"),
            "filename": body["filename"],
            "size": body["size"],
            "sha256": body["sha256"],
            "archive_format": body.get("archive_format") or "tar",
            "part_size": part_size,
            "part_count": -(-int(body["size"]) // part_size),
            "parts": {},
            "status": "active",
            "error_code": None,
            "expires_at": now(),
            "created_at": now(),
            "completed_at": None,
            "dataset_version_id": None,
        }
        self.uploads[sid] = s
        if key:
            self.idem[key] = {"id": sid}
        return self._json(201, self._session_view(s))

    def op_getUpload(self, req: httpx.Request, p: dict[str, str]) -> httpx.Response:
        s = self.uploads.get(p["upload_id"])
        if s is None:
            return self._problem(self._op("getUpload"), 404, "not_found", "no such upload")
        return self._json(200, self._session_view(s))

    def op_abortUpload(self, req: httpx.Request, p: dict[str, str]) -> httpx.Response:
        s = self.uploads.get(p["upload_id"])
        if s is None:
            return self._problem(self._op("abortUpload"), 404, "not_found", "no such upload")
        s["status"] = "aborted"
        return httpx.Response(204)

    def op_uploadPart(self, req: httpx.Request, p: dict[str, str]) -> httpx.Response:
        op = self._op("uploadPart")
        s = self.uploads.get(p["upload_id"])
        if s is None:
            return self._problem(op, 404, "not_found", "no such upload")
        if s["status"] != "active":
            return self._problem(op, 409, "upload_not_active", f"session is {s['status']}")
        n = int(p["part_number"])
        body = req.content
        if int(req.headers["content-length"]) != len(body):
            raise ContractError("Content-Length does not match the body")
        if len(body) > 64 * MIB:
            return self._problem(op, 413, "payload_too_large", "part > 64 MiB")
        if n > s["part_count"]:
            return self._problem(op, 422, "upload_part_out_of_range", "part number too high")
        expected = (
            s["part_size"] if n < s["part_count"] else s["size"] - (s["part_count"] - 1) * s["part_size"]
        )
        if len(body) != expected:
            return self._problem(op, 422, "upload_part_size_invalid", f"expected {expected} bytes")
        digest = hashlib.sha256(body).hexdigest()
        if digest != req.headers["x-content-sha256"]:
            return self._problem(op, 422, "upload_part_checksum_mismatch", "sha256 mismatch")
        (self.part_dir / f"{s['id']}.{n:05d}").write_bytes(body)
        s["parts"][n] = {"size": len(body), "sha256": digest, "at": now()}
        return self._json(200, {"part_number": n, "size": len(body), "sha256": digest, "received_at": now()})

    def op_completeUpload(self, req: httpx.Request, p: dict[str, str]) -> httpx.Response:
        op = self._op("completeUpload")
        s = self.uploads.get(p["upload_id"])
        if s is None:
            return self._problem(op, 404, "not_found", "no such upload")
        if s["status"] == "completed":
            return self._json(202, s["completed_body"])
        missing = [n for n in range(1, s["part_count"] + 1) if n not in s["parts"]]
        if missing:
            return self._problem(op, 409, "upload_incomplete", "parts missing", missing_parts=missing)
        whole = hashlib.sha256()
        with self.assembled(s["id"]).open("wb") as out:
            for n in range(1, s["part_count"] + 1):
                chunk = (self.part_dir / f"{s['id']}.{n:05d}").read_bytes()
                whole.update(chunk)
                out.write(chunk)
                (self.part_dir / f"{s['id']}.{n:05d}").unlink()
        s["assembled_sha256"] = whole.hexdigest()
        if s["dataset_id"]:
            ds = self.datasets[s["dataset_id"]]
        else:
            ds = self.add_dataset(s["new_dataset_name"], versions=0)
        v = self._new_version(ds, size=s["size"])
        if s["assembled_sha256"] != s["sha256"]:
            v["status"] = "failed"
            v["error_code"] = "upload_checksum_mismatch"
            ds["latest_version"] = self._version_summary(v)
        s["status"] = "completed"
        s["completed_at"] = now()
        s["dataset_version_id"] = v["id"]
        job = {
            "id": uid(),
            "workspace_id": self.workspace_id,
            "kind": "validate_dataset",
            "status": "queued",
            "progress": 0,
            "created_at": now(),
            "dataset_version_id": v["id"],
        }
        body = {
            "upload": self._session_view(s),
            "dataset": ds,
            "version": self._version_summary(v),
            "job": job,
        }
        s["completed_body"] = body
        return self._json(202, body)

    # ------------------------------------------------------------------ policies / runs
    def op_listPolicies(self, req: httpx.Request, p: dict[str, str]) -> httpx.Response:
        items = [
            {k: v for k, v in pol.items() if k not in ("policy_schema", "train_schema", "presets")}
            for pol in self.policies.values()
        ]
        return self._json(200, {"lerobot_version": "0.7.1", "items": items})

    def op_getPolicy(self, req: httpx.Request, p: dict[str, str]) -> httpx.Response:
        pol = self.policies.get(p["policy_type"])
        if pol is None:
            return self._problem(self._op("getPolicy"), 404, "policy_unknown", "unknown policy")
        return self._json(200, pol, headers={"ETag": pol["schema_etag"]})

    def _resolve_run_body(self, body: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]] | None:
        ver = self.versions.get(body["dataset_version_id"])
        if ver is None:
            return None
        return self.datasets[ver["dataset_id"]], ver

    def op_preflightRun(self, req: httpx.Request, p: dict[str, str]) -> httpx.Response:
        body = json.loads(req.content)
        r = self._resolve_run_body(body)
        if r is None:
            return self._problem(self._op("preflightRun"), 404, "not_found", "dataset version not found")
        self.last_preflight = body
        checks = [{"id": "dataset_ready", "severity": "info", "code": "ok", "message": "dataset ready"}]
        if not self.preflight_ok:
            checks.append(
                {"id": "vram", "severity": "error", "code": "gpu_insufficient_vram", "message": "needs 30 GB"}
            )
        return self._json(
            200,
            {
                "ok": self.preflight_ok,
                "checks": checks,
                "resolved": {
                    "gpu_id": "cuda0",
                    "mixed_precision": "bf16",
                    "config": body["config"],
                    "heldout_episodes": [3, 11],
                    "train_episodes": [0, 1, 2],
                    "lerobot_args": ["--steps=300"],
                },
                "estimate": {
                    "source": "heuristic",
                    "gpu_id": "cuda0",
                    "peak_vram_mb": 1800,
                    "sec_per_step": 0.11,
                    "total_duration_s": 33.0,
                },
            },
        )

    def op_createRun(self, req: httpx.Request, p: dict[str, str]) -> httpx.Response:
        body = json.loads(req.content)
        key = req.headers.get("idempotency-key")
        if key and key in self.idem:
            return self._json(201, self.runs[self.idem[key]["id"]])
        r = self._resolve_run_body(body)
        if r is None:
            return self._problem(self._op("createRun"), 404, "not_found", "dataset version not found")
        ds, ver = r
        run = self._run_obj(len(self.runs) + 1, ds, ver, body["policy_type"], body["config"], "queued")
        run["preset"] = body.get("preset")
        self.runs[run["id"]] = run
        self.run_events[run["id"]] = []
        self.run_logs[run["id"]] = b""
        self.last_create = body
        if key:
            self.idem[key] = {"id": run["id"]}
        return self._json(201, run, headers={"Location": f"/api/v1/runs/{run['id']}"})

    def op_listRuns(self, req: httpx.Request, p: dict[str, str]) -> httpx.Response:
        items = sorted(self.runs.values(), key=lambda r: -int(r["number"]))
        st = req.url.params.get("status")
        if st:
            wanted = set(st.split(","))
            items = [r for r in items if r["status"] in wanted]
        return self._json(200, {"items": items, "next_cursor": None})

    def op_getRun(self, req: httpx.Request, p: dict[str, str]) -> httpx.Response:
        run = self.runs.get(p["run_id"])
        if run is None:
            return self._problem(self._op("getRun"), 404, "not_found", "no such run")
        return self._json(200, run)

    def op_getRunLogs(self, req: httpx.Request, p: dict[str, str]) -> httpx.Response:
        log = self.run_logs.get(p["run_id"])
        if log is None:
            return self._problem(self._op("getRunLogs"), 404, "not_found", "no such run")
        rng = req.headers.get("range")
        if not rng:
            return httpx.Response(200, content=log, headers={"content-type": "text/plain"})
        spec = rng.removeprefix("bytes=")
        start_s, _, end_s = spec.partition("-")
        start = int(start_s)
        end = int(end_s) if end_s else len(log) - 1
        if start >= len(log):
            return self._problem(self._op("getRunLogs"), 416, "range_not_satisfiable", "past end")
        end = min(end, len(log) - 1)
        return httpx.Response(
            206,
            content=log[start : end + 1],
            headers={"content-type": "text/plain", "Content-Range": f"bytes {start}-{end}/{len(log)}"},
        )

    def op_streamRunEvents(self, req: httpx.Request, p: dict[str, str]) -> httpx.Response:
        run_id = p["run_id"]
        if run_id not in self.runs:
            return self._problem(self._op("streamRunEvents"), 404, "not_found", "no such run")
        last = req.headers.get("last-event-id") or req.url.params.get("after_seq")
        after = int(last) if last else 0
        script = self.sse_scripts.get(run_id) or []
        conn = script.pop(0) if script else SseConnection(end=True)
        if conn.status != 200:
            return httpx.Response(conn.status, text="upstream error", headers={"content-type": "text/plain"})
        replay = [e for e in self.run_events[run_id] if e["seq"] > after]

        def frames() -> Iterator[bytes]:
            yield b"retry: 3000\n\n"
            for e in replay:
                yield self._frame(e["event"], e["data"], e["seq"])
            sent = 0
            for event, data, persist in conn.live:
                if conn.drop_after is not None and sent >= conn.drop_after:
                    raise httpx.ReadError("injected: stream dropped")
                seq = self.persist_event(run_id, event, data) if persist else None
                yield self._frame(event, data, seq)
                sent += 1
            if conn.drop_after is not None and sent >= conn.drop_after:
                raise httpx.ReadError("injected: stream dropped")
            if conn.end:
                yield self._frame("end", {"kind": "end", "final_status": self.runs[run_id]["status"]}, None)

        return httpx.Response(
            200,
            stream=_IterStream(frames()),
            headers={
                "content-type": "text/event-stream",
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    @staticmethod
    def _frame(event: str, data: dict[str, Any], seq: int | None) -> bytes:
        head = f"id: {seq}\n" if seq is not None else ""
        return f"{head}event: {event}\ndata: {json.dumps(data)}\n\n".encode()

    # ------------------------------------------------------------------ models
    def op_listModels(self, req: httpx.Request, p: dict[str, str]) -> httpx.Response:
        q = (req.url.params.get("q") or "").lower()
        items = [m for m in self.models.values() if q in m["name"].lower()]
        return self._json(200, {"items": items, "next_cursor": None})

    def op_getModel(self, req: httpx.Request, p: dict[str, str]) -> httpx.Response:
        m = self.models.get(p["model_id"])
        if m is None:
            return self._problem(self._op("getModel"), 404, "not_found", "no such model")
        return self._json(200, m)

    def op_listModelFiles(self, req: httpx.Request, p: dict[str, str]) -> httpx.Response:
        m = self.model_manifest.get(p["model_id"])
        if m is None:
            return self._problem(self._op("listModelFiles"), 404, "not_found", "no such model")
        return self._json(200, m)

    def _ranged(
        self, req: httpx.Request, data: bytes, etag: str, ctype: str, drop_at: int | None
    ) -> httpx.Response:
        rng = req.headers.get("range")
        start = 0
        status = 200
        if rng and (req.headers.get("if-range") in (None, etag)):
            start = int(rng.removeprefix("bytes=").split("-")[0])
            status = 206
        body = data[start:]
        headers = {
            "content-type": ctype,
            "ETag": etag,
            "Accept-Ranges": "bytes",
            "Content-Length": str(len(body)),
        }
        if status == 206:
            headers["Content-Range"] = f"bytes {start}-{len(data) - 1}/{len(data)}"

        def gen() -> Iterator[bytes]:
            pos = 0
            while pos < len(body):
                if drop_at is not None and pos >= drop_at:
                    raise httpx.ReadError("injected: download dropped")
                step = 64 * 1024 if drop_at is None else min(64 * 1024, max(1, drop_at - pos))
                yield body[pos : pos + step]
                pos += step

        return httpx.Response(status, stream=_IterStream(gen()), headers=headers)

    download_drop_at: int | None = None

    def op_downloadModel(self, req: httpx.Request, p: dict[str, str]) -> httpx.Response:
        m = self.models.get(p["model_id"])
        if m is None:
            return self._problem(self._op("downloadModel"), 404, "not_found", "no such model")
        if m["status"] != "ready":
            return self._problem(self._op("downloadModel"), 409, "model_not_ready", "building")
        drop, self.download_drop_at = self.download_drop_at, None
        return self._ranged(req, self.model_zip[m["id"]], f'"{m["bundle_sha256"]}"', "application/zip", drop)

    def op_getModelFile(self, req: httpx.Request, p: dict[str, str]) -> httpx.Response:
        files = self.model_files.get(p["model_id"])
        path = unquote(p["path"])
        if files is None or path not in files:
            return self._problem(self._op("getModelFile"), 404, "not_found", "no such file")
        data = files[path]
        return self._ranged(
            req, data, f'"{hashlib.sha256(data).hexdigest()}"', "application/octet-stream", None
        )


class _IterStream(httpx.SyncByteStream):
    def __init__(self, it: Iterator[bytes]) -> None:
        self._it = it

    def __iter__(self) -> Iterator[bytes]:
        yield from self._it
