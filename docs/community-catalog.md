# Community catalog retrieval experiment

This standalone CLI evaluates semantic worker retrieval over a frozen synthetic
catalog. It does not change application discovery, dispatch, Gmail, worker
lifecycle, or the UI. The [experiment README](../evals/community_catalog_poc/README.md)
contains dependencies and build/query/evaluate commands.

## Design and frozen configuration

Each worker profile combines its exact name, purpose[:240], and recent assignment
summary[:240]. Normalized worker embeddings are built once. An exact-name request
uses direct database lookup and bypasses embedding/community scoring. Other queries
score community representatives, choose five communities, fetch their members,
then rank those members by exact cosine similarity and return up to five names.

| Setting | Evaluated checkpoint |
| --- | --- |
| Catalog | `build_catalog(1000)`: seven core owners plus 993 synthetic distractors |
| Model | `sentence-transformers/all-MiniLM-L6-v2`, CPU, normalized 384-dimensional vectors |
| Model revision | `c9745ed1d9f207416be6d2e6f8de32d1f16199bf` |
| Graph | Ten highest positive-scoring neighbors per worker; undirected; seeded Louvain, seed 42, resolution 1 |
| Graph size | 1,000 workers, 20 communities, 7,142 similarity edges |
| Representatives | Centroid plus two diverse members per community; 60 total |
| Member selection | Farthest member from centroid, then member farthest from its closest existing representative; exact-name tie breaks |
| Community score | Maximum query cosine across its three representatives |
| Search width | Five communities; pass `--communities 5` explicitly |
| Representative mode | Pass `--representatives 3` explicitly; CLI default remains one centroid |
| Final ranking | Exact cosine over selected members, exact-name tie breaks, top five |
| Database | Dedicated disposable Neo4j Community 5.26.0; no GDS/APOC |

Selection uses no queries, relevance judgments, or owner-specific exceptions.
Each query counts all 60 routing comparisons and every scored member, including
exemplars scored again. The snapshot-wide calculated bound is 315; the observed
maximum is 314. The derived cache is tied to the snapshot and policy/content
fingerprints. Its separate one-time construction took about 1.12 seconds and
2,000 vector comparisons.

## Evaluation and results

Flat exact vectors, global ANN, and community routing share the frozen catalog,
embedding model, and judgments. Relevant-owner recall and vector-neighbor overlap
are separate measures. No-match requests are diagnostic and excluded from recall
denominators. Timing repeats are not additional quality samples.

| Historical configuration | Observed result | Evidence |
| --- | --- | --- |
| Two communities, one centroid | Evaluation owner recall 61.11% versus flat 94.44%; median 121 comparisons | [Original report](../evals/community_catalog_poc/runs/2026-11-11/evaluation/report.md) |
| Boundary diagnosis | A globally first owner was in the fifth-ranked community; combined-topic contract group ranked eleventh | [Diagnosis](../evals/community_catalog_poc/runs/2026-11-11/diagnosis.json) |
| Five communities, one centroid | Recall 88.89%; median 272 comparisons | [Five-community comparison](../evals/community_catalog_poc/runs/2026-11-11/five-communities/comparison.md) |
| Five communities, three representatives | Matches flat recall on both samples; maximum 314 comparisons | [Current comparison](../evals/community_catalog_poc/runs/2026-11-11/three-representatives/comparison.md) |

The revised [frozen protocol](../evals/community_catalog_poc/runs/2026-11-11/three-representatives/protocol.json)
requires owner recall within three percentage points of the same-model flat
control and strictly fewer than one third of flat's explicit comparisons on every
non-direct query, including routing. Latency is outside this demo gate.

| Sample | Judged evaluation requests | Flat recall@5 | Routed recall@5 | Median comparisons | Maximum |
| --- | ---: | ---: | ---: | ---: | ---: |
| Existing authored evaluation | 9 | 94.44% | 94.44% | 312 | 314 |
| New authored confirmation | 9 | 100% | 100% | 313 | 314 |

The [validation](../evals/community_catalog_poc/runs/2026-11-11/three-representatives/validation.json)
records four numerical checks and 234 timing samples. The [existing report](../evals/community_catalog_poc/runs/2026-11-11/three-representatives/existing/report.md)
and [confirmation report](../evals/community_catalog_poc/runs/2026-11-11/three-representatives/fresh/report.md)
retain their original measurements. No new evaluation was run for this guide.

## Interpretation and deferred integration

The same assistant authored the confirmation queries after inspecting earlier
failures, targeting the same seven owners. This is fresh wording, not an
independent holdout. All seven core owners appear among the 40 selected member
exemplars, against repetitive distractors. The ambiguous `Alice contract` request
still misses a renewal owner also missed by flat. Semantic abstention is absent.

Routed lookup remains about 186 ms versus about 4–5 ms for cached flat search.
The [profile](../evals/community_catalog_poc/runs/2026-11-11/five-communities/lookup-profile.json)
identified member-query/transfer/decoding overhead. Different cache and transfer
boundaries prevent a production latency claim. Fewer explicit comparisons do not
establish lower application cost or faster end-to-end operation.

Application integration, live/dirty-profile refresh, incremental indexing,
automatic widening/fallback, worker merging/aliases, hierarchy, and live-agent
quality remain deferred. Similarity and community membership do not establish
ownership, semantic uniqueness, or approval. A frozen full rebuild is a demo
shortcut, not scalable ingestion. Reconsider integration after representative
quality evidence and matched cache/scoring/transport measurements.

See [LIM-003](known-limitations.md#lim-003), [LIM-004](known-limitations.md#lim-004),
[LIM-006](known-limitations.md#lim-006), [LIM-029](known-limitations.md#lim-029),
and [LIM-030](known-limitations.md#lim-030). The [runtime scope](runtime-scope.md)
distinguishes these experiments from active capabilities.
