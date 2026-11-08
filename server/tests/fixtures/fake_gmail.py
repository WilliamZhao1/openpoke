"""Local Gmail tool effects for frozen evaluations, not a full Gmail emulator."""

from collections import defaultdict, deque
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import re
import shlex
from types import SimpleNamespace
from unittest.mock import patch

from .catalogs import load_fixture


@dataclass
class FrozenClock:
    current: datetime

    def __post_init__(self):
        if self.current.tzinfo is None:
            raise ValueError("Fixture clock requires an aware timestamp")
        self.current = self.current.astimezone(timezone.utc)

    def now(self) -> str:
        return self.current.isoformat().replace("+00:00", "Z")

    def advance(self, *, seconds: int):
        if type(seconds) is not int or seconds < 0:
            raise ValueError("Fixture clock advances by nonnegative integer seconds")
        self.current += timedelta(seconds=seconds)


class FakeGmail:
    """Account-qualified state, deterministic IDs, and explicit write evidence.

    This fake performs requested sends without inventing application approval.
    It has no network client, fallback, random IDs, or wall-clock dependency.
    """

    def __init__(self, seed=None):
        seed = deepcopy(seed if seed is not None else load_fixture("gmail_mailbox.json"))
        self.clock = FrozenClock(datetime.fromisoformat(seed["fixed_now"].replace("Z", "+00:00")))
        self._accounts = {}
        self._profiles = {}
        self._calls = []
        self._effects = []
        self._failures = defaultdict(deque)
        for index, account in enumerate(seed["accounts"]):
            account_id = account["account_id"]
            profile_id = account["profile_id"]
            if account_id in self._accounts or profile_id in self._profiles:
                raise ValueError("Duplicate fixture account/profile")
            account["messages"] = self._index(account["messages"])
            account["drafts"] = self._index(account["drafts"])
            account["index"] = index
            account["counters"] = {"message": 0, "thread": 0, "draft": 0}
            self._accounts[account_id] = account
            self._profiles[profile_id] = account_id

    @staticmethod
    def _index(records):
        indexed = {record["id"]: record for record in records}
        if len(indexed) != len(records):
            raise ValueError("Duplicate resource ID within a fixture account")
        return indexed

    @property
    def calls(self):
        return deepcopy(self._calls)

    @property
    def effects(self):
        return deepcopy(self._effects)

    def snapshot(self):
        return deepcopy({
            "fixture_version": 1, "source_mode": "mock", "now": self.clock.now(),
            "accounts": self._accounts, "calls": self._calls, "effects": self._effects,
        })

    def fail_next(self, tool_name: str, *, phase: str = "before"):
        """Fail once before the operation, or after its effects have happened."""
        if phase not in {"before", "after"}:
            raise ValueError("Failure phase must be before or after")
        self._failures[tool_name].append(phase)

    def as_composio_client(self):
        return SimpleNamespace(client=SimpleNamespace(tools=SimpleNamespace(execute=self.execute)))

    def execute(self, tool_name: str, *, user_id: str, arguments=None):
        arguments = deepcopy({key: value for key, value in (arguments or {}).items() if value is not None})
        call = {
            "sequence": len(self._calls) + 1, "tool": tool_name, "profile_id": user_id,
            "arguments": arguments, "timestamp": self.clock.now(), "source_mode": "mock",
            "outcome": "failed",
        }
        self._calls.append(call)
        try:
            account = self._accounts[self._profiles[user_id]]
            call["account_id"] = account["account_id"]
            if arguments.get("user_id", "me") != "me":
                raise ValueError("Fixture supports only user_id=me within the selected account")
            queue = self._failures[tool_name]
            phase = queue.popleft() if queue else None
            if phase == "before":
                raise RuntimeError("Injected fixture failure before operation")
            data = self._dispatch(tool_name, account, arguments)
            if phase == "after":
                call["outcome"] = "unknown"
                raise RuntimeError("Injected fixture failure after operation; reconcile effects")
            call["outcome"] = "succeeded"
            return deepcopy({
                "successful": True, "data": data,
                "fixture": {"source_mode": "mock", "provider": "gmail", "account_id": account["account_id"]},
            })
        except KeyError as exc:
            raise ValueError("Unknown fixture account or resource") from exc

    def _new_id(self, account, kind):
        account["counters"][kind] += 1
        number = account["counters"][kind]
        if kind == "draft":
            return f"r9{account['index']:02d}{number:014d}"
        prefix = "19" if kind == "message" else "1a"
        return f"{prefix}{account['index']:02x}{number:012x}"

    def _effect(self, kind, account, **details):
        self._effects.append(deepcopy({
            "sequence": len(self._effects) + 1, "kind": kind,
            "provider": "gmail", "account_id": account["account_id"],
            "timestamp": self.clock.now(), "source_mode": "mock", **details,
        }))

    def _thread_exists(self, account, thread_id):
        return any(message["threadId"] == thread_id for message in account["messages"].values()) or any(
            draft["message"]["threadId"] == thread_id for draft in account["drafts"].values()
        )

    def _message(self, account, *, recipient, subject, body, thread_id, is_html=False, options=None):
        options = options or {}
        return {
            "id": self._new_id(account, "message"), "threadId": thread_id,
            "sender": account["email"], "to": recipient, "subject": subject,
            "htmlBody" if is_html else "textBody": body,
            "messageTimestamp": self.clock.now(), "labelIds": [],
            "attachmentList": [deepcopy(options["attachment"])] if options.get("attachment") else [],
            **{key: deepcopy(options.get(key, [])) for key in ("cc", "bcc", "extra_recipients")},
        }

    def _dispatch(self, tool, account, args):
        if tool == "GMAIL_FETCH_EMAILS":
            return self._fetch(account, args)
        if tool == "GMAIL_CREATE_EMAIL_DRAFT":
            recipient, subject, body = args["recipient_email"], args["subject"], args["body"]
            thread = args.get("thread_id")
            if thread and not self._thread_exists(account, thread):
                raise ValueError("Unknown fixture thread")
            thread = thread or self._new_id(account, "thread")
            message = self._message(account, recipient=recipient, subject=subject, body=body,
                                    thread_id=thread, is_html=args.get("is_html", False), options=args)
            message["labelIds"] = ["DRAFT"]
            draft_id = self._new_id(account, "draft")
            draft = {"id": draft_id, "message": message, "body": body, "is_html": args.get("is_html", False)}
            account["drafts"][draft_id] = draft
            self._effect("draft_created", account, draft_id=draft_id, message=message, body=body)
            return draft
        if tool in {"GMAIL_SEND_DRAFT", "GMAIL_DELETE_DRAFT"}:
            draft = account["drafts"].pop(args["draft_id"])
            if tool == "GMAIL_DELETE_DRAFT":
                self._effect("draft_deleted", account, draft_id=draft["id"])
                return {"id": draft["id"], "deleted": True}
            message = deepcopy(draft["message"])
            message["id"] = self._new_id(account, "message")
            message["messageTimestamp"] = self.clock.now()
            message["labelIds"] = ["SENT"]
            account["messages"][message["id"]] = message
            self._effect("draft_sent", account, draft_id=draft["id"], message=message, body=draft["body"])
            return {"id": message["id"], "threadId": message["threadId"], "draft_id": draft["id"]}
        if tool in {"GMAIL_REPLY_TO_THREAD", "GMAIL_FORWARD_MESSAGE"}:
            if tool == "GMAIL_REPLY_TO_THREAD":
                thread = args["thread_id"]
                source = next((message for message in account["messages"].values() if message["threadId"] == thread), None)
                if source is None:
                    raise ValueError("Unknown fixture thread")
                body = args["message_body"]
                subject = "Re: " + source["subject"].removeprefix("Re: ")
                kind = "reply_sent"
            else:
                source = account["messages"][args["message_id"]]
                thread = self._new_id(account, "thread")
                body = source.get("textBody", source.get("htmlBody", ""))
                if args.get("additional_text"):
                    body = args["additional_text"] + "\n\n" + body
                subject = "Fwd: " + source["subject"]
                kind = "forward_sent"
            message = self._message(account, recipient=args["recipient_email"], subject=subject, body=body,
                                    thread_id=thread, is_html=args.get("is_html", False), options=args)
            message["labelIds"] = ["SENT"]
            account["messages"][message["id"]] = message
            self._effect(kind, account, source_message_id=source["id"], message=message, body=body)
            return {"id": message["id"], "threadId": thread}
        if tool == "GMAIL_LIST_DRAFTS":
            rows = sorted(account["drafts"].values(), key=lambda row: row["id"])
            page, token = self._page(account, tool, rows, args)
            return {"drafts": page, "nextPageToken": token}
        if tool in {"GMAIL_GET_CONTACTS", "GMAIL_GET_PEOPLE", "GMAIL_SEARCH_PEOPLE"}:
            rows = deepcopy(account["contacts"])
            resource = args.get("resource_name", "people/me")
            if resource != "people/me":
                rows = [row for row in rows if row["resourceName"] == resource]
                if not rows:
                    raise ValueError("Unknown fixture person")
            query = args.get("query", "").casefold()
            rows = [row for row in rows if query in json.dumps(row, ensure_ascii=False).casefold()]
            page, token = self._page(account, tool + query + resource, rows, args)
            if tool == "GMAIL_SEARCH_PEOPLE":
                return {"results": [{"person": row} for row in page], "nextPageToken": token}
            return {"connections": page, "nextPageToken": token}
        raise ValueError(f"Unsupported fixture Gmail tool: {tool}")

    def _page(self, account, context, rows, args):
        limit = args.get("max_results", args.get("page_size", args.get("pageSize", 100)))
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("Fixture page size must be between 1 and 100")
        keys = [row.get("id", row.get("resourceName")) for row in rows]
        signature = hashlib.sha256(json.dumps([account["account_id"], context, keys]).encode()).hexdigest()[:16]
        token = args.get("page_token", args.get("pageToken"))
        start = 0
        if token:
            try:
                prefix, supplied, offset = token.split(":")
                start = int(offset)
            except (ValueError, AttributeError) as exc:
                raise ValueError("Invalid fixture page token") from exc
            if prefix != "fixture" or supplied != signature or not 0 < start < len(rows):
                raise ValueError("Fixture page token does not match this account/query/state")
        end = start + limit
        continuation = f"fixture:{signature}:{end}" if end < len(rows) else None
        return deepcopy(rows[start:end]), continuation

    def _fetch(self, account, args):
        query = args.get("query", "")
        tokens = shlex.split(query)
        predicates = []
        for token in tokens:
            key, separator, value = token.partition(":")
            if token == "OR" or token.startswith(("-", "{", "}")):
                raise ValueError("Unsupported fixture Gmail query syntax")
            if not separator:
                predicates.append(lambda message, term=token.casefold(): term in (message["subject"] + " " + message.get("textBody", message.get("htmlBody", ""))).casefold())
            elif key in {"from", "to", "subject"}:
                field = "sender" if key == "from" else key
                predicates.append(lambda message, field=field, term=value.casefold(): term in message[field].casefold())
            elif key in {"in", "label"}:
                predicates.append(lambda message, label=value.upper(): label in message["labelIds"])
            elif key == "newer_than" and re.fullmatch(r"\d+[mhd]", value):
                units = {"m": 60, "h": 3600, "d": 86400}
                cutoff = self.clock.current - timedelta(seconds=int(value[:-1]) * units[value[-1]])
                predicates.append(lambda message, cutoff=cutoff: datetime.fromisoformat(message["messageTimestamp"].replace("Z", "+00:00")) >= cutoff)
            else:
                raise ValueError(f"Unsupported fixture Gmail query field: {key}")
        labels = set(args.get("label_ids", []))
        rows = [message for message in account["messages"].values()
                if labels.issubset(message["labelIds"]) and all(predicate(message) for predicate in predicates)]
        rows.sort(key=lambda message: (message["messageTimestamp"], message["id"]), reverse=True)
        page, token = self._page(account, "fetch:" + query + ":" + ",".join(sorted(labels)), rows, args)
        if args.get("ids_only"):
            page = [{"id": message["id"], "threadId": message["threadId"]} for message in page]
        return {"messages": page, "nextPageToken": token}


@contextmanager
def use_fake_gmail(fake: FakeGmail, *, profile_id="fixture-profile-a"):
    """Bind below all current Gmail adapters for the scoped test session."""
    from server.data_paths import get_data_dir
    from server.services.gmail import client

    if profile_id not in fake._profiles:
        raise ValueError("Unknown fixture profile")
    with (
        patch.object(client, "_get_composio_client", return_value=fake.as_composio_client()),
        patch.object(client, "_ACTIVE_USER_ID", profile_id),
        patch.object(client, "_ACTIVE_USER_ID_PATH", get_data_dir() / "gmail" / "fixture_active_user.txt"),
        patch.object(client, "_PROFILE_CACHE", {}),
    ):
        yield fake
