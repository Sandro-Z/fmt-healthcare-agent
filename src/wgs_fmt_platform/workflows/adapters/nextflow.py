from __future__ import annotations

import asyncio
from pathlib import Path

from wgs_fmt_platform.workflows.state import PipelineRunState, PipelineStepSpec


class NextflowExecutor:
    def __init__(self, executable: str, pipeline: Path, work_dir: Path) -> None:
        self.executable = executable
        self.pipeline = pipeline.resolve()
        self.work_dir = work_dir.resolve()

    def plan(self, step: PipelineStepSpec, state: PipelineRunState) -> list[str]:
        return [
            self.executable,
            "run",
            str(self.pipeline),
            "-resume",
            "--entry",
            step.step_id,
            "--sample_id",
            state.sample_id,
            "--run_id",
            state.run_id,
        ]

    async def execute(
        self,
        step: PipelineStepSpec,
        state: PipelineRunState,
    ) -> dict[str, str]:
        run_dir = self.work_dir / state.run_id / step.step_id
        run_dir.mkdir(parents=True, exist_ok=True)
        process = await asyncio.create_subprocess_exec(
            *self.plan(step, state),
            cwd=run_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        stdout_path = run_dir / "stdout.log"
        stderr_path = run_dir / "stderr.log"
        stdout_path.write_bytes(stdout)
        stderr_path.write_bytes(stderr)
        if process.returncode != 0:
            raise RuntimeError(
                f"Nextflow step {step.step_id} failed ({process.returncode}): "
                f"{stderr.decode(errors='replace')[-1000:]}"
            )
        return {"run_dir": str(run_dir), "stdout": str(stdout_path)}

