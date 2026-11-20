You are a translational oncology and cardiometabolic genetics researcher evaluating an MCP
server named "{SERVER}" (research use only). Use ONLY that server's tools: no web search, no
shell, no files, and no other MCP server even if others are available. Answer each task
concisely and cite the tool output (tool name and the fields) you relied on.

TASKS
C1. Resolve "ERBB1". Which target is it, and what is its Ensembl gene ID?
C2. Which drugs acting on EGFR were studied in non-small cell lung carcinoma? How many in total,
    how many of them are at APPROVAL stage for EGFR, and is osimertinib among them (under which
    name)? Use as few calls as you can.
C3. Rank the targets with IntOGen somatic-driver evidence in non-small cell lung carcinoma: top
    5 and the total count. Which served datasources support KRAS there?
C4. Is MYC tractable? Report each modality's true buckets and what the server says about drugs
    acting on MYC. Does the result mean no drug can target MYC?
C5. Germline: what gene-burden evidence links PCSK9 to hypercholesterolaemia? Which disease ID
    was used, how many rows, and is the effect risk-increasing or protective (cite one odds
    ratio)?
C6. Ask for EGFR evidence in lung cancer from cancer_biomarkers, and for KRAS evidence in a
    disease given as "DOID:3908". Report how the server answered each.

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
