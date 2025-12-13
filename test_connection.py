#!/usr/bin/env python
"""Quick diagnostic script to test Linear MCP server connection."""

import asyncio
import os
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

from linear_issue_maker.settings import LinearMCPConfig
from linear_issue_maker.mcp_client import LinearMCPClient, LinearMCPError


async def test_connection():
    """Test basic connection to Linear MCP server."""

    print("=" * 60)
    print("Linear MCP Connection Diagnostic")
    print("=" * 60)

    try:
        # Create config - pydantic-settings will auto-load from .env
        config = LinearMCPConfig()
        print(f"\n✓ Token found (length: {len(config.access_token or '')} chars)")
        print(f"✓ Config loaded")
        print(f"  Server URL: {config.server_url}")
        print(f"  HTTP timeout: {config.http_timeout}s")
        print(f"  SSE read timeout: {config.sse_read_timeout}s")

        # Test connection
        print("\nAttempting to connect to Linear MCP server...")
        async with LinearMCPClient(config) as client:
            print("✓ Connection established")

            # Try listing teams
            print("\nFetching teams...")
            teams = await client._list_teams()
            print(f"✓ Found {len(teams)} team(s):")
            for team in teams:
                team_name = team.get("name") or team.get("key", "Unknown")
                team_id = team.get("id", "no-id")
                print(f"  - {team_name} (id: {team_id})")

            if teams:
                # Try listing projects for first team
                first_team = teams[0]
                team_id = first_team.get("id")
                if team_id:
                    print(f"\nFetching projects for team '{first_team.get('name')}'...")
                    projects = await client._list_projects(team_id)
                    print(f"✓ Found {len(projects)} project(s):")
                    for proj in projects[:5]:  # Show first 5
                        proj_name = proj.get("name") or proj.get("key", "Unknown")
                        print(f"  - {proj_name}")
                    if len(projects) > 5:
                        print(f"  ... and {len(projects) - 5} more")

        print("\n" + "=" * 60)
        print("✅ CONNECTION SUCCESSFUL!")
        print("=" * 60)
        return True

    except ValueError as e:
        print(f"\n❌ Configuration Error: {e}")
        return False
    except LinearMCPError as e:
        print(f"\n❌ Linear MCP Error: {e}")
        print("\nThis could mean:")
        print("  - Invalid or expired access token")
        print("  - Network connectivity issues")
        print("  - Linear MCP server is unreachable")
        return False
    except Exception as e:
        print(f"\n❌ Unexpected Error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(test_connection())
    sys.exit(0 if success else 1)
