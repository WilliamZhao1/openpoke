"""Small paired comparison using the existing agents, fixtures and graders."""

import asyncio
from contextlib import ExitStack
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import logging
import math
from time import perf_counter
from types import SimpleNamespace
from unittest.mock import patch

import httpx

from .contracts import EvaluationConfigError, HERE, ROOT, digest, grade_draft_effects, grade_routing, observation, read_json
from .engine import TelemetryCapture, capture_tasks, drain, runtime_source_paths, seed_roster, write_json
from server.agents.execution_agent.batch_manager import ExecutionBatchManager
from server.agents.interaction_agent import agent, tools
from server.agents.interaction_agent.runtime import InteractionAgentRuntime
from server.config import get_settings
from server.content_store import ContentStore
from server.data_paths import get_data_dir
from server.logging_config import logger
from server.models import ChatMessage, ChatRequest
from server.openrouter_client import client
from server.services.conversation import get_conversation_log
from server.services.conversation.chat_handler import handle_chat_request
from server.services.execution import get_agent_roster, get_execution_agent_logs
from server.services.execution.ranking import get_ranker, ranker_parameters
from server.tests.fixtures.catalogs import build_catalog, load_fixture, routing_cases
from server.tests.fixtures.fake_gmail import FakeGmail, use_fake_gmail


DEFAULT_CASES = ("alice-contract", "dormant-owner", "genuinely-new", "competing-drafts", "two-owners")
SUPPORTED_CASES = {*DEFAULT_CASES, "alice-lunch", "alternating-topics", "empty-catalog"}


def usage_total(requests, field, mode):
    values = [row.get("usage", {}).get(field) for row in requests]
    valid = [value for value in values if type(value) in {int, float} and math.isfinite(value) and value >= 0
             and (field == "cost" or type(value) is int)]
    complete = bool(values) and len(valid) == len(values)
    return {**observation(sum(valid) if complete else None, source="provider_usage", source_mode=mode,
                          availability="available" if complete else "unavailable", reason=None if complete else "usage_missing_or_invalid"),
            "reported_calls": len(valid), "attempted_http_calls": len(values), "reported_subtotal": sum(valid) if valid else None}


class ProviderCapture:
    """Record synthetic JSON payloads, never headers; cap actual HTTP requests."""
    def __init__(self, max_calls, request_interval=0):
        self.max_calls, self.requests = max_calls, []
        self.request_interval, self.next_request = request_interval, 0
        self.lock = asyncio.Lock()

    async def on_request(self, request):
        if str(request.url) != client.OpenRouterBaseURL + "/chat/completions":
            raise client.OpenRouterError("Comparison only permits the pinned model endpoint")
        if len(request.content) > 256 * 1024:
            raise client.OpenRouterError("Comparison request exceeds its 256 KiB evaluation cap")
        async with self.lock:
            if len(self.requests) >= self.max_calls:
                raise client.OpenRouterError("Comparison HTTP request limit reached")
            delay = self.next_request - perf_counter()
            if delay > 0:
                await asyncio.sleep(delay)
            self.next_request = perf_counter() + self.request_interval
            row = {"payload": json.loads(request.content), "status_code": None}
            request.extensions["comparison_row"] = row
            self.requests.append(row)

    async def on_response(self, response):
        row = response.request.extensions["comparison_row"]
        row["status_code"] = response.status_code
        await response.aread()
        try:
            value = response.json()
        except ValueError:
            return
        if isinstance(value, dict):
            # Error bodies may echo arbitrary provider diagnostics. Keep status,
            # decisions and numeric usage, without exporting error text/headers.
            if response.is_success:
                row["choices"] = value.get("choices")
            usage = value.get("usage")
            if isinstance(usage, dict):
                row["usage"] = {key: usage[key] for key in ("prompt_tokens", "completion_tokens", "cost")
                                if type(usage.get(key)) in {int, float} and math.isfinite(usage[key])}

    def factory(self, original):
        def create(*args, **kwargs):
            return original(*args, **kwargs, event_hooks={"request": [self.on_request], "response": [self.on_response]})
        return create


