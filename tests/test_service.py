"""OpenTargetsService over recorded Open Targets 26.09 responses (respx, network-free)."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
import respx

from opentargets_link.api.client import GRAPHQL_PATH
from opentargets_link.exceptions import InvalidInputError, NotFoundError
from opentargets_link.service import OpenTargetsService
from tests.conftest import BRAF, KRAS, MELANOMA, load


def _sent(router: respx.MockRouter, op: str) -> list[dict[str, Any]]:
    bodies = [json.loads(c.request.content) for c in router.calls]
    return [b["variables"] for b in bodies if f"query {op}" in b["query"]]


async def test_every_payload_carries_the_ot_data_release(ot_service: OpenTargetsService) -> None:
    p = await ot_service.resolve_target("BRAF")
    assert p["data_version"] == "26.09"
    assert "not a clinical actionability report" in p["disclaimer"]


async def test_resolve_target_by_symbol_and_ensembl(ot_service: OpenTargetsService) -> None:
    by_symbol = (await ot_service.resolve_target("braf"))["target"]
    assert by_symbol["id"] == BRAF and by_symbol["symbol"] == "BRAF"
    assert by_symbol["resolved_from"] == "braf"
    assert by_symbol["location"]["assembly"] == "GRCh38"
    by_id = (await ot_service.resolve_target(BRAF))["target"]
    assert by_id["id"] == BRAF and "resolved_from" not in by_id


async def test_alias_resolves_and_says_so(ot_service: OpenTargetsService) -> None:
    hit = await ot_service._target_id("HER2")
    assert hit == ("ENSG00000141736", "HER2")


async def test_hgnc_id_resolves_through_open_targets(ot_service: OpenTargetsService) -> None:
    p = await ot_service.get_target_tractability("HGNC:1097")
    assert p["target"]["id"] == BRAF and p["target"]["resolved_from"] == "HGNC:1097"


@pytest.mark.parametrize("value", ["NCBIGene:673", "673"])
async def test_foreign_gene_ids_point_to_hgnc(ot_service: OpenTargetsService, value: str) -> None:
    with pytest.raises(InvalidInputError) as info:
        await ot_service.get_target_tractability(value)
    extra = info.value.extra
    assert extra["field"] == "target" and extra["allowed_values"]
    assert extra["next_commands"][0]["tool"] == "hgnc_resolve_symbol"


async def test_unknown_target_is_not_found(ot_service: OpenTargetsService) -> None:
    with pytest.raises(NotFoundError) as info:
        await ot_service.resolve_target("NOTAGENE1")
    assert info.value.extra["field"] == "query"
    with pytest.raises(NotFoundError):
        await ot_service.resolve_target("ENSG00000000001")


async def test_braf_tractability_has_small_molecule_approved_drug(
    ot_service: OpenTargetsService,
) -> None:
    p = await ot_service.get_target_tractability("BRAF")
    assert "Approved Drug" in p["tractability"]["SM"]["true"]
    assert "Approved Drug" in p["tractability"]["AB"]["false"]


async def test_braf_melanoma_drug_candidates_include_vemurafenib_and_dabrafenib(
    ot_service: OpenTargetsService,
) -> None:
    p = await ot_service.get_drug_candidates("BRAF", disease="melanoma", limit=20)
    names = {r["drug_name"] for r in p["drug_candidates"]}
    assert {"VEMURAFENIB", "DABRAFENIB"} <= names
    assert p["disease"] == {"id": MELANOMA, "name": "melanoma", "resolved_from": "melanoma"}
    assert p["total"] < 18  # the disease filter removed drugs never studied in melanoma
    assert "ARQ-736" not in names
    stages = [r["max_clinical_stage_for_target"] for r in p["drug_candidates"]]
    assert p["drug_candidates"][0]["approved"] and stages[0] in {"APPROVAL", "PHASE_4"}
    assert all("clinical_reports" not in r for r in p["drug_candidates"])
    assert "ChEMBL (CC BY-SA 3.0)" in p["licence_note"]


async def test_drug_candidates_page_honestly(ot_service: OpenTargetsService) -> None:
    first = await ot_service.get_drug_candidates(BRAF, limit=5)
    assert first["total"] == 18 and first["returned"] == 5 and first["truncated"]
    last = await ot_service.get_drug_candidates(BRAF, limit=5, offset=15)
    assert last["returned"] == 3 and not last["truncated"] and last["next_offset"] is None


async def test_full_mode_adds_fenced_reports_capped_per_drug(
    ot_service: OpenTargetsService,
) -> None:
    p = await ot_service.get_drug_candidates(KRAS, response_mode="full")
    row = p["drug_candidates"][0]
    assert row["clinical_reports_total"] > 3 and len(row["clinical_reports"]) == 3
    assert row["clinical_reports"][0]["title"]["kind"] == "untrusted_text"
    assert row["mechanism_of_action"]["kind"] == "untrusted_text"


async def test_disease_targets_zero_weight_excluded_sources_and_filter_scores(
    ot_service: OpenTargetsService, mocked_ot: respx.MockRouter
) -> None:
    p = await ot_service.search_disease_targets("MONDO:0005105", limit=5)
    sent = _sent(mocked_ot, "DiseaseTargets")[0]["datasources"]
    zeroed = {d["id"] for d in sent if d["weight"] == 0}
    assert {"cancer_gene_census", "europepmc", "cancer_biomarkers"} <= zeroed
    braf = next(r for r in p["targets"] if r["symbol"] == "BRAF")
    assert "intogen" in braf["datasource_scores"]
    for row in p["targets"]:
        assert not {"cancer_gene_census", "europepmc", "crispr"} & set(row["datasource_scores"])
    assert p["total"] > 1000 and p["truncated"]
    assert _sent(mocked_ot, "DiseaseTargets")[0]["order"] == "score" == p["ranked_by"]


async def test_disease_targets_datasource_filter_is_required(
    ot_service: OpenTargetsService, mocked_ot: respx.MockRouter
) -> None:
    p = await ot_service.search_disease_targets(MELANOMA, datasource="intogen")
    sent = _sent(mocked_ot, "DiseaseTargets")[0]
    assert {"id": "intogen", "weight": 1.0, "propagate": True, "required": True} in sent[
        "datasources"
    ]
    assert sent["order"] == "intogen" and p["ranked_by"] == "intogen"  # not the overall score


@pytest.mark.parametrize("value", ["OMIM:155600", "DOID:1909"])
async def test_foreign_disease_ids_point_to_mondo(
    ot_service: OpenTargetsService, value: str
) -> None:
    with pytest.raises(InvalidInputError) as info:
        await ot_service.search_disease_targets(value)
    assert info.value.extra["next_commands"][0]["tool"] == "mondo_resolve_disease"
    assert "genefoundry" in info.value.extra["hint"] and "name" in info.value.extra["hint"]


async def test_unknown_disease_is_not_found(ot_service: OpenTargetsService) -> None:
    with pytest.raises(NotFoundError):
        await ot_service.search_disease_targets("zzzz not a disease")
    with pytest.raises(NotFoundError) as unknown_id:
        await ot_service.search_disease_targets("MONDO_9999999")
    assert not unknown_id.value.extra.get("next_commands")  # mondo cannot map a made-up ID
    assert "name" in unknown_id.value.extra["hint"]


async def test_braf_melanoma_evidence_is_allowlisted_only(
    ot_service: OpenTargetsService, mocked_ot: respx.MockRouter
) -> None:
    p = await ot_service.get_target_disease_evidence("BRAF", disease=MELANOMA)
    sources = {r["datasource_id"] for r in p["evidence"]}
    assert "intogen" in sources and "cancer_gene_census" not in sources
    sent = _sent(mocked_ot, "DiseaseEvidence")[0]["datasource"]
    assert "cancer_gene_census" not in sent and "europepmc" not in sent
    assert p["total"] == 287 and p["truncated"] and p["next_cursor"]


async def test_excluded_datasource_rows_in_a_response_are_dropped(
    ot_service: OpenTargetsService, mocked_ot: respx.MockRouter
) -> None:
    good = load("disease_evidence_braf_melanoma")
    cgc = load("disease_evidence_braf_melanoma_cgc")["data"]["disease"]["evidences"]["rows"]
    good["data"]["disease"]["evidences"]["rows"] += cgc  # upstream ignoring datasourceIds
    mocked_ot.post(GRAPHQL_PATH).mock(
        side_effect=lambda r: httpx.Response(
            200, json=good if "DiseaseEvidence" in r.content.decode() else _other(r)
        )
    )
    p = await ot_service.get_target_disease_evidence(BRAF, disease=MELANOMA)
    assert {r["datasource_id"] for r in p["evidence"]} <= {"intogen", "clinical_precedence"}
    assert p["filtered_out"] == len(cgc)


def _other(request: httpx.Request) -> Any:
    from tests.conftest import _graphql

    return json.loads(_graphql(request).content)


async def test_evidence_without_disease_is_two_step_with_scope(
    ot_service: OpenTargetsService, mocked_ot: respx.MockRouter
) -> None:
    p = await ot_service.get_target_disease_evidence(KRAS, datasource="gene_burden")
    efo_ids = _sent(mocked_ot, "TargetEvidence")[0]["efo_ids"]
    assert len(efo_ids) == p["disease_scope"]["diseases_considered"] > 1000
    assert p["disease_scope"]["complete"]
    row = p["evidence"][0]
    assert row["datasource_id"] == "gene_burden" and row["odds_ratio"] == 12.27
    assert p["total"] == 3 and not p["truncated"] and p["next_cursor"] is None


async def test_evidence_rows_label_variants_grch38() -> None:
    from opentargets_link.shaping import evidence_row

    row = evidence_row({"datasourceId": "eva", "variant": {"id": "7_140753336_A_T"}}, "compact")
    assert row["variant"] == {"id": "7_140753336_A_T", "assembly": "GRCh38"}


async def test_bad_cursor_names_the_parameter(ot_service: OpenTargetsService) -> None:
    with pytest.raises(InvalidInputError) as info:
        await ot_service.get_target_disease_evidence(BRAF, disease=MELANOMA, cursor="{bad}")
    assert info.value.extra["field"] == "cursor"


@pytest.mark.parametrize("cursor", ["invalid-cursor", "eyJ4IjoxfQ=="])  # not a page position
async def test_well_formed_but_foreign_cursor_is_rejected_not_page_one(
    ot_service: OpenTargetsService, cursor: str
) -> None:
    with pytest.raises(InvalidInputError) as info:
        await ot_service.get_target_disease_evidence(BRAF, disease=MELANOMA, cursor=cursor)
    assert info.value.extra["field"] == "cursor"


async def test_resolve_target_errors_name_query_and_never_loop(
    ot_service: OpenTargetsService,
) -> None:
    with pytest.raises(InvalidInputError) as bad:
        await ot_service.resolve_target("673")
    assert bad.value.extra["field"] == "query"
    with pytest.raises(NotFoundError) as missing:
        await ot_service.resolve_target("ENSG00000000001")
    assert missing.value.extra["field"] == "query"
    assert not missing.value.extra.get("next_commands")  # hgnc cannot map an unknown ENSG
    assert "symbol" in missing.value.extra["hint"]
    assert "genefoundry" in bad.value.extra["hint"]  # the sibling tool is named as such


def test_cache_default_is_bounded_for_large_ot_payloads() -> None:
    from opentargets_link.config import OpenTargetsSettings

    assert OpenTargetsSettings().cache_maxsize <= 128


def test_post_approval_stages_rank_and_read_as_approved() -> None:
    """Open Targets ranks WITHDRAWAL > PHASE_4 > APPROVAL; all three mean the drug was approved."""
    from opentargets_link.shaping import drug_row, stage_rank

    assert stage_rank("APPROVAL") == stage_rank("PHASE_4") == stage_rank("WITHDRAWAL")
    assert stage_rank("PHASE_4") < stage_rank("PHASE_3")
    node = {
        "maxClinicalStage": "PHASE_4",
        "drug": {"id": "CHEMBL2028663", "name": "DABRAFENIB", "parentMolecule": None},
    }
    assert drug_row(node, BRAF, "minimal", None)["approved"] is True
    salt = {
        "maxClinicalStage": "PHASE_3",
        "drug": {"id": "CHEMBL2105729", "parentMolecule": {"id": "CHEMBL2028663"}},
    }
    row = drug_row(salt, BRAF, "compact", None)
    assert row["approved"] is False and row["parent_drug_id"] == "CHEMBL2028663"


async def test_drug_payload_explains_stages(ot_service: OpenTargetsService) -> None:
    p = await ot_service.get_drug_candidates(BRAF, limit=5)
    assert "PHASE_4" in p["stage_note"] and "Salt" in p["stage_note"]


def test_gwas_credible_set_rows_carry_study_lead_variant_and_p_value() -> None:
    from opentargets_link import queries as Q
    from opentargets_link.shaping import evidence_row

    assert "credibleSet {" in Q.DISEASE_EVIDENCE and "credibleSet {" in Q.TARGET_EVIDENCE
    cs = {
        "studyLocusId": "a6ea",
        "study": {"id": "GCST90011809", "pubmedId": "32887889", "nSamples": 417127},
        "variant": {"id": "9_21965233_C_G", "rsIds": ["rs2188127"]},
        "pValueMantissa": 2.01,
        "pValueExponent": -7,
    }
    row = evidence_row({"datasourceId": "gwas_credible_sets", "credibleSet": cs}, "compact")
    assert row["credible_set"]["study"]["pubmedId"] == "32887889"
    assert row["credible_set"]["variant"]["assembly"] == "GRCh38"


def test_minimal_evidence_rows_keep_the_variant_id() -> None:
    from opentargets_link.shaping import evidence_row

    raw = {"id": "e1", "datasourceId": "eva_somatic", "variant": {"id": "7_140753336_A_T"}}
    assert evidence_row(raw, "minimal")["variant"]["id"] == "7_140753336_A_T"


def test_p_value_is_one_float_not_mantissa_and_exponent() -> None:
    from opentargets_link.shaping import evidence_row

    raw = {"id": "e1", "pValueMantissa": 5.253, "pValueExponent": -20, "oddsRatio": 9.8}
    row = evidence_row(raw, "compact")
    assert row["p_value"] == 5.253e-20 and "p_value_mantissa" not in row
