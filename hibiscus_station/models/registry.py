"""Local model registry ``models/index.json`` (spec §4.9)."""

from __future__ import annotations

import json
import shutil
import threading
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from hibiscus_station.settings import write_private


class FeatureSpec(BaseModel):
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    type: str
    shape: list[int]


class ModelEntry(BaseModel):
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    key: str
    name: str
    source: Literal["bundle", "pretrained_dir", "server"]
    server_model_id: str | None = None
    policy_type: str
    input_features: dict[str, FeatureSpec] = Field(default_factory=dict)
    output_features: dict[str, FeatureSpec] = Field(default_factory=dict)
    fps: int | None = None
    task: str | None = None
    robot_type: str | None = None
    verified: bool = False
    imported_at: str = ""
    size_bytes: int = 0
    pretrained_path: str = "pretrained_model"  # relative to the model dir


class ModelRegistry:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.index_path = root / "index.json"
        self._lock = threading.Lock()

    def _read(self) -> list[ModelEntry]:
        if not self.index_path.is_file():
            return []
        raw: Any = json.loads(self.index_path.read_text(encoding="utf-8"))
        return [ModelEntry.model_validate(x) for x in raw.get("models", [])]

    def _write(self, entries: list[ModelEntry]) -> None:
        write_private(
            self.index_path,
            json.dumps({"version": 1, "models": [e.model_dump(mode="json") for e in entries]}, indent=2),
        )

    def list(self) -> list[ModelEntry]:
        with self._lock:
            return self._read()

    def get(self, key: str) -> ModelEntry | None:
        return next((e for e in self.list() if e.key == key), None)

    def add(self, entry: ModelEntry) -> ModelEntry:
        with self._lock:
            entries = [e for e in self._read() if e.key != entry.key]
            entries.append(entry)
            self._write(entries)
        return entry

    def remove(self, key: str) -> bool:
        with self._lock:
            entries = self._read()
            kept = [e for e in entries if e.key != key]
            if len(kept) == len(entries):
                return False
            self._write(kept)
        shutil.rmtree(self.root / key, ignore_errors=True)
        return True

    def model_dir(self, key: str) -> Path:
        return self.root / key

    def pretrained_dir(self, entry: ModelEntry) -> Path:
        return self.root / entry.key / entry.pretrained_path

    def unique_key(self, base: str) -> str:
        existing = {e.key for e in self.list()}
        key, n = base, 2
        while key in existing or (self.root / key).exists():
            key = f"{base}-{n}"
            n += 1
        return key
