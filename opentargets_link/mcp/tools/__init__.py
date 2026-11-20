"""Open Targets MCP tool registrations."""

from __future__ import annotations

from typing import TYPE_CHECKING

from opentargets_link.mcp.tools.discovery import register_discovery_tools
from opentargets_link.mcp.tools.opentargets import register_opentargets_tools

if TYPE_CHECKING:
    from fastmcp import FastMCP


def register_all_tools(mcp: FastMCP) -> None:
    """Register every tool group on a FastMCP instance in canonical order."""
    register_discovery_tools(mcp)
    register_opentargets_tools(mcp)
