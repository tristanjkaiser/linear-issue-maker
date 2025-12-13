"""Utilities for turning text blocks into structured Linear issue specifications."""

from __future__ import annotations

import csv
import re
from io import StringIO
from typing import Dict

from pydantic import BaseModel, ValidationInfo, field_validator

_HEADER_PATTERN = re.compile(r"^(?P<key>[A-Za-z]+):\s*(?P<value>.*)$")
_VALID_HEADERS = {"team", "project", "title", "summary"}
_REQUIRED_HEADERS = {"team", "project", "title", "summary"}


class IssueSpec(BaseModel):
    """Structured issue data parsed from the user's text block."""

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


def parse_issue_spec(raw_text: str) -> IssueSpec:
    """Parse the incoming text and return a structured :class:`IssueSpec`.

    The expected format is simple ``Header: value`` pairs for Team, Project,
    and Title. ``Summary:`` marks the start of a free-form body that extends to EOF.
    """

    if not raw_text.strip():
        raise ValueError("Input text is empty")

    values: Dict[str, str] = {}
    summary_lines: list[str] = []
    in_summary = False

    for line in raw_text.splitlines():
        if not in_summary:
            match = _HEADER_PATTERN.match(line.strip())
            if match:
                key = match.group("key").lower()
                value = match.group("value")
                if key not in _VALID_HEADERS:
                    raise ValueError(f"Unknown header '{match.group('key')}'")
                if key == "summary":
                    in_summary = True
                    if value:
                        summary_lines.append(value)
                else:
                    if key in values:
                        raise ValueError(f"Duplicate header '{match.group('key')}'")
                    values[key] = value.strip()
            elif not line.strip():
                continue
            else:
                raise ValueError(f"Unexpected content before Summary: '{line}'")
        else:
            summary_lines.append(line)

    if not in_summary:
        raise ValueError("Missing 'Summary' section")

    values["summary"] = "\n".join(summary_lines).strip()

    missing = _REQUIRED_HEADERS - values.keys()
    if missing:
        missing_headers = ", ".join(sorted(missing))
        raise ValueError(f"Missing headers: {missing_headers}")

    return IssueSpec(**values)


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
