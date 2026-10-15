import json

import pytest

from app.agent_chat import TOOLS, _invoke_tool, _report_status, execute_confirmed_action


def test_workspace_agent_exposes_only_domain_whitelist() -> None:
    names = {item["function"]["name"] for item in TOOLS}
    assert "load_species_data" in names
    assert "request_report_generation" in names
    assert "create_sandbox_markdown" in names
    assert "read_sandbox_file" in names
    assert "bash" not in names
    assert "write_file" not in names
    assert "read_file" not in names


def test_write_request_creates_pending_action_without_writing(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("WGS_RESULTS_DIR", str(tmp_path))
    pending = []
    payload = json.loads(
        _invoke_tool("request_report_generation", {"sample_id": "SAFE_SAMPLE_01"}, pending)
    )
    assert payload["status"] == "awaiting_confirmation"
    assert pending[0]["kind"] == "generate_report"
    assert not list(tmp_path.glob("*_health_report.*"))


def test_report_status_uses_server_derived_paths(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("WGS_RESULTS_DIR", str(tmp_path))
    (tmp_path / "S1_analysis.json").write_text("{}", encoding="utf-8")
    status = _report_status("S1")
    assert status["artifacts"]["analysis_json"]["exists"] is True
    assert status["artifacts"]["pdf_report"]["exists"] is False


@pytest.mark.parametrize("sample_id", ["../escape", "/tmp/sample", "bad sample", ""])
def test_invalid_sample_ids_are_rejected(sample_id) -> None:
    with pytest.raises(ValueError):
        _invoke_tool("get_report_status", {"sample_id": sample_id}, [])


def test_sandbox_markdown_create_read_and_confirm_overwrite(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("WGS_AGENT_SANDBOX_ROOT", str(tmp_path / "sandboxes"))
    monkeypatch.setenv("WGS_AGENT_AUDIT_DIR", str(tmp_path / "audit"))
    pending = []
    canvas = []
    created = json.loads(_invoke_tool(
        "create_sandbox_markdown",
        {"path": "literature/summary.md", "content": "# First", "title": "Summary"},
        pending,
        canvas,
        sandbox_user_id="user-1",
        sandbox_conversation_id="conversation-1",
    ))
    target = tmp_path / "sandboxes/user-1/conversation-1/output/literature/summary.md"
    assert created["status"] == "created"
    assert target.read_text(encoding="utf-8") == "# First"
    assert target.stat().st_mode & 0o777 == 0o600
    assert canvas[0]["path"].startswith("sandbox://user-1/conversation-1/")

    overwrite_pending = []
    requested = json.loads(_invoke_tool(
        "create_sandbox_markdown",
        {"path": "literature/summary.md", "content": "# Revised"},
        overwrite_pending,
        [],
        sandbox_user_id="user-1",
        sandbox_conversation_id="conversation-1",
    ))
    assert requested["status"] == "awaiting_confirmation"
    assert target.read_text(encoding="utf-8") == "# First"
    result = execute_confirmed_action(overwrite_pending[0])
    assert result["status"] == "overwritten"
    assert target.read_text(encoding="utf-8") == "# Revised"

    read_back = json.loads(_invoke_tool(
        "read_sandbox_file",
        {"path": "output/literature/summary.md"},
        [],
        sandbox_user_id="user-1",
        sandbox_conversation_id="conversation-1",
    ))
    assert read_back["content"] == "# Revised"


def test_sandbox_rejects_path_traversal(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("WGS_AGENT_SANDBOX_ROOT", str(tmp_path / "sandboxes"))
    with pytest.raises(PermissionError):
        _invoke_tool(
            "create_sandbox_markdown",
            {"path": "../escape.md", "content": "blocked"},
            [],
            [],
            sandbox_user_id="user-1",
            sandbox_conversation_id="conversation-1",
        )
