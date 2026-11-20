"""FastAPI host for opentargets-link (thin: health + service info).

The FastAPI layer is intentionally minimal — the MCP plane carries the tool
surface. ``GET /health`` is the liveness/readiness probe and reports the pinned
discovery ``capabilities_version`` so deploy
checks (and the router) can confirm which contract is live without a tool call.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastmcp.server.http import HostOriginGuardMiddleware

from opentargets_link import __version__
from opentargets_link.buildinfo import build_info
from opentargets_link.config import settings
from opentargets_link.mcp.capabilities import capabilities_version

if TYPE_CHECKING:
    pass


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="opentargets-link",
        description=(
            "MCP server for Open Targets (Clinical Interpretation of Variants in Cancer): "
            "molecular profiles, variants, evidence items and assertions, via the live "
            "Open Targets Platform GraphQL API."
        ),
        version=__version__,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # Container Hardening Standard v1: never combine wildcard origins with
    # credentials. Browsers reject "*" + credentials and it is a security
    # footgun, so disable credentials whenever a wildcard origin is configured.
    allow_credentials = "*" not in settings.cors_origins
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=allow_credentials,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )
    app.add_middleware(
        HostOriginGuardMiddleware,
        allowed_hosts=settings.allowed_hosts,
        allowed_origins=settings.allowed_origins,
        mode="strict",
    )

    @app.get("/health")
    async def health() -> dict[str, Any]:
        """Liveness probe reporting the capabilities version (no upstream call)."""
        return {
            "status": "ok",
            "version": __version__,
            "transport": "streamable-http-stateless",
            "capabilities_version": capabilities_version(),
        }

    @app.get("/")
    async def root() -> dict[str, Any]:
        """Service information."""
        return {
            "name": "opentargets-link",
            "version": __version__,
            "data_source": "Open Targets Platform GraphQL API (api.platform.opentargets.org/api/graphql)",
            "mcp_endpoint": settings.mcp_path,
            "docs": "/docs",
            "health": "/health",
            **build_info(),
        }

    return app


app = create_app()
