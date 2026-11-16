"""Server pairing, dataset upload and model pull (spec §4.8), reusing the Hibiscus CLI.

The PAT lives in the CLI credential store (keyring, else a 0600 file), shared with ``hibiscus login``;
it is never sent to the browser. ``server.json`` only keeps the URL, workspace, prefix and scopes.
"""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from typing import Any

from hibiscus_station.errors import StationError
from hibiscus_station.jobs import Job, JobManager
from hibiscus_station.settings import write_private

log = logging.getLogger(__name__)
IMPLIES = {"datasets:write": {"datasets:read"}, "runs:write": {"runs:read"}}
REQUIRED = ("datasets:write", "models:read")


def expand(scopes: list[str]) -> set[str]:
    out = set(scopes)
    for s in scopes:
        out |= IMPLIES.get(s, set())
    return out


def _api_error(exc: Exception) -> StationError:
    code = getattr(exc, "code", None)
    status = getattr(exc, "status", None)
    return StationError(
        "server_error",
        f"Hibiscus server: {exc}"[:400],
        params={"upstream_code": code, "upstream_status": status},
    )


class ServerLink:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.data: dict[str, Any] = {}
        if path.is_file():
            try:
                self.data = json.loads(path.read_text())
            except ValueError:
                self.data = {}

    @property
    def paired(self) -> bool:
        return bool(self.data.get("url"))

    def view(self) -> dict[str, Any]:
        return {
            "paired": self.paired,
            "url": self.data.get("url"),
            "web_url": self.data.get("web_url"),
            "workspace_id": self.data.get("workspace_id"),
            "workspace": self.data.get("workspace_slug"),
            "workspace_name": self.data.get("workspace_name"),
            "token_prefix": self.data.get("token_prefix"),
            "scopes": list(self.data.get("scopes", [])),
        }

    def save(self) -> None:
        write_private(self.path, json.dumps(self.data, indent=2))

    # ------------------------------------------------------------------ api
    def api(self) -> Any:
        from hibiscus.api import HibiscusApi
        from hibiscus.credentials import load_token

        if not self.paired:
            raise StationError("not_paired", "pair Station with a Hibiscus server first")
        stored = load_token(self.data["url"])
        if stored is None:
            raise StationError("not_paired", "the stored token is missing; pair again")
        return HibiscusApi(self.data["url"], stored.token, workspace_id=self.data.get("workspace_id"))

    def require_scope(self, scope: str) -> None:
        if scope not in expand(self.data.get("scopes", [])):
            raise StationError(
                "not_paired", f"the token lacks the {scope} scope", params={"missing_scope": scope}
            )

    def pair(self, url: str, token: str, workspace_id: str | None = None) -> dict[str, Any]:
        from hibiscus.api import ApiError, HibiscusApi
        from hibiscus.config import normalize_server
        from hibiscus.credentials import looks_like_pat, save_token, token_prefix

        try:
            base = normalize_server(url)
        except ValueError as exc:
            raise StationError("validation_failed", str(exc)) from exc
        if not looks_like_pat(token):
            raise StationError("validation_failed", "this is not a Hibiscus personal access token (hbp_...)")
        try:
            with HibiscusApi(base, token) as api:
                me = api.request("GET", "/auth/me").json()
        except ApiError as exc:
            if getattr(exc, "status", 0) == 401:
                raise StationError("validation_failed", "the server rejected this token") from exc
            raise _api_error(exc) from exc
        except Exception as exc:
            raise StationError("server_error", f"cannot reach {base}: {exc}"[:300]) from exc
        tok = me.get("token") or {}
        scopes = list(tok.get("scopes") or [])
        missing = [s for s in REQUIRED if s not in expand(scopes)]
        if missing:
            raise StationError(
                "not_paired",
                f"the token lacks scope(s) {', '.join(missing)}",
                params={"missing_scope": missing[0]},
            )
        memberships = me.get("memberships") or []
        ws = workspace_id or tok.get("workspace_id")
        if ws is None and len(memberships) == 1:
            ws = memberships[0]["workspace_id"]
        member = next((m for m in memberships if m.get("workspace_id") == ws), None)
        if member is None:
            raise StationError(
                "validation_failed",
                "choose a workspace",
                params={
                    "workspaces": [
                        {"id": m["workspace_id"], "slug": m.get("workspace_slug")} for m in memberships
                    ]
                },
            )
        save_token(base, token)
        self.data = {
            "url": base,
            "web_url": base.removesuffix("/api/v1"),
            "workspace_id": ws,
            "workspace_slug": member.get("workspace_slug"),
            "workspace_name": member.get("workspace_name"),
            "token_prefix": f"hbp_{token_prefix(token)}…",
            "scopes": scopes,
        }
        self.save()
        return self.view()

    def unpair(self) -> None:
        from hibiscus.credentials import delete_token

        if self.paired:
            delete_token(self.data["url"])
        self.data = {}
        self.path.unlink(missing_ok=True)

    # ------------------------------------------------------------------ proxies
    def datasets(self) -> list[dict[str, Any]]:
        from hibiscus.api import ApiError

        self.require_scope("datasets:read")
        try:
            with self.api() as api:
                page = api.list_datasets(limit=100)
                items = [d.to_dict() for d in page.items]
        except ApiError as exc:
            raise _api_error(exc) from exc
        return [
            {"id": d.get("id"), "name": d.get("name"), "latest_version": d.get("latest_version")}
            for d in items
        ]

    def models(self) -> list[dict[str, Any]]:
        from hibiscus.api import ApiError

        self.require_scope("models:read")
        try:
            with self.api() as api:
                page = api.list_models(limit=100)
                items = [m.to_dict() for m in page.items]
        except ApiError as exc:
            raise _api_error(exc) from exc
        out = [
            {
                "id": m.get("id"),
                "name": m.get("name"),
                "status": m.get("status"),
                "policy_type": m.get("policy_type"),
                "size_bytes": m.get("bundle_size_bytes"),
                "created_at": m.get("created_at"),
            }
            for m in items
        ]
        out.sort(key=lambda m: (m["status"] != "ready", str(m.get("created_at") or "")), reverse=False)
        return out

    def runs(self, dataset_id: str | None = None) -> list[dict[str, Any]]:
        from hibiscus.api import ApiError

        self.require_scope("runs:read")
        try:
            with self.api() as api:
                page = api.list_runs(limit=100)
                items = [r.to_dict() for r in page.items]
        except ApiError as exc:
            raise _api_error(exc) from exc
        web = self.data.get("web_url", "")
        ws = self.data.get("workspace_slug") or self.data.get("workspace_id")
        out = []
        for r in items:
            ds_obj = r.get("dataset")
            ds = r.get("dataset_id") or (ds_obj.get("id") if isinstance(ds_obj, dict) else None)
            if dataset_id and ds and ds != dataset_id:
                continue
            out.append(
                {
                    "id": r.get("id"),
                    "number": r.get("number"),
                    "status": r.get("status"),
                    "policy_type": r.get("policy_type"),
                    "progress": _fraction(r.get("progress")),
                    "model_id": r.get("model_id"),
                    "url": f"{web}/w/{ws}/runs/{r.get('id')}",
                }
            )
        return out

    def train_link(self, dataset_version_id: str | None) -> str:
        web = self.data.get("web_url", "")
        ws = self.data.get("workspace_slug") or self.data.get("workspace_id")
        q = f"?version={dataset_version_id}" if dataset_version_id else ""
        return f"{web}/w/{ws}/runs/new{q}"


