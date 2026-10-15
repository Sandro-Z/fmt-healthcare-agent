from __future__ import annotations

from datetime import UTC, datetime

from wgs_fmt_platform.contracts import RunStatus
from wgs_fmt_platform.workflows.state import (
    PipelineRunState,
    PipelineStepSpec,
    RunStateStore,
    StepExecutor,
    StepState,
)


class WorkflowDefinitionError(ValueError):
    pass


class ResumableWorkflow:
    def __init__(
        self,
        steps: list[PipelineStepSpec],
        executor: StepExecutor,
        store: RunStateStore,
        workflow_version: str,
    ) -> None:
        self.steps = steps
        self.executor = executor
        self.store = store
        self.workflow_version = workflow_version
        self._validate()

    def _validate(self) -> None:
        ids = [step.step_id for step in self.steps]
        if len(ids) != len(set(ids)):
            raise WorkflowDefinitionError("duplicate step_id")
        known = set(ids)
        for step in self.steps:
            missing = set(step.depends_on) - known
            if missing:
                raise WorkflowDefinitionError(
                    f"step {step.step_id} has missing dependencies: {sorted(missing)}"
                )

        completed: set[str] = set()
        remaining = {step.step_id: step for step in self.steps}
        while remaining:
            ready = [
                step_id
                for step_id, step in remaining.items()
                if set(step.depends_on) <= completed
            ]
            if not ready:
                raise WorkflowDefinitionError("workflow contains a dependency cycle")
            completed.update(ready)
            for step_id in ready:
                remaining.pop(step_id)

    async def run(self, run_id: str, sample_id: str) -> PipelineRunState:
        state = self.store.load(run_id) or PipelineRunState(
            run_id=run_id,
            sample_id=sample_id,
            workflow_version=self.workflow_version,
            steps={step.step_id: StepState() for step in self.steps},
        )
        if state.workflow_version != self.workflow_version:
            raise WorkflowDefinitionError("cannot resume with a different workflow version")

        state.status = RunStatus.running
        self.store.save(state)
        pending = {step.step_id: step for step in self.steps}

        while pending:
            progressed = False
            for step_id, step in list(pending.items()):
                step_state = state.steps[step_id]
                if step_state.status == RunStatus.succeeded:
                    pending.pop(step_id)
                    progressed = True
                    continue
                if not all(
                    state.steps[dependency].status == RunStatus.succeeded
                    for dependency in step.depends_on
                ):
                    continue

                while step_state.attempts < step.max_attempts:
                    step_state.status = RunStatus.running
                    step_state.attempts += 1
                    step_state.started_at = datetime.now(UTC)
                    step_state.error = None
                    self.store.save(state)
                    try:
                        step_state.artifacts = await self.executor.execute(step, state)
                        step_state.status = RunStatus.succeeded
                        step_state.finished_at = datetime.now(UTC)
                        self.store.save(state)
                        break
                    except Exception as exc:
                        step_state.error = str(exc)
                        step_state.status = RunStatus.failed
                        step_state.finished_at = datetime.now(UTC)
                        self.store.save(state)

                if step_state.status != RunStatus.succeeded:
                    state.status = RunStatus.failed
                    self.store.save(state)
                    return state
                pending.pop(step_id)
                progressed = True

            if not progressed:
                state.status = RunStatus.failed
                self.store.save(state)
                return state

        state.status = RunStatus.succeeded
        self.store.save(state)
        return state

