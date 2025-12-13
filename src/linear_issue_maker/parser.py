"""Utilities for parsing CSV files into structured Linear issue specifications."""

from __future__ import annotations

import csv
from io import StringIO

from pydantic import BaseModel, ValidationInfo, field_validator


class IssueSpec(BaseModel):
    """Structured issue data parsed from CSV."""

    team: str
    project: str
    title: str
    summary: str

    @field_validator("team", "project", "title", "summary")
    @classmethod
    def _non_empty(cls, value: str, info: ValidationInfo) -> str:  # type: ignore[override]
        if not value.strip():
            msg = f"Field '{info.field_name}' cannot be empty"
            raise ValueError(msg)
        return value.strip()


def parse_csv_specs(csv_text: str, delimiter: str = ",") -> list[IssueSpec]:
    """Parse CSV input and return a list of :class:`IssueSpec` objects.

    Expected columns: Team, Project, Title, Summary
    Additional columns are ignored for forward compatibility.

    Args:
        csv_text: The CSV content as a string
        delimiter: The delimiter character (default: comma)

    Returns:
        List of IssueSpec objects, one per valid row

    Raises:
        ValueError: If CSV is malformed or required columns are missing
    """
    if not csv_text.strip():
        raise ValueError("CSV input is empty")

    reader = csv.DictReader(StringIO(csv_text), delimiter=delimiter)

    # Validate required columns
    if not reader.fieldnames:
        raise ValueError("CSV has no header row")

    # Normalize column names (case-insensitive, strip whitespace)
    normalized_fieldnames = {name.strip().lower(): name for name in reader.fieldnames if name}
    required_cols = {"team", "project", "title", "summary"}
    missing_cols = required_cols - set(normalized_fieldnames.keys())

    if missing_cols:
        missing = ", ".join(sorted(missing_cols))
        available = ", ".join(sorted(normalized_fieldnames.keys()))
        raise ValueError(
            f"CSV is missing required columns: {missing}. Available columns: {available}"
        )

    # Map normalized names back to actual column names
    col_map = {
        "team": normalized_fieldnames["team"],
        "project": normalized_fieldnames["project"],
        "title": normalized_fieldnames["title"],
        "summary": normalized_fieldnames["summary"],
    }

    specs: list[IssueSpec] = []
    errors: list[str] = []

    for row_num, row in enumerate(reader, start=2):  # Start at 2 (1 is header)
        try:
            # Extract values using the mapped column names
            team = row.get(col_map["team"], "").strip()
            project = row.get(col_map["project"], "").strip()
            title = row.get(col_map["title"], "").strip()
            summary = row.get(col_map["summary"], "").strip()

            # Skip completely empty rows
            if not any([team, project, title, summary]):
                continue

            # Validate and create IssueSpec
            spec = IssueSpec(team=team, project=project, title=title, summary=summary)
            specs.append(spec)

        except ValueError as e:
            errors.append(f"Row {row_num}: {e}")

    if errors:
        error_msg = "CSV parsing errors:\n  " + "\n  ".join(errors)
        raise ValueError(error_msg)

    if not specs:
        raise ValueError("No valid issues found in CSV")

    return specs
