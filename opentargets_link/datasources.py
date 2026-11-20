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

#: Known upstream datasources that are not served (-> why); their weight is forced to 0.
_COMMERCIAL = "licensed to Open Targets users only, not to a third-party gateway"
EXCLUDED: dict[str, str] = {
    "cancer_gene_census": f"COSMIC Cancer Gene Census is {_COMMERCIAL}",
    "genomics_england": f"Genomics England PanelApp is {_COMMERCIAL}",
    "crispr": f"Project Score is {_COMMERCIAL}",
    "europepmc": "Europe PMC text mining covers CC BY-NC publications",
    "cancer_biomarkers": "Cancer Genome Interpreter biomarkers have conflicting licence terms",
    "crispr_screen": "no licence is listed by Open Targets",
    "ot_crispr": "Open Targets partner-only data",
    "ot_crispr_validation": "Open Targets partner-only data",
    "encore": "Open Targets partner-only data",
}

#: ``datasources`` input for association queries: excluded sources contribute nothing.
ZERO_WEIGHTS: list[dict[str, object]] = [
    {"id": d, "weight": 0.0, "propagate": False} for d in EXCLUDED
]
