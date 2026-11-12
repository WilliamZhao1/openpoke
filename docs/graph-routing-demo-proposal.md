# Proposal: community-routed semantic worker discovery

Date: 2026-11-11  
Status: Revised design recommendation for discussion; not implemented or evaluated.  
Scope: A bounded post-baseline catalog-search experiment. This note does not replace the completed reduced-scope implementation plan or authorize deferred storage, identity migration, or worker merging.

**Immediate scope, simplified after the user's clarification:** follow the [minimal PoC implementation and evaluation plan](community-catalog-poc-plan.md). It uses a frozen 1,000-worker catalog, a standalone CLI, a full offline rebuild, Python Louvain, and manual community widening, with zero application-code changes. The broader indexing/update/integration ideas below are future design options, not requirements for this demo.

## 1. Clarified purpose

Organize similar worker profiles into communities, select promising communities for a request, and rank their members. The intended benefit is less backend catalog-search work while preserving relevant-owner coverage. The graph can also expose related workers and possible duplicate work for later inspection.

The previous version proposed a temporal graph of work, resources, and dependencies. That answers a different question and remains a separate possible extension. The user's clarified target is a routing index over the worker catalog.

This is a coarse-to-fine retrieval design, not a claim of a new research algorithm. Its demonstrable distinction would be visible community routing, measured search effort, boundary recovery, and catalog maintenance. Compare it with ordinary indexed vector search before claiming an efficiency advantage.

## 2. Present cost and embedding cost

