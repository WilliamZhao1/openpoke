# Execution Agent Overload: Implementation Plan

Date: 2026-11-07  
Updated: 2026-11-08  
Status: Proposed implementation; no runtime changes are included in this document.  
Scope: The current OpenPoke checkout, preserving the Interaction Agent / Execution Agent architecture.

## 1. Outcome and problem

OpenPoke should remember a growing amount of work while sending a small, relevant, recoverable working context to each model call.

Today, the Interaction Agent receives every execution-agent name on each turn. It chooses a name to reuse, or supplies a new name to create an agent. A selected execution agent then loads its own logged history. As usage grows, both the directory and the histories become harder to use. Missing an existing worker can create duplicates, which makes subsequent routing harder still. Large emails, tool results, pasted messages, and worker callbacks can independently overflow context even after the directory is shortened.

The implementation must improve:

- **Discovery:** Find the workflow that owns earlier work, including dormant work.
- **Continuity:** Preserve identities, commitments, drafts, triggers, and access to source history.
- **Context size:** Bound every model request without silently deleting the omitted source material.
- **Execution pressure:** Bound running and queued work across user requests and background services.
- **Evidence:** Measure task success and incorrect reuse alongside tokens, latency, and cost.

This is an incremental engineering plan. A new model, external vector service, knowledge graph, stateless-worker rewrite, and evaluation UI are outside the first release.

The first release is the bounded, recoverable baseline in Phases 0-5. After that release, Phase 7 implements and evaluates a knowledge graph retrieval strategy. It can proceed independently of the optional semantic retrieval work in Phase 6. The graph experiment is planned work; enabling it by default depends on comparative evidence.

The 2026-11-08 revision incorporates the most directly useful lessons from Akshay Rakheja's implementation: event-derived activity cards, explicit current-turn intent, backend-validated routing decisions, and evidence-aware evaluation. It does not adopt whole-roster model scoring, automatic creation on scorer failure, or mandatory third-party routing APIs.

## 2. Terms and current implementation

| Term                     | Meaning in this plan                                                                                                                     |
| ------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------- |
| Interaction Agent        | The model-driven program that talks to the user and delegates work.                                                                      |
| Execution Agent / worker | The program that activates with its own instructions and saved history to perform work.                                                  |
| Workflow                 | One continuing job, such as arranging lunch with Alice, including later follow-ups. Initially, one existing worker maps to one workflow. |
| Run                      | One activation of a worker. Finishing a run does not necessarily finish its workflow.                                                    |
| Registry                 | The searchable directory of workflow identities and descriptions.                                                                        |
| Context                  | The information sent to a model for one call. Persistent storage is separate from context.                                               |
| Source reference         | An immutable identifier through which original content can be retrieved or passed to a tool.                                             |
| Activity card            | A bounded, versioned view of a workflow's responsibility, recent outcomes, relevant entities, and outstanding commitments.               |
| Routing intent           | The current task and its resolved references, with the conversation evidence needed to interpret it.                                     |
| Knowledge graph strategy | Retrieval through typed relationships among existing entities, workflows, and resources, added after the baseline.                       |

Relevant integration points in this checkout:

| Existing file | Current behavior / required integration |
| --- | --- |
| `server/agents/interaction_agent/agent.py` | Renders the entire name roster into each message. Replace this with a bounded recent-work list and discovery guidance. |
| `server/agents/interaction_agent/tools.py` | `send_message_to_agent` creates or reuses by name and starts asynchronous work. Add explicit lookup, creation, and resume contracts. |
| `server/agents/interaction_agent/runtime.py` | Handles user turns and worker callbacks. Add structured routing context, bounded history, and per-turn limits. |
| `server/services/execution/roster.py` | Stores a JSON list of names. Introduce a compatibility adapter over stable workflow records. |
| `server/services/execution/log_store.py` | Stores logs in name-derived filenames. Import and index these records without destructive rotation. |
| `server/agents/execution_agent/agent.py` | Defaults to loading the full execution transcript. Build a bounded context with recoverable references. |
| `server/agents/execution_agent/runtime.py` | Executes tool loops and records results. Persist full new results before rendering bounded model-visible versions. |
| `server/agents/execution_agent/batch_manager.py` | Keeps process-local pending work and one current batch. Add explicit turn/run correlation and shared admission control. |
| `server/services/trigger_scheduler.py` | Creates a new batch manager for each fired trigger. Route scheduled work through the same execution service as chat work. |
| `server/services/triggers/` | Persists trigger ownership as `agent_name`. Add stable workflow ownership with a migration adapter. |
| `server/services/conversation/` | Provides conversation logs and count-based summarization. Preserve compatibility while adding stable entry IDs and indexed recall. |
| `server/agents/execution_agent/tasks/search_email/` | The search sub-agent can accumulate large email results. Apply previews and references within this loop too. |
| `server/openrouter_client/client.py` | Builds the final provider payload. Add request-wide accounting and preflight validation. |
| `server/routes/chat.py` | History clearing deletes logs, roster, and triggers. Extend clearing to all new stores and coordinate it with background work. |
| `server/app.py` | Starts background services. Run migration and recovery checks before polling or accepting new work. |

Two existing limitations must be accounted for: worker tool responses are currently logged in truncated form, and different names can produce the same filename slug. Migration cannot reconstruct source text that was never saved or reliably separate a historically shared log.

## 3. Design decisions and invariants

