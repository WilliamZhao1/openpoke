# Frozen community catalog PoC

Run status: **complete**.

Authored synthetic retrieval judgments at 1,000 workers; no live agent, dispatch, Gmail, or production quality evidence.
Run settings: ten positive neighbors, Louvain seed 42 / resolution 1, top 5 communities, up to 3 representatives per community, top five workers.
Query evidence scope: freshly_authored_confirmation_after_prior_inspection_not_independent_holdout. Ten newly authored synthetic queries frozen before the three-representative quality run. Author knew prior cases and diagnosis; not independently authored, blind, or real-world labels.
Cases retain their authored splits. No tuning or parameter sweep within this run. Exact-name rows bypass embedding and routing.

| Split | Method | Owner recall@5 | Vector recall@5 | Quality cases | Failed samples | Median / p95 ms | Median explicit comparisons (non-direct) | Median candidate fraction (non-direct) |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| development | flat | unknown | unknown | 0 | 0 | unknown / unknown | unknown | unknown |
| development | ann | unknown | unknown | 0 | 0 | unknown / unknown | unknown | unknown |
| development | community | unknown | unknown | 0 | 0 | unknown / unknown | unknown | unknown |
| evaluation | flat | 1.0000 | 1.0000 | 9 | 0 | 4.2537 / 5.0730 | 1000.0000 | 1.0000 |
| evaluation | ann | 0.7778 | 0.7333 | 9 | 0 | 5.6498 / 6.7001 | unknown | unknown |
| evaluation | community | 1.0000 | 1.0000 | 9 | 0 | 186.2185 / 197.6029 | 313.0000 | 0.2530 |

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
  "flat_owner_recall_at_5": 1.0,
  "community_owner_recall_at_5": 1.0,
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
    "fresh-cafe-guest": 10.565800126641989,
    "fresh-original-redline": 9.066599886864424,
    "fresh-tax-archive": 11.27300038933754,
    "fresh-trip-costs": 9.809399954974651,
    "fresh-auth-code": 9.920299984514713,
    "fresh-nextyear-negotiation": 9.621300268918276,
    "fresh-signed-change": 10.07660012692213,
    "fresh-meal-and-agreement": 11.318199802190065,
    "fresh-expenses-and-code": 10.065999813377857,
    "fresh-no-match": 8.682299870997667
  },
  "build_ms": {
    "model_setup_ms": 7816.501799970865,
    "catalog_embedding_ms": 2816.0234997048974,
    "pairwise_graph_ms": 512.7488998696208,
    "louvain_centroids_ms": 71.36770011857152,
    "database_write_index_validation_ms": 3372.4497999064624,
    "total_build_ms": 15211.561900097877
  },
  "evaluation_setup_ms": 7058.073100168258,
  "representative_setup": {
    "policy": "centroid_plus_two_farthest_v1",
    "maximum_per_community": 3,
    "total_representatives": 60,
    "cache_reused": true,
    "cache_sha256": "cb3b016c555260d0fa19c49e0fe20db755a0c050e49b51a4822f56da8185ee7e",
    "cache_fingerprint": "22e6db8c3fc5ea0f47ea428f44901f379b13f7887a22a912cb4a3c1a12b801f8",
    "build_ms": 1123.9967001602054,
    "build_explicit_comparisons": 2000,
    "load_or_build_ms": 31.94190002977848
  }
}
```

Per-case first-repetition results (exact names; misses are judged owners):

| Case / split | Method | Direct | Selected groups (size) | Candidates / representatives / total comparisons | Owner / vector recall@5 | Top names | Misses / failure |
| --- | --- | --- | --- | --- | --- | --- | --- |
| fresh-cafe-guest / evaluation | flat | False | — | 1000 / 0 / 1000 | 1.0000 / 1.0000 | Alice lunch; Alice Chen lunch project 00256; Alice Chen lunch project 00176; Alice Chen lunch project 00136; Alice Chen lunch project 00216 | — |
| fresh-cafe-guest / evaluation | ann | False | — | None / 0 / None | 1.0000 / 1.0000 | Alice lunch; Alice Chen lunch project 00256; Alice Chen lunch project 00176; Alice Chen lunch project 00136; Alice Chen lunch project 00216 | — |
| fresh-cafe-guest / evaluation | community | False | community-008 (50), community-010 (51), community-007 (51), community-009 (50), community-001 (52) | 254 / 60 / 314 | 1.0000 / 1.0000 | Alice lunch; Alice Chen lunch project 00256; Alice Chen lunch project 00176; Alice Chen lunch project 00136; Alice Chen lunch project 00216 | — |
| fresh-original-redline / evaluation | flat | False | — | 1000 / 0 / 1000 | 1.0000 / 1.0000 | Alice Acme contract; Alice Acme renewal; Acme amendment; Alice Chen receipts project 00132; Alice Chen receipts project 00152 | — |
| fresh-original-redline / evaluation | ann | False | — | None / 0 / None | 1.0000 / 0.6000 | Alice Acme contract; Alice Acme renewal; Acme amendment; Alice Chen contract project 00120; Alice lunch | — |
| fresh-original-redline / evaluation | community | False | community-007 (51), community-001 (52), community-009 (50), community-008 (50), community-010 (51) | 254 / 60 / 314 | 1.0000 / 1.0000 | Alice Acme contract; Alice Acme renewal; Acme amendment; Alice Chen receipts project 00132; Alice Chen receipts project 00152 | — |
| fresh-tax-archive / evaluation | flat | False | — | 1000 / 0 / 1000 | 1.0000 / 1.0000 | 2023 tax documents; Morgan receipts project 00137; Morgan receipts project 00117; Morgan receipts project 00197; Morgan receipts project 00437 | — |
| fresh-tax-archive / evaluation | ann | False | — | None / 0 / None | 1.0000 / 0.8000 | 2023 tax documents; Morgan receipts project 00137; Morgan receipts project 00117; Morgan receipts project 00197; Morgan receipts project 00497 | — |
| fresh-tax-archive / evaluation | community | False | community-000 (51), community-013 (50), community-014 (49), community-011 (50), community-009 (50) | 250 / 60 / 310 | 1.0000 / 1.0000 | 2023 tax documents; Morgan receipts project 00137; Morgan receipts project 00117; Morgan receipts project 00197; Morgan receipts project 00437 | — |
| fresh-trip-costs / evaluation | flat | False | — | 1000 / 0 / 1000 | 1.0000 / 1.0000 | Uber receipts; Morgan receipts project 00257; Morgan receipts project 00317; Alice Chen receipts project 00112; Morgan receipts project 00137 | — |
| fresh-trip-costs / evaluation | ann | False | — | None / 0 / None | 0.0000 / 0.6000 | Morgan receipts project 00257; Morgan receipts project 00317; Morgan receipts project 00397; Morgan receipts project 00137; Morgan receipts project 00337 | Uber receipts |
| fresh-trip-costs / evaluation | community | False | community-000 (51), community-017 (50), community-009 (50), community-004 (50), community-007 (51) | 252 / 60 / 312 | 1.0000 / 1.0000 | Uber receipts; Morgan receipts project 00257; Morgan receipts project 00317; Alice Chen receipts project 00112; Morgan receipts project 00137 | — |
| fresh-auth-code / evaluation | flat | False | — | 1000 / 0 / 1000 | 1.0000 / 1.0000 | GitHub review; Alice Chen receipts project 00152; Alice Chen receipts project 00172; Alice Acme contract; Alice Chen receipts project 00192 | — |
| fresh-auth-code / evaluation | ann | False | — | None / 0 / None | 0.0000 / 0.0000 | Alice Chen renewal project 00164; Alice Chen renewal project 00744; Alice Chen renewal project 00124; Alice Chen renewal project 00724; Alice Chen renewal project 00624 | GitHub review |
| fresh-auth-code / evaluation | community | False | community-010 (51), community-007 (51), community-009 (50), community-001 (52), community-014 (49) | 253 / 60 / 313 | 1.0000 / 1.0000 | GitHub review; Alice Chen receipts project 00152; Alice Chen receipts project 00172; Alice Acme contract; Alice Chen receipts project 00192 | — |
| fresh-nextyear-negotiation / evaluation | flat | False | — | 1000 / 0 / 1000 | 1.0000 / 1.0000 | Alice Acme renewal; Alice Acme contract; Acme amendment; Alice Chen renewal project 00244; Alice Chen renewal project 00824 | — |
| fresh-nextyear-negotiation / evaluation | ann | False | — | None / 0 / None | 1.0000 / 0.8000 | Alice Acme renewal; Alice Acme contract; Acme amendment; Alice Chen renewal project 00244; Alice Chen renewal project 00204 | — |
| fresh-nextyear-negotiation / evaluation | community | False | community-001 (52), community-007 (51), community-008 (50), community-009 (50), community-013 (50) | 253 / 60 / 313 | 1.0000 / 1.0000 | Alice Acme renewal; Alice Acme contract; Acme amendment; Alice Chen renewal project 00244; Alice Chen renewal project 00824 | — |
| fresh-signed-change / evaluation | flat | False | — | 1000 / 0 / 1000 | 1.0000 / 1.0000 | Acme amendment; Alice Acme contract; Alice Acme renewal; Alice Chen contract project 00120; Alice Chen contract project 00180 | — |
| fresh-signed-change / evaluation | ann | False | — | None / 0 / None | 1.0000 / 1.0000 | Acme amendment; Alice Acme contract; Alice Acme renewal; Alice Chen contract project 00120; Alice Chen contract project 00180 | — |
| fresh-signed-change / evaluation | community | False | community-001 (52), community-007 (51), community-009 (50), community-015 (50), community-010 (51) | 254 / 60 / 314 | 1.0000 / 1.0000 | Acme amendment; Alice Acme contract; Alice Acme renewal; Alice Chen contract project 00120; Alice Chen contract project 00180 | — |
| fresh-meal-and-agreement / evaluation | flat | False | — | 1000 / 0 / 1000 | 1.0000 / 1.0000 | Alice lunch; Alice Acme contract; Morgan lunch project 00121; Morgan lunch project 00501; Morgan lunch project 00821 | — |
| fresh-meal-and-agreement / evaluation | ann | False | — | None / 0 / None | 1.0000 / 0.8000 | Alice lunch; Alice Acme contract; Morgan lunch project 00121; Morgan lunch project 00821; Alice Acme renewal | — |
| fresh-meal-and-agreement / evaluation | community | False | community-008 (50), community-007 (51), community-001 (52), community-012 (50), community-016 (50) | 253 / 60 / 313 | 1.0000 / 1.0000 | Alice lunch; Alice Acme contract; Morgan lunch project 00121; Morgan lunch project 00501; Morgan lunch project 00821 | — |
| fresh-expenses-and-code / evaluation | flat | False | — | 1000 / 0 / 1000 | 1.0000 / 1.0000 | Uber receipts; GitHub review; Alice Chen receipts project 00112; Alex Kim receipts project 00127; Alice Chen receipts project 00172 | — |
| fresh-expenses-and-code / evaluation | ann | False | — | None / 0 / None | 1.0000 / 1.0000 | Uber receipts; GitHub review; Alice Chen receipts project 00112; Alex Kim receipts project 00127; Alice Chen receipts project 00172 | — |
| fresh-expenses-and-code / evaluation | community | False | community-000 (51), community-010 (51), community-004 (50), community-009 (50), community-017 (50) | 252 / 60 / 312 | 1.0000 / 1.0000 | Uber receipts; GitHub review; Alice Chen receipts project 00112; Alex Kim receipts project 00127; Alice Chen receipts project 00172 | — |
| fresh-no-match / evaluation | flat | False | — | 1000 / 0 / 1000 | unknown / unknown | Alex Kim renewal project 00139; Alice Chen renewal project 00124; Alex Kim renewal project 00159; Alex Kim renewal project 00119; Alice Chen renewal project 00024 | — |
| fresh-no-match / evaluation | ann | False | — | None / 0 / None | unknown / unknown | Alex Kim renewal project 00139; Alice Chen renewal project 00124; Alice Chen renewal project 00024; Alex Kim renewal project 00159; Alex Kim renewal project 00119 | — |
| fresh-no-match / evaluation | community | False | community-005 (49), community-001 (52), community-018 (49), community-013 (50), community-004 (50) | 250 / 60 / 310 | unknown / unknown | Alex Kim renewal project 00139; Alice Chen renewal project 00124; Alex Kim renewal project 00159; Alex Kim renewal project 00119; Alice Chen renewal project 00024 | — |

No-match rows are qualitative diagnostics: this experiment always retrieves candidates and has no semantic abstention policy. Subset routing can exclude relevant owners; widen manually. Searching every community performs representatives plus the full worker scan. The quadratic frozen build, cached warm timings, and synthetic sample establish neither scalable ingestion nor lower application cost/latency. Do not compare these timings directly with historical fresh-JSON lookup measurements. A poor flat baseline remains poor even when routing preserves its recall.
