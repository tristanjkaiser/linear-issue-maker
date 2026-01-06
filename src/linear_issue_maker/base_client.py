"""Abstract base interface for Linear clients (MCP and GraphQL API)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from .parser import IssueSpec

JsonDict = dict[str, Any]


class LinearIdentifiers:
    """Resolved Linear entities required to create an issue."""

    def __init__(self, team: JsonDict, project: JsonDict) -> None:
        self.team = team
        self.project = project

    @property
    def team_id(self) -> str:
        """Extract team ID from team record."""
        return self._extract_id(self.team)

    @property
    def project_id(self) -> str:
        """Extract project ID from project record."""
        return self._extract_id(self.project)

    @staticmethod
    def _extract_id(record: JsonDict) -> str:
        """Extract ID from a Linear record."""
        for key in ("id", "teamId", "projectId", "identifier"):
            if key in record and record[key]:
                return str(record[key])
        raise ValueError(f"Record is missing an identifier field: {record!r}")


class LinearClient(ABC):
    """Abstract base class for Linear API clients."""

    @abstractmethod
    async def __aenter__(self) -> "LinearClient":
        """Enter async context manager."""
        ...

    @abstractmethod
    async def __aexit__(self, exc_type, exc, tb) -> None:  # type: ignore[override]
        """Exit async context manager."""
        ...

    @abstractmethod
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
            Exception: If team or project cannot be resolved/created
        """
        ...

    @abstractmethod
    async def create_issue(self, spec: IssueSpec, identifiers: LinearIdentifiers) -> JsonDict:
        """Create an issue using the supplied identifiers and spec.

        Args:
            spec: Issue specification from CSV
            identifiers: Resolved team and project IDs

        Returns:
            Created issue record from Linear

        Raises:
            Exception: If issue creation fails
        """
        ...
