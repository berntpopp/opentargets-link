# opentargets-link v0.1.0 implementation plan

> Historical record — the plan executed on 2026-11-20 for the design in `docs/superpowers/specs/2026-11-20-opentargets-link-design.md`.

1. Clone the fleet scaffold (pgscatalog-link lineage via civic-link: MCP plane, Docker, CI,
   conformance, container release); rename package, env prefix, namespace.
2. Probe the live API; write the fixed documents (`queries.py`) and the datasource allowlist
   (`datasources.py`); record fixtures with exactly those documents.
3. TDD the client error mapping (HTTP 400 variable errors, `Variable '$x'`, schema drift).
4. TDD the service: identifiers (Ensembl/symbol, MONDO/EFO/name; HGNC/NCBI/OMIM/DOID rejected
   with converters), tractability, drug candidates (disease filter over descendants, stage
   order, honest offset paging, `full` reports), disease targets (excluded sources at weight 0,
   allowlist-only scores), evidence (allowlist, client-side drop, two-step without a disease,
   honest cursor truncation).
5. TDD the tool surface (names, docs, budget), capabilities, README/NOTICE/AGENTS.
6. Live integration tests as the schema-drift alarm (weekly `drift.yml`); local conformance
   probes (transport, behaviour, identifiers) against the live API.
7. `make ci-local`, PR, ponytail review, merge, release v0.1.0.
