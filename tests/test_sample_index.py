"""Regression coverage for uploaded samples that have no analysis JSON yet."""

import json
import os
import subprocess
import sys

from wgs_agent.pipeline.upload_workflow import (
    UploadWorkflowSettings,
    get_workflow_status,
    list_uploaded_workflows,
)
from wgs_fmt_platform.paths import PROJECT_ROOT


def test_upload_index_skips_invalid_records_and_does_not_read_logs(tmp_path):
    settings = UploadWorkflowSettings(
        workspace=tmp_path,
        upload_root=tmp_path / "uploads",
        job_root=tmp_path / "upload-jobs",
        output_root=tmp_path / "bioinformatics",
        worker=tmp_path / "worker.sh",
    )
    jobs = settings.job_root / "jobs"
    jobs.mkdir(parents=True)
    (jobs / "p1.json").write_text(json.dumps({
        "sample_id": "p1", "state": "running", "pid": os.getpid(), "files": [{}],
    }))
    (jobs / "broken.json").write_text("{")
    (jobs / "array.json").write_text("[]")
    (jobs / "bad id.json").write_text("{}")
    log = settings.output_root / "logs/p1.log"
    log.parent.mkdir(parents=True)
    log.write_text("synthetic pipeline details\n")

    workflows = list_uploaded_workflows(settings=settings)

    assert set(workflows) == {"p1"}
    assert workflows["p1"]["state"] == "running"
    assert workflows["p1"]["log_tail"] == ""
    assert get_workflow_status("p1", settings=settings)["log_tail"] == "synthetic pipeline details"


def test_api_indexes_uploads_and_tracks_completion_without_analysis(tmp_path):
    """Use a separate runtime/SQLite database, never the deployment's data."""
    env = dict(os.environ)
    paths = {
        "WGS_WORKSPACE": tmp_path,
        "WGS_AGENT_CONFIG_DIR": tmp_path / "agent-config",
        "WGS_RESULTS_DIR": tmp_path / "results",
        "WGS_UPLOAD_ROOT": tmp_path / "uploads",
        "WGS_UPLOAD_JOB_ROOT": tmp_path / "upload-jobs",
        "WGS_BIOINFORMATICS_OUTPUT_ROOT": tmp_path / "bioinformatics",
        "WGS_RUNNER_STATUS": tmp_path / "bioinformatics/status/runner_status.tsv",
        "WGS_CONVERSATION_DB_FILE": tmp_path / "db/wgs_agent.db",
        "WGS_KNOWLEDGE_DB": tmp_path / "knowledge/kb.db",
        "WGS_KB_SQLITE_PATH": tmp_path / "knowledge/kb.db",
    }
    env.update({key: str(value) for key, value in paths.items()})
    env["WGS_DATABASE_URL"] = f"sqlite:///{tmp_path / 'db/wgs_agent.db'}"
    env["PYTHONPATH"] = os.pathsep.join([
        str(PROJECT_ROOT / "src"), str(PROJECT_ROOT / "apps/workspace-api"),
    ])
    source = '''
import json
import os
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import app

root = Path(os.environ["WGS_WORKSPACE"])
jobs = root / "upload-jobs/jobs"
jobs.mkdir(parents=True)
for sid, pid in (("p1", os.getpid()), ("failed1", 99999999), ("done1", 99999999)):
    (jobs / f"{sid}.json").write_text(json.dumps({
        "sample_id": sid, "state": "running", "pid": pid, "files": [{}],
        "submitted_at": "2026-01-01T00:00:00+00:00",
        "launcher_log": "/private/synthetic.log",
    }))
status = root / "bioinformatics/status"
(status / "done").mkdir(parents=True)
(status / "done/done1.done").write_text("done")
(status / "runner_status.tsv").write_text("sample_id\\tstate\\np1\\tfailed\\nlegacy\\tcomplete\\n")
(root / "results").mkdir()
(root / "results/legacy_analysis.json").write_text("{}")

with TestClient(app) as client:
    response = client.get("/api/samples")
    assert response.status_code == 200
    result = response.json()
    assert result["count"] == 4
    assert result["status_counts"] == {"complete": 2, "failed": 1, "running": 1}
    rows = {row["sample_id"]: row for row in result["samples"]}
    assert rows["p1"]["status"] == "running"
    assert rows["p1"]["updated_at"] == "2026-01-01T00:00:00+00:00"
    assert rows["p1"]["artifacts"]["analysis"]["exists"] is False
    assert set(rows["p1"]["workflow"]) == {"state", "progress", "submitted_at", "artifacts"}
    assert rows["failed1"]["status"] == "failed"
    assert rows["legacy"]["workflow"] is None
    assert "/private/synthetic.log" not in response.text
    filtered = client.get("/api/samples?q=p1").json()
    assert [row["sample_id"] for row in filtered["samples"]] == ["p1"]
    assert client.get("/api/samples/p1").status_code == 404
    (status / "done/p1.done").write_text("done")
    updated = client.get("/api/samples").json()
    assert updated["status_counts"].get("running", 0) == 0
    assert updated["status_counts"]["complete"] == 3
'''
    subprocess.run(
        [sys.executable, "-c", source], env=env, cwd=PROJECT_ROOT,
        check=True, capture_output=True, text=True,
    )