1. Keep the current agent roles. Introduce stable workflow IDs behind the existing name-based interface during migration.
2. Use a local SQLite store and indexed lexical search for the first release. Use Python's `sqlite3`; FTS5 is available in the inspected development virtual environment. Probe for support at startup and provide an actionable configuration error if a deployment lacks it.
3. Keep mailbox references qualified by provider and account. The initial product remains a single local profile; this plan does not introduce a multi-user authentication system. A legacy reference with unknown account provenance must not be silently reassigned to a different connected mailbox.
4. An exact, validated workflow/draft/trigger reference takes precedence over similarity ranking. A thread may support multiple workflows; require inspection when ownership is genuinely ambiguous.
5. Excluding information from context never deletes its stored source. All previews and summaries carry usable references.
6. Workflow state is separate from run state. A successful draft-creation run may leave a workflow waiting for approval.
7. Record resource IDs from structured tool responses, not regular expressions over worker prose. New resource references supplement previous references rather than replacing them.
8. Search remains available across active, completed, and archived workflows. Recency changes ranking and cache residency, not historical discoverability.
9. Every exposed tool schema has one executable handler. Bind workflow/run state through a tool session rather than adding unrelated special cases to the runtime.
10. Never infer permission to send from a successful lookup or a similarity score. Preserve the existing draft-review and confirmation behavior, including previously supplied valid confirmations.
11. Use bounded queues and a shared execution service. A semaphore attached to an individual batch-manager instance is insufficient for chat plus scheduled work.
12. Treat provider token usage and external side effects as observable evidence. Do not promise exactly-once email sending when the upstream API cannot guarantee it.
13. Resolve the current task separately from unrelated conversation history. A topic switch must not inherit the previous worker merely because it was recently active.
14. Backend checks bind a routing decision to its turn/subtask, evidence, scope, and workflow revisions. The model can request another lookup to revise that decision; it cannot bypass the checks by selecting a different ID.
15. Retrieval failure and ambiguous ownership are not evidence that new work has no owner. Preserve distinct complete/partial/unavailable retrieval states and explicit abstention.
16. A future graph is a rebuildable retrieval projection over source-backed state. Graph links neither grant execution permission nor replace current workflow/approval records.

## 4. Persistent state and service contracts

### 4.1 Storage model

Introduce `server/services/workflows/` with models, storage, migrations, registry/search services, and compatibility adapters. Store application state beneath a configurable data root, with a default matching the existing `server/data/` location. Inject this root in tests so no test reads a user's mailbox state or modifies real history.

Use the following logical tables; the implementation can combine small tables when it preserves their constraints:

| Table | Essential information and constraints |
| --- | --- |
| `workflows` | Immutable UUID, scope, display name, purpose, current summary, workflow status, created/last-activity timestamps, archive timestamp, revision. |
| `workflow_aliases` | Exact legacy name to workflow ID mapping, unique within scope. Display-name changes preserve old aliases. |
| `workflow_entities` | Contacts, topics, and other structured search fields, with provenance and optional account qualification. |
| `resource_refs` | Provider, account, resource type, resource ID, related workflow, relationship, and source event. Preserve older IDs. Explicit ownership rules can be unique; incidental references are not globally exclusive. |
| `events` | Immutable event ID, conversation/workflow/run/turn IDs where applicable, sequence, kind, timestamp, source reference, and complete newly captured payload. Support indexed and paged reads. |
| `source_objects` | Immutable full result/document content, content hash, media type, scope, provenance, and size. Model previews refer here rather than copying large payloads. |
| `runs` | Run/request/turn/batch IDs, workflow ID, queued/running/succeeded/failed/interrupted state, timestamps, deadline, and action/recovery evidence. |
| `activity_records` | Versioned execution outcomes linked to run and source events, including structured actions, resource bindings, obligation changes, and outcome provenance. May be a typed projection of `events` rather than a separate physical table. |
| `routing_decisions` | Decision/intent/turn/subtask IDs, action, eligible workflow IDs and revisions, retrieval status, evidence references, and supersession information. Backend-owned. |
| `approval_records` | The approved draft reference/version, recipient/content fingerprint, originating confirmation, and send outcome. |
| `migration_state` | Schema version, source fingerprints/import progress, legacy-entry mappings, and validation results. |

Maintain FTS5 indexes over compact workflow search documents and recallable event text. Use exact indexed columns for IDs and account boundaries. Maintain indexes in the same transaction as their source records; make rebuilding them a supported maintenance operation.

The initial workflow states are `open`, `waiting_for_approval`, `waiting_for_external_event`, `completed`, and `cancelled`. Archival is a separate storage flag. Failure belongs to a run and can leave its workflow open with an error requiring attention.

Immutable source IDs must survive restart and summary updates. Existing conversation indices can become scoped legacy aliases; array positions are not the new reference format. Clearing history advances a data-generation identifier so old IDs and callbacks cannot attach to newly created records.

### 4.2 Model-visible tools

Introduce these contracts behind the new context strategy:

| Tool | Contract |
| --- | --- |
| `find_worker(query, filters, limit)` | Search all eligible workflow metadata; return bounded cards, match evidence, and explicit no-match/ambiguity information. Clamp limits server-side. |
| `inspect_workflow(workflow_id)` | Return bounded current state, important references, and links to history. |
| `resume_workflow(workflow_id, instructions)` | Validate ownership and scope, then enqueue a run. Request, turn, and retry identities are assigned by the backend. |
| `create_workflow(name, purpose, entities)` | Check recorded search evidence when older work exists, recheck known ownership keys transactionally, and create a workflow or return an existing owner. |
| `recall_history(...)` / `recall_worker_history(...)` | Fetch exact entries or bounded search results by immutable reference, with paging cursors. |
| `read_result(source_ref, cursor)` | Retrieve a bounded original-content page with provenance and continuation information. |
| `digest_result(source_refs, question)` | Perform bounded synthesis outside the caller's context and return source-linked findings. |

Separate creation from execution: `create_workflow` returns an ID; `resume_workflow` starts work. Initially retain `send_message_to_agent` for the legacy strategy and internal callers. When the registry is enabled, that adapter resolves an exact alias and uses the same creation/admission checks rather than bypassing them.

Keep tool definitions near their owning agent and share underlying services. Verify schema/handler parity mechanically. Search evidence and correlation IDs are backend state, not fields the model can fabricate to bypass creation checks.

### 4.3 Routing policy

