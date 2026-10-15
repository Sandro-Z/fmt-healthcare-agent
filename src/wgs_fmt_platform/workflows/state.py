from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, Field

from wgs_fmt_platform.contracts.models import RunStatus


class PipelineStepSpec(BaseModel):
    step_id: str
    depends_on: list[str] = Field(default_factory=list)
    max_attempts: int = Field(default=2, ge=1, le=10)
    parameters: dict[str, Any] = Field(default_factory=dict)


class StepState(BaseModel):
    status: RunStatus = RunStatus.queued
    attempts: int = 0
    artifacts: dict[str, str] = Field(default_factory=dict)
    error: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


class PipelineRunState(BaseModel):
    run_id: str
    sample_id: str
    workflow_version: str
    status: RunStatus = RunStatus.queued
    steps: dict[str, StepState] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class RunStateStore(Protocol):
    def load(self, run_id: str) -> PipelineRunState | None: ...

    def save(self, state: PipelineRunState) -> None: ...


class JsonRunStateStore:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def _path(self, run_id: str) -> Path:
        if not run_id.replace("-", "").replace("_", "").isalnum():
            raise ValueError("unsafe run_id")
        return self.root / run_id / "state.json"

    def load(self, run_id: str) -> PipelineRunState | None:
        path = self._path(run_id)
        if not path.exists():
            return None
        return PipelineRunState.model_validate_json(path.read_text(encoding="utf-8"))

    def save(self, state: PipelineRunState) -> None:
        path = self._path(state.run_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        state.updated_at = datetime.now(UTC)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(state.model_dump_json(indent=2), encoding="utf-8")
        temporary.replace(path)


class StepExecutor(Protocol):
    async def execute(
        self,
        step: PipelineStepSpec,
        state: PipelineRunState,
    ) -> dict[str, str]: ...
