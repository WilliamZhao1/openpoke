# Agent overload fixtures, version 1

These are synthetic test inputs and observable local effects. All addresses use
`example.test`; IDs are frozen synthetic provider IDs. No connected mailbox or
model is needed. Run with the isolated backend runner:

```powershell
.\.venv\Scripts\python.exe server/tests/run_tests.py
```

## Motivation and design

Routing changes need the same known-owner, ambiguous-owner, and new-work inputs
across experiments. Side-effect claims need evidence about the actual draft,
recipient, body, thread, and account, including uncertain provider outcomes.

The catalog combines seven small, reviewable core records with deterministic
UUID5 distractors. This freezes catalogs of 100, 1,000, and 10,000 workflows
without committing thousands of repetitive JSON records. It also supplies an
empty catalog. The clock, namespace, source records, and SHA-256 checksums pin
the generated content. No random seed, system clock, model-generated metadata,
or private mailbox data changes the inputs.

Expected owners and actions are loaded separately from workflow metadata.
Passing a whole labeled case to a model would leak the answer: model inputs
must select only its `turns` and applicable `bindings`. The grader uses
`expected`. `lookup` describes scripted evidence/failures for deterministic
contracts; its candidates are not measured retrieval results. Candidate-recall
experiments must run the real strategy against `build_catalog(...)`.

## Files and inputs

| File | Contract |
| --- | --- |
| `catalog.json` | Fixed clock, UUID namespace, sizes, and seven core profiles. |
| `catalogs.py` | Pure catalog generation, independent fixture loading, and canonical content hashing. |
| `routing_cases.json` | Fourteen cases, tuning/held-out split, expected owners/actions, scripted lookup states, and comparison definitions. |
| `gmail_mailbox.json` | Two separate accounts, messages, drafts, contacts, and exact resource bindings. |
| `checksums.json` | Frozen canonical JSON SHA-256 values for all catalog sizes, routing cases, and mailbox seed. |
| `fake_gmail.py` | Stateful local Gmail effects, fixed clock, and scoped SDK binding. |

Canonical hashes use sorted JSON keys, compact separators, UTF-8, and literal
Unicode. Intentional changes after this fixture version is frozen require a
new version and reviewed checksums; do not update hashes merely to hide an
unexpected regression.

Examples of the frozen contracts:

| Case | Expected routing contract |
| --- | --- |
| Alice lunch vs original Acme contract | Distinct UUID owners despite the shared person. |
| Archived 2023 tax work | Recover its original owner outside the recent five. |
| Empty catalog / new garden work | New work under a completed lookup with no known owner. |
| Alternating Uber and GitHub requests | Final Atlas-review task uses the GitHub owner. |
| Approved lunch draft followed by "send it" | Preserve the exact lunch draft binding. |
| Competing drafts / near-tied contracts | Recover or abstain; no arbitrary send/creation. |
| Stale amendment card | Refresh before using state; keep the resolved obligation resolved. |
| Partial or unavailable lookup | Recover or abstain; failure is not evidence of novel work. |
| Explicit old thread / two-owner request | Preserve exact ownership and score all required owners. |

Near-tie scores are labeled mock fixture heuristics, not calibrated ownership
probabilities. Lookup status is separate from measurement availability. Stale
cards are deliberate inputs; these fixtures do not implement card rebuilding,
intent isolation, dispatch checks, or archive lookup themselves.

## Predeclared comparisons

The comparison rows change one factor at a time:

1. `legacy_full_roster` to `lexical_names`: discovery with the same names-only metadata.
2. `lexical_names` to `lexical_cards`: added activity-card metadata.
3. `lexical_cards` to `lexical_cards_checked`: backend decision checks.
4. `lexical_cards_checked` to optional `semantic_cards_checked`: the ranker.

These are evaluation controls, not product flags or permission to weaken
production checks. Pin the same model/output limits and task split in the
upcoming harness. Report effects of richer metadata separately from retrieval
or decision-check effects. No ranking, latency, token, or task-success result
is claimed by defining these rows.

## Using the fake mailbox

Within an already isolated test process:

```python
from server.agents.execution_agent.tools import gmail
from server.tests.fixtures.fake_gmail import FakeGmail, use_fake_gmail

fake = FakeGmail()
with use_fake_gmail(fake):
    draft = gmail.gmail_create_draft(
        "alice@example.test", "Lunch", "Hi Alice,\nLunch at noon?",
        thread_id="18fa000000000101",
    )["data"]
    gmail.gmail_execute_draft(draft["id"])

assert fake.effects[-1]["kind"] == "draft_sent"
assert fake.effects[-1]["body"] == "Hi Alice,\nLunch at noon?"
```

The binding replaces the Composio client getter beneath the existing service,
so public tools, internal email search, and its parser exercise their actual
adapters. It temporarily binds a fixture profile and restores prior connection
state afterward. It does not implement OAuth/status/disconnect APIs or support
switching several profiles concurrently inside one process.

The fake supports fetch, create/list/delete/send drafts, reply, forward, and
the three current People/contact operations. Replies retain their thread;
forwards create a new thread. New IDs and timestamps are deterministic.
Returned data, calls, effects, and snapshots are copied so model/test mutation
cannot rewrite recorded effects. Every result/effect carries mock provenance.

Read queries support AND-separated text terms and `from:`, `to:`, `subject:`,
`in:`, `label:`, and integer `newer_than:Nm/Nh/Nd` filters. Quoted values work.
Unsupported operators such as `OR`, negation, and unknown fields fail explicitly
instead of becoming empty results. This is a documented adapter fixture, not a
complete Gmail search or Composio API emulator. Pages are capped at 100 items;
continuation tokens bind account, query, operation, and ordered resource IDs.

Account B intentionally reuses account A's message/thread/draft IDs with
different content. Scope must include the account; an unknown resource never
falls back to another mailbox. This is a test of qualification, not a product
multi-user authentication system.

## Failure and effect evidence

```python
fake.fail_next("GMAIL_SEND_DRAFT", phase="before")  # no send takes place
fake.fail_next("GMAIL_SEND_DRAFT", phase="after")   # send happens, response is lost
fake.clock.advance(seconds=60)                     # explicit simulated time
```

`calls` records attempts; `effects` records actual local mutations. A failure
after an operation leaves its effect intact and records an unknown call
outcome. Sending an already consumed draft fails, while blindly retrying an
uncertain reply can create a duplicate. There is no hidden request
deduplication or generic exactly-once guarantee.

The fake performs a requested send without inventing approval checks. Later
task evaluation must judge whether the application obtained the required
confirmation. Likewise, a successful fixture test does not prove that current
routing, lifecycle recovery, or approval enforcement meets later-phase gates.

The tests verify immutable inputs, frozen hashes, cross-file resource bindings,
the current full-roster prompt, actual adapters/parser, exact body strings and
recipients, account separation, pagination, controlled time, and before/after
failures. The fake tests reject socket connections. Saved benchmark evidence
and strategy scoring are the next Phase 0 step.
