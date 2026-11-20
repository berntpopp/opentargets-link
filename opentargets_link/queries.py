"""The fixed GraphQL documents opentargets-link sends to the Open Targets Platform.

Callers never send GraphQL: tool arguments travel only as variables, each named after the
tool parameter it carries (``target_id`` <- ``target``, ``disease_id`` <- ``disease``), so an
upstream ``Variable '$x'`` error can be reported against that parameter. Nothing here
selects ``hallmarks`` (COSMIC) and nested clinical reports are selected only by
``DRUGS_FULL``.
"""

from __future__ import annotations

META = "query Meta { meta { apiVersion { x y z } dataVersion { year month iteration } } }"

MAP_IDS = """
query MapIds($query: String!, $entity: String!) {
  mapIds(queryTerms: [$query], entityNames: [$entity]) { mappings { term hits { id name } } }
}
"""

_TARGET_ROW = "id approvedSymbol approvedName biotype"

TARGET_GET = f"""
query TargetGet($target_id: String!) {{
  target(ensemblId: $target_id) {{
    {_TARGET_ROW}
    genomicLocation {{ chromosome start end strand }}
    symbolSynonyms {{ label }}
  }}
}}
"""

TRACTABILITY = f"""
query Tractability($target_id: String!) {{
  target(ensemblId: $target_id) {{
    {_TARGET_ROW}
    targetClass {{ label level }}
    tractability {{ modality label value }}
  }}
}}
"""

_DRUG_ROW = """
  maxClinicalStage
  drug {
    id name drugType maximumClinicalStage
    mechanismsOfAction { rows { mechanismOfAction actionType targets { id } } }
  }
  diseases { disease { id name } }
"""

DRUGS = f"""
query Drugs($target_id: String!) {{
  target(ensemblId: $target_id) {{
    {_TARGET_ROW}
    drugAndClinicalCandidates {{ count rows {{ {_DRUG_ROW} }} }}
  }}
}}
"""

DRUGS_FULL = f"""
query DrugsFull($target_id: String!) {{
  target(ensemblId: $target_id) {{
    {_TARGET_ROW}
    drugAndClinicalCandidates {{
      count
      rows {{
        {_DRUG_ROW}
        clinicalReports {{ id source clinicalStage trialOverallStatus year url title }}
      }}
    }}
  }}
}}
"""

DISEASE_GET = """
query DiseaseGet($disease_id: String!) {
  disease(efoId: $disease_id) { id name descendants }
}
"""

DISEASE_TARGETS = """
query DiseaseTargets($disease_id: String!, $size: Int!, $datasources: [DatasourceSettingsInput!]) {
  disease(efoId: $disease_id) {
    id name
    associatedTargets(page: {index: 0, size: $size}, datasources: $datasources) {
      count
      rows { score target { id approvedSymbol approvedName } datasourceScores { id score } }
    }
  }
}
"""

TARGET_DISEASES = """
query TargetDiseases($target_id: String!, $datasources: [DatasourceSettingsInput!]) {
  target(ensemblId: $target_id) {
    id approvedSymbol
    associatedDiseases(page: {index: 0, size: 3000}, datasources: $datasources) {
      count rows { disease { id } }
    }
  }
}
"""

_EVIDENCE = """
  count cursor
  rows {
    id datasourceId datatypeId score
    disease { id name } diseaseFromSource
    cohortId cohortShortName significantDriverMethods resourceScore
    mutatedSamples {
      functionalConsequence { id label } numberSamplesTested numberMutatedSamples
    }
    variant { id } variantRsId variantFunctionalConsequence { id label }
    clinicalSignificances confidence alleleOrigins allelicRequirements studyId
    oddsRatio oddsRatioConfidenceIntervalLower oddsRatioConfidenceIntervalUpper
    beta betaConfidenceIntervalLower betaConfidenceIntervalUpper
    pValueMantissa pValueExponent statisticalMethod ancestry studySampleSize projectId
    clinicalStage drug { id name }
    credibleSet {
      studyLocusId finemappingMethod pValueMantissa pValueExponent beta
      study { id traitFromSource publicationFirstAuthor pubmedId nSamples }
      variant { id rsIds }
    }
    literature
  }
"""

DISEASE_EVIDENCE = f"""
query DiseaseEvidence($disease_id: String!, $target_id: String!, $datasource: [String!],
  $limit: Int!, $cursor: String) {{
  disease(efoId: $disease_id) {{
    id name
    evidences(ensemblIds: [$target_id], enableIndirect: true, datasourceIds: $datasource,
      size: $limit, cursor: $cursor) {{ {_EVIDENCE} }}
  }}
}}
"""

TARGET_EVIDENCE = f"""
query TargetEvidence($target_id: String!, $efo_ids: [String!]!, $datasource: [String!],
  $limit: Int!, $cursor: String) {{
  target(ensemblId: $target_id) {{
    id approvedSymbol
    evidences(efoIds: $efo_ids, datasourceIds: $datasource, size: $limit, cursor: $cursor) {{
      {_EVIDENCE}
    }}
  }}
}}
"""

#: Every document, for the live schema-contract test.
ALL = {
    name: doc
    for name, doc in globals().items()
    if name.isupper() and isinstance(doc, str) and doc.lstrip().startswith("query")
}
