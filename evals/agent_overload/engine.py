"""Capture the actual legacy prompt and one explicitly scripted runtime trace."""

import asyncio
from contextlib import asynccontextmanager
from copy import deepcopy
from datetime import datetime, timezone
from html import escape
import gzip
import hashlib
import importlib.metadata
import json
import logging
from pathlib import Path
import platform
from time import perf_counter
from unittest.mock import patch

import httpx

from .contracts import (
    EvaluationConfigError, HERE, ROOT, digest, grade_draft_effects, grade_routing,
    observation, read_json,
)
from server.agents.interaction_agent import agent, tools
from server.agents.interaction_agent.runtime import InteractionAgentRuntime
from server.agents.execution_agent.batch_manager import ExecutionBatchManager
from server.agents.execution_agent.runtime import ExecutionAgentRuntime
from server.agents.execution_agent.tasks.search_email.tool import MAX_LLM_ITERATIONS
from server.config import get_settings
from server.data_paths import get_data_dir
from server.logging_config import logger
from server.models import ChatMessage, ChatRequest
from server.openrouter_client import use_mock_provider
from server.services.conversation import get_conversation_log
from server.services.conversation.chat_handler import handle_chat_request
from server.services.execution import AgentRoster, get_agent_roster
from server.tests.fixtures.catalogs import build_catalog, load_fixture, routing_cases
from server.tests.fixtures.fake_gmail import FakeGmail, use_fake_gmail


SOURCE_PATHS = (
    "server/__init__.py", "server/app.py", "server/config.py", "server/data_paths.py",
    "server/logging_config.py", "server/observability.py", "server/tests/fixtures/catalogs.py",
    "server/tests/fixtures/fake_gmail.py", "evals/agent_overload/contracts.py",
    "evals/agent_overload/engine.py", "evals/agent_overload/run.py",
)


def runtime_source_paths():
    paths = set(SOURCE_PATHS)
    for directory in ("agents", "services", "models", "routes", "openrouter_client", "utils"):
        for path in (ROOT / "server" / directory).rglob("*"):
            if path.is_file() and path.suffix in {".py", ".md"}:
                paths.add(path.relative_to(ROOT).as_posix())
    return sorted(paths)


def case_transcript(turns):
    tags = {"user": "user_message", "assistant": "poke_reply"}
    return "\n".join(
        f'<{tags[turn["role"]]}>{escape(turn["content"], quote=False)}</{tags[turn["role"]]}>'
        for turn in turns
    )


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def seed_roster(roster, catalog):
    roster._roster_path.write_text(json.dumps([row["display_name"] for row in catalog]), encoding="utf-8")
    roster.load()


def capture_contexts(manifest, sizes, output, data_root, request_archive):
    rows = []
    shapes = []
    hashes = {}
    system = agent.build_system_prompt()
    for size in sizes:
        catalog = build_catalog(size)
        hashes[str(size)] = digest(catalog)
        if hashes[str(size)] != manifest["fixture_checksums"]["catalogs"][str(size)]:
            raise EvaluationConfigError("Generated catalog digest does not match the frozen manifest")
        path = data_root / f"catalog-{size}.json"
        path.write_text(json.dumps([row["display_name"] for row in catalog]), encoding="utf-8")
        roster = AgentRoster(path)
        eligible = [case for case in routing_cases() if (case["catalog"] == "empty") == (size == 0)]
        with patch.object(agent, "get_agent_roster", return_value=roster):
            rendered = agent._render_active_agents()
            visible = rendered.count("<agent name=")
            shapes.append({
                "catalog_size": size,
                "visible_workflows": observation(visible),
                "roster_characters": observation(len(rendered)),
                "roster_utf8_bytes": observation(len(rendered.encode("utf-8"))),
                "roster_tokens": observation(None, availability="unavailable", reason="tokenizer_not_configured"),
                "all_names_rendered": observation(all(f'<agent name="{escape(row["display_name"], quote=True)}" />' in rendered for row in catalog)),
            })
            for index, case in enumerate(eligible):
                # Only turn text enters the prompt. Gold and scripted lookup stay out.
                transcript = case_transcript(case["turns"][:-1])
                messages = agent.prepare_message_with_history(case["turns"][-1]["content"], transcript)
                payload = {
                    "model": manifest["runtime_settings"]["interaction_agent_model"],
                    "messages": [{"role": "system", "content": system}, *messages],
                    "tools": tools.get_tool_schemas(), "stream": False,
                    "max_tokens": manifest["runtime_settings"]["openrouter_max_tokens"],
                }
                representative = f"prompts/catalog-{size:05d}.json" if index == 0 else None
                if representative:
                    write_json(output / representative, payload)
                rows.append({
                    "case_id": case["id"], "split": case["split"], "catalog_size": size,
                    "request_sha256": digest(payload),
                    "prompt_text_characters": observation(sum(len(message["content"]) for message in payload["messages"])),
                    "representative_payload": representative,
                    "payload_archive": "case_requests.jsonl.gz", "payload_line": len(rows),
                    "routing_grade": grade_routing(case["expected"], None, source_mode="mock"),
                    "expected": case["expected"],
                })
                request_archive.write((json.dumps({"case_id": case["id"], "catalog_size": size, "payload": payload}, ensure_ascii=False) + "\n").encode("utf-8"))
    return shapes, rows, hashes