- Current `find_workers()` reads the JSON snapshot and builds/ranks all name/purpose/recent-assignment documents. There is no persistent index or runtime catalog cache. The saved synthetic 10,000-worker heuristic median was about 306 ms in one local run, including preparation and packing. This is not a vector-search measurement or production guarantee. See [discovery](../server/services/execution/discovery.py), [rankers](../server/services/execution/ranking.py), and [ranking evidence](worker-ranking-implementation-plan.md).
- Cache worker embeddings once per changed profile. A request normally needs one query embedding. Comparing stored vectors is local numerical work, not an embedding-model call per worker. Exact scanning costs work proportional to catalog size times vector dimension; latency depends on implementation, storage, and hardware.
- Approximate nearest-neighbor (ANN) indexes already avoid exhaustive comparison. HNSW navigates a similarity graph. IVF selects a few vector-space partitions and searches their contents. Storing nodes and embeddings in a graph database does not provide these search behaviors automatically.
- The primary target is [LIM-006](known-limitations.md#lim-006). Quality, freshness, and reconciliation constraints remain under [LIM-002](known-limitations.md#lim-002), [LIM-003](known-limitations.md#lim-003), [LIM-004](known-limitations.md#lim-004), and [LIM-001](known-limitations.md#lim-001). None is resolved by this discussion.

## 3. Minimum graph model

| Record | Information and purpose |
| --- | --- |
| Worker node | Exact dispatch name, profile, profile hash, embedding/model version, scope and data generation. A search representation of an existing owner, not a replacement runtime identity. |
| Community node | Versioned membership, representative vectors, member count, optional display label. Routes queries to a subset. |
| `SIMILAR_TO` edge | Sparse nearest-neighbor similarity and index version. Supports community construction and boundary inspection. |
| `MEMBER_OF` edge | Versioned worker/community membership. Fetch selected members without loading the whole roster. |
| Optional `CHILD_OF` edge | A later community hierarchy if there are too many representatives to search cheaply. |

Profiles must describe the ongoing work a worker owns, rather than only generic capabilities such as sending email. Workers with the same tools can own entirely different tasks. Initially use the same metadata available to comparison methods; richer summaries are a separate experimental factor with their own generation/update cost.

Labels help people inspect the demo. Route using representative vectors rather than an LLM examining every label. Start with a normalized centroid; if a community is diffuse, test several representative member vectors. Membership is a retrieval neighborhood, not proof of ownership, same-task identity, or permission to act.

## 4. Build and maintain outside the query path

1. Embed a consistent catalog generation and cache by profile hash/model version. Preserve exact names and known scope labels; do not invent missing legacy mailbox provenance.
2. Build a sparse nearest-neighbor graph using ANN. Avoid comparing every worker pair, which would make construction quadratic.
3. Run a weighted community algorithm such as Leiden and compute representatives. Leiden finds connectivity-based communities; it does not guarantee balanced groups, optimal routing, or overlapping membership. Multi-community selection and boundary links are explicit retrieval policies.
4. Publish profiles, embeddings, memberships, and representatives as a consistent versioned projection. Keep the previous usable version until replacement is ready; rebuild after model changes.
5. Refresh changed profiles incrementally and communities on a declared schedule/threshold. Keep new or dirty profiles searchable through a bounded delta index until incorporated; use global indexed lookup when that delta exceeds its bound. Unprojected workers must not silently disappear.

The projection is rebuildable. History-clear/reset generations must prevent stale names and vectors from attaching to newly created work. A global ANN index can support graph construction and query fallback/control; count its storage and maintenance cost.

## 5. Query path

1. Resolve explicit names/known owner references directly with current roster validation.
2. Embed the actual lookup request once. Apply supported scope constraints; the graph does not add application-level multi-user isolation.
3. Score representatives and select several communities using a configurable deterministic policy.
4. Fetch their union of members, eligible delta entries, and a bounded number of boundary neighbors. Deduplicate and score cached embeddings. Exact cosine scoring is a simple first implementation for small selected sets.
5. Widen when several communities are competitive, or use global ANN when selected groups exceed the declared budget. Similarity gaps are heuristics, not calibrated confidence. Validate the policy on held-out boundary cases.
6. Pack the final maximum-five-worker response within current size limits, preserving exact names and profile evidence. Any expensive reranking follows candidate generation over a small set.
7. Let the Interaction Agent select, inspect, or clarify as today. A graph miss/outage does not prove a new worker is needed. Revalidate the chosen name before dispatch.

Illustration only: 10,000 workers in 100 equal groups, one representative per group, and three selected communities imply about 100 representative comparisons plus 300 worker comparisons instead of 10,000. This excludes construction, updates, expansion, fallback, I/O, and query embedding generation. It is not a measured speedup/cost saving or a guarantee of balanced communities.

Community-restricted ANN needs a verified filter/index design. Taking a few global ANN hits and discarding those outside the communities does not search fully within those communities. Start with exact scoring over bounded selected membership; validate any filtered ANN against the chosen database version and query plan.

## 6. Database and integration

Neo4j is a reasonable demo host for worker/community nodes, similarity edges, embeddings, and inspection. Its HNSW vector index has an internal graph distinct from the visible community graph. Neo4j Graph Data Science documents Leiden; community construction is a separately configured job/dependency, not an automatic result of creating a vector index. Pin compatible versions before implementation.

Integrate at the `find_worker` discovery-service boundary. The current ranker receives an already constructed full catalog; replacing its scoring formula alone retains that preparation cost. Indexed discovery must retrieve candidate metadata directly from its maintained projection.

Preserve current name dispatch, source recovery, model-context/result budgets, and explicit baseline availability fallback. Record fallback's full-scan cost. Keep the experiment optional until evidence justifies default use. A vector index alone is simpler if speed is the only requirement; explicit communities must earn their additional maintenance cost.

## 7. Grouping and merging

Grouping naturally supports related-work inspection and duplicate suggestions, even if it does not outperform global ANN on latency.

Merging is a separate lifecycle operation. Two Alice workers can be close neighbors while owning distinct contracts. Similarity may propose reconciliation, not execute it. A future design must define canonical owners/aliases and preserve original histories, trigger/draft references, known account boundaries, pending work, and dispatch behavior. Current runtime identity remains names/filenames; graph edges do not implement that migration. Automatic merging is outside this experiment.

## 8. Evaluation and demo

Compare current lexical search, cached exact vector scan, global HNSW, and community routing plus exact subset scoring. Hold profiles, embedding model where applicable, query set, scope, packing, and hardware constant. Include actual boundary/fallback costs.

Measure relevant-owner recall before/after packing and final reuse/duplicate/clarification outcomes. Separately measure ANN recall against exact vector neighbors: a vector neighbor is not necessarily the actual owner. Include cross-community requests, same-person/different-task cases, weak metadata, new/changed profiles, unequal groups, and exact names.

Record p50/p95 query/end-to-end latency, communities/candidates visited, reliable vector-comparison counts where exposed, fallback rate, embedding/model calls and tokens, memory/storage, build/update latency, and repeated-query total cost. Preserve historical reports and label synthetic, scripted, and live evidence separately.

The demo highlights selected communities and inspected workers, shows measured counts/timing, demonstrates a boundary query triggering widening, and shows a profile update/indexing status. Grouping/duplicate suggestions do not merge owners. Visualization demonstrates the mechanism; production efficiency and task quality require their own evidence.

First implementation milestone, if authorized: one optional `find_worker` path with cached embeddings, versioned communities, exact subset scoring, and a global ANN control/fallback. Dependency reasoning, automatic merging, and a learned router remain separate. Retain community routing only if its recall/latency/inspectability tradeoff adds useful value beyond ordinary ANN.

## 9. Reading

- [HNSW paper](https://arxiv.org/abs/1603.09320): graph navigation for vector search; the key efficiency baseline.
- [Faiss index documentation](https://github.com/facebookresearch/faiss/wiki/Faiss-indexes): IVF partitions, multi-probing, HNSW, and speed/recall tradeoffs. IVF closely resembles selecting groups before scoring members.
- [Neo4j vector indexes](https://neo4j.com/docs/cypher-manual/current/indexes/search-indexes/vector-indexes/): storage, HNSW configuration, and version-specific capabilities.
- [Neo4j GDS Leiden](https://neo4j.com/docs/graph-data-science/current/algorithms/leiden/): weighted and hierarchical community detection; worker-routing quality still requires evaluation.