class DispatchRecorder:
    def __init__(self, delegate=None):
        self.delegate, self.calls = delegate, []

    async def execute_agent(self, agent_name, instructions):
        self.calls.append({"agent_name": agent_name, "instructions": instructions})
        if self.delegate is not None:
            return await self.delegate.execute_agent(agent_name, instructions)
        # Routing cases observe successful public dispatch, not worker outcomes.
        return SimpleNamespace(success=True)


def grade_dispatches(expected, catalog, dispatches, mode, failed):
    names = list(dict.fromkeys(call["agent_name"] for call in dispatches))
    by_name = {row["display_name"]: row["workflow_id"] for row in catalog}
    actual = {"action": "create_new" if any(name not in by_name for name in names) else "reuse" if names else "abstain",
              "workflow_ids": [by_name[name] for name in names if name in by_name],
              "created_names": [name for name in names if name not in by_name], "reused_names": [name for name in names if name in by_name]}
    # A later worker/callback error does not erase an observed routing decision.
    return grade_routing(expected, actual if names or not failed else None, source_mode=mode)


def seed_case(catalog, script, smoke):
    ContentStore().clear()
    log, roster, logs = get_conversation_log(), get_agent_roster(), get_execution_agent_logs()
    log.clear()
    logs.clear_all()
    roster.clear()
    seed_roster(roster, catalog)
    metadata = {}
    for row in catalog:
        name = row["display_name"]
        metadata[name] = {"purpose": row["purpose"][:240], "recent_assignment": row["card"]["summary"][:240],
                          "last_activity": row["last_activity_at"]}
        logs.record_request(name, row["purpose"])
        logs.record_agent_response(name, row["card"]["summary"] + "\nSaved resources: " + json.dumps(row["resource_refs"]))
    write_json(roster.metadata_path, metadata)
    if smoke:
        log.record_reply(script["input"]["review"])
        logs.record_agent_response("Alice lunch", "User review of the pending draft:\n" + script["input"]["review"])


def scripted_response(script, request):
    payload = json.loads(request.content)
    names = {tool["function"]["name"] for tool in payload.get("tools", [])}
    last = payload["messages"][-1]
    if "send_message_to_agent" in names:
        if "<new_agent_message>" in last.get("content", ""):
            key = "interaction_callback"
        else:
            key = "interaction_after_tools" if last["role"] == "tool" else "interaction_initial"
    elif "gmail_execute_draft" in names:
        key = "execution_after_tools" if last["role"] == "tool" else "execution_initial"
    else:
        raise RuntimeError("Unexpected component for the frozen smoke script")
    return httpx.Response(200, json={"choices": [{"message": deepcopy(script["responses"][key])}]})


async def run_case(case, catalog, strategy, script, provider, mode, timeout, *, smoke=False):
    seed_case(catalog, script, smoke)
    fake, capture = FakeGmail(), TelemetryCapture()
    manager = ExecutionBatchManager() if smoke else None
    dispatcher = DispatchRecorder(manager)
    log = get_conversation_log()
    if not smoke:
        for turn in case["turns"][:-1]:
            (log.record_user_message if turn["role"] == "user" else log.record_reply)(turn["content"])
    rendered = agent._render_active_agents()
    first = len(provider.requests)
    logger.addHandler(capture)
    started = perf_counter()
    result, accepted, failure = None, None, None
    try:
        with use_fake_gmail(fake), patch.object(tools, "_EXECUTION_BATCH_MANAGER", dispatcher):
            async with capture_tasks() as tasks:
                async def execute():
                    nonlocal result, accepted
                    if smoke:
                        response = await handle_chat_request(ChatRequest(messages=[ChatMessage(role="user", content=script["input"]["request"])]))
                        accepted = response.status_code == 202
                    else:
                        result = await InteractionAgentRuntime().execute(case["turns"][-1]["content"])
                    await drain(tasks)
                await asyncio.wait_for(execute(), timeout=timeout)
    except Exception as exc:
        failure = type(exc).__name__
    finally:
        if manager is not None:
            await manager.shutdown()
        logger.removeHandler(capture)
    requests = provider.requests[first:]
    events = capture.events
    model_events = [event for event in events if event["event"] == "model_call.completed"]
    failed_events = [event for event in events if event.get("outcome") == "failed"
                     and event["event"] in {"chat.completed", "callback.completed", "execution.completed"}]
    if failure is None and (failed_events or result is not None and not result.success
                            or any(event["provider_mode"] != mode for event in model_events)):
        failure = "runtime_or_provider_failure"
    routing_grade = grade_dispatches(script["expected"] if smoke else case["expected"], catalog, dispatcher.calls, mode, failure)
    effects = grade_draft_effects(script["expected"], fake.effects) if smoke else None
    return {"case_id": "approved-draft" if smoke else case["id"], "strategy": strategy, "catalog_size": len(catalog),
            "split": "scripted_contract" if smoke else case["split"], "decision_mode": mode, "gmail_mode": "mock",
            "scope": "chat_worker_callback_effects" if smoke else "routing_only_workers_not_executed",
            "failure": failure, "chat_accepted": accepted, "dispatches": dispatcher.calls,
            "model_errors": sum(event.get("outcome") == "failed" for event in model_events),
            "tool_errors": sum(event["event"] == "tool.completed" and event.get("outcome") == "failed" for event in events),
            "routing_grade": routing_grade, "effect_grade": effects,
            "callback_received": any(event["event"] == "callback.received" for event in events),
            "roster_shape": {"visible_workers": rendered.count("<agent name="), "characters": len(rendered), "utf8_bytes": len(rendered.encode())},
            "measurements": {"model_call_attempts": len(model_events), "http_requests": len(requests),
                             "elapsed_ms": (perf_counter() - started) * 1000,
                             "input_tokens": usage_total(requests, "prompt_tokens", mode),
                             "output_tokens": usage_total(requests, "completion_tokens", mode), "cost": usage_total(requests, "cost", mode)},
            "provider_requests": requests, "telemetry": events,
            "conversation": [{"kind": tag, "content": content} for tag, _, content in log.iter_entries()], "gmail": fake.snapshot()}


