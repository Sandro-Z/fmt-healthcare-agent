from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

from wgs_fmt_platform.contracts import (
    AnalysisRequest,
    AnalysisResult,
    RunStatus,
    SampleManifest,
)


class MProjectError(RuntimeError):
    pass


class MProjectAdapter:
    """Typed adapter around the mProject CLI.

    No shell is used: arguments are passed directly to the subprocess to avoid
    command injection. The adapter stores raw output as an artifact; a parser
    can later translate exported mProject records into FeatureObservation.
    """

    def __init__(self, executable: str, database: Path, workspace: Path) -> None:
        self.executable = executable
        self.database = database.resolve()
        self.workspace = workspace.resolve()

    def plan_run(self, sample: SampleManifest) -> list[str]:
        args = [
            self.executable,
            "run",
            "--database",
            str(self.database),
            "--sample",
            sample.sample_id,
            "-1",
            str(sample.read1),
        ]
        if sample.read2:
            args.extend(["-2", str(sample.read2)])
        return args

    async def _execute(self, args: list[str]) -> tuple[str, str]:
        process = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        out = stdout.decode(errors="replace")
        err = stderr.decode(errors="replace")
        if process.returncode != 0:
            raise MProjectError(f"mProject exited {process.returncode}: {err[-2000:]}")
        return out, err

    async def initialize(self, reference: Path) -> str:
        await self._execute(
            [
                self.executable,
                "initialize",
                "--database",
                str(self.database),
                "--host",
                reference.name,
                "--reference",
                str(reference.parent),
            ]
        )
        return await self.version()

    async def update(self) -> str:
        await self._execute([self.executable, "update", "--database", str(self.database)])
        return await self.version()

    async def run(self, sample: SampleManifest, *, database_version: str) -> AnalysisResult:
        request = AnalysisRequest(sample=sample, database_version=database_version)
        result = AnalysisResult(request=request, status=RunStatus.running)
        run_dir = self.workspace / "runs" / result.analysis_id
        run_dir.mkdir(parents=True, exist_ok=False)
        try:
            stdout, stderr = await self._execute(self.plan_run(sample))
            (run_dir / "stdout.log").write_text(stdout, encoding="utf-8")
            (run_dir / "stderr.log").write_text(stderr, encoding="utf-8")
            result.artifacts["run_dir"] = str(run_dir)
            result.status = RunStatus.succeeded
        except Exception as exc:
            result.status = RunStatus.failed
            result.warnings.append(str(exc))
        result.finished_at = datetime.now(UTC)
        return result

    async def export(self, output_dir: Path) -> Path:
        output_dir = output_dir.resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        await self._execute(
            [self.executable, "dump", "--database", str(self.database), "-o", str(output_dir)]
        )
        return output_dir

    async def version(self) -> str:
        manifest = self.database / "wgs-fmt-version.json"
        if manifest.exists():
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            return str(payload.get("version", "unknown"))
        return f"unversioned-{self.database.name}"

