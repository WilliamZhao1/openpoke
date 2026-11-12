# Community catalog: minimal proof-of-concept plan

Date: 2026-11-11  
Status: Implemented and evaluated on 2026-11-11; original centroid policy failed, and the subsequent three-representative policy meets the user's revised demo targets on small synthetic samples.  
Goal: Demonstrate that a query can select graph communities and rank a subset of workers, then measure the retrieval tradeoff.

Current user-approved checkpoint, milestone history, and presentation commands: [Community catalog demo progress and runbook](community-catalog-demo-progress.md).

## 1. Smallest useful demo

Build a standalone CLI over a frozen synthetic catalog. Use one local Neo4j instance to store embeddings, similarity edges, and community membership. Run the demo directly rather than wiring it into the Interaction Agent.

**Change budget: zero edits to existing application Python, configuration, dependencies, or UI.** Add a small experiment folder; reuse existing catalog/query fixtures read-only. The completed overload implementation plan remains unchanged.

This is the immediate implementation checklist for the [broader graph proposal](graph-routing-demo-proposal.md). Live indexing, incremental updates, automatic widening/fallback, worker merging, hierarchy, richer summaries, and live-agent/Gmail evaluation are future work. A frozen snapshot and explicit rebuild replace those mechanisms for this PoC.

## 2. Files and dependencies

Add only these hand-maintained experiment files:

| File under `evals/community_catalog_poc/` | Responsibility |
| --- | --- |
| `demo.py` | `build`, `query`, and `evaluate` commands; ordinary functions in one module. |
| `test_demo.py` | Two small numerical routing checks using fixed vectors. |
| `requirements.txt` | Demo-only dependencies: NumPy, NetworkX, Sentence Transformers, and the Neo4j Python driver. Pin versions verified during implementation. |
| `README.md` | Local Neo4j setup, three commands, graph inspection queries, and result interpretation. |

Use an isolated demo environment and a dedicated disposable Neo4j instance. No GDS/APOC plugin, ORM, new API server, or custom frontend. Use Neo4j Browser for graph inspection and CLI output for the query trace. Generated snapshot/cache and result files go to an explicit new output directory, separate from application data; they are not additional hand-maintained fixtures.

## 3. Build once

- [x] Reuse `build_catalog(1000)` from [the existing generator](../server/tests/fixtures/catalogs.py). Read only exact display name, purpose, and recent-assignment summary, with the same 240-character metadata caps as existing experiments. Exclude fixture-only IDs, entities, status, resources, and relevance judgments from retrieval inputs.
- [x] Embed `name + purpose + recent_assignment` with one local model: `sentence-transformers/all-MiniLM-L6-v2`. Normalize vectors and cache them. Record the model revision and catalog fingerprint in a small manifest. A model download is setup work; warm evaluation uses cached data.
- [x] Compute the worker-to-worker cosine matrix once with NumPy. Keep each worker's ten highest positive-scoring neighbors, excluding itself. Make an undirected graph with one edge per pair and retain isolated nodes.
- [x] Use NetworkX's seeded Louvain community detection (`seed=42`, default resolution). This avoids installing a graph analytics plugin. Compute one normalized mean vector per community. Check that every worker belongs to exactly one community and all representatives are valid; fail visibly if the build is invalid.
- [x] Save `PoCWorker {name, profile, embedding}`, `PoCCommunity {id, centroid}`, `SIMILAR_TO {score}`, and `MEMBER_OF` to Neo4j. Index the community ID for membership lookup and create one worker vector index for the global ANN baseline. Wait for that index to become ready.
- [x] Save the snapshot manifest and community sizes. Reuse a cache only when its catalog/model fingerprint matches; otherwise require an explicit full rebuild. Rebuild only the dedicated PoC data.

**Intentional shortcut:** the one-time pairwise build is quadratic. At this fixed 1,000-worker size it keeps the implementation straightforward. Record its time separately; this experiment makes no scalable-ingestion claim. ANN-based graph construction can be a later replacement if needed.

