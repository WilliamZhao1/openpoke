# Frozen community catalog PoC

Standalone retrieval experiment over the existing 1,000-worker synthetic catalog.
It does not import the application, change its ranker, dispatch workers, or call Gmail.
The implementation follows [the PoC plan](../../docs/community-catalog-poc-plan.md).

For the accepted configuration, milestone history, and a presentation script, start
with [the demo progress and runbook](../../docs/community-catalog-demo-progress.md).

## Setup

Run from the repository root with Python 3.11+ in an isolated environment
(the pinned NetworkX version requires 3.11; the saved run used 3.12.3):

```powershell
python -m venv evals/community_catalog_poc/.venv
$python = 'evals/community_catalog_poc/.venv/Scripts/python.exe'
& $python -m pip install -r evals/community_catalog_poc/requirements.txt
```

The four direct dependencies are pinned to the versions used in the saved run.
The snapshot manifest also records model revision, runtime/library versions, source
hashes, catalog/cache fingerprints, community sizes, and build stages.

Use a **dedicated disposable Neo4j Community 5.26.0** instance. No GDS/APOC plugin,
application `.env`, external embedding API, or application dependency is needed.
For example, with Docker running:

```powershell
$env:POC_NEO4J_PASSWORD = 'catalog-poc-local-only'
docker run --rm --name openpoke-community-poc `
  -p 127.0.0.1:17474:7474 -p 127.0.0.1:17687:7687 `
  -e "NEO4J_AUTH=neo4j/$env:POC_NEO4J_PASSWORD" `
  -e NEO4J_server_memory_heap_initial__size=256m `
  -e NEO4J_server_memory_heap_max__size=512m `
  -e NEO4J_server_memory_pagecache_size=128m `
  neo4j:5.26.0-community
```

