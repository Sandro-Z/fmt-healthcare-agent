from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


def _safe(value: str) -> str:
    if not value.replace("-", "").replace("_", "").replace(".", "").isalnum():
        raise ValueError(f"unsafe registry identifier: {value}")
    return value


class ModelManifest(BaseModel):
    name: str
    task: str
    version: str
    artifact_uri: str
    feature_version: str
    training_dataset_version: str
    metrics: dict[str, float] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class DeploymentRevision(BaseModel):
    model_version: str
    traffic_percent: int = Field(default=100, ge=0, le=100)
    changed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    reason: str = ""


class DeploymentState(BaseModel):
    environment: str
    active: DeploymentRevision
    candidate: DeploymentRevision | None = None
    history: list[DeploymentRevision] = Field(default_factory=list)


class FileModelRegistry:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def _manifest_path(self, name: str, version: str) -> Path:
        return self.root / "models" / _safe(name) / _safe(version) / "manifest.json"

    def _deployment_path(self, name: str, environment: str) -> Path:
        return self.root / "deployments" / _safe(name) / f"{_safe(environment)}.json"

    @staticmethod
    def _write(path: Path, payload: BaseModel | dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = payload.model_dump(mode="json") if isinstance(payload, BaseModel) else payload
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)

    def register(self, manifest: ModelManifest) -> Path:
        path = self._manifest_path(manifest.name, manifest.version)
        if path.exists():
            existing = ModelManifest.model_validate_json(path.read_text(encoding="utf-8"))
            if existing != manifest:
                raise ValueError("model version is immutable and already registered")
            return path
        self._write(path, manifest)
        return path

    def get(self, name: str, version: str) -> ModelManifest:
        path = self._manifest_path(name, version)
        return ModelManifest.model_validate_json(path.read_text(encoding="utf-8"))

    def deployment(self, name: str, environment: str) -> DeploymentState | None:
        path = self._deployment_path(name, environment)
        if not path.exists():
            return None
        return DeploymentState.model_validate_json(path.read_text(encoding="utf-8"))

    def promote(
        self,
        name: str,
        version: str,
        environment: str,
        *,
        traffic_percent: int = 100,
        reason: str = "",
    ) -> DeploymentState:
        self.get(name, version)
        path = self._deployment_path(name, environment)
        current = self.deployment(name, environment)
        revision = DeploymentRevision(
            model_version=version,
            traffic_percent=traffic_percent,
            reason=reason,
        )
        if current is None:
            state = DeploymentState(environment=environment, active=revision)
        elif traffic_percent < 100:
            state = current.model_copy(deep=True)
            state.candidate = revision
        else:
            state = current.model_copy(deep=True)
            state.history.append(state.active)
            state.active = revision
            state.candidate = None
        self._write(path, state)
        return state

    def rollback(self, name: str, environment: str, reason: str = "rollback") -> DeploymentState:
        state = self.deployment(name, environment)
        if state is None or not state.history:
            raise ValueError("no previous deployment is available")
        previous = state.history.pop()
        state.history.append(state.active)
        state.active = previous.model_copy(update={"reason": reason})
        state.candidate = None
        self._write(self._deployment_path(name, environment), state)
        return state

