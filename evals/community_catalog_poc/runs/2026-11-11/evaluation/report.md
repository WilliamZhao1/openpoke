# Frozen community catalog PoC

Run status: **complete**.

Authored synthetic retrieval judgments at 1,000 workers; no live agent, dispatch, Gmail, or production quality evidence.
Settings were fixed before evaluation: ten positive neighbors, Louvain seed 42 / resolution 1, top two communities, top five workers.
Development cases run first as a smoke check; no tuning or parameter sweep. Exact-name rows bypass embedding and routing.

| Split | Method | Owner recall@5 | Vector recall@5 | Quality cases | Failed samples | Median / p95 ms | Median explicit comparisons (non-direct) | Median candidate fraction (non-direct) |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| development | flat | 1.0000 | 1.0000 | 5 | 0 | 4.2261 / 5.1311 | 1000.0000 | 1.0000 |
| development | ann | 0.8000 | 0.7200 | 5 | 0 | 6.8180 / 10.2881 | unknown | unknown |
| development | community | 0.7333 | 0.8000 | 5 | 0 | 77.6977 / 84.7210 | 121.0000 | 0.1010 |
| evaluation | flat | 0.9444 | 1.0000 | 9 | 0 | 3.9546 / 4.4863 | 1000.0000 | 1.0000 |
| evaluation | ann | 0.3889 | 0.5111 | 9 | 0 | 5.5365 / 6.7498 | unknown | unknown |
| evaluation | community | 0.6111 | 0.6667 | 9 | 0 | 76.5702 / 79.3949 | 121.0000 | 0.1010 |

Predeclared targets:

```json
{
  "measurable": true,
  "median_comparisons_at_most_500": true,
  "owner_recall_within_5_percentage_points": false,
  "both_targets_met": false,
  "scope": "non-direct evaluation effort; nonempty relevant-owner cases; demo targets only"
}
```

Each case has three timed repetitions in rotating method order, not three quality examples. Quality uses the first repetition; all outputs and any variation are retained in results.json. Recall excludes both no-match cases. Failed samples remain recorded; affected quality aggregates and targets are unavailable. Any timing from an incomplete run is partial.
Warm lookup includes the common exact-name DB probe and method-specific fetches/scoring, and excludes shared embedding and setup. Median/p95 use only three samples per case and a small authored sample overall. ANN internal comparisons and candidate fraction are unknown. Neo4j ANN scores are converted from [0,1] to cosine; tie ordering is deterministic within its approximate returned set.

Embedding and offline build times (ms; first build can include model download):

```json
{
  "embedding_ms": {
    "exact-lunch": 0.0,
    "original-contract": 7.843699771910906,
    "old-taxes": 7.243500091135502,
    "atlas-review": 7.284800056368113,
    "new-garden": 6.593599915504456,
    "acme-ambiguity": 9.096499998122454,
    "cafe-invitation": 9.321399964392185,
    "services-owner": 7.15220021083951,
    "dormant-documents": 6.994399707764387,
    "expense-owner": 7.69019965082407,
    "repository-owner": 8.502299897372723,
    "renewal-owner": 7.129199802875519,
    "amendment-owner": 7.462400011718273,
    "new-science": 7.11630005389452,
    "two-topics": 7.554899901151657,
    "contract-ambiguity": 9.121499955654144
  },
  "build_ms": {
    "model_setup_ms": 7816.501799970865,
    "catalog_embedding_ms": 2816.0234997048974,
    "pairwise_graph_ms": 512.7488998696208,
    "louvain_centroids_ms": 71.36770011857152,
    "database_write_index_validation_ms": 3372.4497999064624,
    "total_build_ms": 15211.561900097877
  },
  "evaluation_setup_ms": 7027.806099969894
}
```

Per-case first-repetition results (exact names; misses are judged owners):

