# Linear Issue Maker

A Python CLI that creates Linear issues from CSV files using either the Linear MCP server or direct GraphQL API.

## Features

- **Batch CSV import** - Create multiple issues from spreadsheet exports
- **Template support** - Apply Linear issue templates (API mode)
- **Dual client modes** - Use MCP server or GraphQL API
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
   export LINEAR_ACCESS_TOKEN=lin_api_xxxxxxxxx
   ```
   Or add it to `.env`:
   ```
   LINEAR_ACCESS_TOKEN=lin_api_xxxxxxxxx
   ```

3. Create issues from CSV:
   ```bash
   # Basic usage (auto-detects client mode)
   linear-issue-maker -i examples/issues.csv

   # With templates (automatically uses API mode)
   linear-issue-maker -i examples/issues_with_templates.csv
   ```

## Usage

### CSV Format

#### Basic Format (4 columns - MCP mode)
Create a CSV file with columns: `Team`, `Project`, `Title`, `Summary`

```csv
Team,Project,Title,Summary
The A Team,User Project,User Sign Up,"As a user, I want to sign up with email and password."
The A Team,Admin Project,Admin Portal Icon,"As an admin, I want a silly icon and affirming statement to greet me in the portal every day."
```

#### With Templates (5 columns - API mode)
Add an optional `Template` column to apply Linear issue templates:

```csv
Team,Project,Title,Summary,Template
Engineering,Backend,Add authentication,"Implement JWT-based auth system",Feature Template
Engineering,Backend,Fix login bug,"Users can't log in with special characters",Bug Template
Engineering,Frontend,Update dashboard,"Redesign the main dashboard UI",
```

**Note:** The 5th column can be empty for specific rows. Templates are matched by name (case-insensitive).

### Commands

```bash
# Create all issues (auto-detects mode based on Template column)
linear-issue-maker -i issues.csv

# Preview issues before creating (dry-run, shows detected client mode)
linear-issue-maker -i issues.csv --dry-run

# Force specific client mode
linear-issue-maker -i issues.csv --client-mode api
linear-issue-maker -i issues.csv --client-mode mcp

# Auto-create missing projects
linear-issue-maker -i issues.csv --create-missing-projects

# Continue even if some issues fail
linear-issue-maker -i issues.csv --continue-on-error

# Use tab-separated values
linear-issue-maker -i issues.tsv --delimiter $'\t'
```

## Configuration

### Client Modes

The tool supports two client modes:

1. **MCP Mode** (`--client-mode mcp`)
   - Uses Linear's MCP server
   - Simpler, managed API
   - Does NOT support templates

2. **API Mode** (`--client-mode api`)
   - Direct GraphQL API access
   - Supports issue templates
   - Full control over API parameters

3. **Auto Mode** (`--client-mode auto`, default)
   - Automatically selects mode based on CSV
   - Uses API mode if Template column has any values
   - Falls back to MCP mode otherwise

### Environment Variables

**Universal (works for both modes):**
- `LINEAR_ACCESS_TOKEN`: Your Linear API token (recommended)
- `LINEAR_TOKEN_PATH`: Alternative - path to file containing token

**MCP-specific:**
- `LINEAR_MCP_ACCESS_TOKEN`: MCP server token (deprecated, use LINEAR_ACCESS_TOKEN)
- `LINEAR_MCP_SERVER_URL`: Override MCP endpoint (default: `https://mcp.linear.app/sse`)

**API-specific:**
- `LINEAR_API_ACCESS_TOKEN`: GraphQL API token (deprecated, use LINEAR_ACCESS_TOKEN)
- `LINEAR_API_URL`: Override GraphQL endpoint (default: `https://api.linear.app/graphql`)

**Template Mappings (API mode only):**

You can map template names to specific template IDs using environment variables. This is useful when you have multiple templates with the same name and want to control which one is used.

Format: `LINEAR_TEMPLATE_<NAME>=<template-id>`

Example:
```bash
export LINEAR_TEMPLATE_STORY=5e6f00c2-c508-477c-a0cc-1eb6b48d865e
export LINEAR_TEMPLATE_BUG=a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

Or in `.env`:
```
LINEAR_TEMPLATE_STORY=5e6f00c2-c508-477c-a0cc-1eb6b48d865e
LINEAR_TEMPLATE_BUG=a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

When a template mapping is set, it takes precedence over auto-detection from the Linear API.

### CLI Flags

Override environment variables:
- `--client-mode`: Select client mode (mcp, api, auto)
- `--token`: Linear API token
- `--token-path`: Path to token file
- `--server-url`: MCP server endpoint (MCP mode only)
- `--api-url`: GraphQL API endpoint (API mode only)
