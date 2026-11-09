# Execution Agent Overload: Implementation Plan

- Date: 2026-11-07
- Revised: 2026-11-08, reduced scope
- Status: Active plan; this revision changes documentation only.
- Scope: Improve discovery and bound model context while preserving the current Interaction Agent / Execution Agent architecture.

## 1. Goal and scope

OpenPoke should find earlier work without putting every worker name into each prompt, and continue long tasks without putting every message or tool result into each model request.

The first release has three deliverables: bounded worker discovery, bounded context with recoverable content, and a small comparison against the existing behavior. Each change must have an immediate runtime use and focused checks. Do not build infrastructure for a deferred feature.

Keep the existing name-based dispatch, roster, conversation logs, worker logs, and trigger ownership. Full history migration, a universal event store, durable execution recovery, and a new workflow lifecycle are not prerequisites. Preserve the original files and draft-confirmation behavior.

This revision supersedes the earlier eight-phase roadmap. **Phase 1 below means discovery, not the former storage/migration phase.** The [progress log](execution-agent-overload-progress.md) records work under the earlier roadmap; its migration next-step instructions are historical and do not override this plan. The earlier plan remains available in Git history.

## 2. Rules that remain essential

- Omitted context must remain recoverable from stored content. Preserve full new results before showing a preview. Historical content that was never saved must be identified as unavailable.
- Preserve exact worker names and existing histories. Do not merge workers because they share a contact or similar wording. Reject new names that would collide with an existing log filename; report historical collisions without guessing ownership.
- Prefer validated exact worker/resource references over lexical matches. Keep mailbox references qualified by provider and account when known; do not silently assign unknown legacy references to another account.
- A lookup failure is different from no matches. Do not create another worker simply because lookup failed. Ambiguous drafts or owners require another lookup or clarification.
- Finding a worker does not authorize sending. Preserve user confirmation and exact draft content; never reconstruct an omitted draft from a summary.
- Missing usage remains unknown, actual zero remains zero, and mock results remain labeled mock. Lower token counts alone do not establish task correctness.
- New persisted data uses the configured data root and participates in history clearing. References cannot resolve into a different worker, mailbox, or replacement history.

## 3. Delivery phases

### Phase 0: Retain the preparation already completed

The earlier Phase 0 supplied isolated data paths, telemetry, fixed catalogs, a fake Gmail backend, and a model-free baseline. Reuse these assets without expanding their frameworks.

- Keep the isolated test runner and shared data-root helper.
- Keep the existing usage/timing/failure logging. Do not rewrite working telemetry merely to reduce its line count; add no further generalized observation machinery for this release.
- Reuse the relevant fixtures and existing evaluation command. Add cases only for behavior changed by this plan.
- Treat saved baseline results as model-free evidence. They do not establish live routing accuracy, provider latency, or cost.

No additional preparatory phase is required before discovery work starts.

### Phase 1: Bounded roster and explicit worker lookup

**Outcome:** The Interaction Agent sees a small recent list and can find any existing worker by lookup. Prompt roster size stays capped as the catalog grows.

**Implementation**

1. Keep the current roster authoritative for worker membership. Add a small metadata sidecar keyed by exact worker name: purpose, recent assignment, and last activity. Use the existing local JSON approach with atomic writes; do not adopt the inactive workflow database for this phase.
2. Existing workers remain searchable by name immediately. Add available metadata incrementally from assignments; missing purpose stays unknown. Avoid scanning every worker log or making summarization calls on each lookup. Metadata is a rebuildable aid, not authoritative task or approval state.
3. Add `find_worker(query, limit=5)` with simple deterministic lexical matching over this metadata. Search the entire roster, including older workers. Return exact names, short descriptions, and match reasons under a response budget. Clamp the count and query size; distinguish successful empty results from storage/search errors.
4. Replace the full prompt roster with at most five recent entries under a text budget, the total worker count, and lookup guidance. Count and text limits both apply. Missing activity timestamps must not be presented as known recency.
5. Reuse `send_message_to_agent`. Require a successful discovery attempt before creating a new name when earlier workers exist, using small per-turn backend state. Recheck exact membership and filename collisions when creating; protect the local update with a short lock. Search reduces accidental duplication but does not prove semantic uniqueness.
6. Update the prompt to use the current request and necessary follow-up evidence. Preserve genuine draft/pronoun references; an unrelated topic must not inherit the last worker. Keep exact callback/trigger ownership when available. No persistent routing-decision system or separate intent model is required.

Primary integration points: `server/services/execution/roster.py`, `server/agents/interaction_agent/{agent.py,tools.py,runtime.py,system_prompt.md}`, and one small metadata/search helper near the roster.

**Checks**

- An old worker outside the recent list remains findable and reuses its existing history.
- Alice lunch and Alice contract remain separate; unrelated topic switches and genuine follow-ups route appropriately.
- Failed lookup cannot masquerade as an empty catalog and permit creation. Repeated exact names reuse the existing worker.
- Existing dispatch and trigger names still work. Metadata can be rebuilt without changing original history, and clearing history clears the sidecar.
- At 100, 1,000, and 10,000 workers, both the recent roster and lookup output obey their configured budgets. Use the existing catalog generator.

### Phase 2: Bounded context with source recovery

**Outcome:** Long histories and large results fit the configured model input budgets, and omitted details can still be read accurately.

**Implementation**

