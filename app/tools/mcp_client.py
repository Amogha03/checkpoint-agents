"""
MCP Client Manager for connecting to Filesystem and GitHub MCP servers.
Manages lifecycle of both stdio-based MCP server connections.
Provides LangChain-compatible tool wrappers for agent integration.
"""

import asyncio
import json
import logging
import os
import sys
from contextlib import asynccontextmanager
from typing import Optional, Any

from langchain_core.tools import tool
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.types import Tool

logger = logging.getLogger(__name__)

# Global manager instance for tool wrappers
_mcp_manager: Optional["MCPClientManager"] = None


class MCPClientManager:
    """
    Manages connections to multiple MCP servers via stdio transport.
    Handles startup, shutdown, and tool listing for both Filesystem and GitHub servers.
    """

    def __init__(
        self,
        filesystem_root: str = "/tmp/workspaces",
        github_token: Optional[str] = None,
    ):
        """
        Initialize the MCP Client Manager.

        Args:
            filesystem_root: Root directory for Filesystem MCP server access.
            github_token: GitHub Personal Access Token for GitHub MCP server.
        """
        self.filesystem_root = filesystem_root
        self.github_token = github_token or os.getenv("GITHUB_PERSONAL_ACCESS_TOKEN", "")

        # Session containers
        self.filesystem_session: Optional[ClientSession] = None
        self.github_session: Optional[ClientSession] = None

        # Context managers for cleanup
        self._fs_cm = None
        self._gh_cm = None

        logger.info(f"MCPClientManager initialized with filesystem_root={filesystem_root}")

    async def connect(self) -> None:
        """
        Connect to both Filesystem and GitHub MCP servers sequentially.
        Each server must initialize before moving to the next.

        Raises:
            RuntimeError: If connection to either server fails.
        """
        logger.info("Connecting to MCP servers...")

        try:
            await self._connect_filesystem()
            await self._connect_github()
            logger.info("✓ Successfully connected to both MCP servers")
        except Exception as e:
            logger.error(f"Failed to connect to MCP servers: {e}")
            await self.close()
            raise

    async def _connect_filesystem(self) -> None:
        """
        Connect to Filesystem MCP server via stdio.
        Spins up the server using npx.
        """
        logger.info("Connecting to Filesystem MCP server...")

        try:
            params = StdioServerParameters(
                command="npx",
                args=[
                    "-y",
                    "@modelcontextprotocol/server-filesystem",
                    self.filesystem_root,
                ],
            )

            logger.debug(
                f"Filesystem server command: npx {' '.join(params.args)}"
            )

            # Create and enter the context manager
            self._fs_cm = stdio_client(params, errlog=sys.stderr)
            read_stream, write_stream = await self._fs_cm.__aenter__()
            self.filesystem_session = ClientSession(read_stream, write_stream)
            await self.filesystem_session.initialize()

            logger.info("✓ Connected to Filesystem MCP server")

        except Exception as e:
            logger.error(f"Filesystem MCP connection error: {e}")
            raise

    async def _connect_github(self) -> None:
        """
        Connect to GitHub MCP server via stdio.
        Spins up the server using npx.
        Requires GITHUB_PERSONAL_ACCESS_TOKEN environment variable.
        """
        logger.info("Connecting to GitHub MCP server...")

        if not self.github_token:
            logger.warning(
                "GITHUB_PERSONAL_ACCESS_TOKEN not set. GitHub MCP server may not function properly."
            )

        try:
            env = os.environ.copy()
            if self.github_token:
                env["GITHUB_PERSONAL_ACCESS_TOKEN"] = self.github_token

            params = StdioServerParameters(
                command="npx",
                args=["-y", "@modelcontextprotocol/server-github"],
                env=env,
            )

            logger.debug("GitHub server command: npx -y @modelcontextprotocol/server-github")

            # Create and enter the context manager
            self._gh_cm = stdio_client(params, errlog=sys.stderr)
            read_stream, write_stream = await self._gh_cm.__aenter__()
            self.github_session = ClientSession(read_stream, write_stream)
            await self.github_session.initialize()

            logger.info("✓ Connected to GitHub MCP server")

        except Exception as e:
            logger.error(f"GitHub MCP connection error: {e}")
            raise

    async def list_filesystem_tools(self) -> list[Tool]:
        """
        List all tools available from the Filesystem MCP server.

        Returns:
            List of Tool objects from Filesystem server.

        Raises:
            RuntimeError: If not connected to Filesystem server.
        """
        if not self.filesystem_session:
            raise RuntimeError("Not connected to Filesystem MCP server")

        logger.debug("Listing Filesystem MCP tools...")
        tools = await self.filesystem_session.list_tools()
        logger.info(f"Found {len(tools)} Filesystem tools")
        return tools

    async def list_github_tools(self) -> list[Tool]:
        """
        List all tools available from the GitHub MCP server.

        Returns:
            List of Tool objects from GitHub server.

        Raises:
            RuntimeError: If not connected to GitHub server.
        """
        if not self.github_session:
            raise RuntimeError("Not connected to GitHub MCP server")

        logger.debug("Listing GitHub MCP tools...")
        tools = await self.github_session.list_tools()
        logger.info(f"Found {len(tools)} GitHub tools")
        return tools

    async def close(self) -> None:
        """
        Close both MCP server connections.
        Should be called during shutdown for cleanup.
        """
        logger.info("Closing MCP server connections...")

        if self._fs_cm:
            try:
                await self._fs_cm.__aexit__(None, None, None)
                logger.info("✓ Filesystem server closed")
            except Exception as e:
                logger.warning(f"Error closing Filesystem server: {e}")

        if self._gh_cm:
            try:
                await self._gh_cm.__aexit__(None, None, None)
                logger.info("✓ GitHub server closed")
            except Exception as e:
                logger.warning(f"Error closing GitHub server: {e}")

        logger.info("✓ MCP connections closed")

    async def call_tool(self, server: str, tool_name: str, arguments: dict[str, Any]) -> str:
        """
        Call a tool on the specified MCP server.
        Wraps all errors gracefully to prevent agent crashes.

        Args:
            server: "filesystem" or "github"
            tool_name: Name of the tool to call
            arguments: Tool arguments as a dictionary

        Returns:
            Tool result as a string, or error message on failure.
        """
        try:
            session = (
                self.filesystem_session
                if server == "filesystem"
                else self.github_session
            )

            if not session:
                raise RuntimeError(f"Not connected to {server} MCP server")

            logger.debug(
                f"Calling {server}.{tool_name} with arguments: {arguments}"
            )

            result = await session.call_tool(tool_name, arguments)

            if result.content:
                content_str = ""
                for block in result.content:
                    if hasattr(block, "text"):
                        content_str += block.text
                    elif isinstance(block, dict) and "text" in block:
                        content_str += block["text"]
                logger.debug(f"Tool result: {content_str[:200]}...")
                return content_str
            else:
                return f"Tool {tool_name} returned empty result"

        except Exception as e:
            error_msg = f"Error calling {server}.{tool_name}: {type(e).__name__}: {str(e)}"
            logger.error(error_msg)
            return error_msg

    @asynccontextmanager
    async def managed_connection(self):
        """
        Context manager for automatic connection management.

        Usage:
            async with manager.managed_connection():
                tools = await manager.list_filesystem_tools()
        """
        await self.connect()
        try:
            yield self
        finally:
            await self.close()


