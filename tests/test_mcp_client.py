from pathlib import Path

import pytest

from linear_issue_maker.mcp_client import LinearMCPClient, LinearMCPError, _record_id
from linear_issue_maker.settings import LinearMCPConfig


def test_match_record_supports_name_and_key() -> None:
    records = [
        {"id": "team-1", "name": "Backend"},
        {"id": "team-2", "key": "BE"},
    ]

    matched_by_name = LinearMCPClient._match_record(records, "Backend", "team")
    matched_by_key = LinearMCPClient._match_record(records, "BE", "team")

    assert matched_by_name["id"] == "team-1"
    assert matched_by_key["id"] == "team-2"


def test_match_record_raises_with_helpful_error() -> None:
    records = [{"id": "1", "name": "Backend"}]

    with pytest.raises(LinearMCPError) as excinfo:
        LinearMCPClient._match_record(records, "Unknown", "team")

    assert "Unknown" in str(excinfo.value)
    assert "Backend" in str(excinfo.value)


def test_record_id_falls_back_to_identifier() -> None:
    record = {"identifier": "abc123"}
    assert _record_id(record) == "abc123"


def test_config_reads_token_from_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Ensure env vars (and .env) don't override the explicit token path for this test.
    monkeypatch.setenv("LINEAR_MCP_ACCESS_TOKEN", "")
    monkeypatch.delenv("LINEAR_MCP_TOKEN_PATH", raising=False)

    token_file = tmp_path / "token"
    token_file.write_text("secret-token\n", encoding="utf-8")

    config = LinearMCPConfig(token_path=token_file)

    assert config.access_token == "secret-token"
