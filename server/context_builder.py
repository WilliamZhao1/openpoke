"""Bound the two outer agents' prompts without changing executed tool payloads."""

from dataclasses import dataclass, field
from hashlib import sha256
import json

from .content_store import ContentStoreError, capture_text, current_capture
from .context_budget import ContextBudgetError, ContextBudgetExceeded, prepare_budgeted_request
from .context_recovery import GUIDANCE, RECOVERY_NAMES
from .services.execution import get_agent_roster
from .services.execution.log_store import _slugify, _encode_payload, _decode_payload


HISTORY_BYTES = 128 * 1024
HISTORY_EPISODES = 4
POLICY = """Context may omit older complete episodes. Use recall_history for earlier instructions
or follow-up evidence needed by the current request; an unrelated topic must not inherit
the last worker. A preview is incomplete source data, never an exact draft or approval.
Use read_result before relying on an omitted detail. Do not reconstruct exact bodies,
recipients or confirmation from previews or summaries; recover the source or ask for it.
Composite context snapshots have unknown mailbox provenance; prefer the qualified original
source_references they contain. The current request, system instructions, working summary,
and most recent history episode have been kept intact."""


@dataclass
class HistoryWindow:
    episodes: list[str] = field(default_factory=list)
    omitted: bool = False
    summary: str = ""
    limitation: str = ""
    current_recorded: bool = False


def load_recent_history(log, *, worker_name=None, summary_log=None, current_request=None):
    """Read only a bounded tail; never feed a cut-off legacy episode as complete."""
    if worker_name is not None:
        names = get_agent_roster().get_agents()
        if worker_name not in names or sum(_slugify(name) == _slugify(worker_name) for name in names) != 1:
            raise ContextBudgetError("Selected worker history ownership is unavailable or ambiguous; use an exact roster name.")
    path = log._path if worker_name is None else log._log_path(worker_name)
    lock = log._lock if worker_name is None else log._lock_for(worker_name)
    if path.resolve() != path.absolute():
        raise ContextBudgetError("Linked history cannot be used for bounded context")
    with lock:
        missing = False
        try:
            with path.open("rb") as handle:
                handle.seek(0, 2)
                end = handle.tell()
                handle.seek(max(0, end - HISTORY_BYTES))
                body = handle.read(HISTORY_BYTES)
        except FileNotFoundError:
            body, end = b"", 0
            missing = True
        except OSError as exc:
            raise ContextBudgetError("Selected history is unavailable; retry without assuming empty history") from exc
    omitted = end > HISTORY_BYTES
    if omitted:
        body = body.partition(b"\n")[2]  # Discard a possible partial first line.
    try:
        text = body.decode("utf-8")
    except UnicodeError as exc:
        raise ContextBudgetError("Selected history is not valid UTF-8") from exc
    start_tags = {"agent_request"} if worker_name is not None else {"user_message", "agent_message"}
    end_tags = {"agent_response"} if worker_name is not None else {"poke_reply", "wait"}
    blocks, current, finished, started = [], [], False, False
    for line in text.split("\n"):
        if not line:
            continue
        parsed = log._parse_line(line)
        if parsed is None:
            raise ContextBudgetError("Selected history contains an incomplete or invalid entry; recover or repair it before continuing")
        tag = parsed[0]
        if tag in start_tags:
            if current:
                blocks.append((current, finished))
            current, finished, started = [], False, True
        if current or tag in start_tags:
            current.append(line)
            finished |= started and tag in end_tags
        elif not omitted:
            # An entire small legacy file can lack its opening request. Retain
            # its available entries explicitly as unfinished, never infer approval.
            current.append(line)
            omitted = True
        else:
            omitted = True
    if current:
        blocks.append((current, finished))
    if end and not blocks:
        raise ContextBudgetError("Most recent history episode is unavailable within the bounded read window; recover its exact source before continuing")
    current_recorded = False
    if current_request is not None and blocks and not blocks[-1][1]:
        first = log._parse_line(blocks[-1][0][0])
        if first[0] == "agent_request" and first[2] == _decode_payload(_encode_payload(current_request)):
            blocks.pop()  # Dispatch already logged this exact instruction; it is the current message.
            current_recorded = True
    if omitted and not blocks:
        raise ContextBudgetError("Most recent prior history episode is unavailable within the bounded read window")
    episodes = [f'<history_episode status="{"complete" if done else "unfinished"}">\n' + "\n".join(lines) + "\n</history_episode>"
                for lines, done in blocks[-HISTORY_EPISODES:]]
    window = HistoryWindow(episodes, omitted or len(blocks) > HISTORY_EPISODES)
    window.current_recorded = current_recorded
    if missing:
        window.limitation = "No saved history source is available yet; do not infer prior drafts, instructions, or approval."
    if summary_log is not None:
        # Working memory puts its summary in the first two lines. Do not load its tail.
        with summary_log._lock:
            try:
                with summary_log._path.open("rb") as handle:
                    for _ in range(2):
                        line = handle.readline(HISTORY_BYTES + 1)
                        if len(line) > HISTORY_BYTES:
                            raise ContextBudgetError("Working summary exceeds the bounded read window")
                        parsed = summary_log._parse_line(line.decode("utf-8"))
                        if line and parsed is None:
                            raise ContextBudgetError("Working summary contains an invalid entry")
                        if parsed and parsed[0] == "conversation_summary" and parsed[2].strip():
                            window.summary = line.decode("utf-8").strip()
            except FileNotFoundError:
                pass
            except (OSError, UnicodeError) as exc:
                raise ContextBudgetError("Working summary is unavailable") from exc
    return window