# ============================================================================
# LANGCHAIN TOOL WRAPPERS (For LLM-driven agent tool calling)
# ============================================================================


def set_mcp_manager(manager: "MCPClientManager") -> None:
    """Set the global MCP manager instance for tool wrappers."""
    global _mcp_manager
    _mcp_manager = manager
    logger.info("MCP manager set for tool wrappers")


@tool
def mcp_read_file(filepath: str, start_line: int = 1, end_line: Optional[int] = None) -> str:
    """
    Read file contents from the Filesystem MCP server.
    Used by the Researcher agent to examine code files.

    Args:
        filepath: Path to file (relative to workspace root)
        start_line: Starting line number (1-indexed)
        end_line: Ending line number (1-indexed), None for EOF

    Returns:
        File contents or error message
    """
    if not _mcp_manager:
        return "Error: MCP manager not initialized"

    try:
        arguments = {
            "path": filepath,
        }
        if start_line > 1 or end_line:
            arguments["startLine"] = start_line
            if end_line:
                arguments["endLine"] = end_line

        # Run async call in event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(
                _mcp_manager.call_tool("filesystem", "read_file", arguments)
            )
            return result
        finally:
            loop.close()

    except Exception as e:
        return f"Error reading file {filepath}: {type(e).__name__}: {str(e)}"


@tool
def mcp_search_files(repo_path: str, pattern: str) -> str:
    """
    Search for files matching a pattern in the repository.
    Uses Filesystem MCP server search capabilities.

    Args:
        repo_path: Repository root path
        pattern: Regex pattern or substring to match filenames

    Returns:
        JSON-formatted list of matching files or error message
    """
    if not _mcp_manager:
        return "Error: MCP manager not initialized"

    try:
        arguments = {
            "path": repo_path,
            "pattern": pattern,
        }

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(
                _mcp_manager.call_tool("filesystem", "search_files", arguments)
            )
            return result
        finally:
            loop.close()

    except Exception as e:
        return f"Error searching files: {type(e).__name__}: {str(e)}"


@tool
def mcp_github_search(query: str, max_results: int = 10) -> str:
    """
    Search GitHub repositories or issues using GitHub MCP server.
    For authenticated searches (requires valid GitHub token).

    Args:
        query: Search query
        max_results: Maximum results to return

    Returns:
        JSON-formatted search results or error message
    """
    if not _mcp_manager:
        return "Error: MCP manager not initialized"

    try:
        arguments = {
            "query": query,
            "maxResults": max_results,
        }

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(
                _mcp_manager.call_tool("github", "search_repositories", arguments)
            )
            return result
        finally:
            loop.close()

    except Exception as e:
        return f"Error searching GitHub: {type(e).__name__}: {str(e)}"


def get_mcp_tools() -> list:
    """
    Get LangChain tool objects for use with agents.
    Returns all available MCP tools for binding to LLM.

    Returns:
        List of LangChain tool objects
    """
    return [mcp_read_file, mcp_search_files, mcp_github_search]
