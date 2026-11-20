"""Pure shapers and argument forms: Open Targets GraphQL nodes -> compact, honest rows.

Identifiers and controlled vocabularies pass through verbatim. Free text from upstream
(ChEMBL mechanism-of-action strings, clinical-report titles) is fenced as
``untrusted_text``. Open Targets variant IDs (``7_140753336_A_T``) are GRCh38.
"""

from __future__ import annotations

import re
from typing import Any

from opentargets_link.datasources import ALLOWED
from opentargets_link.mcp.untrusted_content import fence_untrusted_text

SITE = "https://platform.opentargets.org"

NOT_A_REPORT = (
    "Research use only; this is not a clinical actionability report and not clinical "
    "decision support."
)
NO_DRUGS = (
    "No Open Targets drug or clinical candidate found. Open Targets lists ChEMBL "
    "mechanism-of-action drugs only: this does not mean no drug acts on this target or "
    "disease (see civic for biomarker-based therapy evidence)."
)
NO_EVIDENCE = (
    "No Open Targets evidence from the served datasources. Absence of evidence here is "
    "not evidence that the target is unrelated to the disease."
)

#: Argument forms.
ENSEMBL_GENE = re.compile(r"^ENSG\d{11}(?:\.\d+)?$", re.IGNORECASE)
FOREIGN_GENE = re.compile(r"^(?:HGNC:\d+|(?:NCBIGene|Entrez(?:Gene)?):\d+|\d{1,9})$", re.I)
SYMBOL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.\-_@]{0,29}$")
DISEASE_ID = re.compile(r"^(MONDO|EFO|Orphanet|HP|OTAR|OBA)[_:](\d{1,9})$", re.IGNORECASE)
FOREIGN_DISEASE = re.compile(r"^(?:OMIM|MIM|DOID|ORPHA|ICD10|ICD-?10|UMLS|MESH|NCIT):", re.I)
CURSOR = re.compile(r"^[A-Za-z0-9+/=_-]{1,200}$")

#: Clinical stages, most advanced first (Open Targets enum strings).
STAGES = (
    "APPROVAL",
    "PHASE_4",
    "PHASE_3",
    "PHASE_2_3",
    "PHASE_2",
    "PHASE_1_2",
    "PHASE_1",
    "EARLY_PHASE_1",
    "PRECLINICAL",
    "UNKNOWN",
)


def stage_rank(stage: Any) -> int:
    """Sort key: lower is more advanced; unknown strings sort last."""
    return STAGES.index(stage) if stage in STAGES else len(STAGES)


def disease_curie(value: str) -> str | None:
    """``MONDO:0005105`` / ``mondo_0005105`` -> ``MONDO_0005105``; None if not a disease ID."""
    match = DISEASE_ID.fullmatch(value.strip())
    if not match:
        return None
    prefix = {"orphanet": "Orphanet"}.get(match.group(1).lower(), match.group(1).upper())
    return f"{prefix}_{match.group(2)}"


def fence(raw: Any, record_id: str) -> dict[str, Any] | None:
    """Fence one upstream prose value (``None``/empty stays ``None``)."""
    if not isinstance(raw, str) or not raw.strip():
        return None
    return fence_untrusted_text(raw, source="opentargets", record_id=record_id).model_dump(
        mode="json"
    )


def page_block(*, total: int, returned: int, limit: int, offset: int) -> dict[str, Any]:
    """Uniform offset pagination block; ``total`` is the full result-set size."""
    truncated = offset + returned < total
    return {
        "total": total,
        "returned": returned,
        "limit": limit,
        "offset": offset,
        "truncated": truncated,
        "next_offset": offset + returned if truncated else None,
    }


def target_row(raw: dict[str, Any]) -> dict[str, Any]:
    """A target's identity."""
    return {
        "id": raw.get("id"),
        "symbol": raw.get("approvedSymbol"),
        "name": raw.get("approvedName"),
        "biotype": raw.get("biotype"),
    }


def allowed_scores(raw: Any) -> dict[str, float]:
    """Per-datasource scores, allowlisted datasources only."""
    return {
        s["id"]: round(float(s.get("score") or 0.0), 4)
        for s in raw or []
        if isinstance(s, dict) and s.get("id") in ALLOWED
    }


def drug_row(
    raw: dict[str, Any], target_id: str, mode: str, matched: list[dict[str, Any]] | None
) -> dict[str, Any]:
    """One drug/clinical candidate for a target at one response_mode."""
    drug = raw.get("drug") or {}
    out: dict[str, Any] = {
        "drug_id": drug.get("id"),
        "drug_name": drug.get("name"),
        "max_clinical_stage_for_target": raw.get("maxClinicalStage"),
    }
    if mode == "minimal":
        return out
    moa = [
        m
        for m in (drug.get("mechanismsOfAction") or {}).get("rows") or []
        if any(t.get("id") == target_id for t in m.get("targets") or [])
    ]
    seen: dict[str, dict[str, Any]] = {}
    for d in raw.get("diseases") or []:
        if (dz := d.get("disease")) and dz.get("id") not in seen:
            seen[dz["id"]] = {"id": dz["id"], "name": dz.get("name")}
    diseases = matched if matched is not None else list(seen.values())
    out.update(
        {
            "drug_type": drug.get("drugType"),
            "drug_max_clinical_stage": drug.get("maximumClinicalStage"),
            "action_types": sorted({m["actionType"] for m in moa if m.get("actionType")}),
            "diseases": diseases[:10],
            "diseases_total": len(diseases),
        }
    )
    if mode in ("standard", "full"):
        text = "; ".join(
            sorted({m["mechanismOfAction"] for m in moa if m.get("mechanismOfAction")})
        )
        out["mechanism_of_action"] = fence(text, str(drug.get("id")))
    if mode == "full":
        reports = sorted(
            raw.get("clinicalReports") or [],
            key=lambda r: (stage_rank(r.get("clinicalStage")), -(r.get("year") or 0)),
        )
        out["clinical_reports_total"] = len(reports)
        out["clinical_reports"] = [
            {
                "id": r.get("id"),
                "source": r.get("source"),
                "clinical_stage": r.get("clinicalStage"),
                "status": r.get("trialOverallStatus"),
                "year": r.get("year"),
                "url": r.get("url"),
                "title": fence(r.get("title"), str(r.get("id"))),
            }
            for r in reports[:3]
        ]
    return out


def _snake(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


_MINIMAL = ("id", "datasource_id", "datatype_id", "score", "disease")


def evidence_row(raw: dict[str, Any], mode: str) -> dict[str, Any]:
    """One evidence row: non-empty upstream fields in snake_case, variants labelled GRCh38."""
    out: dict[str, Any] = {}
    for key, value in raw.items():
        if value is None or value == [] or (key == "literature" and mode == "compact"):
            continue
        if key == "variant":
            value = {"id": value.get("id"), "assembly": "GRCh38"}
        out[_snake(key)] = value
    if mode == "minimal":
        return {k: out[k] for k in _MINIMAL if k in out}
    return out
