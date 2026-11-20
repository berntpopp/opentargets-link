"""Async client for the Open Targets Platform GraphQL API.

Every request: passes the process-wide :class:`RateLimiter`, carries an honest
User-Agent (product/version + project URL, no user data), is restricted to the
configured origin over HTTPS with a hard response-byte cap, and backs off on
429/5xx/timeouts (honouring ``Retry-After``). Successful results are cached in-process
for ``cache_ttl_s`` (no data snapshot is kept).

GraphQL reports errors as ``errors[]`` on HTTP 200, or on HTTP 400 for variable/validation
errors. A ``Variable '$x'`` error becomes ``invalid_input`` naming the tool parameter behind
``$x``; ``Cannot query field`` means the upstream schema drifted under a fixed query; any
other GraphQL error is an upstream fault. Upstream text is used only to classify; callers see fixed messages
(Response-Envelope v1.1 error-message sanitation).
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

import httpx
import structlog

from opentargets_link import __version__
from opentargets_link.api.url_guard import (
    MAX_REDIRECTS,
    build_origin_allowlist,
    make_url_guard,
    read_capped_response,
)
from opentargets_link.config import OpenTargetsSettings
from opentargets_link.exceptions import (
    InvalidInputError,
    RateLimitedError,
    UpstreamSchemaError,
    UpstreamUnavailableError,
)
from opentargets_link.ratelimit import RateLimiter

logger = structlog.get_logger(__name__)
USER_AGENT = f"opentargets-link/{__version__} (+https://github.com/berntpopp/opentargets-link)"
_RETRY_STATUS = {429, 500, 502, 503, 504}


def _retry_after(response: httpx.Response | None) -> float | None:
    raw = response.headers.get("retry-after") if response is not None else None
    try:
        return max(0.0, float(raw)) if raw is not None else None
    except ValueError:
        return None


_VARIABLE = re.compile(r"^Variable '?\$([A-Za-z_][A-Za-z0-9_]*)\b")


def _graphql_error(
    errors: list[Any], variables: Mapping[str, Any], fields: Mapping[str, str]
) -> Exception:
    """Map Open Targets's HTTP-200 ``errors[]`` to a typed error naming the tool parameter."""
    for err in errors:
        match = _VARIABLE.match(str(err.get("message", "")) if isinstance(err, dict) else "")
        if match and match.group(1) in variables:  # only ever echo our own variable names
            field = fields.get(match.group(1), match.group(1))
            return InvalidInputError(
                f"Open Targets rejected the value of `{field}`.",
                field=field,
                recovery_action="reformulate_input",
            )
        if isinstance(err, dict) and str(err.get("message", "")).startswith("Cannot query field"):
            logger.warning("opentargets_schema_drift: a fixed query names a vanished field")
            return UpstreamSchemaError(
                "Open Targets changed its GraphQL schema under a fixed query (schema drift).",
                field="response",
            )
    return UpstreamSchemaError(
        "Open Targets answered the query with a GraphQL error.", field="response"
    )


GRAPHQL_PATH = "/api/v4/graphql"


