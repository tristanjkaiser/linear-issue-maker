# Implementation Summary: Linear API Integration with Template Support

## Overview
Successfully integrated direct Linear GraphQL API support alongside the existing MCP implementation, enabling users to create issues with Linear templates via a 5th CSV column.

## What Was Built

### 1. Architecture Changes

#### New Base Client Interface ([base_client.py](src/linear_issue_maker/base_client.py))
- Abstract `LinearClient` class defining common interface
- `LinearIdentifiers` class for resolved team/project records
- Both MCP and GraphQL clients implement this interface

#### GraphQL API Client ([graphql_client.py](src/linear_issue_maker/graphql_client.py))
- Direct HTTP client using `httpx` for async GraphQL requests
- Template resolution by name (case-insensitive matching)
- Same caching strategy as MCP client for teams/projects
- Full GraphQL error handling and response parsing
- Supports all MCP features plus templates

#### Client Factory ([client_factory.py](src/linear_issue_maker/client_factory.py))
- `create_client()` function for mode-based client creation
- `detect_mode_from_specs()` for auto-detection logic
- Handles configuration for both client types
- Token fallback: tries API config, falls back to MCP token

### 2. Data Model Updates

#### IssueSpec Model ([parser.py](src/linear_issue_maker/parser.py))
- Added optional `template: str | None` field
- Template validator normalizes empty strings to None
- CSV parser updated to handle 5th column (optional)
- Backward compatible: 4-column CSVs still work

#### Settings ([settings.py](src/linear_issue_maker/settings.py))
- New `ClientMode` enum: MCP, API, AUTO
- New `LinearAPIConfig` for GraphQL API settings
- Separate environment variable prefixes:
  - `LINEAR_ACCESS_TOKEN` (universal)
  - `LINEAR_MCP_*` (MCP-specific)
  - `LINEAR_API_*` (API-specific)

### 3. CLI Enhancements ([cli.py](src/linear_issue_maker/cli.py))

#### New Options
- `--client-mode`: Select mcp, api, or auto (default: auto)
- `--api-url`: Override GraphQL API endpoint
- Updated `--token` to work for both modes

#### Auto-Detection Logic
- Scans all `IssueSpec` objects for templates
- If any spec has a template → API mode
- Otherwise → MCP mode
- Shows detected mode in output: "API mode (auto-detected)"

#### Output Changes
- Dry-run shows client mode and template column
- Live progress unchanged, works with both clients
- Error handling supports both `LinearMCPError` and `LinearGraphQLError`

### 4. Examples & Documentation

#### New Example ([examples/issues_with_templates.csv](examples/issues_with_templates.csv))
```csv
Team,Project,Title,Summary,Template
VisionaryASC–NGynS,Backend,Feature X,Description,Feature Template
```

#### Updated README
- Documented both CSV formats (4 and 5 columns)
- Explained client modes and auto-detection
- Environment variable reference updated
- Added template usage examples

## Key Features

### Template Support
- **Template matching**: By name, case-insensitive
- **Graceful degradation**: If template not found, creates issue without template
- **Mixed usage**: Some rows can have templates, others can be empty

### Client Mode Selection
1. **Auto Mode** (default):
   - Inspects CSV for Template column values
   - Switches to API mode if any templates present
   - User doesn't need to think about it

2. **Explicit Mode**:
   - `--client-mode api`: Force GraphQL API
   - `--client-mode mcp`: Force MCP server
   - Useful for testing or specific requirements

3. **Token Reuse**:
   - Same Linear API token works for both modes
   - Single `LINEAR_ACCESS_TOKEN` environment variable
   - Backward compatible with old variable names

## Technical Decisions

### Why Both Clients?
- **MCP**: Simple, managed, good for basic workflows
- **API**: Full control, templates, more parameters
- **User choice**: Let users pick based on needs

### Why Auto-Detection?
- **Zero configuration**: Templates "just work"
- **No breaking changes**: Old CSVs use MCP automatically
- **Explicit override**: Power users can force mode

### Why httpx?
- Async/await support (matches MCP client)
- Modern, well-maintained
- Simpler than GraphQL-specific libraries
- Direct control over requests

## Testing Results

### Auto-Detection
✅ CSV with templates → API mode (auto-detected)
✅ CSV without templates → MCP mode (auto-detected)

### Mode Override
✅ `--client-mode api` forces API mode
✅ `--client-mode mcp` forces MCP mode

### CSV Parsing
✅ 4-column CSV works (MCP mode)
✅ 5-column CSV works (API mode)
✅ Empty template values handled correctly

## Files Modified

### Core Implementation
- `src/linear_issue_maker/base_client.py` (new)
- `src/linear_issue_maker/graphql_client.py` (new)
- `src/linear_issue_maker/client_factory.py` (new)
- `src/linear_issue_maker/parser.py` (modified)
- `src/linear_issue_maker/settings.py` (modified)
- `src/linear_issue_maker/mcp_client.py` (modified - implements base class)
- `src/linear_issue_maker/cli.py` (modified - mode selection)

### Configuration
- `pyproject.toml` (added httpx dependency)

### Documentation & Examples
- `README.md` (comprehensive update)
- `examples/issues_with_templates.csv` (new)

## Migration Path

### For Existing Users
- **No changes required**: Old 4-column CSVs work as before
- **Old env vars work**: `LINEAR_MCP_ACCESS_TOKEN` still supported
- **Behavior unchanged**: MCP mode by default for old CSVs

### To Use Templates
1. Add 5th "Template" column to CSV
2. Fill in template names (or leave empty for some rows)
3. Run normally: `linear-issue-maker -i file.csv --no-dry-run`
4. Auto-detection handles the rest

## Future Enhancements

### Possible Additions
- Template ID support (in addition to name matching)
- More GraphQL mutation parameters (priority, labels, etc.)
- Batch template operations
- Template validation before issue creation
- Support for additional issue fields via API mode

### Not Implemented (By Design)
- MCP template support (MCP server doesn't expose this)
- Automatic template discovery/listing
- Template creation via CLI