async def run_comparison(manifest, sizes, output, data_root, *, mode, cases=None, max_calls=64, timeout=180, request_interval=0, rankers=None):
    if get_data_dir() != data_root.resolve():
        raise EvaluationConfigError("Comparison stores must use the disposable evaluation root")
    selected = list((DEFAULT_CASES if mode == "live" else ("alice-lunch",)) if cases is None else cases)
    if len(set(selected)) != len(selected) or not selected or set(selected) - SUPPORTED_CASES:
        raise EvaluationConfigError("Select unique supported routing cases; see comparison documentation")
    eligible = [case for case in routing_cases() if case["id"] in selected and any((case["catalog"] == "empty") == (size == 0) for size in sizes)]
    if {case["id"] for case in eligible} != set(selected):
        raise EvaluationConfigError("Selected cases require matching empty/nonempty catalog sizes")
    checksums = load_fixture("checksums.json")
    if checksums != manifest["fixture_checksums"] or any(digest(load_fixture(name + ".json")) != checksums[name] for name in ("routing_cases", "gmail_mailbox")):
        raise EvaluationConfigError("Comparison fixture checksums differ from the frozen inputs")
    script = read_json(HERE / "approved_draft.json")
    if digest(script) != manifest["smoke_sha256"]:
        raise EvaluationConfigError("Comparison smoke input differs from the frozen input")
    settings = get_settings()
    if any(getattr(settings, key) != value for key, value in manifest["runtime_settings"].items()):
        raise EvaluationConfigError("Comparison must preserve the pinned model/output/runtime limits")
    catalogs = {size: build_catalog(size) for size in {*sizes, manifest["smoke_catalog_size"]}}
    if any(digest(catalog) != checksums["catalogs"][str(size)] for size, catalog in catalogs.items()):
        raise EvaluationConfigError("Comparison generated catalogs differ from the frozen inputs")
    public = {"schema_version": 1, "profile": "legacy_bounded_comparison_v1", "decision_mode": "live" if mode == "live" else "mock",
              "gmail_mode": "mock", "model": settings.interaction_agent_model, "max_tokens": settings.openrouter_max_tokens,
              "model_context_windows": settings.model_context_windows, "input_cap": settings.context_input_tokens,
              "headroom": settings.context_headroom_tokens, "max_http_requests": max_calls, "case_timeout_seconds": timeout,
              "request_interval_seconds": request_interval, "arm_order": "paired; alternate first strategy by scenario",
              "max_request_bytes": 256 * 1024, "catalog_sizes": sizes, "cases": selected,
              "strategies": ["legacy", "bounded"], "baseline_manifest_sha256": digest(manifest),
              "scope": "combined_discovery_and_context; not a ranker/metadata ablation"}
    if rankers is not None:
        if not rankers or len(set(rankers)) != len(rankers):
            raise EvaluationConfigError("Select unique worker rankers")
        public.update(profile="worker_ranker_agent_comparison_v1", strategies=list(rankers),
                      scope="ranker_only; discovery_and_context_fixed_bounded",
                      arm_order="paired; rotate first ranker by scenario", worker_discovery_strategy="bounded", context_strategy="bounded",
                      ranker_parameters={identifier: ranker_parameters(get_ranker(identifier)) for identifier in rankers})
    write_json(output / "comparison.json", public)
    write_json(output / "inputs.json", {"routing_cases": [case for case in eligible], "smoke_input": script["input"],
                                        "smoke_expected": script["expected"], "fixture_checksums": checksums})
    provider, rows = ProviderCapture(max_calls, request_interval), []
    original_client = httpx.AsyncClient
    original_level, original_propagate = logger.level, logger.propagate
    logger.setLevel(logging.INFO)
    logger.propagate = False
    try:
        with ExitStack() as stack:
            stack.enter_context(patch.object(httpx, "AsyncClient", provider.factory(original_client)))
            if mode == "model-free":
                stack.enter_context(client.use_mock_provider(httpx.MockTransport(lambda request: scripted_response(script, request))))
            jobs = [(case, catalogs[size], False) for size in sizes for case in eligible if (case["catalog"] == "empty") == (size == 0)]
            jobs.append((None, catalogs[manifest["smoke_catalog_size"]], True))
            for index, (case, catalog, smoke) in enumerate(jobs):
                order = (rankers[index % len(rankers):] + rankers[:index % len(rankers)] if rankers is not None
                         else ("legacy", "bounded") if index % 2 == 0 else ("bounded", "legacy"))
                for strategy in order:
                    discovery_strategy = "bounded" if rankers is not None else strategy
                    with (patch.object(settings, "worker_discovery_strategy", discovery_strategy),
                          patch.object(settings, "context_strategy", discovery_strategy),
                          patch.object(settings, "worker_ranker", strategy if rankers is not None else "heuristic_v1")):
                        if len(provider.requests) >= max_calls:
                            rows.append({"case_id": "approved-draft" if smoke else case["id"], "catalog_size": len(catalog), "strategy": strategy,
                                         "decision_mode": public["decision_mode"], "failure": "not_run_request_limit", "routing_grade": {"availability": "unavailable"}})
                        else:
                            rows.append(await run_case(case, catalog, strategy, script, provider, public["decision_mode"], timeout, smoke=smoke))
                        write_json(output / "results.json", rows)  # Keep partial evidence on interruption.
    finally:
        logger.setLevel(original_level)
        logger.propagate = original_propagate
    summary = summarize(rows, public)
    write_json(output / "summary.json", summary)
    sources = {*runtime_source_paths(), "server/context_budget.py", "server/context_builder.py", "server/content_store.py", "server/context_recovery.py", "server/draft_content.py", "server/inner_context.py", "evals/agent_overload/comparison.py"}
    write_json(output / "provenance.json", {"created_at": datetime.now(timezone.utc).isoformat(), "fixture_checksums": checksums,
        "source_sha256_lf_normalized": {path: hashlib.sha256((ROOT / path).read_text(encoding="utf-8").replace("\r\n", "\n").encode()).hexdigest() for path in sorted(sources)}})
    write_report(output, summary)
    write_json(output / "artifacts.json", {path.relative_to(output).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(output.rglob("*")) if path.is_file()})
    return summary


