from io import BytesIO
from pathlib import Path

import pytest

from wgs_agent.pipeline.upload_workflow import (
    UploadWorkflowSettings,
    get_workflow_status,
    validate_sample_id,
)


def _settings(tmp_path: Path) -> UploadWorkflowSettings:
    return UploadWorkflowSettings(
        workspace=tmp_path,
        upload_root=tmp_path / "uploads",
        job_root=tmp_path / "jobs",
        output_root=tmp_path / "outputs",
        worker=tmp_path / "worker.sh",
        threads=2,
    )


def test_sample_id_validation_blocks_paths() -> None:
    assert validate_sample_id("FMT_001-A") == "FMT_001-A"
    with pytest.raises(ValueError):
        validate_sample_id("../../etc/passwd")


def test_status_tracks_pipeline_artifacts(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    job_dir = settings.job_root / "jobs"
    job_dir.mkdir(parents=True)
    (job_dir / "FMT_001.json").write_text(
        '{"sample_id":"FMT_001","state":"running","pid":999999,"files":[{}]}',
        encoding="utf-8",
    )
    profile = settings.output_root / "profiles/metaphlan/FMT_001_profile.tsv"
    profile.parent.mkdir(parents=True)
    profile.write_text("# profile\n", encoding="utf-8")
    failed = settings.output_root / "status/failed/FMT_001.failed"
    failed.parent.mkdir(parents=True)
    failed.write_text("failed", encoding="utf-8")

    status = get_workflow_status("FMT_001", settings=settings)
    assert status["state"] == "failed"
    assert status["artifacts"]["uploaded"] is True
    assert status["artifacts"]["taxonomy"] is True
    assert status["progress"] == 55


def test_unknown_sample_is_not_submitted(tmp_path: Path) -> None:
    status = get_workflow_status("FMT_002", settings=_settings(tmp_path))
    assert status["state"] == "not_submitted"
    assert status["progress"] == 0