1. Accept structured origin information from a trigger, callback, draft, or explicit workflow reference. Validate scope and current revision.
2. Build the routing intent described below. For references such as "send it," inspect the recent turn and pending-action state. Preserve actual reference dependencies while excluding unrelated earlier topics; resolve only an unambiguous referent.
3. Show a small, token-bounded recent-work list with a total-work count and `find_worker` guidance. Keep important applicable instructions visible.
4. Search exact metadata, then FTS5 name/purpose/entity/recent-task fields. Cap recency boosts so they cannot override a known resource owner.
5. Return bounded candidate cards with reasons. Keep separate records for different workflows involving the same contact.
6. Inspect or reformulate when matches are ambiguous. An empty lexical search is not proof that a workflow does not exist. Allow bounded alternate queries and historical lookup before creation.
7. Recheck creation inside a transaction. Deduplicate a repeated request by its request ID and a known exclusive ownership key when one exists. Do not collapse workflows because they share a person or have similar embeddings. Semantic duplicates without a reliable key remain an evaluation problem, not a guarantee solved by a UUID.

The default path uses no embeddings. A later optional semantic retriever augments these candidates rather than replacing exact ownership checks or the recovery tools.

### 4.4 Activity records and current-state cards

For each meaningful run outcome, persist a typed activity record containing `workflow_id`, `run_id`, source event IDs, task intent, structured actions/results, resource bindings, disposition, and explicit obligation changes. Capture observed outcomes from tool adapters; keep model-written narrative separate from facts confirmed by tools or supplied by the user.

Derive cards incrementally from these records and authoritative current state. Include purpose, resolved entities, relevant resource references, a bounded number of recent episodes, outstanding commitments, revision, and content hash. The source records remain accessible through immutable references. Do not rebuild cards by scanning every log during routing.

Obligations require stable identities and explicit opened/resolved/cancelled transitions. An empty latest obligation set must not resurrect older resolved commitments. An unknown outcome remains unknown; do not mark imported or interrupted episodes completed merely to populate a card.

Use the revision/hash to cache search profiles and detect stale routing evidence. Exclude volatile render-only values such as "three minutes ago" from content fingerprints. Preserve complete request/action/result episodes where they fit; omitted or oversized episodes retain source references.

### 4.5 Routing intent and enforced decisions

Introduce `RoutingIntent` and `RoutingDecision` models in workflow services, separate from prompt rendering and any optional ranker:

| Contract | Required fields / interpretation |
| --- | --- |
| `RoutingIntent` | Turn/subtask ID, current goal, entities, explicit bindings, resolved referents, unresolved distinctions, and supporting conversation/source references. |
| `RoutingDecision` | Decision ID, intent ID, action (`reuse`, `create_new`, `abstain`), eligible workflow IDs/revisions, retrieval status, evidence references, scope, data generation, and supersession/expiry metadata. |
| Retrieval status | `complete`, `partial`, or `unavailable` for the requested bounded lookup. Complete means the planned lookup finished, not that every possible semantic match has been disproved. |
| Ranking evidence | Named score components and reasons; heuristic scores are not calibrated probabilities of ownership. Missing confidence stays unknown. |

Construct intent from the current request plus the smallest evidence needed to resolve references. Explicit new topics suppress irrelevant previous-worker hints. Do not strip all conversation context: genuine pronouns, approved drafts, and multi-turn constraints still need their sources. Begin with available structured references and the Interaction Agent's lookup arguments; a separate intent-extraction model is not required for the baseline.

Bind decisions in backend state to `create_workflow` and `resume_workflow`. Validate the action, eligible ID, scope, data generation, and relevant current-state revisions at admission. If changed evidence invalidates a decision, refresh/inspect and issue a superseding decision instead of permanently locking the turn to an early guess. Resume acceptance and execution still use the shared coordination checks.

Abstention first permits bounded recovery: inspect candidates, reformulate, or widen the authorized lookup. Ask the user only when a material distinction remains unresolved. Partial/unavailable retrieval or a failed scorer cannot by itself authorize new creation. Optional-ranker failure may fall back to the baseline; that fallback's own evidence and status must be recorded. These checks concern worker selection and remain separate from approval for external actions.

## 5. Delivery phases

Each phase should be a reviewable change with its own acceptance checks. Keep new behavior disabled for normal use until its dependencies and lifecycle checks pass.

### Phase 0 / PR 1: Baseline, fixtures, and observability

**Purpose:** Establish whether later changes preserve correct ownership and task behavior.

**Implementation**

- Add an injectable data-path helper, proposed as `server/data_paths.py`; use it for test-owned registry, logs, triggers, summaries, and Gmail fixtures.
- Extend `server/openrouter_client/client.py` to record component/model, provider-reported input/output usage, elapsed time, and failure category. Missing usage is unknown, not zero. Avoid recording secrets or full content in metrics.
- Give observations an explicit availability state: `available` (directly observed), `inferred` (derived with evidence), `unavailable` (missing/failed with reason), or `not_applicable`. Keep this distinct from retrieval status. A mock scorer and a live provider must be labeled separately; never silently substitute a fake while reporting a live result.
- Add correlation IDs to instrumentation without changing routing behavior. Include callbacks and scheduled tasks, not just the initial interaction request.
- Add fixed-catalog retrieval fixtures and a deterministic fake Gmail backend in `server/tests/fixtures/`. Include exact provider IDs and controllable side effects.
- Include alternating unrelated topics, genuine pronoun follow-ups, stale cards, near-tied owners, and complete/partial lookup failures. Predeclare comparisons so improved metadata, decision checks, and a future semantic ranker can be evaluated separately.
- Add a small executable evaluation harness under `evals/agent_overload/` with a fixed model/configuration manifest, frozen inputs, and saved evidence.
- Capture current full-roster behavior as the baseline. Keep the existing model/output-token configuration unchanged during comparisons.

**Acceptance**

- Existing tests pass using isolated storage.
- Fixtures cover two Alice workflows, an old owner, an empty catalog, and a request requiring a new workflow.
- A model-free run can trace request -> dispatch -> tool result -> callback -> user-visible reply.
- Observed, inferred, unavailable, and inapplicable metrics stay distinguishable in stored evidence and reports.
- No live email is sent and no model-backed benchmark is required for ordinary tests.

### Phase 1 / PR 2: Stable identities and non-destructive migration

**Purpose:** Give later routing and recall a reliable source of truth.

**Files:** New `server/services/workflows/` package; adapt execution roster/log services, conversation log services, trigger models/store/service, and startup ordering in `server/app.py`.

