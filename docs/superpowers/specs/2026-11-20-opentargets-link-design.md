# opentargets-link design

> Historical record — design as approved for v0.1.0 on 2026-11-20 (cancer/somatic expansion plan §3 item 6, evidence report H). Later changes live in CHANGELOG.md.

## Goal

A GeneFoundry `-link` backend for the Open Targets Platform GraphQL API
(`https://api.platform.opentargets.org/api/v4/graphql`, data release 26.09, CC0 1.0):
target tractability, drug and clinical candidates, disease→target ranking and
target–disease evidence, under the fleet standards. It is the fleet's drug/driver layer
(owner decision 2026-11-20: no DGIdb / IntOGen links). `opentargets/platform-mcp` is not
federated (raw GraphQL passthrough, over the tool budget).

## Tools (namespace `opentargets`)

| Tool | Upstream | Notes |
|---|---|---|
| `resolve_target(query)` | `mapIds` / `target` | entry point; symbol, alias or Ensembl ID → target |
| `get_target_tractability(target)` | `Target.tractability` | buckets per modality (SM/AB/PR/OC) |
| `get_drug_candidates(target, disease=, response_mode=, limit=, offset=)` | `Target.drugAndClinicalCandidates` | `knownDrugs` is gone; clinical reports only in `full` (top 5/row) |
| `search_disease_targets(disease, datasource=, limit=, offset=)` | `Disease.associatedTargets` | score recomputed with every non-allowlisted datasource at weight 0 |
| `get_target_disease_evidence(target, disease=, datasource=, limit=, cursor=)` | `Disease.evidences` / `Target.evidences` | without `disease`: two steps, associated diseases → `efoIds` |
| `get_server_capabilities`, `get_diagnostics` | — | fleet discovery tools |

Germline bonus at zero extra tools: `gwas_credible_sets` and `gene_burden` are allowlisted
evidence datasources.

## Datasource allowlist

Evidence and association scores only ever come from an **allowlist**
(`opentargets_link/datasources.py`): intogen, eva_somatic, eva, clinical_precedence,
gene_burden, gwas_credible_sets, clingen, orphanet, gene2phenotype, uniprot_variants,
uniprot_literature, reactome, impc, expression_atlas.

Excluded: `cancer_gene_census` (COSMIC; "commercial use for Open Targets"), the same class
`genomics_england` and `crispr` (Project Score), `europepmc` (mixed CC BY-NC text mining),
`cancer_biomarkers` (held: CGI CC BY vs CC BY-NC conflict), `crispr_screen` (licence not
listed), partner-only `ot_crispr*`/`encore`, and any datasource added upstream later.
COSMIC hallmarks (`Target.hallmarks`) are never queried. Rows from a non-allowlisted
datasource are dropped client-side as a second line of defence.

## Contracts

- Fixed GraphQL documents only (`queries.py`); arguments travel as variables named after
  the tool parameter, so an upstream `Variable '$x'` error is `invalid_input` naming `x`.
- `data_version` = the OT data release from `meta.dataVersion` (e.g. `26.09`) on every
  payload. A GraphQL "Cannot query field" error is upstream schema drift; the live
  integration test checks `meta` against the tested release and runs every document.
- ~3 req/s process-wide (`min_interval_s=0.34`), in-process cache, honest `total`/`truncated`.
- Free text (mechanism-of-action strings, trial titles) is fenced as `untrusted_text`.
- Identifiers: targets = Ensembl gene ID or symbol; HGNC/NCBI Gene IDs are rejected with
  `hgnc_resolve_symbol`. Diseases = MONDO/EFO/Orphanet/HP ID or name; OMIM/DOID are rejected
  with `mondo_resolve_disease`. Drugs = ChEMBL IDs.
- An empty answer says "no Open Targets data found", never "not druggable" or "no drug".
