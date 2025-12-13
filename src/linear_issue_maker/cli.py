"""Command-line interface for the Linear Issue Maker."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import anyio
import typer
from rich import print_json

from .mcp_client import LinearMCPClient, LinearMCPError
from .parser import IssueSpec, parse_csv_specs, parse_issue_spec
from .settings import LinearMCPConfig

app = typer.Typer(help="Turn structured text into Linear issues via MCP.")


def _read_text(source: Optional[Path]) -> str:
    if source:
        return source.read_text(encoding="utf-8")
    return typer.get_text_stream("stdin").read()


def _echo_spec(spec: IssueSpec) -> None:
    print_json(data=spec.model_dump())


@app.command()
def parse(
    input_file: Optional[Path] = typer.Option(
        None,
        "--input",
        "-i",
        exists=True,
        dir_okay=False,
        readable=True,
        help="Path to the text block file. Reads stdin when omitted.",
    ),
) -> None:
    """Parse the input and output the structured representation."""

    raw_text = _read_text(input_file)
    spec = parse_issue_spec(raw_text)
    _echo_spec(spec)


@app.command()
def create(
    input_file: Optional[Path] = typer.Option(
        None,
        "--input",
        "-i",
        exists=True,
        dir_okay=False,
        readable=True,
        help="Path to the text block file. Reads stdin when omitted.",
    ),
    dry_run: bool = typer.Option(True, help="When true, only parse and display the payload."),
    server_url: Optional[str] = typer.Option(
        None,
        "--server-url",
        envvar="LINEAR_MCP_SERVER_URL",
        help="Override the Linear MCP URL (default points to hosted service).",
    ),
    token: Optional[str] = typer.Option(
        None,
        "--token",
        envvar="LINEAR_MCP_ACCESS_TOKEN",
        help="Bearer token returned by `codex mcp login linear`.",
    ),
    token_path: Optional[Path] = typer.Option(
        None,
        "--token-path",
        envvar="LINEAR_MCP_TOKEN_PATH",
        exists=True,
        dir_okay=False,
        readable=True,
        resolve_path=True,
        help="Path to a file that stores the bearer token (alternative to --token).",
    ),
) -> None:
    """Create a Linear issue via MCP (dry-run by default)."""

    raw_text = _read_text(input_file)
    spec = parse_issue_spec(raw_text)
    if dry_run:
        typer.echo("Dry run – parsed payload:")
        _echo_spec(spec)
        raise typer.Exit(code=0)

    config_kwargs: dict[str, Any] = {}
    if server_url is not None:
        config_kwargs["server_url"] = server_url
    if token is not None:
        config_kwargs["access_token"] = token
    if token_path is not None:
        config_kwargs["token_path"] = token_path

    try:
        config = LinearMCPConfig(**config_kwargs)
    except Exception as exc:  # pragma: no cover - depends on user env
        typer.secho(f"Failed to load MCP configuration: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    async def _run() -> dict[str, Any]:
        async with LinearMCPClient(config) as client:
            identifiers = await client.resolve_identifiers(spec.team, spec.project)
            issue = await client.create_issue(spec, identifiers)
            return issue

    try:
        issue_payload = anyio.run(_run)
    except LinearMCPError as exc:
        typer.secho(f"MCP error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    typer.echo("Successfully created issue via Linear MCP:")
    print_json(data=issue_payload)


@app.command()
def batch_csv(
    input_file: Optional[Path] = typer.Option(
        None,
        "--input",
        "-i",
        exists=True,
        dir_okay=False,
        readable=True,
        help="Path to the CSV file. Reads stdin when omitted.",
    ),
    dry_run: bool = typer.Option(True, help="When true, only parse and display the issues."),
    delimiter: str = typer.Option(",", help="CSV delimiter character (default: comma)."),
    continue_on_error: bool = typer.Option(
        False,
        help="Continue processing remaining issues if one fails.",
    ),
    progress: bool = typer.Option(True, help="Show progress bar during batch creation."),
    server_url: Optional[str] = typer.Option(
        None,
        "--server-url",
        envvar="LINEAR_MCP_SERVER_URL",
        help="Override the Linear MCP URL.",
    ),
    token: Optional[str] = typer.Option(
        None,
        "--token",
        envvar="LINEAR_MCP_ACCESS_TOKEN",
        help="Bearer token for Linear MCP.",
    ),
    token_path: Optional[Path] = typer.Option(
        None,
        "--token-path",
        envvar="LINEAR_MCP_TOKEN_PATH",
        exists=True,
        dir_okay=False,
        readable=True,
        resolve_path=True,
        help="Path to file containing bearer token.",
    ),
) -> None:
    """Create multiple Linear issues from a CSV file."""

    # Read and parse CSV
    csv_text = _read_text(input_file)

    try:
        specs = parse_csv_specs(csv_text, delimiter=delimiter)
    except ValueError as exc:
        typer.secho(f"CSV parsing error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(f"Parsed {len(specs)} issue(s) from CSV")

    if dry_run:
        typer.echo("\nDry run – parsed issues:")
        for i, spec in enumerate(specs, 1):
            typer.echo(f"\n{i}. {spec.title}")
            typer.echo(f"   Team: {spec.team}")
            typer.echo(f"   Project: {spec.project}")
            typer.echo(f"   Summary: {spec.summary[:100]}{'...' if len(spec.summary) > 100 else ''}")
        raise typer.Exit(code=0)

    # Build config
    config_kwargs: dict[str, Any] = {}
    if server_url is not None:
        config_kwargs["server_url"] = server_url
    if token is not None:
        config_kwargs["access_token"] = token
    if token_path is not None:
        config_kwargs["token_path"] = token_path

    try:
        config = LinearMCPConfig(**config_kwargs)
    except Exception as exc:  # pragma: no cover
        typer.secho(f"Failed to load MCP configuration: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    # Create issues
    async def _run_batch() -> tuple[list[dict[str, Any]], list[tuple[IssueSpec, str]]]:
        created: list[dict[str, Any]] = []
        failed: list[tuple[IssueSpec, str]] = []

        async with LinearMCPClient(config) as client:
            for i, spec in enumerate(specs, 1):
                if progress:
                    typer.echo(f"[{i}/{len(specs)}] Creating: {spec.title}")

                try:
                    identifiers = await client.resolve_identifiers(spec.team, spec.project)
                    issue = await client.create_issue(spec, identifiers)
                    created.append(issue)

                    if progress:
                        issue_id = issue.get("identifier", issue.get("id", "unknown"))
                        issue_url = issue.get("url", "")
                        typer.secho(f"  ✓ Created {issue_id}: {issue_url}", fg=typer.colors.GREEN)

                except LinearMCPError as exc:
                    error_msg = str(exc)
                    failed.append((spec, error_msg))

                    if progress:
                        typer.secho(f"  ✗ Failed: {error_msg}", fg=typer.colors.RED, err=True)

                    if not continue_on_error:
                        raise

        return created, failed

    try:
        created_issues, failed_issues = anyio.run(_run_batch)
    except LinearMCPError as exc:
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


if __name__ == "__main__":
    app()
