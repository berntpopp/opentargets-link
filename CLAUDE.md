# CLAUDE.md

**Read [AGENTS.md](AGENTS.md) first** — it is the authoritative contributor and agent guide.

Essentials:

- Read-only MCP server over the Open Targets Platform GraphQL API: tractability, drug candidates,
  disease-target associations, evidence. Live calls only; no data snapshot.
- Fixed GraphQL documents only (`opentargets_link/queries.py`); callers never send GraphQL.
- Evidence datasources are an ALLOWLIST (`opentargets_link/datasources.py`); never add
  `cancer_gene_census`/`europepmc`/`cancer_biomarkers` or query `hallmarks`.
- Data plane returns plain dicts and raises typed errors; `run_mcp_tool` owns the envelope.
- Open Targets errors arrive as HTTP 200/400 + `errors[]`; the last evidence page still has a cursor.
- Every upstream call goes through the process-wide `RateLimiter` — respect it in live tests.
- FastMCP 4.x is post-training-cutoff: verify symbols against this repo's own `.venv`.
- Gate: `make ci-local` (serialize it on shared machines). Never `gh release create`.
