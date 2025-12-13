# Linear Issue Maker - Product Description

## Overview

Linear Issue Maker is a Python CLI tool that enables bulk creation of Linear issues from CSV files via Linear's Model Context Protocol (MCP) server. It was built to streamline the process of importing multiple issues into Linear, particularly when migrating from other systems, planning sprints, or batch-creating related stories.

## What It Does

The tool allows users to:

1. **Define issues in a spreadsheet** - Users create a CSV with columns: Team, Project, Title, Summary
2. **Validate before creation** - Dry-run mode previews all issues before creating them in Linear
3. **Batch create issues** - Automatically creates all issues with a single command
4. **Auto-create projects** - Optionally creates new projects if they don't exist yet
5. **Handle errors gracefully** - Continues processing remaining issues even if some fail, with detailed reporting

## How It Works

### Architecture

```
User's CSV File
      ↓
CSV Parser (Python stdlib)
      ↓
Pydantic Models (validation)
      ↓
Linear MCP Client (async)
      ↓
Linear MCP Server (HTTPS/SSE)
      ↓
Linear GraphQL API
      ↓
Linear Database
```

### Technical Components

#### 1. **CSV Parser** (`src/linear_issue_maker/parser.py`)
- Uses Python's built-in `csv.DictReader` for robust CSV parsing
- **Validation Features:**
  - Case-insensitive column matching (`Team`, `team`, `TEAM` all work)
  - Whitespace trimming on column names and values
  - Empty row skipping
  - Per-row error collection with line numbers
  - Required field validation via Pydantic
- **Output:** List of `IssueSpec` objects (Pydantic models with built-in validation)

#### 2. **MCP Client** (`src/linear_issue_maker/mcp_client.py`)
- **Protocol:** Connects to Linear's MCP server via Server-Sent Events (SSE) over HTTPS
- **Endpoint:** `https://mcp.linear.app/sse`
- **Authentication:** Bearer token (Linear Personal API Key)
- **Key Features:**
  - **Async/await architecture** using `anyio` for efficient I/O
  - **Connection pooling** - Single MCP session reused for all operations
  - **Result caching** - Teams/projects cached within a session to minimize API calls
  - **Auto-project creation** - Calls Linear's `create_project` tool when enabled
  - **Response parsing** - Handles Linear's JSON-in-text-content response format

**MCP Tools Used:**
- `list_teams` - Fetches all teams (cached)
- `list_projects` - Fetches projects for a team (cached per team)
- `create_project` - Creates new projects when needed
- `create_issue` - Creates individual issues

#### 3. **CLI Interface** (`src/linear_issue_maker/cli.py`)
- Built with **Typer** (modern Python CLI framework)
- **Single command:** `linear-issue-maker create`
- **Key Options:**
  - `--dry-run` (default: true) - Preview before creating
  - `--create-missing-projects` - Auto-create projects
  - `--continue-on-error` - Keep processing if individual issues fail
  - `--delimiter` - Support for tab-separated or custom delimiters
  - `--progress` - Real-time progress updates

**Progress Reporting:**
```
[1/5] Creating: User sign up
  → Created new project: Provider Profiles
  ✓ Created NGYNS-345: https://linear.app/...

[2/5] Creating: Password reset
  ✓ Created NGYNS-346: https://linear.app/...
```

#### 4. **Configuration System** (`src/linear_issue_maker/settings.py`)
- Built with **Pydantic Settings** for type-safe configuration
- **Configuration Sources** (in priority order):
  1. CLI flags (`--token`, `--server-url`)
  2. Environment variables (`LINEAR_MCP_ACCESS_TOKEN`)
  3. `.env` file (automatically loaded)
  4. Token file (`LINEAR_MCP_TOKEN_PATH`)
- **Validation:** Ensures token exists before attempting connection

### Data Flow

#### Single Issue Creation Flow

