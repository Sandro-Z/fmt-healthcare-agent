"""Single-server runtime paths, independent of the caller's working directory."""

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env", override=False)


def project_path(value: str | Path) -> Path:
    path = Path(value).expanduser()
    return (path if path.is_absolute() else PROJECT_ROOT / path).resolve()


def workspace_root() -> Path:
    return project_path(os.environ.get("WGS_WORKSPACE") or "var")


def runtime_path(variable: str, *parts: str) -> Path:
    value = os.environ.get(variable, "").strip()
    return project_path(value) if value else workspace_root().joinpath(*parts)


def knowledge_db_path() -> Path:
    # Both names are retained for existing API and knowledge-tool callers.
    value = os.environ.get("WGS_KNOWLEDGE_DB") or os.environ.get("WGS_KB_SQLITE_PATH")
    return project_path(value) if value else workspace_root() / "knowledge" / "kb.db"


def bioinformatics_root() -> Path:
    return runtime_path("WGS_BIOINFORMATICS_OUTPUT_ROOT", "bioinformatics")


def legacy_output_root() -> Path:
    value = os.environ.get("WGS_LEGACY_PIPELINE_OUTPUT_DIR")
    return project_path(value) if value else bioinformatics_root() / "legacy"


def runner_status_path() -> Path:
    value = os.environ.get("WGS_RUNNER_STATUS")
    return project_path(value) if value else bioinformatics_root() / "status" / "runner_status.tsv"
