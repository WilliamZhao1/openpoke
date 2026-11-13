# Bounded solution test rerun — November 13, 2026

**The local tests and offline harnesses passed. The expanded live comparison failed its overall gate.** All 272 backend tests, five frontend checks, lint, TypeScript checking and the production build passed. Live routing matched the fixture action and all owners in 7/9 scenarios for each strategy. Bounded also had one terminal turn failure after selecting the correct owner. Both strategies sent the original approved fake draft exactly once, without unexpected mailbox mutations.

This run covers the active bounded solution, including discovery-v2. Community PoC/database experiments and the inactive deferred checkpoint are excluded under the existing bounded-first scope. No production history or mailbox was used; live model calls were explicitly authorized and all Gmail effects remain fake. Production code, prompts, graders, fixture labels and defaults were not changed to obtain a passing result.

## Run results

| Check | Result | Executed scope | Time |
| --- | --- | --- | --- |
| [backend](checks/backend.log) | Passed (exit 0) | 272 tests / 23 modules; unit and scripted integration checks | 62.17 s |
| [frontend](checks/frontend.log) | Passed (exit 0) | 5 Node/React/history/proxy checks | 1.85 s |
| [lint](checks/lint.log) | Passed (exit 0) | Next.js ESLint, no cache | 9.52 s |
| [typecheck](checks/typecheck.log) | Passed (exit 0) | TypeScript --noEmit | 1.75 s |
| [build](checks/build.log) | Passed (exit 0) | Next.js production build | 19.02 s |
| [baseline](checks/baseline.log) | Passed (exit 0) | 40 frozen legacy prompt contexts plus one scripted exact-draft smoke trace | 2.06 s |
| [scripted](checks/scripted.log) | Passed (exit 0) | 4 paired rows: lunch routing and approved draft, both strategies | 1.73 s |
| [ranking-v1](checks/ranking-v1.log) | Passed (exit 0) | 144 rows: 16 queries × 3 rankers × 3 sizes; 3 timing repeats | 70.33 s |
| [ranker-agents](checks/ranker-agents.log) | Passed (exit 0) | 6 scripted rows: lunch routing and approved draft for each ranker | 2.08 s |
| [discovery-v2](checks/discovery-v2.log) | Passed (exit 0) | 4,200 rows: 200 requests × 3 rankers × 7 catalogs; one timing repeat | 1526.04 s |
| [live](checks/live.log) | FAILED (exit 1) | 18 rows: all 8 supported routing scenarios plus approved draft, both strategies | 203.52 s |

The live comparison used the pinned `anthropic/claude-sonnet-4.6`, 2,048 output reservation, 65,536 planning allowance, 32,768 input cap, 1,024 headroom, 180 seconds per case, a global 128-request ceiling and 3.1-second pacing. It completed 61 provider requests. The empty-catalog case used zero workers; other live scenarios used 100. These budgets are application planning settings, not published provider-capacity claims.

## Scenario-to-test map

The complete appendices map **every executed backend/frontend test** and **every retrieval request**:

- [All backend and frontend test cases, scenarios, source locations and results](test-case-map.md)
- [All 16 original and 200 discovery-v2 retrieval requests, with expected owners](retrieval-case-map.md)
- [Live decisions, initial roster names, actual model tool calls and returned tool data](live-case-map.json)

