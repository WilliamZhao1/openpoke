# Legacy versus bounded comparison

Decision mode: mock. Gmail effects: mock. Checks passed: True.

| Strategy | Correct routes / graded / cases | Wrong reuse | Unnecessary creation | Model attempts / HTTP | Failures | Exact draft sent | Elapsed ms |
| --- | --- | --- | --- | --- | --- | --- | --- |
| legacy | 2 / 2 / 2 | 0 | 0 | 7 / 7 | 0 | True | 41 |
| bounded | 2 / 2 / 2 | 0 | 0 | 7 / 7 | 0 | True | 111 |

Routing cases execute real lookup/registration and record accepted dispatch; their workers are not run. The approved-draft case executes chat acceptance, actual workers, callbacks and fake Gmail effects.

This is one small combined-strategy comparison, not a metadata/ranker ablation. This is not a general accuracy estimate. Mock decisions provide no live-quality evidence and may skip lookup entirely. Usage and cost totals stay unknown when any request lacks valid provider values; reported subtotals remain separate. Elapsed time is local end-to-end time including configured request pacing, not isolated provider latency. Recovered tool errors are reported separately from terminal task failures; downstream errors do not erase observed dispatch decisions.

Production configuration is unchanged. The default ranker remains heuristic_v1. No runtime mailbox or history was used.

See [results and traces](results.json), [numeric summary](summary.json), [public settings](comparison.json), [inputs and grading labels](inputs.json), and [source provenance](provenance.json).
