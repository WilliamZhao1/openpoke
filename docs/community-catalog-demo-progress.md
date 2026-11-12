# Community catalog demo: progress and runbook

Last updated: 2026-11-11. User-approved checkpoint: **three representatives, five communities**.

This is the starting point for future demos and continuation of the community-catalog PoC. Keep new milestones here and link their immutable results. The [implementation plan](community-catalog-poc-plan.md) records scope and decisions; the [experiment README](../evals/community_catalog_poc/README.md) covers installation and CLI details. System limitations remain in [the central register](known-limitations.md).

## Current result to present

On the frozen 1,000-worker synthetic catalog, community routing matches the flat-vector control's owner recall while using fewer than one third of its explicit vector comparisons on every tested non-direct lookup.

| Sample | Judged evaluation requests | Flat owner recall@5 | Routed owner recall@5 | Median comparisons | Maximum comparisons |
| --- | ---: | ---: | ---: | ---: | ---: |
| Existing authored evaluation | 9 | 94.44% | 94.44% | 312 | 314 |
| New authored confirmation | 9 | 100% | 100% | 313 | 314 |

The accepted demo targets are:

- Absolute owner-recall difference from the same-model flat control at most **three percentage points**. Both observed gaps are zero.
- Total explicit comparisons **strictly below one third of flat on every non-direct request**, including routing work. The observed maximum is **314 / 1,000 = 31.4%**.
- Latency is outside the current demo gate and remains a tracked follow-up.

Evidence: [comparison and interpretation](../evals/community_catalog_poc/runs/2026-11-11/three-representatives/comparison.md), [existing-sample report](../evals/community_catalog_poc/runs/2026-11-11/three-representatives/existing/report.md), [new-authored-sample report](../evals/community_catalog_poc/runs/2026-11-11/three-representatives/fresh/report.md), [frozen protocol](../evals/community_catalog_poc/runs/2026-11-11/three-representatives/protocol.json), and [validation](../evals/community_catalog_poc/runs/2026-11-11/three-representatives/validation.json).

## Configuration to preserve

| Setting | Checkpoint |
| --- | --- |
| Catalog | Existing `build_catalog(1000)`; seven core owners plus 993 synthetic distractors |
| Retrieval inputs | Exact name, purpose[:240], recent assignment summary[:240] |
| Embedding model | `sentence-transformers/all-MiniLM-L6-v2`, CPU, normalized 384-dimensional vectors |
| Model revision | `c9745ed1d9f207416be6d2e6f8de32d1f16199bf` |
| Graph | Ten highest positive-scoring neighbors per worker; undirected; seeded Louvain, seed 42, resolution 1 |
| Frozen graph size | 1,000 workers, 20 communities, 7,142 similarity edges |
| Representatives | Centroid plus two diverse members per community; 60 representatives total |
| Representative selection | Choose the member farthest from the centroid, then the distinct member farthest from its closest existing representative; exact-name tie breaks |
| Community score | Maximum query cosine across its three representatives |
| Search width | Five communities; pass `--communities 5` explicitly |
| Representative mode | Pass `--representatives 3` explicitly; the CLI default remains one centroid |
| Final ranking | Exact cosine over selected members, exact-name tie breaks, top five |
| Exact name | Direct DB lookup; bypasses embedding and community routing |
| Database | Dedicated disposable Neo4j Community 5.26.0; no GDS/APOC |

Representatives are selected without queries, relevance judgments, or owner-specific exceptions. Cached worker embeddings, memberships, and earlier reports were preserved. Each lookup counts all 60 representative comparisons plus all scored members, including exemplars scored again. The snapshot-wide calculated bound is 315; the measured maximum is 314.

The derived `representatives-3.json` cache is tied to the original snapshot ID and its own policy/content fingerprint. Its one-time construction took about 1.12 seconds and 2,000 vector comparisons, recorded separately from query effort.

## Progress so far

All milestones below occurred on 2026-11-11. Historical results retain their original gates and measurements.

| Milestone | Observed result | Evidence |
| --- | --- | --- |
| Initial standalone PoC: two communities, one centroid | Evaluation owner recall 61.11% versus flat 94.44%; median 121 comparisons | [Original report](../evals/community_catalog_poc/runs/2026-11-11/evaluation/report.md) |
| Boundary diagnosis | A globally first contract owner belonged to the fifth-ranked community; the combined-topic request's contract group ranked eleventh | [Diagnosis](../evals/community_catalog_poc/runs/2026-11-11/diagnosis.json) |
| Widen to five communities | Owner recall improved to 88.89%; median 272 comparisons; still below the desired recall | [Five-community comparison](../evals/community_catalog_poc/runs/2026-11-11/five-communities/comparison.md) |
| Profile the slowdown | Combined member-query/transfer/decoding stage dominated; vector ranking itself was fast | [Instrumented profile](../evals/community_catalog_poc/runs/2026-11-11/five-communities/lookup-profile.json) |
| Freeze revised demo targets | Three-point recall allowance and fewer than one-third comparisons per request; defer latency optimization | [Frozen experiment protocol](../evals/community_catalog_poc/runs/2026-11-11/three-representatives/protocol.json) |
| Add three representatives, retain five groups and MiniLM | Match flat recall on both samples; maximum 314 comparisons; both targets pass | [Current comparison](../evals/community_catalog_poc/runs/2026-11-11/three-representatives/comparison.md) |
| Verification and user acceptance | Four numerical checks and 234 timing samples passed; user selected this result as the future demo checkpoint | [Validation](../evals/community_catalog_poc/runs/2026-11-11/three-representatives/validation.json) |

