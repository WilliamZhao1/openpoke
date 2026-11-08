import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from server.config import Settings
from server import data_paths


# Fresh processes exercise the import-time singletons and restart behavior.
# Only local persistence APIs run; background services are never started.
_STORE_PROBE = """
import json
import os
from pathlib import Path
import socket
import sys

def reject_network(*args, **kwargs):
    raise AssertionError("Storage tests must not use the network")

socket.socket.connect = reject_network
socket.socket.connect_ex = reject_network

from server.data_paths import get_data_dir
from server.services.conversation import get_conversation_log, get_working_memory_log
from server.services.conversation.summarization.state import SummaryState
from server.services.execution import get_agent_roster, get_execution_agent_logs
from server.services.gmail import client as gmail
from server.services.gmail import get_important_email_watcher
from server.services.timezone_store import get_timezone_store
from server.services.triggers import get_trigger_service

root = Path(os.environ["OPENPOKE_DATA_DIR"]).resolve()
assert get_data_dir() == root
roster = get_agent_roster()
logs = get_execution_agent_logs()
conversation = get_conversation_log()
memory = get_working_memory_log()
triggers = get_trigger_service()
timezone = get_timezone_store()
seen = get_important_email_watcher()._seen_store

assert roster._roster_path == root / "execution_agents" / "roster.json"
assert logs._base_dir == root / "execution_agents"
assert conversation._path == root / "conversation" / "poke_conversation.log"
assert memory._path == root / "conversation" / "poke_working_memory.log"
assert triggers._store._db_path == root / "triggers.db"
assert gmail._ACTIVE_USER_ID_PATH == root / "gmail" / "active_user_id.txt"
assert seen._path == root / "gmail_seen.json"
assert timezone._path == root / "timezone.txt"

mode, label = sys.argv[1:]
if mode == "populate":
    roster.add_agent(label)
    logs.record_request(label, "task " + label)
    conversation.record_user_message("message " + label)
    memory.write_summary_state(SummaryState(summary_text="summary " + label, last_index=0))
    triggers.create_trigger(agent_name=label, payload="reminder " + label, timezone_name="UTC")
    gmail._set_active_gmail_user_id("account-" + label)
    seen.mark_seen(["message-id-" + label])
    timezone.set_timezone("Etc/GMT+1")
elif mode == "clear":
    roster.clear()
    logs.clear_all()
    conversation.clear()
    triggers.clear_all()
    gmail._set_active_gmail_user_id(None)
    seen.clear()
    timezone.clear()

state = memory.load_summary_state()
print(json.dumps({
    "agents": roster.get_agents(),
    "requests": [payload for tag, _, payload in logs.iter_entries(label) if tag == "agent_request"],
    "conversation": [payload for _, _, payload in conversation.iter_entries()],
    "summary": state.summary_text,
    "summary_index": state.last_index,
    "triggers": [record.payload for record in triggers.list_triggers(agent_name=label)],
    "gmail_user": gmail.get_active_gmail_user_id(),
    "seen": seen.snapshot(),
    "timezone": timezone.get_timezone(),
}))
"""


class DataPathTests(unittest.TestCase):
    def test_default_matches_legacy_data_directory(self):
        with patch.dict(os.environ):
            os.environ.pop("OPENPOKE_DATA_DIR", None)
            settings = Settings()
        expected = Path(__file__).resolve().parents[1] / "data"
        self.assertEqual(settings.data_dir, expected)

    def test_environment_override_is_resolved_without_creating_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "unused data"
            with patch.dict(os.environ, {"OPENPOKE_DATA_DIR": str(path)}):
                settings = Settings()
            with patch.object(data_paths, "get_settings", return_value=settings):
                self.assertEqual(data_paths.get_data_dir(), path.resolve())
            self.assertFalse(path.exists())

    def test_relative_and_home_paths_are_expanded(self):
        for path in (Path("relative-data"), Path("~") / "openpoke-data"):
            with self.subTest(path=path):
                with patch.object(data_paths, "get_settings", return_value=Settings(data_dir=path)):
                    self.assertEqual(data_paths.get_data_dir(), path.expanduser().resolve())

    def test_empty_environment_override_is_rejected(self):
        for value in ("", "  "):
            with self.subTest(value=value):
                with patch.dict(os.environ, {"OPENPOKE_DATA_DIR": value}):
                    with self.assertRaisesRegex(ValueError, "OPENPOKE_DATA_DIR must be a non-empty path"):
                        Settings()

    def _probe(self, root, mode, label):
        environment = dict(os.environ, OPENPOKE_DATA_DIR=str(root))
        result = subprocess.run(
            [sys.executable, "-c", _STORE_PROBE, mode, label],
            cwd=Path(__file__).resolve().parents[2],
            env=environment,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def test_stores_persist_after_restart_and_clear_only_their_configured_root(self):
        with tempfile.TemporaryDirectory() as directory:
            root_a = Path(directory) / "profile a"
            root_b = Path(directory) / "profile b"
            empty = {
                "agents": [], "requests": [], "conversation": [],
                "summary": "", "summary_index": -1, "triggers": [],
                "gmail_user": None, "seen": [], "timezone": "UTC",
            }
            self.assertEqual(self._probe(root_a, "read", "alpha"), empty)
            expected_a = {
                "agents": ["alpha"], "requests": ["task alpha"],
                "conversation": ["message alpha"], "summary": "summary alpha",
                "summary_index": 0, "triggers": ["reminder alpha"],
                "gmail_user": "account-alpha", "seen": ["message-id-alpha"],
                "timezone": "Etc/GMT+1",
            }
            self.assertEqual(self._probe(root_a, "populate", "alpha"), expected_a)
            self.assertEqual(self._probe(root_a, "read", "alpha"), expected_a)
            self.assertEqual(self._probe(root_b, "read", "beta"), empty)
            expected_b = self._probe(root_b, "populate", "beta")
            self.assertEqual(expected_b["agents"], ["beta"])
            self.assertEqual(self._probe(root_a, "clear", "alpha"), empty)
            self.assertEqual(self._probe(root_a, "read", "alpha"), empty)
            self.assertEqual(self._probe(root_b, "read", "beta"), expected_b)


if __name__ == "__main__":
    unittest.main()
