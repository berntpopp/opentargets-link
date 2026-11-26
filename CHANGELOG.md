# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] - 2026-11-26

### Added

- Response-Envelope Standard v1.2: every successful data result carries `_meta.source`,
  `_meta.data_version` (the Open Targets data release, e.g. `26.09`) and `_meta.retrieved_at`
  (UTC time of the oldest upstream fetch behind the result; a cache hit keeps the time of the
  fetch that filled its entry).
- Schema tests: every data tool result is validated against the vendored
  `envelope-v1.2.schema.json` (genefoundry-envelope v1.2.0, sha256-pinned).

### Changed

- **Breaking:** the primary payload key is now `results` (`get_drug_candidates`,
  `search_disease_targets`, `get_target_disease_evidence`) or `result` (`resolve_target`,
  `get_target_tractability`), per Response-Envelope Standard v1 §1. It was `drug_candidates`,
  `targets`, `evidence`, `target` (in `resolve_target`) and `tractability`.
- Re-vendored `tests/conformance/behaviour.py` from genefoundry-router (v1.2 provenance check).

### Deprecated

- The top-level `data_version` and `retrieved_at` of a data result. Read them from `_meta`;
  the top-level copies will be removed in the next minor release.

## [0.1.1] - 2026-11-20

Fixes from an agent UX evaluation (Claude Code, Codex, Antigravity; five rounds, see
`docs/benchmarks/agent-ux-results.md`). No tool or parameter was added or renamed.

### Fixed

- `get_drug_candidates`: Open Targets picks a drug's stage for a target as WITHDRAWAL >
  PHASE_4 > APPROVAL, so approved drugs (vemurafenib) showed PHASE_4 and withdrawn-somewhere
  drugs (gefitinib) sorted to the last page. The three now share the top tier; rows carry
  `approved` and, for salt forms, `parent_drug_id`; `stage_note` (first page) explains.
- `get_target_disease_evidence`: GWAS credible-set rows carry the study, lead variant
  (GRCh38), p-value, beta and fine-mapping method (`credible_set`); a cursor that is not an
  Open Targets page position is `invalid_input` instead of silently returning page one;
  minimal rows keep the variant ID; `p_value` is one float instead of mantissa/exponent.
- Requesting an excluded datasource (`cancer_gene_census`, `europepmc`, `cancer_biomarkers`,
  ...) names the licence reason it is not served.
- Recovery hints name `hgnc_resolve_symbol` / `mondo_resolve_disease` as GeneFoundry sibling
  tools with a standalone alternative; an unknown Ensembl or MONDO ID no longer suggests a
  resolver that cannot map it.
- Disease names in British spelling (`hypercholesterolaemia`, `oesophageal`) are retried in US
  spelling; HP IDs are documented as accepted.
- `get_diagnostics` counts argument rejections as errors.

### Changed

- `search_disease_targets(datasource=)` ranks by that datasource's score (`ranked_by`;
  `score_note` names the sort key), not the overall score.
- HGNC IDs (`HGNC:1097`) resolve through Open Targets instead of being rejected.
- `get_drug_candidates` reports `stage_counts`, `approved_total` and `parent_drugs_total`
  over every row, not just the page.
- Compact and minimal evidence rows round float32 noise to 4 significant digits and drop
  `datatype_id` (implied by `datasource_id`); standard/full keep upstream values verbatim.
  The `response_mode` parameter says what each mode returns.

### Added

- Agent UX evaluation harness: `docs/benchmarks/` (protocol, frozen tasks, results) and
  `scripts/agent_ux_{eval,session}.sh`, `scripts/agent_ux_scores.py`.

## [0.1.0] - 2026-11-20

### Added

- First release: a read-only MCP server over the live Open Targets Platform GraphQL API
  (https://api.platform.opentargets.org/api/v4/graphql, data release 26.09), router namespace
  `opentargets`. Tools: `resolve_target` (entry resolver: symbol, alias or Ensembl gene ID),
  `get_target_tractability`, `get_drug_candidates` (upstream `drugAndClinicalCandidates`;
  clinical reports only in `response_mode="full"`), `search_disease_targets`,
  `get_target_disease_evidence` (two-step associations → `efoIds` without a disease), plus
  `get_server_capabilities` and `get_diagnostics`.
- Evidence datasource ALLOWLIST: `cancer_gene_census` (COSMIC), `genomics_england`, `crispr`
  (Project Score), `europepmc` and the held `cancer_biomarkers` are never served; association
  scores are recomputed with them at weight 0; COSMIC hallmarks are never queried.
- Fixed GraphQL documents only; outbound requests are limited to
  `api.platform.opentargets.org` at ~3 req/s. GraphQL errors (HTTP 200/400 + `errors[]`)
  become typed envelope errors naming the parameter; a vanished field is schema drift.
- `data_version` = the Open Targets data release (`meta.dataVersion`) on every payload;
  honest `total`/`truncated`; mechanism text and trial titles fenced as untrusted text.
- HGNC/NCBI gene IDs point to `hgnc_resolve_symbol`, OMIM/DOID disease IDs to
  `mondo_resolve_disease`.