def summarize(rows, public):
    arms = {}
    for strategy in public["strategies"]:
        arm = [row for row in rows if row["strategy"] == strategy]
        routed = [row for row in arm if row["routing_grade"]["availability"] != "unavailable"]
        requests = [request for row in arm for request in row.get("provider_requests", [])]
        smoke = next((row for row in arm if row["case_id"] == "approved-draft"), {})
        arms[strategy] = {"cases": len(arm), "graded": len(routed), "failures": sum(bool(row["failure"]) for row in arm),
            "correct_routes": sum(row["routing_grade"]["action_correct"] and row["routing_grade"]["owners_correct"] for row in routed),
            "correct_reuse": sum(row["routing_grade"]["actual"]["action"] == "reuse" and row["routing_grade"]["owners_correct"] and row["routing_grade"]["action_correct"] for row in routed),
            "incorrect_reuse": sum(row["routing_grade"]["incorrect_reuse"] for row in routed),
            "unnecessary_creation": sum(row["routing_grade"]["unnecessary_creation"] for row in routed),
            "model_errors": sum(row.get("model_errors", 0) for row in arm), "tool_errors": sum(row.get("tool_errors", 0) for row in arm),
            "model_call_attempts": sum(row.get("measurements", {}).get("model_call_attempts", 0) for row in arm), "http_requests": len(requests),
            "elapsed_ms": sum(row.get("measurements", {}).get("elapsed_ms", 0) for row in arm),
            "input_tokens": usage_total(requests, "prompt_tokens", public["decision_mode"]), "output_tokens": usage_total(requests, "completion_tokens", public["decision_mode"]),
            "cost": usage_total(requests, "cost", public["decision_mode"]),
            "exact_fake_draft_effect": smoke["effect_grade"]["exact_approved_draft_sent_once"] if smoke.get("effect_grade") else None,
            "unexpected_fake_mutations": smoke.get("effect_grade", {}).get("unexpected_mutation_count"),
            "chat_callback_checked": smoke.get("chat_accepted") is True and smoke.get("callback_received") is True}
    passed = all(arm["graded"] == arm["cases"] == arm["correct_routes"] and arm["failures"] == 0 and arm["exact_fake_draft_effect"]
                 and arm["unexpected_fake_mutations"] == 0 and arm["chat_callback_checked"] for arm in arms.values())
    return {"profile": public["profile"], "decision_mode": public["decision_mode"], "gmail_mode": "mock", "checks_passed": passed,
            "case_context_count": len(rows), "arms": arms, "defaults_promoted": False,
            "routing_quality": ("selected_cases_only" if any(arm["graded"] for arm in arms.values()) else "unavailable_no_completed_decisions")
                               if public["decision_mode"] == "live" else "unavailable_scripted_decisions"}


