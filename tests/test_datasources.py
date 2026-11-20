"""Guard: the evidence datasource ALLOWLIST and what it must never contain."""

from __future__ import annotations

from opentargets_link import queries as Q
from opentargets_link.datasources import ALLOWED, EXCLUDED, ZERO_WEIGHTS

#: Licence-gated: COSMIC / "commercial use for Open Targets" grants, NC text mining, held CGI.
MUST_NEVER_SERVE = {
    "cancer_gene_census",
    "genomics_england",
    "crispr",
    "europepmc",
    "cancer_biomarkers",
}


def test_allowlist_never_contains_licence_gated_sources() -> None:
    assert not MUST_NEVER_SERVE & set(ALLOWED)
    assert set(EXCLUDED) >= MUST_NEVER_SERVE
    assert not set(ALLOWED) & set(EXCLUDED)


def test_allowlist_is_the_reviewed_set() -> None:
    # Adding a datasource is a licence decision: update this set in the same PR as its review.
    assert set(ALLOWED) == {
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
    }


def test_every_excluded_source_is_zero_weighted_in_scores() -> None:
    assert {w["id"] for w in ZERO_WEIGHTS if w["weight"] == 0.0} == set(EXCLUDED)


def test_no_fixed_query_selects_cosmic_hallmarks_or_names_a_datasource() -> None:
    for name, doc in Q.ALL.items():
        assert "hallmarks" not in doc, name
        assert not any(source in doc for source in EXCLUDED), name
