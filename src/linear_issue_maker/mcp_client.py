"""Linear MCP client implementation."""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from contextlib import AbstractAsyncContextManager, AsyncExitStack
from dataclasses import dataclass
from typing import Any

from mcp import ClientSession, Implementation, McpError
from mcp.client.sse import sse_client
from mcp.types import CallToolResult, TextContent

from .parser import IssueSpec
from .settings import LinearMCPConfig

JsonDict = dict[str, Any]


class LinearMCPError(RuntimeError):
    """Domain-specific error for all MCP failures."""


@dataclass(slots=True)
class LinearIdentifiers:
    """Resolved Linear entities that are required to create an issue."""

    team: JsonDict
    project: JsonDict

    @property
    def team_id(self) -> str:
        return _record_id(self.team)

    @property
    def project_id(self) -> str:
        return _record_id(self.project)


class LinearMCPClient:
    """High-level helper around the Linear MCP HTTP server."""

    def __init__(
        self,
        config: LinearMCPConfig,
        *,
        transport_factory: Callable[[], AbstractAsyncContextManager[tuple[Any, Any]]] | None = None,
    ) -> None:
        self.config = config
        self._exit_stack: AsyncExitStack | None = None
        self._session: ClientSession | None = None
        self._transport_factory = transport_factory

        # Simple caches to avoid duplicate lookups within a single CLI invocation.
        self._teams_cache: list[JsonDict] | None = None
        self._projects_cache: dict[str, list[JsonDict]] = {}

    async def __aenter__(self) -> "LinearMCPClient":
        await self._ensure_session()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:  # type: ignore[override]
        await self.aclose()

    async def aclose(self) -> None:
        """Close the MCP session and transport."""

        if self._exit_stack is None:
            return

        await self._exit_stack.aclose()
        self._exit_stack = None
        self._session = None

    async def _ensure_session(self) -> ClientSession:
        if self._session is not None:
            return self._session

        stack = AsyncExitStack()
        transport_cm = (
            self._transport_factory()
            if self._transport_factory
            else sse_client(
                url=str(self.config.server_url),
                headers=self.config.as_headers(),
                timeout=self.config.http_timeout,
                sse_read_timeout=self.config.sse_read_timeout,
            )
        )
        read_stream, write_stream = await stack.enter_async_context(transport_cm)

        session = await stack.enter_async_context(
            ClientSession(
                read_stream=read_stream,
                write_stream=write_stream,
                client_info=Implementation(name="linear-issue-maker", version="0.1.0"),
            )
        )
        await session.initialize()

        self._exit_stack = stack
        self._session = session
        return session

    async def resolve_identifiers(
        self, team: str, project: str, *, create_missing_projects: bool = False
    ) -> LinearIdentifiers:
        """Resolve team and project names into structured records.

        Args:
            team: Team name or ID to resolve
            project: Project name or ID to resolve
            create_missing_projects: If True, create project if it doesn't exist

        Returns:
            LinearIdentifiers with resolved team and project

        Raises:
            LinearMCPError: If team or project cannot be resolved/created
        """
        team_record = await self._resolve_team(team)
        project_record = await self._resolve_project(project, team_record, create_missing_projects)
        return LinearIdentifiers(team=team_record, project=project_record)

    async def create_issue(self, spec: IssueSpec, identifiers: LinearIdentifiers) -> JsonDict:
        """Create the issue using the supplied identifiers."""

        # Linear MCP uses team/project names or IDs directly, not separate ID fields
        arguments = {
            "team": identifiers.team_id,
            "project": identifiers.project_id,
            "title": spec.title,
            "description": spec.summary,
        }

        result = await self._call_tool(self.config.create_issue_tool, arguments=arguments)
        return self._extract_structured_dict(result, self.config.create_issue_tool)

    async def _resolve_team(self, team_name: str) -> JsonDict:
        teams = await self._list_teams()
        return self._match_record(teams, team_name, "team")

    async def _resolve_project(
        self, project_name: str, team: JsonDict, create_if_missing: bool = False
    ) -> JsonDict:
        """Resolve project by name, optionally creating it if not found."""
        team_id = _record_id(team)
        projects = await self._list_projects(team_id)

        try:
            return self._match_record(projects, project_name, "project")
        except LinearMCPError as exc:
            if not create_if_missing:
                raise

            # Project not found, create it
            team_name = team.get("name", team_id)
            return await self._create_project(project_name, team_id, team_name)

    async def _list_teams(self) -> list[JsonDict]:
        if self._teams_cache is not None:
            return self._teams_cache

        result = await self._call_tool(self.config.list_teams_tool, {})
        teams = self._extract_structured_list(result, self.config.list_teams_tool)
        self._teams_cache = teams
        return teams

    async def _list_projects(self, team_id: str) -> list[JsonDict]:
        if team_id in self._projects_cache:
            return self._projects_cache[team_id]

        result = await self._call_tool(self.config.list_projects_tool, {"team": team_id})
        projects = self._extract_structured_list(result, self.config.list_projects_tool)
        self._projects_cache[team_id] = projects
        return projects

    async def _create_project(self, name: str, team_id: str, team_name: str) -> JsonDict:
        """Create a new project in Linear."""
        arguments = {
            "name": name,
            "team": team_id,
            "color": "#bec2c8",  # Default gray color
        }

        result = await self._call_tool("create_project", arguments=arguments)
        project = self._extract_structured_dict(result, "create_project")

        # Add to cache
        if team_id in self._projects_cache:
            self._projects_cache[team_id].append(project)
        else:
            self._projects_cache[team_id] = [project]

        return project

    async def _call_tool(self, name: str, arguments: JsonDict | None = None) -> CallToolResult:
        session = await self._ensure_session()
        try:
            return await session.call_tool(name=name, arguments=arguments)
        except McpError as exc:
            raise LinearMCPError(f"MCP tool '{name}' failed: {exc}") from exc
        except TimeoutError as exc:  # pragma: no cover - depends on network conditions
            raise LinearMCPError(f"MCP tool '{name}' timed out") from exc
        except Exception as exc:  # pragma: no cover - defensive
            raise LinearMCPError(f"Unexpected MCP error for tool '{name}': {exc}") from exc

    @staticmethod
    def _extract_structured_list(result: CallToolResult, tool_name: str) -> list[JsonDict]:
        # Try structuredContent first
        payload = result.structuredContent
        if isinstance(payload, list):
            dict_items = [item for item in payload if isinstance(item, dict)]
            if dict_items:
                return dict_items
        elif isinstance(payload, dict):
            for key in ("content", "items", "nodes", "data"):
                nested = payload.get(key)
                if isinstance(nested, list):
                    dict_items = [item for item in nested if isinstance(item, dict)]
                    if dict_items:
                        return dict_items

        # Linear MCP returns JSON in text content
        if result.content and len(result.content) > 0:
            first_content = result.content[0]
            if isinstance(first_content, TextContent) and first_content.text:
                try:
                    parsed = json.loads(first_content.text)
                    if isinstance(parsed, list):
                        dict_items = [item for item in parsed if isinstance(item, dict)]
                        if dict_items:
                            return dict_items
                    elif isinstance(parsed, dict):
                        # Check for nested arrays (Linear API uses "content" key)
                        for key in ("content", "items", "nodes", "data"):
                            nested = parsed.get(key)
                            if isinstance(nested, list):
                                dict_items = [item for item in nested if isinstance(item, dict)]
                                if dict_items:
                                    return dict_items
                except (json.JSONDecodeError, AttributeError):
                    pass

        raise LinearMCPError(f"Tool '{tool_name}' did not return a structured list payload")

    @staticmethod
    def _extract_structured_dict(result: CallToolResult, tool_name: str) -> JsonDict:
        # Try structuredContent first
        payload = result.structuredContent
        if isinstance(payload, dict):
            return payload
        if isinstance(payload, list) and payload and isinstance(payload[0], dict):
            return payload[0]

        # Linear MCP returns JSON in text content
        if result.content and len(result.content) > 0:
            first_content = result.content[0]
            if isinstance(first_content, TextContent) and first_content.text:
                try:
                    parsed = json.loads(first_content.text)
                    if isinstance(parsed, dict):
                        return parsed
                    if isinstance(parsed, list) and parsed and isinstance(parsed[0], dict):
                        return parsed[0]
                except (json.JSONDecodeError, AttributeError):
                    pass

        raise LinearMCPError(f"Tool '{tool_name}' did not return structured JSON data")

    @staticmethod
    def _match_record(records: Sequence[JsonDict], expected: str, entity_label: str) -> JsonDict:
        needle = expected.strip().lower()
        for record in records:
            for key in ("name", "title", "key", "slug"):
                value = record.get(key)
                if isinstance(value, str) and value.strip().lower() == needle:
                    return record

        available = ", ".join(
            sorted(
                {
                    str(record.get("name") or record.get("title") or record.get("key") or record.get("slug"))
                    for record in records
                    if any(record.get(field) for field in ("name", "title", "key", "slug"))
                }
            )
        )
        raise LinearMCPError(f"Could not find {entity_label} '{expected}'. Available options: {available}")


def _record_id(record: JsonDict) -> str:
    for key in ("id", "teamId", "projectId", "templateId", "identifier"):
        if key in record and record[key]:
            return str(record[key])
    raise LinearMCPError(f"Record is missing an identifier field: {record!r}")
