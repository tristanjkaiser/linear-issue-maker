"""Factory for creating Linear clients based on mode and configuration."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .base_client import LinearClient
from .graphql_client import LinearGraphQLClient
from .mcp_client import LinearMCPClient
from .parser import IssueSpec
from .settings import ClientMode, LinearAPIConfig, LinearMCPConfig


def create_client(
    mode: ClientMode,
    specs: list[IssueSpec],
    *,
    server_url: str | None = None,
    api_url: str | None = None,
    token: str | None = None,
    token_path: Path | None = None,
) -> LinearClient:
    """Create a Linear client based on mode and configuration.

    Args:
        mode: Client mode (mcp, api, or auto)
        specs: List of issue specs (used for auto-detection)
        server_url: Override MCP server URL
        api_url: Override GraphQL API URL
        token: Access token (works for both MCP and API)
        token_path: Path to token file

    Returns:
        Configured LinearClient instance (MCP or GraphQL)

    Raises:
        ValueError: If configuration is invalid
    """
    # Auto-detect mode based on template column presence
    if mode == ClientMode.AUTO:
        has_templates = any(spec.template is not None for spec in specs)
        mode = ClientMode.API if has_templates else ClientMode.MCP

    # Build config kwargs
    config_kwargs: dict[str, Any] = {}
    if token is not None:
        config_kwargs["access_token"] = token
    if token_path is not None:
        config_kwargs["token_path"] = token_path

    # Create client based on mode
    if mode == ClientMode.MCP:
        if server_url is not None:
            config_kwargs["server_url"] = server_url
        config = LinearMCPConfig(**config_kwargs)
        return LinearMCPClient(config)

    elif mode == ClientMode.API:
        if api_url is not None:
            config_kwargs["api_url"] = api_url

        # Try to load API config, fall back to using MCP token for API
        try:
            config = LinearAPIConfig(**config_kwargs)
        except ValueError:
            # If API token not found, try using MCP token (same token works for both)
            mcp_config = LinearMCPConfig(**config_kwargs)
            if mcp_config.access_token:
                config_kwargs["access_token"] = mcp_config.access_token
                config = LinearAPIConfig(**config_kwargs)
            else:
                raise

        assert config.access_token, "Token should be validated by config"
        return LinearGraphQLClient(
            api_url=config.api_url,
            access_token=config.access_token,
            http_timeout=config.http_timeout,
        )

    else:
        raise ValueError(f"Unknown client mode: {mode}")


def detect_mode_from_specs(specs: list[IssueSpec]) -> ClientMode:
    """Detect appropriate client mode based on issue specs.

    Args:
        specs: List of parsed issue specs

    Returns:
        ClientMode.API if any spec has a template, otherwise ClientMode.MCP
    """
    has_templates = any(spec.template is not None for spec in specs)
    return ClientMode.API if has_templates else ClientMode.MCP
