# Worker ranking experiments

Date: 2026-11-11
Status: Implemented and locally validated. Production remains `heuristic_v1`;
neither alternative met the predeclared offline improvement gate.

## Goal

Compare interchangeable worker rankers using the same roster metadata, queries,
response budgets, and agent settings. Keep the current heuristic reproducible.
This extends the completed reduced-scope overload release; it does not reopen
its deferred workflow-storage or migration roadmap.

## Implementation checkpoints

- [x] Extract the existing heuristic behind a small ranker protocol and immutable
  catalog/result types. Preserve current public lookup behavior and reasons.
- [x] Add `idf_v1` (field weights, rarity, query coverage, bounded phrase bonus)
  and `bm25_v1` (independent field scores, frequency saturation, length normalization).
- [x] Add validated `OPENPOKE_WORKER_RANKER` configuration and direct injection.
  Keep `heuristic_v1` as the default and leave discovery/context flags independent.
- [x] Extend the existing evaluation CLI with an offline ranking comparison at
  100/1,000/10,000 workers. Save queries and relevance labels separately from
  ranker inputs, per-case scores, parameters, metrics, timings, and source hashes.
- [x] Add a ranker-only agent comparison with both discovery and context fixed
  to bounded. Preserve scripted/live provenance, synthetic Gmail effects, request
  limits, and the existing comparison/baseline behavior.
- [x] Verify baseline parity, ranking contracts, exact-name priority, Unicode,
  missing metadata, ambiguity, no matches, response budgets, configuration,
  metadata changes/clear, CLI isolation, and actual lookup/agent integration.
- [x] Run backend regressions and local comparisons; record results and promotion
  decision here. Add runtime caching only if measurements justify it.

## Evaluation and promotion rules (declared before measurement)

Use the existing frozen catalog generator. A separate versioned query/relevance
file describes metadata retrieval only: no resource-index, approval-state, or
historical-state claims. It includes development and evaluation cases; these are
small authored synthetic examples, not an independent real-world accuracy set.
Never use the old fixtures' scripted lookup candidates as measured rankings.

Report top-1 accuracy for single-owner queries, recall@5, reciprocal rank,
recall after the actual 3,500-character response packing, no-match false positives,
and preparation/ranking/lookup time and memory. Show development and evaluation
results separately. Keep relevant-owner coverage distinct from action correctness:
retrieving both ambiguous owners does not authorize choosing one.

A replacement is eligible only if it preserves exact-name and integration checks,
does not reduce evaluation recall@5 or packed recall versus the heuristic,
improves at least one evaluation quality metric without increasing no-match false
positives, and stays within twice baseline median end-to-end lookup time at 10,000
workers. Local timings are noisy; record repeats and p95 rather than claim a
universal latency guarantee. Eligibility alone does not promote a default.
Promotion additionally requires a useful live-model comparison with fixed model,
prompts, metadata and output limits, including actual draft effects. If this
evidence is absent or inconclusive, retain `heuristic_v1` and report the limitation.

## Scope limits

All initial rankers are deterministic local implementations, with no new service,
database, package dependency, log scanning, embeddings, or model calls inside
lookup. Scores are algorithm-specific, not confidence probabilities. Failures
stay failures; no silent ranker fallback. Recency is informational, not a scoring
feature. Exact worker identities, collision warnings, discovery-before-creation,
source recovery and confirmation behavior remain intact. Future semantic methods
must evaluate candidate retrieval as well as reranking: reranking a lexical
shortlist cannot recover a worker absent from that shortlist.

## Results

The isolated runner passes **255 backend tests**, including 14 new ranking,
configuration, CLI and integration tests. Golden response hashes were generated
from `find_workers` at the original commit `4677aae`, then compared with the
extracted implementation: **24 responses match exactly**, across empty,
100/1,000/10,000-worker catalogs and six query forms. They cover complete public
responses, not only the winning worker. Existing discovery, source recovery,
confirmation, application and history-clear checks continue to pass.

The local comparison completed **144 case/method/catalog rows** (16 authored
queries, three rankers, three catalog sizes), with three timing repetitions each.
Development/evaluation metrics stay separate. All three methods tied: evaluation
top-1 accuracy was 7/7, mean recall@5 and packed recall were 0.9444 over nine
relevant queries, reciprocal rank was 1.0, and the one evaluation no-match query
had no false positives. This small synthetic set is not an independent accuracy
estimate. In the ambiguous `Alice contract` query at 10,000 workers, every method
ranked the original contract first but its other judged-relevant owner, the
renewal, 502nd. The tie does not establish that this ambiguity has been solved.

Final evaluation-split local lookup measurements at 10,000 workers:

| Ranker | Median ms | p95 ms |
| --- | ---: | ---: |
| heuristic_v1 | 306.27 | 370.12 |
| idf_v1 | 360.57 | 448.84 |
| bm25_v1 | 352.63 | 426.80 |

