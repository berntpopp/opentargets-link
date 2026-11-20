"""Shared fixtures: a real OpenTargetsService over a respx-mocked Open Targets Platform GraphQL API.

Unit tests are network-free. ``mocked_ot`` answers each fixed GraphQL document with a
recorded response from ``tests/fixtures/opentargets/`` (captured from https://api.platform.opentargets.org/api/v4/graphql
on 2026-11-20 with the exact documents in ``opentargets_link/queries.py``); ``facade`` wires the
service into a real FastMCP instance and ``call_tool`` drives it through an in-memory
``fastmcp.Client``.
"""

from __future__ import annotations

import json
import pathlib
import re
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from typing import Any

import httpx
import pytest
import respx

from opentargets_link.api.client import GRAPHQL_PATH, OpenTargetsClient
from opentargets_link.config import OpenTargetsSettings
from opentargets_link.mcp import metrics
from opentargets_link.mcp.facade import create_opentargets_mcp
from opentargets_link.mcp.service_adapters import set_opentargets_service
from opentargets_link.service import OpenTargetsService

FX = pathlib.Path(__file__).parent / "fixtures" / "opentargets"
BASE = "https://api.platform.opentargets.org"


def load(name: str) -> Any:
    """Load a recorded Open Targets JSON fixture by file stem."""
    return json.loads((FX / f"{name}.json").read_text())


def fast_settings() -> OpenTargetsSettings:
    """Upstream settings with politeness spacing disabled so tests run instantly."""
    return OpenTargetsSettings(min_interval_s=0.0, backoff_base_s=0.0)


BRAF, KRAS, MELANOMA = "ENSG00000157764", "ENSG00000133703", "MONDO_0005105"


def _fixture_for(op: str, v: dict[str, Any]) -> str:
    """The recorded response for one (operation, variables) pair."""
    if op == "MapIds":
        hits = {
            ("target", "BRAF"): "map_braf",
            ("target", "HER2"): "map_her2",
            ("disease", "melanoma"): "map_melanoma",
        }
        miss = "map_none" if v["entity"] == "target" else "map_disease_none"
        query = v["query"].upper() if v["entity"] == "target" else v["query"]
        return hits.get((v["entity"], query), miss)
    if op in ("TargetGet", "Tractability", "Drugs", "DrugsFull"):
        gene = {BRAF: "braf", KRAS: "kras"}.get(v["target_id"])
        if gene is None:
            return "target_missing"
        stem = {"TargetGet": "target", "Tractability": "tractability", "DrugsFull": "drugs_full"}
        stem = stem.get(op, "drugs")
        return f"{stem}_{gene}" if op != "Tractability" or gene == "braf" else "target_missing"
    if op == "DiseaseGet":
        return "disease_melanoma" if v["disease_id"] == MELANOMA else "disease_missing"
    if op == "DiseaseTargets":
        return "disease_targets_melanoma"
    if op == "DiseaseEvidence":
        return "disease_evidence_braf_melanoma"
    if op == "TargetDiseases":
        return "target_diseases_kras" if v["target_id"] == KRAS else "target_missing"
    if op == "TargetEvidence":
        return "target_evidence_kras_burden"
    return "meta"


def _graphql(request: httpx.Request) -> httpx.Response:
    body = json.loads(request.content)
    match = re.search(r"query\s+(\w+)", body["query"])
    op = match.group(1) if match else ""
    return httpx.Response(200, json=load(_fixture_for(op, body.get("variables") or {})))


@pytest.fixture(autouse=True)
def _reset_metrics() -> Iterator[None]:
    """Keep the process-wide metrics collector clean between tests."""
    metrics.reset()
    yield
    metrics.reset()


@pytest.fixture
def mocked_ot() -> Iterator[respx.MockRouter]:
    """A respx router serving the recorded Open Targets fixtures."""
    with respx.mock(base_url=BASE, assert_all_called=False) as router:
        router.post(GRAPHQL_PATH).mock(side_effect=_graphql)
        yield router


@pytest.fixture
async def ot_service(mocked_ot: respx.MockRouter) -> AsyncIterator[OpenTargetsService]:
    """A real OpenTargetsService over the respx-mocked client."""
    client = OpenTargetsClient(fast_settings())
    try:
        yield OpenTargetsService(client)
    finally:
        await client.aclose()


@pytest.fixture
def facade(ot_service: OpenTargetsService) -> Iterator[Any]:
    """A FastMCP facade with the fixture service injected; cleans up after."""
    mcp = create_opentargets_mcp(service_factory=lambda: ot_service)
    yield mcp
    set_opentargets_service(None)


@pytest.fixture
def call_tool() -> Callable[[Any, str, dict[str, Any]], Awaitable[Any]]:
    """Call a tool through an in-memory ``fastmcp.Client``; return the structured dict."""
    from fastmcp import Client

    async def _call(mcp: Any, name: str, args: dict[str, Any]) -> Any:
        async with Client(mcp) as client:
            res = await client.call_tool(name, args, raise_on_error=False)
        if isinstance(res.structured_content, dict):
            return res.structured_content
        return res.data

    return _call
