# Bounded worker discovery

This implements revised Phase 1 through the existing Interaction Agent and
`send_message_to_agent`. Worker membership remains in `execution_agents/roster.json`;
worker names, log filenames, trigger owners, and Gmail/draft adapters retain
their existing formats. No workflow database or history migration is used.

## Motivation and behavior

Previously every worker name appeared in every Interaction Agent prompt, and
dispatch created an unfamiliar name without checking whether earlier work was
relevant. Roster read failures could become empty catalogs. The bounded strategy
shows a small recent list and exposes lookup across the entire roster.

Set this before starting the backend, then restart:

```dotenv
OPENPOKE_WORKER_DISCOVERY=bounded
```

The default remains `legacy` during development. That setting retains the full
roster and original tool schemas for comparison. Invalid strategy values fail
configuration validation. Bounded-mode failures produce an explicit unavailable
state; they never fall back to the unbounded roster. The evaluation command and
test runner pin `legacy` before imports; bounded tests select their mode explicitly.
Default promotion and model-backed routing comparisons belong to Phase 3.

## Metadata and matching

`execution_agents/roster.metadata.json` lives alongside the roster under
`OPENPOKE_DATA_DIR`. Its exact-name entries contain a purpose snippet from the
first observed assignment, the latest assignment snippet, and its UTC activity
time. Text fields are capped at 240 characters. These are assignment observations,
not authoritative pending-action, completion, or approval state.

The shared batch manager updates metadata when assignments start, including
scheduled work with an existing worker name. It never adds a worker just to
record metadata. Unreadable metadata leaves exact dispatch available and causes
lookup to fail explicitly until repaired. A failed atomic metadata update keeps
the previous readable projection. Existing workers are immediately
searchable by name even before this file exists. Missing purpose/activity stays
unknown; lookup does not scan worker logs or call a model to fill it.

`find_worker(query, limit=5)` searches every roster name plus available purpose
and recent-assignment text. It uses Unicode normalization/case folding, exact
name and name-phrase boosts, and deterministic weighted term overlap. The order
of equal scores is deterministic. Exact spelling is returned for dispatch;
matching never merges names or establishes semantic uniqueness.

For example, searching `Alice lunch` ranks that exact worker first, while
`Alice contract` selects the separate contract worker. A dormant worker absent
from the recent list remains findable. A successful empty lookup reports
`status: ok` and zero matches. Invalid input or unavailable roster/metadata
returns a tool error, preserving the distinction from no matches.

## Output and creation limits

| Component | Server limit |
| --- | --- |
| Recent roster | At most 5 entries and 2,000 characters, including count/guidance text. |
| Lookup query | First 256 characters; truncation is reported. |
| Lookup results | Requested count clamped to 1–5. |
| Lookup payload | At most 3,500 JSON characters. |
| Formatted lookup tool result | At most 4,000 characters; original arguments are not echoed. |

Descriptions shorten before names are omitted, and `descriptions_limited`
reports that shortening. Exact names are never truncated. Counts expose total
workers/matches and omitted entries. An exceptionally large historical name may
not fit a result; it remains stored and its omitted match is reported. Missing
timestamps are labeled unknown and do not imply known recency. These are text
budgets, not token measurements or whole-model-request limits.

Each bounded interaction loop has its own small backend `DiscoveryState`.
Creating a new name when workers already exist requires a successful lookup in
that loop. A failed/invalid lookup revokes previous success. State is not a tool
argument and cannot be carried over from another turn. The first worker can be
created without lookup, and an exact existing name can be reused directly.
This enforces an attempt at discovery; it does not prove that a new task is
semantically unique.

Creation reloads authoritative membership, rechecks the guard, and rejects
filename-slug collisions under a short local lock. It also rejects a new name
whose expected log file already exists without a roster owner. Repeated exact
names reuse the existing worker. New names must contain 1–200 characters.
Historical collisions are reported on candidate/recent entries and require
manual reconciliation; no historical log is split or assigned by guessing.

Roster and sidecar replacements are atomic JSON writes. The shared lock protects
updates within the application's single writer process. Cross-process writer
coordination remains outside this release. Lookup errors are no longer swallowed
as empty membership, and invalid roster values are preserved on disk for repair.

## Follow-ups, rebuilds, and clearing

The bounded prompt chooses from the current request and necessary follow-up
evidence. An unrelated topic must not inherit the most recent worker. Exact
callback/trigger names remain in their existing dispatch paths. Genuine draft
and pronoun dependencies remain relevant; competing drafts require resolution.
Lookup does not authorize a send or replace the exact reviewed draft.

`AgentRoster.rebuild_metadata()` resets the sidecar to an empty projection.
Names remain searchable immediately and later assignments refill metadata.
Rebuilding does not modify the roster or original logs. The existing history-clear
route clears the sidecar with membership/history. A late metadata update for an
absent worker is ignored. This does not resolve all pre-existing asynchronous
history-clear/execution races; content-reference handling belongs to Phase 2.

## Verification

`python server/tests/run_tests.py` passes 98 tests, including 20 new discovery
tests. They cover catalog/output caps, dormant workers, exact names and separate
topics, metadata persistence/rebuild, unknown activity, malformed storage,
atomic-write failure, concurrent membership updates, collisions, history clearing,
per-loop creation checks, invalid/forged state, exact history reuse, chat/callback
prompt integration, and metadata updates through the real batch manager.
Existing trigger, confirmation/draft-effect, telemetry, and legacy evaluation
regressions also pass. No live model or Gmail calls were made.

Using the existing fixed catalogs with their name/purpose/activity metadata and
an exact-name query for `Alice lunch` produced these model-free measurements:

| Workers | Legacy roster characters | Bounded roster characters | Shown | Lookup tool-result characters |
| --- | --- | --- | --- | --- |
| 100 | 4,702 | 1,108 | 5 | 1,801 |
| 1,000 | 47,947 | 1,110 | 5 | 1,804 |
| 10,000 | 480,397 | 1,112 | 5 | 1,807 |

Lookup returned five candidates in each case. These verify rendering, lexical
retrieval, and execution plumbing. Scripted tests and prompt-policy checks do
not establish actual model routing quality for topic switches or ambiguous
pronouns. That comparison remains in Phase 3. Conversation/result context is
still handled by the legacy path; Phase 2 adds full input budgeting and source
recovery.
