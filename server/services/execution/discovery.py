"""Small, rebuildable worker metadata and bounded lexical discovery."""

from collections import Counter
from datetime import datetime, timezone
from html import escape
import json
import os
from pathlib import Path
import re
import tempfile
import unicodedata

from .log_store import _slugify


RECENT_LIMIT = 5
ROSTER_CHAR_BUDGET = 2000
LOOKUP_CHAR_BUDGET = 3500
QUERY_CHAR_LIMIT = 256
LOOKUP_LIMIT = 5
METADATA_TEXT_LIMIT = 240


class WorkerDiscoveryError(RuntimeError):
    pass


def atomic_json(path: Path, data):
    """Replace a local JSON file only after the new contents are complete."""
    temporary = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as handle:
            temporary = Path(handle.name)
            json.dump(data, handle, ensure_ascii=True, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except (OSError, ValueError, TypeError) as exc:
        raise WorkerDiscoveryError("Could not save worker data") from exc
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass  # Preserve the original save error if cleanup also fails.


def load_metadata(path):
    try:
        with path.open(encoding="utf-8") as handle:
            data = json.load(handle)
        if not isinstance(data, dict):
            raise ValueError()
        for record in data.values():
            if not isinstance(record, dict):
                raise ValueError()
            for field in ("purpose", "recent_assignment"):
                if record.get(field) is not None and (not isinstance(record[field], str) or len(record[field]) > METADATA_TEXT_LIMIT):
                    raise ValueError()
            if record.get("last_activity") is not None:
                stamp = datetime.fromisoformat(record["last_activity"])
                if stamp.tzinfo is None or stamp.utcoffset() is None:
                    raise ValueError()
        return data
    except FileNotFoundError:
        return {}
    except (OSError, ValueError, TypeError, UnicodeError) as exc:
        raise WorkerDiscoveryError("Worker metadata is unavailable; retry or rebuild the sidecar") from exc


def assignment_metadata(previous, instructions):
    text = instructions[:METADATA_TEXT_LIMIT]
    stamp = datetime.now(timezone.utc)
    if previous.get("last_activity"):
        stamp = max(stamp, datetime.fromisoformat(previous["last_activity"]))
    return {"purpose": previous.get("purpose") or text, "recent_assignment": text,
            "last_activity": stamp.astimezone(timezone.utc).isoformat()}


def _normalise(text):
    return unicodedata.normalize("NFKC", text).casefold()


def _terms(text):
    return set(re.findall(r"[^\W_]+", _normalise(text)))


def find_workers(roster, query, limit=LOOKUP_LIMIT):
    if not isinstance(query, str) or not _terms(query[:QUERY_CHAR_LIMIT]):
        raise ValueError("query must contain words or numbers")
    if type(limit) is not int:
        raise ValueError("limit must be an integer")
    limit = max(1, min(LOOKUP_LIMIT, limit))
    truncated = len(query) > QUERY_CHAR_LIMIT
    query = query[:QUERY_CHAR_LIMIT]
    names, metadata = roster.discovery_snapshot()
    names = list(dict.fromkeys(names))
    collisions = Counter(_slugify(name) for name in names)
    tokens, normal_query = _terms(query), _normalise(query)
    ranked = []
    for name in names:
        record = metadata.get(name, {})
        fields = [("name", name, 20), ("purpose", record.get("purpose") or "", 6),
                  ("recent_assignment", record.get("recent_assignment") or "", 3)]
        reasons, score = [], 0
        if query == name:
            score += 10000
            reasons.append("exact_name")
        elif normal_query in _normalise(name):
            score += 1000
            reasons.append("name_phrase")
        for field, value, weight in fields:
            hits = tokens & _terms(value)
            if hits:
                score += weight * len(hits)
                reasons.append(field + "_terms")
        if score:
            ranked.append((-score, name, {"agent_name": name, "purpose": record.get("purpose"),
                           "recent_assignment": record.get("recent_assignment"),
                           "last_activity": record.get("last_activity"), "match_reasons": reasons,
                           "history_collision": collisions[_slugify(name)] > 1}))
    ranked.sort(key=lambda row: (row[0], row[1]))
    payload = {"status": "ok", "query_characters": len(query), "query_truncated": truncated,
               "total_workers": len(names), "total_matches": len(ranked), "workers": [], "omitted_matches": len(ranked)}
    for _, _, card in ranked:
        if len(payload["workers"]) >= limit:
            break
        for description_limit in (120, 40, 0):
            compact = {**card, "descriptions_limited": False}
            for field in ("purpose", "recent_assignment"):
                text = card[field]
                if text is not None and len(text) > description_limit:
                    compact[field] = text[:description_limit] if description_limit else None
                    compact["descriptions_limited"] = True
            trial = {**payload, "workers": [*payload["workers"], compact],
                     "omitted_matches": len(ranked) - len(payload["workers"]) - 1}
            if len(json.dumps(trial)) <= LOOKUP_CHAR_BUDGET:
                payload = trial
                break
    return payload


def render_recent(roster):
    names, metadata = roster.discovery_snapshot()
    names = list(dict.fromkeys(names))
    names.sort(key=lambda name: (-datetime.fromisoformat(metadata[name]["last_activity"]).timestamp()
                               if metadata.get(name, {}).get("last_activity") else float("inf"), name))
    collisions = Counter(_slugify(name) for name in names)
    rows = []
    for name in names:
        record = metadata.get(name, {})
        row = (f'<agent name="{escape(name, quote=True)}" purpose="{escape(record.get("purpose") or "unknown", quote=True)}" '
               f'last_activity="{escape(record.get("last_activity") or "unknown", quote=True)}" '
               f'history_collision="{str(collisions[_slugify(name)] > 1).lower()}" />')
        if len("\n".join([*rows, row])) <= ROSTER_CHAR_BUDGET - 400:
            rows.append(row)
        if len(rows) == RECENT_LIMIT:
            break
    header = f'<worker_catalog total="{len(names)}" shown="{len(rows)}" hidden="{len(names) - len(rows)}">'
    guidance = ("Recent assignments when known; unknown timestamps do not establish recency.\n"
                "Use find_worker to search all workers before creating new work. Shared history collisions need clarification.")
    return "\n".join([header, guidance, *rows, "</worker_catalog>"])
