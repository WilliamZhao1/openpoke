"""Release defaults, explicit opt-outs, and fresh-process startup/data checks."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from server.config import BUNDLED_LLM_MODEL, Settings


ROOT = Path(__file__).resolve().parents[2]
MODEL_FIELDS = ("interaction_agent_model", "execution_agent_model", "execution_agent_search_model", "summarizer_model", "email_classifier_model")
STRATEGY_ENV = ("OPENPOKE_WORKER_DISCOVERY", "OPENPOKE_CONTEXT_STRATEGY", "OPENPOKE_MODEL_CONTEXT_WINDOWS")


_PROBE = r'''
import asyncio
import hashlib
import json
import os
from pathlib import Path
import socket
import sys
from unittest.mock import patch

import httpx

root = Path(os.environ["OPENPOKE_DATA_DIR"])
env_file = Path.cwd() / ".env"
original_is_file = Path.is_file

def is_file(path):
    return False if path == env_file else original_is_file(path)

def reject_network(*args, **kwargs):
    raise AssertionError("Default startup probes must not access the network")

# Windows creates a local socket pair when constructing its event loop.
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)
try:
    with patch.object(Path, "is_file", is_file), patch.object(socket.socket, "connect", side_effect=reject_network), patch.object(socket.socket, "connect_ex", side_effect=reject_network):
        try:
            from server.config import get_settings
            from server.content_store import ContentStore, capture_scope, capture_text
            from server.agents.interaction_agent import agent
            from server.agents.interaction_agent.runtime import InteractionAgentRuntime
            from server.agents.execution_agent.runtime import ExecutionAgentRuntime
            from server.openrouter_client import client
            from server.services.execution import get_agent_roster, get_execution_agent_logs
            from evals.agent_overload.engine import capture_tasks, drain
        except (ValueError, TypeError) as exc:
            print(json.dumps({"status": "invalid", "error_type": type(exc).__name__}))
            raise SystemExit(2)
        settings = get_settings()
        # Keep unrelated summarization scheduling out of this startup probe.
        settings.conversation_summary_threshold = 0
        roster = get_agent_roster()
        requests = []
        checks = None
        if sys.argv[1] == "exercise":
            roster._roster_path.write_text(json.dumps([f"worker-{n:03d}" for n in range(100)]), encoding="utf-8")
            roster.load()
            logs = get_execution_agent_logs()
            logs.record_request("worker-099", "Preserved task")
            with capture_scope("worker:worker-099"):
                reference = capture_text("Preserved body\r\nliteral \\n", kind="release_probe", min_bytes=-1)
                logs.record_content_reference("worker-099", reference, "release_probe")
            (root / "probe.json").write_text(json.dumps({"reference": reference}), encoding="utf-8")

            def respond(request):
                payload = json.loads(request.content)
                requests.append(payload)
                if len(requests) == 1:
                    name, arguments = "find_worker", {"query": "worker-099"}
                elif len(requests) == 2:
                    lookup = json.loads(payload["messages"][-1]["content"])
                    assert "worker-099" in json.dumps(lookup)
                    name, arguments = "send_message_to_user", {"message": "Found worker-099."}
                else:
                    return httpx.Response(200, json={"choices": [{"message": {"content": "Done."}}]})
                return httpx.Response(200, json={"choices": [{"message": {"tool_calls": [{"id": f"call-{len(requests)}", "type": "function",
                    "function": {"name": name, "arguments": json.dumps(arguments)}}]}}]})

            async def exercise():
                async with capture_tasks() as tasks:
                    result = await InteractionAgentRuntime().execute("Find my older worker-099")
                    await drain(tasks)
                    assert result.success, result.error

            with patch.object(client, "prepare_budgeted_request", wraps=client.prepare_budgeted_request) as preflight, client.use_mock_provider(httpx.MockTransport(respond)):
                loop.run_until_complete(exercise())
                checks = preflight.call_count
            assert checks == len(requests) == 3
            assert requests[0]["messages"][1]["content"].count("<agent name=") <= 5
            assert len(roster.get_agents()) == 100

        runtime = InteractionAgentRuntime()
        worker = ExecutionAgentRuntime("worker-099")
        source = None
        if (root / "probe.json").exists():
            reference = json.loads((root / "probe.json").read_text(encoding="utf-8"))["reference"]
            source = ContentStore().read_source_page(reference, owner="worker:worker-099").content.decode("utf-8")
        print(json.dumps({"status": "ok", "discovery": settings.worker_discovery_strategy, "context": settings.context_strategy,
            "model": settings.interaction_agent_model, "windows": settings.model_context_windows,
            "input_cap": settings.context_input_tokens, "headroom": settings.context_headroom_tokens,
            "interaction_tools": [tool["function"]["name"] for tool in runtime.tool_schemas],
            "worker_tools": [tool["function"]["name"] for tool in worker.tool_schemas],
            "visible_workers": agent._render_active_agents().count("<agent name="), "worker_count": len(roster.get_agents()),
            "model_requests": len(requests), "provider_preflights": checks, "source": source,
            "files": {path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                      for path in sorted(root.rglob("*")) if path.is_file()}}))
finally:
    loop.run_until_complete(loop.shutdown_asyncgens())
    loop.run_until_complete(loop.shutdown_default_executor())
    loop.close()
    asyncio.set_event_loop(None)
'''


class DefaultStrategySettingsTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        for name in STRATEGY_ENV:
            os.environ.pop(name, None)

    def settings(self, **changes):
        return Settings(**{**dict.fromkeys(MODEL_FIELDS, BUNDLED_LLM_MODEL), **changes})

    def test_defaults_use_bounded_strategies_and_an_independent_bundled_policy(self):
        first = self.settings()
        self.assertEqual((first.worker_discovery_strategy, first.context_strategy), ("bounded", "bounded"))
        self.assertEqual(first.model_context_windows, {"anthropic/claude-sonnet-4.6": 65536})
        first.model_context_windows[BUNDLED_LLM_MODEL] = 1000
        self.assertEqual(self.settings().model_context_windows[BUNDLED_LLM_MODEL], 65536)

    def test_custom_models_require_allowances_for_each_selected_component(self):
        for field in MODEL_FIELDS:
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "cover every configured model"):
                self.settings(**{field: "custom/model"})
            selected = self.settings(**{field: "custom/model", "model_context_windows": {BUNDLED_LLM_MODEL: 65536, "custom/model": 50000}})
            self.assertEqual(getattr(selected, field), "custom/model")
        selected = self.settings(**{**dict.fromkeys(MODEL_FIELDS, "custom/model"), "model_context_windows": {"custom/model": 50000}})
        self.assertEqual(selected.model_context_windows, {"custom/model": 50000})

    def test_explicit_legacy_choices_remain_independent_and_constructor_values_win(self):
        os.environ["OPENPOKE_CONTEXT_STRATEGY"] = "legacy"
        self.assertEqual(self.settings().worker_discovery_strategy, "bounded")
        self.assertEqual(self.settings().context_strategy, "legacy")
        os.environ["OPENPOKE_WORKER_DISCOVERY"] = "legacy"
        self.assertEqual(self.settings(worker_discovery_strategy="bounded").worker_discovery_strategy, "bounded")
        self.assertEqual(self.settings(context_strategy="bounded").context_strategy, "bounded")
        self.assertEqual(self.settings(model_context_windows={}).model_context_windows, {})

    def test_invalid_or_explicit_empty_configuration_never_uses_a_fallback(self):
        for changes in ({"model_context_windows": {}}, {"model_context_windows": {"other": 65536}},
                        {"openrouter_max_tokens": 65536}, {"context_strategy": "invalid"}, {"worker_discovery_strategy": "invalid"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.settings(**changes)
        for value in ("{}", "invalid-json", '{"anthropic/claude-sonnet-4.6": true}'):
            with self.subTest(value=value), patch.dict(os.environ, {"OPENPOKE_MODEL_CONTEXT_WINDOWS": value}), self.assertRaises(ValueError):
                self.settings()


class DefaultStrategyStartupTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name) / "profile"
        self.root.mkdir()
        (self.root / "unrelated.txt").write_text("Preserve this file", encoding="utf-8")
        self.environment = dict(os.environ, OPENPOKE_DATA_DIR=str(self.root), OPENROUTER_API_KEY="test-key",
            COMPOSIO_API_KEY="test-key", COMPOSIO_GMAIL_AUTH_CONFIG_ID="test-config", OPENROUTER_MAX_TOKENS="2048",
            OPENPOKE_CONTEXT_INPUT_TOKENS="32768", OPENPOKE_CONTEXT_HEADROOM_TOKENS="1024")
        for name in (*STRATEGY_ENV, "OPENROUTER_MODEL"):
            self.environment.pop(name, None)

    def probe(self, mode="inspect", *, expected=0, **changes):
        result = subprocess.run([sys.executable, "-c", _PROBE, mode], cwd=ROOT, env={**self.environment, **changes},
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def test_fresh_defaults_enable_lookup_recovery_and_provider_preflight(self):
        result = self.probe("exercise")
        self.assertEqual((result["discovery"], result["context"]), ("bounded", "bounded"))
        self.assertEqual(result["model"], "anthropic/claude-sonnet-4.6")
        self.assertEqual(result["windows"], {result["model"]: 65536})
        self.assertEqual((result["input_cap"], result["headroom"]), (32768, 1024))
        self.assertTrue({"find_worker", "read_result", "recall_history"}.issubset(result["interaction_tools"]))
        self.assertTrue({"read_result", "recall_history"}.issubset(result["worker_tools"]))
        self.assertEqual((result["model_requests"], result["provider_preflights"]), (3, 3))
        self.assertEqual(result["worker_count"], 100)
        self.assertLessEqual(result["visible_workers"], 5)

    def test_unknown_model_startup_fails_before_creating_stores_until_configured(self):
        result = self.probe(expected=2, OPENROUTER_MODEL="custom/model")
        self.assertEqual(result["error_type"], "ValidationError")
        self.assertEqual(list(self.root.iterdir()), [self.root / "unrelated.txt"])
        configured = self.probe(OPENROUTER_MODEL="custom/model", OPENPOKE_MODEL_CONTEXT_WINDOWS='{"custom/model":50000}')
        self.assertEqual(configured["windows"], {"custom/model": 50000})
        self.assertEqual(configured["context"], "bounded")

    def test_restart_opt_out_and_reenable_preserve_existing_files_and_references(self):
        initial = self.probe("exercise")
        legacy = self.probe(OPENPOKE_WORKER_DISCOVERY="legacy", OPENPOKE_CONTEXT_STRATEGY="legacy", OPENPOKE_MODEL_CONTEXT_WINDOWS="{}")
        self.assertEqual((legacy["discovery"], legacy["context"]), ("legacy", "legacy"))
        self.assertFalse({"find_worker", "read_result", "recall_history"} & set(legacy["interaction_tools"]))
        self.assertEqual(legacy["visible_workers"], 100)
        self.assertEqual(legacy["files"], initial["files"])
        self.assertEqual(legacy["source"], initial["source"])
        restored = self.probe()
        self.assertEqual(restored["context"], "bounded")
        self.assertEqual(restored["files"], initial["files"])
        self.assertEqual(restored["source"], initial["source"])


if __name__ == "__main__":
    unittest.main()