class TelemetryCapture(logging.Handler):
    def __init__(self):
        super().__init__()
        self.events = []

    def emit(self, record):
        if hasattr(record, "telemetry"):
            self.events.append(json.loads(json.dumps(record.telemetry)))


@asynccontextmanager
async def capture_tasks():
    loop = asyncio.get_running_loop()
    original = loop.create_task
    tasks = []

    def create(coroutine, *args, **kwargs):
        task = original(coroutine, *args, **kwargs)
        tasks.append(task)
        return task

    with patch.object(loop, "create_task", side_effect=create):
        try:
            yield tasks
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)


async def drain(tasks):
    index = 0
    for _ in range(30):
        current = [task for task in tasks[index:] if task is not asyncio.current_task()]
        index = len(tasks)
        if not current:
            return
        await asyncio.gather(*current)
    raise RuntimeError("Mock background work did not drain")


async def run_smoke(manifest, script):
    fake = FakeGmail()
    roster = get_agent_roster()
    catalog = build_catalog(manifest["smoke_catalog_size"])
    seed_roster(roster, catalog)
    requests = []
    response_keys = []
    capture = TelemetryCapture()
    manager = ExecutionBatchManager()
    if manager.timeout_seconds != manifest["loop_limits"]["batch_timeout_seconds"]:
        raise EvaluationConfigError("Batch timeout differs from the pinned baseline")
    log = get_conversation_log()
    initial_names = set(roster.get_agents())

    def provider(request):
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
            raise RuntimeError("Unexpected component in the frozen mock script")
        requests.append(deepcopy(payload))
        response_keys.append(key)
        # Missing provider usage is intentional: do not fabricate zero counts.
        return httpx.Response(200, json={"choices": [{"message": deepcopy(script["responses"][key])}]})

    started = perf_counter()
    prior_level = logger.level
    prior_propagate = logger.propagate
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger.addHandler(capture)
    try:
        with (
            use_fake_gmail(fake), use_mock_provider(httpx.MockTransport(provider)),
            patch.object(tools, "_EXECUTION_BATCH_MANAGER", manager),
        ):
            async with capture_tasks() as tasks:
                log.record_reply(script["input"]["review"])
                response = await handle_chat_request(ChatRequest(messages=[ChatMessage(role="user", content=script["input"]["request"])]))
                await asyncio.wait_for(drain(tasks), timeout=manifest["smoke_deadline_seconds"])
        events = capture.events
    finally:
        logger.removeHandler(capture)
        logger.setLevel(prior_level)
        logger.propagate = prior_propagate
        await manager.shutdown()
    elapsed = (perf_counter() - started) * 1000
    callbacks = [event for event in events if event["event"] == "callback.received"]
    accepted = [event for event in events if event["event"] == "chat.accepted"]
    dispatched = [event for event in events if event["event"] == "execution.dispatched"]
    worker_tools = [event for event in events if event["event"] == "tool.completed" and event["component"] == "execution"]
    replies = [event for event in events if event["event"] == "reply.recorded"]
    model_events = [event for event in events if event["event"] == "model_call.completed"]
    new_entries = list(log.iter_entries())
    routed = []
    for payload in requests:
        for call in payload["messages"]:
            if call.get("role") == "assistant":
                for invocation in call.get("tool_calls", []):
                    if invocation["function"]["name"] == "send_message_to_agent":
                        args = json.loads(invocation["function"]["arguments"])
                        if args["agent_name"] not in routed:
                            routed.append(args["agent_name"])
    by_name = {row["display_name"]: row["workflow_id"] for row in catalog}
    actual = {"action": "reuse" if routed and all(name in initial_names for name in routed) else "create_new",
              "workflow_ids": [by_name[name] for name in routed if name in by_name]}
    effect_grade = grade_draft_effects(script["expected"], fake.effects)
    route_grade = grade_routing(script["expected"], actual, source_mode="mock")
    checks = {
        "http_accepted": response.status_code == 202,
        "five_mock_calls": len(requests) == len(model_events) == 5 and len(set(response_keys)) == 5,
        "mock_provenance": bool(model_events) and all(event["provider_mode"] == "mock" for event in model_events),
        "original_provider_payload": all(
            payload["model"] == manifest["runtime_settings"]["interaction_agent_model"]
            and payload["max_tokens"] == manifest["runtime_settings"]["openrouter_max_tokens"]
            and payload["stream"] is False
            and set(payload) == {"model", "messages", "tools", "stream", "max_tokens"}
            for payload in requests
        ),
        "correlated_trace": (
            len(accepted) == len(dispatched) == len(worker_tools) == len(callbacks) == 1
            and accepted[0]["request_id"] == dispatched[0]["request_id"] == worker_tools[0]["request_id"] == callbacks[0]["request_id"]
            and dispatched[0]["run_id"] == worker_tools[0]["run_id"]
            and callbacks[0]["parent_turn_id"] == accepted[0]["turn_id"]
            and any(reply.get("turn_id") == callbacks[0]["turn_id"] for reply in replies)
        ),
        "exact_fake_effect": effect_grade["exact_approved_draft_sent_once"] and effect_grade["unexpected_mutation_count"] == 0,
        "exact_fixture_owner": route_grade["action_correct"] and route_grade["owners_correct"],
        "roster_unchanged": set(roster.get_agents()) == initial_names,
        "user_reply_stored": bool(new_entries) and new_entries[-1][0] == "poke_reply" and new_entries[-1][2] == script["expected"]["reply"],
        "provider_usage_unknown": all(event["input_tokens"] is None and event["output_tokens"] is None for event in model_events),
    }
    return {
        "script_id": script["id"], "source_mode": "mock", "checks": checks,
        "local_elapsed_ms": observation(elapsed, source="monotonic_clock"),
        "routing_grade": {**route_grade, "identity_resolution": "exact_legacy_alias_in_fixture", "evidence_refs": ["smoke.json#/provider_requests"]},
        "effect_grade": {**effect_grade, "evidence_refs": ["smoke.json#/gmail/effects", "approved_draft.json#/expected"]},
        "telemetry": events, "provider_requests": requests, "response_keys": response_keys,
        "conversation": [{"kind": kind, "content": content} for kind, _, content in new_entries],
        "gmail": fake.snapshot(),
    }