| Case | Scenario | Exact live case ID | Legacy | Bounded |
| --- | --- | --- | --- | --- |
| A | Worker is outside the recent list: recover the original 2023 tax owner through lookup and dispatch that exact worker. | `dormant-owner` | Passed | Passed |
| B | Shared person, different task: reuse the original Acme contract worker rather than the Alice lunch worker. | `alice-contract` | Passed | Passed |
| C | Nonempty catalog with new garden work: create a new worker rather than reuse an unrelated owner. | `genuinely-new` | Passed | Routing FAILED |
| D | No workers yet: create the first worker for the garden task without needing prior lookup. | `empty-catalog` | Routing FAILED | Routing FAILED |
| E | After Uber/GitHub topic switches, the final Atlas authentication-review request belongs to the GitHub worker. | `alternating-topics` | Routing FAILED | Passed |
| F | Ambiguous draft referent: abstain from arbitrary dispatch; the routing grader does not score clarification wording or recovery quality. | `competing-drafts` | Passed | Passed |
| G | One request covers lunch and the original contract: dispatch both exact owners; one owner alone fails. | `two-owners` | Passed | Passed |
| H | A seeded exact draft review followed by approval: reuse its owner and send the original fake draft exactly once through the worker/callback flow. | `approved-draft` | Passed | Passed |
| I | Existing lunch work: reuse Alice lunch and complete the Interaction Agent turn; routing-only workers are not actually run. | `alice-lunch` | Passed | Routing passed; turn FAILED |

### Case A: worker outside the recent list

The bounded model initially saw these five recent workers: `Uber receipts`, `Acme amendment`, `Alice lunch`, `Alice Acme contract`, `Alice Acme renewal`. `2023 tax documents` was absent. The actual live sequence was:

1. After a user acknowledgement, the model tried creating `Morgan 2023 tax filing`; the backend rejected this because discovery had not succeeded.
2. The model called `find_worker` with `Morgan 2023 tax filing correspondence`.
3. The real lookup returned `2023 tax documents` first among five packed candidates (24 total matches).
4. The model dispatched the exact original worker `2023 tax documents` and finished the turn.

This passed routing, while retaining the recovered tool error. The routing-only worker was a recorder, so this proves real lookup/owner selection rather than actual tax-email completion. The related backend cases are `WorkerDiscoveryTests.test_old_worker_is_findable_outside_recent_entries` and `WorkerRankingTests.test_real_lookup_loop_uses_selected_ranker_with_bounded_preflight`; their model responses are local/scripted.

## Live failures and interpretation

- **D / empty catalog, both strategies:** expected creation of the first garden worker; both models instead asked the user clarifying garden questions and dispatched nothing. The grader records abstention, so this fails the declared fixture action. This is not evidence that asking clarification is always wrong for real users.
- **C / genuinely new work, bounded:** expected creation for the new garden task; bounded instead asked clarification and dispatched no worker. Legacy created new work and passed.
- **E / alternating topics, legacy:** expected dispatch to `GitHub review`; legacy called `wait` and said the worker was already handling the request. No dispatch occurred in this turn, so it failed the fixture. Bounded dispatched the expected owner and passed.
- **I / Alice lunch, bounded:** selected the correct worker but consumed all eight allowed model iterations without a final response. All eight provider calls returned HTTP 200; there were no model or tool errors in that row. The trace contains assistant-authored worker/calendar claims despite workers being recorders. Those claims are not actual worker output or evidence that calendar/email actions occurred. Legacy completed this case.

The original six-scenario subset (original contract, dormant owner, new work, competing drafts, two owners, approved draft) was also present: legacy 6/6 correct routes, bounded 5/6. This is one fresh stochastic observation, not a repeated-trial accuracy estimate. No failed case was automatically rerun or label changed.

The routing grader checks dispatch action and exact owner set. It does not grade clarification wording, required-recovery steps, open-obligation state or general worker success. A routing-only pass therefore does not prove successful task completion.

## Live usage and exact effects

| Measurement | Legacy | Bounded |
| --- | ---: | ---: |
| Correct routes | 7 | 7 |
| Terminal failures | 0 | 1 |
| HTTP/model calls | 28 | 33 |
| Model errors | 0 | 0 |
| Tool errors | 0 | 1 |
| Provider input tokens | 139566 | 201246 |
| Provider output tokens | 1950 | 3048 |
| Provider-returned cost total | 0.447948 | 0.649458 |
| Exact approved fake draft sent | Once | Once |
| Unexpected fake mailbox mutations | 0 | 0 |
| Chat accepted and callback observed in draft flow | Yes | Yes |