**Implementation**

- Implement schema versioning, short transactions, foreign-key checks, bounded busy handling, and explicit storage errors. Do not treat a failed database read as an empty catalog.
- Add migration dry-run/report and apply modes. Run migration in a maintenance window before schedulers, inbox polling, and request processing start.
- Back up original files and SQLite databases using consistent snapshots. Import the plain-string roster without dropping entries. Assign stable workflow IDs and preserve every exact name alias.
- Import conversation and worker logs in streams with original source locations, sequence mappings, and raw-source fingerprints. Recover purpose/recent-task metadata from available requests; label unknown state instead of inventing it.
- Detect slug collisions, orphan log files, and unresolved trigger owners. Report unresolved records for reconciliation; do not auto-merge workflows or guess names from filenames.
- Preserve already-truncated historical tool responses as such. Fetch fresh source data through tools when needed; never manufacture missing content.
- Add nullable `workflow_id` to triggers and backfill it through aliases while keeping legacy `agent_name`. Because triggers and new workflow state begin in separate databases, use resumable migration checkpoints and validate both before enabling background dispatch.
- Map the summarizer's current `last_index` and legacy entry indices to stable event references. Preserve the current summary and its provenance.
- Make the database authoritative once its feature is enabled; route writes through adapters. Avoid unsynchronized independent file/database writers. Legacy files become preserved inputs or explicit compatibility exports.
- Add typed activity-record writes and a rebuildable card projection. Commit confirmed state changes, resource links, obligation transitions, and revision updates atomically; preserve the source event behind every derived field.

**Acceptance**

- Repeating or resuming migration produces the same workflow/event mappings without duplication.
- Every resolvable legacy alias and trigger reaches its original history after restart.
- Input files remain intact; all unresolved collisions and missing references appear in the migration report.
- New workflow history is keyed by ID, preventing new filename-slug collisions.
- An unknown historical state is not automatically marked completed or archived.
- Rebuilding cards preserves outstanding obligations, leaves resolved obligations resolved, and retains source provenance.

### Phase 2 / PR 3: Explicit discovery and reuse

**Purpose:** Remove roster-size growth from ordinary Interaction Agent prompts while preserving access to older work.

**Files:** Registry/search services; `server/agents/interaction_agent/{agent.py,tools.py,runtime.py,system_prompt.md}`; structured result adapters in execution Gmail tools and runtime; trigger dispatch adapter.

**Implementation**

- Build an FTS5 search document from purpose, aliases, entities, current summary, and bounded recent task descriptions. Update it when events change; do not rescan every historical log on each query.
- Implement `find_worker`, `inspect_workflow`, `create_workflow`, and `resume_workflow`. Parameterize SQL and normalize/escape full-text query syntax so punctuation and user text cannot become unintended operators.
- Render only recent workflow cards under a roster token budget. Display hidden-work counts and the recovery tool, including when the recent set is empty.
- Build `RoutingIntent` from the current request and required reference evidence. Pass structured workflow/run origin information on callbacks and triggers instead of rediscovering their sender through similarity.
- Persist typed routing decisions and enforce them at dispatch, including stale-revision detection, explicit abstention, and a bounded path to inspect/research and supersede an incorrect early decision.
- Add transactional creation checks and backend-generated request idempotency. Preserve multiple valid workflows for the same contact or supporting thread.
- Update resource references from normalized tool responses. Add new references without overwriting earlier thread/draft ownership evidence.
- Run in shadow mode first: compute candidates and record decisions while retaining current model-visible routing.

**Acceptance**

- Exact-reference fixtures resolve to the expected owner with no embedding request.
- A known older workflow remains findable outside the recent list and after archival.
- "Send it" uses the correct pending draft or produces explicit ambiguity; it never guesses between concurrent drafts.
- Switching from an Uber-receipt request to a GitHub-review request does not inherit the Uber workflow. A genuine follow-up still preserves its earlier referent.
- Total lookup/scoring failure and near-tied owners cannot automatically create another worker. Unauthorized or stale dispatch attempts trigger recovery rather than execution.
- Same contact/different task fixtures remain separate. Repeated creation of the same request returns the same workflow.
- At catalog sizes 100, 1,000, and 10,000, the rendered roster obeys the configured token budget. Database/index size may grow; prompt size stays capped.

### Phase 3 / PR 4: Bounded context with exact recovery

**Purpose:** Protect all model calls from large histories and results while preserving access to their sources.

**Files:** New shared context services, proposed as `server/context/`; interaction/execution context builders; execution tool sessions; conversation summarizer; email-search task; Gmail importance classifier; final request builder.

**Implementation**

- Persist new messages, full tool results, and callbacks before building model-visible previews. Give previews immutable source references and explicit omission markers.
- Build interaction and worker contexts from required instructions/current state, bounded recent episodes, source-linked summaries, a compact older-history index, and capped activity cards. Preserve episode boundaries and valid tool-call/result pairs while they fit; retain recovery references when an episode must be omitted or previewed.
- Implement indexed, paged recall. Search and paging must not read every historical payload into memory merely to return a few matches.
- Keep important commitments and applicable approval rules in structured current state with provenance. Summaries supplement authoritative state; they do not replace it.
- Add a per-run tool session that owns workflow identity, result references, handler registry, and cumulative read/digest budgets.
- Support exact draft/document bodies by reference. Persist new large results durably so a reference remains meaningful after a run ends or the app restarts.
- Add optional bounded digest operations for synthesis: chunk, cap concurrency/calls/output, preserve source attribution, and expose partial failures. Use original sources for verbatim operations.
- Apply previewing within the email-search sub-agent, to merged callbacks/current-turn payloads, and to summarizer/classifier inputs. A budgeted outer agent must not delegate an oversized prompt to an inner agent.
- Add a final request preflight that accounts for system text, messages, tool schemas/results, protocol overhead, output reservation from `openrouter_max_tokens`, and safety headroom.
- Use a token-counting adapter per supported model where available; label fallback estimates honestly and validate them against provider usage on representative inputs. Four characters per token is not an exact cross-model guarantee. Handle actual provider overflow as a bounded rebuild or clear terminal failure, never an unbounded retry loop.
- Clamp recall pages, candidate cards, digest work, per-turn tool-result growth, total model iterations, and task deadlines. Rebuild older context as needed while preserving valid tool-call/result pairs.
- Keep full draft review available to the user even when the model sees only a reference. Add the smallest necessary read-only UI/API support for full content; do not ship an unrelated UI redesign.

