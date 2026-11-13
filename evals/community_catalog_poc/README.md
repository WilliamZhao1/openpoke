# Community catalog evaluation

Compare flat vector search, Neo4j ANN, and community routing over a frozen
1,000-worker synthetic catalog. This experiment runs separately from the app.

## Setup

Run from the repository root with Python 3.11+. These examples use PowerShell.

```powershell
python -m venv evals/community_catalog_poc/.venv
$python = 'evals/community_catalog_poc/.venv/Scripts/python.exe'
& $python -m pip install -r evals/community_catalog_poc/requirements.txt
```

Start a dedicated disposable Neo4j Community **5.26.0** instance. With Docker,
run this in a separate terminal and keep it open:

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

The CLI connects to `bolt://127.0.0.1:17687`. No application `.env`, Gmail credentials,
external embedding API, or Neo4j plugins are needed.

<details>
<summary>Windows setup without Docker</summary>

Extract the [Neo4j 5.26.0 ZIP](https://dist.neo4j.org/neo4j-community-5.26.0-windows.zip)
into a disposable directory and set `JAVA_HOME` to a Java 21 runtime. Use this
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

From the extracted Neo4j directory, run
`bin/neo4j-admin.bat dbms set-initial-password catalog-poc-local-only` before first
startup, then `bin/neo4j.bat console`. Stop it with Ctrl+C when finished.

</details>

<a id="three-commands"></a>
## Run

In your evaluation terminal, build a snapshot, query it, and evaluate the accepted
five-community, three-representative configuration:

```powershell
$env:POC_NEO4J_PASSWORD = 'catalog-poc-local-only'
$snapshot = 'evals/community_catalog_poc/.venv/snapshot'

& $python evals/community_catalog_poc/demo.py build --output $snapshot
& $python evals/community_catalog_poc/demo.py query --snapshot $snapshot --query 'Cafe Etoile Acme original services' --communities 5 --representatives 3
& $python evals/community_catalog_poc/demo.py evaluate --snapshot $snapshot --communities 5 --representatives 3 --output 'evals/community_catalog_poc/.venv/results'
```

The first build downloads the pinned MiniLM model and creates the graph. Later
queries use the local cache. Keep Windows snapshot paths short to avoid cache
path-length problems. The example paths stay inside the ignored `.venv/` folder.

Use a **new output directory** for each evaluation. Repeating `build` reuses and
validates the cache; `--rebuild` explicitly replaces reserved PoC data in the
dedicated database. A fresh empty database needs a fresh build or explicit rebuild.

The CLI defaults remain two communities and one centroid. Pass both flags above
to reproduce the accepted configuration. For connection overrides and other
options, run `& $python evals/community_catalog_poc/demo.py query --help` or
`& $python evals/community_catalog_poc/demo.py evaluate --help`.

<a id="verification-and-presentation"></a>
## Checks

Run numerical mechanism tests without a model download or database:

```powershell
& $python -m unittest evals.community_catalog_poc.test_demo -v
```

For a direct-name lookup, query `Alice lunch`. Exact names bypass embedding and
community scoring; this does not measure semantic retrieval quality.

<details>
<summary>Inspect the graph</summary>

Open [Neo4j Browser](http://localhost:17474), connect to `bolt://127.0.0.1:17687`,
and sign in as `neo4j` with the password above. The saved graph has 20 communities;
`--communities 5` selects five to search for a query. List all groups with:

```cypher
MATCH (w:PoCWorker) RETURN count(w) AS workers;
MATCH (c:PoCCommunity) RETURN c.id, c.size ORDER BY c.id;
```

To display three sample workers from every community, use:

```cypher
MATCH (c:PoCCommunity)
CALL (c) {
  MATCH (w:PoCWorker)-[r:MEMBER_OF]->(c)
  RETURN w, r
  ORDER BY w.name
  LIMIT 3
}
RETURN c, r, w;
```

A single outer `LIMIT` can show only the first few groups. Similar worker names
come from synthetic person/topic templates with distinct project IDs; these are
test catalog entries. See [the fixture generator](../../server/tests/fixtures/catalogs.py).

</details>

## Outputs and results

Evaluation writes `report.md`, `results.json`, and representative/cache metadata.
Reports retain failed rows, recall, vector-neighbor overlap, comparison counts,
and warm lookup timings. No-match cases are excluded from recall denominators.

- [Design, configuration, and interpretation](../../docs/community-catalog.md)
- [Accepted three-representative results](runs/2026-11-11/three-representatives/comparison.md)
- [Original two-community report](runs/2026-11-11/evaluation/report.md)
- [Known limitations](../../docs/known-limitations.md)

These are small synthetic retrieval experiments. Confirmation queries are not an
independent holdout, and fewer comparisons do not establish lower latency or
production agent quality. Historical reports keep their original results.