Use a fixed Neo4j version verified during implementation. Similarity graph construction and community detection run in Python; the database holds the resulting graph and participates in actual query-time member retrieval.

## 4. Search with one simple policy

- [x] Load only community IDs/representatives into the query process. Resolve an exact existing worker name directly in Neo4j and return that owner without embedding or community routing.
- [x] Otherwise embed the query once. Score community representatives, select the top **two** communities, and fetch only their members and embeddings from Neo4j.
- [x] Score those members with exact cosine similarity, break ties consistently by exact name, and return up to five workers. Reuse the same ranking rule in the flat-vector control.
- [x] Print selected community IDs, their sizes, unique candidate count, representative/worker comparisons, top-five exact names/scores, and lookup time.
- [x] Accept `--communities 1`, `2`, or another explicit count so the presenter can widen the search manually. Clamp the count to the actual number of communities. Report honestly if the selected groups cover the entire catalog.

There is no learned router, confidence threshold, automatic global fallback, or reranker. A database/cache error stops the command; it does not become an empty-success result. This keeps misses and search effort visible. Top-five names demonstrate retrieval, not production response packing, correct dispatch, or task completion.

## 5. Evaluate three methods on the same snapshot

| Method | Implementation | Purpose |
| --- | --- | --- |
| Flat vectors | Exact NumPy cosine search over all cached worker vectors. | Reference vector neighbors and semantic owner coverage. |
| Global ANN | Neo4j's worker vector index over the same stored embeddings. | Check whether ordinary indexed search is already sufficient. |
| Community routing | Score all community representatives, then exact-score members of the top two groups. | Test the proposed search-space reduction and its recall cost. |

Use [the existing 16-query file](../evals/agent_overload/ranking_queries.json), preserving its development/evaluation split and relevance labels. Reuse the development cases for a smoke check, then freeze settings for the evaluation cases. This is an already-authored synthetic sample, not a new independent holdout. No parameter sweep, new large query suite, or modification of historical ranking results is required.

Encode each query once and share its vector across all three methods. Warm model/cache/DB connections once, then run three timed repetitions per method/query in rotating order. Report warm lookup time including method-specific database fetches and scoring; exclude shared query embedding and setup from that timing. Report query embedding time and build time separately. Do not compare these warm timings directly with earlier fresh-JSON full-lookup measurements.

Save one compact `results.json` and `report.md` containing:

1. **Relevant-owner recall@5:** fraction of judged-relevant names returned, per case and averaged for nonempty relevance cases. Show actual returned names and misses.
2. **Vector-neighbor recall@5:** overlap with flat-vector top five, separately from owner correctness. Apply the same exact-name shortcut to all methods and mark those rows as direct lookups.
3. **Search effort:** selected groups, candidate workers scored, candidate fraction of the 1,000-worker catalog, and representative comparisons. Count total explicit comparisons as representatives plus candidate workers, rather than hiding the routing overhead. Internal ANN vector-comparison counts stay unknown unless actually exposed.
4. **Latency:** warm median and p95 for each method, with three-repetition/small-sample caveats; embedding and build time separately. Repetitions are timing samples, not additional quality examples.

The two no-match cases are qualitative diagnostics: show their returned candidates, but exclude them from recall denominators. This PoC has no semantic abstention policy and must not claim to solve no-match detection. Keep failed rows and mark the run incomplete instead of dropping failures from a successful-looking average.

**Predeclared useful-result targets:** on non-direct evaluation requests, median total explicit comparisons (representatives plus candidate workers) at most 50% of the flat scan's 1,000 comparisons, with mean relevant-owner recall@5 no more than five percentage points below flat vectors. Report candidate fraction and absolute owner recall too; preserving a poor flat baseline is not evidence of good routing. These are demo targets, not production promotion gates. Faster latency is a measured possibility, not a requirement or promised outcome. If targets fail, document the tradeoff and stop rather than expanding the project or tuning against evaluation labels.