All 61 calls supplied valid usage/cost. The combined returned cost field totals 1.097406; no rate-card estimate fills missing data. Bounded used more input tokens/calls/reported cost in this sample. Case timings include deliberate pacing. Offline lookup runs overlapped part of the live run, so timing is descriptive local evidence rather than an isolated performance comparison.

## Offline retrieval results

All 144 original retrieval rows completed without runtime failures. All three methods again tied on evaluation quality: 7/7 single-owner top-1, 94.44% mean recall@5/packed recall over nine judged relevant requests, reciprocal rank 1.0, and no false positive on the one no-match request. The ambiguous `Alice contract` query still placed the other relevant owner at rank 502 at 10,000 workers. See [numeric v1 summary](ranking-v1/summary.json).

Discovery-v2 completed 4,200 rows without runtime failures. Its 200 authored requests cover 20 families and all 100 base workers. At 10,000 workers, evaluation results average the three draws within each request:

| Ranker | Single-owner top-1 | Recall@5 | Packed recall | Every owner packed | No-match false positives |
| --- | ---: | ---: | ---: | ---: | ---: |
| heuristic_v1 | 74.44% | 92.92% | 92.92% | 90.00% | 100.00% |
| idf_v1 | 80.00% | 97.50% | 97.50% | 96.67% | 100.00% |
| bm25_v1 | 87.78% | 98.75% | 98.75% | 98.33% | 100.00% |

Top-1 uses 90 distinct evaluation requests; recall/coverage use 120. Fifteen insufficient-metadata requests are diagnostic. All methods return candidates for all 15 evaluation no-match requests in this overlapping-vocabulary dataset; this is candidate false-positive evidence, not actual wrong dispatch. At 100 workers the heuristic retains higher evaluation recall than either alternative. Labels remain authored by the implementation assistant, with independent semantic review pending. Neither this rerun nor a passing measurement command promotes a ranker; production remains `heuristic_v1`. See [v2 numeric summary, intervals and category breakdowns](discovery-v2/summary.json).

## Coverage still absent

- The six fixture IDs not supported by paired comparison remain unrun live: `pronoun-draft`, `stale-card`, `near-tied-owners`, `partial-lookup`, `lookup-unavailable`, `explicit-old-thread`. Related contract tests are not live evidence for those exact cases.
- No live discovery-v2 routing, alternate-ranker agent comparison, 1,000/10,000-worker agent run, independent production-quality sample or model/sampling matrix was added.
- No live Gmail/OAuth, real mailbox watcher, browser clicks/visual scrolling, production-load benchmark or provider-native token-accuracy validation was performed.
- ASGI/component and scripted large-content tests passed; they do not establish live-model large-email comprehension, summarization/classification accuracy or complete browser behavior.
- Durable approval/revision locking, restart replay, exactly-once effects, cross-process execution, multi-user isolation and automatic retention remain documented unsupported/deferred capabilities.

## Evidence and execution notes

- [Machine-readable overall results and commands](results.json), [test cases and source hashes](test-cases.json), [live evidence](live/README.md), [live public controls](live/comparison.json), [live source provenance](live/provenance.json).
- Every retained per-run artifact hash was read back and verified; command-log hashes were verified too. Complete raw runs remain at [20261113T055958Z-full-suite](D:/personal_projects/openpoke/evals/agent_overload/runs/20261113T055958Z-full-suite). Each offline subfolder also contains a complete `evidence.zip`, read back against its original manifest. Extract it into a new directory to follow original relative links. The copied original manifests describe these complete runs; this bundle has its own `artifacts.json`.
- An initial display-only helper error encountered Windows console Unicode when printing successful lint/build tails. Both underlying commands had already completed with exit 0 and their full logs/status files were retained. The local helper was corrected to escape unsupported console characters. This did not change or rerun application code; both helper versions and their hashes are retained.
- Historical comparisons and their failed evidence were preserved. New findings are linked from the central limitations register; no broad limitation is marked resolved.
