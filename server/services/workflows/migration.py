"""Read-only legacy migration inventory. Run this file directly, not with -m.

Keep this module stdlib-only: importing server initializes legacy writers. This
slice deliberately has no apply mode, WorkflowStore dependency, or generated IDs.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from hashlib import sha256
from html import unescape
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import sys
import tempfile


ROSTER = "execution_agents/roster.json"
CONVERSATION = "conversation/poke_conversation.log"
MEMORY = "conversation/poke_working_memory.log"
TRIGGERS = "triggers.db"
FIXED_SOURCES = (ROSTER, CONVERSATION, MEMORY, TRIGGERS,
                 "triggers.db-wal", "triggers.db-shm", "triggers.db-journal")
TRIGGER_COLUMNS = {"id", "agent_name", "payload", "start_time", "next_trigger",
                   "recurrence_rule", "timezone", "status", "last_error",
                   "created_at", "updated_at"}
ATTRIBUTES = re.compile(r'(\w+)\s*=\s*"([^"]*)"')


def legacy_slug(name: str) -> str:
    """Frozen legacy filename rule; parity-tested against the existing writer."""
    slug = "".join(ch.lower() if ch.isalnum() else "-" for ch in name.strip()).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug or "agent"


def parse_legacy_line(line: str):
    """Match legacy parsing/index semantics, without constructing a live store."""
    stripped = line.strip()
    if not stripped.startswith("<") or "</" not in stripped:
        return None
    open_end, close_start, close_end = stripped.find(">"), stripped.rfind("</"), stripped.rfind(">")
    if min(open_end, close_start, close_end) == -1:
        return None
    opening = stripped[1:open_end]
    tag, attributes = opening.split(" ", 1) if " " in opening else (opening, "")
    if stripped[close_start + 2:close_end] != tag:
        return None
    timestamp = dict(ATTRIBUTES.findall(attributes)).get("timestamp", "")
    payload = unescape(stripped[open_end + 1:close_start]).replace("\\n", "\n")
    return tag, timestamp, payload


def _json_bytes(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode("utf-8")


def _fingerprint(path):
    """No SQLite connection, writes, or whole-file buffering on source paths."""
    with path.open("rb") as handle:
        before = os.fstat(handle.fileno())
        digest = sha256()
        size = 0
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
        after = os.fstat(handle.fileno())
    signature = lambda stat: (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns)
    if signature(before) != signature(after) or size != after.st_size:
        raise OSError("Source changed during fingerprinting")
    return {"sha256": digest.hexdigest(), "size_bytes": size,
            "identity": list(signature(after))}


class LegacyMigrationInspector:
    def __init__(self, data_dir: Path, *, scope="local"):
        self.root = Path(data_dir).expanduser().resolve()
        if not self.root.is_dir():
            raise ValueError("--data-dir must identify an existing directory")
        if not isinstance(scope, str) or not scope.strip():
            raise ValueError("scope must be a nonempty string")
        self.scope = scope

    def _issue(self, code, path, *, severity="error", **details):
        self.issues.append({"code": code, "severity": severity, "path": path, "details": details})

    def _path(self, relative):
        path = self.root / relative
        # Refuse linked sources; the report must describe this profile's inputs.
        if path.resolve() != path:
            raise OSError("Linked migration sources require reconciliation")
        return path

    def _discover(self):
        directory = self._path("execution_agents")
        logs = []
        if directory.exists():
            logs = [path.relative_to(self.root).as_posix() for path in directory.iterdir()
                    if path.suffix.lower() == ".log"]
        return sorted(set(FIXED_SOURCES) | set(logs))

    def _capture(self, relative):
        try:
            path = self._path(relative)
            fingerprint = _fingerprint(path)
            return {"path": relative, "status": "available", **fingerprint}
        except FileNotFoundError:
            return {"path": relative, "status": "missing"}
        except OSError:
            self._issue("source_unreadable", relative)
            return {"path": relative, "status": "unavailable"}

    def inspect(self):
        # Reusable inspector instances do not retain earlier reports.
        self.issues = []
        try:
            paths = self._discover()
        except OSError:
            paths = sorted(FIXED_SOURCES)
            self._issue("source_discovery_failed", "execution_agents")
        self.sources = {path: self._capture(path) for path in paths}
        roster = self._roster()
        names = defaultdict(list)
        slugs = defaultdict(list)
        for entry in roster:
            if entry["name"] is not None:
                names[entry["name"]].append(entry["roster_index"])
        for name, indices in names.items():
            slugs[legacy_slug(name)].append(name)
            if len(indices) > 1:
                self._issue("duplicate_roster_alias", ROSTER, name=name, roster_indices=indices)
        for slug, owners in sorted(slugs.items()):
            if len(owners) > 1:
                self._issue("slug_collision", f"execution_agents/{slug}.log", owner_names=owners)

        workers = []
        actual_logs = {path for path in paths if path.startswith("execution_agents/") and path != ROSTER}
        expected_logs = {f"execution_agents/{slug}.log" for slug in slugs}
        for path in sorted(actual_logs | expected_logs):
            if path not in self.sources:
                self.sources[path] = self._capture(path)
            owners = slugs.get(Path(path).stem, [])
            resolution = "resolved" if len(owners) == 1 and len(names[owners[0]]) == 1 else "unresolved"
            if not owners:
                self._issue("orphan_worker_log", path)
            elif self.sources[path]["status"] == "missing":
                self._issue("worker_log_missing", path, severity="warning", owner_names=owners)
            log = self._log(path)
            requests = [entry for entry in log["entries"] if entry["tag"] == "agent_request"]
            workers.append({"path": path, "owner_names": owners, "owner_resolution": resolution,
                            "workflow_status": None, "purpose": None,
                            "first_request_ref": requests[0]["ref"] if requests else None,
                            "latest_request_ref": requests[-1]["ref"] if requests else None, **log})
            if any(entry["tag"] in {"tool_response", "agent_action"} for entry in log["entries"]):
                self._issue("legacy_tool_content_may_be_truncated", path, severity="warning")

        conversation = self._log(CONVERSATION)
        memory = self._memory(conversation)
        triggers = self._triggers(names)
        unchanged = self._verify_sources(paths)
        errors = sum(issue["severity"] == "error" for issue in self.issues)
        return {"report_version": 1, "mode": "dry-run", "data_dir": str(self.root), "scope": self.scope,
                "status": "blocked" if errors else "review_ready", "apply_supported": False,
                "source_set_unchanged": unchanged,
                "consistency": "observational_only; pause all writers and revalidate before apply",
                "sources": [self.sources[path] for path in sorted(self.sources)],
                "roster_entries": roster, "worker_logs": workers, "conversation": conversation,
                "working_memory": memory, "triggers": triggers, "issues": self.issues,
                "counts": {"roster_entries": len(roster), "worker_logs": len(workers),
                           "conversation_entries": len(conversation["entries"]),
                           "triggers": len(triggers["records"]), "errors": errors,
                           "warnings": sum(issue["severity"] == "warning" for issue in self.issues)}}

    def _roster(self):
        if self.sources[ROSTER]["status"] != "available":
            return []
        try:
            with self._path(ROSTER).open("r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, UnicodeError, ValueError):
            self._issue("roster_invalid_json", ROSTER)
            return []
        if not isinstance(data, list):
            self._issue("roster_not_a_list", ROSTER)
            return []
        entries = []
        for index, name in enumerate(data):
            valid = isinstance(name, str)
            entries.append({"roster_index": index, "name": name if valid else None,
                            "value_type": type(name).__name__, "workflow_id": None,
                            "legacy_log_path": f"execution_agents/{legacy_slug(name)}.log" if valid else None})
            if not valid:
                self._issue("roster_name_not_string", ROSTER, roster_index=index)
            elif not name.strip():
                self._issue("display_name_required", ROSTER, roster_index=index, exact_alias=name)
        return entries

    def _log(self, relative, *, include_payload=False):
        result = {"entries": [], "unparsed_lines": [], "tag_counts": {}}
        if self.sources[relative]["status"] != "available":
            return result
        digest, offset, tags = sha256(), 0, Counter()
        try:
            with self._path(relative).open("rb") as handle:
                for line_number, raw in enumerate(handle, 1):
                    digest.update(raw)
                    ref = {"path": relative, "line": line_number, "byte_offset": offset, "byte_length": len(raw)}
                    offset += len(raw)
                    try:
                        line = raw.decode("utf-8")
                    except UnicodeError:
                        line = None
                    parsed = parse_legacy_line(line) if line is not None else None
                    if parsed is None:
                        result["unparsed_lines"].append(ref)
                        self._issue("unparsed_log_line", relative, line=line_number)
                        continue
                    tag, timestamp, payload = parsed
                    entry = {"ref": ref, "legacy_index": len(result["entries"]), "tag": tag,
                             "timestamp": timestamp or None, "payload_sha256": sha256(payload.encode("utf-8")).hexdigest(),
                             "payload_characters": len(payload)}
                    if include_payload and tag == "summary_info":
                        entry["_payload"] = payload
                    result["entries"].append(entry)
                    tags[tag] += 1
                    if not re.fullmatch(r'<([A-Za-z_]\w*)(?: timestamp="[^"]*")?>.*</\1>', line.strip()):
                        self._issue("noncanonical_log_line", relative, line=line_number)
                    if len(line.splitlines()) > 1:
                        self._issue("legacy_line_separator_ambiguous", relative, line=line_number)
            if digest.hexdigest() != self.sources[relative]["sha256"]:
                self._issue("source_changed_during_scan", relative)
        except OSError:
            self._issue("log_read_failed", relative)
        result["tag_counts"] = dict(sorted(tags.items()))
        return result

    def _memory(self, conversation):
        log = self._log(MEMORY, include_payload=True)
        infos = [entry for entry in log["entries"] if entry["tag"] == "summary_info"]
        summaries = [entry for entry in log["entries"] if entry["tag"] == "conversation_summary"]
        tail = [entry for entry in log["entries"] if entry["tag"] not in {"summary_info", "conversation_summary"}]
        result = {"present": self.sources[MEMORY]["status"] == "available", "last_index": None,
                  "boundary_ref": None, "summary_ref": None, "summary_sha256": None,
                  "summary_info_ref": None, "updated_at": None, "tail_matches_conversation": None, **log}
        try:
            if not result["present"]:
                return result
            if len(infos) != 1 or len(summaries) != 1:
                self._issue("summary_records_ambiguous", MEMORY, info_records=len(infos), summary_records=len(summaries))
                return result
            info, summary = infos[0], summaries[0]
            result.update(summary_ref=summary["ref"], summary_sha256=summary["payload_sha256"], summary_info_ref=info["ref"])
            try:
                metadata = json.loads(info["_payload"])
                last_index = metadata["last_index"]
                if type(last_index) is not int or last_index < -1:
                    raise ValueError()
                updated_at = metadata.get("updated_at")
                if updated_at is not None and not isinstance(updated_at, str):
                    raise ValueError()
            except (ValueError, TypeError, KeyError):
                self._issue("summary_metadata_invalid", MEMORY)
                return result
            result.update(last_index=last_index, updated_at=updated_at)
            entries = conversation["entries"]
            if last_index >= len(entries):
                self._issue("summary_boundary_missing", MEMORY, last_index=last_index, conversation_entries=len(entries))
                return result
            if last_index >= 0:
                result["boundary_ref"] = entries[last_index]["ref"]
            identity = lambda entry: (entry["tag"], entry["timestamp"], entry["payload_sha256"])
            matches = [identity(entry) for entry in tail] == [identity(entry) for entry in entries[last_index + 1:]]
            result["tail_matches_conversation"] = matches
            if not matches:
                self._issue("working_memory_tail_mismatch", MEMORY, last_index=last_index)
            return result
        finally:
            for entry in log["entries"]:
                entry.pop("_payload", None)  # Reports retain references/hashes, not conversation text.

    def _triggers(self, names):
        result = {"records": [], "logical_sha256": None, "schema_sha256": None,
                  "snapshot": "temporary copy of main database and WAL; source never opened by SQLite"}
        source = self.sources[TRIGGERS]
        if source["status"] != "available":
            if self.sources["triggers.db-wal"]["status"] == "available":
                self._issue("trigger_database_missing_with_wal", TRIGGERS)
            return result
        if self.sources["triggers.db-journal"].get("size_bytes", 0):
            self._issue("trigger_rollback_journal_present", "triggers.db-journal")
            return result
        try:
            with tempfile.TemporaryDirectory(prefix="openpoke-migration-inspect-") as directory:
                target = Path(directory) / TRIGGERS
                for relative in (TRIGGERS, "triggers.db-wal"):
                    if self.sources[relative]["status"] == "available":
                        shutil.copyfile(self._path(relative), Path(directory) / relative)
                        if _fingerprint(Path(directory) / relative)["sha256"] != self.sources[relative]["sha256"]:
                            self._issue("source_changed_during_copy", relative)
                            return result
                connection = sqlite3.connect(target, timeout=0.25)
                try:
                    connection.row_factory = sqlite3.Row
                    connection.execute("PRAGMA query_only=ON")
                    connection.execute("BEGIN")
                    if connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                        self._issue("trigger_integrity_failed", TRIGGERS)
                        return result
                    columns = {row[1] for row in connection.execute("PRAGMA table_info(triggers)")}
                    if not TRIGGER_COLUMNS.issubset(columns):
                        self._issue("trigger_schema_unsupported", TRIGGERS, missing_columns=sorted(TRIGGER_COLUMNS - columns))
                        return result
                    schema = [tuple(row) for row in connection.execute("SELECT type, name, tbl_name, sql FROM sqlite_master ORDER BY type, name")]
                    result["schema_sha256"] = sha256(_json_bytes(schema)).hexdigest()
                    digest = sha256()
                    for row in connection.execute("SELECT * FROM triggers ORDER BY id"):
                        data = dict(row)
                        row_bytes = _json_bytes(data)
                        digest.update(row_bytes + b"\n")
                        owner = data["agent_name"]
                        valid = isinstance(owner, str) and len(names.get(owner, [])) == 1
                        record = {"legacy_trigger_id": data["id"], "agent_name": owner,
                                  "owner_resolution": "resolved" if valid else "unresolved",
                                  "roster_indices": names.get(owner, []) if isinstance(owner, str) else [],
                                  "status": data["status"], "row_sha256": sha256(row_bytes).hexdigest()}
                        result["records"].append(record)
                        if not valid:
                            self._issue("trigger_owner_unresolved", TRIGGERS, trigger_id=data["id"], agent_name=owner)
                        if data.get("workflow_id") is not None:
                            self._issue("trigger_existing_workflow_binding", TRIGGERS, trigger_id=data["id"])
                    result["logical_sha256"] = digest.hexdigest()
                finally:
                    connection.close()
        except (OSError, sqlite3.Error, TypeError, ValueError):
            self._issue("trigger_snapshot_read_failed", TRIGGERS)
        return result

    def _verify_sources(self, discovered):
        unchanged = not any(source["status"] == "unavailable" for source in self.sources.values())
        if any(issue["code"] == "source_discovery_failed" for issue in self.issues):
            unchanged = False
        for relative, original in self.sources.items():
            current = self._capture(relative)
            if current != original:
                unchanged = False
                self._issue("source_changed_during_scan", relative)
        try:
            if self._discover() != discovered:
                unchanged = False
                self._issue("source_set_changed_during_scan", "execution_agents")
        except OSError:
            unchanged = False
            self._issue("source_discovery_failed", "execution_agents")
        if any(issue["code"].startswith("source_changed_") for issue in self.issues):
            unchanged = False
        return unchanged


def main(argv=None):
    parser = argparse.ArgumentParser(description="Inspect legacy migration inputs without importing the app or modifying source files.")
    parser.add_argument("--data-dir", required=True, type=Path, help="Explicit existing legacy data root; no app config is imported.")
    parser.add_argument("--scope", default="local")
    parser.add_argument("--output", type=Path, help="New JSON file outside the source root; parent must already exist. Defaults to stdout.")
    args = parser.parse_args(argv)
    try:
        inspector = LegacyMigrationInspector(args.data_dir, scope=args.scope)
        output = args.output.expanduser().resolve() if args.output is not None else None
        if output is not None and output.is_relative_to(inspector.root):
            raise ValueError("--output must be outside the inspected data root")
        report = inspector.inspect()
        rendered = json.dumps(report, indent=2, ensure_ascii=True) + "\n"
        if output is None:
            sys.stdout.write(rendered)
        else:
            with output.open("x", encoding="utf-8") as handle:
                handle.write(rendered)
        return 2 if report["status"] == "blocked" else 0
    except (OSError, ValueError):
        print("Migration inspection failed: use an existing data directory and a new output file outside it.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
