"""Open Targets evidence datasources this server may serve: an ALLOWLIST, never a denylist.

A datasource added upstream stays out until it is reviewed and listed here. Excluded on
purpose (and guarded by tests/test_datasources.py):

- ``cancer_gene_census`` (COSMIC), ``genomics_england`` (PanelApp) and ``crispr`` (Project
  Score): OT lists them as "commercial use for Open Targets"; that grant covers Open Targets
  users, not a third-party gateway.
- ``europepmc``: text mining over mixed CC BY / CC BY-NC publications.
- ``cancer_biomarkers`` (CGI): HELD while OT (CC BY 4.0) and DGIdb (CC BY-NC 4.0) disagree.
- ``crispr_screen`` (licence not listed by OT) and partner-only ``ot_crispr``,
  ``ot_crispr_validation``, ``encore``.

COSMIC hallmarks (``Target.hallmarks``) are never queried.
"""

from __future__ import annotations

from typing import Literal, get_args

Datasource = Literal[
    "intogen",
    "eva_somatic",
    "eva",
    "clinical_precedence",
    "gene_burden",
    "gwas_credible_sets",
    "clingen",
    "orphanet",
    "gene2phenotype",
    "uniprot_variants",
    "uniprot_literature",
    "reactome",
    "impc",
    "expression_atlas",
]
ALLOWED: tuple[str, ...] = get_args(Datasource)

#: Known upstream datasources that are not served; their weight is forced to 0 in scores.
EXCLUDED: tuple[str, ...] = (
    "cancer_gene_census",
    "genomics_england",
    "crispr",
    "europepmc",
    "cancer_biomarkers",
    "crispr_screen",
    "ot_crispr",
    "ot_crispr_validation",
    "encore",
)

#: ``datasources`` input for association queries: excluded sources contribute nothing.
ZERO_WEIGHTS: list[dict[str, object]] = [
    {"id": d, "weight": 0.0, "propagate": False} for d in EXCLUDED
]