## 6. Minimal verification and presentation

Two deterministic checks, without model downloads or a running database:

- [x] With a tiny hand-written vector graph, demonstrate that subset routing can omit a globally relevant neighbor and that increasing the selected community count recovers it. This verifies the central boundary tradeoff rather than model quality.
- [x] With the same numeric fixture, selecting every community reproduces exact flat top-five results, including deterministic ties and unique exact names.

Then run one manual DB smoke check: build, query, and rerun a query from cache. Verify node/membership counts, exact-name lookup, and that printed candidate counts equal the returned membership union. Full backend/Gmail/browser regression suites are unnecessary while application code remains untouched.

Use three presentation beats: an exact name, a topical request showing a genuine subset, and a boundary/ambiguous request rerun with a wider community count. Use existing cases and show their real outcomes, including failures. If none demonstrates a boundary loss, use the numerical test as an explicitly labeled mechanism example rather than scripting a semantic failure. Inspect selected memberships in Neo4j Browser with saved queries; no animated visualization is required.

Implemented command interface:

```powershell
python evals/community_catalog_poc/demo.py build --output <new-snapshot-directory>
python evals/community_catalog_poc/demo.py query --snapshot <snapshot-directory> --query "Alice contract" --communities 2
python evals/community_catalog_poc/demo.py evaluate --snapshot <snapshot-directory> --output <new-result-directory>
```