def run_evaluation(manifest, sizes, output, data_root, loop):
    settings = get_settings()
    if get_data_dir() != data_root.resolve():
        raise EvaluationConfigError("Application stores were not initialized in the evaluation data root")
    if any(getattr(settings, key) != value for key, value in manifest["runtime_settings"].items()):
        raise EvaluationConfigError("Runtime configuration differs from the pinned baseline profile")
    if (InteractionAgentRuntime.MAX_TOOL_ITERATIONS, ExecutionAgentRuntime.MAX_TOOL_ITERATIONS, MAX_LLM_ITERATIONS) != (8, 8, 8):
        raise EvaluationConfigError("Runtime loop limits differ from the pinned baseline")
    checksums = manifest["fixture_checksums"]
    if load_fixture("checksums.json") != checksums:
        raise EvaluationConfigError("Fixture checksums differ from the pinned manifest")
    for name in ("routing_cases", "gmail_mailbox"):
        if digest(load_fixture(name + ".json")) != checksums[name]:
            raise EvaluationConfigError("Fixture content differs from its frozen checksum")
    script = read_json(HERE / "approved_draft.json")
    if digest(script) != manifest["smoke_sha256"]:
        raise EvaluationConfigError("Mock script differs from its frozen checksum")
    with (output / "case_requests.jsonl.gz").open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
            shapes, contexts, hashes = capture_contexts(manifest, sizes, output, data_root, compressed)
    smoke = loop.run_until_complete(run_smoke(manifest, script))
    write_json(output / "manifest.json", manifest)
    write_json(output / "approved_draft.json", script)
    write_json(output / "prompt_shapes.json", shapes)
    write_json(output / "case_contexts.json", contexts)
    write_json(output / "smoke.json", smoke)
    for name in ("catalog.json", "routing_cases.json", "gmail_mailbox.json", "checksums.json"):
        write_json(output / "inputs" / name, load_fixture(name))
    (output / "inputs" / "catalogs.py").write_text(
        (ROOT / "server/tests/fixtures/catalogs.py").read_text(encoding="utf-8"), encoding="utf-8",
    )
    source_hashes = {
        path: hashlib.sha256((ROOT / path).read_text(encoding="utf-8").replace("\r\n", "\n").encode("utf-8")).hexdigest()
        for path in runtime_source_paths()
    }
    versions = {name: importlib.metadata.version(name) for name in ("httpx", "fastapi", "pydantic")}
    write_json(output / "provenance.json", {
        "manifest_sha256": digest(manifest), "catalog_sha256": hashes,
        "routing_cases_sha256": checksums["routing_cases"], "gmail_mailbox_sha256": checksums["gmail_mailbox"],
        "source_sha256_lf_normalized": source_hashes, "python_version": platform.python_version(),
        "package_versions": versions, "requested_catalog_sizes": sizes,
        "comparisons": load_fixture("routing_cases.json")["comparisons"],
    })
    checks_passed = all(smoke["checks"].values()) and all(row["visible_workflows"]["value"] == row["catalog_size"] and row["all_names_rendered"]["value"] for row in shapes)
    unavailable = {
        name: observation(None, availability="unavailable", reason="requires_model_backed_evaluation")
        for name in ("routing_accuracy", "incorrect_reuse_rate", "end_task_success_rate", "live_provider_cost", "live_provider_latency")
    }
    unavailable["candidate_recall_at_5"] = observation(
        None, availability="not_applicable", reason="legacy_has_no_ranked_shortlist",
    )
    summary = {
        "schema_version": 1, "created_at": datetime.now(timezone.utc).isoformat(),
        "run_mode": "model-free", "provider_mode": "mock", "strategy": manifest["strategy"],
        "provider_contract": manifest["provider"],
        "checks_passed": checks_passed, "case_context_count": len(contexts), "catalog_sizes": sizes,
        "measurements": unavailable, "smoke_checks": smoke["checks"],
        "unexecuted_comparisons": [row["id"] for row in load_fixture("routing_cases.json")["comparisons"] if row["id"] != manifest["strategy"]],
    }
    write_json(output / "summary.json", summary)
    lines = [
        "# Model-free legacy baseline", "",
        f"Contract checks: {'passed' if checks_passed else 'failed'}. Provider: mock. Case contexts: {len(contexts)}.", "",
        "The scripted trace verifies instrumentation and fake effects. It does not measure model routing quality.", "",
        "| Catalog workflows | Rendered workflows | Roster characters | Roster UTF-8 bytes |",
        "| --- | --- | --- | --- |",
        *[f"| {row['catalog_size']} | {row['visible_workflows']['value']} | {row['roster_characters']['value']} | {row['roster_utf8_bytes']['value']} |" for row in shapes],
        "", "Character counts are observed; token counts, live cost, live latency, and routing/task quality remain unavailable.",
        "", "See [summary](summary.json), [trace and tool evidence](smoke.json), [case contexts](case_contexts.json), and [provenance](provenance.json).", "",
    ]
    (output / "report.md").write_text("\n".join(lines), encoding="utf-8")
    artifacts = {str(path.relative_to(output)).replace("\\", "/"): hashlib.sha256(path.read_bytes()).hexdigest()
                 for path in sorted(output.rglob("*")) if path.is_file()}
    write_json(output / "artifacts.json", artifacts)
    return summary
