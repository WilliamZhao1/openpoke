# Three-representative routing experiment

Both user-requested demo targets pass on the original sample and the new authored confirmation sample. The MiniLM model, worker vectors, graph partition, five selected communities, and final ranking rule are unchanged. The sole routing change is scoring each community by the best of its centroid and two diverse member exemplars.

| Sample / policy | Judged evaluation requests | Flat owner recall@5 | Routed owner recall@5 | Vector-neighbor recall@5 | Median / maximum explicit comparisons | Demo targets |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Original / one centroid, five groups | 9 | 0.9444 | 0.8889 | 0.9333 | 272 / 274 | recall fails |
| Original / three representatives, five groups | 9 | 0.9444 | 0.9444 | 1.0000 | 312 / 314 | pass |
| New authored / three representatives, five groups | 9 | 1.0000 | 1.0000 | 1.0000 | 313 / 314 | pass |

The new gates are absolute owner-recall difference at most 0.03 and fewer than 1,000/3 comparisons on every non-direct request, including all representative scores. Both observed recall gaps are zero. The maximum is 314 comparisons (31.4% of flat), versus the snapshot-wide calculated upper bound of 315. Mean candidate-owner coverage before final ranking is 1.0 on both evaluation samples.

## Fixed selection rule

Each group retains its normalized centroid. Pick the member with lowest similarity to that centroid. Pick the second distinct member with lowest similarity to its closest existing representative (centroid or first exemplar). Exact-name tie breaks make this deterministic. Score a query against all representatives and use the maximum per group, then exact-score members of the top five groups. Queries, judgments, fixture IDs/status/resources, and owner-specific exceptions never enter exemplar selection.

All 20 communities have three representatives, for 60 query comparisons. Members already scored as representatives are scored again and counted again in the final member pass. The derived cache uses the original snapshot ID and its own content fingerprint; it adds no embeddings or graph mutations. One offline setup pass took about 1.12 seconds and 2,000 vector comparisons, recorded separately from per-query effort. Cache reuse was verified on the fresh run and a CLI query.

## Outcomes and remaining bounds

The original combined Cafe Etoile / Acme services request now retrieves both owners. The ambiguous Alice contract request still returns only one of its two judged owners, exactly as flat search does. Matching the control does not establish perfect ownership decisions or task completion.

The original set has 16 authored requests, nine judged evaluation requests, two diagnostic no-match requests across its splits, and 144 timing samples. The ten newly authored requests were frozen before the prototype quality run: nine have relevant-owner judgments and one is a qualitative no-match diagnostic. They add 90 timing samples. The same assistant authored them after inspecting prior failures, and they target the same seven core owners in the same frozen catalog; they are not an independent holdout or production evaluation.

Post-run inspection shows all seven core workers appear among the 40 label-free member exemplars, against 993 repetitive synthetic distractors. This explains a favorable property of this fixture, not representative real-world coverage. No choices were changed after either quality run.

Latency remains outside the demo gate. Warm evaluation median lookup remains about 186 ms for the routed method versus roughly 4–5 ms for the cached flat control. The previously profiled DB-transfer/materialization issue was not optimized. No production speedup claim follows from comparison counts.

## Verification

Four deterministic numerical checks pass. All 234 timing samples succeed. Every routed non-direct sample selects five communities and counts all 60 representatives; candidate counts agree with live DB member unions. Every selected exemplar belongs to its group and matches the stored vector; reversing member input order reproduces selections exactly. The original-sample flat control reproduces its saved names/scores exactly. The router reproduces flat ordered top-five names for all 26 requests, with scores agreeing within 1e-12 (some differ at floating-point rounding precision). No-match outputs remain diagnostic. The original cache/report/snapshot hashes are unchanged. A corrupt derived cache fails visibly; exact-name lookup bypasses it and model loading. A single 334-comparison sample fails the per-request gate even when the median remains lower.

## Reproduce

```powershell
python evals/community_catalog_poc/demo.py evaluate --snapshot <snapshot-directory> --communities 5 --representatives 3 --output <new-result-directory>
python evals/community_catalog_poc/demo.py evaluate --snapshot <snapshot-directory> --communities 5 --representatives 3 --queries evals/community_catalog_poc/runs/2026-11-11/three-representatives/fresh-queries.json --output <another-new-directory>
```

The dedicated Neo4j instance must be running and POC_NEO4J_PASSWORD set; query uses the same --communities 5 --representatives 3 options. No model download, graph rebuild, or application change is required.

Evidence: [frozen protocol](protocol.json), [original-sample report](existing/report.md), [new-authored-sample report](fresh/report.md), [representatives](existing/representatives.json), [validation](validation.json), and the two raw results.json files beside their reports. Earlier [single-centroid results](../five-communities/comparison.md) remain intact.
