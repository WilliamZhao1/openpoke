# Five-community follow-up comparison

The user selected five communities after reviewing the original two-community result. This repeats the same authored queries; it is a diagnostic comparison, not a new holdout. The frozen MiniLM model, worker vectors, graph, relevance labels, final top-five ranking, and original artifacts are unchanged.

| Run / method | Owner recall@5 | Vector recall@5 | Median candidates | Median total comparisons | Warm median / p95 ms |
| --- | ---: | ---: | ---: | ---: | ---: |
| Original / two communities | 0.6111 | 0.6667 | 101 | 121.0 | 76.57 / 79.39 |
| Follow-up / five communities | 0.8889 | 0.9333 | 252 | 272.0 | 187.49 / 195.89 |
| Follow-up / flat vectors | 0.9444 | 1.0000 | 1000 | 1000.0 | 4.70 / 5.27 |
| Follow-up / global ANN | 0.3889 | 0.5111 | unknown | unknown | 6.17 / 7.79 |

Owner recall improves by 27.78 percentage points (61.11% to 88.89%). The five-community result is 5.56 points below flat (94.44%), narrowly missing the original five-point allowance. Median explicit comparisons are 272 (252 workers plus 20 representatives), passing the 500-comparison target. The joint target still fails. Lookup is slower in the follow-up; individual transfer/validation/scoring stages were not profiled.

Mean evaluation candidate-owner coverage, measured before final top-five ranking, rises from 0.6111 to 0.9444. This metric uses live DB membership and original judgments; it is distinct from final owner recall.

| Case | Relevant owners | Two-community owner recall | Five-community owner recall | Five-community misses |
| --- | --- | ---: | ---: | --- |
| cafe-invitation | Alice lunch | 1.00 | 1.00 | none |
| services-owner | Alice Acme contract | 0.00 | 1.00 | none |
| dormant-documents | 2023 tax documents | 1.00 | 1.00 | none |
| expense-owner | Uber receipts | 1.00 | 1.00 | none |
| repository-owner | GitHub review | 1.00 | 1.00 | none |
| renewal-owner | Alice Acme renewal | 1.00 | 1.00 | none |
| amendment-owner | Acme amendment | 0.00 | 1.00 | none |
| two-topics | Alice lunch; Alice Acme contract | 0.00 | 0.50 | Alice Acme contract |
| contract-ambiguity | Alice Acme contract; Alice Acme renewal | 0.50 | 0.50 | Alice Acme renewal |

Five communities recover the original-contract development case, the services-owner case, and the amendment-owner case. The two-topic request now returns Alice lunch but still excludes Alice Acme contract from its candidate pool. The ambiguous Alice contract request includes Alice Acme renewal in its candidate pool, but it remains below the top five; flat search also misses it.

Validation: both numerical checks pass; all 144 timing samples succeed; every non-direct follow-up result selects five communities; candidate counts agree with live Neo4j membership unions; all 16 flat top-five names and scores exactly match the original run. Original report, results, smoke evidence, diagnosis, and snapshot file hashes are unchanged. No model download, rebuild, parameter sweep, further width change, or application integration was performed.

Both no-match cases remain qualitative diagnostics and are excluded from recall. Quality uses nine nonempty-relevance evaluation cases; three repetitions are timing samples, not extra quality examples. Original and follow-up timings are separate small-sample warm runs, not an interleaved paired comparison of widths. Shared query embedding and setup remain excluded from lookup timing.

See [full report](report.md), [raw outputs](results.json), and [comparison/validation details](comparison.json).
