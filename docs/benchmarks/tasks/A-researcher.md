You are a cancer target-discovery researcher evaluating an MCP server named "{SERVER}"
(research use only). Use ONLY that server's tools: no web search, no shell, no files, and no
other MCP server even if others are available. Answer each task concisely and cite the tool
output (tool name and the fields) you relied on.

QUESTION: Is BRAF a druggable driver in melanoma, and which drugs act on it?

TASKS
A1. Resolve BRAF: its Ensembl gene ID and GRCh38 location.
A2. Is BRAF tractable by small molecule and by antibody? Name the supporting buckets.
A3. Which drugs or clinical candidates act on BRAF and were studied in melanoma (or a more
    specific melanoma)? How many are there? Give vemurafenib's and dabrafenib's clinical stage
    for BRAF, and say whether that stage is the same thing as regulatory approval.
A4. Which disease ID did you use for melanoma? How many IntOGen somatic-driver evidence rows
    link BRAF to melanoma and its descendants? Page to the end and list every cohort.
A5. Which targets with IntOGen evidence rank highest for melanoma (top 5), and how many such
    targets are there in total?
A6. Germline side: what gene-burden evidence links CDKN2A to melanoma? How many rows, and for
    one row give cohort, odds ratio with 95% CI, p-value and sample size. Does the server also
    hold GWAS credible-set evidence for that pair, and what does one such row tell you?
A7. Which data release did your answers come from, under what licence terms (including the drug
    data), and how should the source be cited?

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
