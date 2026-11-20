"""Open Targets tools: targets, tractability, drug candidates, disease targets and evidence."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Annotated, Any, Literal

from pydantic import Field, StrictInt

from opentargets_link.datasources import Datasource
from opentargets_link.mcp.annotations import READ_ONLY_OPEN_WORLD
from opentargets_link.mcp.envelope import McpErrorContext, ToolReturn, run_mcp_tool
from opentargets_link.mcp.next_commands import cmd
from opentargets_link.mcp.service_adapters import get_opentargets_service
from opentargets_link.service import DEFAULT_LIMIT, DRUG_MAX_LIMIT, MAX_LIMIT

if TYPE_CHECKING:
    from fastmcp import FastMCP

Target = Annotated[
    str,
    Field(
        min_length=1,
        max_length=40,
        description="Ensembl gene ID (ENSG00000157764), HGNC symbol (BRAF) or HGNC ID.",
        examples=["BRAF"],
    ),
]
_Disease = Annotated[str, Field(min_length=2, max_length=200)]
DiseaseArg = Annotated[
    _Disease,
    Field(
        description="MONDO/EFO/HP ID (MONDO_0005105) or disease name (melanoma, top match is "
        "reported as resolved_from); covers descendants.",
        examples=["MONDO_0005105"],
    ),
]
OptDisease = Annotated[
    _Disease | None,
    Field(description="Only this disease and its descendants (MONDO/EFO/HP ID or name)."),
]
OptSource = Annotated[
    Datasource | None,
    Field(description="Only this served datasource (intogen = somatic drivers)."),
]
Offset = Annotated[
    StrictInt, Field(ge=0, description="Rows to skip; use the previous `next_offset`.")
]
Mode = Annotated[
    Literal["minimal", "compact", "standard", "full"],
    Field(
        description="Row detail. minimal: IDs, stage or score, disease, variant; compact "
        "(default): key fields, floats to 4 significant digits; standard: upstream values "
        "verbatim (+ literature, drug mechanism); full: + top 3 drug clinical reports."
    ),
]


Limit = Annotated[
    StrictInt,
    Field(ge=1, le=MAX_LIMIT, description=f"Max rows (default {DEFAULT_LIMIT}, max {MAX_LIMIT})."),
]
DrugLimit = Annotated[
    StrictInt,
    Field(
        ge=1,
        le=DRUG_MAX_LIMIT,
        description=f"Max rows (default {DEFAULT_LIMIT}, max {DRUG_MAX_LIMIT}).",
    ),
]


def _set(**values: Any) -> dict[str, Any]:
    return {k: v for k, v in values.items() if v is not None}


async def _run(
    tool: str,
    args: dict[str, Any],
    fetch: Callable[[], Awaitable[dict[str, Any]]],
    steps: Callable[[dict[str, Any]], list[dict[str, Any]]],
) -> ToolReturn:
    async def call() -> dict[str, Any]:
        payload = await fetch()
        payload["_meta"] = {"next_commands": steps(payload)}
        return payload

    return await run_mcp_tool(tool, call, context=McpErrorContext(tool, arguments=args))


def _next(p: dict[str, Any], tool: str, args: dict[str, Any]) -> list[dict[str, Any]]:
    if p.get("next_offset") is not None:
        return [cmd(tool, **{**args, "offset": p["next_offset"]})]
    if p.get("next_cursor"):
        return [cmd(tool, **{**args, "cursor": p["next_cursor"]})]
    return []


def register_opentargets_tools(mcp: FastMCP) -> None:
    """Register the Open Targets tools on a FastMCP instance."""

    @mcp.tool(
        name="resolve_target",
        annotations=READ_ONLY_OPEN_WORLD,
        output_schema=None,
        tags={"targets"},
        description=(
            "Return one Open Targets target (Ensembl gene ID, symbol, name, biotype, GRCh38 "
            "location, synonyms) for a symbol, alias (HER2) or Ensembl ID. Start here. "
            "Signature: resolve_target(query)."
        ),
    )
    async def resolve_target(
        query: Annotated[
            str,
            Field(
                min_length=1,
                max_length=40,
                description="HGNC symbol, alias, HGNC ID or Ensembl gene ID.",
                examples=["BRAF"],
            ),
        ],
    ) -> ToolReturn:
        def steps(p: dict[str, Any]) -> list[dict[str, Any]]:
            tid = p["target"]["id"]
            return [
                cmd("get_target_tractability", target=tid),
                cmd("get_drug_candidates", target=tid),
            ]

        return await _run(
            "resolve_target",
            {"query": query},
            lambda: get_opentargets_service().resolve_target(query),
            steps,
        )

    @mcp.tool(
        name="get_target_tractability",
        annotations=READ_ONLY_OPEN_WORLD,
        output_schema=None,
        tags={"targets"},
        description=(
            "Return a target's tractability buckets per modality (SM small molecule, AB "
            "antibody, PR PROTAC, OC other), split into true/false labels such as 'Approved "
            "Drug' or 'High-Quality Pocket', plus its ChEMBL target class. "
            "Signature: get_target_tractability(target)."
        ),
    )
    async def get_target_tractability(target: Target) -> ToolReturn:
        return await _run(
            "get_target_tractability",
            {"target": target},
            lambda: get_opentargets_service().get_target_tractability(target),
            lambda p: [cmd("get_drug_candidates", target=p["target"]["id"])],
        )

    @mcp.tool(
        name="get_drug_candidates",
        annotations=READ_ONLY_OPEN_WORLD,
        output_schema=None,
        tags={"drugs"},
        description=(
            "Return ChEMBL drugs and clinical candidates acting on a target, most advanced "
            "stage first: ChEMBL ID, name, stage for this target, action types, indications. "
            "disease= keeps drugs studied in that disease or its descendants. standard adds "
            "fenced mechanism text; full adds the top 3 clinical reports. Stages lag "
            "regulators; empty is not 'no drug'. Signature: get_drug_candidates(target, "
            "disease=, response_mode=, limit=, offset=)."
        ),
    )
    async def get_drug_candidates(
        target: Target,
        disease: OptDisease = None,
        response_mode: Mode = "compact",
        limit: DrugLimit = DEFAULT_LIMIT,
        offset: Offset = 0,
    ) -> ToolReturn:
        args = _set(
            target=target,
            disease=disease,
            response_mode=None if response_mode == "compact" else response_mode,
            limit=limit,
            offset=offset,
        )
        return await _run(
            "get_drug_candidates",
            args,
            lambda: get_opentargets_service().get_drug_candidates(
                target, disease=disease, response_mode=response_mode, limit=limit, offset=offset
            ),
            lambda p: _next(p, "get_drug_candidates", args),
        )

    @mcp.tool(
        name="search_disease_targets",
        annotations=READ_ONLY_OPEN_WORLD,
        output_schema=None,
        tags={"associations"},
        description=(
            "Return targets associated with a disease, ranked by Open Targets association "
            "score recomputed from served datasources only, with per-datasource scores. "
            "datasource= keeps targets with that source and ranks by its score (ranked_by): "
            "'intogen' somatic cancer drivers; 'gene_burden' or 'gwas_credible_sets' germline "
            "signals. `total` is exact. "
            "Signature: search_disease_targets(disease, datasource=, limit=, offset=)."
        ),
    )
    async def search_disease_targets(
        disease: DiseaseArg,
        datasource: OptSource = None,
        limit: Limit = DEFAULT_LIMIT,
        offset: Offset = 0,
    ) -> ToolReturn:
        args = _set(disease=disease, datasource=datasource, limit=limit, offset=offset)

        def steps(p: dict[str, Any]) -> list[dict[str, Any]]:
            top = [
                cmd("get_target_disease_evidence", target=t["id"], disease=p["disease"]["id"])
                for t in p["targets"][:1]
            ]
            return _next(p, "search_disease_targets", args) + top

        return await _run(
            "search_disease_targets",
            args,
            lambda: get_opentargets_service().search_disease_targets(
                disease, datasource=datasource, limit=limit, offset=offset
            ),
            steps,
        )

    @mcp.tool(
        name="get_target_disease_evidence",
        annotations=READ_ONLY_OPEN_WORLD,
        output_schema=None,
        tags={"evidence"},
        description=(
            "Return evidence rows linking a target to a disease and its descendants (or, "
            "without disease, to every associated disease) from served datasources only: "
            "IntOGen drivers (cohort, methods, q-value), ClinVar somatic/germline (GRCh38 "
            "variant), clinical precedence, gene burden, GWAS credible sets. Page with "
            "next_cursor. Signature: get_target_disease_evidence(target, disease=, "
            "datasource=, response_mode=, limit=, cursor=)."
        ),
    )
    async def get_target_disease_evidence(
        target: Target,
        disease: OptDisease = None,
        datasource: OptSource = None,
        response_mode: Mode = "compact",
        limit: Limit = DEFAULT_LIMIT,
        cursor: Annotated[
            str | None,
            Field(max_length=200, description="The previous call's `next_cursor`."),
        ] = None,
    ) -> ToolReturn:
        args = _set(
            target=target,
            disease=disease,
            datasource=datasource,
            response_mode=None if response_mode == "compact" else response_mode,
            limit=limit,
            cursor=cursor,
        )
        return await _run(
            "get_target_disease_evidence",
            args,
            lambda: get_opentargets_service().get_target_disease_evidence(
                target,
                disease=disease,
                datasource=datasource,
                response_mode=response_mode,
                limit=limit,
                cursor=cursor,
            ),
            lambda p: _next(p, "get_target_disease_evidence", args),
        )
