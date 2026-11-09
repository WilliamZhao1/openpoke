"""Immutable content files with owner checks and history-clear invalidation."""

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import threading
from uuid import uuid4

from .config import get_settings
from .data_paths import get_data_dir


CAPTURE_BYTES = 4096
_REFERENCE = re.compile(r"c1_([0-9a-f]{32})_([0-9a-f]{32})")


class ContentStoreError(RuntimeError):
    pass


class ContentExpiredError(ContentStoreError):
    pass


@dataclass(frozen=True)
class ContentPage:
    reference: str
    metadata: dict
    content: bytes
    next_offset: int | None


class ContentStore:
    # Single application writer process, shared across explicit store handles.
    _lock = threading.RLock()

    def __init__(self, root=None):
        self.root = Path(root if root is not None else get_data_dir() / "content").resolve()

    def _objects(self):
        path = self.root / "objects"
        if path.resolve() != path:
            raise ContentStoreError("Content storage cannot use a linked objects directory")
        return path

    def _generation(self):
        path = self.root / "generation.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            generation = data["generation"]
            if not isinstance(generation, str) or re.fullmatch(r"[0-9a-f]{32}", generation) is None:
                raise ValueError()
            return generation
        except FileNotFoundError:
            objects = self._objects()
            if objects.exists() and any(objects.iterdir()):
                raise ContentStoreError("Content generation metadata is missing; restore it before use")
            generation = uuid4().hex
            self._write_generation(generation)
            return generation
        except (OSError, ValueError, TypeError, KeyError) as exc:
            raise ContentStoreError("Content generation metadata is unavailable") from exc

    def _write_generation(self, generation):
        self.root.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.root, delete=False) as handle:
                temporary = Path(handle.name)
                json.dump({"generation": generation}, handle)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.root / "generation.json")
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def generation(self):
        with self._lock:
            try:
                return self._generation()
            except OSError as exc:
                raise ContentStoreError("Could not initialize content storage") from exc

    def assert_generation(self, generation):
        with self._lock:
            if generation != self.generation():
                raise ContentExpiredError("Content history was cleared; this run cannot write into replacement history")

    @staticmethod
    def _qualification(owner, provider, account_id):
        if not isinstance(owner, str) or not owner:
            raise ValueError("Content owner is required")
        if provider is not None and (not isinstance(provider, str) or not provider):
            raise ValueError("Provider must be a nonempty string or explicitly unknown")
        if account_id is not None and (provider is None or not isinstance(account_id, str) or not account_id):
            raise ValueError("Known mailbox accounts require a provider and nonempty account ID")

    def put_text(self, text, *, owner, generation, kind, provider=None, account_id=None):
        self._qualification(owner, provider, account_id)
        if not isinstance(text, str) or not isinstance(kind, str) or not kind:
            raise ValueError("Text and content kind are required")
        try:
            body = text.encode("utf-8")
        except UnicodeError as exc:
            raise ContentStoreError("Content is not valid UTF-8 text") from exc
        with self._lock:
            self.assert_generation(generation)
            identifier = uuid4().hex
            reference = f"c1_{generation}_{identifier}"
            metadata = {"reference": reference, "owner": owner, "provider": provider, "account_id": account_id,
                        "kind": kind, "media_type": "text/plain; charset=utf-8", "size_bytes": len(body),
                        "sha256": sha256(body).hexdigest(), "created_at": datetime.now(timezone.utc).isoformat()}
            try:
                objects = self._objects() / generation
                if objects.resolve() != objects:
                    raise ContentStoreError("Content generation directory is linked")
                objects.mkdir(parents=True, exist_ok=True)
                # Publish body and metadata together. Names never contain owner/account text.
                with tempfile.TemporaryDirectory(prefix=".capture-", dir=objects) as directory:
                    temporary = Path(directory)
                    (temporary / "body.txt").write_bytes(body)
                    (temporary / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=True), encoding="utf-8")
                    target = objects / identifier
                    if target.exists():
                        raise ContentStoreError("Content identifier collision")
                    os.rename(temporary, target)
            except OSError as exc:
                raise ContentStoreError("Full content could not be preserved") from exc
            return reference

    def read_page(self, reference, *, owner, provider=None, account_id=None, offset=0, limit=8192):
        self._qualification(owner, provider, account_id)
        match = _REFERENCE.fullmatch(reference) if isinstance(reference, str) else None
        if match is None:
            raise ContentStoreError("Invalid content reference")
        if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 65536:
            raise ValueError("Content pages require a nonnegative offset and a limit of 1–65536 bytes")
        generation, identifier = match.groups()
        with self._lock:
            self.assert_generation(generation)
            path = self._objects() / generation / identifier
            if any(item.resolve() != item for item in (path, path / "metadata.json", path / "body.txt")):
                raise ContentStoreError("Content object directory is linked")
            try:
                metadata = json.loads((path / "metadata.json").read_text(encoding="utf-8"))
                if metadata["reference"] != reference or type(metadata["size_bytes"]) is not int or metadata["size_bytes"] < 0:
                    raise ValueError()
                if not isinstance(metadata["sha256"], str) or re.fullmatch(r"[0-9a-f]{64}", metadata["sha256"]) is None:
                    raise ValueError()
                if (metadata["owner"], metadata["provider"], metadata["account_id"]) != (owner, provider, account_id):
                    raise ContentStoreError("Content is unavailable for this owner or mailbox")
                with (path / "body.txt").open("rb") as handle:
                    if os.fstat(handle.fileno()).st_size != metadata["size_bytes"]:
                        raise ContentStoreError("Stored content is incomplete")
                    if offset > metadata["size_bytes"]:
                        raise ValueError("Content offset exceeds its size")
                    handle.seek(offset)
                    body = handle.read(limit)
            except FileNotFoundError as exc:
                raise ContentStoreError("Content reference is unavailable; missing or historical content cannot be reconstructed") from exc
            except (OSError, KeyError, TypeError, ValueError) as exc:
                raise ContentStoreError("Content storage is unavailable or invalid") from exc
            following = offset + len(body)
            return ContentPage(reference, metadata, body, following if following < metadata["size_bytes"] else None)

    def clear(self):
        with self._lock:
            if not self.root.exists():
                return
            try:
                # Invalidate leases first; even failed cleanup cannot revive old references.
                self._write_generation(uuid4().hex)
                objects = self._objects()
                if objects.exists():
                    for path in objects.iterdir():
                        if path.is_symlink() or path.resolve().parent != objects.resolve() or re.fullmatch(r"[0-9a-f]{32}", path.name) is None:
                            raise ContentStoreError("Unexpected content-storage path; old references were invalidated")
                        shutil.rmtree(path)
            except OSError as exc:
                raise ContentStoreError("Old content references were invalidated but file cleanup failed") from exc


