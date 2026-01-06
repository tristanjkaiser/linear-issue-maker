"""Linear GraphQL API client implementation."""

from __future__ import annotations

import json
from typing import Any

import httpx

from .base_client import LinearClient, LinearIdentifiers
from .parser import IssueSpec

JsonDict = dict[str, Any]


class LinearGraphQLError(RuntimeError):
    """Domain-specific error for GraphQL API failures."""


class LinearGraphQLClient(LinearClient):
    """Direct GraphQL API client for Linear with template support."""

    def __init__(
        self,
        api_url: str,
        access_token: str,
        *,
        http_timeout: float = 30.0,
    ) -> None:
        self.api_url = api_url
        self.access_token = access_token
        self.http_timeout = http_timeout
        self._client: httpx.AsyncClient | None = None

        # Simple caches to avoid duplicate lookups within a single CLI invocation
        self._teams_cache: list[JsonDict] | None = None
        self._projects_cache: dict[str, list[JsonDict]] = {}

    async def __aenter__(self) -> "LinearGraphQLClient":
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(self.http_timeout),
            headers={
                "Authorization": self.access_token,
                "Content-Type": "application/json",
            },
        )
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:  # type: ignore[override]
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def resolve_identifiers(
        self, team: str, project: str, *, create_missing_projects: bool = False
    ) -> LinearIdentifiers:
        """Resolve team and project names into structured records."""
        team_record = await self._resolve_team(team)
        project_record = await self._resolve_project(
            project, team_record, create_if_missing=create_missing_projects
        )
        return LinearIdentifiers(team=team_record, project=project_record)

    async def create_issue(self, spec: IssueSpec, identifiers: LinearIdentifiers) -> JsonDict:
        """Create an issue using the GraphQL API with optional template support."""
        mutation = """
        mutation IssueCreate($input: IssueCreateInput!) {
            issueCreate(input: $input) {
                success
                issue {
                    id
                    identifier
                    title
                    description
                    url
                    createdAt
                }
            }
        }
        """

        variables: JsonDict = {
            "input": {
                "teamId": identifiers.team_id,
                "projectId": identifiers.project_id,
                "title": spec.title,
                "description": spec.summary,
            }
        }

        # Add template if specified
        if spec.template:
            # First try to resolve template by name
            template_id = await self._resolve_template(spec.template, identifiers.team_id)
            if template_id:
                variables["input"]["templateId"] = template_id
            # Note: If template not found, we continue without it (graceful degradation)

        result = await self._execute_graphql(mutation, variables)

        if not result.get("issueCreate", {}).get("success"):
            raise LinearGraphQLError("Issue creation failed")

        issue = result["issueCreate"]["issue"]
        if not issue:
            raise LinearGraphQLError("No issue returned from creation")

        return issue

    async def _resolve_team(self, team_name: str) -> JsonDict:
        """Resolve team by name or ID."""
        teams = await self._list_teams()
        return self._match_record(teams, team_name, "team")

    async def _resolve_project(
        self, project_name: str, team: JsonDict, create_if_missing: bool = False
    ) -> JsonDict:
        """Resolve project by name, optionally creating it if not found."""
        team_id = team["id"]
        projects = await self._list_projects(team_id)

        try:
            return self._match_record(projects, project_name, "project")
        except LinearGraphQLError:
            if not create_if_missing:
                raise

            # Project not found, create it
            team_name = team.get("name", team_id)
            return await self._create_project(project_name, team_id, team_name)

    async def _resolve_template(self, template_name: str, team_id: str) -> str | None:
        """Resolve template by name to get its ID.

        Returns:
            Template ID if found, None otherwise (allows creation without template)
        """
        # Query templates through team - Linear's templates are workspace-wide
        # but we query through the team for context
        query = """
        query Templates {
            templates {
                id
                name
                type
                teamId
            }
        }
        """

        try:
            result = await self._execute_graphql(query, {})
            templates = result.get("templates", [])

            # Match by name (case-insensitive), optionally filter by team
            needle = template_name.strip().lower()
            for template in templates:
                if template.get("name", "").strip().lower() == needle:
                    # Prefer templates matching the team, but accept any match
                    if template.get("teamId") == team_id:
                        return template["id"]

            # Try again without team filter
            for template in templates:
                if template.get("name", "").strip().lower() == needle:
                    return template["id"]

            # Template not found - return None to create issue without template
            return None

        except Exception:
            # If template resolution fails, continue without template
            return None

    async def _list_teams(self) -> list[JsonDict]:
        """List all teams."""
        if self._teams_cache is not None:
            return self._teams_cache

        query = """
        query Teams {
            teams {
                nodes {
                    id
                    name
                    key
                }
            }
        }
        """

        result = await self._execute_graphql(query, {})
        teams = result.get("teams", {}).get("nodes", [])
        self._teams_cache = teams
        return teams

    async def _list_projects(self, team_id: str) -> list[JsonDict]:
        """List projects for a team."""
        if team_id in self._projects_cache:
            return self._projects_cache[team_id]

        query = """
        query Projects($teamId: String!) {
            team(id: $teamId) {
                projects {
                    nodes {
                        id
                        name
                    }
                }
            }
        }
        """

        result = await self._execute_graphql(query, {"teamId": team_id})
        projects = result.get("team", {}).get("projects", {}).get("nodes", [])
        self._projects_cache[team_id] = projects
        return projects

    async def _create_project(self, name: str, team_id: str, team_name: str) -> JsonDict:
        """Create a new project in Linear."""
        mutation = """
        mutation CreateProject($input: ProjectCreateInput!) {
            projectCreate(input: $input) {
                success
                project {
                    id
                    name
                }
            }
        }
        """

        variables = {
            "input": {
                "name": name,
                "teamIds": [team_id],
                "color": "#bec2c8",  # Default gray color
            }
        }

        result = await self._execute_graphql(mutation, variables)

        if not result.get("projectCreate", {}).get("success"):
            raise LinearGraphQLError(f"Failed to create project '{name}' in team '{team_name}'")

        project = result["projectCreate"]["project"]
        if not project:
            raise LinearGraphQLError("No project returned from creation")

        # Add to cache
        if team_id in self._projects_cache:
            self._projects_cache[team_id].append(project)
        else:
            self._projects_cache[team_id] = [project]

        return project

    async def _execute_graphql(self, query: str, variables: JsonDict | None = None) -> JsonDict:
        """Execute a GraphQL query/mutation."""
        if self._client is None:
            raise LinearGraphQLError("Client not initialized - use async context manager")

        payload = {"query": query}
        if variables:
            payload["variables"] = variables

        try:
            response = await self._client.post(self.api_url, json=payload)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise LinearGraphQLError(
                f"HTTP {exc.response.status_code}: {exc.response.text}"
            ) from exc
        except httpx.TimeoutException as exc:
            raise LinearGraphQLError("Request timed out") from exc
        except Exception as exc:
            raise LinearGraphQLError(f"Request failed: {exc}") from exc

        try:
            data = response.json()
        except json.JSONDecodeError as exc:
            raise LinearGraphQLError(f"Invalid JSON response: {response.text}") from exc

        # Check for GraphQL errors
        if "errors" in data:
            errors = data["errors"]
            error_messages = [e.get("message", str(e)) for e in errors]
            raise LinearGraphQLError(f"GraphQL errors: {', '.join(error_messages)}")

        if "data" not in data:
            raise LinearGraphQLError(f"No data in response: {data}")

        return data["data"]

    @staticmethod
    def _match_record(records: list[JsonDict], expected: str, entity_label: str) -> JsonDict:
        """Match a record by name, key, or slug (case-insensitive)."""
        needle = expected.strip().lower()

        for record in records:
            for key in ("name", "title", "key", "slug"):
                value = record.get(key)
                if isinstance(value, str) and value.strip().lower() == needle:
                    return record

        # Not found - provide helpful error
        available = ", ".join(
            sorted(
                {
                    str(record.get("name") or record.get("title") or record.get("key") or record.get("slug"))
                    for record in records
                    if any(record.get(field) for field in ("name", "title", "key", "slug"))
                }
            )
        )
        raise LinearGraphQLError(
            f"Could not find {entity_label} '{expected}'. Available options: {available}"
        )
