"""
Tools module: MCP client connections and LangChain tool wrappers.

Exports:
    - MCPClientManager: Manager for Filesystem and GitHub MCP servers
    - get_mcp_tools: Get LangChain tool objects for agent binding
    - set_mcp_manager: Initialize global MCP manager for tool wrappers
"""

from app.tools.mcp_client import (
    MCPClientManager,
    get_mcp_tools,
    set_mcp_manager,
)

__all__ = ["MCPClientManager", "get_mcp_tools", "set_mcp_manager"]