def _fraction(progress: Any) -> float | None:
    """Server ``RunProgress`` ({current_step, total_steps}) as 0..1."""
    if isinstance(progress, (int, float)):
        return float(progress)
    if isinstance(progress, dict):
        cur, tot = progress.get("current_step"), progress.get("total_steps")
        if isinstance(cur, (int, float)) and isinstance(tot, (int, float)) and tot > 0:
            return round(min(1.0, max(0.0, cur / tot)), 4)
    return None


# --------------------------------------------------------------------------- jobs
def upload_dataset(
    link: ServerLink,
    jobs: JobManager,
    job: Job,
    root: Path,
    *,
    new_dataset_name: str | None,
    dataset_id: str | None,
) -> dict[str, Any]:
    from hibiscus.api import ApiError
    from hibiscus.archive import VirtualTar
    from hibiscus.recording import check_recording
    from hibiscus.upload import Uploader, UploadError, UploadEvents

    link.require_scope("datasets:write")
    st = check_recording(root)
    if not st.complete:
        raise StationError("dataset_not_finalized", "; ".join(st.reasons[:5]), params={"reasons": st.reasons})
    state = {"done": 0, "total": 0}

    def hash_start(total: int) -> None:
        state["total"], state["done"] = total, 0
        jobs.progress(job, done=0, total=total, phase="hashing")

    def hash_progress(n: int) -> None:
        job.check_cancel()
        state["done"] += n
        jobs.progress(job, done=state["done"], phase="hashing")

    def upload_start(total: int, already: int) -> None:
        state["total"], state["done"] = total, already
        jobs.progress(job, done=already, total=total, phase="uploading", resumed_bytes=already)

    def part_done(part: int, nbytes: int) -> None:
        job.check_cancel()
        state["done"] += nbytes
        jobs.progress(job, done=state["done"], phase="uploading")

    def retry(part: int, attempt: int, exc: BaseException, delay: float) -> None:
        jobs.progress(job, retries=int(job.progress.get("retries", 0)) + 1)

    events = UploadEvents(
        on_hash_start=hash_start,
        on_hash_progress=hash_progress,
        on_upload_start=upload_start,
        on_part_done=part_done,
        on_retry=retry,
    )
    try:
        with link.api() as api:
            result = Uploader(api, events=events).push(
                VirtualTar(root), new_dataset_name=new_dataset_name, dataset_id=dataset_id
            )
    except (ApiError, UploadError) as exc:
        raise _api_error(exc) from exc
    jobs.progress(job, done=state["total"], phase="verifying")
    web = link.data.get("web_url", "")
    ws = link.data.get("workspace_slug") or link.data.get("workspace_id")
    return {
        "dataset_id": result.dataset_id,
        "dataset_name": result.dataset_name,
        "version_id": result.version_id,
        "version": result.version,
        "resumed_parts": result.resumed_parts,
        "sent_parts": result.sent_parts,
        "server_url": f"{web}/w/{ws}/datasets/{result.dataset_id}",
        "train_url": link.train_link(result.version_id),
    }


def pull_model(link: ServerLink, jobs: JobManager, job: Job, model_id: str, dest: Path) -> Path:
    from hibiscus.api import ApiError
    from hibiscus.pull import Puller, PullError, PullEvents

    link.require_scope("models:read")
    state = {"done": 0}

    def start(total: int, have: int) -> None:
        state["done"] = have
        jobs.progress(job, done=have, total=total, phase="downloading")

    def on_bytes(n: int) -> None:
        job.check_cancel()
        state["done"] += n
        jobs.progress(job, done=state["done"])

    dest.mkdir(parents=True, exist_ok=True)
    try:
        with link.api() as api:
            res = Puller(api, PullEvents(on_start=start, on_bytes=on_bytes)).pull(model_id, dest)
    except PullError as exc:
        raise StationError("model_incompatible", f"pull failed: {exc}", errors=[{"code": "pull"}]) from exc
    except ApiError as exc:
        raise _api_error(exc) from exc
    jobs.progress(job, phase="verifying")
    return Path(res.bundle_dir)


def cleanup(path: Path) -> None:
    shutil.rmtree(path, ignore_errors=True)