Lookup includes fresh JSON reads, catalog preparation, ranking and response
packing. The final timing run followed backend validation, with frozen scoring
parameters. Shared catalog preparation at 10,000 workers took about 191.66 ms;
its separately traced Python allocation peak was 21,789,525 bytes. These are local
measurements, not provider latency or universal performance guarantees. No runtime
cache was added: repeated production lookup load has not been measured, and the
first release keeps fresh snapshot ownership/invalidation simple.

The fixed-strategy scripted agent comparison completed six rows (Alice-lunch
routing and approved-draft flow for each method). Every arm preserved bounded
discovery/context and fixed model/output settings, accepted the chat, delivered
the callback and sent the exact original fake draft once, with no unexpected
mutations. Separate forced-lookup transport tests verify the selected ranker is
actually used and every model request passes preflight. Another regression proves
ranker failure revokes discovery success and prevents new-worker creation.

**Decision:** retain `heuristic_v1`. Neither alternative improved the evaluation
quality metrics, so neither passed the offline gate. The live-model comparison
path is implemented, but no new live model/Gmail calls were made and no live
quality/cost claim is made. A paid live comparison is unnecessary for promoting
these candidates while the prerequisite offline improvement is absent.

The [saved evidence](../evals/agent_overload/ranking_comparisons/2026-11-11/README.md)
includes reviewable reports/summaries and a compressed, hash-verified archive of
complete catalog inputs, separate judgments, scored and packed results,
parameters, source fingerprints and scripted agent traces. Existing baseline and
earlier live evidence were not rewritten. No runtime user history or mailbox was
used by these comparisons.

## Interfaces and configuration

`server/services/execution/ranking.py` contains `WorkerRanker`, `RankedWorker`,
`SearchCatalog`, the three independent implementations and a small selector.
Call `rank_workers(ranker, query, catalog)` for validated, deterministic ordering;
the implementation's `rank` method supplies scored matches. The shared driver
requires exact known identities, unique results, positive finite scores, bounded
explanations and preservation of an exact original-name match. Scores stay out of
the public tool response. Each implementation's version and parameters are saved
in evaluation artifacts.

`find_workers` continues to own query validation, snapshot selection, collision
warnings and public response packing. It accepts `ranker=` for explicit injection;
otherwise it reads the validated `Settings.worker_ranker`. Catalogs contain only
detached immutable name/purpose/assignment data and local token statistics; they
do not contain fixture gold, resource ownership, approval state or histories.
The three implementations use identical Unicode normalization and tokenization.
No stopword/recency changes or runtime cache are included in this first comparison.

```dotenv
# Restart after changing; applies to lookup independently of the two strategies.
OPENPOKE_WORKER_RANKER=heuristic_v1
# Other explicit options: idf_v1, bm25_v1
```

An unknown identifier fails settings validation. Ranking errors remain lookup
errors, revoking discovery success through the existing tool handler. Changing
the method does not rewrite stored metadata/history. Returning to `heuristic_v1`
restores the original score/reason behavior.

## Comparison commands

Run from the repository root; every `--output` must be a new directory.
The CLI sets disposable data and dummy integration credentials before importing
the server. Offline and scripted runs block network connections. Existing baseline
and legacy/bounded comparison commands explicitly pin the heuristic control.

```powershell
# Local retrieval quality, timings and Python allocation peak; no model calls.
.\.venv\Scripts\python.exe evals/agent_overload/run.py --compare-rankers heuristic_v1 idf_v1 bm25_v1 --sizes 100 1000 10000 --repeats 3

# Real agent/worker/callback paths with scripted model decisions and fake Gmail.
.\.venv\Scripts\python.exe evals/agent_overload/run.py --compare-rankers heuristic_v1 idf_v1 bm25_v1 --ranker-agent-check --context-window 65536 --sizes 100 --cases alice-lunch

# Optional live model decisions; Gmail remains synthetic. Incurs provider charges.
.\.venv\Scripts\python.exe evals/agent_overload/run.py --compare-rankers heuristic_v1 idf_v1 bm25_v1 --ranker-agent-check --mode live --context-window 65536 --sizes 100 --max-calls 96

# Complete isolated backend regressions.
.\.venv\Scripts\python.exe server/tests/run_tests.py
```

The local comparison rotates method order, reuses prepared snapshots for the
ranking-only measurement, and separately measures the real discovery function
including fresh JSON reads and response packing. Allocation tracing runs in a
separate preparation pass and does not contaminate recorded timings. Repeats are
timing repetitions, not independent quality samples. Query judgments and catalog
inputs are saved separately. Failed rows are retained and excluded from metric
denominators, with explicit failure counts and a failing command status.

The agent mode changes only ranker selection; bounded discovery/context, model,
prompts, output reservation, seeded data and grading remain fixed. Model-free
replies establish plumbing and exact fake effects, not ranking/routing quality;
they can choose an existing worker without lookup. A separate transport-level
regression forces an actual `find_worker` exchange for every configured method.
Live mode has no automatic fallback and retains request/time limits and partial
evidence. The command never promotes production defaults.
