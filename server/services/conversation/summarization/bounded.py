"""Bounded passes over the existing conversation, with a small resume cursor."""

from datetime import datetime, timezone
import json
import os

from ....content_store import capture_scope, current_capture
from ....context_budget import ContextBudgetError
from ....context_builder import ContextBuilder, validate_tool_calls
from ....inner_context import SourceReader, READ_SCHEMA, INNER_POLICY, INNER_GUIDANCE, MAX_TOOL_CALLS, arguments, prefix
from ....openrouter_client import OpenRouterError, request_chat_completion
from .prompt_builder import build_summarization_prompt
from .state import LogEntry, SummaryState


MAX_SCAN_BYTES = 16 * 1024 * 1024
MAX_ENTRY_BYTES = 8 * 1024 * 1024
MAX_BATCH_ENTRIES = 64
MAX_MODEL_CALLS = 2  # The previous summarizer's two attempts, including source reads.


def _window(log, state, generation, count):
    if log._path.resolve() != log._path.absolute():
        raise ContextBudgetError("Linked conversation sources cannot be summarized")
    rows, scanned = [], 0
    with log._lock:
        try:
            with log._path.open("rb") as handle:
                stat = os.fstat(handle.fileno())
                identity = [stat.st_dev, stat.st_ino]
                if state.source_offset is not None:
                    if state.source_generation != generation or identity != state.source_identity or stat.st_size < state.source_offset:
                        raise ContextBudgetError("Summary cursor belongs to cleared, replaced or truncated history")
                    handle.seek(state.source_offset)
                    index = state.last_index
                else:
                    index = -1
                while len(rows) < count:
                    line = handle.readline(min(MAX_ENTRY_BYTES, MAX_SCAN_BYTES - scanned) + 1)
                    if not line:
                        break
                    scanned += len(line)
                    if len(line) > MAX_ENTRY_BYTES or scanned > MAX_SCAN_BYTES:
                        raise ContextBudgetError("Summary source scan/entry limit reached; cursor was not advanced and original history remains available")
                    parsed = log._parse_line(line.decode("utf-8"))
                    if parsed is None:
                        raise ContextBudgetError("Summary source contains an invalid entry; no progress was committed")
                    index += 1
                    if index > state.last_index:
                        tag, timestamp, payload = parsed
                        rows.append((LogEntry(tag, payload, index, timestamp or None), handle.tell()))
                if index < state.last_index:
                    raise ContextBudgetError("Summary index exceeds the selected history; no replacement history was adopted")
        except FileNotFoundError:
            if state.last_index >= 0:
                raise ContextBudgetError("Summary source is unavailable")
            return [], None
        except UnicodeError as exc:
            raise ContextBudgetError("Summary source is not valid UTF-8") from exc
    return rows, identity


