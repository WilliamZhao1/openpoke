"""Authoritative exact worker names, with a rebuildable metadata sidecar."""

import json
from pathlib import Path
import threading

from ...data_paths import get_data_dir
from .discovery import WorkerDiscoveryError, assignment_metadata, atomic_json, load_metadata
from .log_store import _slugify


class AgentRoster:
    # One local writer process; share the short lock across roster handles.
    _lock = threading.RLock()

    def __init__(self, roster_path: Path):
        self._roster_path = Path(roster_path)
        self.metadata_path = self._roster_path.with_suffix(".metadata.json")
        self.load()

    def _read(self):
        try:
            with self._roster_path.open(encoding="utf-8") as handle:
                names = json.load(handle)
            if not isinstance(names, list) or any(not isinstance(name, str) for name in names):
                raise ValueError()
            return names
        except FileNotFoundError:
            return []
        except (OSError, ValueError, UnicodeError) as exc:
            raise WorkerDiscoveryError("Worker roster is unavailable; retry before creating a worker") from exc

    def load(self):
        with self._lock:
            names = self._read()
            if not self._roster_path.exists():
                atomic_json(self._roster_path, names)

    def get_agents(self):
        with self._lock:
            return self._read()

    def add_agent(self, agent_name):
        self.register(agent_name)

    def register(self, agent_name, *, allow_creation=True):
        """Recheck membership, discovery and slug ownership under the local lock."""
        if not isinstance(agent_name, str):
            raise ValueError("agent_name must be a string")
        with self._lock:
            names = self._read()
            if agent_name in names:
                return False
            if not agent_name.strip() or len(agent_name) > 200:
                raise ValueError("New worker names must contain 1–200 characters")
            if names and not allow_creation:
                raise ValueError("Call find_worker successfully in this turn before creating another worker")
            slug = _slugify(agent_name)
            if any(_slugify(name) == slug for name in names) or (self._roster_path.parent / f"{slug}.log").exists():
                raise ValueError("Worker name collides with an existing history filename; use another name or reconcile the history")
            atomic_json(self._roster_path, [*names, agent_name])
            return True

    def discovery_snapshot(self):
        with self._lock:
            return self._read(), load_metadata(self.metadata_path)

    def record_assignment(self, agent_name, instructions):
        with self._lock:
            if agent_name not in self._read():
                return  # Late assignments cannot restore removed metadata.
            metadata = load_metadata(self.metadata_path)
            metadata[agent_name] = assignment_metadata(metadata.get(agent_name, {}), instructions)
            atomic_json(self.metadata_path, metadata)

    def rebuild_metadata(self):
        """Reset derived fields; every roster name remains searchable immediately."""
        with self._lock:
            atomic_json(self.metadata_path, {})

    def clear(self):
        with self._lock:
            self.metadata_path.unlink(missing_ok=True)
            self._roster_path.unlink(missing_ok=True)


_ROSTER_PATH = get_data_dir() / "execution_agents" / "roster.json"

_agent_roster = AgentRoster(_ROSTER_PATH)


def get_agent_roster() -> AgentRoster:
    """Get the singleton roster instance."""
    return _agent_roster
