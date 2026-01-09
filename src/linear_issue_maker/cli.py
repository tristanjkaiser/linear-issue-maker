"""Command-line interface for the Linear Issue Maker."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import anyio
import typer
from rich import print_json

from .client_factory import create_client, detect_mode_from_specs
from .graphql_client import LinearGraphQLError
from .mcp_client import LinearMCPError, _record_id
from .parser import IssueSpec, parse_csv_specs
from .settings import ClientMode

app = typer.Typer(
    help="Create Linear issues from CSV files via MCP or GraphQL API.",
    add_completion=True,
)


def _read_text(source: Optional[Path]) -> str:
    if source:
        return source.read_text(encoding="utf-8")
    return typer.get_text_stream("stdin").read()


@app.command(name="create")
def create(
    input_file: Optional[Path] = typer.Option(
        None,
        "--input",
        "-i",
        exists=True,
        dir_okay=False,
        readable=True,
        help="Path to the CSV file. Reads stdin when omitted.",
    ),
    dry_run: bool = typer.Option(False, help="When true, only parse and display the issues."),
    delimiter: str = typer.Option(",", help="CSV delimiter character (default: comma)."),
    create_missing_projects: bool = typer.Option(
        True,
        help="Automatically create projects if they don't exist.",
    ),
    continue_on_error: bool = typer.Option(
        False,
        help="Continue processing remaining issues if one fails.",
    ),
    progress: bool = typer.Option(True, help="Show progress during creation."),
    client_mode: ClientMode = typer.Option(
        ClientMode.AUTO,
        "--client-mode",
        help="Client mode: 'mcp' (MCP server), 'api' (GraphQL API with templates), 'auto' (detect from CSV).",
    ),
    server_url: Optional[str] = typer.Option(
        None,
        "--server-url",
        envvar="LINEAR_MCP_SERVER_URL",
        help="Override the Linear MCP URL (MCP mode only).",
    ),
    api_url: Optional[str] = typer.Option(
        None,
        "--api-url",
        envvar="LINEAR_API_URL",
        help="Override the Linear GraphQL API URL (API mode only).",
    ),
    token: Optional[str] = typer.Option(
        None,
        "--token",
        envvar="LINEAR_ACCESS_TOKEN",
        help="Linear API token (works for both MCP and API modes).",
    ),
    token_path: Optional[Path] = typer.Option(
        None,
        "--token-path",
        envvar="LINEAR_TOKEN_PATH",
        exists=True,
        dir_okay=False,
        readable=True,
        resolve_path=True,
        help="Path to file containing API token.",
    ),
) -> None:
    """Create Linear issues from a CSV file.

    Supports both MCP server and direct GraphQL API modes.
    Use --client-mode to select, or let 'auto' detect based on template usage.
    """

    # Read and parse CSV
    csv_text = _read_text(input_file)

    try:
        specs = parse_csv_specs(csv_text, delimiter=delimiter)
    except ValueError as exc:
        typer.secho(f"CSV parsing error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(f"Parsed {len(specs)} issue(s) from CSV")

    # Determine and display client mode
    detected_mode = detect_mode_from_specs(specs)
    actual_mode = client_mode if client_mode != ClientMode.AUTO else detected_mode

    if dry_run:
        mode_display = f"{actual_mode.value.upper()} mode"
        if client_mode == ClientMode.AUTO:
            mode_display += f" (auto-detected)"
        typer.echo(f"Client mode: {mode_display}\n")

        typer.echo("Dry run – parsed issues:")
        for i, spec in enumerate(specs, 1):
            typer.echo(f"\n{i}. {spec.title}")
            typer.echo(f"   Team: {spec.team}")
            typer.echo(f"   Project: {spec.project}")
            if spec.template:
                typer.echo(f"   Template: {spec.template}")
            typer.echo(f"   Summary: {spec.summary[:100]}{'...' if len(spec.summary) > 100 else ''}")
        raise typer.Exit(code=0)

    # Create client based on mode
    try:
        client = create_client(
            mode=client_mode,
            specs=specs,
            server_url=server_url,
            api_url=api_url,
            token=token,
            token_path=token_path,
        )
        # Display active mode
        actual_mode = detect_mode_from_specs(specs) if client_mode == ClientMode.AUTO else client_mode
        mode_display = f"{actual_mode.value.upper()}"
        if client_mode == ClientMode.AUTO:
            mode_display += " (auto-detected)"
        typer.echo(f"Using {mode_display} client\n")
    except Exception as exc:  # pragma: no cover
        typer.secho(f"Failed to create client: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    # Create issues
    async def _run_batch() -> tuple[list[dict[str, Any]], list[tuple[IssueSpec, str]]]:
        created: list[dict[str, Any]] = []
        failed: list[tuple[IssueSpec, str]] = []
        created_projects: set[str] = set()

        async with client:
            for i, spec in enumerate(specs, 1):
                if progress:
                    typer.echo(f"[{i}/{len(specs)}] Creating: {spec.title}")

                try:
                    # Check if we're creating a project
                    project_key = f"{spec.team}/{spec.project}"
                    if create_missing_projects and project_key not in created_projects:
                        # Try to resolve, which may create the project
                        identifiers = await client.resolve_identifiers(
                            spec.team, spec.project, create_missing_projects=True
                        )
                        # Track if this is a newly created project
                        if progress and spec.project not in [
                            p.get("name", "") for p in await client._list_projects(_record_id(identifiers.team))
                            if p.get("id") != identifiers.project.get("id")
                        ]:
                            created_projects.add(project_key)
                            typer.secho(
                                f"  → Created new project: {spec.project}",
                                fg=typer.colors.YELLOW,
                            )
                    else:
                        identifiers = await client.resolve_identifiers(
                            spec.team, spec.project, create_missing_projects=create_missing_projects
                        )

                    issue = await client.create_issue(spec, identifiers)
                    created.append(issue)

                    if progress:
                        issue_id = issue.get("identifier", issue.get("id", "unknown"))
                        issue_url = issue.get("url", "")
                        typer.secho(f"  ✓ Created {issue_id}: {issue_url}", fg=typer.colors.GREEN)

                except (LinearMCPError, LinearGraphQLError) as exc:
                    error_msg = str(exc)
                    failed.append((spec, error_msg))

                    if progress:
                        typer.secho(f"  ✗ Failed: {error_msg}", fg=typer.colors.RED, err=True)

                    if not continue_on_error:
                        raise

        return created, failed

    try:
        created_issues, failed_issues = anyio.run(_run_batch)
    except (LinearMCPError, LinearGraphQLError) as exc:
        typer.secho(f"\nBatch creation stopped due to error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    # Summary
    typer.echo(f"\n{'=' * 60}")
    typer.echo(f"Batch creation complete!")
    typer.echo(f"  Successfully created: {len(created_issues)}")
    typer.echo(f"  Failed: {len(failed_issues)}")

    if failed_issues:
        typer.echo(f"\n{'=' * 60}")
        typer.echo("Failed issues:")
        for spec, error in failed_issues:
            typer.secho(f"  • {spec.title}: {error}", fg=typer.colors.RED)

    if created_issues:
        typer.echo(f"\n{'=' * 60}")
        typer.echo("Created issues:")
        for issue in created_issues:
            issue_id = issue.get("identifier", issue.get("id", "unknown"))
            title = issue.get("title", "Untitled")
            url = issue.get("url", "")
            typer.secho(f"  • {issue_id}: {title}", fg=typer.colors.GREEN)
            if url:
                typer.echo(f"    {url}")

    # Exit with error code if any failed
    if failed_issues:
        raise typer.Exit(code=1)


def main() -> None:
    """Entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()