Keep that process running in another terminal. The default Bolt URI is
`bolt://127.0.0.1:17687`; Browser is [localhost:17474](http://localhost:17474).
Connect Browser to `bolt://127.0.0.1:17687` with the same credentials.
Each command also accepts `--uri`, `--user`, and `--database`, or the corresponding
`POC_NEO4J_URI`, `POC_NEO4J_USER`, and `POC_NEO4J_DATABASE` environment variables.
Password is read only from `POC_NEO4J_PASSWORD`, never saved in artifacts.
The CLI checks the exact Neo4j server version to keep the experiment reproducible.

If Docker is unavailable, extract the [Neo4j 5.26.0 Windows ZIP](https://dist.neo4j.org/neo4j-community-5.26.0-windows.zip)
into a disposable directory, set `JAVA_HOME` to a Java 21 runtime, and use this
`conf/neo4j.conf` in that instance:

```ini
server.default_listen_address=127.0.0.1
server.default_advertised_address=127.0.0.1
server.bolt.enabled=true
server.bolt.listen_address=:17687
server.bolt.advertised_address=:17687
server.http.enabled=true
server.http.listen_address=:17474
server.http.advertised_address=:17474
server.https.enabled=false
server.memory.heap.initial_size=256m
server.memory.heap.max_size=512m
server.memory.pagecache.size=128m
```

Before first startup, run `bin/neo4j-admin.bat dbms set-initial-password catalog-poc-local-only`,
then `bin/neo4j.bat console`. Stop it with Ctrl+C when finished.
See [Neo4j's Windows installation instructions](https://neo4j.com/docs/operations-manual/current/installation/windows/).
The saved smoke run used this ZIP method with Java 21; Docker was unavailable.

## Three commands

Choose explicit **new directories outside application data**. The example uses
the ignored experiment virtual environment to keep large generated model/cache
files out of version control. Saved reviewable results can go elsewhere.

```powershell
$env:POC_NEO4J_PASSWORD = 'catalog-poc-local-only'
$snapshot = 'evals/community_catalog_poc/.venv/snapshot'

& $python evals/community_catalog_poc/demo.py build --output $snapshot
& $python evals/community_catalog_poc/demo.py query --snapshot $snapshot --query 'Alice contract' --communities 2
& $python evals/community_catalog_poc/demo.py evaluate --snapshot $snapshot --output 'evals/community_catalog_poc/.venv/results'
```

The first build downloads `sentence-transformers/all-MiniLM-L6-v2` at immutable
revision `c9745ed1d9f207416be6d2e6f8de32d1f16199bf`, embeds only exact name,
purpose[:240], and recent assignment[:240], then builds the ten-positive-neighbor
undirected graph and seeded Louvain communities. Fixture IDs, entities, timestamps,
status, resources, and relevance labels never enter retrieval inputs.
The pure existing generator is loaded by file to avoid the `server` package's
application startup side effects. Model inference uses CPU; setup/download and
embedding are reported separately from lookup.

Rerun `build --output $snapshot` to validate and reuse the cache without embedding
or rewriting Neo4j. Query and evaluate load the model from that cache with
`local_files_only=True`. Changed catalog/model fingerprints, corrupt files, invalid
memberships, database errors, and missing indexes fail visibly. An intentional
full rebuild requires `build --output $snapshot --rebuild`. Rebuild replaces only
the reserved `PoCWorker`/`PoCCommunity` data and `poc_worker_vectors` index in the
dedicated database; it does not delete arbitrary directories or other DB labels.
Never point this experiment at a database whose PoC labels need preserving.

Query loads community representatives and sizes, then retrieves embeddings only
for selected members through Neo4j. Exact existing names return directly without
loading the model or scoring vectors. Output includes selected IDs/sizes, unique
candidates/fraction, representative and worker comparisons, exact names/scores,
embedding time, and lookup time. `--communities` accepts any positive integer and
clamps to the number of actual communities. Full-catalog coverage is explicit.
There is no automatic widening, global fallback, reranker, or abstention policy.

Evaluation compares exact cached NumPy vectors, the real Neo4j worker vector
index, and top-two-community routing. It preserves all 16 existing query cases,
development/evaluation splits, and judgments. Development cases are a smoke
check; fixed settings are not tuned against evaluation labels. Each non-direct
query is encoded once and that vector is shared by all methods. After warmup,
each method/query runs three timed repetitions in rotating order. Lookup timings
include the common exact-name DB probe and method-specific DB fetches/scoring;
they exclude shared embedding, cache/model loading, and database validation.

Both `query` and `evaluate` accept an explicit query-time `--communities` count
(default two). To repeat with five communities on the same model, vectors, and
graph, without rebuilding:

```powershell
& $python evals/community_catalog_poc/demo.py query --snapshot $snapshot --query 'Acme original services redline' --communities 5
& $python evals/community_catalog_poc/demo.py evaluate --snapshot $snapshot --communities 5 --output 'evals/community_catalog_poc/.venv/results-five'
```

The original snapshot manifest retains its two-community setting; the new result's
`settings` and `routing_width` record the actual requested/effective width. This
follow-up reuses already inspected authored cases, so it is diagnostic evidence
rather than an independent holdout. Each run needs a new output directory.

To use the three-representative router, keep five communities and add
`--representatives 3` to `query` or `evaluate` (the default is one centroid):

```powershell
& $python evals/community_catalog_poc/demo.py query --snapshot $snapshot --query 'Cafe Etoile Acme original services' --communities 5 --representatives 3
& $python evals/community_catalog_poc/demo.py evaluate --snapshot $snapshot --communities 5 --representatives 3 --output 'evals/community_catalog_poc/.venv/results-three-representatives'
& $python evals/community_catalog_poc/demo.py evaluate --snapshot $snapshot --communities 5 --representatives 3 --queries 'evals/community_catalog_poc/runs/2026-11-11/three-representatives/fresh-queries.json' --output 'evals/community_catalog_poc/.venv/results-three-fresh'
```

The first non-direct use creates `representatives-3.json` inside the snapshot from
the existing DB members. Each community retains its centroid and adds up to two
distinct member vectors chosen greedily farthest from their closest current
representative, with exact-name tie breaks. Queries and relevance labels are not
inputs to this step. Subsequent uses load the fingerprinted derived cache. This
does not download a model, recompute worker embeddings, change memberships, or
rewrite the original snapshot files. A corrupt derived cache fails visibly;
remove that single derived file to regenerate it from the frozen DB. Exact names
still bypass the model and representative cache.

Community scoring takes the best match across its representatives. All 20 groups
have three in the saved run, so every non-direct query counts 60 representative
comparisons plus every scored member, including exemplars scored again as members.
The one-time 2,000-comparison representative build and its approximately 1.12-second
setup cost are recorded separately. `results.json` records setup/cache metadata;
`representatives.json` preserves the actual vectors and selected exact names.

Reports now retain the original plan's gates and separately grade the user's
current demo targets: absolute evaluation owner-recall difference at most three
percentage points and fewer than one third of flat comparisons on **every**
non-direct request, including routing overhead. Latency has no demo gate.
`--queries` accepts the same authored query JSON schema as the original fixture;
custom/fresh provenance and splits are preserved rather than called independent.

`results.json` retains every timing sample and output, failures, per-case owner
misses, vector-neighbor overlap, and search effort. `report.md` presents these
results and the predeclared targets: at most 500 median explicit comparisons on
non-direct evaluation requests and owner recall within five percentage points of
flat vectors. Representatives count toward comparisons. ANN internal comparison
counts and candidate fractions remain unknown. Failed runs exit nonzero, retain
failed rows, and mark affected aggregates unavailable. No-match rows show their
candidates but are excluded from both recall denominators.

## Verification and presentation

The four numerical tests require NumPy, with no model download or database:

```powershell
& $python -m unittest evals.community_catalog_poc.test_demo -v
```

They demonstrate boundary loss/recovery with fixed vectors, and equality with
flat top five when every group is searched, including deterministic ties, unique
exact names, and count clamping. These are mechanism checks, not semantic quality
evidence.

The additional representative checks cover recovery of the hidden neighbor,
counting all routing comparisons, all-community equality, order-independent
selection, deterministic ties, and singleton communities.

After building, verify an exact name, a topical subset, then an ambiguous request
with manual widening. Repeating the same query exercises the offline model cache:

```powershell
& $python evals/community_catalog_poc/demo.py query --snapshot $snapshot --query 'Alice lunch'
& $python evals/community_catalog_poc/demo.py query --snapshot $snapshot --query 'Atlas repository authentication'
& $python evals/community_catalog_poc/demo.py query --snapshot $snapshot --query 'Alice contract' --communities 1
& $python evals/community_catalog_poc/demo.py query --snapshot $snapshot --query 'Alice contract' --communities 4
& $python evals/community_catalog_poc/demo.py query --snapshot $snapshot --query 'Acme original services redline' --communities 2
& $python evals/community_catalog_poc/demo.py query --snapshot $snapshot --query 'Acme original services redline' --communities 99999
```

Use real outputs, including failures. If a semantic boundary loss is absent,
present the numerical test as the explicitly labeled boundary mechanism example.
For an all-community control, `--communities 99999` clamps automatically.

Inspect the graph in Neo4j Browser (replace IDs with those printed by query):

```cypher
MATCH (w:PoCWorker) RETURN count(w) AS workers;
MATCH (:PoCWorker)-[r:MEMBER_OF]->(:PoCCommunity) RETURN count(r) AS memberships;
MATCH (c:PoCCommunity)<-[:MEMBER_OF]-(w:PoCWorker)
RETURN c.id, c.size, count(w) AS actual_members ORDER BY c.id;
SHOW VECTOR INDEXES YIELD name, state, populationPercent;

// Must return zero rows: one owner group for every worker.
MATCH (w:PoCWorker) OPTIONAL MATCH (w)-[r:MEMBER_OF]->(:PoCCommunity)
WITH w, count(r) AS memberships WHERE memberships <> 1 RETURN w.name, memberships;

// Candidate membership union must match the CLI's unique candidate count.
MATCH (c:PoCCommunity)<-[:MEMBER_OF]-(w:PoCWorker)
WHERE c.id IN ['community-000', 'community-001']
RETURN count(DISTINCT w) AS candidates;

// Display a bounded piece of selected membership and similarity structure.
MATCH (c:PoCCommunity)<-[m:MEMBER_OF]-(w:PoCWorker)
WHERE c.id IN ['community-000', 'community-001']
RETURN c, m, w LIMIT 60;
MATCH (a:PoCWorker)-[s:SIMILAR_TO]-(b:PoCWorker)
WHERE a.name = 'Alice Acme contract' RETURN a, s, b LIMIT 30;
```

The saved [evaluation report](runs/2026-11-11/evaluation/report.md) and
[results](runs/2026-11-11/evaluation/results.json) record the implementation run.
The [build manifest](runs/2026-11-11/build-manifest.json) and
[smoke traces](runs/2026-11-11/smoke.json) retain cache, membership, boundary,
and explicit failure checks. The saved run built 20 communities and 7,142 edges.
Routing scored a median 101 workers plus 20 representatives, reducing explicit
comparisons from 1,000 to 121. Evaluation owner recall@5 fell from 94.44% (flat)
to 61.11% (community); global ANN returned 38.89%. The comparison-count target
passed and the owner-recall target failed. Median warm lookup was 3.95 ms for
flat, 5.54 ms for ANN, and 76.57 ms for routing. Settings remain unchanged.

For the presentation, `Alice lunch` is an exact lookup, the Atlas request searches
102 workers and returns `GitHub review`, and `Acme original services redline`
omits `Alice Acme contract` with two communities but recovers it with all 20.
The `Alice contract` example returned the same top five at one and four groups;
it is not evidence of boundary recovery.

The subsequent [read-only diagnosis](runs/2026-11-11/diagnosis.json) reproduces the
original communities and flat scores from the frozen cache. For `original Acme
services`, the correct worker is globally first but its community ranks fifth.
Its mean pools the owner with 50 similar distractors. Amendment and two-topic
requests also lose owners at the top-two community gate. These are query-routing
losses; the similarity edges are not traversed at query time. Latency contributors
and the separate ANN approximation loss need further measurement. No settings
were changed and the original evaluation remains intact.

The user-requested [five-community follow-up](runs/2026-11-11/five-communities/comparison.md)
keeps the same snapshot and model. Evaluation owner recall rises from 61.11% to
88.89%, versus flat search's unchanged 94.44%. Vector-neighbor recall rises from
66.67% to 93.33%. The median member pool grows from 101 to 252 workers, with
272 total explicit comparisons including representatives. Warm median lookup
is 187.49 ms, versus 4.70 ms for the flat control in that follow-up run.
The five-point recall allowance is narrowly missed (a 5.56-point gap), so the
joint demo target still fails. Development owner recall is 100% at five groups.

Live DB membership checks show evaluation candidate-owner coverage before final
ranking rises from 61.11% to 94.44%. The two-topic request still excludes
`Alice Acme contract`; `Alice contract` now includes `Alice Acme renewal` in the
candidate pool but ranks it below the returned five, as flat search also does.
All 144 timing samples succeed, numerical checks pass, and original artifact and
snapshot hashes are preserved. The two widths were timed in separate warm runs;
the comparison is not an interleaved paired latency measurement. See the
[validation details](runs/2026-11-11/five-communities/comparison.json). No model
change or further width search followed this rerun.

A separate [lookup profile](runs/2026-11-11/five-communities/lookup-profile.json)
times three existing requests with three repetitions and unchanged outputs.
The community ranking stage takes a median 0.17 ms versus 1.25 ms for flat;
the combined member-query, Bolt transfer, driver decoding, and record
materialization takes 188.49 ms. Array conversion/validation adds 3.24 ms.
Both methods also pay about 4.1 ms for the exact-name DB probe. This isolates
the dominant combined retrieval/materialization stage, not its internal server,
transfer, and decoder components. These instrumented timing samples do not replace
the original evaluation or demonstrate a production performance bound.

The [three-representative experiment](runs/2026-11-11/three-representatives/comparison.md)
meets the current demo targets without changing MiniLM or the graph partition:

| Sample | Flat owner recall@5 | Routed owner recall@5 | Median / maximum comparisons |
| --- | ---: | ---: | ---: |
| Existing authored evaluation | 94.44% | 94.44% | 312 / 314 |
| Newly authored confirmation | 100% | 100% | 313 / 314 |

The maximum is 31.4% of flat's 1,000 comparisons, including all 60 representative
scores, and the owner-recall gap is zero on both samples. The router returns the
same ordered top-five names as flat for all 26 requests, with scores agreeing
within 1e-12. The combined lunch/services request now recovers both owners;
the ambiguous contract request still misses the renewal owner that flat misses.
Warm routed lookup remains about 186 ms; latency optimization was deferred.

All 234 timing samples, four numerical checks, live membership/representative
checks, cache reuse/corruption handling, and per-request budget checks pass.
The [frozen protocol](runs/2026-11-11/three-representatives/protocol.json),
[original-sample report](runs/2026-11-11/three-representatives/existing/report.md),
[new-query report](runs/2026-11-11/three-representatives/fresh/report.md), and
[validation](runs/2026-11-11/three-representatives/validation.json) preserve the
rule, inputs, representative provenance, and unchanged prior artifact hashes.
The ten new queries were frozen before prototype quality measurement, but were
authored by the same assistant after inspecting prior cases and target the same
seven core owners. All seven happen to be selected among the 40 member exemplars
in this repetitive synthetic catalog. These are small synthetic demo results,
not independent production-quality evidence; the broader limitations stay open.

Keep Windows snapshot paths short: Hugging Face's nested cache paths can exceed
the OS path-length limit. The initial longer-path download failed; the successful
build reused partial downloads at `.venv/snapshot`. The recorded 15.21-second
build covers that successful attempt, not all earlier setup/download work.

Warm small-sample timing is noisy and is not comparable to historical fresh-JSON
lookup benchmarks. The all-pairs build is quadratic and deliberately limited to
1,000 frozen workers. No result establishes production response packing, correct
dispatch, live-agent quality, scalable updates, or lower end-to-end cost. Existing
[system limitations](../../docs/known-limitations.md) remain open.