class OpenTargetsClient:
    """Rate-limited, cached, origin-guarded client for ``api.platform.opentargets.org``."""

    def __init__(
        self, settings: OpenTargetsSettings, *, limiter: RateLimiter | None = None
    ) -> None:
        """Build the HTTP client, limiter and cache from settings."""
        self.settings = settings
        self.limiter = limiter or RateLimiter(
            min_interval_s=settings.min_interval_s,
            daily_cap=settings.daily_cap,
            max_wait_s=settings.max_wait_s,
        )
        guard = make_url_guard(build_origin_allowlist(settings.base_url))
        self._http = httpx.AsyncClient(
            base_url=settings.base_url,
            timeout=settings.request_timeout_s,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            follow_redirects=True,
            max_redirects=MAX_REDIRECTS,
            event_hooks={"request": [guard]},
        )
        self._cache: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self._inflight: dict[str, asyncio.Future[Any]] = {}
        self.upstream_requests = 0
        self.cache_hits = 0

    async def aclose(self) -> None:
        """Close the underlying HTTP connection pool."""
        await self._http.aclose()

    def _cache_get(self, key: str) -> Any:
        hit = self._cache.get(key)
        if hit is None or hit[0] < time.monotonic():
            self._cache.pop(key, None)
            return None
        self._cache.move_to_end(key)
        self.cache_hits += 1
        return hit[1]

    def _cache_put(self, key: str, value: Any) -> None:
        self._cache[key] = (time.monotonic() + self.settings.cache_ttl_s, value)
        while len(self._cache) > self.settings.cache_maxsize:
            self._cache.popitem(last=False)

    async def _once(self, key: str, fetch: Callable[[], Awaitable[Any]]) -> Any:
        cached = self._cache_get(key)
        if cached is not None:
            return cached
        # Single-flight: parallel identical calls share one upstream request (politeness).
        task = self._inflight.get(key)
        if task is None:
            task = self._inflight[key] = asyncio.ensure_future(fetch())
            task.add_done_callback(lambda done: self._settle(key, done))
        return await asyncio.shield(task)

    def _settle(self, key: str, task: asyncio.Future[Any]) -> None:
        self._inflight.pop(key, None)
        if not task.cancelled() and task.exception() is None:
            self._cache_put(key, task.result())

    async def graphql(
        self,
        document: str,
        variables: Mapping[str, Any],
        *,
        fields: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        """Run one fixed GraphQL ``document``; return ``data`` or raise a typed error.

        ``fields`` maps a variable name to the tool parameter it carries (default: same name).
        """
        body = {"query": document, "variables": dict(variables)}
        key = "POST " + json.dumps(body, sort_keys=True, default=str)

        async def fetch() -> dict[str, Any]:
            response = await self._request("POST", GRAPHQL_PATH, json=body, graphql=True)
            try:
                payload = response.json()
            except ValueError:
                raise UpstreamSchemaError(
                    "Open Targets returned a non-JSON body.", field="response"
                ) from None
            if not isinstance(payload, dict):
                raise UpstreamSchemaError(
                    "Open Targets returned a non-object body.", field="response"
                )
            errors = payload.get("errors")
            if errors:
                raise _graphql_error(
                    errors if isinstance(errors, list) else [], variables, fields or {}
                )
            data = payload.get("data")
            if not isinstance(data, dict):
                raise UpstreamSchemaError("Open Targets returned no data object.", field="response")
            return data

        result: dict[str, Any] = await self._once(key, fetch)
        return result

    async def _request(
        self, method: str, path: str, *, graphql: bool = False, **kwargs: Any
    ) -> httpx.Response:
        attempts = self.settings.max_retries + 1
        response: httpx.Response | None = None
        for attempt in range(attempts):
            if attempt:
                delay = _retry_after(response) or self.settings.backoff_base_s * 2 ** (attempt - 1)
                await asyncio.sleep(min(delay, 30.0))
            await self.limiter.acquire()
            self.upstream_requests += 1
            try:
                response = await read_capped_response(
                    self._http,
                    method,
                    path,
                    max_bytes=self.settings.max_response_bytes,
                    **kwargs,
                )
            except httpx.TimeoutException, httpx.TransportError:
                response = None
                continue
            if response.status_code not in _RETRY_STATUS:
                break
        if response is None or response.status_code in _RETRY_STATUS:
            if response is not None and response.status_code == 429:
                raise RateLimitedError(
                    "Open Targets is rate limiting requests. Retry after retry_after_s seconds.",
                    retryable=True,
                    retry_after_s=_retry_after(response) or 60.0,
                )
            raise UpstreamUnavailableError(
                "Open Targets is temporarily unavailable.", retryable=True
            )
        # GraphQL validation/variable errors arrive as HTTP 400 with an errors[] body.
        if response.status_code != 200 and not (graphql and response.status_code == 400):
            raise UpstreamUnavailableError(
                "Open Targets returned an unexpected status.", retryable=False
            )
        return response
