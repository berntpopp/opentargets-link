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
FOREIGN_GENE = re.compile(r"^(?:(?:NCBIGene|Entrez(?:Gene)?):\d+|\d{1,9})$", re.I)
HGNC_ID = re.compile(r"^HGNC:\d{1,7}$", re.I)  # Open Targets mapIds resolves these itself
SYMBOL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.\-_@]{0,29}$")
DISEASE_ID = re.compile(r"^(MONDO|EFO|Orphanet|HP|OTAR|OBA)[_:](\d{1,9})$", re.IGNORECASE)
FOREIGN_DISEASE = re.compile(r"^(?:OMIM|MIM|DOID|ORPHA|ICD10|ICD-?10|UMLS|MESH|NCIT):", re.I)
FOREIGN_DISEASE_ID = re.compile(FOREIGN_DISEASE.pattern + r"[A-Za-z0-9._-]{1,30}$", re.I)
CURSOR = re.compile(r"^[A-Za-z0-9+/=_-]{1,200}$")

#: Clinical stages, most advanced first (Open Targets enum strings).
STAGES = (
    "APPROVAL",
    "PHASE_3",
    "PHASE_2_3",
    "PHASE_2",
    "PHASE_1_2",
    "PHASE_1",
    "EARLY_PHASE_1",
    "PRECLINICAL",
    "UNKNOWN",
)
#: Open Targets ranks WITHDRAWAL > PHASE_4 (post-marketing) > APPROVAL when it picks a drug's
#: stage for a target, so an approved drug with phase-4 trials shows PHASE_4. All three mean
#: the drug reached approval; they share the APPROVAL tier.
APPROVED_STAGES = frozenset({"APPROVAL", "PHASE_4", "WITHDRAWAL"})
STAGE_NOTE = (
    "max_clinical_stage_for_target is Open Targets' highest stage for this drug and target; "
    "Open Targets ranks WITHDRAWAL above PHASE_4 (post-marketing trials) above APPROVAL, so "
    "all three mean the drug was approved somewhere (approved=true). drug_max_clinical_stage "
    "covers any target. Salt forms (e.g. DABRAFENIB MESYLATE) are separate ChEMBL records; "
    "parent_drug_id links them. Stages lag regulators and are not indication-specific."
)


def stage_rank(stage: Any) -> int:
    """Sort key: lower is more advanced; unknown strings sort last."""
    if stage in APPROVED_STAGES:
        return 0
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
        "approved": raw.get("maxClinicalStage") in APPROVED_STAGES,
    }
    if mode == "minimal":
        return out
    if parent := (drug.get("parentMolecule") or {}).get("id"):
        out["parent_drug_id"] = parent
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


_MINIMAL = ("id", "datasource_id", "score", "disease", "variant")


def _p_and_floats(d: dict[str, Any], mantissa: str, exponent: str, round_: bool) -> dict[str, Any]:
    """One ``p_value`` float from mantissa/exponent; floats to 4 significant digits if asked.

    Upstream floats are float32 noise past 4 significant digits (OR 9.81350040435791).
    """
    m, e = d.pop(mantissa, None), d.pop(exponent, None)
    if m is not None and e is not None:
        d["p_value"] = float(f"{m}e{e}")
    return {k: float(f"{v:.4g}") if round_ and isinstance(v, float) else v for k, v in d.items()}


def evidence_row(raw: dict[str, Any], mode: str) -> dict[str, Any]:
    """One evidence row: non-empty upstream fields in snake_case, variants labelled GRCh38."""
    compact = mode in ("minimal", "compact")
    out: dict[str, Any] = {}
    for key, value in raw.items():
        if value is None or value == [] or (key == "literature" and mode == "compact"):
            continue
        if key == "variant":
            value = {"id": value.get("id"), "assembly": "GRCh38"}
        if key == "credibleSet":
            if value.get("variant"):
                value = {**value, "variant": {**value["variant"], "assembly": "GRCh38"}}
            value = _p_and_floats(dict(value), "pValueMantissa", "pValueExponent", compact)
        out[_snake(key)] = value
    out = _p_and_floats(out, "p_value_mantissa", "p_value_exponent", compact)
    if not compact:
        return out
    out.pop("datatype_id", None)  # implied by datasource_id
    if mode == "minimal":
        return {k: out[k] for k in _MINIMAL if k in out}
    return out
