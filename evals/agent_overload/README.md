# Agent evaluations

Capture a model-free baseline, compare legacy and bounded strategies, or compare
worker rankers. Runs use synthetic Gmail and temporary application storage.

## Setup

Complete the [root setup](../../README.md#quickstart), including backend dependencies,
and activate its Python environment. Run all commands from the repository root.
The web app and backend server do not need to be running.

## Run

Capture the baseline without model calls:

```powershell
python evals/agent_overload/run.py
```

Output goes into a new directory under `evals/agent_overload/runs/`. Use
`--output <new-directory>` to choose a destination; existing directories are
never overwritten. Use `--sizes 0 100` for a smaller baseline capture.

<a id="phase-3-paired-comparison"></a>
## Compare strategies

Check legacy and bounded discovery/context with scripted model responses:

```powershell
python evals/agent_overload/run.py --compare --context-window 65536
```

`--context-window` is an explicit evaluation allowance for the pinned model,
not a provider-capacity claim. See [context configuration](../../docs/context-budgets.md#configuration).

<details>
<summary>Optional live-model comparison</summary>

This makes paid OpenRouter calls using `OPENROUTER_API_KEY` from the environment
or root `.env`. Gmail remains synthetic, and runtime mailbox/history are not used.

```powershell
python evals/agent_overload/run.py --compare --mode live --context-window 65536 --sizes 100 --max-calls 64
```

Use `--cases` to select frozen scenarios, `--max-calls` to limit provider requests,
and `--case-timeout` to limit each case. Partial and failed results are retained.
Both arms use the model/output settings pinned in `manifest.json`; the command
does not change application defaults.

</details>

## Compare rankers

Compare local retrieval quality and lookup timings without model calls:

```powershell
python evals/agent_overload/run.py --compare-rankers heuristic_v1 idf_v1 bm25_v1 --sizes 100 1000 10000 --repeats 3
```

See the [ranking guide](../../docs/worker-ranking.md#comparison-commands) for
agent checks, live comparisons, scoring rules, and saved results.

## Outputs and checks

Each completed run includes `report.md`, `summary.json`, input/provenance records,
and artifact hashes. Comparison runs also retain per-case traces, telemetry,
and fake Gmail effects. Exit codes: `0` passed, `1` failed checks/runtime errors,
`2` invalid configuration or an existing destination.

Scripted runs check local behavior, not live-model quality. Live runs grade routing
and fake tool effects separately. Missing provider usage/cost stays unknown.
See the [evaluation guide](../../docs/evaluation.md) for interpretation and limits.

Run the isolated backend regressions with:

```powershell
python server/tests/run_tests.py
```

## Saved evidence

- [Model-free baseline](baseline/report.md)
- [Live comparison and focused draft recheck](../../docs/agent-overload-comparison.md)
- [Ranking comparison](ranking_comparisons/2026-11-11/README.md)
- [Application release checks](../../docs/agent-overload-release-checks.md)

For all options, run `python evals/agent_overload/run.py --help`.
