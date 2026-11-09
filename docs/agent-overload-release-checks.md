# Bounded strategy application release checks

Updated: 2026-11-09. Phase 3 is complete: the focused comparison, draft-ID
follow-up, application checks and findings are recorded, and **bounded discovery
and context are now the defaults**. Explicit legacy settings remain supported.

## Motivation, old behavior, and changes

The existing tests verified individual agents, content recovery, and draft
adapters. The live comparison exercised a small approved-draft flow, but its
review was seeded directly in backend history. Those checks did not establish
that the full public HTTP/proxy/render path preserved a large review, that real
stored triggers retained their owners, or that startup/shutdown released their
resources.

The new backend checks use the actual FastAPI app through ASGI HTTP, actual
Interaction/Execution Agent loops, the batch manager and callbacks, existing
local stores, and the existing fake Gmail backend. Model responses are scripted
and every request passes full-request preflight. Source and trigger data are
disposable. Tests poll the real scheduler with controlled times instead of
waiting for wall-clock reminders. The watcher is stubbed in the lifecycle test;
its classification/polling behavior remains covered by retained tests.

Two integration issues were found and fixed:

- **Exact review text:** `web/app/page.tsx` decoded literal backslash sequences
  again after JSON parsing. For example, a body containing the characters `\n`
  was displayed as a newline; `\t`, `\r`, and doubled backslashes also changed.
  The history mapping now keeps `message.content` unchanged, and optimistic user
  text uses the same submitted string. Normal JSON decoding and React escaping
  already provide the required transport/render behavior. The mapper is shared
  by the existing polling paths and directly testable.
- **Trigger connection lifetime:** the existing SQLite transaction context did
  not close its connection. The new lifespan check left `triggers.db` open on
  Windows. `TriggerStore._connect` now preserves transaction handling and closes
  in `finally`, including statement failure. This fixes resource lifetime in
  the existing trigger store; it changes no schema or scheduling policy.

Frontend checks use Node's built-in test runner, the installed TypeScript
compiler, React's renderer, and the actual history/proxy/component source.
No browser test framework or new dependency was added. A small Next ESLint
configuration makes the existing lint command run without an interactive setup
prompt. These choices reuse the application paths and keep the checks local.

## Results

| Check | Result and evidence |
| --- | --- |
| Public chat acceptance | Invalid input returns 400/422 without a model call. A valid POST returns 202 while the provider is still blocked; completion later appears through GET history. |
| Public chat failure | A scripted provider 503 still accepts asynchronously, then stores the existing user-visible failure reply rather than leaving the UI waiting or exposing provider diagnostics. |
| Large draft review | A body over 256 KiB, with Unicode, real CRLF, literal backslashes, middle/end details and trailing spaces, survives referenced creation and callback into complete HTTP history. Only creation occurs before confirmation. |
| Separate confirmation and send | A second HTTP user turn confirms that review. Context carries the verified reference rather than repeating the huge body. Fake Gmail records one original exact-body send with the original recipient, Cc/Bcc, and no recreation. |
| Frontend/proxy review | The actual proxy GET and history mapper preserve large JSON content. The actual chat component renders an entire review over 300 KiB with escaped HTML text. Literal escapes and whitespace remain unchanged. |
| Frontend chat/clear proxies | The actual POST proxy preserves input text and upstream 202. The history proxy forwards DELETE and preserves its successful response. These proxy tests stub only upstream fetch. |
| Trigger ownership | A worker creates a real SQLite-backed trigger. Another worker cannot pause it or list it. Due execution uses its exact owner and reaches the actual callback/chat path. No new worker is created. |
| Trigger scheduling | A pre-due poll does nothing; repeated polls during an in-flight run admit it once. One-shot completion clears its next time, and a separate recurring owner's trigger advances to its next day. |
| Trigger correlation | Each fired trigger retains one request correlation and trigger ID through worker execution and the asynchronous callback. |
| Startup/shutdown and connection release | The app lifespan starts/stops the real scheduler and watcher lifecycle interface; health responds. Actual SQLite connections are closed after both a successful read and an SQL binding error. |
| History clearing | HTTP DELETE clears conversation/memory, worker logs/roster/metadata, triggers and managed source generation. An unrelated file survives. Old sources fail and a late generation-bound batch callback adds neither a model request nor history. |
| Legacy data preservation | Switching both flags to legacy leaves the full HTTP review unchanged; switching back permits its existing reference to continue through confirmation. Clearing is a separate explicit operation. |

Commands run from the repository root:

```powershell
.\.venv\Scripts\python.exe server/tests/run_tests.py
npm.cmd --prefix web test
npm.cmd --prefix web run lint -- --no-cache
.\web\node_modules\.bin\tsc.cmd --project web/tsconfig.json --noEmit
npm.cmd --prefix web run build
git diff --check
```

The application checkpoint passed **234 backend tests** (228 retained plus six
application/resource checks), **5 frontend checks**, clean lint/type checking,
and a successful production build. After promotion, the backend suite passes
**241 tests**, including seven new default/configuration checks described below.
No live model or real Gmail request was made in the application or promotion steps.
Scripted checks establish integration behavior; the [separate live evidence](agent-overload-comparison.md)
retains its actual model decisions and mock Gmail effects.

