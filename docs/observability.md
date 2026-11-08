# Runtime telemetry

Phase 0 adds metadata to the existing `openpoke.server` logger. Lines whose
message starts with `telemetry ` contain a JSON object. A logging handler can
also read that object from `LogRecord.telemetry`.

## Model usage and timing

Every attempt through `request_chat_completion` emits `model_call.completed`,
including failed and cancelled attempts. The five current callers identify
themselves as `interaction`, `execution`, `search_email`, `summarizer`, and
`email_classifier`.

| Field | Meaning |
| --- | --- |
| `model` | Requested configured model identifier. |
| `input_tokens` | Provider-reported `usage.prompt_tokens`, or `null` when unknown/invalid. |
| `output_tokens` | Provider-reported `usage.completion_tokens`, or `null` when unknown/invalid. |
| `usage_complete` | Both counts are known; actual zero counts remain zero. |
| `elapsed_ms` | Monotonic elapsed time for this attempt, including client setup and response decoding. |
| `status_code` | HTTP response status, or `null` when no response was received. |
| `outcome` | `succeeded` or `failed` for this attempt. |
| `failure_category` | Fixed category, or `null` on success. |

Model failure categories are `configuration`, `authentication`, `rate_limit`,
`provider_request`, `provider_server`, `provider_error`, `timeout`, `network`,
`invalid_response`, `cancelled`, and `internal`. An HTTP-success error envelope
or missing choices is measured as a failure while retaining the original raw
return contract. A successful model request is not evidence that the task was
performed correctly.

Example fields from an illustrative event (other metadata omitted):

```json
{
  "event": "model_call.completed",
  "component": "execution",
  "model": "configured-provider/model",
  "input_tokens": 120,
  "output_tokens": 15,
  "usage_complete": true,
  "elapsed_ms": 250.5,
  "status_code": 200,
  "outcome": "succeeded",
  "failure_category": null
}
```

If the provider omits usage, both token fields are `null` and `usage_complete`
is false. No estimated tokens or inferred prices fill those gaps. Existing
model selection, output limits, request bodies, and retry behavior are retained.

## Correlation across asynchronous tasks

Correlation uses immutable metadata in Python `ContextVar` scopes. Spawned
asyncio tasks inherit the current scope; leaving a scope restores its caller.

| Identifier | Meaning |
| --- | --- |
| `request_id` | Backend UUID for a chat request, fired trigger, or Gmail poll. |
| `turn_id` | One interaction turn; a worker callback gets a new turn. |
| `parent_turn_id` | Originating turn when a callback starts another turn. |
| `batch_id` | Existing execution batch UUID. |
| `run_id` | Existing execution request UUID, scoped to a worker activation. |
| `call_id` | Separate UUID for each model-call attempt. |
| `trigger_id` | Persisted trigger ID when scheduled work is the origin. |

`origin` distinguishes `chat`, `trigger`, `gmail`, `internal`, and combined
`batch` work. IDs are telemetry for the current execution; durable workflow
identity and run recovery are later implementation phases.

A typical request produces this sequence, with other model/tool events between
the listed entries:

```text
chat.accepted          request R, turn T
execution.dispatched   request R, turn T, batch B, run A
tool.completed         request R, turn T, batch B, run A
callback.dispatched    request R, turn T, batch B, parents [run A]
callback.received      request R, turn U, parent turn T, batch B
reply.recorded         request R, turn U, batch B
callback.completed     request R, turn U, batch B
```

The letters abbreviate actual UUIDs. `chat.completed` ends initial interaction
processing and may precede worker completion. HTTP 202 still means accepted;
`reply.recorded` means the reply was stored for chat history, not that a browser
has rendered it.

The existing batch manager can aggregate several requests. Such a callback
gets a separate `batch` trace, and `callback.dispatched.parents` preserves every
originating request/turn/run link. Batching and routing policy are unchanged.
Triggers and Gmail polling carry their trace through worker/model calls and
notification callbacks. Trigger completion includes updating trigger state.

## Content boundaries and storage

Telemetry includes metadata only: fixed component/tool names, configured model
IDs, backend identifiers, counts, timing, and fixed outcome categories. It does
not copy prompts, email content, recipients, worker names, tool arguments or
results, credentials, provider error bodies, or exception messages. Unknown
metric field names are ignored. This applies to the new telemetry events;
existing application diagnostics and conversation journals keep their formats.

Events use the existing logging output; this step adds no metrics database or
log-retention service. Capture the process logs if evidence must survive a
restart. If the telemetry sink raises, a generic message is attempted on stderr
and the model/tool outcome is preserved.

## Deterministic validation

Run `python server/tests/run_tests.py` from the repository root. Tests use
temporary storage, `httpx.MockTransport`, and a local mocked tool. They cover
the complete chat/worker/callback/reply chain, scheduled work, Gmail
classification/notification, all five model components, concurrent requests,
combined batches, usage gaps, provider failures, timeouts, cancellation, and a
broken telemetry sink. No live email or model calls are required.