| Case / split | Method | Direct | Selected groups (size) | Candidates / representatives / total comparisons | Owner / vector recall@5 | Top names | Misses / failure |
| --- | --- | --- | --- | --- | --- | --- | --- |
| exact-lunch / development | flat | True | — | 1 / 0 / 0 | 1.0000 / 1.0000 | Alice lunch | — |
| exact-lunch / development | ann | True | — | 1 / 0 / 0 | 1.0000 / 1.0000 | Alice lunch | — |
| exact-lunch / development | community | True | — | 1 / 0 / 0 | 1.0000 / 1.0000 | Alice lunch | — |
| original-contract / development | flat | False | — | 1000 / 0 / 1000 | 1.0000 / 1.0000 | Alice Acme contract; Alice Acme renewal; Acme amendment; Alice Chen renewal project 00124; Morgan renewal project 00109 | — |
| original-contract / development | ann | False | — | None / 0 / None | 1.0000 / 0.8000 | Alice Acme contract; Alice Acme renewal; Acme amendment; Alice Chen renewal project 00124; Sam Patel renewal project 00114 | — |
| original-contract / development | community | False | community-001 (52), community-013 (50) | 102 / 20 / 122 | 0.0000 / 0.8000 | Alice Acme renewal; Acme amendment; Alice Chen renewal project 00124; Morgan renewal project 00109; Morgan renewal project 00149 | Alice Acme contract |
| old-taxes / development | flat | False | — | 1000 / 0 / 1000 | 1.0000 / 1.0000 | 2023 tax documents; Morgan receipts project 00117; Morgan receipts project 00137; Morgan review project 00253; Morgan review project 00433 | — |
| old-taxes / development | ann | False | — | None / 0 / None | 1.0000 / 1.0000 | 2023 tax documents; Morgan receipts project 00117; Morgan receipts project 00137; Morgan review project 00253; Morgan review project 00433 | — |
| old-taxes / development | community | False | community-000 (51), community-014 (49) | 100 / 20 / 120 | 1.0000 / 1.0000 | 2023 tax documents; Morgan receipts project 00117; Morgan receipts project 00137; Morgan review project 00253; Morgan review project 00433 | — |
| atlas-review / development | flat | False | — | 1000 / 0 / 1000 | 1.0000 / 1.0000 | GitHub review; Alice Acme contract; Acme amendment; Alice Chen receipts project 00172; Alice Chen review project 00508 | — |
| atlas-review / development | ann | False | — | None / 0 / None | 1.0000 / 0.6000 | GitHub review; Alice Acme contract; Acme amendment; Alice Acme renewal; Alice Chen review project 00168 | — |
| atlas-review / development | community | False | community-010 (51), community-009 (50) | 101 / 20 / 121 | 1.0000 / 0.6000 | GitHub review; Alice Chen receipts project 00172; Alice Chen review project 00508; Alice Chen receipts project 00112; Alice Chen receipts project 00152 | — |
| new-garden / development | flat | False | — | 1000 / 0 / 1000 | unknown / unknown | Sam Patel renewal project 00014; Sam Patel renewal project 00094; Sam Patel renewal project 00514; Sam Patel renewal project 00074; Sam Patel renewal project 00434 | — |
| new-garden / development | ann | False | — | None / 0 / None | unknown / unknown | Sam Patel renewal project 00014; Sam Patel renewal project 00094; Sam Patel renewal project 00914; Sam Patel renewal project 00814; Sam Patel renewal project 00074 | — |
| new-garden / development | community | False | community-018 (49), community-001 (52) | 101 / 20 / 121 | unknown / unknown | Sam Patel renewal project 00014; Sam Patel renewal project 00094; Sam Patel renewal project 00514; Sam Patel renewal project 00074; Sam Patel renewal project 00434 | — |
| acme-ambiguity / development | flat | False | — | 1000 / 0 / 1000 | 1.0000 / 1.0000 | Alice Acme contract; Alice Acme renewal; Acme amendment; Alice lunch; Alice Chen review project 00648 | — |
| acme-ambiguity / development | ann | False | — | None / 0 / None | 0.0000 / 0.2000 | Alice Chen review project 00648; Alice Chen review project 00148; Alice Chen review project 00368; Alice Chen review project 00568; Alice Chen renewal project 00364 | Acme amendment; Alice Acme contract; Alice Acme renewal |
| acme-ambiguity / development | community | False | community-001 (52), community-010 (51) | 103 / 20 / 123 | 0.6667 / 0.6000 | Alice Acme renewal; Acme amendment; Alice Chen review project 00648; Alice Chen review project 00368; Alice Chen review project 00148 | Alice Acme contract |
| cafe-invitation / evaluation | flat | False | — | 1000 / 0 / 1000 | 1.0000 / 1.0000 | Alice lunch; Morgan lunch project 00121; Morgan lunch project 00521; Morgan lunch project 00501; Morgan lunch project 00181 | — |
| cafe-invitation / evaluation | ann | False | — | None / 0 / None | 1.0000 / 0.8000 | Alice lunch; Morgan lunch project 00501; Morgan lunch project 00121; Morgan lunch project 00881; Morgan lunch project 00181 | — |
| cafe-invitation / evaluation | community | False | community-012 (50), community-008 (50) | 100 / 20 / 120 | 1.0000 / 1.0000 | Alice lunch; Morgan lunch project 00121; Morgan lunch project 00521; Morgan lunch project 00501; Morgan lunch project 00181 | — |
| services-owner / evaluation | flat | False | — | 1000 / 0 / 1000 | 1.0000 / 1.0000 | Alice Acme contract; Alice Acme renewal; Acme amendment; Sam Patel renewal project 00714; Sam Patel renewal project 00814 | — |
| services-owner / evaluation | ann | False | — | None / 0 / None | 0.0000 / 0.0000 | Morgan renewal project 00209; Morgan renewal project 00709; Morgan renewal project 00869; Morgan renewal project 00909; Morgan renewal project 00329 | Alice Acme contract |
| services-owner / evaluation | community | False | community-001 (52), community-013 (50) | 102 / 20 / 122 | 0.0000 / 0.4000 | Alice Acme renewal; Acme amendment; Morgan renewal project 00209; Morgan renewal project 00709; Morgan renewal project 00869 | Alice Acme contract |
| dormant-documents / evaluation | flat | False | — | 1000 / 0 / 1000 | 1.0000 / 1.0000 | 2023 tax documents; Morgan receipts project 00117; Morgan receipts project 00137; Morgan receipts project 00197; Morgan receipts project 00177 | — |
| dormant-documents / evaluation | ann | False | — | None / 0 / None | 1.0000 / 1.0000 | 2023 tax documents; Morgan receipts project 00117; Morgan receipts project 00137; Morgan receipts project 00197; Morgan receipts project 00177 | — |
| dormant-documents / evaluation | community | False | community-000 (51), community-013 (50) | 101 / 20 / 121 | 1.0000 / 1.0000 | 2023 tax documents; Morgan receipts project 00117; Morgan receipts project 00137; Morgan receipts project 00197; Morgan receipts project 00177 | — |
| expense-owner / evaluation | flat | False | — | 1000 / 0 / 1000 | 1.0000 / 1.0000 | Uber receipts; Alice Acme contract; Sam Patel receipts project 00202; Alice Chen receipts project 00252; Morgan receipts project 00337 | — |
| expense-owner / evaluation | ann | False | — | None / 0 / None | 0.0000 / 0.6000 | Sam Patel receipts project 00202; Alice Chen receipts project 00252; Morgan receipts project 00337; Alice Chen receipts project 00332; Alex Kim receipts project 00207 | Uber receipts |
| expense-owner / evaluation | community | False | community-000 (51), community-009 (50) | 101 / 20 / 121 | 1.0000 / 0.6000 | Uber receipts; Alice Chen receipts project 00252; Morgan receipts project 00337; Morgan receipts project 00837; Alice Chen receipts project 00852 | — |
| repository-owner / evaluation | flat | False | — | 1000 / 0 / 1000 | 1.0000 / 1.0000 | GitHub review; Alice Chen contract project 00160; Alice Chen receipts project 00152; Alice Chen receipts project 00172; Alice Chen receipts project 00112 | — |
| repository-owner / evaluation | ann | False | — | None / 0 / None | 0.0000 / 0.2000 | Alice Chen contract project 00160; Alice Chen contract project 00120; Alice Chen contract project 00380; Alice Chen contract project 00140; Alice Chen review project 00388 | GitHub review |
| repository-owner / evaluation | community | False | community-010 (51), community-007 (51) | 102 / 20 / 122 | 1.0000 / 0.4000 | GitHub review; Alice Chen contract project 00160; Alice Chen contract project 00120; Alice Chen contract project 00380; Alice Chen contract project 00700 | — |
| renewal-owner / evaluation | flat | False | — | 1000 / 0 / 1000 | 1.0000 / 1.0000 | Alice Acme renewal; Alice Chen renewal project 00864; Alice Chen renewal project 00304; Alice Chen renewal project 00464; Alice Chen renewal project 00504 | — |
| renewal-owner / evaluation | ann | False | — | None / 0 / None | 1.0000 / 0.8000 | Alice Acme renewal; Alice Chen renewal project 00464; Alice Chen renewal project 00864; Alice Chen renewal project 00304; Alice Chen renewal project 00324 | — |
| renewal-owner / evaluation | community | False | community-001 (52), community-013 (50) | 102 / 20 / 122 | 1.0000 / 1.0000 | Alice Acme renewal; Alice Chen renewal project 00864; Alice Chen renewal project 00304; Alice Chen renewal project 00464; Alice Chen renewal project 00504 | — |
| amendment-owner / evaluation | flat | False | — | 1000 / 0 / 1000 | 1.0000 / 1.0000 | Acme amendment; Alice Acme contract; Alice Acme renewal; GitHub review; Sam Patel contract project 00130 | — |
| amendment-owner / evaluation | ann | False | — | None / 0 / None | 0.0000 / 0.2000 | Sam Patel contract project 00170; Sam Patel contract project 00130; Sam Patel contract project 00770; Sam Patel contract project 00150; Sam Patel contract project 00270 | Acme amendment |
| amendment-owner / evaluation | community | False | community-015 (50), community-011 (50) | 100 / 20 / 120 | 0.0000 / 0.2000 | Sam Patel contract project 00130; Sam Patel contract project 00170; Sam Patel contract project 00870; Sam Patel contract project 00830; Sam Patel contract project 00270 | Acme amendment |
| new-science / evaluation | flat | False | — | 1000 / 0 / 1000 | unknown / unknown | Alice Chen review project 00448; Alice Chen review project 00468; Alice Chen review project 00568; Alice Chen review project 00108; Alice Chen review project 00508 | — |
| new-science / evaluation | ann | False | — | None / 0 / None | unknown / unknown | Alice Chen review project 00448; Alice Chen review project 00568; Alice Chen review project 00468; Alice Chen review project 00108; Alice Chen review project 00508 | — |
| new-science / evaluation | community | False | community-010 (51), community-009 (50) | 101 / 20 / 121 | unknown / unknown | Alice Chen review project 00448; Alice Chen review project 00468; Alice Chen review project 00568; Alice Chen review project 00108; Alice Chen review project 00508 | — |
| two-topics / evaluation | flat | False | — | 1000 / 0 / 1000 | 1.0000 / 1.0000 | Alice lunch; Alice Acme contract; Alice Acme renewal; Morgan lunch project 00701; Morgan lunch project 00361 | — |
| two-topics / evaluation | ann | False | — | None / 0 / None | 0.0000 / 0.2000 | Morgan lunch project 00361; Morgan lunch project 00521; Morgan lunch project 00201; Morgan lunch project 00121; Morgan lunch project 00461 | Alice Acme contract; Alice lunch |
| two-topics / evaluation | community | False | community-012 (50), community-013 (50) | 100 / 20 / 120 | 0.0000 / 0.4000 | Morgan lunch project 00701; Morgan lunch project 00361; Morgan lunch project 00501; Morgan lunch project 00521; Morgan lunch project 00121 | Alice Acme contract; Alice lunch |
| contract-ambiguity / evaluation | flat | False | — | 1000 / 0 / 1000 | 0.5000 / 1.0000 | Alice Acme contract; Alice Chen contract project 00400; Alice Chen contract project 00120; Alice Chen contract project 00620; Alice Chen contract project 00180 | Alice Acme renewal |
| contract-ambiguity / evaluation | ann | False | — | None / 0 / None | 0.5000 / 0.8000 | Alice Acme contract; Alice Chen contract project 00400; Alice Chen contract project 00120; Alice Chen contract project 00180; Alice Chen contract project 00200 | Alice Acme renewal |
| contract-ambiguity / evaluation | community | False | community-007 (51), community-009 (50) | 101 / 20 / 121 | 0.5000 / 1.0000 | Alice Acme contract; Alice Chen contract project 00400; Alice Chen contract project 00120; Alice Chen contract project 00620; Alice Chen contract project 00180 | Alice Acme renewal |

No-match rows are qualitative diagnostics: this experiment always retrieves candidates and has no semantic abstention policy. Subset routing can exclude relevant owners; widen manually. Searching every community performs representatives plus the full worker scan. The quadratic frozen build, cached warm timings, and synthetic sample establish neither scalable ingestion nor lower application cost/latency. Do not compare these timings directly with historical fresh-JSON lookup measurements. A poor flat baseline remains poor even when routing preserves its recall.