1. **Parse CSV Row**
   ```python
   {
     "team": "Engineering",
     "project": "Backend",
     "title": "Add user authentication",
     "summary": "Implement JWT-based auth..."
   }
   ```

2. **Validate with Pydantic**
   - Non-empty field checks
   - Type validation
   - Strip whitespace

3. **Resolve Identifiers**
   - Fetch teams → Find "Engineering" → Get ID
   - Fetch projects for team → Find "Backend" → Get ID
   - If project not found and `--create-missing-projects`:
     - Create project with Linear's `create_project` tool
     - Cache the new project

4. **Create Issue**
   - Build MCP tool arguments:
     ```json
     {
       "team": "<team-id>",
       "project": "<project-id>",
       "title": "Add user authentication",
       "description": "Implement JWT-based auth..."
     }
     ```
   - Call Linear's `create_issue` MCP tool
   - Parse response (JSON embedded in text content)

5. **Report Result**
   - Success: Display issue ID and URL
   - Failure: Display error, optionally continue

### Technical Innovations

#### 1. **MCP Protocol Handling**

**Challenge:** Linear's MCP server returns data in an unconventional format - JSON serialized as text within a `TextContent` object, rather than using `structuredContent`.

**Solution:** Custom extraction logic that:
- First checks `structuredContent` (MCP spec)
- Falls back to parsing `content[0].text` as JSON
- Handles nested response formats (`{content: [...]}` for lists)

```python
# Example: Handling Linear's response format
if isinstance(first_content, TextContent) and first_content.text:
    parsed = json.loads(first_content.text)
    if isinstance(parsed, dict) and "content" in parsed:
        return parsed["content"]  # Linear wraps in {content: [...]}
```

#### 2. **Efficient Caching Strategy**

**Problem:** Creating 100 issues in the same project would make 100 identical `list_projects` calls.

**Solution:** Three-level cache:
- **Team cache:** `list_teams` called once per session
- **Project cache:** `list_projects(team_id)` called once per team
- **Auto-created project cache:** Newly created projects added to cache immediately

**Impact:** For 100 issues in 2 projects across 1 team:
- Without caching: ~300 API calls
- With caching: ~3 API calls

#### 3. **Auto-Project Creation with Smart Detection**

**Problem:** How to avoid creating duplicate projects when processing multiple issues for the same new project?

**Solution:** Track project creation in-memory during batch:
```python
created_projects: set[str] = set()  # "Team/Project" keys

if project_key not in created_projects:
    # Attempt resolve (may create)
    identifiers = await client.resolve_identifiers(
        team, project, create_missing_projects=True
    )
    created_projects.add(project_key)
```

**Result:** For 10 issues all going to "New Project":
- Project created once
- Subsequent 9 issues reuse the created project from cache

### Error Handling & Resilience

#### Validation Errors (CSV Parsing)
- **Collected, not raised immediately** - All row errors gathered
- **Detailed reporting** - "Row 5: Field 'title' cannot be empty"
- **Partial validation** - Valid rows still processed

#### MCP/Network Errors
- **Per-issue try/catch** - One failure doesn't stop the batch
- **Error categorization:**
  - Team not found → Clear message with available teams
  - Project not found → Offer to create with flag
  - Connection timeout → Retry-able error message
- **Summary reporting** - "Created 8/10 issues" with failure details

### Dependencies

**Core:**
- `typer[all]>=0.12.3` - CLI framework with rich terminal output
- `pydantic>=2.7.0` - Data validation and settings management
- `rich>=13.7.1` - Terminal formatting and progress
- `mcp>=1.24.0` - Model Context Protocol client
- `anyio` - Async I/O (dependency of MCP)

**Development:**
- `pytest>=8.2.0` - Testing framework

**Standard Library:**
- `csv` - CSV parsing
- `asyncio` - Async runtime
- `pathlib` - File path handling


### Why not templates?
- **Linear MCP limitation** - `create_issue` tool doesn't support template parameter
- **Workaround** - Could be added via Labels or custom fields later

