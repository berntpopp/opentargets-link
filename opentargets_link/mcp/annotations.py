"""Shared tool annotations: every opentargets-link tool is a read-only query of Open Targets."""

from __future__ import annotations

from mcp.types import ToolAnnotations

READ_ONLY_OPEN_WORLD = ToolAnnotations(read_only_hint=True, open_world_hint=True)
