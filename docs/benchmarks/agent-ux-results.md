# Agent UX evaluation results (2026-11-20)

Five rounds against opentargets-link: v0.1.0 in round 1, then the fixes listed below
(released as v0.1.1). The live contract is `get_server_capabilities` and the README.

Method: [`agent-ux-protocol.md`](agent-ux-protocol.md). Agents: Claude Code 2.1.329
(`claude-opus-5-5`), Codex CLI 0.164.0 (its configured default model) and Antigravity `agy`
1.5.13 (its configured default model; `agy -p` does not print it). Prompts: A (researcher)
and B (adversarial) in every round. C (fresh) was frozen before round 1, was never shown to
an agent before round 3, and ran in rounds 3-5. Raw traces are machine-local and are not
committed.

**Codex ran only in round 1.** In round 2 its account hit a usage limit (until 21:18 CET).
One session failed mid-task and one stalled; both are kept in the round-2 table as unrated.
Rounds 3-5 ran Claude and agy only (`AGENTS="claude agy"`). That limit is on the agent's
account, not on this server.

## Minimum rating per category (0-100, over all sessions of the round)

| Round | sessions | discov | schema | correct | complete | error | speed | tokens | provenance | overall |
|------:|------:|------:|------:|------:|------:|------:|------:|------:|------:|------:|
| 1 (v0.1.0) | 6 (A, B x 3 agents) | 70 | 78 | 75 | 62 | 68 | 92 | 60 | 88 | 74 |
| 2 | 4 rated + 2 Codex failed | 85 | 82 | 85 | 70 | 72 | 86 | 70 | 88 | 80 |
| 3 (+C) | 6 (A, B, C x Claude, agy) | 85 | 82 | 80 | 65 | 72 | 86 | 70 | 88 | 80 |
| 4 | 6 | 88 | 85 | 85 | 72 | 82 | 84 | 70 | 88 | 84 |
| 5 | 6 | 82 | 85 | 80 | 72 | 78 | 86 | 65 | 88 | 82 |

**Gate not reached (>= 80 in every category) after the 5-round maximum.** Three categories
miss, and every miss comes from a Claude session. In round 5 agy's lowest rating was 78, for tokens on B; every
other agy rating was 82 or higher.

- **Completeness 72 (Claude B, rounds 4-5).** Claude names the licence exclusions in its
  rating: Cancer Gene Census (COSMIC), Europe PMC and Cancer Genome Interpreter biomarkers. It
  also wants variant-level (V600E) filtering and MEK-inhibitor partners for a BRAF query. The
  exclusions are an owner decision, and the server discloses them with the reason. Open
  Targets evidence has no variant filter. Partner drugs act on other targets. This is outside
  what the server can fix.
- **Error recovery 78 (Claude C, round 5).** A DOID ID (`DOID:3908`) is answered with
  `mondo_resolve_disease`, a tool on a sibling GeneFoundry server. Open Targets cannot map
  DOID or OMIM itself (`mapIds` and `search` both return nothing, checked live). Behind the
  router that hint is a working call. Standalone, the hint says to pass the disease name.
- **Tokens 65 (Claude A, round 5).** Claude asked for a 45-row gene-burden page and found it
  large. Many rows are separate Open Targets evidence records for the same study, one under
  the parent disease and one under a descendant. The server reports them honestly and does
  not merge them. Compact rows now round float noise and drop derivable fields: the page went
  from 29.5 KB to 25.7 KB. That change landed before round 5. Claude A rated tokens 70 in
  rounds 2-4 and 65 in round 5.

Speed was never the problem. Calls take 0-1.4 s (`elapsed_ms`); cached repeats take 0 ms.

## Answer audit

Every answer was checked against the private answer key, which was verified against the live
API before round 1. **No wrong fact caused by the server in any round.**

- Round 1: agents read vemurafenib's PHASE_4 next to its salt competitors' APPROVAL as "not
  approved" or as a contradiction. None of them stated it wrongly as fact. This was the main
  ambiguity, and it was fixed (see below).
- Rounds 1-5: every session refused the patient-treatment request (B8). Every session read
  the empty BRAF/cystic fibrosis result as "no evidence here", never as "not associated".
- Round 3 C: Claude doubted rociletinib's APPROVAL stage. That stage is upstream ChEMBL/Open
  Targets data, not a server error.

## What changed because of the agents (v0.1.1)

- **Stage semantics** (6/6 sessions in round 1). Open Targets ranks WITHDRAWAL > PHASE_4 >
  APPROVAL when it picks a drug's stage for a target. We checked this on every EGFR drug.
  - PHASE_4 and WITHDRAWAL now share the top tier with APPROVAL.
  - Rows carry `approved` and a salt-to-parent link (`parent_drug_id`).
  - `stage_note`, `stage_counts`, `approved_total` and `parent_drugs_total` explain and
    count without paging.
  - Gefitinib (WITHDRAWAL) had sorted to the last page. Our answer-key check caught it.
- **GWAS credible sets** had only a score. The detail lives under `credibleSet` upstream;
  rows now carry the study, PMID, lead variant, p-value, beta and fine-mapping method.
- **Excluded datasources** got a bare "must be one of". The error now names the licence
  reason.
- **Dead-end recovery.**
  - HGNC IDs resolve through Open Targets `mapIds`.
  - Sibling-server hints say they are GeneFoundry tools and give the standalone fallback.
  - Unknown Ensembl and MONDO IDs no longer point to a resolver that cannot map them.
  - British spellings are retried in US form.
- **Silent wrong page.** A malformed cursor returned page one. It is now `invalid_input`; a
  live test guards the cursor format.
- **IntOGen ranking.** `datasource=` now ranks by that datasource's score (`ranked_by`).
- **Smaller fixes:**
  - one `p_value` float
  - minimal rows keep the variant
  - compact rows are rounded
  - `get_diagnostics` counts argument rejections
  - HP IDs are documented
  - `response_mode` says what each mode returns

## Declined, with reason

- **A local DOID/OMIM/NCBI crosswalk.** Open Targets cannot map these forms, so we would need
  a second data source. That is the job of the `mondo` and `hgnc` siblings behind the router.
- **Deduplicating parent and descendant evidence rows.** They are distinct upstream evidence
  records. Merging them would make `total` disagree with Open Targets.
- **Variant filter, drug-name filter, collapsing salts into parents.** Open Targets has no
  variant filter on evidence. Drug name and salt grouping are answered by `parent_drugs_total`
  and `stage_counts` without a new parameter (Tool-Surface Budget).
- **Raising the drug `limit` above 20 for non-full modes.** Full mode needs the cap, because
  it fences 4 texts per row under the 128-fence ceiling. A mode-dependent cap would make the
  schema more permissive than the runtime.
- **Serving excluded datasources.** These are owner-decided licence exclusions.
