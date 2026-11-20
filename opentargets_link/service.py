"""Open Targets data plane: validate arguments, run fixed GraphQL documents, shape honest payloads.

Returns plain dicts and raises typed :mod:`opentargets_link.exceptions` errors; the MCP
envelope owns ``success``/``_meta``. Open Targets answers an unknown ID with ``null``: that
becomes ``not_found`` naming the argument, never a silent empty list. Evidence and scores
come only from the datasource allowlist (:mod:`opentargets_link.datasources`).
"""

from __future__ import annotations

import base64
import json
from collections import Counter
from datetime import UTC, datetime
from typing import Any

from opentargets_link import queries as Q
from opentargets_link.api.client import OpenTargetsClient
from opentargets_link.datasources import ALLOWED, ZERO_WEIGHTS
from opentargets_link.exceptions import (
    AmbiguousQueryError,
    InvalidInputError,
    NotFoundError,
    UpstreamSchemaError,
)
from opentargets_link.mcp.next_commands import cmd
from opentargets_link.shaping import (
    CURSOR,
    ENSEMBL_GENE,
    FOREIGN_DISEASE,
    FOREIGN_GENE,
    HGNC_ID,
    NO_DRUGS,
    NO_EVIDENCE,
    NOT_A_REPORT,
    SITE,
    STAGE_NOTE,
    SYMBOL,
    allowed_scores,
    disease_curie,
    drug_row,
    evidence_row,
    page_block,
    stage_rank,
    target_row,
)

DEFAULT_LIMIT = 10
MAX_LIMIT = 50
DRUG_MAX_LIMIT = 20  # full mode fences 1 + 3 texts per row; stay under the 128-fence ceiling
ASSOC_MAX_WINDOW = 3000  # Open Targets' largest page
GENE_FORMS = [
    "Ensembl gene ID (ENSG00000157764)",
    "HGNC symbol (BRAF)",
    "HGNC ID (HGNC:1097)",
]
DISEASE_FORMS = ["MONDO/EFO/Orphanet/HP ID (MONDO_0005105 or MONDO:0005105)", "disease name"]
HGNC_HINT = (
    "hgnc_resolve_symbol runs on the GeneFoundry hgnc server (call it through the genefoundry "
    "router); standalone, pass the approved HGNC symbol or the Ensembl gene ID."
)
MONDO_HINT = (
    "mondo_resolve_disease runs on the GeneFoundry mondo server (call it through the "
    "genefoundry router); standalone, pass the disease name, e.g. disease='melanoma'."
)
_FIELDS = {"target_id": "target", "disease_id": "disease", "size": "limit", "efo_ids": "disease"}


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _limit(limit: int, maximum: int, offset: int = 0) -> None:
    if not 1 <= limit <= maximum:
        raise InvalidInputError(f"`limit` must be 1-{maximum}.", field="limit")
    if offset < 0:
        raise InvalidInputError("`offset` must be >= 0.", field="offset")


def _position(cursor: Any) -> int | None:
    """Rows before the page a cursor points at, or None if it is not an Open Targets cursor.

    ponytail: reads the cursor's undocumented base64 ``{"index", "size"}`` (Open Targets
    answers any other string with page one, so we must check). If upstream changes the
    format, the live paging test fails and this decoder needs updating.
    """
    try:
        pos = json.loads(base64.b64decode(cursor, validate=True))
        return int(pos["index"]) * int(pos["size"])
    except ValueError, KeyError, TypeError:
        return None


def _more(cursor: Any, total: int) -> bool:
    """Whether rows remain after this page (Open Targets returns a cursor on the last page too)."""
    pos = _position(cursor) if isinstance(cursor, str) else None
    return pos is not None and pos < total


