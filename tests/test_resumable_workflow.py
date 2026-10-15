from pathlib import Path

import pytest

from wgs_fmt_platform.contracts import RunStatus
from wgs_fmt_platform.workflows import JsonRunStateStore, PipelineStepSpec, ResumableWorkflow


class FailingOnceExecutor:
    def __init__(self) -> None:
        self.calls: dict[str, int] = {}

    async def execute(self, step, state):
        self.calls[step.step_id] = self.calls.get(step.step_id, 0) + 1
        if step.step_id == "classify" and self.calls[step.step_id] == 1:
            raise RuntimeError("temporary failure")
        return {"result": f"{state.sample_id}-{step.step_id}.json"}


@pytest.mark.asyncio
async def test_workflow_retries_and_persists_state(tmp_path: Path) -> None:
    executor = FailingOnceExecutor()
    workflow = ResumableWorkflow(
        [
            PipelineStepSpec(step_id="qc"),
            PipelineStepSpec(step_id="classify", depends_on=["qc"], max_attempts=2),
        ],
        executor,
        JsonRunStateStore(tmp_path),
        workflow_version="workflow-v1",
    )
    result = await workflow.run("run-001", "sample-001")
    assert result.status == RunStatus.succeeded
    assert result.steps["qc"].attempts == 1
    assert result.steps["classify"].attempts == 2

    resumed = await workflow.run("run-001", "sample-001")
    assert resumed.status == RunStatus.succeeded
    assert executor.calls["qc"] == 1