async def summarize_bounded(settings, log, memory):
    threshold, tail = settings.conversation_summary_threshold, max(settings.conversation_summary_tail_size, 0)
    if threshold <= 0:
        return False
    # The existing default threshold is 100. Bound its effective batch/window
    # here so enabling bounded mode works with the existing configuration.
    threshold, tail = min(threshold, MAX_BATCH_ENTRIES), min(tail, MAX_BATCH_ENTRIES)
    with capture_scope("conversation") as capture:
        if capture is None:
            raise ContextBudgetError("Bounded summary capture is unavailable")
        state = memory.load_summary_header()
        rows, identity = _window(log, state, capture.generation, threshold + tail)
        if len(rows) < threshold + tail:
            return False
        # Sources are linked in the resulting memory, not appended into the very
        # conversation being summarized (which would feed the scheduler forever).
        reader = SourceReader(record_reference=lambda reference, kind: None)
        previous = reader.save(state.summary_text, "conversation_summary.previous") if state.summary_text else None
        builder = ContextBuilder(settings=settings, model=settings.summarizer_model, tools=[READ_SCHEMA],
                                 record_reference=reader.record, policy=INNER_POLICY, guidance=INNER_GUIDANCE)
        prepared_entries, entry_refs = [], {}
        for entry, _ in rows[:threshold]:
            payload = entry.payload
            if entry.tag == "content_reference":
                try:
                    saved = json.loads(payload)["reference"]
                    reader.register(saved)
                except (ValueError, KeyError, TypeError) as exc:
                    raise ContextBudgetError("Conversation source reference is invalid; no progress was committed") from exc
                entry_refs[entry.index] = saved
            if len(payload.encode()) > 2048 and entry.tag not in {"user_message", "agent_request"}:
                reference = reader.save(payload, "conversation_summary.entry")
                entry_refs[entry.index] = reference
                payload = prefix(payload, 1024) + f"\nIncomplete entry; full source reference={reference}. Keep this reference for omitted facts."
            prepared_entries.append(LogEntry(entry.tag, payload, entry.index, entry.timestamp))
        size = len(prepared_entries)
        output_limit = min(16384, settings.context_input_tokens // 2)
        while True:
            prompt = build_summarization_prompt(state.summary_text, prepared_entries[:size])
            selected = prepared_entries[:size]
            references = [entry_refs[entry.index] for entry in selected if entry.index in entry_refs]
            if previous:
                references.insert(0, previous)
            system_prompt = prompt.system_prompt + f"\nKeep the briefing within {max(1, output_limit - len(str(references)) - 128)} UTF-8 bytes. Exact drafts/approvals remain in source records; do not reconstruct them."
            try:
                builder.build(system_prompt, prompt.messages)
                break
            except ContextBudgetError:
                if size == 1:
                    raise
                size = max(1, size // 2)
        messages = prompt.messages
        summary = None
        for attempt in range(MAX_MODEL_CALLS):
            system, prepared = builder.build(system_prompt, messages)
            try:
                response = await request_chat_completion(component="summarizer", model=settings.summarizer_model, messages=prepared,
                                                        system=system + "\n\n" + INNER_GUIDANCE, api_key=settings.openrouter_api_key, tools=[READ_SCHEMA])
            except OpenRouterError:
                if attempt + 1 < MAX_MODEL_CALLS:
                    continue
                raise
            assistant = ((response.get("choices") or [{}])[0].get("message") or {})
            calls = assistant.get("tool_calls") or []
            validate_tool_calls(calls)
            if not calls:
                summary = assistant.get("content")
                if (not isinstance(summary, str) or not summary.strip()) and attempt + 1 < MAX_MODEL_CALLS:
                    continue
                break
            if len(calls) > MAX_TOOL_CALLS:
                raise ContextBudgetError("Summary source-read call limit reached")
            messages.append({"role": "assistant", "content": assistant.get("content") or "", "tool_calls": calls})
            for call in calls:
                args = arguments(call["function"].get("arguments"))
                payload = reader.read(args) if call["function"]["name"] == "read_result" else {"status": "error", "error": "Only read_result is executable here"}
                messages.append({"role": "tool", "tool_call_id": call["id"], "content": json.dumps(payload, ensure_ascii=False)})
            reader.prune(messages)
        if not isinstance(summary, str) or not summary.strip():
            raise ContextBudgetError("Summary exhausted its two attempts without a complete briefing; progress was not committed")
        summary = summary.strip()
        if references:
            summary += "\nRecoverable memory sources (not approval): " + ", ".join(references)
        if len(summary.encode()) > output_limit:
            reader.save(summary, "conversation_summary.rejected")
            raise ContextBudgetError("Generated briefing exceeds the bounded memory limit; old memory and cursor were preserved")
        cutoff, offset = rows[size - 1]
        with capture.store._lock:
            capture.store.assert_generation(capture.generation)
            stat = log._path.stat()
            if [stat.st_dev, stat.st_ino] != identity or stat.st_size < offset:
                raise ContextBudgetError("Conversation changed before summary commit")
            memory.write_bounded_summary_state(SummaryState(summary_text=summary, last_index=cutoff.index,
                                                           updated_at=datetime.now(timezone.utc), source_offset=offset,
                                                           source_identity=identity, source_generation=capture.generation),
                                              expected_last_index=state.last_index)
        return True
