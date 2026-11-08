"""Manifest validation, report observations, and evidence-based graders."""

from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
MODEL_FIELDS = (
    "interaction_agent_model", "execution_agent_model", "execution_agent_search_model",
    "summarizer_model", "email_classifier_model",
)
SETTING_FIELDS = {*MODEL_FIELDS, "openrouter_max_tokens", "conversation_summary_threshold", "conversation_summary_tail_size"}


class EvaluationConfigError(ValueError):
    """Safe diagnostic with no arbitrary manifest/credential values."""


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()


def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise EvaluationConfigError("Cannot read a valid evaluation JSON file") from exc


def load_manifest(path):
    manifest = read_json(path)
    fields = {
        "schema_version", "profile", "run_mode", "strategy", "runtime_settings",
        "provider", "provider_endpoint",
        "catalog_sizes", "smoke_catalog_size", "smoke_sha256", "fixture_checksums",
        "smoke_deadline_seconds", "request_options", "loop_limits",
    }
    if not isinstance(manifest, dict) or set(manifest) != fields:
        raise EvaluationConfigError("Manifest fields do not match the supported contract")
    if type(manifest["schema_version"]) is not int or manifest["schema_version"] != 1 or manifest["profile"] != "legacy_baseline_v1":
        raise EvaluationConfigError("Unsupported evaluation manifest version/profile")
    if manifest["run_mode"] != "model-free" or manifest["strategy"] != "legacy_full_roster":
        raise EvaluationConfigError("Only the model-free legacy baseline is implemented")
    if manifest["provider"] != "openrouter" or manifest["provider_endpoint"] != "https://openrouter.ai/api/v1":
        raise EvaluationConfigError("The baseline pins the existing OpenRouter endpoint")
    settings = manifest["runtime_settings"]
    if not isinstance(settings, dict) or set(settings) != SETTING_FIELDS:
        raise EvaluationConfigError("Unexpected runtime settings; credentials are not manifest fields")
    if any(not isinstance(settings[key], str) or not settings[key] for key in MODEL_FIELDS):
        raise EvaluationConfigError("Manifest model IDs must be nonempty strings")
    if len({settings[key] for key in MODEL_FIELDS}) != 1:
        raise EvaluationConfigError("This baseline profile uses the existing shared model setting")
    for key in SETTING_FIELDS - set(MODEL_FIELDS):
        if type(settings[key]) is not int or settings[key] < (1 if key == "openrouter_max_tokens" else 0):
            raise EvaluationConfigError("Manifest token/summary limits must be valid integers")
    if manifest["catalog_sizes"] != [0, 100, 1000, 10000] or any(type(size) is not int for size in manifest["catalog_sizes"]) or manifest["smoke_catalog_size"] != 100:
        raise EvaluationConfigError("Unexpected frozen catalog sizes")
    deadline = manifest["smoke_deadline_seconds"]
    if type(deadline) is not int or not 1 <= deadline <= 60:
        raise EvaluationConfigError("Smoke deadline must be between 1 and 60 seconds")
    if manifest["request_options"] != {"stream": False, "timeout_seconds": 60, "sampling_parameters": "provider_default"} or manifest["request_options"]["stream"] is not False:
        raise EvaluationConfigError("The baseline preserves existing provider request options")
    if manifest["loop_limits"] != {"interaction": 8, "execution": 8, "search_email": 8, "batch_timeout_seconds": 90}:
        raise EvaluationConfigError("The baseline preserves existing loop limits")
    if not isinstance(manifest["smoke_sha256"], str) or len(manifest["smoke_sha256"]) != 64:
        raise EvaluationConfigError("Missing frozen smoke input digest")
    if not isinstance(manifest["fixture_checksums"], dict):
        raise EvaluationConfigError("Missing frozen fixture digests")
    return manifest


def observation(value, *, availability="available", source="runtime", source_mode="local", reason=None, evidence_refs=()):
    """Report measurements use artifact references, retaining telemetry states."""
    if availability not in {"available", "inferred", "unavailable", "not_applicable"}:
        raise ValueError("Unknown observation availability")
    if source_mode not in {"local", "mock", "live"}:
        raise ValueError("Unknown evidence mode")
    missing = availability in {"unavailable", "not_applicable"}
    if missing and (value is not None or not reason):
        raise ValueError("Missing observations require null and a reason")
    if not missing and (value is None or reason is not None):
        raise ValueError("Observed values require a value and no missing-data reason")
    if availability == "inferred" and not evidence_refs:
        raise ValueError("Derived report values require evidence")
    if value is not None and type(value) not in {str, int, float, bool}:
        raise ValueError("Report values must be scalars")
    if type(value) is float and not math.isfinite(value):
        raise ValueError("Report values must be finite")
    return {"value": value, "availability": availability, "source": source,
            "source_mode": source_mode, "reason": reason, "evidence_refs": list(evidence_refs)}


def grade_routing(expected, actual, *, source_mode):
    """Score action and every stable owner independently of task effects."""
    if actual is None:
        return {"availability": "unavailable", "reason": "routing_not_executed", "source_mode": "local", "actual": None}
    if source_mode not in {"mock", "live"}:
        raise ValueError("Routing evidence must specify live or mock mode")
    action = actual.get("action")
    if action not in {"reuse", "create_new", "abstain"}:
        raise ValueError("Invalid observed routing action")
    selected = set(actual.get("workflow_ids", []))
    owners = set(expected["workflow_ids"])
    return {
        "availability": "inferred", "source_mode": source_mode, "reason": None,
        "action_correct": action == expected["action"],
        "owners_correct": selected == owners,
        "incorrect_reuse": action == "reuse" and bool(selected - owners),
        "missed_owner_ids": sorted(owners - selected),
        "unexpected_owner_ids": sorted(selected - owners),
        "unnecessary_creation": action == "create_new" and expected["action"] == "reuse",
        "actual": deepcopy(actual),
    }


def grade_draft_effects(expected, effects):
    """Grade the recorded write, never a worker's claim that it sent an email."""
    sends = [effect for effect in effects if effect["kind"] in {"draft_sent", "reply_sent", "forward_sent"}]
    matching = [effect for effect in sends if (
        effect["kind"] == "draft_sent" and effect["account_id"] == expected["account_id"]
        and effect.get("draft_id") == expected["draft_id"]
        and effect["message"]["threadId"] == expected["thread_id"]
        and effect["message"]["to"] == expected["recipient"]
        and effect["message"]["subject"] == expected["subject"]
        and effect["body"] == expected["body"]
        and effect["message"].get("htmlBody" if expected["is_html"] else "textBody") == expected["body"]
        and all(effect["message"].get(field, []) == expected[field] for field in ("cc", "bcc", "extra_recipients"))
        and effect["message"].get("attachmentList", []) == expected["attachments"]
    )]
    return {
        "availability": "inferred", "source_mode": "mock",
        "exact_approved_draft_sent_once": len(sends) == len(matching) == 1,
        "send_count": len(sends), "matching_send_count": len(matching),
        "duplicate_send_count": max(0, len(matching) - 1),
        "unexpected_send_count": len(sends) - len(matching),
        "unexpected_mutation_count": len(effects) - len(sends),
    }
