# Discovery-quality benchmark v2

## Accepted design and scope

Accepted on 2026-11-12. This benchmark addresses worker-catalog diversity and
discovery quality, separately from bounded model context, draft execution, and
the community PoC. Preserve the original fixtures and all historical reports.
Use the existing evaluation CLI and production discovery/ranking implementations;
do not change production rankers to improve the first benchmark score.

The dataset contains 100 explicitly authored workers in 20 task families/domains
and 200 requests: 50 development requests in five families and 150 evaluation
requests in 15 different families. Every family has five related workers and ten
requests. All 100 workers are judged owners somewhere; targets are not confined
to the original seven workers. Public metadata uses the actual 240-character
field bounds. Judgments and family/intent annotations are separate from the
name/purpose/recent-assignment projection supplied to ranking.

Ten request categories cover exact names, descriptions, paraphrases, shared
entities, periods/artifacts, dormant owners, multiple owners, ambiguous requests,
new work with overlapping vocabulary, and insufficient searchable evidence.
Ambiguous requests measure candidate coverage, not authorization or clarification
quality. Insufficient-evidence requests are diagnostic and excluded from primary
quality aggregates. No-match requests have no owner-recall denominator.

## Catalog construction

The same 100 workers form the base catalog. At 1,000 and 10,000 workers, three
fixed draws (seeds 11, 22, 33) add different deterministic populations. Within a
draw, each smaller catalog is an exact prefix of the larger one. Evaluate the
shared 100-worker base once, rather than counting it three times.

Expansion mixes heterogeneous background work with close alternatives sharing
organizations and task vocabulary. Close alternatives have explicitly different
project scopes. Judged requests identify the base project, so additional workers
are not silently treated as irrelevant to an otherwise unrestricted request.
Validation checks those scope boundaries and identity uniqueness. Generated
records are still synthetic and templated; they are not representative production
history. Keep fixed seeds, complete saved catalog snapshots, and canonical hashes.

## Measurement protocol

Freeze source data and judgments before measuring ranker results. First compare
heuristic_v1, idf_v1 and bm25_v1 without tuning. Run actual find_workers response
packing, with ranking-only timing separated from fresh-read end-to-end lookup.
Record top-1, recall@5, reciprocal rank, packed recall, complete-owner coverage,
precision, no-match false positives, failures, median/p95 timing and preparation
allocation. Report split, category, answerability, catalog size and draw separately.

Average repeated draws within each request before uncertainty calculations.
Resample whole task families, keeping their related requests together, for
descriptive 95% bootstrap intervals and paired ranker differences. Report distinct
requests/families and excluded failures. Draws and timing repeats are not new
independent quality samples. Intervals on authored synthetic families do not
establish production accuracy or fine-grained statistical power.

The implementation assistant also authors and checks the scenarios. Requests are
predominantly English; Unicode worker names do not establish multilingual semantic
retrieval quality. No
independent human review has occurred. Label review status as pending independent
review, and preserve that boundary even when integrity tests pass. Evaluation
families are disjoint from development families, but the author knows both.
No model/Gmail calls are needed to build or run this offline benchmark.

## Delivery checklist

- Versioned public workers, queries, separate judgments and generation vocabulary.
- Frozen manifest with provenance, file hashes and all seven catalog hashes.
- Dataset selection in the existing offline ranking CLI; reject live/agent modes.
- Integrity, leakage, nesting, grading, uncertainty and CLI regression checks.
- Saved first baseline with complete inputs, failures, controls and artifact hashes.
- Linked current evidence under LIM-029/LIM-030; retain broader limitations.

A later routing-only live comparison may test use of these candidates, with
context strategy held fixed. It requires separate live-mode support and provider
authorization; draft tasks and community integration are outside this delivery.

## Files and reproduction

The frozen source is under `evals/agent_overload/datasets/discovery_v2/`:

| File | Purpose |
| --- | --- |
| `workers.json` | The 100 public worker records, with only identity/name and production metadata |
| `families.json` | Split membership, domain and protected project scopes; excluded from ranking |
| `queries.json` | 200 requests with split/category/answerability annotations; no expected owner labels |
| `judgments.json` | Expected owner IDs and explicit relevance rationale; excluded from ranking |
| `scenario_source.json` | Reviewable original authoring record linking each family, its workers and requests |
| `background.json` | Vocabulary, activities and writing styles for deterministic catalog expansion |
| `manifest.json` | Canonical source/catalog hashes, seed policy and pending independent-review provenance |