Stop when these commands, two checks, one DB smoke run, and the small report work. The deliverable demonstrates catalog retrieval only; application integration and production claims require separate work. Existing [LIM-003](known-limitations.md#lim-003), [LIM-004](known-limitations.md#lim-004), [LIM-006](known-limitations.md#lim-006), [LIM-029](known-limitations.md#lim-029), and [LIM-030](known-limitations.md#lim-030) remain open/evidence gaps as currently recorded.

## Implementation outcome — 2026-11-11

The four hand-maintained experiment files are in [evals/community_catalog_poc](../evals/community_catalog_poc/README.md). Application Python, configuration, dependencies, UI, the completed overload plan, and historical comparisons were not changed. The isolated run used Python 3.12.3, Neo4j Community 5.26.0, the pinned local MiniLM model revision, and the four pinned demo dependencies.

- The [build manifest](../evals/community_catalog_poc/runs/2026-11-11/build-manifest.json) records 1,000 workers, 384-dimensional normalized embeddings, 20 communities, and 7,142 similarity edges. The successful build attempt took about 15.21 seconds; earlier setup/download failures are disclosed in the smoke notes and are outside that timing.
- Both [numerical checks](../evals/community_catalog_poc/test_demo.py) passed. The [real DB smoke run](../evals/community_catalog_poc/runs/2026-11-11/smoke.json) passed node/membership/index checks, exact-name bypass, offline model/cache reuse, selected-membership union counts, count clamping, and cache/database failure handling. Docker was unavailable, so a disposable Windows ZIP instance with Java 21 was used.
- The [complete report](../evals/community_catalog_poc/runs/2026-11-11/evaluation/report.md) and [all 144 timing samples](../evals/community_catalog_poc/runs/2026-11-11/evaluation/results.json) preserve the 16 existing authored cases. Nine evaluation cases have nonempty relevance judgments; the two no-match cases remain qualitative diagnostics across the development/evaluation splits.
- Non-direct evaluation routing used a median 101 candidate workers plus 20 representative comparisons (121 total, versus 1,000 flat comparisons). Mean relevant-owner recall@5 was 0.6111 for routing, 0.9444 for flat vectors, and 0.3889 for global ANN. Routing therefore passed the comparison-count target and failed the five-percentage-point recall target. Community vector-neighbor recall@5 was 0.6667.
- Warm evaluation median lookup was about 76.57 ms for routing, 3.95 ms for flat vectors, and 5.54 ms for ANN. Lower comparison count did not imply lower latency in this run. Shared embedding, setup, and build timing stay separate.
- The existing development request `Acme original services redline` demonstrates a real synthetic boundary loss: two selected communities omit `Alice Acme contract`; searching all 20 recovers it. The smoke trace retains both outputs, while the numerical example remains labeled mechanism evidence.

The declared settings remain frozen. The implementation stops here as planned; no evaluation-label tuning, fallback policy, live indexing, application integration, or production promotion was added. The limitations register retains the existing open/evidence-gap states.

## User-requested five-community follow-up — 2026-11-11

After reviewing the original result and diagnosis, the user explicitly requested a repeat with five communities. The evaluator now accepts `--communities 5`; query-time width is recorded separately from the unchanged snapshot manifest's original setting. Model revision, catalog vectors, community graph, judgments, and final top-five ranking remain the same. This is a diagnostic repeat on the existing authored queries, not a new independent holdout. The original report and snapshot hashes are preserved.

The [follow-up comparison](../evals/community_catalog_poc/runs/2026-11-11/five-communities/comparison.md), [full report](../evals/community_catalog_poc/runs/2026-11-11/five-communities/report.md), and [validation details](../evals/community_catalog_poc/runs/2026-11-11/five-communities/comparison.json) record:

- Evaluation owner recall@5 increases from 0.6111 to 0.8889; flat remains 0.9444. The 0.0556 gap narrowly misses the original 0.05 allowance. The joint target still fails, while development owner recall is 1.0 at five groups.
- Evaluation vector-neighbor recall@5 increases from 0.6667 to 0.9333. Median candidates increase from 101 to 252 (25.2% of workers), plus 20 representatives for 272 total explicit comparisons; the comparison-count target passes.
- Warm evaluation median lookup is 187.49 ms for routing and 4.70 ms for flat in the follow-up run. The original two-community median was 76.57 ms in a separately timed run; these are small-sample warm measurements, not an interleaved paired latency comparison.
- Candidate-owner coverage before final ranking, checked against live DB memberships, increases from 0.6111 to 0.9444. The two-topic request still excludes `Alice Acme contract`. The ambiguous contract request includes `Alice Acme renewal` in the candidate pool but omits it from the final five; flat search also omits that owner.
- Both numerical checks pass; all 144 samples succeed; all non-direct follow-up samples select five groups; candidate counts equal DB membership unions; and all 16 flat top-five names/scores exactly match the original. Original report, results, build manifest, smoke, diagnosis, and snapshot file hashes are unchanged.

No embedding model change, graph rebuild, further width search, application integration, or limitation closure followed this authorized repeat.

## Next proposed demo experiment — 2026-11-11

The user proposed a new useful-demo target: owner recall@5 within three percentage points of the same-model flat control, with total explicit comparisons below one third of flat. For the current 1,000-worker snapshot, interpret the comparison bound per non-direct request (including all representative and worker comparisons): at most 333 comparisons. The current flat recall is 0.9444, so the recall floor is 0.9144; the five-community result is 0.8889 at a median 272 comparisons. These new targets do not rewrite the original reports' predeclared five-point/500-comparison gates. Latency remains tracked and is deferred for this demo's next recall experiment, with performance validation still required before production integration.

Recommended next experiment, not yet implemented: retain MiniLM, the existing graph partition, five selected communities, and exact final top-five scoring. Represent each community with its normalized centroid plus two diverse member vectors chosen automatically from the cached embeddings, without relevance labels or owner-specific exceptions. Score each community by its best match among those three representatives. This tests whether distinctive workers hidden by the single mean can affect routing. Multiple representatives have precedent in [CURE's clustering work](https://www.sciencedirect.com/science/article/pii/S0306437901000084), but this proposed routing policy is an unmeasured adaptation, not CURE or an established improvement for this catalog.

The frozen snapshot has 20 communities; its five largest sizes are 52, 51, 51, 51, and 50. Three representatives per community require 60 comparisons; any five-member union contains at most 255 workers. The resulting upper bound is 315 explicit comparisons per non-direct request, including repeated scoring of representatives that are also selected workers. This satisfies the proposed effort budget on this snapshot without hiding routing overhead; recall benefit remains unknown.

The remaining additional miss versus flat is the combined lunch/services query, whose contract-owner community ranks eleventh under the current centroid rule. Simply selecting a sixth centroid-ranked group does not recover that observed owner. The ambiguous contract case also misses a renewal owner in flat search, so matching flat does not require claiming that ambiguity is solved.

Freeze the representative-selection/scoring rule before running it. Use the inspected authored set as regression/diagnostic evidence, and use a small fresh judged set before claiming the new target generalizes. Only nine current evaluation requests have nonempty relevance labels; one half-recall case changes their mean by about 5.56 percentage points. No code change, model migration, new quality examples, prototype selection, or prototype evaluation was performed by this planning discussion.

## Authorized three-representative outcome — 2026-11-11

The user authorized the proposed experiment. [The frozen protocol](../evals/community_catalog_poc/runs/2026-11-11/three-representatives/protocol.json) records the deterministic centroid-plus-two-farthest-member rule and maximum-of-three community score before quality evaluation. MiniLM, worker vectors, the graph partition, five selected communities, exact final ranking, and earlier reports remain unchanged. The CLI supports `--representatives 3` on query/evaluate and a fingerprinted derived cache; no query or relevance judgment enters representative construction.

The [comparison](../evals/community_catalog_poc/runs/2026-11-11/three-representatives/comparison.md) and [validation](../evals/community_catalog_poc/runs/2026-11-11/three-representatives/validation.json) show both revised targets pass:

- Original authored evaluation: routed owner recall@5 is 0.9444, matching flat; vector-neighbor recall@5 is 1.0. Median explicit comparisons are 312, and the maximum across all non-direct samples is 314, including 60 representative scores. The combined lunch/services request recovers both owners. The ambiguous contract case still misses the renewal owner also missed by flat.
- Ten new authored queries were frozen before prototype quality measurement, using the same catalog: nine have relevant-owner judgments and one is a qualitative no-match diagnostic. Routed and flat owner recall@5 are both 1.0, with median 313 and maximum 314 explicit comparisons. These inputs were authored by the same assistant after prior case/diagnosis inspection and target the same seven owners, so they are not independently authored or a production holdout.
- Candidate-owner coverage before final ranking is 1.0 on both evaluation samples. The router returns flat's ordered top-five names on all 26 requests; scores agree within 1e-12, with some floating-point rounding differences.
- Four numerical checks and all 234 timing samples pass. Live checks verify exemplar membership/vectors, deterministic reconstruction, union counts, all 60 routing comparisons, cache reuse/corruption handling, and rejection of a single over-budget sample. Original artifact and snapshot hashes are unchanged.
- The one-time derived representative build takes about 1.12 seconds and 2,000 vector comparisons, recorded outside lookup effort. Per-query latency remains about 186 ms and is outside the current demo gates; no transfer/cache optimization or production speedup claim was added.

Post-run inspection shows all seven core owners appear among the 40 member exemplars, against 993 repetitive synthetic distractors. This favorable fixture property limits generalization. The existing [limitations](known-limitations.md) remain open; passing these synthetic demo gates does not close retrieval, runtime indexing, live-agent quality, or efficiency gaps. No model change or further representative/width sweep followed the frozen experiment.

## References

- [Sentence Transformers model card](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2): the selected local embedding model.
- [NetworkX Louvain](https://networkx.org/documentation/stable/reference/algorithms/generated/networkx.algorithms.community.louvain.louvain_communities.html): community detection and seed parameter.
- [Neo4j vector indexes](https://neo4j.com/docs/cypher-manual/current/indexes/search-indexes/vector-indexes/): embedding properties and global ANN control.
