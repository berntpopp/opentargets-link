# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
