# Linear Issue Maker

A Python CLI that creates Linear issues from CSV files via the Linear MCP server.

## Features

- **Batch CSV import** - Create multiple issues from spreadsheet exports
- **Auto-create projects** - Automatically create projects if they don't exist
- **Dry-run mode** - Preview issues before creating
- **Progress tracking** - Real-time progress during batch operations
- **Error handling** - Continue-on-error support with detailed reporting

## Installation

1. Ensure Python 3.11+ is available
2. Clone this repository
3. Create a virtual environment: `python -m venv venv && source venv/bin/activate`
4. Install: `pip install -e .`

## Quick Start

1. Get your Linear API token from [Linear Settings → API](https://linear.app/settings/api)
2. Set the token in your environment:
   ```bash
   export LINEAR_MCP_ACCESS_TOKEN=lin_api_xxxxxxxxx
   ```
   Or add it to `.env`:
   ```
   LINEAR_MCP_ACCESS_TOKEN=lin_api_xxxxxxxxx
   ```

3. Create issues from CSV:
   ```bash
   linear-issue-maker create -i examples/issues.csv --no-dry-run
   ```

## Usage

### CSV Format

Create a CSV file with columns: `Team`, `Project`, `Title`, `Summary`

```csv
Team,Project,Title,Summary
The A Team,User Project,User Sign Up,"As a user, I want to sign up with email and password."
The A Team,Admin Project,Admin Portal Icon,"As an admin, I want a silly icon and affirming statement to greet me in the portal every day."
```

### Commands

```bash
# Preview issues (dry-run)
linear-issue-maker create -i issues.csv

# Create all issues
linear-issue-maker create -i issues.csv --no-dry-run

# Auto-create missing projects
linear-issue-maker create -i issues.csv --no-dry-run --create-missing-projects

# Continue even if some issues fail
linear-issue-maker create -i issues.csv --no-dry-run --continue-on-error

# Use tab-separated values
linear-issue-maker create -i issues.tsv --delimiter $'\t' --no-dry-run
```

## Configuration

Environment variables:
- `LINEAR_MCP_ACCESS_TOKEN`: Your Linear API token (required)
- `LINEAR_MCP_TOKEN_PATH`: Alternative - path to file containing token
- `LINEAR_MCP_SERVER_URL`: Override default endpoint (default: `https://mcp.linear.app/sse`)

CLI flags override environment variables:
- `--token`: Bearer token
- `--token-path`: Path to token file
- `--server-url`: MCP server endpoint