**Acceptance**

- Oversized conversation history, one giant user message, long worker history, large email results, and merged callbacks all produce bounded requests with usable source references.
- Details omitted from a preview can be recovered; a middle-of-document fixture is not answered from head/tail text alone.
- Draft bodies passed by reference match source content exactly through storage and the Gmail adapter.
- Missing/expired references return explicit errors; content is never silently reconstructed from a summary.
- Tool schemas and executable handlers remain in one-to-one agreement.
- Test multilingual text, long identifiers, escaped XML/JSON, attachments/unsupported content, and very small budgets. Source-size limits are explicit and produce visible ingestion errors rather than silent data loss.

### Phase 4 / PR 5: Shared execution control and lifecycle integrity

**Purpose:** Bound resource pressure and preserve correctness across overlapping user requests, triggers, callbacks, and restarts.

**Files:** Shared workflow execution service; `server/agents/execution_agent/batch_manager.py`; interaction dispatch/runtime; `server/services/trigger_scheduler.py`; Gmail watcher dispatch; app startup/shutdown; chat handler and clear-history route.

**Implementation**

- Introduce an application-owned execution queue/service used by every batch-manager instance and trigger. Persist accepted work and track outstanding task handles.
- Limit active workers and pending jobs separately. The initial implementation supports one application worker process; document/enforce this constraint until cross-process admission and coordination are implemented.
- Apply per-workflow serialization without holding a database transaction across model or network calls. Coordinate short interaction planning/state updates while allowing different workflows to execute concurrently.
- Use explicit `request_id`, `turn_id`, `batch_id`, `workflow_id`, and `run_id`. Replace the single shared current batch with records keyed by actual originating turn/event.
- Keep run state independent of workflow status. Tool-confirmed milestones update waiting-for-approval/external-event/completed state; returning from the execution loop alone does not complete the workflow.
- Preserve the existing HTTP acceptance contract: 202 means accepted, not finished. Persist acceptance before returning it; queue rejection/storage failure must be visible instead of silently dropping work.
- Bind send authorization to the actual approved draft/version and recipients. Revalidate changed drafts and record send outcomes. On uncertain provider outcomes, reconcile before retrying; do not automatically replay a potentially completed send.
- Track callback delivery so a restart can recover a completed result without repeating its external actions. Limit callbacks to a bounded summary plus references.
- At shutdown, stop admission and drain or mark remaining work interrupted. Recover safe pending/read-only work after restart; reconcile interrupted writes before deciding to resume them.
- Coordinate history clearing with the execution service: stop admission, cancel/drain applicable work, advance the data generation, clear all new records/indexes/caches and existing triggers/history, then resume. Ignore late callbacks from the old generation. Report any external action already in flight whose outcome cannot be undone.

**Acceptance**

- Combined chat and trigger load never exceeds configured active or pending limits.
- The same workflow cannot execute competing draft/send operations simultaneously.
- Separate turns/events receive their own callbacks; one slow unrelated job does not hold all results in a global batch.
- Timeout, cancellation, exception, and shutdown release execution capacity and leave inspectable run states.
- Restart after send-but-before-callback does not blindly send again.
- Clearing history leaves no stale registry results, pending approvals, trigger owners, embeddings, or post-clear callbacks.

### Phase 5 / PR 6: Archival, end-to-end evaluation, and initial release

**Purpose:** Demonstrate bounded operation and continuity before enabling the new path by default.

**Implementation**

- Add explicit archival for completed/cancelled workflows with no outstanding run, approval, or active trigger. Age alone does not end an open workflow.
- Evict dormant cards from the hot cache while retaining searchable records, event references, and resource mappings. Resume a recovered workflow using its existing ID.
- Keep source retention separate from prompt management. The first release has no automatic source deletion; later retention policies require explicit behavior, reference-expiry handling, and tests.
- Add application-level tests through FastAPI for message acceptance, history polling, worker callback delivery, scheduled execution, restart recovery, and clearing history. Use fake Gmail and mocked model responses for deterministic cases.
- Run the fixed-catalog and longitudinal evaluations described below. Publish sanitized raw evidence with the report so reported wins can be checked.
- Update README/environment documentation with migration, feature flags, supported deployment topology, failure recovery, and rollback procedures.

**Acceptance**

- All deterministic ownership, recovery, exact-content, queue, and lifecycle scenarios pass.
- Archived workflows remain searchable and resumable without duplicate creation.
- Full-stack tests preserve existing draft confirmation and chat error behavior.
- Model-backed runs show their outcome distribution, usage completeness, latency, and failure categories; no routing-quality claim is inferred from token reduction alone.
- Default enablement waits for the release gates in section 8.

### Phase 6 / PR 7, optional: Semantic retrieval behind a separate flag

**Purpose:** Improve measured paraphrase failures without making every interaction depend on an embedding request.

**Files:** New embedding client/cache and semantic retriever in workflow services; retrieval policy; optional evaluation fixtures.

**Implementation**

- Profile each workflow using stable purpose, meaningful entities, current summary, and bounded recent assignments. Preserve exact IDs for deterministic lookup instead of trusting their embedding similarity.
- Cache embeddings by workflow ID, profile hash, model, and index version. Refresh profiles from new events; backfill existing records, repair missing entries, and invalidate changed/deleted records without rereading all logs per request.
- Skip semantic retrieval for known-owner and sufficiently small/clear cases. Use it when lexical evidence is weak or the agent asks for another discovery pass.
- Combine lexical and semantic candidates using a measured fusion/reranking policy, with a hard output token/candidate ceiling. Tune any confidence thresholds on validation data; cosine similarity is not a calibrated probability of ownership.
- Optionally compare a small classifier reranker against embedding reranking on the same retrieved candidates. It may assess task relevance, continuity evidence, and conflicting entities. Use a provider-neutral interface, labeled real/mock modes, and a bounded shortlist; do not make one external model call per workflow in the whole roster. Keep this experiment outside baseline requirements.
- On embedding failure, retain bounded lexical/recent lookup and recovery tools. Record degraded mode rather than failing the whole user interaction or silently loading the full catalog.
- Account for embedding calls, cold-start indexing, retries, and profile-refresh work in the comparison.