## Demo preparation and commands

Run from the repository root. The current machine retains the isolated Python environment, model cache, graph files, and snapshot under `evals/community_catalog_poc/.venv/`; they are ignored local setup, not portable checked-in assets. Neo4j was **stopped after verification**. Start the dedicated instance before querying. For a fresh machine or missing local cache, follow [the setup instructions](../evals/community_catalog_poc/README.md#setup).

For the retained Windows ZIP instance, start this in a separate PowerShell terminal:

```powershell
Set-Location 'D:\personal_projects\openpoke'
$env:JAVA_HOME = (Resolve-Path 'evals/community_catalog_poc/.venv/tools/jdk21/zulu21.40.17-ca-jre21.0.6-win_x64').Path
& 'evals/community_catalog_poc/.venv/tools/neo4j/neo4j-community-5.26.0/bin/neo4j.bat' console
```

The instance uses `bolt://127.0.0.1:17687`; Neo4j Browser is at `http://127.0.0.1:17474`. The credentials below are for this dedicated disposable local demo only. In the presentation terminal:

```powershell
Set-Location 'D:\personal_projects\openpoke'
$pocPython = 'evals/community_catalog_poc/.venv/Scripts/python.exe'
$pocSnapshot = 'evals/community_catalog_poc/.venv/snapshot'
$env:POC_NEO4J_PASSWORD = 'catalog-poc-local-only'
$env:HF_HUB_OFFLINE = '1'

# 1. Exact-name ownership: no query embedding or community scoring.
& $pocPython evals/community_catalog_poc/demo.py query --snapshot $pocSnapshot --query 'Alice lunch' --communities 5 --representatives 3

# 2. Topical subset retrieval: inspect selected groups and all comparison counts.
& $pocPython evals/community_catalog_poc/demo.py query --snapshot $pocSnapshot --query 'Atlas repository authentication' --communities 5 --representatives 3

# 3. The observed boundary loss and its recovery, on the same model and graph.
& $pocPython evals/community_catalog_poc/demo.py query --snapshot $pocSnapshot --query 'Cafe Etoile Acme original services' --communities 5 --representatives 1
& $pocPython evals/community_catalog_poc/demo.py query --snapshot $pocSnapshot --query 'Cafe Etoile Acme original services' --communities 5 --representatives 3

# Model/database-free mechanism checks.
& $pocPython -m unittest evals.community_catalog_poc.test_demo -v

# Optional rerun: choose a NEW output directory each time, preserving saved reports.
& $pocPython evals/community_catalog_poc/demo.py evaluate --snapshot $pocSnapshot --communities 5 --representatives 3 --output 'evals/community_catalog_poc/.venv/demo-rerun-new'
```

In the boundary example, the one-centroid/five-group policy returns the lunch owner but misses `Alice Acme contract`; the three-representative policy returns both. Finish by opening the saved comparison table and explaining the recall and effort targets. The [experiment README](../evals/community_catalog_poc/README.md#verification-and-presentation) includes Neo4j Browser inspection queries.

## Claims and follow-ups to keep distinct

- This is catalog retrieval over a frozen synthetic snapshot. Application discovery, dispatch, Gmail, worker lifecycle, and UI were not changed.
- Original-sample evaluation has nine judged requests. The ten new queries include nine judged requests and one no-match diagnostic; they were frozen before prototype quality measurement but authored by the same assistant after prior failures were inspected. They are not an independent holdout.
- All seven core owners appear among the 40 member exemplars, against repetitive synthetic distractors. This favorable fixture property limits generalization.
- The ambiguous `Alice contract` request still misses a renewal owner also missed by flat. Equal recall does not mean all owners are retrieved correctly.
- No-match cases still return candidates; abstention is unimplemented. Exclude them from recall denominators and present them as diagnostics.
- Routed lookup is still about 186 ms versus about 4–5 ms for the cached flat control. The paths have different transfer/cache boundaries. No production latency advantage is established; optimization and a matched timing comparison remain deferred.
- A fresh representative catalog/query set and live-agent evidence are separate future work. Do not silently change the accepted model, selection rule, width, or comparison accounting while presenting this checkpoint.

Keep broader issues open under [LIM-003](known-limitations.md#lim-003), [LIM-004](known-limitations.md#lim-004), [LIM-006](known-limitations.md#lim-006), [LIM-029](known-limitations.md#lim-029), and [LIM-030](known-limitations.md#lim-030). Append future milestones here with configuration, evidence, and changed limitations; preserve prior reports and distinguish planned work from completed measurements.
