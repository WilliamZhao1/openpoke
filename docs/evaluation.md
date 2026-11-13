# Evaluation guide

OpenPoke separates retrieval measurements, agent routing, tool effects, application
checks, and provider usage. A passing test in one layer does not establish quality
in another. This guide indexes retained evidence; reorganizing the documentation
does not run a new benchmark or change historical results.

## Evaluation layers and reproduction

Run commands from the repository root, using an environment with the documented
dependencies installed. Backend and agent-harness runners isolate storage and
credentials from runtime data. See the CLI guides for output-directory rules.

| Layer | Command or guide | What it establishes |
| --- | --- | --- |
| Backend regressions | `python server/tests/run_tests.py` | Runtime contracts with mocked providers and disposable data |
| Frontend history | `npm test --prefix web` | Chat-history handling under the frontend test runner |
| Model-free baseline | `python evals/agent_overload/run.py` | Full-roster fixtures, telemetry availability, synthetic routing/effect plumbing |
| Retrieval comparison | [Worker ranking commands](worker-ranking.md#comparison-commands) | Actual ranked/packed outputs, judged-owner recall, local lookup timing, and preparation allocation |
| Varied discovery benchmark | [Discovery-quality v2](discovery-quality-benchmark.md) | 100 authored workers, 200 family-split requests, seven frozen catalogs and separate diagnostic/primary metrics; independent review pending |
| Paired agent comparison | [Agent harness](../evals/agent_overload/README.md#phase-3-paired-comparison) | Legacy/bounded controls; scripted or live model decisions; Gmail effects remain fake |
| Application checks | [Release checks](agent-overload-release-checks.md) | Scripted HTTP/proxy/rendering, callbacks, triggers, startup/shutdown, and clearing |
| Community mechanism checks | `python -m unittest evals.community_catalog_poc.test_demo -v` | Numerical boundary recovery, deterministic selection, and comparison accounting; requires NumPy |
| Semantic retrieval experiment | [Community CLI](../evals/community_catalog_poc/README.md), [design and results](community-catalog.md) | Actual pinned local embeddings and Neo4j over a frozen synthetic catalog; separate from application dispatch |

Live agent comparisons incur provider charges only when explicitly selected.
Scripted checks are not live-model evidence. Community evaluation requires its
separate model/database setup; numerical tests do not require either.

## Discovery-v2 regression validation

The discovery-v2 extension adds 12 backend checks; its 2026-11-12 isolated run
passed **267 backend tests**. It introduces no frontend changes or new live-model
evidence. Its [design and evidence](discovery-quality-benchmark.md) keep worker
discovery measurements separate from the broader bounded release and historical
release-check counts.

## Saved results

| Evidence | Observed outcome and boundary |
| --- | --- |
| [Full bounded rerun, 2026-11-13](../evals/agent_overload/validation_reports/2026-11-13-full-suite/report.md) | 272 backend and five frontend checks pass, with lint/type/build, baseline/scripted comparisons, 144 original retrieval rows and 4,200 v2 rows. Expanded live comparison covers all eight supported routing cases plus approved draft in both arms: 7/9 correct routes each, one bounded terminal turn failure, exact fake draft sends in both arms, overall gate failed. Complete test/request scenario maps and preserved evidence distinguish local contracts, live routing and fake effects. |
| [Baseline](../evals/agent_overload/baseline/report.md) | Model-free control, not live quality/cost evidence |
| [Legacy/bounded live comparison](agent-overload-comparison.md) | Both arms selected expected routing actions/owners in 6/6 selected scenarios at 100 workers. Original bounded draft effect failed; focused guidance recheck passed. Fake Gmail, small synthetic sample. |
| [Ranking comparison](../evals/agent_overload/ranking_comparisons/2026-11-11/retrieval-report.md) | All three rankers tied: 94.44% mean owner recall@5 over nine judged evaluation queries, 100% top-1 over seven applicable queries. Same authored queries repeated at 100/1,000/10,000 workers. Default remains `heuristic_v1`. |
| [Varied discovery v2](../evals/agent_overload/discovery_comparisons/2026-11-12/report.md) | 4,200 offline rows, no failures; 10,000-worker evaluation recall@5 is 92.92%/97.50%/98.75% for heuristic/IDF/BM25. Family-level uncertainty and per-draw results retained; independent review pending, no defaults promoted. |
| [Scripted ranking agents](../evals/agent_overload/ranking_comparisons/2026-11-11/agent-report.md) | Six rows preserve routing/callback plumbing and exact fake draft effects; scripted choices do not measure live compliance. |
| [Community routing](community-catalog.md#evaluation-and-results) | Five communities/three representatives match flat recall on both nine-request judged samples, with maximum 314/1,000 explicit comparisons. Confirmation is not independent; latency remains slower. |

Historical comparisons and their raw evidence remain under `evals/`. Generated
agent runs under `evals/agent_overload/runs/` remain local. Use fresh output
directories for reruns; preserve failures, original gates, and provenance.

## Interpreting the evidence

- Relevant-owner recall measures retrieval, not authorization or action correctness.
  A no-match or clarification case cannot supply a judged-owner recall denominator.
- Timing repetitions measure variability, not extra independent quality cases.
- Smaller roster text and fewer vector comparisons do not establish lower total
  provider usage, application latency, or production cost.
- Missing usage/cost stays unknown. Estimates, characters, provider tokens, and
  available subtotals remain separately labeled.
- Standalone graph results do not demonstrate production graph routing. The
  confirmation queries target known owners after prior failures were inspected.
- The original live draft failure and focused recheck both remain visible. The
  focused fix alone does not establish a complete post-fix six-case result;
  the separate 2026-11-13 expanded rerun includes that original subset and its
  new routing failures rather than substituting the focused recheck.

Current evidence gaps remain open under [LIM-029](known-limitations.md#lim-029)
and [LIM-030](known-limitations.md#lim-030). Retrieval limits remain under
[LIM-003](known-limitations.md#lim-003) and [LIM-006](known-limitations.md#lim-006).

## Provider usage in the original paired run

The following arithmetic was derived on 2026-11-12 from the retained
[request/usage traces](../evals/agent_overload/comparisons/2026-11-09/results.json.gz)
and [numeric summary](../evals/agent_overload/comparisons/2026-11-09/summary.json).
No new model calls were made. Both discovery and context strategies change
between arms, so this does not isolate the roster's token cost.

| Measurement | Legacy | Bounded |
| --- | ---: | ---: |
| First-request input tokens, six-case sum | 29,807 | 32,214 |
| First-request input tokens, mean | 4,967.8333 | 5,369 |
| Complete-run input tokens | 106,344 | 143,212 |
| Complete-run model calls | 21 | 25 |
| Live-comparison initial roster characters | 4,702 | 1,083 |

The first-request token counts are legacy `[4951, 4949, 4945, 4978, 4951, 5033]`
and bounded `[5343, 5341, 5337, 5391, 5343, 5459]`: bounded is larger in every
pair, with an 8.0753% increase in the mean. Complete-run input increases by
36,868 tokens (34.6686%), despite 76.9672% fewer initial roster characters.
These are actual provider `usage.prompt_tokens`, not tokenizer estimates.
The original bounded failure and recovery errors are included. A complete
post-fix rerun has not established token savings.

## Request components

The original `alice-contract` first-request pair shows where payload increased:

| Component | Legacy | Bounded | Unit |
| --- | ---: | ---: | --- |
| Worker-list text | 4,702 | 1,083 | Characters, roster interior excluding surrounding whitespace |
| Complete system instructions | 10,424 | 14,065 | Characters |
| Complete user message | 4,901 | 1,412 | Characters, including the worker-list row |
| Tool definitions | 2,006 (4 tools) | 4,721 (7 tools) | Characters in compact JSON |
| Complete first-request input | 4,951 | 5,343 | Provider-reported tokens |

Roster text falls by 3,619 characters while system instructions grow by 3,641
and tool-definition JSON by 2,715. Bounded mode adds `find_worker`, `read_result`,
and `recall_history`, plus reference-based draft arguments. Retrieved matches
arrive later as tool results. Component character counts do not allocate native
tokens to individual components. Measuring a token crossover at larger catalogs
requires a separate controlled comparison.

Source: [original traces](../evals/agent_overload/comparisons/2026-11-09/results.json.gz).
Current [prompt construction](../server/agents/interaction_agent/agent.py),
[tool schemas](../server/agents/interaction_agent/tools.py), and
[context policy](../server/context_builder.py) explain the mechanisms; historical
request strings supply the sizes above.

## Roster scale checks

The [discovery verification](worker-discovery.md#verification) repeats the exact
query `Alice lunch` at three synthetic catalog sizes. The
[existing test](../server/tests/test_worker_discovery.py) asserts the worker is
first with the `exact_name` reason at every size. This is 3/3 successful
model-free exact-name checks, not general 100% recall or live-model accuracy.

| Workers | Legacy initial roster characters | Bounded initial roster characters | Reduction | Lookup-result characters |
| --- | ---: | ---: | ---: | ---: |
| 100 | 4,702 | 1,108 | 76.44% | 1,801 |
| 1,000 | 47,947 | 1,110 | 97.68% | 1,804 |
| 10,000 | 480,397 | 1,112 | 99.77% | 1,807 |

At 10,000 workers, initial roster plus one lookup result is 2,919 characters,
99.39% below the legacy roster alone. This compares those text components,
not complete requests or tokens. The 1,108-character fixture row and the
1,083-character live-comparison row use different setups. The broader retrieval
result is separately 94.44% mean recall@5 over nine judged synthetic requests.

The focused scale test was rerun through the repository runner's disposable
storage/credential isolation on 2026-11-12 and passed all three sizes. This
records the existing validation; no new model or Gmail call was made for this guide.