**Acceptance**

- Missing or stale indexes repair themselves and existing workflows remain discoverable.
- Known IDs and ambiguous-owner cases retain their required behavior with semantics enabled.
- Held-out paraphrase cases improve over the lexical baseline without an unacceptable end-to-end quality, latency, or cost regression under predeclared evaluation criteria.
- Failure of the embedding provider does not stop otherwise supportable work.
- Semantics stays disabled if the evaluation does not justify its complexity.

### Phase 7 / PR 8: Knowledge graph retrieval strategy after the baseline

**Purpose:** Test whether following explicit relationships improves discovery across people, projects, workflows, and resources when names or isolated descriptions are insufficient.

**Dependencies:** Phases 0-5 completed and the baseline evaluation frozen. Phase 6 is independent and optional. Implement and evaluate the graph strategy after the baseline; leave its default enablement gated on the evidence below.

**Scope:** A local graph projection and bounded traversal strategy, initially stored in SQLite. The baseline already records many useful links in `workflow_entities` and `resource_refs`. Reuse those IDs and facts rather than introducing a competing identity system. A graph is a way to represent and traverse relationships; it does not require a separate graph database or the full Microsoft GraphRAG indexing pipeline.

**Example:** To find earlier Acme contract work involving Alice, resolve Alice and the Acme project, follow their recorded participation links to workflows, then inspect the related contract thread and its owner. Return the supporting path and source references. Being connected to Alice alone does not establish that a workflow owns this contract.

**Files:** Proposed `server/services/workflows/graph/{models.py,projection.py,store.py,retrieval.py}`; migration/index maintenance; the existing lookup service; and graph-specific evaluation fixtures under `evals/agent_overload/` and `server/tests/`.

**Implementation**

- Define a small allowlisted schema. Initial node types are `Workflow`, `Person`, `Organization`, `Project`, and `Resource` (email thread/message, draft, document, or trigger). Initial relationships include `HAS_PARTICIPANT`, `PART_OF_PROJECT`, `USES_THREAD`, `CREATED_DRAFT`, and `TRIGGER_FOR`. Add types only for a tested query need.
- Project observed structured tool data, explicit user-supplied relationships, and existing source-backed records. Store assertion kind and source event for each relationship. The initial experiment does not require LLM extraction over the inbox or inferred relationships generated from co-occurrence.
- Store relationships with stable endpoint IDs, scope/account qualification where relevant, provenance, validity timestamps, revision, and supersession/tombstone information. Prefer provider/explicit entity IDs; identical names must not silently merge different people or projects.
- Build the graph as a replayable projection with a source-event watermark. Make event application idempotent, support rebuilds, and invalidate edges affected by deletion or corrected facts. Derive current obligations from current state so resolved commitments do not reappear through old edges.
- Implement an additional retrieval strategy behind `find_worker`, preserving its output contract. Resolve anchor entities/resources, traverse only permitted relationship types, intersect useful constraints, and return bounded workflow candidates with explanation paths and immutable evidence references.
- Bound hops, visited nodes/edges, candidate count, lookup time, and model-visible output. Start experiments at no more than three hops; treat limits as tunable budgets. High-degree contacts and projects cannot expand into an entire account's history.
- Combine graph and lexical candidates with deterministic deduplication by workflow ID. If the optional semantic strategy exists, test it as a separate combination. Exact validated bindings and current backend ownership/approval checks keep precedence over graph ranking.
- On a graph miss, staleness, or failure, preserve access to baseline lookup and record the strategy's availability. Graph failure alone cannot authorize creation. A graph path is retrieval evidence, not permission to dispatch or send.
- Re-read current workflow/resource state before acting. Preserve time-qualified conflicting claims and source links; a historical edge does not prove that an external email, project assignment, or approval is still current.
- Include graph projection state, nodes/edges, caches, and watermarks in rebuild, backup, history-clear generation, and deletion handling. Cross-account traversal and orphaned evidence links must fail their contract tests.

**Acceptance**

- Graph nodes reuse existing workflow/resource/entity IDs; known facts and past history are not duplicated into a second source of truth.
- Replaying the same events twice or rebuilding yields equivalent relationships and candidate evidence.
- Fixtures cover a person shared by unrelated projects, several workflows using one thread, same-name contacts, changed project membership, a superseded fact, archived workflow recovery, high-degree entities, and a cleared/deleted source.
- Returned paths explain the selected candidates and cite source events. Unsupported inferred relationships cannot become authoritative ownership or approval records.
- Traversal and prompt output remain within configured budgets; graph failure falls back to baseline discovery without suppressing valid historical work.
- The ablation in section 7.4 reports routing/task outcomes, candidate coverage, factual linkage errors, lookup latency, update/rebuild cost, and storage growth.
- Enable by default only if the graph adds reproducible benefit over the strongest non-graph baseline within predeclared operational budgets. If ordinary joins provide equivalent results, retain the simpler implementation and record that result rather than forcing graph-specific infrastructure.

## 6. Configuration and rollout controls

Proposed settings are implementation choices, not measured optimal values:

| Setting | Initial behavior |
| --- | --- |
| `OPENPOKE_DATA_DIR` | Defaults to the current data root; injectable for tests/evals. |
| `OPENPOKE_WORKFLOW_STORE_ENABLED` | Off during initial development; enabled after verified migration. |
| `OPENPOKE_CONTEXT_STRATEGY` | `legacy`, `shadow`, or `bounded`; initially `legacy`. Shadow computes new context/ranking without changing model input. |
| `OPENPOKE_SEMANTIC_RETRIEVAL_ENABLED` | Off; independently gated after the lexical release. |
| `OPENPOKE_GRAPH_RETRIEVAL_ENABLED` | Off for the baseline; introduced for the post-baseline Phase 7 experiment. |
| Recent workflow / candidate limits | Start with 5 recent cards and 5 lookup results, clamped to a maximum of 20 and the roster token budget; tune from evidence. |
| Model context/input budgets | Explicit per-model/per-stage configuration with output reservation and safety headroom; validate relationships at startup. |
| Recall / digest budgets | Separate per-result, per-turn, and per-run limits, plus deadlines and call caps. |
| Graph traversal budgets | Explicit hop, visited-node/edge, candidate, time, and output limits; begin at a maximum of three hops in graph experiments. |
| Active / pending run limits | Initial development values of 5 active and 100 pending; validate with mixed chat/trigger workloads. |

Invalid settings fail at startup with a clear error. The configured model's context capacity must not be inferred from the default output-token limit. Increasing a candidate count must never bypass the total prompt budget.

Roll back new routing/context through the strategy flag while keeping migrated storage and its compatibility adapters authoritative. A code-version downgrade is a separate operation: pause writers, drain/reconcile work, export verified legacy-compatible state, preserve ID/alias mappings, then switch versions. Do not assume flipping a flag synchronizes old files with new database writes. Do not deploy old and new independent writers against the same data directory.

## 7. Evaluation plan

### 7.1 Deterministic contracts

Add focused tests under `server/tests/` for migration, registry search, routing, context construction, source references, execution admission, and lifecycle operations. Use fixed clocks, temporary data roots, fake tools, and mocked model responses. Existing tests remain the compatibility baseline.

Essential scenarios:

| Scenario | Required result |
| --- | --- |
| Alice lunch and Alice contract | Correct distinct workflow; shared contact does not merge them. |
| Topic switch after several uses of one worker | Current task routes independently of unrelated prior-worker history. |
| Old worker outside the recent list | Discoverable through lookup, including after archive/restart. |
| "Send it" with one pending draft | Resume its exact owner and approved content. |
| "Send it" with competing referents | Resolve from reliable context or ask for the distinction; no arbitrary send. |
| Repeated request / concurrent known ownership | One durable request and intended owner; no duplicate action. |
| New task with no owner | Creation succeeds after appropriate lookup checks. |
| New report contains a new thread ID | Previous resource mappings remain searchable. |
| Latest activity resolves a commitment | Cards and later graph projections do not resurrect the older open obligation. |
| Card or workflow revision changes before dispatch | Refresh the evidence and decision; do not execute a stale routing choice. |
| All scorer calls fail, or top candidates tie | Record unavailable/ambiguous evidence and recover or abstain; do not infer novel work or certain confidence. |
| Huge text with an important fact in its middle | Recover the source or digest it; do not answer solely from the preview. |
| Exact content sent by reference | Stored and sent text match; actual approved draft is reused. |
| Trigger fires for an old workflow | Dispatch by stable owner; no semantic rediscovery required. |
| Provider/model overflow or unavailable embeddings | Bounded recovery/degraded mode; no retry storm or source deletion. |
| History clear while work is pending | New generation is clean and late callbacks cannot recreate old state. |

### 7.2 Fixed-catalog retrieval experiments

Freeze catalogs of 100, 1,000, and 10,000 workflows with similar names, different dates, dormant work, paraphrases, and legitimate no-match/ambiguous cases. Compare full roster, compact recent roster plus lexical lookup, and optional hybrid lookup using the same metadata and query labels. Split tuning and held-out evaluation cases.

Measure candidate Recall@5, correct final owner, incorrect reuse, new-work/no-match decisions, search calls, lookup p50/p95 latency, and model-visible roster tokens. For tasks requiring multiple owners, score all required owners rather than assuming one gold label. Direct-reference contract cases must resolve exactly.

### 7.3 Longitudinal task experiments

Run the same frozen sequence of user requests and timed overlapping follow-ups from identical empty state under each strategy. Let each run's roster evolve independently. Do not copy a favorable candidate state into the baseline or score fewer agents as inherently better.

Score outcomes using tool evidence: correct recipients, thread/draft identity, approved content, required confirmations, successful reminders, truthful replies, duplicate actions, and missed commitments. Include three or more model-backed repetitions for the release evaluation, report variability, and retain failure traces.

Grade routing action/ID correctness separately from end-task correctness, identity continuity, duplicate creation, and context containment. Compare immutable workflow IDs rather than display-name string matching. Pin model/provider/configuration and fixture provenance; report uncontrolled differences instead of attributing every gain to the retrieval algorithm.

Measure input/output tokens for interaction, execution, search, summarization, digest, classification, and embeddings where enabled. Report provider-priced cost only when prices/usage are actually available. Include queue wait and end-to-end latency, not just first response time. Compare efficiency on comparable completed work because an early-failing baseline can appear artificially cheap.

All catalogs, counts, and limits in this document are proposed evaluation inputs or initial settings. No new performance result is claimed here.

### 7.4 Post-baseline graph ablation

Freeze the completed baseline's code/configuration, source-event snapshots, metadata, tasks, and evaluation split before tuning the graph. Compare:

1. Baseline exact-reference and lexical retrieval.
2. Equivalent relational filters/joins over the same facts, to determine whether a separate graph strategy adds anything beyond the baseline's existing relationships.
3. Baseline plus bounded graph traversal.
4. If Phase 6 exists, semantic reranking with and without graph candidates under the same model and budgets.

Include tasks that genuinely require multiple relationships: an earlier project involving a person, the correct contract thread among several interactions, dependencies between workflows, and historical relationships whose validity has changed. Keep unrelated simple/exact-ID tasks as a regression set. Measure all required workflow owners for multi-workflow requests.

Use the same source facts in every comparison; do not give only the graph strategy richer metadata. Measure candidate recall, wrong reuse, task success, abstention/duplicate rates, unsupported-link rate, source-path correctness, p50/p95 latency, model cost, index update/rebuild time, and storage. Report full traversal and evidence counts so hidden graph fanout cannot masquerade as bounded model input.

