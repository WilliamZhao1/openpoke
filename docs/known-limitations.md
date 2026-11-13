# Known system limitations

Last reviewed: 2026-11-12. Initial source baseline: `b8a9c32`.

This is the central register for known OpenPoke limitations, intentional runtime bounds, deferred capabilities, and gaps in the evidence. It consolidates the active discovery, ranking, context, draft, and release documentation plus inspected runtime paths. It covers the whole application, including limitations relevant to agent overload. It is an inventory of known issues, not a claim that every undiscovered defect has been identified.

## Keeping this register current

- Add or update an entry when implementation work, review, testing, or a user discussion exposes a limitation. Search existing entries before adding another ID.
- Preserve IDs and resolved entries. When fixing an item, record the date, changed behavior, and relevant regression or other verification; do not silently delete it.
- Each entry needs a concrete behavior/impact, current safeguards, evidence links, and a condition for reconsidering or closing it. Distinguish observed behavior from an unverified concern.
- Use **Open** for a current capability gap, **Designed bound** for a deliberate limit, **Deferred** for excluded scope, **Evidence gap** for an unsupported claim, and **Resolved** for a verified historical finding.
- An entry is not a commitment to implement a fix or expand the current task. Priority, owner, and schedule remain unassigned until explicitly decided.
- Feature documents remain the detailed evidence. This register tracks current status; historical reports keep their original results.

## Index