## Release findings and limits

The first live comparison had correct owner/action selection but failed bounded
draft sending because of provider-ID/reference confusion. The targeted guidance
fix and live rerun passed; the original failed evidence remains preserved.
The final application checks exposed the review-text rewrite and trigger
connection leak above, and now pass with those fixes.

These results supported default promotion. They do not prove
deterministic model compliance, universal routing accuracy, lower cost, or native
token-count accuracy. The original 100-worker live sample used more total calls,
tokens and reported cost in bounded mode, despite a smaller roster; the focused
draft recheck is a different sample and must not be substituted for that result.
Lexical matching and explicit recovery remain the implemented retrieval strategy.
Some large required instructions or old histories still fail explicitly rather
than being shortened or silently loaded without a bound.

The application checks use ASGI and component rendering; they do not automate
browser clicks or measure visual scroll performance. Periodic watcher behavior
is not rerun against a live mailbox. The clear check covers a completed flow and
a late generation-bound callback; it does not cancel already-running external
actions or resolve all existing unbound/legacy journal races. Durable replay,
cross-process execution coordination, automatic source retention, and universal
approval state remain outside this release. Existing confirmation stays an
agent-policy workflow, not a new durable approval ledger.

## Configuration and disabling without deleting data

Both strategies now default to `bounded` when their settings are absent. The
bundled `anthropic/claude-sonnet-4.6` profile ships with the same **65,536 planning
allowance** used in the release comparison; input cap remains 32,768 and headroom
1,024. The shipped allowance is a local application policy, not a claim about
the provider's published capacity or a guessed capacity for other models.

The bundled model needs no extra budget setting. For custom models, configure
the selected model and a complete allowance map before restarting:

```dotenv
OPENPOKE_WORKER_DISCOVERY=bounded
OPENPOKE_CONTEXT_STRATEGY=bounded
OPENROUTER_MODEL=your-exact-model-id
OPENPOKE_MODEL_CONTEXT_WINDOWS={"your-exact-model-id":65536}
OPENPOKE_CONTEXT_INPUT_TOKENS=32768
OPENPOKE_CONTEXT_HEADROOM_TOKENS=1024
```

Supply independently chosen allowances for every configured model ID, not just
the placeholder. An explicit map replaces the bundled map instead of merging
with it; an empty map does not restore defaults. Unknown/custom IDs without
allowances fail startup, and invalid configuration never selects an unbounded
fallback. Output reservation and headroom must also fit. The numbers above are
example planning allowances, not provider specifications. See
[context configuration](context-budgets.md) and [worker discovery](worker-discovery.md).

To disable the new strategies, set these before startup and restart the backend:

```dotenv
OPENPOKE_WORKER_DISCOVERY=legacy
OPENPOKE_CONTEXT_STRATEGY=legacy
```

Keep the same `OPENPOKE_DATA_DIR` and existing valid allowance settings. No
history clear, data deletion, migration, or source rewrite is required. Existing
conversation/worker logs, metadata, triggers and immutable sources stay on disk;
re-enabling bounded mode can recover sources that have not been cleared. Legacy
mode intentionally restores its original prompt behavior and may exceed provider
context limits on large inputs. There is no automatic fallback that loads a full
unbounded roster/history into a bounded request.

If either flag was already explicitly set to `legacy`, that choice stays in
effect after updating; remove it or set `bounded` to use the new default. Existing
`.env` files and runtime data are not rewritten by promotion.

## Default promotion validation and plan completion

Previously both strategy defaults were legacy and the default model allowance
map was empty. Simply flipping the flags would make normal bundled-model startup
fail validation. Promotion therefore ships the previously exercised allowance
only for the bundled model. It does not copy that value to an arbitrary
`OPENROUTER_MODEL` or weaken per-model checks. An absent configuration can start
with the tested bundled profile, while custom settings remain deliberate.

Seven new backend checks verify:

- bounded settings and independent per-instance bundled allowance maps;
- explicit allowance coverage for each of the five model selections;
- independent legacy opt-outs and constructor/environment precedence;
- rejection of invalid/empty maps and incompatible reservations without fallback;
- fresh default startup with bounded schemas, a capped 100-worker roster, a real
  lookup loop, and final provider preflight on every mocked model request;
- custom-model startup failing before store creation, then succeeding with its
  explicit map;
- fresh-process legacy opt-out and re-enable preserving every existing profile
  file hash and saved source reference.

Those subprocesses disable private `.env` loading, use disposable roots/dummy
credentials, and reject network connections. The ordinary test runner and
evaluation CLI still pin their legacy controls explicitly; promoting production
defaults does not relabel or regenerate the frozen model-free baseline or live
comparison artifacts. The earlier live results remain the measured evidence;
no new quality/cost claim follows from changing a default.

The reduced-scope plan's first release implementation is complete. Deferred
infrastructure and remaining product limitations stay outside this release;
future work should follow the plan's demonstrated-need triggers.
