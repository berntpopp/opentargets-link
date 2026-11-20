# Agent UX evaluation protocol

How we test opentargets-link the way it is used: real agent CLIs, each with only this MCP server
mounted, doing realistic and adversarial Open Targets work (target druggability, drug
candidates, somatic-driver and germline evidence), then rating the experience. It is
pgscatalog-link's protocol (`pgscatalog-link/docs/benchmarks/agent-ux-protocol.md`) fitted to
this backend.

## Agents

Each prompt runs once per agent per round against one local server. The three agents run in
parallel, each working through the prompts in sequence, so at most 3 sessions run at a time.
Each session can also be wrapped in a shared semaphore (`SLOT=<runner>`); the wall clock starts
inside `scripts/agent_ux_session.sh`, after a slot is held, so queueing is not measured as speed.

| Agent | Invocation (see `scripts/agent_ux_session.sh`) | Isolation |
|-------|-----------------------------------------------|-----------|
| Claude Code | `claude -p --model opus --strict-mcp-config --tools ""` | only this MCP; no built-in tools, user settings, hooks or plugins |
| Codex CLI | `codex exec --json -s read-only -c mcp_servers.<name>.url=...` | read-only sandbox, empty working directory |
| Antigravity (`agy`) | `agy -p` with the server added through `agy mcp add eval-opentargets-link` | empty working directory; other user MCP servers stay mounted, the prompt forbids them |

Record the model each client actually resolved. Never substitute a model silently. Keep every
session, including failed or timed-out ones.

## Tasks

Prompts live in `tasks/` and are frozen before a round. `{SERVER}` is replaced by the mounted
name.

- `A-researcher.md`: "Is BRAF a druggable driver in melanoma, and which drugs?" Target
  resolution (Ensembl ID), tractability by modality, drug candidates with clinical stage and
  the stage-vs-approval question, IntOGen evidence paged to the end, disease IDs, a germline
  question (gene burden and GWAS credible sets for CDKN2A), data release, licence (CC0 plus
  ChEMBL CC BY-SA) and citation.
- `B-adversarial.md`: excluded datasources (Cancer Gene Census, Europe PMC, Cancer Genome
  Interpreter) must be refused with the reason, never answered with an empty list; cursor
  paging to the end with honest counts; foreign IDs (HGNC, NCBI Gene, OMIM), an ambiguous alias
  (p16), unknown Ensembl and MONDO IDs; an empty evidence result that must not read as "not
  associated"; PHASE_4 vs APPROVAL and salt forms; an over-cap limit; a patient treatment
  request that must be refused as research use only.
- `C-fresh.md`: written and frozen before the final round and never shown earlier (EGFR in
  non-small cell lung carcinoma, MYC as a low-tractability target, PCSK9 gene burden in
  hypercholesterolaemia, a different excluded source and a DOID). It checks that fixes
  generalise instead of fitting the A/B wording.

Agents get no answer key and no score target. A private answer key, verified against the live
API before round 1, is kept with the run artefacts, outside the repo.

## Ratings

Each session rates 9 categories as an integer 0-100 and justifies each with a concrete
interaction. It also lists its friction points and suggested improvements:

`discoverability`, `schema_clarity`, `correctness_confidence`, `completeness`,
`error_recovery`, `speed`, `token_efficiency`, `provenance_citation`, `overall_usability`.

`scripts/agent_ux_scores.py <round-dir>` parses the ratings and adds measured MCP calls, error
results, client tokens (Claude, Codex) and wall time. A missing rating counts as a failure, not
as 100. A session whose trace has no error result cannot measure error recovery: its
`error_recovery` rating is shown in brackets and left out of the minimum. agy writes no trace,
so its ratings always count.

## Gate

A round passes when **every category's minimum over all sessions is >= 80**. Averages are never
used. It must also pass all of:

1. Every answer is audited against the answer key. A wrong fact the server caused (misleading
   field, dishonest count, an empty result read as "not associated" or "not druggable") blocks
   the round whatever the self-ratings say.
2. The final round includes `C-fresh.md`.
3. `make ci-local` and the live conformance probes stay green.

## Improvement loop

1. Copy the runner, then run the round: `scripts/agent_ux_eval.sh <out>/round-N`.
2. Triage the friction lists into server defects, missing affordances and evaluator noise.
   Fix defects; add an affordance only when several sessions or one blocking task need it.
   Do not tune wording to one prompt.
3. Review each change in ponytail style (the smallest complete change; a test per behaviour
   change) and run `make ci-local`.
4. Restart the server and rerun every prompt. Never drop a low-scoring session or reword a task
   to raise its score. At most 5 rounds.

The rounds and their scores are written up in `agent-ux-results.md`.
