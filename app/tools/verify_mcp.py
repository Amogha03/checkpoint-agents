"""
MCP Server Verification Script
Standalone script to test Filesystem and GitHub MCP server connections.
Verifies that both servers respond to tools/list calls.
"""

import asyncio
import logging
import os
import sys

from dotenv import load_dotenv

from app.tools.mcp_client import MCPClientManager

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def verify_mcp_servers() -> bool:
    """
    Verify MCP server connections and list available tools.

    Returns:
        True if both servers connected and responded successfully, False otherwise.
    """
    print("\n" + "=" * 80)
    print(" 🔍 MCP SERVER VERIFICATION ".center(80))
    print("=" * 80 + "\n")

    filesystem_root = os.getenv("FILESYSTEM_MCP_ROOT", "/tmp/workspaces")
    github_token = os.getenv("GITHUB_PERSONAL_ACCESS_TOKEN", "")

    print(f"Configuration:")
    print(f"  Filesystem Root: {filesystem_root}")
    print(f"  GitHub Token: {'✓ Set' if github_token else '✗ Not set (optional)'}\n")

    manager = MCPClientManager(
        filesystem_root=filesystem_root,
        github_token=github_token,
    )

    try:
        # Connect to both servers
        print("Connecting to MCP servers...")
        await manager.connect()
        print("✓ Connected to both servers\n")

        # List Filesystem tools
        print("=" * 80)
        print(" FILESYSTEM MCP SERVER TOOLS ".center(80))
        print("=" * 80)
        try:
            filesystem_tools = await manager.list_filesystem_tools()
            print(f"\n✓ Found {len(filesystem_tools)} tools:\n")
            for tool in filesystem_tools:
                print(f"  • {tool.name}")
                if tool.description:
                    print(f"    └─ {tool.description}")
            filesystem_success = True
        except Exception as e:
            print(f"\n✗ Error listing Filesystem tools: {e}")
            filesystem_success = False

        # List GitHub tools
        print("\n" + "=" * 80)
        print(" GITHUB MCP SERVER TOOLS ".center(80))
        print("=" * 80)
        try:
            github_tools = await manager.list_github_tools()
            print(f"\n✓ Found {len(github_tools)} tools:\n")
            for tool in github_tools:
                print(f"  • {tool.name}")
                if tool.description:
                    print(f"    └─ {tool.description}")
            github_success = True
        except Exception as e:
            print(f"\n✗ Error listing GitHub tools: {e}")
            github_success = False

        # Summary
        print("\n" + "=" * 80)
        print(" VERIFICATION SUMMARY ".center(80))
        print("=" * 80 + "\n")

        filesystem_status = "✅ PASS" if filesystem_success else "❌ FAIL"
        github_status = "✅ PASS" if github_success else "❌ FAIL"

        print(f"  Filesystem MCP Server: {filesystem_status}")
        print(f"  GitHub MCP Server:     {github_status}")

        overall_success = filesystem_success and github_success
        overall_status = "✅ ALL SYSTEMS OPERATIONAL" if overall_success else "⚠️  PARTIAL FAILURE"

        print(f"\n  Overall Status: {overall_status}\n")
        print("=" * 80 + "\n")

        return overall_success

    except Exception as e:
        logger.error(f"Verification failed with exception: {e}", exc_info=True)
        print(f"\n✗ Verification failed: {e}\n")
        return False

    finally:
        # Cleanup
        await manager.close()


def main() -> int:
    """
    Main entry point for verification script.

    Returns:
        0 if verification succeeded, 1 otherwise.
    """
    try:
        success = asyncio.run(verify_mcp_servers())
        return 0 if success else 1
    except KeyboardInterrupt:
        print("\n\n⏸  Verification interrupted by user\n")
        return 1
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        print(f"\n✗ Unexpected error: {e}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