@dataclass(frozen=True)
class ContentCapture:
    store: ContentStore
    generation: str
    owner: str


_capture: ContextVar[ContentCapture | None] = ContextVar("content_capture", default=None)


def current_capture():
    return _capture.get()


@contextmanager
def capture_scope(owner, *, generation=None):
    """Only content ownership/clear leases; no tool dispatch or approval state."""
    if get_settings().context_strategy != "bounded":
        yield None
        return
    parent = current_capture()
    store = parent.store if parent else ContentStore()
    lease = generation if generation is not None else parent.generation if parent else store.generation()
    context = ContentCapture(store, lease, owner)
    token = _capture.set(context)
    try:
        store.assert_generation(lease)
        yield context
    finally:
        _capture.reset(token)


def capture_text(text, *, kind, provider=None, account_id=None, min_bytes=CAPTURE_BYTES):
    context = current_capture()
    if context is None:
        return None  # No caller-owned capture; never invent ownership or mailbox provenance.
    context.store.assert_generation(context.generation)
    try:
        size = len(text.encode("utf-8"))
    except (AttributeError, UnicodeError) as exc:
        raise ContentStoreError("Captured content must be valid UTF-8 text") from exc
    if size <= min_bytes:
        return None
    return context.store.put_text(text, owner=context.owner, generation=context.generation, kind=kind,
                                  provider=provider, account_id=account_id)
