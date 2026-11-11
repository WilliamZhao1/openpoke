# Worker ranking evidence, 2026-11-11

Production remains `heuristic_v1`. All three methods tied on this small authored
synthetic retrieval set; no replacement passed the offline improvement gate.
No live model or real Gmail call was made.

- [Retrieval report](retrieval-report.md): 16 queries, three methods, three catalog
  sizes, three timing repeats; 144 scored case/method/catalog rows.
- [Numeric retrieval summary](summary.json): metrics, denominators, failures,
  preparation allocation peak, timing distributions and eligibility decisions.
- [Scripted agent report](agent-report.md) and [summary](agent-summary.json): six
  agent runs; fixed bounded strategies; exact approved fake draft sent once per
  method, no unexpected mutations. Scripted decisions are not live routing evidence.
- `comparison.json` and `agent-comparison.json`: controls and ranker parameters.
- `provenance.json`: executed retrieval source fingerprints and fixture checksums.
- `evidence.zip`: complete original evidence under `retrieval/` and
  `scripted-agents/`, including all catalog snapshots, separate queries/judgments,
  ranked/packed results, actual synthetic agent traces, and each run's artifact
  manifest. Archive contents were read back and checked against those manifests.
- `artifacts.json`: hashes of the review files and compressed evidence here.

The retrieval run was repeated after backend validation finished, using frozen
scoring parameters. Repetitions measure local timing variability, not independent
accuracy samples. Preparation memory is traced Python allocation peak, not RSS.
The evaluation set is authored synthetic metadata retrieval; it cannot establish
real-world accuracy, semantic synonym handling or live model compliance.

See the [implementation plan](../../../../docs/worker-ranking-implementation-plan.md)
for commands, test coverage, configuration and promotion rules.