Promote the strategy only after reproducible improvements on held-out relationship tasks, passing deterministic lifecycle/account-boundary tests, and acceptable regression/operational budgets fixed before the evaluation. A graph implementation or a more impressive diagram is not itself a success criterion.

## 8. Release gates and definition of done

- [ ] Existing deterministic tests pass, with no real data touched.
- [ ] Migration is repeatable, collision-aware, backed up, and verified before background services start.
- [ ] Historical names, stable IDs, resource references, and trigger owners remain connected after restart.
- [ ] Full-roster rendering is removed from the bounded strategy; older work remains searchable.
- [ ] Activity cards preserve source-backed outcomes and the current set of outstanding commitments.
- [ ] Intent isolation passes topic-switch and genuine-follow-up cases; typed routing decisions are enforced and can be revised through lookup.
- [ ] Partial/unavailable retrieval and ambiguous scores do not silently create new workers or report unsupported certainty.
- [ ] Every omitted source has a usable reference, or an explicit indication that it was never captured/unavailable.
- [ ] Prompt builders and final request preflight enforce configured budgets across every model-calling component.
- [ ] Required deterministic ownership and approval scenarios pass with no duplicate sends or fabricated IDs/content.
- [ ] Shared chat/background admission, per-workflow coordination, callback correlation, shutdown, restart, and history clearing pass integration tests.
- [ ] Archive removes cache residency without deleting discovery metadata or outstanding commitments.
- [ ] Model-backed comparison evidence and remaining failures are published; usage coverage and uncertainty are explicit.
- [ ] Rollback has been rehearsed against copied representative state.
- [ ] Semantic retrieval remains optional until its separate gate passes.

The first release is complete at Phase 5 when these gates pass. Freeze it as the comparison baseline. Phase 6 is an optional semantic optimization; Phase 7 is the planned subsequent knowledge graph experiment with its own acceptance and promotion gates. Neither extends the prerequisites for the first baseline release.

## 9. Trade-offs and deferred ideas

| Decision | Trade-off and follow-up |
| --- | --- |
| Local SQLite/FTS5 | Keeps initial operations simple and gives transactional state, but has one writer at a time. Keep transactions short and measure contention before considering another database. |
| Explicit lookup tools | Add possible model round trips. Exact-owner and clear recent-state paths bypass unnecessary discovery. |
| Source-backed bounded context | Adds indexing/storage and recall latency. Track storage growth; add retention policy separately from prompt truncation. |
| Single-process shared execution service | Makes admission and coordination reviewable initially. Multiple application workers need cross-process leases/admission and scheduler ownership before support is advertised. |
| Semantic retrieval later | Defers some paraphrase improvements while preserving a simpler baseline and availability. Measure the failure cases that justify it. |
| Summaries/digests | Useful for synthesis but can omit facts. Preserve provenance and original content for exact operations. |
| Durable local actions vs external APIs | Local request deduplication cannot establish exactly-once upstream sends after an uncertain network outcome. Reconcile uncertain actions and report limitations. |
| Source-backed graph projection after the baseline | Can connect entities and earlier work across several relationships, but adds entity-resolution errors, stale-edge handling, traversal cost, and maintenance. Begin with explicit links in SQLite and test against equivalent relational lookup before adopting graph-specific infrastructure. |

Potential work beyond the planned graph experiment: LLM-proposed relationships with explicit uncertainty and provenance; reusable domain-worker implementations loading workflow-specific state; hierarchical discovery for many integrations; ranking learned from evaluated routing failures; full tokenizer/counting support for additional models; cross-process execution and durable distributed queues. None is required for the initial bounded, recoverable design.

## 10. References and reuse from existing proposals

- [OpenPoke architecture and the original overload problem](https://www.shloked.com/openpoke).
- [PR #12: bounded context and recall/reference tools](https://github.com/shlokkhemani/openpoke/pull/12): adopt the recovery mechanisms and explicit worker lookup; strengthen durable identity, resource history, and deployment/lifecycle coverage.
- [PR #15: semantic shortlisting](https://github.com/shlokkhemani/openpoke/pull/15): reuse the idea of recent-task profiles and fingerprinted embedding caches; make semantics conditional and preserve a non-embedding recovery path.
- [PR #11: Smart Roster](https://github.com/shlokkhemani/openpoke/pull/11): reuse resource-control ideas; use shared admission and searchable archival instead of deleting completed-worker discovery records or rotating away source history.
- [Akshay Rakheja's agent-overload implementation, reviewed revision](https://github.com/akshay-rakheja/agent-overload-take-home-assignment/tree/c1259d43bd9fa8468f5507513589e672745d8c8f): reuse the concepts of activity records/cards, explicit routing outcomes, dispatch checks, and layered evaluation. The baseline plan strengthens these with intent isolation, revision-aware recovery, and separate failure/ambiguity states. This is selective design reuse, not a wholesale adoption of its router or benchmark claims.
- [SQLite FTS5 documentation](https://www.sqlite.org/fts5.html): lexical search, tokenization, ranking, and index maintenance.
- [SQLite transactions](https://www.sqlite.org/lang_transaction.html): write coordination and transaction behavior.
- [Effective context engineering for AI agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents): bounded working context, recovery, and long-running work.
- [Contextual Retrieval](https://www.anthropic.com/news/contextual-retrieval): lexical/semantic combination and reranking for the optional retrieval phase.
- [MemGPT](https://arxiv.org/abs/2310.08560): persistent information outside the model's immediate working context.
- [Agent-as-a-Graph](https://arxiv.org/abs/2511.18194): research on retrieving linked tools and their parent agents; useful inspiration, not validation of this plan's workflow/entity graph.
- [Microsoft GraphRAG query overview](https://microsoft.github.io/graphrag/query/overview/): distinguishes entity-focused local retrieval from resource-intensive global community-summary search. The planned first graph strategy is local relationship traversal.
- [Microsoft GraphRAG custom graphs](https://microsoft.github.io/graphrag/index/byog/): a possible later integration with existing entity/relationship tables. Adopting this package is not required by Phase 7.

The PRs are design references, not dependencies to merge wholesale. Their published benchmark claims do not substitute for evaluation of this implementation in the current checkout.
