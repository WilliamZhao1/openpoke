# Frozen community catalog PoC

Run status: **complete**.

Authored synthetic retrieval judgments at 1,000 workers; no live agent, dispatch, Gmail, or production quality evidence.
Run settings: ten positive neighbors, Louvain seed 42 / resolution 1, top 5 communities, up to 3 representatives per community, top five workers.
Query evidence scope: repeat_on_existing_authored_queries_not_independent_holdout. Authored synthetic metadata-retrieval judgments; not independent real-world labels. No tuning against evaluation results.
Cases retain their authored splits. No tuning or parameter sweep within this run. Exact-name rows bypass embedding and routing.

| Split | Method | Owner recall@5 | Vector recall@5 | Quality cases | Failed samples | Median / p95 ms | Median explicit comparisons (non-direct) | Median candidate fraction (non-direct) |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| development | flat | 1.0000 | 1.0000 | 5 | 0 | 4.8653 / 6.2614 | 1000.0000 | 1.0000 |
| development | ann | 0.8000 | 0.7200 | 5 | 0 | 7.4714 / 12.0170 | unknown | unknown |
| development | community | 1.0000 | 1.0000 | 5 | 0 | 188.2574 / 198.5773 | 312.0000 | 0.2520 |
| evaluation | flat | 0.9444 | 1.0000 | 9 | 0 | 4.5285 / 6.2994 | 1000.0000 | 1.0000 |
| evaluation | ann | 0.3889 | 0.5111 | 9 | 0 | 6.6385 / 7.8787 | unknown | unknown |
| evaluation | community | 0.9444 | 1.0000 | 9 | 0 | 186.0436 / 192.1013 | 312.0000 | 0.2520 |

Original-plan targets (retained for comparison):

```json
{
  "measurable": true,
  "median_comparisons_at_most_500": true,
  "owner_recall_within_5_percentage_points": true,
  "both_targets_met": true,
  "scope": "non-direct evaluation effort; nonempty relevant-owner cases; demo targets only"
}
```

Current user-requested demo targets (three percentage points / fewer than one third of comparisons per request):

```json
{
  "measurable": true,
  "maximum_absolute_recall_gap": 0.03,
  "comparison_fraction_exclusive": 0.3333333333333333,
  "scope": "mean evaluation owner recall; every non-direct sample including routing overhead; no latency gate",
  "flat_owner_recall_at_5": 0.9444444444444444,
  "community_owner_recall_at_5": 0.9444444444444444,
  "absolute_recall_gap": 0.0,
  "recall_within_3_percentage_points": true,
  "max_explicit_comparisons": 314,
  "max_comparison_fraction": 0.314,
  "every_non_direct_sample_below_one_third": true,
  "both_targets_met": true
}
```

Each case has three timed repetitions in rotating method order, not three quality examples. Quality uses the first repetition; all outputs and any variation are retained in results.json. Recall excludes both no-match cases. Failed samples remain recorded; affected quality aggregates and targets are unavailable. Any timing from an incomplete run is partial.
Warm lookup includes the common exact-name DB probe and method-specific fetches/scoring, and excludes shared embedding and setup. Median/p95 use only three samples per case and a small authored sample overall. ANN internal comparisons and candidate fraction are unknown. Neo4j ANN scores are converted from [0,1] to cosine; tie ordering is deterministic within its approximate returned set.

Embedding and offline build times (ms; first build can include model download):

