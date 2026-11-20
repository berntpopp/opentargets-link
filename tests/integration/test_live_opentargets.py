"""Live Open Targets contract checks (opt-in: OPENTARGETS_LINK_LIVE_INTEGRATION=1).

Run weekly by .github/workflows/drift.yml. A handful of calls through the real rate limiter:
the schema contract (every fixed document validates; the data release is the tested one) and
the plan's acceptance path.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest

from opentargets_link import queries as Q
from opentargets_link.api.client import OpenTargetsClient
from opentargets_link.config import OpenTargetsSettings
from opentargets_link.datasources import ALLOWED, EXCLUDED, ZERO_WEIGHTS
from opentargets_link.mcp.capabilities import TESTED_DATA_VERSION
from opentargets_link.service import OpenTargetsService

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("OPENTARGETS_LINK_LIVE_INTEGRATION") != "1",
        reason="set OPENTARGETS_LINK_LIVE_INTEGRATION=1 to call the live Open Targets API",
    ),
]
BRAF, MELANOMA = "ENSG00000157764", "MONDO_0005105"


@pytest.fixture
async def service() -> AsyncIterator[OpenTargetsService]:
    client = OpenTargetsClient(OpenTargetsSettings())
    try:
        yield OpenTargetsService(client)
    finally:
        await client.aclose()


async def test_live_release_is_the_tested_one(service: OpenTargetsService) -> None:
    # Fails on each quarterly release: re-verify queries.py, re-record fixtures, bump the constant.
    assert await service.release() == TESTED_DATA_VERSION


async def test_live_every_fixed_document_still_validates(service: OpenTargetsService) -> None:
    variables = {
        "MAP_IDS": {"query": "BRAF", "entity": "target"},
        "DISEASE_GET": {"disease_id": MELANOMA},
        "DISEASE_TARGETS": {"disease_id": MELANOMA, "size": 1, "datasources": ZERO_WEIGHTS},
        "TARGET_DISEASES": {"target_id": BRAF, "datasources": ZERO_WEIGHTS},
        "DISEASE_EVIDENCE": {"disease_id": MELANOMA, "target_id": BRAF, "limit": 1},
        "TARGET_EVIDENCE": {"target_id": BRAF, "efo_ids": [MELANOMA], "limit": 1},
    }
    for name, doc in Q.ALL.items():
        await service.client.graphql(doc, variables.get(name, {"target_id": BRAF}))


async def test_live_datasources_are_all_reviewed(service: OpenTargetsService) -> None:
    """A datasource Open Targets adds upstream must be reviewed (allowlisted or excluded)."""
    data = await service.client.graphql(
        "query Seen($target_id: String!) { target(ensemblId: $target_id) {"
        " associatedDiseases(page: {index: 0, size: 500}) { rows { datasourceScores { id } } } } }",
        {"target_id": BRAF},
    )
    rows = data["target"]["associatedDiseases"]["rows"]
    seen = {s["id"] for r in rows for s in r["datasourceScores"]}
    assert seen <= set(ALLOWED) | set(EXCLUDED), seen - set(ALLOWED) - set(EXCLUDED)


async def test_live_braf_acceptance(service: OpenTargetsService) -> None:
    tract = await service.get_target_tractability("BRAF")
    assert "Approved Drug" in tract["tractability"]["SM"]["true"]
    drugs = await service.get_drug_candidates("BRAF", disease="melanoma", limit=20)
    assert {"VEMURAFENIB", "DABRAFENIB"} <= {d["drug_name"] for d in drugs["drug_candidates"]}
    assert drugs["parent_drugs_total"] < drugs["total"]  # dabrafenib mesylate folds into dabrafenib
    evidence = await service.get_target_disease_evidence("BRAF", disease=MELANOMA, limit=50)
    sources = {e["datasource_id"] for e in evidence["evidence"]}
    assert "intogen" in sources and "cancer_gene_census" not in sources
    assert "filtered_out" not in evidence  # upstream honoured the datasource allowlist


async def test_live_cursor_pages_to_the_end(service: OpenTargetsService) -> None:
    """Guards the decoded cursor format: 8 IntOGen rows page 5 + 3, then stop."""
    args = {"disease": MELANOMA, "datasource": "intogen", "limit": 5}
    first = await service.get_target_disease_evidence(BRAF, **args)  # type: ignore[arg-type]
    assert first["truncated"] and first["next_cursor"]
    last = await service.get_target_disease_evidence(BRAF, **args, cursor=first["next_cursor"])  # type: ignore[arg-type]
    assert first["returned"] + last["returned"] == first["total"]
    assert not last["truncated"] and last["next_cursor"] is None
