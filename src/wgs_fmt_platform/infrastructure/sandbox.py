from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class SandboxPolicy:
    mode: str
    workspace: Path
    allowed_root: Path
    allowed_commands: frozenset[str] = field(default_factory=frozenset)
    timeout_s: int = 300
    cpu_limit: float = 2.0
    memory_mb: int = 4096
    network_enabled: bool = False
    docker_image: str = "python:3.12-slim"
    docker_workspace: str = "/workspace"
    docker_read_only_root: bool = True

    def validate(self) -> None:
        workspace = self.workspace.resolve()
        if not workspace.is_relative_to(self.allowed_root.resolve()):
            raise ValueError("sandbox workspace escapes the allowed root")
        if self.mode not in {"process", "docker"}:
            raise ValueError("sandbox mode must be process or docker")
        if not self.allowed_commands:
            raise ValueError("at least one command must be allowed")


class SandboxExecutor:
    def __init__(self, policy: SandboxPolicy) -> None:
        policy.validate()
        self.policy = policy

    def _validate_command(self, argv: list[str]) -> None:
        if not argv:
            raise ValueError("empty command")
        executable = Path(argv[0]).name
        if executable not in self.policy.allowed_commands:
            raise PermissionError(f"command is not allowed in this workspace: {executable}")

    def command(self, argv: list[str]) -> list[str]:
        self._validate_command(argv)
        if self.policy.mode == "process":
            return argv
        docker = shutil.which("docker")
        if not docker:
            raise RuntimeError("Docker runtime is not installed")
        command = [docker, "run", "--rm", "--cpus", str(self.policy.cpu_limit), "--memory", f"{self.policy.memory_mb}m", "--network", "bridge" if self.policy.network_enabled else "none", "-v", f"{self.policy.workspace.resolve()}:{self.policy.docker_workspace}:rw", "-w", self.policy.docker_workspace]
        if self.policy.docker_read_only_root:
            command.extend(["--read-only", "--tmpfs", "/tmp:rw,noexec,nosuid,size=256m"])
        command.extend([self.policy.docker_image, *argv])
        return command

    def run(self, argv: list[str]) -> subprocess.CompletedProcess[str]:
        self.policy.workspace.mkdir(parents=True, exist_ok=True)
        command = self.command(argv)
        env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LANG": "C.UTF-8"}
        return subprocess.run(command, cwd=self.policy.workspace, env=env, capture_output=True, text=True, timeout=self.policy.timeout_s, check=False)
