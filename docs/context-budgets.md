# Shared context budgeting and provider preflight

This is the first slice of revised Phase 2. It checks complete text requests at
the shared provider boundary. It does not yet trim histories, build previews,
save omitted results, or expose recovery tools. Oversized requests fail locally
with a clear error rather than being shortened silently.

## Motivation and old behavior

The shared provider client previously reserved `max_tokens` for output but did
not check the size of instructions, history, current messages, or tool schemas
and results. A small outer response could still hide an oversized inner email
search or classifier request. Context capacity was not configured separately
from output size.

`server/context_budget.py` now provides the reusable budget check. The provider
client applies it immediately before HTTP setup on every bounded-mode call.
Interaction, execution, email search, summarization, and classification all
already use that client, so their inner iterations pass through the same guard.

## Configuration

The default remains `legacy` during development, preserving the comparison
request path. To opt in, configure these before startup and restart:

```dotenv
OPENPOKE_CONTEXT_STRATEGY=bounded
OPENPOKE_MODEL_CONTEXT_WINDOWS={"your-model-id":65536}
OPENPOKE_CONTEXT_INPUT_TOKENS=32768
OPENPOKE_CONTEXT_HEADROOM_TOKENS=1024
```

Replace the placeholder with every selected model's exact ID and an independently
verified context allowance. It can be lower than the provider's capacity.
There is no built-in capacity guess, automatic model lookup, or inference from
`OPENROUTER_MAX_TOKENS`. Model metadata includes the published context length
and tokenizer family; inspect the relevant provider/model constraints using
[OpenRouter's model metadata](https://openrouter.ai/docs/api/api-reference/models/list-all-models-and-their-properties).

Startup validates the mode, positive integer allowances/input cap, nonnegative
headroom, coverage of all five configured model selections, and space for input
after output reservation and headroom. Invalid JSON/numbers are rejected rather
than replaced with defaults. A dynamically requested model without an allowance
also fails preflight; it does not inherit another model's capacity.

`OPENPOKE_WORKER_DISCOVERY=bounded` is independent and remains useful for capping
the roster. Context preflight does not automatically enable discovery. The
existing evaluation command and test runner pin the legacy strategy and budget
settings before application imports, even if the caller's environment enables
bounded mode or contains incompatible budget configuration.

## Accounting and examples

The effective input limit for the requested model is:

```text
min(configured input cap, model context allowance - output reservation - headroom)
```

Output reservation is the actual `max_tokens` sent to OpenRouter. The same
configured output limit is preserved; this check does not reduce it to make
requests fit. OpenRouter constrains output against the space left after input,
as described in its [request parameters](https://github.com/OpenRouterTeam/docs/blob/main/api_reference/parameters.mdx).

For a hypothetical allowance of 1,000, output reservation of 200, headroom of
100, and input cap of 800, the effective input limit is **700**. An input estimate
of 700 passes; 701 fails. Changing output reservation to 300 lowers the input
limit to 600. A window that leaves no input space is a configuration error.

The installed runtime has no supported native tokenizer for its selected models.
The helper therefore labels its method `utf8_json_bytes_estimate`. It counts
every UTF-8 byte of the serialized request as an estimated token, plus 32 units
of fixed framing, 16 per message, and 32 per tool schema. The complete JSON
includes system instructions, current messages/callbacks, history, assistant
tool calls and arguments, tool results, schemas, and request metadata. This
conservative planning estimate can reject requests a native tokenizer would fit.
It is not an exact count or a universal upper bound on provider tokenization.
Headroom remains necessary, and model-native usage stays separate.

UTF-8 sizing accounts for multilingual text without assuming four characters
per token. For example, twenty `旅` characters consume forty more UTF-8 bytes
than twenty ASCII `a` characters. Structured image/audio/file content is rejected
explicitly because text sizing cannot account for its model-specific cost.

The helper returns a content-free `BudgetEstimate` and the exact serialized wire
bytes. When accepted, the client sends those immutable bytes. A caller changing
its message list while the HTTP client opens cannot enlarge the checked request.
Messages, tool-call/result pairs, draft bodies, and schemas are otherwise retained
unchanged. The provider response/usage return contract is unchanged too.

## Failure behavior

`ContextBudgetExceeded` carries the numeric estimate and limits, with an error
that identifies the estimation method and says the request was not sent.
Unsupported input or missing/invalid allowances raise `ContextBudgetError`.
Neither error embeds prompt text, tool results, or credentials. No HTTP client
is opened for a rejected request. There is no fallback to an unbounded request,
automatic trimming, output-limit reduction, or retry loop.

Summarization does not retry a deterministic budget rejection. Existing agent
callers return their normal failed-execution result; the classifier keeps its
existing failure/logging return contract. An accepted request's later provider
or network errors retain their original handling.

The existing telemetry schema remains in place. Local rejections use the
`context_budget` failure category; provider usage and HTTP status are marked
not applicable with `request_not_sent`. An accepted response with missing usage
still has unknown usage. Local estimates never populate provider token fields,
and real zero counts remain zero. The estimate object can be used by subsequent
context builders without adding a new observation framework.

## Verification and remaining work

`python server/tests/run_tests.py` passes all 114 tests, including 16 new context
budget tests. Checks cover every input section, exact boundaries, output/headroom
arithmetic, multilingual text, configuration failures, unsupported media, no-HTTP
rejection, immutable wire bytes, unchanged accepted content/output, provider-usage
separation, growing tool-result input, no summarizer retry, and all five real
model-calling paths reaching the shared guard. The existing baseline CLI tests
also run with conflicting bounded settings in the caller environment to verify
legacy isolation. All data and provider responses are temporary or mocked.

Phase 2 remains in progress. The next slice preserves full oversized content in
a small owner/account-qualified content store before introducing previews.
Bounded episode construction, source-reference paging, exact draft-by-reference
adapters, and cumulative recovery limits follow. No source is deleted or
shortened by this preflight, and it does not establish routing quality, native
token accuracy, or completion of the full bounded-context release.
