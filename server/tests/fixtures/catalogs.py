"""Pure deterministic catalogs; gold labels are loaded separately from profiles."""

from copy import deepcopy
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path
from uuid import UUID, uuid5


FIXTURE_DIR = Path(__file__).resolve().parent


def load_fixture(name: str) -> dict:
    if name not in {"catalog.json", "routing_cases.json", "gmail_mailbox.json", "checksums.json"}:
        raise ValueError("Unknown fixture")
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def fingerprint(value) -> str:
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_catalog(size: int = 100) -> list[dict]:
    """Return frozen core records plus deterministic distractors, never rankings."""
    manifest = load_fixture("catalog.json")
    core = manifest["core_workflows"]
    if type(size) is not int or size not in {0, *manifest["catalog_sizes"]}:
        raise ValueError("Catalog size must be 0, 100, 1000, or 10000")
    if size == 0:
        return []
    records = deepcopy(core)
    namespace = UUID(manifest["namespace"])
    clock = datetime.fromisoformat(manifest["fixed_now"].replace("Z", "+00:00"))
    for index in range(size - len(core)):
        person = ("Alice Chen", "Morgan", "Sam Patel", "Alex Kim")[index % 4]
        topic = ("contract", "lunch", "receipts", "review", "renewal")[index % 5]
        stamp = (clock - timedelta(days=1 + index % 730, minutes=index)).isoformat().replace("+00:00", "Z")
        records.append({
            "workflow_id": str(uuid5(namespace, f"distractor:{index}")),
            "display_name": f"{person} {topic} project {index:05d}",
            "purpose": f"Coordinate {topic} for a separate synthetic project {index:05d} involving {person}.",
            "entities": [person, topic, f"project-{index:05d}"],
            "status": "completed" if index % 3 == 0 else "open",
            "archived": index % 33 == 0,
            "created_at": stamp, "last_activity_at": stamp, "revision": 1,
            "card": {"revision": 1, "summary": f"Synthetic {topic} episode {index:05d}.", "obligations": []},
            "resource_refs": [],
        })
    return records


def routing_cases() -> list[dict]:
    """Resolve human-readable core indexes to the frozen UUID gold labels."""
    core = load_fixture("catalog.json")["core_workflows"]
    cases = load_fixture("routing_cases.json")["cases"]
    for case in cases:
        expected = case["expected"]
        expected["workflow_ids"] = [core[number - 1]["workflow_id"] for number in expected.pop("owner_numbers")]
        lookup = case["lookup"]
        lookup["candidate_ids"] = [core[number - 1]["workflow_id"] for number in lookup.pop("candidate_numbers")]
    return cases
