# Discovery-quality v2 baseline, 2026-11-12

This is a new offline discovery baseline, using 100 authored workers, 200 requests
and three fixed background draws at 1,000/10,000 workers. The shared 100-worker
base is evaluated once. Three unchanged production rankers yield 4,200
case/method/catalog rows with one timing repetition per row. Timing repetitions
and background draws are not additional independent quality cases.

Read [report.md](report.md) for aggregate results and timing, [summary.json](summary.json)
for categories, answerability, denominators, failures, family-cluster intervals and
paired differences, and `results.jsonl.gz` for every scored/packed result.
`catalogs/` contains complete generated snapshots; `inputs/` retains the full
separate source inputs and judgments. Controls are in [comparison.json](comparison.json),
source/environment fingerprints in [provenance.json](provenance.json), regression
validation in [validation.json](validation.json), and byte hashes in [artifacts.json](artifacts.json).

The core workers and requests were authored by the same assistant that implemented
the evaluator. Independent human semantic review is pending. The initial retained
manifest's phrase "No model-generated data" means that catalog construction made
no separate model-provider calls; it must not be read as human-authored data.
The current dataset manifest clarifies assistant authorship. Only this provenance
wording changed after measurement began: all six source-file hashes and all seven
catalog hashes are identical to the retained initial manifest. No workers, queries,
judgments, generation rules or ranker parameters were tuned after scoring.

Primary recall excludes insufficient-metadata diagnostics; no-match requests have
no recall denominator. Ambiguous requests measure candidate coverage, not model
clarification or authorization. This run makes no model or Gmail calls, promotes
no defaults, and does not measure draft execution, bounded context, production
quality, or the community PoC. The background remains synthetic and templated;
answerable requests explicitly identify a protected project. Historical v1 results
and the original live comparison remain unchanged and are not directly comparable.

See the [benchmark design and commands](../../../../docs/discovery-quality-benchmark.md).
