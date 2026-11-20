"""End-to-end MCP tool tests through an in-memory FastMCP client."""

from __future__ import annotations

from typing import Any

from fastmcp import Client

from opentargets_link.mcp.capabilities import TOOLS


async def _raw(mcp: Any, name: str, args: dict[str, Any]) -> Any:
    async with Client(mcp) as client:
        return await client.call_tool(name, args, raise_on_error=False)


async def test_registered_tools_match_capabilities_and_are_documented(facade: Any) -> None:
    async with Client(facade) as client:
        tools = await client.list_tools()
    assert [t.name for t in tools] == TOOLS
    for tool in tools:
        props = tool.input_schema.get("properties", {})
        for name, prop in props.items():
            assert prop.get("description"), f"{tool.name}.{name} lacks a description"
        for name in tool.input_schema.get("required", []):
            assert props[name].get("examples"), f"{tool.name}.{name} lacks examples"
        assert tool.description and "Signature:" in tool.description
        assert tool.annotations is not None and tool.annotations.read_only_hint is True
        assert tool.output_schema is None


async def test_braf_acceptance_path(facade: Any, call_tool: Any) -> None:
    """BRAF -> tractability (SM approved) -> melanoma drugs -> evidence without COSMIC rows."""
    found = await call_tool(facade, "resolve_target", {"query": "BRAF"})
    assert found["success"] is True and found["target"]["id"] == "ENSG00000157764"
    meta = found["_meta"]
    assert meta["source"] == "opentargets" and meta["unsafe_for_clinical_use"] is True
    assert meta["next_commands"][0] == {
        "tool": "get_target_tractability",
        "arguments": {"target": "ENSG00000157764"},
    }
    tract = await call_tool(facade, "get_target_tractability", {"target": "ENSG00000157764"})
    assert "Approved Drug" in tract["tractability"]["SM"]["true"]
    drugs = await call_tool(
        facade, "get_drug_candidates", {"target": "BRAF", "disease": "melanoma", "limit": 20}
    )
    assert {"VEMURAFENIB", "DABRAFENIB"} <= {d["drug_name"] for d in drugs["drug_candidates"]}
    evidence = await call_tool(
        facade, "get_target_disease_evidence", {"target": "BRAF", "disease": "MONDO_0005105"}
    )
    sources = {e["datasource_id"] for e in evidence["evidence"]}
    assert "intogen" in sources and "cancer_gene_census" not in sources
    assert evidence["data_version"] == "26.09"


async def test_unknown_target_is_is_error_not_found(facade: Any) -> None:
    res = await _raw(facade, "resolve_target", {"query": "ENSG00000000001"})
    assert res.is_error is True
    body = res.structured_content
    assert body["error_code"] == "not_found" and body["field"] == "query"


async def test_evidence_paging_suggests_next_cursor(facade: Any, call_tool: Any) -> None:
    args = {"target": "BRAF", "disease": "MONDO_0005105"}
    out = await call_tool(facade, "get_target_disease_evidence", args)
    step = out["_meta"]["next_commands"][0]
    assert step["tool"] == "get_target_disease_evidence"
    assert step["arguments"]["cursor"] == out["next_cursor"]


async def test_off_allowlist_datasource_is_invalid_input_with_allowed_values(facade: Any) -> None:
    args = {"disease": "MONDO_0005105", "datasource": "cancer_gene_census"}
    res = await _raw(facade, "search_disease_targets", args)
    body = res.structured_content
    assert res.is_error is True and body["error_code"] == "invalid_input"
    assert (
        "intogen" in body["allowed_values"] and "cancer_gene_census" not in body["allowed_values"]
    )
    assert "not served" in body["message"] and "COSMIC" in body["message"]


async def test_unknown_datasource_gets_no_exclusion_reason(facade: Any) -> None:
    args = {"disease": "MONDO_0005105", "datasource": "zzz"}
    body = (await _raw(facade, "search_disease_targets", args)).structured_content
    assert body["error_code"] == "invalid_input" and "not served" not in body["message"]


async def test_over_cap_limit_suggests_the_clamped_call(facade: Any) -> None:
    args = {"disease": "MONDO_0005105", "limit": 500}
    res = await _raw(facade, "search_disease_targets", args)
    assert res.is_error is True
    assert res.structured_content["_meta"]["next_commands"] == [
        {"tool": "search_disease_targets", "arguments": {**args, "limit": 50}}
    ]


async def test_foreign_gene_id_is_rejected_with_a_converter(facade: Any) -> None:
    res = await _raw(facade, "get_drug_candidates", {"target": "HGNC:1097"})
    body = res.structured_content
    assert res.is_error is True and body["field"] == "target" and body["allowed_values"]
    assert body["_meta"]["next_commands"] == [
        {"tool": "hgnc_resolve_symbol", "arguments": {"query": "HGNC:1097"}}
    ]


async def test_capabilities_and_diagnostics(facade: Any, call_tool: Any) -> None:
    caps = await call_tool(facade, "get_server_capabilities", {})
    assert caps["tools"] == TOOLS and caps["research_use_only"] is True
    assert "CC0" in caps["license"] and "39657122" in caps["recommended_citation"]
    assert "cancer_gene_census" in caps["datasources"]["excluded"]
    diag = await call_tool(facade, "get_diagnostics", {})
    assert diag["upstream"]["base_url"] == "https://api.platform.opentargets.org"


async def test_descriptions_name_only_returned_fields(facade: Any, call_tool: Any) -> None:
    """Contract truth: the fields a description promises are in the response."""
    target = (await call_tool(facade, "resolve_target", {"query": "BRAF"}))["target"]
    assert {"id", "symbol", "name", "biotype", "location", "synonyms"} <= set(target)
    tract = await call_tool(facade, "get_target_tractability", {"target": "BRAF"})
    assert {"tractability", "target_class"} <= set(tract)
    drug = (await call_tool(facade, "get_drug_candidates", {"target": "BRAF"}))["drug_candidates"][
        0
    ]
    assert {"drug_id", "drug_name", "max_clinical_stage_for_target", "action_types"} <= set(drug)
    assert "diseases" in drug
    ranked = await call_tool(facade, "search_disease_targets", {"disease": "MONDO_0005105"})
    assert {"targets", "total"} <= set(ranked) and "datasource_scores" in ranked["targets"][0]