1. Add a small shared context-budget helper. Account for system instructions, current messages, history, tool schemas/results, output reservation, and headroom. Use supported token counting where available; label estimates honestly. Add a final preflight in the shared provider client, with bounded rebuild or a clear error if required content cannot fit.
2. Keep recent complete conversation/tool episodes and applicable instructions; omit or preview older material with recovery information. Preserve valid tool-call/result pairs. Apply size limits to the current user message and callbacks as well as history.
3. Save full new oversized messages/results under opaque IDs in a small content store beneath the data root. Store the owner and mailbox qualification where applicable. The simplest implementation is immutable content files plus minimal metadata; it does not require importing old history or creating an event schema.
4. Add bounded `read_result` and history-recall handlers with paging. Stream only the selected legacy history when searching it; avoid loading all workers' logs. Expose references, not arbitrary filesystem paths. Keep source content readable after restart; clearing history invalidates references and rejects late content writes from earlier runs.
5. Pass exact large draft/document bodies by reference through the relevant adapter. Preserve full user review using the existing draft display path, resolving the body in backend code. Missing or historically truncated content returns an explicit limitation.
6. Apply the same limits inside email search, summarization, and classification. An outer preview cannot prevent an inner agent from overflowing. Reuse existing iteration/time limits and cap cumulative result growth and recall work. Add no digest sub-agent or general tool-session framework initially.

Primary integration points: interaction/execution prompt builders and runtimes, execution log/result handling, conversation summarization, the email-search task, Gmail classifier, provider client, and history-clear route. Add only the small budget/content helpers needed by those callers.

**Checks**

- Long worker history, one giant user message, large email results, and combined callbacks produce bounded requests across every model-calling component.
- A detail in the middle of an omitted result can be recovered. Paging is bounded; missing or cleared references fail explicitly.
- A draft passed by reference preserves its exact body and recipients, and still requires confirmation.
- Tool schemas have executable handlers, tool-call/result pairs stay valid, and small budgets or multilingual inputs have explicit behavior.
- Full new content survives restart, remains tied to its owner/account, and cannot reappear through old references after clearing. Existing source files remain intact.

### Phase 3: Focused comparison and release

**Outcome:** Demonstrate the discovery/context improvements without building another evaluation platform.

- Use the existing fixtures/harness for a small comparison: legacy behavior versus bounded discovery/context, with the same model and output limits. Existing scripted tests can verify plumbing; routing-quality claims require actual model decisions.
- Report correct reuse, incorrect reuse, unnecessary creation, actual draft/tool effects, total model calls, available token usage, latency, and failures. Keep unavailable measurements explicit. No confidence framework or additional benchmark infrastructure is required.
- Run the focused regressions, existing backend suite, and relevant application checks for chat acceptance, callbacks, triggers, full draft review, and history clearing. Publish a short report and document known limitations, configuration, and how to disable the new prompt/lookup strategy while preserving data.
- Enable the new strategy after the relevant checks pass. Keep the legacy strategy available for comparison during development. Never fall back by silently loading an unbounded full roster into a bounded request.

The release is complete when earlier work remains discoverable, every model request obeys its configured budget, omitted content can be recovered, and existing dispatch/confirmation behavior passes regression checks. Report remaining lexical-routing failures honestly.

## 4. What to do with the existing implementation

The workflow package inspected for this revision is not connected to the live agents, scheduler, or application startup. Its database and history APIs are preparatory work. There is no need to finish their migration to deliver Phase 1 above.

| Existing work | Disposition |
| --- | --- |
| Shared data root and isolated runner | Keep in active use. |
| Existing telemetry and its regression tests | Keep working behavior; freeze further framework expansion. |
| Catalogs, fake Gmail, and evaluation tooling | Reuse the relevant cases; do not expand the emulator or harness without a concrete changed behavior to verify. |
| Large generated baseline artifacts | Preserve the current evidence. Optional later cleanup can retain the recipe and concise report, regenerate bulk outputs, and update any consumers before removing artifacts from the active branch. |
| Workflow UUID/alias/SQLite foundation | Preserve as deferred work. Do not activate it just because it exists. Reuse a helper only if it actually simplifies the smaller implementation. |
| Migration inspector, source/event APIs, schema upgrades, and their dedicated tests/docs | Preserve together as deferred work. Full legacy import, schema adoption, and event mappings are outside this release. |

Before cleanup, review and checkpoint the existing tracked **and untracked** work, including history modules and their tests. Preserve it in a named Git commit on a separate branch or an equivalent explicit backup. A branch pointer alone does not preserve uncommitted files. Leave unrelated working changes out of that checkpoint.

Then, in a separate reviewable cleanup change, remove unused workflow/migration/event code and its dedicated tests/docs from the active implementation, checking imports first and running the relevant suite. Preserve the deferred checkpoint. Do not reset to an earlier commit, rewrite published history, discard unrelated changes, or delete runtime data. This plan revision itself performs none of those code or Git operations.

Keep the historical progress entries as a record. At the next implementation update, mark the old migration roadmap superseded and report work against the phases above. Do not continue its backup/apply next step merely because it is already written down.

## 5. Deferred work and triggers for reconsidering it

- **Execution pressure:** If mixed chat/trigger load demonstrates a concurrency problem, add a shared application-level active limit, bounded pending admission, and per-worker serialization used by every dispatch path. A semaphore on each batch-manager instance is insufficient. Durable queues and restart replay are separate requirements.
- **Migration and lifecycle:** Revisit stable workflow IDs, complete historical import, persisted obligations, approval ledgers, archival, and durable callback/send recovery only for a demonstrated product need. This release does not claim to resolve all existing restart or asynchronous history-clear races.
- **Retrieval quality:** Consider semantic retrieval or graph traversal only after the lexical comparison exposes failures they could plausibly address. Neither is scheduled first-release work.
- **Storage and deployment:** Automatic source deletion, multi-user authentication, cross-process coordination, and distributed execution require their own explicit scope.

## 6. Next action

Checkpoint and set aside the unused infrastructure from the former Phase 1, then implement the bounded recent roster and `find_worker` through the existing dispatch path. The next functional review should show that behavior running before any further storage framework work.