class OpenTargetsService:
    """All Open Targets queries; one instance per process over a shared client."""

    def __init__(self, client: OpenTargetsClient) -> None:
        """Bind the service to a rate-limited, cached upstream client."""
        self.client = client

    async def _q(self, document: str, variables: dict[str, Any]) -> dict[str, Any]:
        return await self.client.graphql(document, variables, fields=_FIELDS)

    async def release(self) -> str:
        """The Open Targets data release (``meta.dataVersion``), e.g. ``26.09``."""
        meta = (await self._q(Q.META, {})).get("meta") or {}
        v = meta.get("dataVersion") or {}
        if not v.get("year") or not v.get("month"):
            raise UpstreamSchemaError("Open Targets returned no data version.", field="meta")
        return f"{v['year']}.{v['month']}" + (f".{v['iteration']}" if v.get("iteration") else "")

    async def _stamp(self, payload: dict[str, Any]) -> dict[str, Any]:
        payload["data_version"] = await self.release()
        payload["retrieved_at"] = _now()
        payload["disclaimer"] = NOT_A_REPORT
        return payload

    # -- identifiers ----------------------------------------------------------------

    async def _map(self, query: str, entity: str) -> list[dict[str, Any]]:
        data = await self._q(Q.MAP_IDS, {"query": query, "entity": entity})
        mappings = (data.get("mapIds") or {}).get("mappings") or []
        return [h for m in mappings for h in m.get("hits") or []]

    async def _target_id(self, value: str, field: str = "target") -> tuple[str, str | None]:
        """Ensembl gene ID for ``value`` (+ the symbol it was resolved from, if any)."""
        term = value.strip()
        if ENSEMBL_GENE.fullmatch(term):
            return term.split(".")[0].upper(), None
        if FOREIGN_GENE.fullmatch(term):
            raise InvalidInputError(
                f"`{field}` takes an Ensembl gene ID, HGNC symbol or HGNC ID, not an NCBI "
                "Gene ID; convert it first.",
                field=field,
                allowed_values=GENE_FORMS,
                hint=HGNC_HINT,
                next_commands=[cmd("hgnc_resolve_symbol", query=term)],
                recovery_action="reformulate_input",
            )
        if HGNC_ID.fullmatch(term):
            term = term.upper()
        elif not SYMBOL.fullmatch(term):
            raise InvalidInputError(
                f"`{field}` must be an Ensembl gene ID or an HGNC symbol.",
                field=field,
                allowed_values=GENE_FORMS,
                hint=HGNC_HINT,
                next_commands=[cmd("hgnc_resolve_symbol", query=term[:60])],
            )
        hits = await self._map(term, "target")
        exact = [h for h in hits if str(h.get("name", "")).upper() == term.upper()]
        hits = exact or hits
        if not hits:
            raise NotFoundError(
                f"No Open Targets target matches `{field}`.",
                field=field,
                hint=HGNC_HINT,
                next_commands=[cmd("hgnc_resolve_symbol", query=term)],
            )
        if len(hits) > 1:
            raise AmbiguousQueryError(
                f"`{field}` matches {len(hits)} Open Targets targets.",
                field=field,
                candidates=[{"id": h.get("id"), "symbol": h.get("name")} for h in hits[:10]],
                next_commands=[cmd("resolve_target", query=str(h.get("id"))) for h in hits[:3]],
            )
        return str(hits[0]["id"]), term

    async def _disease(self, value: str) -> dict[str, Any]:
        """``{id, name, descendants, resolved_from}`` for a disease ID or name."""
        term = " ".join(value.split())
        if FOREIGN_DISEASE.match(term):
            raise InvalidInputError(
                "`disease` takes a MONDO/EFO/Orphanet/HP ID or a disease name; convert OMIM, "
                "DOID and other IDs to MONDO first.",
                field="disease",
                allowed_values=DISEASE_FORMS,
                hint=MONDO_HINT,
                next_commands=[cmd("mondo_resolve_disease", query=term)],
                recovery_action="reformulate_input",
            )
        disease_id = disease_curie(term)
        resolved_from = None
        if disease_id is None:
            hits = await self._map(term, "disease")
            us = term.replace("ae", "e").replace("oe", "e")  # haem-, oesophag-, -aemia
            if not hits and us != term:
                hits = await self._map(us, "disease")
            if not hits:
                raise self._no_disease(term)
            disease_id, resolved_from = str(hits[0]["id"]), term
        found = (await self._q(Q.DISEASE_GET, {"disease_id": disease_id})).get("disease")
        if not found:
            raise self._no_disease(term, by_id=resolved_from is None)
        return {**found, "resolved_from": resolved_from}

    @staticmethod
    def _no_disease(term: str, by_id: bool = False) -> NotFoundError:
        if by_id:  # a made-up or obsolete ID: no resolver can map it
            return NotFoundError(
                "No Open Targets disease has this `disease` ID (obsolete or not in Open Targets).",
                field="disease",
                hint="Pass the disease name instead, e.g. disease='melanoma'.",
            )
        return NotFoundError(
            "No Open Targets disease matches `disease`.",
            field="disease",
            hint=MONDO_HINT,
            next_commands=[cmd("mondo_resolve_disease", query=term)],
        )

    @staticmethod
    def _disease_block(d: dict[str, Any]) -> dict[str, Any]:
        block = {"id": d["id"], "name": d.get("name")}
        if d.get("resolved_from"):
            block["resolved_from"] = d["resolved_from"]
        return block

    async def _target(
        self, document: str, target: str, field: str = "target"
    ) -> tuple[dict[str, Any], str | None]:
        target_id, resolved_from = await self._target_id(target, field)
        raw = (await self._q(document, {"target_id": target_id})).get("target")
        if not raw:  # only an Ensembl ID reaches here (symbols resolve to existing targets)
            raise NotFoundError(
                f"No Open Targets target has this `{field}` (retired or not a gene ID).",
                field=field,
                hint="Pass the gene symbol to resolve_target(query) for the current Ensembl ID.",
            )
        return raw, resolved_from

    @staticmethod
    def _target_block(raw: dict[str, Any], resolved_from: str | None) -> dict[str, Any]:
        block = target_row(raw)
        if resolved_from:
            block["resolved_from"] = resolved_from
        return block

    # -- tools ----------------------------------------------------------------------

    async def resolve_target(self, query: str) -> dict[str, Any]:
        """Symbol, alias or Ensembl gene ID -> one target with location and synonyms."""
        raw, resolved_from = await self._target(Q.TARGET_GET, query, "query")
        loc = raw.get("genomicLocation") or {}
        target = self._target_block(raw, resolved_from)
        target["location"] = {"assembly": "GRCh38", **loc} if loc else None
        target["synonyms"] = sorted({s["label"] for s in raw.get("symbolSynonyms") or []})[:15]
        target["url"] = f"{SITE}/target/{raw.get('id')}"
        return await self._stamp({"target": target})

    async def get_target_tractability(self, target: str) -> dict[str, Any]:
        """Tractability buckets per modality, plus the ChEMBL target class."""
        raw, resolved_from = await self._target(Q.TRACTABILITY, target)
        modalities: dict[str, dict[str, list[str]]] = {}
        for t in raw.get("tractability") or []:
            m = modalities.setdefault(str(t.get("modality")), {"true": [], "false": []})
            m["true" if t.get("value") else "false"].append(str(t.get("label")))
        return await self._stamp(
            {
                "target": self._target_block(raw, resolved_from),
                "modality_legend": {
                    "SM": "small molecule",
                    "AB": "antibody",
                    "PR": "PROTAC",
                    "OC": "other clinical",
                },
                "tractability": modalities,
                "target_class": sorted({c["label"] for c in raw.get("targetClass") or []}),
            }
        )

    async def get_drug_candidates(
        self,
        target: str,
        *,
        disease: str | None = None,
        response_mode: str = "compact",
        limit: int = DEFAULT_LIMIT,
        offset: int = 0,
    ) -> dict[str, Any]:
        """ChEMBL drugs and clinical candidates acting on a target, most advanced first."""
        _limit(limit, DRUG_MAX_LIMIT, offset)
        document = Q.DRUGS_FULL if response_mode == "full" else Q.DRUGS
        raw, resolved_from = await self._target(document, target)
        dz = await self._disease(disease) if disease is not None else None
        wanted = {dz["id"], *(dz.get("descendants") or [])} if dz else None
        rows: list[dict[str, Any]] = []
        parents: set[str] = set()  # a salt counts with its parent drug
        conn = raw.get("drugAndClinicalCandidates") or {}
        for node in conn.get("rows") or []:
            matched = None
            if wanted is not None:
                found = {
                    d["disease"]["id"]: {"id": d["disease"]["id"], "name": d["disease"].get("name")}
                    for d in node.get("diseases") or []
                    if (d.get("disease") or {}).get("id") in wanted
                }
                if not found:
                    continue
                matched = list(found.values())
            rows.append(drug_row(node, raw["id"], response_mode, matched))
            drug = node.get("drug") or {}
            parents.add(str((drug.get("parentMolecule") or {}).get("id") or drug.get("id")))
        rows.sort(key=lambda r: (stage_rank(r["max_clinical_stage_for_target"]), r["drug_name"]))
        page = rows[offset : offset + limit]
        payload: dict[str, Any] = {
            "target": self._target_block(raw, resolved_from),
            "drug_candidates": page,
            **page_block(total=len(rows), returned=len(page), limit=limit, offset=offset),
            "parent_drugs_total": len(parents),
            "approved_total": sum(r["approved"] for r in rows),
            "stage_counts": dict(Counter(r["max_clinical_stage_for_target"] for r in rows)),
            "licence_note": "Drug and mechanism data derive from ChEMBL (CC BY-SA 3.0).",
        }
        if offset == 0:  # explained once, not on every page
            payload["stage_note"] = STAGE_NOTE
        if dz:
            payload["disease"] = self._disease_block(dz)
            payload["disease_scope"] = "this disease and its descendants"
        if not rows:
            payload["evidence_note"] = NO_DRUGS
        return await self._stamp(payload)

    async def search_disease_targets(
        self,
        disease: str,
        *,
        datasource: str | None = None,
        limit: int = DEFAULT_LIMIT,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Targets associated with a disease, ranked by the allowlist-only association score."""
        _limit(limit, MAX_LIMIT, offset)
        if offset + limit > ASSOC_MAX_WINDOW:
            raise InvalidInputError(
                f"`offset` + `limit` must be <= {ASSOC_MAX_WINDOW}.", field="offset"
            )
        dz = await self._disease(disease)
        weights = list(ZERO_WEIGHTS)
        if datasource is not None:
            weights.append({"id": datasource, "weight": 1.0, "propagate": True, "required": True})
        data = await self._q(
            Q.DISEASE_TARGETS,
            {
                "disease_id": dz["id"],
                "size": offset + limit,
                "datasources": weights,
                "order": datasource or "score",
            },
        )
        conn = ((data.get("disease") or {}).get("associatedTargets")) or {}
        rows = [
            {
                **target_row(r.get("target") or {}),
                "score": round(float(r.get("score") or 0.0), 4),
                "datasource_scores": allowed_scores(r.get("datasourceScores")),
            }
            for r in (conn.get("rows") or [])[offset:]
        ]
        for r in rows:
            r.pop("biotype", None)
        payload: dict[str, Any] = {
            "disease": self._disease_block(dz),
            "filters": {"datasource": datasource} if datasource else {},
            "ranked_by": datasource or "score",
            "targets": rows,
            **page_block(
                total=int(conn.get("count") or 0), returned=len(rows), limit=limit, offset=offset
            ),
            "score_note": "Association score recomputed by Open Targets with every "
            "non-served datasource at weight 0; targets supported only by those score 0.",
        }
        if not rows:
            payload["evidence_note"] = NO_EVIDENCE
        return await self._stamp(payload)

    async def get_target_disease_evidence(
        self,
        target: str,
        *,
        disease: str | None = None,
        datasource: str | None = None,
        response_mode: str = "compact",
        limit: int = DEFAULT_LIMIT,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        """Evidence rows linking a target to a disease (or to any disease) from served sources."""
        _limit(limit, MAX_LIMIT)
        if cursor is not None and (not CURSOR.fullmatch(cursor) or _position(cursor) is None):
            raise InvalidInputError(
                "`cursor` must be the `next_cursor` of a previous call.", field="cursor"
            )
        target_id, resolved_from = await self._target_id(target)
        sources = [datasource] if datasource else list(ALLOWED)
        page = {"datasource": sources, "limit": limit, "cursor": cursor}
        payload: dict[str, Any] = {}
        if disease is not None:
            dz = await self._disease(disease)
            data = await self._q(
                Q.DISEASE_EVIDENCE, {"disease_id": dz["id"], "target_id": target_id, **page}
            )
            conn = (data.get("disease") or {}).get("evidences") or {}
            payload["disease"] = self._disease_block(dz)
            payload["disease_scope"] = "this disease and its descendants"
        else:
            # Step 1: the target's associated diseases (allowlist-scored); step 2: their evidence.
            assoc = (
                (
                    await self._q(
                        Q.TARGET_DISEASES, {"target_id": target_id, "datasources": ZERO_WEIGHTS}
                    )
                ).get("target")
                or {}
            ).get("associatedDiseases") or {}
            efo_ids = [r["disease"]["id"] for r in assoc.get("rows") or [] if r.get("disease")]
            total_diseases = int(assoc.get("count") or 0)
            payload["disease_scope"] = {
                "diseases_considered": len(efo_ids),
                "diseases_total": total_diseases,
                "complete": len(efo_ids) >= total_diseases,
            }
            conn = {}
            if efo_ids:
                data = await self._q(
                    Q.TARGET_EVIDENCE, {"target_id": target_id, "efo_ids": efo_ids, **page}
                )
                conn = (data.get("target") or {}).get("evidences") or {}
        if not conn and disease is None and payload["disease_scope"]["diseases_total"] == 0:
            await self._target(Q.TARGET_GET, target_id)  # unknown target -> not_found
        raw_rows = conn.get("rows") or []
        rows = [
            evidence_row(r, response_mode) for r in raw_rows if r.get("datasourceId") in ALLOWED
        ]
        total = int(conn.get("count") or 0)
        next_cursor = conn.get("cursor") if raw_rows and _more(conn.get("cursor"), total) else None
        payload.update(
            {
                "target": {
                    "id": target_id,
                    **({"resolved_from": resolved_from} if resolved_from else {}),
                },
                "filters": {"datasource": datasource} if datasource else {},
                "served_datasources": sources,
                "evidence": rows,
                "total": total,
                "returned": len(rows),
                "truncated": next_cursor is not None,
                "next_cursor": next_cursor,
            }
        )
        if dropped := len(raw_rows) - len(rows):
            payload["filtered_out"] = dropped
        if not rows:
            payload["evidence_note"] = NO_EVIDENCE
        return await self._stamp(payload)