| ID | State | Limitation |
| --- | --- | --- |
| [LIM-001](#lim-001) | Open | Different names can represent the same work |
| [LIM-002](#lim-002) | Open | Candidate selection and ambiguity handling depend on model decisions |
| [LIM-003](#lim-003) | Open | Lexical retrieval can miss relevant owners |
| [LIM-004](#lim-004) | Open | Discovery metadata is partial and can become stale |
| [LIM-005](#lim-005) | Designed bound | Query/result packing can omit distinguishing evidence or candidates |
| [LIM-006](#lim-006) | Open | Lookup still processes the whole backend catalog |
| [LIM-007](#lim-007) | Deferred | Worker identity remains name/filename based |
| [LIM-008](#lim-008) | Open | Budget estimates are not native token counts |
| [LIM-009](#lim-009) | Designed bound | Model allowances require configuration; bounded accounting is text-only |
| [LIM-010](#lim-010) | Designed bound | Required giant inputs or recent episodes can stop processing |
| [LIM-011](#lim-011) | Designed bound | Recovery is limited and requires deliberate source selection |
| [LIM-012](#lim-012) | Open | Historical truncation and unknown mailbox provenance cannot be reconstructed |
| [LIM-013](#lim-013) | Designed bound | Inner search, classification and summarization can exhaust work budgets |
| [LIM-014](#lim-014) | Open | Confirmation is agent policy, without a durable approval ledger |
| [LIM-015](#lim-015) | Open | External Gmail drafts are not revision-locked after review |
| [LIM-016](#lim-016) | Designed bound | Exact body adapters have size and format limits |
| [LIM-017](#lim-017) | Deferred | No shared execution admission limit or per-worker run serialization |
| [LIM-018](#lim-018) | Open | Overlapping requests can share a batch and delay callbacks |
| [LIM-019](#lim-019) | Deferred | Accepted work and callback delivery are not durably replayed |
| [LIM-020](#lim-020) | Open | External effects do not have an exactly-once guarantee |
| [LIM-021](#lim-021) | Open | History clearing is not an atomic cancellation of all activity |
| [LIM-022](#lim-022) | Deferred | Local locks/atomic writes do not provide distributed or power-loss guarantees |
| [LIM-023](#lim-023) | Deferred | Content retention and resource use lack hard application-wide quotas |
| [LIM-024](#lim-024) | Open | File/cursor integrity assumptions and repair remain limited |
| [LIM-025](#lim-025) | Deferred | No application-level multi-user isolation/authentication model |
| [LIM-026](#lim-026) | Open | Watcher coverage, retries and notification delivery are best effort |
| [LIM-027](#lim-027) | Open | Chat-history delivery and UI completion tracking remain unbounded/heuristic |
| [LIM-028](#lim-028) | Designed bound | Legacy opt-outs restore unbounded prompt behavior |
| [LIM-029](#lim-029) | Evidence gap | Live quality and application coverage are limited |
| [LIM-030](#lim-030) | Evidence gap | Lower total cost/latency and complete persistent measurements are unproven |
| [LIM-031](#lim-031) | Resolved | Provider draft ID confused with saved-content reference |
| [LIM-032](#lim-032) | Resolved | Frontend decoded literal escape sequences twice |
| [LIM-033](#lim-033) | Resolved | Trigger-store SQLite connections remained open |
| [LIM-034](#lim-034) | Resolved | Cancelled background tasks could abort evaluation draining |

## Discovery and identity

<a id="lim-001"></a>
### LIM-001 — Different names can represent the same work

**Status: Open.** `Alice contract` and `contract with Alice` can coexist with separate histories. `AgentRoster.register()` checks exact membership and filename collisions, not equivalence of task purpose. A successful `find_worker()` attempt permits creation when other workers exist; it does not prove semantic uniqueness or require zero matches.

**Current safeguard:** lookup exposes related workers, exact returned names support reuse, and the prompt guides the Interaction Agent to resolve ownership. No automatic merge, alias reconciliation, or backend semantic deduplication exists. **Closure condition:** demonstrate duplicate-task cases and validate an explicit deduplication/reconciliation policy that preserves distinct tasks and original histories.

**Design clarification, 2026-11-11:** [Catalog communities](community-catalog.md#interpretation-and-deferred-integration) could surface related workers and reconciliation candidates. Similarity or shared membership does not establish duplicate ownership. Actual merging remains separate lifecycle work requiring canonical-owner/alias rules and preservation of histories, references, and pending work.

Evidence: [discovery rules](worker-discovery.md), [runtime identity scope](runtime-scope.md), [registration](../server/services/execution/roster.py), [dispatch guard](../server/agents/interaction_agent/tools.py).

<a id="lim-002"></a>
### LIM-002 — Candidate selection and ambiguity handling depend on model decisions

**Status: Open.** Ranking returns candidates; the Interaction Agent chooses whether to look up, which exact worker to reuse, or whether to create work. An exact existing name can be dispatched without lookup. Scores are not confidence probabilities, and the creation guard is not an ambiguity resolver or intent-isolation system.

**Current safeguard:** current-request/follow-up guidance, exact callback/trigger owners, recoverable history, and clarification instructions. These do not guarantee correct model behavior. **Reconsider when:** reproduced wrong-owner reuse, topic leakage, or ambiguous-draft decisions justify stronger checks, with actual action correctness measured separately from retrieval.

**Expanded live rerun, 2026-11-13:** the [retained test report](../evals/agent_overload/validation_reports/2026-11-13-full-suite/report.md) exercises all eight supported routing scenarios plus the approved-draft flow in both strategies. Both arms match the fixture action/owner set in 7/9 scenarios. Both ask clarification instead of creating the expected first garden worker; bounded also asks clarification instead of creating new garden work in a nonempty catalog, while legacy waits instead of dispatching the expected GitHub owner after topic switches. These are failures against declared fixture actions, not proof that clarification or waiting is universally wrong. Bounded lunch selects the correct owner but reaches the eight-iteration limit; its routing-only trace contains assistant-authored worker/calendar claims even though workers are recorders. Those claims are not actual worker output or action evidence. Bounded dormant-owner lookup recovers after the creation guard rejects a premature new name. Exact fake draft sending passes in both arms. This remains one synthetic live sample, with no production failure-rate claim or policy change; broader model-decision limits stay open.

**Proposed experiment, 2026-11-11:** [Community-routed catalog discovery](community-catalog.md#interpretation-and-deferred-integration) would narrow candidates before final selection. Membership and vector similarity do not prove ownership or resolve ambiguity; multi-community lookup and widening need validation. This is a design recommendation, not an implemented resolver or measured improvement; the status remains open.

**PoC scope:** the [implemented standalone experiment](../evals/community_catalog_poc/README.md) exercises retrieval with manual widening. It does not exercise Interaction Agent selection, dispatch, clarification decisions, or duplicate creation. The [saved synthetic evaluation](../evals/community_catalog_poc/runs/2026-11-11/evaluation/report.md) is retrieval evidence only; this limitation remains open.

Evidence: [interaction prompt](../server/agents/interaction_agent/system_prompt.md), [interaction tools](../server/agents/interaction_agent/tools.py), [ranking scope](worker-ranking.md), [live comparison](agent-overload-comparison.md).

<a id="lim-003"></a>
### LIM-003 — Lexical retrieval can miss relevant owners

**Status: Open; demonstrated on synthetic evaluation.** All current rankers use local lexical evidence. Synonyms, weak metadata, or competing similar tasks can defeat retrieval. In the saved 10,000-worker ambiguous `Alice contract` case, all three rankers placed another judged-relevant owner at rank 502, outside the returned set.

**Current safeguard:** exact-name priority, alternative deterministic rankers, match reasons and repeated refined lookup. Neither `idf_v1` nor `bm25_v1` improved the declared quality metrics in the original 2026-11-11 v1 comparison; the later v2 evidence below does not promote a default. Production remains `heuristic_v1`. **Closure condition:** improve candidate coverage on representative failures, including retrieval before reranking; reranking a shortlist alone cannot recover an absent candidate.

**Varied offline evidence, 2026-11-12:** the [discovery-v2 baseline](discovery-quality-benchmark.md#first-retained-baseline-2026-11-12) measures 200 assistant-authored requests across 20 different task families and seven catalog snapshots. At 10,000 workers, mean evaluation recall@5 is 92.92% for heuristic_v1, 97.50% for idf_v1 and 98.75% for bm25_v1 over 120 distinct relevant requests, with draws averaged within each request. Complete-owner coverage is respectively 90.00%, 96.67% and 98.33%. At 100 workers the heuristic has slightly higher recall than either alternative. Every method returns candidates for all 15 evaluation no-match requests at each size/draw because those new tasks deliberately share existing project vocabulary. This is retrieval candidate evidence, not incorrect model dispatch or a live production failure. Independent label review is pending; no production ranker or original v1 promotion decision changed. Preserve both datasets' evidence and reconsider after independently reviewed representative cases and separately authorized routing validation.

**Proposed experiment, 2026-11-11:** [Cached semantic retrieval and community routing](community-catalog.md#interpretation-and-deferred-integration) could generate candidates independently of lexical top five. Compare equally informed exact-vector and global ANN controls. Community exclusion can itself lose relevant owners, so measure boundary recovery and relevant-owner recall separately from agreement with exact vector neighbors. No graph implementation, new live failure, or quality benefit is established by this discussion.

**PoC evidence, 2026-11-11:** the [standalone implementation and real-model/Neo4j evaluation](../evals/community_catalog_poc/runs/2026-11-11/evaluation/report.md) now exist. Across nine nonempty-relevance evaluation cases at 1,000 workers, mean owner recall@5 was 0.9444 for flat vectors, 0.3889 for global ANN, and 0.6111 for top-two-community routing. Community vector-neighbor recall@5 was 0.6667. On the existing development request `Acme original services redline`, routing excluded `Alice Acme contract`; [the saved DB smoke trace](../evals/community_catalog_poc/runs/2026-11-11/smoke.json) records recovery when all 20 communities are searched. Manual widening and exact-name lookup are safeguards, not automatic recovery. The five-percentage-point owner-recall target failed; settings were not tuned against evaluation labels. These are authored synthetic retrieval outcomes, not live-agent failures or a production ranker change. Reconsider community routing only with a separately authorized retrieval policy and representative coverage evidence.

**Diagnostic follow-up, 2026-11-11:** [Read-only reconstruction from the cached vectors](../evals/community_catalog_poc/runs/2026-11-11/diagnosis.json) reproduced the original seeded communities and the saved flat top-five scores exactly. For `original Acme services`, `Alice Acme contract` is the flat first result, but its community representative ranks fifth; that community contains the owner plus 50 `Alice Chen contract` distractors. The amendment owner's community ranks fourth for its request, while the two relevant owners' communities rank third and eleventh for the two-topic request. The implementation assigns each worker to exactly one community and gates retrieval on the top two normalized means; it does not traverse similarity edges at query time or recover excluded groups. These cases confirm loss at candidate selection rather than failure of the shared final cosine scorer. Single-centroid dilution, exclusive membership, and fixed routing width are concrete PoC bounds; a useful graph partition does not by itself establish a useful query router. Multiple representatives, overlapping/neighbor expansion, broader/global candidate generation, and later reranking remain unimplemented options. Reconsider on development evidence and a fresh evaluation set, preserving the original failed result; reranking alone cannot recover excluded workers.

**Next-experiment clarification, 2026-11-11 (proposal only):** candidate coverage means judged-relevant owners admitted to the member pool before final top-five ranking; a larger candidate count alone is not proof of better coverage. The smallest available diagnostic is explicit manual widening from two to five communities using the same model and snapshot. Five would include the original-contract development case's fifth-ranked owner community, but aggregate owner recall and latency at that width have not been measured; this is not a newly passed target. Keep development checks and any fresh evaluation distinct from the original report. A model change is a separate experiment: the current [MiniLM model](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2) is already available for local use; [BGE-small-en-v1.5](https://huggingface.co/BAAI/bge-small-en-v1.5) and [E5-small-v2](https://huggingface.co/intfloat/e5-small-v2) are MIT-licensed retrieval alternatives, not verified improvements for this catalog. Follow each model's query/document input conventions and fully rebuild cached worker vectors, communities, centroids, and the DB index for a model change. Do not mix embeddings across models or change model and routing width together when attributing effects. No widening run, alternate model download, model migration, or runtime integration was performed by this discussion.

**Authorized five-community follow-up, 2026-11-11:** the user then requested the five-community run. [The saved comparison](../evals/community_catalog_poc/runs/2026-11-11/five-communities/comparison.md) keeps the exact same model, worker vectors, graph, queries, and judgments. Evaluation owner recall@5 improves from 0.6111 to 0.8889, versus flat's unchanged 0.9444; vector-neighbor recall improves from 0.6667 to 0.9333. The 0.0556 owner-recall gap narrowly misses the original 0.05 allowance. [Live membership checks](../evals/community_catalog_poc/runs/2026-11-11/five-communities/comparison.json) show mean evaluation candidate-owner coverage before final ranking improves from 0.6111 to 0.9444. The two-topic request still excludes `Alice Acme contract` at the community gate. The ambiguous contract request now admits `Alice Acme renewal` but ranks it below the final five, as flat search also does. Widening improves these observed retrieval results without resolving candidate/ranking limitations or establishing general quality. No further width search or model change followed; reconsider on separately developed coverage/ranking improvements and fresh evaluation evidence.

**Next demo target/proposal, 2026-11-11:** the user proposed recall within three percentage points of flat and fewer than one third as many total explicit comparisons. The [next-experiment proposal](../evals/community_catalog_poc/runs/2026-11-11/three-representatives/protocol.json) interprets effort per non-direct request and counts representative scoring: with 1,000 flat comparisons, at most 333, and a current recall floor of 0.9144 against flat's 0.9444. The five-community result (0.8889, median 272 comparisons) misses the recall requirement. Proposed single-variable change: retain the model/partition/five groups and replace one-vector community routing with a centroid plus two diverse, label-free member representatives, using the best of three query matches. Across the frozen 20 groups, 60 representative comparisons plus at most 255 members gives a 315-comparison bound. This is a proposed budget calculation, not measured new quality or proof of recovery. No representatives or new policy have been built/evaluated. Reconsider after a frozen-rule diagnostic and fresh judged evidence; preserve both earlier reports and their original gates. The nine-case evaluation sample is coarse: one half-recall request moves its mean by about 5.56 points, so a three-point target cannot establish fine-grained quality precision on that sample alone.

**Authorized three-representative result, 2026-11-11:** [The frozen-rule experiment](../evals/community_catalog_poc/runs/2026-11-11/three-representatives/comparison.md) implements a centroid plus two diverse member vectors per group, selected without queries/judgments and scored by maximum query similarity. With the same model/partition and five selected groups, original-sample evaluation owner recall@5 is 0.9444, matching flat; vector-neighbor recall@5 is 1.0. The observed two-topic exclusion is recovered on 2026-11-11; [live membership/output validation](../evals/community_catalog_poc/runs/2026-11-11/three-representatives/validation.json) confirms both owners enter the pool and top five. The ambiguous contract request still omits a renewal owner also omitted by flat. Nine newly authored judged queries also match flat at 1.0 recall; one additional new no-match query remains diagnostic. Both sets pass the revised absolute-three-point recall gate and per-request one-third comparison gate, with maximum 314 comparisons. This resolves the observed additional miss for this frozen policy/sample, not the broader lexical, boundary, ranking, or ownership limitations. Candidate-owner coverage is 1.0 on these evaluation sets, while final owner recall remains the separate reported metric. No production integration or model change followed.

Evidence: [ranking results and decision](worker-ranking.md), [rankers](../server/services/execution/ranking.py).

<a id="lim-004"></a>
### LIM-004 — Discovery metadata is partial and can become stale

**Status: Open.** Purpose is a snippet from the first observed assignment; recent assignment/activity are observations of assignment start. Text is capped at 240 characters. Older workers can lack fields, and these fields do not establish current completion, pending actions, or approval state.

**Current safeguard:** missing values stay unknown, names remain searchable, and the sidecar can be rebuilt without changing histories. Lookup avoids history scans/model summarization. **Reconsider when:** stale or incomplete metadata causes measured retrieval/routing errors; assess an incremental update policy without making metadata authoritative approval state.

**Proposed experiment, 2026-11-11:** The [catalog graph proposal](community-catalog.md#interpretation-and-deferred-integration) requires profile-hash/model-version embedding caches, consistent membership versions, refresh rules, and search coverage for new/dirty profiles. The standalone PoC implements frozen catalog/model fingerprints and explicit full rebuilds; live refresh and dirty-profile coverage remain unimplemented. Embedding current metadata or grouping it does not make its contents more complete or authoritative.

**PoC scope:** the [implemented experiment](../evals/community_catalog_poc/README.md) uses one frozen synthetic snapshot and explicit full rebuilds. Catalog/model/source and generated-file fingerprints guard cache reuse; database membership counts and the snapshot version are checked before querying. [Smoke checks](../evals/community_catalog_poc/runs/2026-11-11/smoke.json) verify offline cache reuse and rejection of corrupt cache data. Live changes, incremental refresh, and stale-owner handling remain outside this PoC.

**Derived representative cache:** the [three-representative implementation](../evals/community_catalog_poc/demo.py) binds its separate `representatives-3.json` cache to the original snapshot ID and a policy/content fingerprint. The first non-direct use makes one offline member-vector pass; later lookups load only the derived representatives before DB subset retrieval. [Validation](../evals/community_catalog_poc/runs/2026-11-11/three-representatives/validation.json) verifies each selected name/vector belongs to its group, cache reuse, explicit corruption failure, and exact-name bypass without the model/cache. This leaves original snapshot files intact and does not provide live metadata updates or incremental invalidation beyond the frozen-snapshot assumptions.

Evidence: [metadata behavior](worker-discovery.md), [`assignment_metadata()`](../server/services/execution/discovery.py), [assignment updates](../server/agents/execution_agent/batch_manager.py).

<a id="lim-005"></a>
### LIM-005 — Query/result packing can omit evidence or candidates

**Status: Designed bound.** Queries use the first 256 characters. Recent roster: at most five entries/2,000 characters. Lookup: at most five results/3,500 JSON characters. Descriptions shorten, and exceptionally long historical names can fail to fit. These bounds can hide a relevant worker or distinguishing information.

**Configuration clarification:** each lookup can request 1–5 results. The recent-list maximum and lookup maximum are currently the code constants `RECENT_LIMIT` and `LOOKUP_LIMIT` in [discovery.py](../server/services/execution/discovery.py), rather than dedicated environment settings. Changing either maximum requires an implementation change that keeps tool descriptions/defaults and payload budgets consistent. The [discovery explanation](worker-discovery.md#motivation-and-behavior) distinguishes the small prompt list from the complete stored catalog; older workers remain searchable.

**Current safeguard:** truncation/description/omission indicators, total counts, exact unshortened names and refined lookup. **Reconsider when:** packed recall or a concrete missed task warrants adjusting retrieval/querying within the model budget; count limits alone are not a coverage guarantee.

Evidence: [output limits](worker-discovery.md), [response packing](../server/services/execution/discovery.py).

<a id="lim-006"></a>
### LIM-006 — Lookup still processes the whole backend catalog

**Status: Open; local cost measured.** Each lookup reads the current JSON snapshot and builds/ranks the whole catalog. A bounded prompt does not bound backend work independently of catalog size. No persistent index or runtime cache is used.

**Current safeguard:** local deterministic algorithms with no model calls or worker-log scans. The saved 10,000-worker heuristic median lookup was about 306 ms in one local evaluation, not a production guarantee. **Reconsider when:** real repeated lookup load justifies indexing/caching with correct invalidation and owner isolation.

**Proposed experiment, 2026-11-11:** [Community routing](community-catalog.md#interpretation-and-deferred-integration) targets full-catalog processing with cached worker embeddings and subset retrieval. Current lookup has no embeddings, so its measured cost is not evidence that cosine comparison is the bottleneck. Compare cached exact vectors, global ANN, and community routing including preparation, updates, and fallback; replacing the ranker after building the full catalog would retain that preparation cost. No indexed runtime or efficiency gain is established.

**PoC scope:** the [minimal plan](community-catalog.md) compares three semantic retrieval methods on 1,000 frozen workers without changing application discovery. Its offline all-pairs graph build is an intentional small-demo shortcut, not scalable ingestion. Even a successful subset-search demonstration would leave current runtime full-catalog processing unchanged.

**PoC measurement, 2026-11-11:** the [saved run](../evals/community_catalog_poc/runs/2026-11-11/evaluation/report.md) built 20 communities and 7,142 undirected similarity edges. Non-direct evaluation requests scored a median 101 workers (10.1% of the catalog), plus 20 representative comparisons, versus 1,000 flat comparisons. Despite less explicit scoring, warm median lookup was about 76.57 ms for routing versus 3.95 ms for flat vectors; membership/vector transfer participates in routing time. Startup graph validation, shared embedding, and offline build are separately excluded/reported. Neither scalable ingestion nor lower runtime latency is established, and the application still processes the full catalog.

**Diagnostic boundary:** [Code inspection](../evals/community_catalog_poc/runs/2026-11-11/diagnosis.json) confirms that flat search uses an already loaded matrix, whereas routing also fetches/deserializes selected embeddings and converts/validates them in Python. Those extra stages are plausible contributors to the measured gap; the saved run has no stage-level profile establishing which dominates. Database-side scoring or a correctly invalidated local cache are possible experiments, not verified speedups. Production discovery was not a paired arm in this semantic PoC, so its latency/quality cannot be inferred from the flat control.

**Five-community measurement:** the [follow-up](../evals/community_catalog_poc/runs/2026-11-11/five-communities/comparison.md) scores a median 252 workers (25.2% of the catalog) plus 20 representatives: 272 explicit comparisons. Warm median routing lookup is about 187.49 ms, versus 4.70 ms for flat in the same follow-up run. The original two-community median was 76.57 ms in a separate warm run; width timing was not interleaved/paired. The comparison-count target still passes, but lower counts still do not imply lower latency. That follow-up did not split latency stages; scalable/runtime efficiency remains unproven.

**Measured latency diagnosis, 2026-11-11:** [A separate instrumented warm profile](../evals/community_catalog_poc/runs/2026-11-11/five-communities/lookup-profile.json) covers three existing non-direct requests, three repetitions each, with the same five-community policy, model, snapshot, and outputs. Median community ranking/conversion/scoring/sorting took about 0.17 ms, versus 1.25 ms for the cached flat matrix. Routing's combined member-query/Bolt-transfer/Python-decoding/record-materialization stage took about 188.49 ms, array conversion/validation 3.24 ms, and community selection 0.30 ms. Both methods also paid a roughly 4.1 ms exact-name DB probe. Profile total medians were 197.02 ms for routing and 5.31 ms for flat; these are new instrumented timing samples, not replacements for the original evaluation. The combined fetch/materialization stage dominates this implementation's measured lookup overhead; server execution, transfer, and driver decoding are not individually isolated. At the median 252-worker pool, 384-dimensional embeddings require returning 96,768 scalar values per query. Comparison counts represent vector dot products and omit those transfer/conversion costs. Local vector caching or DB-side scoring with only final results transferred remain proposed optimizations requiring separate validation; no runtime speedup or scaling threshold is established.

**Production/benchmark interpretation, 2026-11-11:** hosted embeddings need not be downloaded into the caller on every lookup. A search process can retain vectors in its own server memory, or compute scores in the database and return only final names/scores; Neo4j supports [exact similarity scoring within a query](https://neo4j.com/docs/cypher-manual/current/functions/vector/). Both flat and community approaches can use those execution placements. The current comparison measures a cached in-process flat scan against DB-to-Python member-vector retrieval, so its latency difference combines routing policy with data placement, transfer, and materialization. A remote deployment alone would not remove the existing bulk-fetch overhead or require flat search to adopt it. Reconsider production latency claims only after comparing both methods with matched cache/scoring/transport boundaries and representative scale/load; no such matched experiment or speedup has been established. The separately measured candidate exclusions and owner-recall losses remain valid on the saved synthetic sample.

**Three-representative effort bound:** [Measured results](../evals/community_catalog_poc/runs/2026-11-11/three-representatives/comparison.md) count all 60 representatives plus the selected workers, including repeated exemplar scoring. Original-sample median effort is 312 comparisons and new-authored-sample median is 313; every non-direct sample is at most 314 (31.4% of 1,000), below the snapshot-wide calculated 315 bound. The one-time derived-cache construction takes about 1.12 seconds and 2,000 comparisons, recorded separately. Lookup remains about 186 ms with the same transfer/materialization path; no latency optimization was performed. The user deferred latency from the current demo gate, not from eventual production validation. Passing the quality/search-effort demo does not establish scalable ingestion or runtime speed.

Evidence: [lookup measurements](worker-ranking.md), [`SearchCatalog.build()`](../server/services/execution/ranking.py), [`find_workers()`](../server/services/execution/discovery.py).

<a id="lim-007"></a>
### LIM-007 — Worker identity remains name/filename based

**Status: Deferred.** Dispatch, history filenames and trigger ownership retain exact names. Historical names that share a normalized log filename require manual reconciliation; the application does not guess ownership or merge/split logs. Stable workflow IDs, renaming/alias lifecycle, archival and complete migration are outside the current release.

**Current safeguard:** new collisions are rejected and ambiguous historical ownership is reported/rejected on bounded history reads. **Reconsider when:** a concrete identity/lifecycle need justifies activating reviewed migration work; an archived foundation is not an active runtime feature.

Evidence: [discovery identity rules](worker-discovery.md), [deferred scope](runtime-scope.md), [checkpoint](runtime-scope.md#deferred-storage-checkpoint).

## Context and recovery

<a id="lim-008"></a>
### LIM-008 — Budget estimates are not native token counts

**Status: Open.** Request accounting uses serialized UTF-8 JSON bytes plus framing allowances. It can reject text that a native tokenizer would fit and is not a universal upper bound on provider tokenization. Passing preflight does not guarantee provider acceptance.

**Current safeguard:** explicit estimate labeling, output reservation/headroom, complete-request preflight and separate actual usage observations. **Closure condition:** adopt a supported model-appropriate counter with boundary/multilingual checks, or keep the estimator limitation explicit.

Evidence: [accounting method](context-budgets.md), [budget helper](../server/context_budget.py).

<a id="lim-009"></a>
### LIM-009 — Model allowances require configuration; accounting is text-only

**Status: Designed bound.** Custom model IDs require explicit allowance coverage for all configured model callers. There is no automatic capacity lookup. Structured image/audio/file message content is rejected by the bounded text preflight. Settings/data-root changes require restart; choosing another root does not migrate files.

**Current safeguard:** validation fails instead of guessing another model's capacity or falling back to unbounded input. **Reconsider when:** a concrete multimodal or dynamic-model requirement supplies suitable accounting and configuration validation.

Evidence: [context configuration](context-budgets.md), [settings](../server/config.py), [data-root behavior](../README.md).

<a id="lim-010"></a>
### LIM-010 — Required giant inputs or recent episodes can stop processing

**Status: Designed bound.** Current instructions, necessary latest history, working summaries and tool-call arguments are preserved rather than arbitrarily shortened. If this required floor cannot fit, the next request fails. The outer history reader also has a 128 KiB tail window; a necessary episode outside it can be unavailable. Generic giant combined callbacks are not split into independent notices.

**Current safeguard:** full new content capture, clear errors, bounded recovery and exact draft references. **Reconsider when:** a real blocked task needs explicit source-reference input, user-controlled splitting, or callback partitioning that preserves instruction/confirmation meaning.

Evidence: [outer-context limits](bounded-context.md), [`load_recent_history()` / `ContextBuilder.build()`](../server/context_builder.py).

<a id="lim-011"></a>
### LIM-011 — Recovery is limited and requires deliberate source selection

**Status: Designed bound.** Recovery pages are at most 2 KiB; per outer loop limits include eight calls, 32 KiB accepted responses and 512 KiB read/scan work. `recall_history` searches literal case-sensitive text in one selected log. A scan continuation is not a complete no-match result. The model must choose useful sources/offsets; availability does not ensure it reads every needed detail.

**Current safeguard:** paging/cursors, incomplete-state indicators, owner/mailbox labels and no action authorization from recovered text. **Reconsider when:** measured task failures require better source navigation or another bounded retrieval strategy.

**Source-navigation clarification, 2026-11-13:** `read_result` accepts a reference, byte offset and page limit; it has no content-search query. A known valid offset can retrieve a page in the middle of a saved result, but preserving the full result does not locate an unknown fact within it. Reading a 2 MiB source sequentially would require at least 1,024 maximum-size pages, beyond one loop's eight-call allowance. `recall_history` searches a selected journal rather than arbitrary saved object bodies. This is a source-confirmed interface/work bound clarified during a user walkthrough, not a newly observed production failure or authorization to add a search feature.

Evidence: [recovery contract](context-recovery.md), [recovery handlers](../server/context_recovery.py).

<a id="lim-012"></a>
### LIM-012 — Historical truncation and unknown provenance cannot be reconstructed

**Status: Open.** Older logs may contain normalized or truncated tool outputs whose original was never saved. Legacy mailbox provenance may be unknown. New capture cannot restore missing text or safely assign an old reference to the currently active account.

**Current safeguard:** explicit unavailable/unknown results and account-qualified new sources; exact body actions reject insufficient provenance. **Reconsider when:** original source data and a verified historical mapping exist. A summary/preview is not evidence for reconstructing an exact draft or approval.

Evidence: [capture](content-capture.md), [legacy recall](context-recovery.md), [exact-body validation](draft-references.md).

<a id="lim-013"></a>
### LIM-013 — Inner operations can exhaust their work budgets

**Status: Designed bound.** Search has eight model iterations/Gmail attempts, at most 20 processed emails per query, 100 cached IDs and a 256 KiB cache. Inner source readers limit newly saved source work to 16 MiB. Classification cannot declare unread content unimportant. Summarization allows two model attempts, 16 MiB scan work and 8 MiB individual entries, with bounded generated memory. Exhaustion can leave a task incomplete or summary progress blocked.

**Current safeguard:** preserve received originals, report incomplete work rather than empty success/negative classification, and preserve prior summary/cursor on failure. **Reconsider when:** representative work needs tuned limits or bounded continuation, with task correctness retained.

Evidence: [inner-context contracts](inner-context.md), [search](../server/agents/execution_agent/tasks/search_email/tool.py), [bounded summarizer](../server/services/conversation/summarization/bounded.py).

## Drafts and external actions

<a id="lim-014"></a>
### LIM-014 — Confirmation is agent policy, without a durable approval ledger

**Status: Open.** Draft references and review markers bind exact content; they do not authorize sending. The existing model workflow is responsible for obtaining and respecting user confirmation. The send adapter does not enforce a new persisted approval state tied to the current turn/draft revision.

**Current safeguard:** explicit prompt/tool guidance, full review, ownership/mailbox/integrity checks for real references, and confirmation-flow regressions. **Reconsider when:** stronger enforcement is required; design explicit review/approval identity and action checks rather than treating a content reference as permission.

Evidence: [confirmation contract](draft-references.md), [`gmail_execute_draft()`](../server/agents/execution_agent/tools/gmail.py).

<a id="lim-015"></a>
### LIM-015 — External drafts are not revision-locked after review

**Status: Open.** A saved review preserves its body and recipients, but a draft can be edited externally in Gmail after review. Sending the provider draft ID does not implement a revision lock against those edits.

**Current safeguard:** saved-reference ownership/integrity checks and distinct provider-ID/reference handling. These checks establish the saved source, not an external immutable Gmail revision. **Closure condition:** verify the actual provider draft contents/revision against the reviewed action immediately before sending, with mismatch behavior and race limits documented.

Evidence: [external-edit limit](draft-references.md), [draft loading](../server/draft_content.py), [send adapter](../server/agents/execution_agent/tools/gmail.py).

<a id="lim-016"></a>
### LIM-016 — Exact body adapters have size and format limits

**Status: Designed bound.** Exact sources/bodies resolve up to 8 MiB, draft metadata up to 64 KiB, and JSON Pointers up to 1,024 characters/32 steps. Only supported complete raw sources or pure bodies can be selected. Live body adapters are Gmail text/HTML; there is no separate generic document-writing adapter. A provider response without an exact draft ID cannot be sent by an invented ID.

**Current safeguard:** reject ambiguous, truncated, missing, mismatched or oversized sources before ordinary action validation proceeds. **Reconsider when:** a concrete larger-body/document workflow has an exact-source adapter and appropriate validation.

Evidence: [draft/body references](draft-references.md), [adapter limits](../server/draft_content.py).

## Execution, storage and deployment

<a id="lim-017"></a>
### LIM-017 — No shared admission limit or per-worker run serialization

**Status: Deferred; source confirms current structure.** Dispatch uses asynchronous tasks and per-manager bookkeeping. There is no application-wide active/pending admission bound or whole-run serialization per worker across chat and trigger paths. File/batch locks do not serialize an entire model/tool execution. Overlapping runs can compete for context, resources or external effects.

**Current safeguard:** finite loop limits, worker timeout and scheduler in-flight trigger IDs. **Reconsider when:** mixed load demonstrates pressure or conflicting same-worker runs; any limiter must cover every dispatch path, not just one manager instance.

Evidence: [deferred execution-pressure work](runtime-scope.md), [batch manager](../server/agents/execution_agent/batch_manager.py), [scheduler](../server/services/trigger_scheduler.py).

<a id="lim-018"></a>
### LIM-018 — Overlapping requests can share a batch and delay callbacks

**Status: Open; observed batching design.** A shared manager's current batch accepts overlapping dispatches and emits a combined callback when pending reaches zero. It is not isolated by originating user request. A slow worker or a continuously replenished batch can delay otherwise finished results; a large combined callback can hit LIM-010.

**Current safeguard:** worker timeout and trace links to every originating request. Trace correlation does not change batching semantics. **Reconsider when:** actual delay/mixed-request cases require bounded batch windows or request-scoped delivery.

Evidence: [`_register_pending_execution()` / `_complete_execution()`](../server/agents/execution_agent/batch_manager.py), [outer callback limits](bounded-context.md).

<a id="lim-019"></a>
### LIM-019 — Accepted work and callbacks are not durably replayed

**Status: Deferred.** HTTP 202 means asynchronous acceptance, not completed or durably queued work. Chat tasks, worker pending state, results awaiting callback and callback tasks are process memory. Restart does not provide durable execution/callback replay. Persisted sources and trigger definitions do not supply that guarantee by themselves.

**Current safeguard:** persistent journals/sources, user-visible chat failure handling and stored triggers. **Reconsider when:** a product need requires durable task identities, persisted progress/outbox and restart reconciliation across acceptance, action and delivery.

Evidence: [chat acceptance](../server/services/conversation/chat_handler.py), [batch state/callback scheduling](../server/agents/execution_agent/batch_manager.py), [release limits](agent-overload-release-checks.md).

<a id="lim-020"></a>
### LIM-020 — External effects do not have an exactly-once guarantee

**Status: Open.** Gmail may complete an operation before a timeout, transport error or local persistence failure obscures its outcome. An error does not prove no external effect occurred; a manual/agent retry can duplicate work. Cancelling a local task is not proof an external operation was cancelled.

**Current safeguard:** post-effect persistence failures stop the loop with outcome-check guidance instead of automatically replaying. **Reconsider when:** concrete uncertain/duplicate effects justify idempotency support or an operation-reconciliation protocol using actual provider capabilities.

Evidence: [capture failure semantics](content-capture.md), [draft failure handling](draft-references.md), [Gmail execution](../server/agents/execution_agent/tools/gmail.py).

<a id="lim-021"></a>
### LIM-021 — History clearing is not atomic cancellation of all activity

**Status: Open.** Clearing invalidates content generation and clears stores sequentially. It does not cancel all in-flight external actions, form one transaction across stores, or resolve every legacy/unbound journal race. Gmail connection, seen IDs and timezone are not part of chat-history clearing.

**Current safeguard:** old references fail and generation-bound late content writes/callbacks are rejected; managed cleanup preserves unrelated files. **Reconsider when:** reproduced races or stronger clear semantics require shared admission/cancellation and a coordinated clear boundary across all writers.

Evidence: [clear route](../server/routes/chat.py), [generation handling](content-capture.md), [release clear coverage](agent-overload-release-checks.md).

<a id="lim-022"></a>
### LIM-022 — Local writes do not provide distributed or power-loss guarantees

**Status: Deferred.** Roster/content coordination uses process-local locks and local filesystem operations. Atomic file replacement is not a cross-store transaction, cross-process writer protocol or complete power-loss durability guarantee. Multiple server processes/distributed execution are outside the supported coordination design.

**Current safeguard:** short local locks, atomic JSON replacements and joint content publication. **Reconsider when:** deployment needs multiple writers or crash durability guarantees, with explicit coordination and crash/recovery tests.

Evidence: [discovery storage](worker-discovery.md), [content publication](content-capture.md), [deployment scope](runtime-scope.md).

<a id="lim-023"></a>
### LIM-023 — No automatic retention or hard application-wide resource quotas

**Status: Deferred.** Immutable source files and journals accumulate until explicitly cleared; there is no automatic source expiry/garbage collection policy. Processing/result quotas and prompt limits are not hard download, heap, disk or application-wide spend quotas. An oversized response can be received/saved before its processing budget is rejected.

**Current safeguard:** bounded model requests, cumulative inner work limits, loop/time limits and explicit history clearing. **Reconsider when:** actual storage/resource growth requires a retention/admission policy that preserves the sources needed by active references.

Evidence: [outer resource limits](bounded-context.md), [inner source quotas](inner-context.md), [deferred retention](runtime-scope.md).

<a id="lim-024"></a>
### LIM-024 — File/cursor integrity assumptions and repair remain limited

**Status: Open.** Recovery/summarization cursors assume append-only logs; arbitrary in-place edits preserving file identity/size can evade change detection. Missing/corrupt stores fail explicitly but do not have universal automatic repair. Ordinary paged reads expose the recorded hash without rehashing the entire object on every page; exact draft assembly does verify its complete body.

**Current safeguard:** generation, identity, length and schema checks; exact-body hashes; explicit metadata rebuild. **Reconsider when:** an integrity/repair requirement calls for stronger versioned sources, verification or operator recovery tools.

Evidence: [cursor assumptions and page hashing](context-recovery.md), [summary cursor](inner-context.md), [store validation](../server/content_store.py).

<a id="lim-025"></a>
### LIM-025 — No application-level multi-user isolation/authentication model

**Status: Deferred.** The application uses a shared data root, conversation, roster and active Gmail routing identity. The FastAPI routes do not establish per-user authentication/authorization or tenant storage isolation. Source owner labels distinguish internal workers/mailboxes; they do not authenticate an external caller. Gmail OAuth establishes the integration connection, not a multi-user application access model.

**Current safeguard:** current local/shared-user architecture and internal source/mailbox checks. **Reconsider when:** deployment needs multiple users or remote access, with explicit identity, authorization and per-user store/integration isolation.

Evidence: [deployment scope](runtime-scope.md), [application/routes](../server/app.py), [active account](../server/services/gmail/client.py), [shared data root](../server/data_paths.py).

<a id="lim-026"></a>
### LIM-026 — Watcher coverage, retries and notification delivery are best effort

**Status: Open.** The watcher inspects a bounded recent fetch (at most 50 messages), skips warmup messages and retains a bounded seen set (default 300 IDs). Incomplete-classification retry state is in memory and does not guarantee later retries after restart or lookback/fetch expiry. Notification delivery is best effort; classified messages can be marked seen even when callback delivery fails, without a durable notification outbox.

**Current safeguard:** strict classification distinguishes unavailable from negative, failed classifications stay unseen in the current window, and seen IDs qualify accounts. **Reconsider when:** missed/repeated alerts require durable retry/outbox state and explicit delivery acknowledgment or broader mailbox continuation.

Evidence: [watcher limits](inner-context.md), [polling and dispatch](../server/services/gmail/importance_watcher.py), [seen store](../server/services/gmail/seen_store.py).

<a id="lim-027"></a>
### LIM-027 — Chat delivery and UI completion tracking remain unbounded/heuristic

**Status: Open; source inspection.** `to_chat_messages()` reads the full conversation for history responses, and the UI repeatedly fetches it; model-context bounds do not bound HTTP response size or browser rendering. The UI identifies completion by matching user text and the last assistant message, rather than a per-request completion ID, and stops its short loading loop after 30 attempts while regular polling continues.

**Current safeguard:** asynchronous acceptance, regular polling and exact history rendering. **Reconsider when:** large-history performance or overlapping/repeated identical submissions need paged/incremental delivery and explicit request-status correlation. Current component tests do not measure browser scroll performance (LIM-029).

Evidence: [history serialization](../server/services/conversation/log.py), [frontend polling](../web/app/page.tsx), [release UI scope](agent-overload-release-checks.md).

<a id="lim-028"></a>
### LIM-028 — Legacy opt-outs restore unbounded prompt behavior

**Status: Designed bound.** `OPENPOKE_WORKER_DISCOVERY=legacy` restores the full roster; `OPENPOKE_CONTEXT_STRATEGY=legacy` restores original context behavior and disables bounded capture/recovery paths. Large inputs may exceed provider limits. The two flags are independent, and existing explicit legacy settings survive default promotion.

**Current safeguard:** bounded defaults, explicit opt-out configuration, preserved data and no silent bounded-to-unbounded fallback. **Reconsider when:** retiring comparison compatibility or changing defaults, with existing saved-data/reference compatibility verified.

Evidence: [opt-out guide](agent-overload-release-checks.md), [settings](../server/config.py), [capture scope](../server/content_store.py).

## Evidence and measurement

<a id="lim-029"></a>
### LIM-029 — Live quality and application coverage are limited

**Status: Evidence gap.** Live discovery/context comparisons remain small authored synthetic samples. The original comparison and focused draft recheck are preserved; the expanded 2026-11-13 rerun covers all currently supported cases but fails its overall gate. Alternative rankers have no new live-model validation. Most regressions use scripted model responses and fake Gmail. ASGI/component checks do not automate browser clicks, visual scrolling, live OAuth, or periodic production-mailbox behavior.

**Current safeguard:** separate retrieval, routing and actual fake tool-effect grades; preserved failures; explicit mock/live labels and held-out synthetic splits. **Closure condition:** representative additional live/provider/browser evidence for the specific claim being made, with controls and limitations retained. Passing plumbing tests alone does not establish universal task correctness.

**Full active bounded rerun, 2026-11-13:** [the report and complete scenario maps](../evals/agent_overload/validation_reports/2026-11-13-full-suite/report.md) retain 272 passing backend tests across 23 modules, five passing frontend checks, clean lint/type checking and a passing production build. Baseline capture, scripted agent comparisons, all 144 original retrieval rows and all 4,200 discovery-v2 rows also complete without runtime failures; repeated frozen inputs are not new independent quality samples. The v2 recall results repeat the first run and its 100% candidate false-positive rate on the 15 evaluation no-match requests remains. Complete offline evidence archives and live traces were read back against artifact hashes. The expanded live run executes 18 rows: eight supported routing cases plus the approved-draft flow in both arms, at zero/100 workers. Both arms have 7/9 correct routing actions/owner sets; bounded additionally fails one turn after correct dispatch by exhausting eight iterations. Both exact fake draft effects and callbacks pass, but the overall live gate fails. The original six-case subset is present (legacy 6/6, bounded 5/6 correct routes), rather than being replaced by the earlier focused recheck. The dormant-worker trace verifies absence from the recent list, a real model-chosen find_worker call, and accepted exact-owner dispatch; its worker remains a recorder. All six unsupported fixture IDs remain outside the paired harness, and recovery/clarification quality is not graded. The report distinguishes fixture-action mismatches from general production correctness and retains complete requests/decisions, usage, fake effects and artifact hashes. Reconsider with representative repeated live evidence and an explicitly extended rubric where those additional behaviors matter; no broad evidence limitation is closed.

**Varied discovery benchmark, 2026-11-12:** the user-authorized [discovery-v2 benchmark](discovery-quality-benchmark.md) adds 100 explicitly authored workers across 20 domains/task families, 200 requests (50 development, 150 evaluation), and three fixed larger-catalog draws. All 100 workers are targets; complete families and their paraphrases stay in one split. Separate source/judgment files and seven canonical catalog hashes are frozen before scoring. Twelve new integrity, nesting, leakage, grading, uncertainty and CLI checks passed within the 267-test backend suite. This improves synthetic variety, not independent review or production representativeness: the implementation author also wrote the cases; independent semantic review is pending; families share a five-role structure; answerable requests explicitly name a protected project; background expansion remains templated. Primary metrics exclude deliberately unavailable metadata links, distinguish no-match denominators and average draws within each request before family-cluster intervals. The benchmark is offline-only and does not establish live query formulation, clarification quality or external task effects. Reconsider this gap after independent label review and representative additional families/requests, including requests without explicit project names; broader limitations remain open.

The [retained first v2 run](../evals/agent_overload/discovery_comparisons/2026-11-12/README.md) completed 4,200 rows without runtime failures, with complete catalog snapshots, separate labels, source fingerprints and byte-verified artifacts. It is a new offline baseline rather than independent validation or a live-model comparison. Authorship provenance was clarified after the run began without changing any data-file or catalog hash; the initial manifest and clarification are both retained. No broader evidence limitation is closed.

**Bounded coverage audit, 2026-11-12:** the [current evaluation inventory](evaluation.md#current-bounded-regression-and-scenario-coverage) records a passing local rerun of 255 backend tests and five frontend checks, without new live-model or real Gmail calls. The 14 routing fixtures supply 40 baseline prompt captures, but the paired harness supports eight routing case IDs and always appends a separate 100-worker approved-draft flow. Six fixture IDs are not selectable in that comparison. The [grader](../evals/agent_overload/contracts.py) checks routing action and exact owner set; it does not evaluate fixture `required_recovery`/`expected_open_obligations`, clarification quality, or general task completion. Routing-only workers are replaced by a [dispatch recorder](../evals/agent_overload/comparison.py); the separate draft flow grades actual fake mailbox effects. Defining expectations, passing related contract tests, or capturing prompts does not establish live behavior for those expectations. Reconsider this boundary when extending the grader or adding retained scenario-specific live evidence; the broader evidence gap remains open.

**Roster-scale presentation clarification, 2026-11-12:** the [discovery size table](worker-discovery.md#verification) repeats one exact-name query (`Alice lunch`) at 100/1,000/10,000 synthetic workers. The [existing scale test](../server/tests/test_worker_discovery.py) asserts the target ranks first at all three sizes; a focused isolated rerun passed on 2026-11-12 without model/Gmail calls. The [roster-scale evidence](evaluation.md#roster-scale-checks) labels this 3/3 exact-name lookup success alongside up to 99.77% less initial roster text, not general 100% recall or complete-request/token savings. The broader nine-request synthetic evaluation remains 94.44% mean owner recall@5; repeating one query at several sizes is not independent quality evidence. Historical reports and limitation status are unchanged.

**Graph evidence, 2026-11-11:** the [standalone community-routing demonstration](../evals/community_catalog_poc/README.md) is implemented and evaluated with the actual pinned local embedding model and Neo4j 5.26.0. [Two numerical checks](../evals/community_catalog_poc/test_demo.py) and [DB smoke checks](../evals/community_catalog_poc/runs/2026-11-11/smoke.json) passed. The [saved report](../evals/community_catalog_poc/runs/2026-11-11/evaluation/report.md) keeps relevant-owner recall, vector-neighbor overlap, explicit comparisons, and warm latency separate. The joint demo target failed because owner recall dropped; no parameter tuning or application integration followed. Existing historical ranking/comparison reports remain unchanged.

**PoC scope:** the [completed minimal evaluation](community-catalog.md) reuses the existing 16 authored queries and one catalog size, with two numerical checks and a real DB smoke run. Fourteen cases have nonempty relevance labels, nine in the evaluation split; timing repetitions are not extra quality examples. This is not a new independent holdout. It measures retrieval rather than live-agent behavior or production response packing. Semantic abstention/no-match detection is excluded; the two no-match outputs are diagnostic only and excluded from recall denominators. Failure-path checks also confirm unavailable DB runs retain all 16 cases and 144 failed samples with unavailable quality aggregates; these checks establish error handling, not semantic quality.

**ANN evidence gap:** low global-ANN recall is observed, but its cause has not been isolated. [The implementation](../evals/community_catalog_poc/demo.py) specifies dimensions/cosine and requests exactly five approximate neighbors; it does not evaluate broader candidate retrieval, exact rescoring, or alternative index settings. This single configuration does not establish ANN's general quality or an advantage for community graphs. Diagnose approximation/index behavior separately on development cases before adopting ANN as a recall safeguard; retain unknown internal comparison counts and use fresh evaluation evidence for any changed settings.

**Follow-up evidence boundary:** the [five-community repeat](../evals/community_catalog_poc/runs/2026-11-11/five-communities/report.md) reuses all 16 existing authored cases after the original failures were inspected; its nine nonempty-relevance evaluation cases are not a fresh holdout. All 144 timing samples succeed and [validation](../evals/community_catalog_poc/runs/2026-11-11/five-communities/comparison.json) confirms unchanged snapshot/original artifacts, identical flat names/scores, five selected groups per non-direct sample, and member-union counts. This supports the recorded diagnostic comparison, not production promotion or an independently validated policy. Original reports retain their failures and results.

**Three-representative evidence:** [The rule and ten new queries](../evals/community_catalog_poc/runs/2026-11-11/three-representatives/protocol.json) were frozen before prototype quality measurement, with no subsequent sweep or tuning. [The original-sample run](../evals/community_catalog_poc/runs/2026-11-11/three-representatives/existing/report.md) has 144 timing samples and [the new-authored run](../evals/community_catalog_poc/runs/2026-11-11/three-representatives/fresh/report.md) adds 90; each has nine judged evaluation requests, and timing repetitions are not additional quality cases. Four numerical checks and live DB/cache/provenance checks pass. The same assistant authored the ten new queries after inspecting prior failures, targeting the same seven owners, so this is a fresh-wording confirmation rather than an independently authored or production holdout. Post-run inspection finds all seven core owners among the 40 selected member exemplars, against 993 repetitive synthetic distractors; this favorable fixture property limits generalization. The revised demo gates pass on these synthetic samples only. Existing reports and original snapshot hashes are preserved, and live action/agent quality remains unmeasured.

**Graph inspection clarification, 2026-11-12:** the [fixture generator](../server/tests/fixtures/catalogs.py) cycles four people and five topics with distinct project IDs, producing repetitive synthetic worker profiles and homogeneous-looking groups. A read-only check of the local PoC database confirmed 1,000 workers and 20 communities; the example's global `LIMIT 100` displayed only two groups (51 and 49 rows). Query-time `--communities 5` selects a search subset, not the graph's total community count. The [updated graph example](../evals/community_catalog_poc/README.md#verification-and-presentation) returns three sample workers per community and was checked against all 20 groups. This corrects display interpretation only; it does not add catalog diversity, establish live-agent behavior, or close the representative-evidence gap.

**Presentation checkpoint:** the user accepted this result for future demos. [The experiment guide](community-catalog.md) records the approved configuration, milestone/evidence links, and claim boundaries; the [experiment README](../evals/community_catalog_poc/README.md) retains reproducible commands. The local recording plan remains ignored. Its local command rehearsal reproduced exact-name bypass and the combined request's centroid miss/three-representative recovery (270/313 comparisons), with four mechanism checks passing. The [evaluation guide](evaluation.md) preserves the distinction between current production paths and standalone retrieval, scripted checks and live model decisions, and historical results and a new demonstration; the confirmation sample remains non-independent. The rehearsal is preparation evidence on the same snapshot, not a new aggregate quality or latency study. Presentation readiness does not change this entry's evidence-gap status or close the broader retrieval/efficiency limitations.

Evidence: [live comparison](agent-overload-comparison.md), [release coverage](agent-overload-release-checks.md), [ranking evidence](worker-ranking.md), [fixture scope](../server/tests/fixtures/README.md).

<a id="lim-030"></a>
### LIM-030 — Efficiency gains and complete persistent measurement are unproven

**Status: Evidence gap.** A smaller roster is not proof of lower total calls/tokens/cost. The original 100-worker live bounded arm used 25 calls and 143,212 input tokens versus legacy's 21 calls and 106,344; reported cost was also higher. Pacing contributes to recorded elapsed time. Missing provider usage/cost remains unknown; historical telemetry cannot gain missing provenance. Logging has no built-in dedicated durable telemetry store.

**Expanded live measurement, 2026-11-13:** the [18-row rerun](../evals/agent_overload/validation_reports/2026-11-13-full-suite/report.md) uses 61 live requests: legacy 28 calls / 139,566 input tokens / 1,950 output tokens / returned cost 0.447948; bounded 33 / 201,246 / 3,048 / 0.649458. All calls return valid usage/cost. Both fake draft effects pass, but routing/turn failures keep the overall gate failed; this is not a task-correct efficiency win. Timings include deliberate 3.1-second pacing, and offline lookup work overlaps part of the live run. The sample is expanded relative to the original six cases, so totals are not a matched historical performance trend. Source estimates remain separate from actual provider usage; broader cost/latency and persistent-measurement gaps remain open.

**Basic-solution recording clarification, 2026-11-12:** the [evaluation analysis](evaluation.md#provider-usage-in-the-original-paired-run) distinguishes the roster's 4,702-to-1,083 **character** reduction (76.97%) from actual provider-reported input tokens, which increased by 36,868 (34.67%) in that original paired run. These percentages are arithmetic derived from the retained [comparison observations](agent-overload-comparison.md), not new measurements. The later focused draft recheck does not establish post-fix six-case token savings; the broader evidence gap remains open.

**Initial-request trace analysis, 2026-11-12:** the [usage evidence notes](evaluation.md#provider-usage-in-the-original-paired-run) also calculate means from actual first-request `usage.prompt_tokens` in all six retained [live case pairs](../evals/agent_overload/comparisons/2026-11-09/results.json.gz): legacy 4,967.8333 versus bounded 5,369, an 8.0753% increase, with every bounded first request larger. These complete requests include strategy instructions/tool schemas and precede retrieved results; the combined-strategy comparison does not isolate the roster's token cost. This read-only derivation makes no new model calls, preserves historical reports, and confirms that initial-request token savings are not demonstrated at the tested 100-worker size. The paired quality result is 6/6 correct routing actions/owners in each arm, not a paired Recall@5 measurement; the separate lexical recall result must not be substituted for legacy-versus-bounded recall.

**Payload-overhead explanation, 2026-11-12:** the [request-component breakdown](evaluation.md#request-components) inspects the original `alice-contract` first-request pair. The roster shrinks by 3,619 characters, but system instructions grow by 3,641 and compact tool-schema JSON by 2,715 (four to seven tools, plus the expanded draft schema); actual complete-request input grows from 4,951 to 5,343 provider tokens. Legacy sends names only, while bounded recent entries include metadata and retrieved matches arrive in later tool results. Component sizes are character measurements, not native-token attribution. This explains observed additional payload without establishing a larger-catalog token crossover or isolating discovery from context-policy changes. Historical reports remain unchanged; no new model calls or runtime changes were made.

**Current safeguard:** provider measurements stay separate from estimates, zero stays zero, available subtotals are labeled, and original reports are preserved. **Closure condition:** representative paired task-correct comparisons with end-to-end usage/latency and configured log retention for any operational claim.

**Varied offline measurement, 2026-11-12:** [discovery-v2](discovery-quality-benchmark.md) records fresh-read backend lookup timing, ranking-only timing and separately traced Python preparation allocations for seven frozen catalog snapshots. The retained first run uses one timing repetition per row and three larger-catalog background draws; these are authored workload measurements, not live/provider costs, cold-disk guarantees, load testing or extra independent quality cases. Changed metadata/workload makes direct timing or accuracy comparison with old v1 reports inappropriate. No efficiency claim about the combined application or default promotion follows; this evidence gap remains open.

**PoC scope:** the [completed community experiment](../evals/community_catalog_poc/runs/2026-11-11/evaluation/report.md) reports warm backend lookup timing, shared query embedding time, and offline build time separately. It counts representative comparisons as well as worker scoring; ANN internal comparison counts remain unknown. Evaluation median lookup was about 3.95 ms for flat vectors, 5.54 ms for ANN, and 76.57 ms for community routing. Lower explicit comparison count did not produce lower lookup latency in this run. The successful build attempt took about 15.21 seconds; [setup notes](../evals/community_catalog_poc/runs/2026-11-11/smoke.json) disclose earlier failed setup/partial model download outside that timing. Three timed repetitions per case and this small authored sample do not establish production performance. No lower application-wide latency/provider-cost claim is supported, and warm snapshot timings are not directly comparable to historical fresh-JSON lookup results.

**Current demo boundary:** the [three-representative result](../evals/community_catalog_poc/runs/2026-11-11/three-representatives/comparison.md) meets the user's recall/comparison criteria, with latency explicitly outside the gate. It retains offline setup measurements and the slower DB-transfer lookup path. The [evaluation guide](evaluation.md) and [experiment guide](community-catalog.md) present the 314/1,000 comparison maximum alongside the slower measured lookup and preserve the original bounded arm's higher total calls/tokens/reported cost. Warm lookup timings exclude process/model loading. The [evidence interpretation](evaluation.md#interpreting-the-evidence) retains the non-independent synthetic-sample bounds, labels community routing as standalone, and separates retrieval metrics from live routing/fake-effect checks and scripted application validation. This is neither an end-to-end efficiency result nor a closure of the production measurement gap.

Evidence: [comparison metrics](agent-overload-comparison.md), [observation semantics](observability.md), [logging configuration](../server/logging_config.py).

## Resolved findings retained for regression tracking

<a id="lim-031"></a>
### LIM-031 — Provider draft ID confused with saved-content reference

**Status: Resolved for the observed case, 2026-11-09.** The first live bounded draft send failed when the model used a Gmail ID as `draft_reference.reference` and inferred expiry. Schema/prompt guidance and malformed-selector validation now distinguish IDs; three focused regressions and the live affected-scenario recheck passed. This does not eliminate general model mistakes (LIM-002) or establish approval enforcement (LIM-014).

Evidence: [failure, fix and live recheck](agent-overload-comparison.md), [draft identifier rules](draft-references.md).

<a id="lim-032"></a>
### LIM-032 — Frontend decoded literal escape sequences twice

**Status: Resolved, 2026-11-09.** History mapping now preserves parsed `message.content` rather than rewriting literal backslash sequences. Large exact-body history/proxy/component checks passed. Retain these checks when changing frontend message decoding.

Evidence: [release findings](agent-overload-release-checks.md), [history mapper](../web/components/chat/history.ts), [frontend regressions](../web/tests/chat-history.test.mjs).

<a id="lim-033"></a>
### LIM-033 — Trigger-store SQLite connections remained open

**Status: Resolved, 2026-11-09.** The connection context now closes in `finally`, including statement failure. Application/resource checks verify release of actual SQLite connections. This fixes connection lifetime, not distributed trigger execution or durable job replay.

Evidence: [release findings](agent-overload-release-checks.md), [trigger store](../server/services/triggers/store.py), [application regressions](../server/tests/test_bounded_application.py).

<a id="lim-034"></a>
### LIM-034 — Cancelled background tasks could abort evaluation draining

**Status: Resolved for the reproduced cancelled-child failure, 2026-11-12.** The evaluation task capture also records dependency tasks. Awaiting them with ordinary `asyncio.gather()` propagated a cancelled child's `CancelledError` out of the paired runner, whose `except Exception` does not catch cancellation. A user-reported live comparison stopped before saving its in-progress row; its exact cancelled task was not identified. A local, network-free reproducer confirmed the shared drain helper could abort solely because an already-cancelled background child was captured.

**Fix and safeguards:** draining now collects child outcomes with `return_exceptions=True`, skips cancelled children, and re-raises actual task exceptions. Cancellation of the draining evaluation itself still propagates and cancels pending work; case deadlines still time out. Five isolated regressions cover cancelled children with continuing worker/callback work, a genuine failure alongside cancellation, evaluation cancellation/cleanup, timeout/cleanup, and an exception object returned as a value. These checks passed locally; no paid live recheck was made. Application grading and historical evidence are unchanged, and the broader live-evidence gap remains open under LIM-029.

**Reopen when:** a captured child cancellation still aborts an otherwise completing evaluation, a genuine task failure or evaluation cancellation is suppressed, or another interrupted-run evidence path requires a separate fix.

Evidence: [shared task capture/drain](../evals/agent_overload/engine.py), [cancellation regressions](../server/tests/test_agent_overload_tasks.py), [paired runner](../evals/agent_overload/comparison.py).

Validation: `python server/tests/run_tests.py` passed all **272 backend tests** on 2026-11-12, including the five new cancellation regressions and retained scripted comparison/application checks. This is local regression evidence, not a new live-model comparison.

## Change record

- 2026-11-13: Clarified LIM-011 during the context-overload walkthrough: lossless source preservation and bounded page access do not guarantee automatic discovery of an unknown fact in a large result. Recorded the existing offset-only object reader and per-loop navigation bound; no runtime behavior, limitation status or historical evidence changed.
- 2026-11-11: Created the central register from active feature/release/ranking documentation and current runtime inspection; explicitly recorded same-purpose/different-name workers as LIM-001. Retained three fixed findings separately from the 30 current limitations/bounds/evidence gaps.
- 2026-11-11: Linked the graph-demo design discussion to existing LIM-002, LIM-003, LIM-004, and LIM-029. Preserved their states and the original comparison evidence; no graph capability or improvement was marked implemented or resolved.
- 2026-11-11: Clarified the proposed graph as a community-based catalog index rather than a work/dependency graph. Updated LIM-001, LIM-002, LIM-003, LIM-004, LIM-006, and LIM-029 with caching/indexing controls, community-boundary risks, and the separation of grouping from merging. No runtime feature or limitation status changed.
- 2026-11-11: Narrowed implementation/evaluation planning to a standalone frozen-catalog PoC with zero application-code changes. Recorded its full-rebuild, manual-widening, small-sample, no-abstention, and warm-timing bounds under LIM-002, LIM-004, LIM-006, LIM-029, and LIM-030; no experiment ran and no limitation was closed.
- 2026-11-11: Implemented the isolated community catalog PoC and recorded actual local-model/Neo4j results, numerical and DB smoke checks, and explicit failure handling under LIM-002, LIM-003, LIM-004, LIM-006, LIM-029, and LIM-030. The comparison-count target passed; the owner-recall target failed and routing was slower. Retained fixed settings and historical reports, with no application integration or limitation closure.
- 2026-11-11: Diagnosed representative-ranking exclusions using the original frozen snapshot. Recorded exact owner/community rank examples, the single-centroid/exclusive-membership bounds, unprofiled latency attribution, and the unisolated ANN cause under LIM-003, LIM-006, and LIM-029. Changed no retrieval settings or application code, and preserved all original evaluation reports.
- 2026-11-11: Ran the user-requested five-community follow-up on the unchanged frozen snapshot. Updated LIM-003, LIM-006, and LIM-029 with improved candidate/owner coverage, the remaining gate/ranking misses, 272 explicit comparisons, slower measured lookup, and the reused-query evidence boundary. Added an evaluator width flag and preserved original artifact hashes; no model change, further tuning, integration, or limitation closure.
- 2026-11-11: Profiled three existing requests to explain the lookup slowdown. LIM-006 now distinguishes fast vector ranking from the dominant combined member-query/transfer/decoding stage, while keeping its internal attribution and production scaling unproven. Preserved prior reports and snapshot hashes; no source-code, routing-policy, or model changes.
- 2026-11-11: Clarified LIM-006's production/benchmark boundary: server-hosted vectors can be cached or scored near storage for either retrieval policy. Recorded that the observed latency combines algorithm and execution placement, while retaining the actual recall losses and the requirement for matched latency evidence. No new experiment or runtime change.
- 2026-11-11: Recorded the user's proposed three-percentage-point/one-third-comparisons demo target and a label-free three-representative routing experiment under LIM-003 and the PoC plan. Distinguished the calculated 315-comparison bound from unmeasured recall, retained the small-sample caveat and historical gates, and made no implementation/evaluation change.
- 2026-11-11: Implemented and ran the authorized three-representative policy with a frozen rule and ten prewritten confirmation queries. Updated LIM-003, LIM-004, LIM-006, LIM-029, and LIM-030 with the recovered observed case, matching flat recall, per-request maximum 314 comparisons, derived-cache checks, and fixture/authoring/latency bounds. Preserved earlier results and kept all broader limitations open; no model change, tuning sweep, or application integration.
- 2026-11-11: Saved the user-accepted demo checkpoint in a dedicated progress/runbook document, linked from the plan, experiment README, and LIM-029. Retained the numerical results, configuration, reproduction/presentation commands, and outstanding caveats; no new experiment or limitation status change.
- 2026-11-11: Added the single-file five-minute end-to-end recording plan and linked it under LIM-029/LIM-030. Rehearsed its three local DB/model queries and four mechanism checks on the retained snapshot. Kept production, standalone retrieval, scripted effects and live-model evidence distinct; retained the non-independent sample and comparison-count/latency boundaries. No new aggregate evaluation was run, limitation closed, or deferred feature implemented.

- 2026-11-12: Curated tracked documentation into system/evaluation guides; retained planning notes and deferred checkpoints locally under ignore rules. Redirected evidence links to published guides and the frozen protocol, preserved the prior recording analysis and historical comparison reports, and documented checkpoint recovery from Git history. No runtime behavior, measured result, limitation ID, or status changed.