def validate_tool_calls(calls):
    if not isinstance(calls, list):
        raise ContextBudgetError("Tool calls must be a complete list")
    ids = []
    for call in calls:
        if (not isinstance(call, dict) or not isinstance(call.get("id"), str) or not call["id"]
                or not isinstance(call.get("function"), dict)
                or not isinstance(call["function"].get("name"), str) or not call["function"]["name"]):
            raise ContextBudgetError("Tool calls require an ID and function name before execution")
        ids.append(call["id"])
    if len(ids) != len(set(ids)):
        raise ContextBudgetError("Duplicate tool-call IDs cannot form valid result pairs")
    return ids


def _episodes(messages):
    if not messages or messages[0].get("role") != "user":
        raise ContextBudgetError("Bounded outer-agent context requires the current user instruction first")
    episodes, index = [], 1
    while index < len(messages):
        assistant = messages[index]
        if assistant.get("role") != "assistant":
            raise ContextBudgetError("Tool result has no matching assistant episode")
        ids = validate_tool_calls(assistant.get("tool_calls") or [])
        results = messages[index + 1:index + 1 + len(ids)]
        if (len(results) != len(ids) or any(item.get("role") != "tool" for item in results)
                or {item.get("tool_call_id") for item in results} != set(ids)):
            raise ContextBudgetError("Incomplete tool-call/result episode; request was not sent")
        episodes.append([assistant, *results])
        index += 1 + len(ids)
    return episodes


