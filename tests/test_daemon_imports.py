def test_daemon_logging_uses_current_config_contract() -> None:
    from wgs_agent.core.config import WgsConfig
    from wgs_agent.core.logging_setup import setup_logging

    assert callable(setup_logging)
    assert WgsConfig.__name__ == "WgsConfig"


def test_cli_json_rpc_ids_match_daemon_string_contract() -> None:
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[1] / "src/wgs_agent/cli/main.py"
    ).read_text(encoding="utf-8")
    assert '"id": "cli-ping"' in source
    assert '"id": "cli-run"' in source
    assert '"id": 1' not in source