def write_report(output, summary):
    ranker_only = summary["profile"] == "worker_ranker_agent_comparison_v1"
    lines = ["# Worker ranker agent comparison" if ranker_only else "# Legacy versus bounded comparison", "", f"Decision mode: {summary['decision_mode']}. Gmail effects: mock. Checks passed: {summary['checks_passed']}.", "",
        "| Strategy | Correct routes / graded / cases | Wrong reuse | Unnecessary creation | Model attempts / HTTP | Failures | Exact draft sent | Elapsed ms |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for name, arm in summary["arms"].items():
        lines.append(f"| {name} | {arm['correct_routes']} / {arm['graded']} / {arm['cases']} | {arm['incorrect_reuse']} | {arm['unnecessary_creation']} | {arm['model_call_attempts']} / {arm['http_requests']} | {arm['failures']} | {arm['exact_fake_draft_effect']} | {arm['elapsed_ms']:.0f} |")
    lines += ["", "Routing cases execute real lookup/registration and record accepted dispatch; their workers are not run. The approved-draft case executes chat acceptance, actual workers, callbacks and fake Gmail effects.",
        "", ("Only worker ranking varies; discovery and context are bounded in every arm. " if ranker_only else "This is one small combined-strategy comparison, not a metadata/ranker ablation. ")
        + "This is not a general accuracy estimate. Mock decisions provide no live-quality evidence and may skip lookup entirely. Usage and cost totals stay unknown when any request lacks valid provider values; reported subtotals remain separate. Elapsed time is local end-to-end time including configured request pacing, not isolated provider latency. Recovered tool errors are reported separately from terminal task failures; downstream errors do not erase observed dispatch decisions.",
        "", "Production configuration is unchanged. The default ranker remains heuristic_v1. No runtime mailbox or history was used.",
        "", "See [results and traces](results.json), [numeric summary](summary.json), [public settings](comparison.json), [inputs and grading labels](inputs.json), and [source provenance](provenance.json).", ""]
    (output / "report.md").write_text("\n".join(lines), encoding="utf-8")
