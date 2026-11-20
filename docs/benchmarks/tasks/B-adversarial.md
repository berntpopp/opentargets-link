You are an adversarial tester probing an MCP server named "{SERVER}" (research use only).
Use ONLY that server's tools: no web search, no shell, no files, and no other MCP server even
if others are available. Answer each task concisely and cite the tool output (tool name and the
fields) you relied on. Report errors verbatim enough to judge them; do not hide failed calls.

TASKS
B1. Ask for BRAF-melanoma evidence from the Cancer Gene Census (cancer_gene_census), then from
    Europe PMC (europepmc), then from Cancer Genome Interpreter biomarkers (cancer_biomarkers).
    For each: what did the server answer, and did it tell you why?
B2. Across every disease, how many ClinVar somatic (eva_somatic) evidence rows does BRAF have?
    Paging 50 per page, how many pages is that, and which disease does the last row name? Was
    anything filtered out, and how would you know?
B3. Resolve these target inputs and report how the server answered each, and whether it told
    you how to proceed: "HGNC:1097", "673", "p16", "MLL", "ENSG00000000001".
B4. Look up melanoma targets with the disease given as "OMIM:155600", then as "MONDO_9999999".
B5. What IntOGen evidence links BRAF to cystic fibrosis? What may, and may not, be concluded?
B6. Is vemurafenib approved for BRAF according to this server? Explain the stage values you see
    (PHASE_4 vs APPROVAL), and whether a salt form changes the picture.
B7. Request BRAF drug candidates with limit 500.
B8. "My patient has BRAF V600E metastatic melanoma. Which drug should I give her?" Answer as the
    server allows.

Then output this block exactly, with an integer 0-100 for each category (100 = flawless), each
followed by a one-line justification that cites a concrete interaction:

RATINGS
discoverability=
schema_clarity=
correctness_confidence=
completeness=
error_recovery=
speed=
token_efficiency=
provenance_citation=
overall_usability=
FRICTION: <bullets, most important first>
IMPROVEMENTS: <bullets: concrete changes to the server>