`discovery_dataset.py` validates and materializes these inputs. The existing
`run.py` CLI selects the dataset, then `discovery_quality.py` calls the production
`SearchCatalog`, rankers and `find_workers`. `search_projection()` strips IDs and
all family/judgment annotations. No model generates data during a run.

Run from the repository root, with backend dependencies installed. Every output
destination must be new. The default dataset remains `legacy`; v2 is explicit:

```powershell
# Development only; use before making any retrieval changes.
.\.venv\Scripts\python.exe evals/agent_overload/run.py --compare-rankers heuristic_v1 idf_v1 bm25_v1 --dataset discovery-v2 --sizes 100 --split development --repeats 1

# Complete frozen baseline: 4,200 rows, all 200 requests, seven catalogs,
# three rankers and one timing repetition per row. Larger runs can take minutes.
.\.venv\Scripts\python.exe evals/agent_overload/run.py --compare-rankers heuristic_v1 idf_v1 bm25_v1 --dataset discovery-v2 --sizes 100 1000 10000 --draws 11 22 33 --repeats 1

# Use a fresh directory and --repeats 3 for more timing samples.
# A request is still only one quality case, regardless of timing repetitions.
.\.venv\Scripts\python.exe server/tests/run_tests.py
```

`--split evaluation` runs only the held-out families. `--draws 11` selects one
larger-catalog draw; the shared base is always evaluated once. Empty catalogs,
duplicate draws, and v2 live/agent comparisons are rejected. A passing command
means measurement completed without failed rows, not that quality is sufficient.

Outputs retain `inputs/`, complete `catalogs/*.json.gz` snapshots,
`results.jsonl.gz`, `comparison.json`, `summary.json`, `provenance.json` and
`artifacts.json`. Each result row is flushed as it is written; partial gzip files
can require streaming recovery after abrupt process termination. Failed rows are
retained and make exit status 1. `summary.json` includes category/answerability
breakdowns, actual metric denominators, per-draw timing, family intervals and
paired differences. Failed requests are excluded entirely from pooled draw means.

Precision is the fraction of returned candidates (up to five) that are relevant,
with zero for an empty result on a judged-positive request. Complete-owner
coverage requires every judged owner to be present, independently of precision.
Recall and coverage exclude no-match requests; their false-positive rate instead
measures whether any candidates were returned. Insufficient-evidence cases retain
separate diagnostic scores and are excluded from all primary quality metrics.

## First retained baseline, 2026-11-12

The [complete first run](../evals/agent_overload/discovery_comparisons/2026-11-12/README.md)
completed all 4,200 rows with zero runtime failures and no model/Gmail calls.
The backend suite passed 267 tests, including 12 new benchmark regressions.
All 22 artifact byte hashes and seven catalog fingerprints were read back and
verified. One timing repetition was used per row; quality results use all draws.

Evaluation results at 10,000 workers, averaging draws within each request:

| Ranker | Single-owner top-1 | Mean recall@5 / packed recall | Every owner packed |
| --- | ---: | ---: | ---: |
| heuristic_v1 | 74.44% | 92.92% | 90.00% |
| idf_v1 | 80.00% | 97.50% | 96.67% |
| bm25_v1 | 87.78% | 98.75% | 98.33% |

Top-1 uses 90 distinct evaluation requests; recall and complete-owner coverage
use 120, including multiple-owner and ambiguous cases. Fifteen insufficient-
metadata requests are diagnostic. All three methods returned candidates for all
15 evaluation no-match requests at every size/draw: a 100% candidate false-positive
rate on this deliberately overlapping sample. This is not a measured rate of
incorrect model dispatch or unnecessary worker creation.

The [numeric summary](../evals/agent_overload/discovery_comparisons/2026-11-12/summary.json)
retains family-cluster intervals, paired differences, all category results and
per-draw latency. At 100 workers the heuristic has higher evaluation recall than either
alternative, so the larger-catalog improvement is not a universal win. The new
dataset does not run the original v1 promotion gate or promote defaults.
Production remains heuristic_v1, independent label review is pending, and old
scores are not directly comparable to these different inputs.

The initial retained manifest used imprecise authorship wording. Its run README
clarifies assistant authorship; the current source manifest carries that same
clarification. Only provenance wording changed after scoring began: all six
data-file hashes and all seven catalog hashes remain identical. Original measured
inputs and numeric results were retained.
