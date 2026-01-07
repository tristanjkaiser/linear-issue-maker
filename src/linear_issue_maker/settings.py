"""Configuration helpers for the Linear MCP client."""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import AnyHttpUrl, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ClientMode(str, Enum):
    """Client mode selection for Linear API."""

    MCP = "mcp"
    API = "api"
    AUTO = "auto"


class LinearMCPConfig(BaseSettings):
    """Settings that describe how to reach the Linear MCP server."""

    server_url: AnyHttpUrl = Field("https://mcp.linear.app/sse", description="Linear MCP SSE endpoint.")
    access_token: str | None = Field(
        default=None,
        description="Bearer token returned by `codex mcp login linear`.",
    )
    token_path: Path | None = Field(
        default=None,
        description="Optional path to a file that contains the bearer token.",
    )
    http_timeout: float = Field(
        default=15.0,
        description="HTTP timeout (seconds) for the SSE transport.",
    )
    sse_read_timeout: float = Field(
        default=60.0 * 5,
        description="How long to wait for SSE messages before reconnecting.",
    )
    list_teams_tool: str = Field("list_teams", description="Tool used to fetch teams.")
    list_projects_tool: str = Field("list_projects", description="Tool used to fetch projects.")
    list_templates_tool: str = Field("list_templates", description="Tool used to fetch templates.")
    create_issue_tool: str = Field("create_issue", description="Tool used to create a new issue.")
    user_agent: str = Field(
        default="linear-issue-maker/0.1.0",
        description="User agent header reported to the MCP server.",
    )

    model_config = SettingsConfigDict(env_prefix="LINEAR_MCP_", env_file=".env", extra="ignore")

    @model_validator(mode="after")
    def _populate_token(self) -> "LinearMCPConfig":
        """Ensure we have a token either directly or via ``token_path``."""

        if self.access_token:
            return self

        if self.token_path:
            token_file = self.token_path.expanduser()
            if not token_file.exists():  # pragma: no cover - depends on user setup
                raise ValueError(f"Token file '{token_file}' not found")
            self.access_token = token_file.read_text(encoding="utf-8").strip()

        if not self.access_token:
            raise ValueError("Provide LINEAR_MCP_ACCESS_TOKEN or LINEAR_MCP_TOKEN_PATH")

        return self

    def as_headers(self) -> dict[str, Any]:
        """Return HTTP headers for establishing the SSE connection."""

        assert self.access_token, "access_token validated in model_validator"
        return {
            "Authorization": f"Bearer {self.access_token}",
            "User-Agent": self.user_agent,
            # Linear's SSE endpoint requires clients to accept text/event-stream.
            "Accept": "text/event-stream",
        }


class LinearAPIConfig(BaseSettings):
    """Settings for direct Linear GraphQL API access."""

    api_url: str = Field(
        "https://api.linear.app/graphql",
        description="Linear GraphQL API endpoint.",
    )
    access_token: str | None = Field(
        default=None,
        description="Linear Personal API Key.",
    )
    token_path: Path | None = Field(
        default=None,
        description="Optional path to a file that contains the API token.",
    )
    http_timeout: float = Field(
        default=30.0,
        description="HTTP timeout (seconds) for GraphQL requests.",
    )

    model_config = SettingsConfigDict(env_prefix="LINEAR_API_", env_file=".env", extra="ignore")

    @model_validator(mode="after")
    def _populate_token(self) -> "LinearAPIConfig":
        """Ensure we have a token either directly or via ``token_path``."""

        if self.access_token:
            return self

        if self.token_path:
            token_file = self.token_path.expanduser()
            if not token_file.exists():  # pragma: no cover - depends on user setup
                raise ValueError(f"Token file '{token_file}' not found")
            self.access_token = token_file.read_text(encoding="utf-8").strip()

        if not self.access_token:
            raise ValueError("Provide LINEAR_API_ACCESS_TOKEN or LINEAR_API_TOKEN_PATH")

        return self