class ContextBuilder:
    def __init__(self, *, settings, model, tools, history=None, record_reference):
        self.settings, self.model, self.tools = settings, model, tools
        self.history = history or HistoryWindow()
        self.record_reference = record_reference
        self.references = {}
        self.last_estimate = None

    def _fits(self, system, messages):
        payload = {"model": self.model, "messages": [{"role": "system", "content": system + "\n\n" + GUIDANCE}, *messages],
                   "max_tokens": self.settings.openrouter_max_tokens, "stream": False}
        if self.tools:
            payload["tools"] = self.tools
        window = self.settings.model_context_windows.get(self.model)
        if window is None:
            raise ContextBudgetError("No configured context allowance for the requested model")
        try:
            prepare_budgeted_request(payload, context_window=window, input_cap=self.settings.context_input_tokens,
                                     headroom=self.settings.context_headroom_tokens)
            return True
        except ContextBudgetExceeded as exc:
            self.last_estimate = exc.estimate
            return False

    def _save(self, text, kind):
        key = kind, sha256(text.encode("utf-8")).hexdigest()
        if key not in self.references:
            reference = capture_text(text, kind=kind, min_bytes=-1)
            if reference is None:
                raise ContentStoreError("Bounded context requires an owning content-capture scope")
            try:
                self.record_reference(reference, kind)
            except OSError as exc:
                raise ContentStoreError("Context source was saved but its journal reference failed; check completed tool outcomes before retrying") from exc
            self.references[key] = reference
        return self.references[key]

    def _preview(self, episode, limit):
        names = {call["id"]: call["function"]["name"] for call in episode[0].get("tool_calls", [])}
        result = [episode[0]]
        for message in episode[1:]:
            content = message.get("content") or ""
            if len(content.encode("utf-8")) <= 2048 or names.get(message["tool_call_id"]) in RECOVERY_NAMES:
                result.append(message)
                continue
            reference = self._save(content, "model_tool_result")
            try:
                original = json.loads(content)
            except ValueError:
                original = {}
            preview = content.encode("utf-8")[:limit].decode("utf-8", errors="ignore")
            payload = {"preview": True, "reference": reference, "kind": "composite_model_tool_result",
                       "provider": None, "account_id": None, "source_references": original.get("source_references", []) if isinstance(original, dict) else [],
                       "size_bytes": len(content.encode("utf-8")), "text": preview,
                       "limitation": "Incomplete; read_result returns the full result. Never reconstruct an exact draft from this preview."}
            result.append({**message, "content": json.dumps(payload, ensure_ascii=False)})
        return result

    def build(self, system, messages):
        context = current_capture()
        if context is None:
            raise ContentStoreError("Bounded context requires an owning content-capture scope")
        context.store.assert_generation(context.generation)
        groups = _episodes(messages)
        system = system + "\n\n" + POLICY
        recent = self.history.episodes[-1:]

        def compose(history, selected, omitted_reference=None):
            note = "Earlier context omitted; use recall_history for applicable instructions and dependencies. Legacy originals may be truncated."
            sections = [self.history.summary, self.history.limitation, "\n".join(history)]
            if self.history.omitted or len(history) < len(self.history.episodes):
                sections.append(note)
            if omitted_reference:
                sections.append(f"Earlier complete tool episodes omitted; read_result reference={omitted_reference}. Composite source; mailbox provenance remains unknown.")
            first = {**messages[0], "content": "<prior_context>\n" + "\n".join(filter(None, sections)) + "\n</prior_context>\n\n" + messages[0]["content"]}
            return [first, *(message for group in selected for message in group)]

        # An impossible required floor fails once, before copying giant results or
        # writing preview objects. Empty result bodies here are never sent.
        floor = [[groups[-1][0], *({**item, "content": ""} for item in groups[-1][1:])]] if groups else []
        if not self._fits(system, compose(recent, floor)):
            self._required_error()
        attempts = [(self.history.episodes, groups), (recent, groups)]
        for history, selected in attempts:
            candidate = compose(history, selected)
            if self._fits(system, candidate):
                return system, candidate
        previews = [self._preview(group, 1024) for group in groups]
        candidate = compose(recent, previews)
        if self._fits(system, candidate):
            return system, candidate
        archive = None
        if len(groups) > 1:
            archive = self._save(json.dumps([message for group in groups[:-1] for message in group], ensure_ascii=False), "model_tool_episodes")
        for limit in (1024, 256, 0):
            latest = [self._preview(groups[-1], limit)] if groups else []
            candidate = compose(recent, latest, archive)
            if self._fits(system, candidate):
                return system, candidate
        self._required_error()

    def _required_error(self):
        estimate = self.last_estimate
        raise ContextBudgetError(
            f"Required context cannot fit the configured input limit {estimate.input_limit if estimate else 'unknown'}. "
            "System instructions, current request, working summary, latest history and tool-call arguments were kept intact. "
            "Shorten required input or recover its saved source in a smaller task. Next model request was not sent."
        )