```json
{
  "embedding_ms": {
    "exact-lunch": 0.0,
    "original-contract": 9.00179985910654,
    "old-taxes": 7.09470035508275,
    "atlas-review": 7.337199989706278,
    "new-garden": 7.228599861264229,
    "acme-ambiguity": 10.181500110775232,
    "cafe-invitation": 9.354399982839823,
    "services-owner": 8.357400074601173,
    "dormant-documents": 8.169400040060282,
    "expense-owner": 8.643500041216612,
    "repository-owner": 7.411700207740068,
    "renewal-owner": 8.301699999719858,
    "amendment-owner": 7.275599986314774,
    "new-science": 7.042699959129095,
    "two-topics": 8.356399834156036,
    "contract-ambiguity": 7.680700160562992
  },
  "build_ms": {
    "model_setup_ms": 7816.501799970865,
    "catalog_embedding_ms": 2816.0234997048974,
    "pairwise_graph_ms": 512.7488998696208,
    "louvain_centroids_ms": 71.36770011857152,
    "database_write_index_validation_ms": 3372.4497999064624,
    "total_build_ms": 15211.561900097877
  },
  "evaluation_setup_ms": 10638.423800002784,
  "representative_setup": {
    "policy": "centroid_plus_two_farthest_v1",
    "maximum_per_community": 3,
    "total_representatives": 60,
    "cache_reused": false,
    "cache_sha256": "cb3b016c555260d0fa19c49e0fe20db755a0c050e49b51a4822f56da8185ee7e",
    "cache_fingerprint": "22e6db8c3fc5ea0f47ea428f44901f379b13f7887a22a912cb4a3c1a12b801f8",
    "build_ms": 1123.9967001602054,
    "build_explicit_comparisons": 2000,
    "load_or_build_ms": 1189.9921000003815
  }
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
| original-contract / development | community | False | community-007 (51), community-001 (52), community-013 (50), community-018 (49), community-015 (50) | 252 / 60 / 312 | 1.0000 / 1.0000 | Alice Acme contract; Alice Acme renewal; Acme amendment; Alice Chen renewal project 00124; Morgan renewal project 00109 | — |
| old-taxes / development | flat | False | — | 1000 / 0 / 1000 | 1.0000 / 1.0000 | 2023 tax documents; Morgan receipts project 00117; Morgan receipts project 00137; Morgan review project 00253; Morgan review project 00433 | — |
| old-taxes / development | ann | False | — | None / 0 / None | 1.0000 / 1.0000 | 2023 tax documents; Morgan receipts project 00117; Morgan receipts project 00137; Morgan review project 00253; Morgan review project 00433 | — |
| old-taxes / development | community | False | community-000 (51), community-014 (49), community-013 (50), community-011 (50), community-012 (50) | 250 / 60 / 310 | 1.0000 / 1.0000 | 2023 tax documents; Morgan receipts project 00117; Morgan receipts project 00137; Morgan review project 00253; Morgan review project 00433 | — |
| atlas-review / development | flat | False | — | 1000 / 0 / 1000 | 1.0000 / 1.0000 | GitHub review; Alice Acme contract; Acme amendment; Alice Chen receipts project 00172; Alice Chen review project 00508 | — |
| atlas-review / development | ann | False | — | None / 0 / None | 1.0000 / 0.6000 | GitHub review; Alice Acme contract; Acme amendment; Alice Acme renewal; Alice Chen review project 00168 | — |
| atlas-review / development | community | False | community-010 (51), community-007 (51), community-001 (52), community-009 (50), community-004 (50) | 254 / 60 / 314 | 1.0000 / 1.0000 | GitHub review; Alice Acme contract; Acme amendment; Alice Chen receipts project 00172; Alice Chen review project 00508 | — |
| new-garden / development | flat | False | — | 1000 / 0 / 1000 | unknown / unknown | Sam Patel renewal project 00014; Sam Patel renewal project 00094; Sam Patel renewal project 00514; Sam Patel renewal project 00074; Sam Patel renewal project 00434 | — |
| new-garden / development | ann | False | — | None / 0 / None | unknown / unknown | Sam Patel renewal project 00014; Sam Patel renewal project 00094; Sam Patel renewal project 00914; Sam Patel renewal project 00814; Sam Patel renewal project 00074 | — |
| new-garden / development | community | False | community-018 (49), community-015 (50), community-001 (52), community-019 (49), community-013 (50) | 250 / 60 / 310 | unknown / unknown | Sam Patel renewal project 00014; Sam Patel renewal project 00094; Sam Patel renewal project 00514; Sam Patel renewal project 00074; Sam Patel renewal project 00434 | — |
| acme-ambiguity / development | flat | False | — | 1000 / 0 / 1000 | 1.0000 / 1.0000 | Alice Acme contract; Alice Acme renewal; Acme amendment; Alice lunch; Alice Chen review project 00648 | — |
| acme-ambiguity / development | ann | False | — | None / 0 / None | 0.0000 / 0.2000 | Alice Chen review project 00648; Alice Chen review project 00148; Alice Chen review project 00368; Alice Chen review project 00568; Alice Chen renewal project 00364 | Acme amendment; Alice Acme contract; Alice Acme renewal |
| acme-ambiguity / development | community | False | community-007 (51), community-001 (52), community-008 (50), community-010 (51), community-009 (50) | 254 / 60 / 314 | 1.0000 / 1.0000 | Alice Acme contract; Alice Acme renewal; Acme amendment; Alice lunch; Alice Chen review project 00648 | — |
| cafe-invitation / evaluation | flat | False | — | 1000 / 0 / 1000 | 1.0000 / 1.0000 | Alice lunch; Morgan lunch project 00121; Morgan lunch project 00521; Morgan lunch project 00501; Morgan lunch project 00181 | — |
| cafe-invitation / evaluation | ann | False | — | None / 0 / None | 1.0000 / 0.8000 | Alice lunch; Morgan lunch project 00501; Morgan lunch project 00121; Morgan lunch project 00881; Morgan lunch project 00181 | — |
| cafe-invitation / evaluation | community | False | community-008 (50), community-012 (50), community-003 (50), community-016 (50), community-007 (51) | 251 / 60 / 311 | 1.0000 / 1.0000 | Alice lunch; Morgan lunch project 00121; Morgan lunch project 00521; Morgan lunch project 00501; Morgan lunch project 00181 | — |
| services-owner / evaluation | flat | False | — | 1000 / 0 / 1000 | 1.0000 / 1.0000 | Alice Acme contract; Alice Acme renewal; Acme amendment; Sam Patel renewal project 00714; Sam Patel renewal project 00814 | — |
| services-owner / evaluation | ann | False | — | None / 0 / None | 0.0000 / 0.0000 | Morgan renewal project 00209; Morgan renewal project 00709; Morgan renewal project 00869; Morgan renewal project 00909; Morgan renewal project 00329 | Alice Acme contract |
| services-owner / evaluation | community | False | community-007 (51), community-001 (52), community-013 (50), community-018 (49), community-015 (50) | 252 / 60 / 312 | 1.0000 / 1.0000 | Alice Acme contract; Alice Acme renewal; Acme amendment; Sam Patel renewal project 00714; Sam Patel renewal project 00814 | — |
| dormant-documents / evaluation | flat | False | — | 1000 / 0 / 1000 | 1.0000 / 1.0000 | 2023 tax documents; Morgan receipts project 00117; Morgan receipts project 00137; Morgan receipts project 00197; Morgan receipts project 00177 | — |
| dormant-documents / evaluation | ann | False | — | None / 0 / None | 1.0000 / 1.0000 | 2023 tax documents; Morgan receipts project 00117; Morgan receipts project 00137; Morgan receipts project 00197; Morgan receipts project 00177 | — |
| dormant-documents / evaluation | community | False | community-000 (51), community-013 (50), community-014 (49), community-011 (50), community-012 (50) | 250 / 60 / 310 | 1.0000 / 1.0000 | 2023 tax documents; Morgan receipts project 00117; Morgan receipts project 00137; Morgan receipts project 00197; Morgan receipts project 00177 | — |
| expense-owner / evaluation | flat | False | — | 1000 / 0 / 1000 | 1.0000 / 1.0000 | Uber receipts; Alice Acme contract; Sam Patel receipts project 00202; Alice Chen receipts project 00252; Morgan receipts project 00337 | — |
| expense-owner / evaluation | ann | False | — | None / 0 / None | 0.0000 / 0.6000 | Sam Patel receipts project 00202; Alice Chen receipts project 00252; Morgan receipts project 00337; Alice Chen receipts project 00332; Alex Kim receipts project 00207 | Uber receipts |
| expense-owner / evaluation | community | False | community-000 (51), community-007 (51), community-004 (50), community-009 (50), community-017 (50) | 252 / 60 / 312 | 1.0000 / 1.0000 | Uber receipts; Alice Acme contract; Sam Patel receipts project 00202; Alice Chen receipts project 00252; Morgan receipts project 00337 | — |
| repository-owner / evaluation | flat | False | — | 1000 / 0 / 1000 | 1.0000 / 1.0000 | GitHub review; Alice Chen contract project 00160; Alice Chen receipts project 00152; Alice Chen receipts project 00172; Alice Chen receipts project 00112 | — |
| repository-owner / evaluation | ann | False | — | None / 0 / None | 0.0000 / 0.2000 | Alice Chen contract project 00160; Alice Chen contract project 00120; Alice Chen contract project 00380; Alice Chen contract project 00140; Alice Chen review project 00388 | GitHub review |
| repository-owner / evaluation | community | False | community-010 (51), community-009 (50), community-001 (52), community-007 (51), community-004 (50) | 254 / 60 / 314 | 1.0000 / 1.0000 | GitHub review; Alice Chen contract project 00160; Alice Chen receipts project 00152; Alice Chen receipts project 00172; Alice Chen receipts project 00112 | — |
| renewal-owner / evaluation | flat | False | — | 1000 / 0 / 1000 | 1.0000 / 1.0000 | Alice Acme renewal; Alice Chen renewal project 00864; Alice Chen renewal project 00304; Alice Chen renewal project 00464; Alice Chen renewal project 00504 | — |
| renewal-owner / evaluation | ann | False | — | None / 0 / None | 1.0000 / 0.8000 | Alice Acme renewal; Alice Chen renewal project 00464; Alice Chen renewal project 00864; Alice Chen renewal project 00304; Alice Chen renewal project 00324 | — |
| renewal-owner / evaluation | community | False | community-001 (52), community-007 (51), community-013 (50), community-018 (49), community-009 (50) | 252 / 60 / 312 | 1.0000 / 1.0000 | Alice Acme renewal; Alice Chen renewal project 00864; Alice Chen renewal project 00304; Alice Chen renewal project 00464; Alice Chen renewal project 00504 | — |
| amendment-owner / evaluation | flat | False | — | 1000 / 0 / 1000 | 1.0000 / 1.0000 | Acme amendment; Alice Acme contract; Alice Acme renewal; GitHub review; Sam Patel contract project 00130 | — |
| amendment-owner / evaluation | ann | False | — | None / 0 / None | 0.0000 / 0.2000 | Sam Patel contract project 00170; Sam Patel contract project 00130; Sam Patel contract project 00770; Sam Patel contract project 00150; Sam Patel contract project 00270 | Acme amendment |
| amendment-owner / evaluation | community | False | community-001 (52), community-007 (51), community-010 (51), community-015 (50), community-011 (50) | 254 / 60 / 314 | 1.0000 / 1.0000 | Acme amendment; Alice Acme contract; Alice Acme renewal; GitHub review; Sam Patel contract project 00130 | — |
| new-science / evaluation | flat | False | — | 1000 / 0 / 1000 | unknown / unknown | Alice Chen review project 00448; Alice Chen review project 00468; Alice Chen review project 00568; Alice Chen review project 00108; Alice Chen review project 00508 | — |
| new-science / evaluation | ann | False | — | None / 0 / None | unknown / unknown | Alice Chen review project 00448; Alice Chen review project 00568; Alice Chen review project 00468; Alice Chen review project 00108; Alice Chen review project 00508 | — |
| new-science / evaluation | community | False | community-010 (51), community-009 (50), community-001 (52), community-006 (50), community-004 (50) | 253 / 60 / 313 | unknown / unknown | Alice Chen review project 00448; Alice Chen review project 00468; Alice Chen review project 00568; Alice Chen review project 00108; Alice Chen review project 00508 | — |
| two-topics / evaluation | flat | False | — | 1000 / 0 / 1000 | 1.0000 / 1.0000 | Alice lunch; Alice Acme contract; Alice Acme renewal; Morgan lunch project 00701; Morgan lunch project 00361 | — |
| two-topics / evaluation | ann | False | — | None / 0 / None | 0.0000 / 0.2000 | Morgan lunch project 00361; Morgan lunch project 00521; Morgan lunch project 00201; Morgan lunch project 00121; Morgan lunch project 00461 | Alice Acme contract; Alice lunch |
| two-topics / evaluation | community | False | community-008 (50), community-007 (51), community-001 (52), community-012 (50), community-013 (50) | 253 / 60 / 313 | 1.0000 / 1.0000 | Alice lunch; Alice Acme contract; Alice Acme renewal; Morgan lunch project 00701; Morgan lunch project 00361 | — |
| contract-ambiguity / evaluation | flat | False | — | 1000 / 0 / 1000 | 0.5000 / 1.0000 | Alice Acme contract; Alice Chen contract project 00400; Alice Chen contract project 00120; Alice Chen contract project 00620; Alice Chen contract project 00180 | Alice Acme renewal |
| contract-ambiguity / evaluation | ann | False | — | None / 0 / None | 0.5000 / 0.8000 | Alice Acme contract; Alice Chen contract project 00400; Alice Chen contract project 00120; Alice Chen contract project 00180; Alice Chen contract project 00200 | Alice Acme renewal |
| contract-ambiguity / evaluation | community | False | community-007 (51), community-001 (52), community-009 (50), community-008 (50), community-002 (49) | 252 / 60 / 312 | 0.5000 / 1.0000 | Alice Acme contract; Alice Chen contract project 00400; Alice Chen contract project 00120; Alice Chen contract project 00620; Alice Chen contract project 00180 | Alice Acme renewal |

No-match rows are qualitative diagnostics: this experiment always retrieves candidates and has no semantic abstention policy. Subset routing can exclude relevant owners; widen manually. Searching every community performs representatives plus the full worker scan. The quadratic frozen build, cached warm timings, and synthetic sample establish neither scalable ingestion nor lower application cost/latency. Do not compare these timings directly with historical fresh-JSON lookup measurements. A poor flat baseline remains poor even when routing preserves its recall.
