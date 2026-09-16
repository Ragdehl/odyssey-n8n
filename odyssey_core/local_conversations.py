"""Root-bound, segmented conversation presentation state."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any

from .conversations import (
    MAIN_CONVERSATION_ID,
    _CHUNK_MAX_TURNS,
    _PAGE_DEFAULT_TURNS,
    _PAGE_MAX_TURNS,
    _RECENT_CONTEXT_MAX_BYTES,
    _RECENT_CONTEXT_MAX_TURNS,
    ConversationError,
    _timestamp,
    _validate_actor,
    _validate_id,
    _validate_request_detail,
    _validate_turn,
)

_MAX_RECORD_BYTES = 256 * 1024
_MAX_TURN_TEXT_BYTES = 64 * 1024


class ConversationRootResolver:
    """Resolve authenticated actors to isolated, user-local conversation roots.

    This is the hosted compatibility boundary.  The root-bound store receives no actor identity and
    therefore does not persist it inside its new manifest, chunks, or request index.
    """

    def __init__(self, state_root: Path) -> None:
        self._root = state_root / "conversations"

    def resolve(self, actor_id: str) -> Path:
        """Return one stable local state root for a validated internal actor."""
        actor = _validate_actor(actor_id)
        return self._root / hashlib.sha256(actor.encode("utf-8")).hexdigest()


class LocalConversationStore:
    """Persist one local root's durable segmented `main` transcript.

    Each JSON document is atomically replaced.  A corrupt manifest, chunk, cursor, or incomplete
    migration fails closed.  This store is presentation/operational state only: it is not a vault,
    semantic index, retrieval corpus, or multi-user tenancy layer.
    """

    def __init__(self, root: Path) -> None:
        self._root = root
        self._cursor_key = hashlib.sha256(str(root.absolute()).encode("utf-8")).digest()

    def load_or_create_main(self, *, now: str) -> dict[str, Any]:
        """Return the local main transcript, creating or safely migrating it if needed."""
        if self._main_directory().exists():
            return self.load_main_page()
        if self._legacy_main_path().exists():
            self._migrate_legacy_main()
            return self.load_main_page()
        self._write(
            self._main_directory() / "manifest.json",
            {
                "conversation_id": MAIN_CONVERSATION_ID,
                "created_at": _timestamp(now),
                "updated_at": _timestamp(now),
                "turn_count": 0,
                "chunks": [],
            },
        )
        return self.load_main_page()

    def load_main_page(
        self, *, limit: int = _PAGE_DEFAULT_TURNS, before: str | None = None
    ) -> dict[str, Any]:
        """Return one chronological page without deserializing unrelated history chunks."""
        if (
            not isinstance(limit, int)
            or isinstance(limit, bool)
            or not 1 <= limit <= _PAGE_MAX_TURNS
        ):
            raise ConversationError("conversation page limit is invalid")
        manifest = self._manifest()
        end = (
            manifest["turn_count"]
            if before is None
            else self._decode_cursor(before, manifest["turn_count"])
        )
        start = max(0, end - limit)
        return {
            "conversation_id": MAIN_CONVERSATION_ID,
            "created_at": manifest["created_at"],
            "updated_at": manifest["updated_at"],
            "turns": self._slice(manifest, start, end),
            "has_older": start > 0,
            "before": self._encode_cursor(start) if start else None,
        }

    def append_turn(
        self,
        *,
        request_id: str,
        role: str,
        text: str,
        created_at: str,
        status: str | None = None,
        request_detail: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Append one turn using a constant-time operational request-id lookup."""
        _validate_id(request_id, "request_id")
        if (
            role not in {"user", "assistant"}
            or not isinstance(text, str)
            or not text.strip()
            or len(text.encode("utf-8")) > _MAX_TURN_TEXT_BYTES
        ):
            raise ConversationError("turn is invalid")
        if status is not None and (not isinstance(status, str) or len(status) > 80):
            raise ConversationError("turn is invalid")
        detail = _validate_request_detail(request_detail, request_id, role)
        self.load_or_create_main(now=created_at)
        existing = self._request_entry(request_id, role)
        if existing is not None:
            if existing["text"] != text or existing.get("request_detail") != detail:
                raise ConversationError("request ID is already bound to another turn")
            return self.load_main_page()

        manifest = self._manifest()
        chunks = manifest["chunks"]
        target = (
            self._chunk_path(chunks[-1]["name"])
            if chunks
            else self._chunk_path("000001.json")
        )
        chunk = (
            {"turns": []} if not chunks else self._read_chunk(target, chunks[-1]["count"])
        )
        if len(chunk["turns"]) >= _CHUNK_MAX_TURNS:
            target = self._chunk_path(f"{len(chunks) + 1:06d}.json")
            chunk = {"turns": []}
        turn: dict[str, Any] = {
            "request_id": request_id,
            "role": role,
            "text": text,
            "created_at": _timestamp(created_at),
            "status": status,
        }
        if detail is not None:
            turn["request_detail"] = detail
        chunk["turns"].append(turn)
        self._write(target, chunk)
        self._write_request_entry(request_id, role, text, detail)
        if chunks and target.name == chunks[-1]["name"]:
            chunks[-1]["count"] += 1
        else:
            chunks.append({"name": target.name, "count": 1})
        manifest["turn_count"] += 1
        manifest["updated_at"] = _timestamp(created_at)
        self._write(self._main_directory() / "manifest.json", manifest)
        return self.load_main_page()

    def recent_context(
        self,
        *,
        exclude_request_id: str | None = None,
        max_turns: int = _RECENT_CONTEXT_MAX_TURNS,
        max_bytes: int = _RECENT_CONTEXT_MAX_BYTES,
    ) -> list[dict[str, str]]:
        """Return only complete newest role/text turns within explicit planner bounds."""
        if (
            not isinstance(max_turns, int)
            or not isinstance(max_bytes, int)
            or max_turns <= 0
            or max_bytes <= 0
        ):
            raise ConversationError("recent context bounds are invalid")
        if exclude_request_id is not None:
            _validate_id(exclude_request_id, "request_id")
        selected: list[dict[str, str]] = []
        size = 0
        for entry in reversed(self._manifest()["chunks"]):
            chunk = self._read_chunk(self._chunk_path(entry["name"]), entry["count"])
            for turn in reversed(chunk["turns"]):
                if turn["request_id"] == exclude_request_id:
                    continue
                item = {"role": turn["role"], "text": turn["text"]}
                cost = len(
                    json.dumps(item, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                )
                if len(selected) >= max_turns or size + cost > max_bytes:
                    return list(reversed(selected))
                selected.append(item)
                size += cost
            if len(selected) >= max_turns:
                break
        return list(reversed(selected))

    def _migrate_legacy_main(self) -> None:
        """Atomically stage legacy `main.json` conversion while preserving the source file."""
        staging = self._main_directory().with_name(".main.migrating")
        if staging.exists():
            if self._stage_is_complete(staging):
                os.replace(staging, self._main_directory())
                return
            shutil.rmtree(staging)
        legacy = self._read_json(self._legacy_main_path())
        if (
            not isinstance(legacy.get("actor_id"), str)
            or legacy.get("conversation_id") != MAIN_CONVERSATION_ID
            or not isinstance(legacy.get("turns"), list)
        ):
            raise ConversationError("legacy conversation is invalid")
        _timestamp(legacy.get("created_at"))
        for turn in legacy["turns"]:
            _validate_turn(turn)
        chunks: list[dict[str, Any]] = []
        for index in range(0, len(legacy["turns"]), _CHUNK_MAX_TURNS):
            name = f"{index // _CHUNK_MAX_TURNS + 1:06d}.json"
            turns = legacy["turns"][index : index + _CHUNK_MAX_TURNS]
            self._write(staging / "chunks" / name, {"turns": turns})
            chunks.append({"name": name, "count": len(turns)})
        for turn in legacy["turns"]:
            self._write_request_entry(
                turn["request_id"],
                turn["role"],
                turn["text"],
                turn.get("request_detail"),
                root=staging,
            )
        self._write(
            staging / "manifest.json",
            {
                "conversation_id": MAIN_CONVERSATION_ID,
                "created_at": legacy["created_at"],
                "updated_at": legacy.get("updated_at", legacy["created_at"]),
                "turn_count": len(legacy["turns"]),
                "chunks": chunks,
            },
        )
        os.replace(staging, self._main_directory())

    def _stage_is_complete(self, staging: Path) -> bool:
        """Determine whether an interrupted migration stage can be published safely."""
        try:
            manifest = self._manifest(root=staging)
            return all(
                self._request_entry(turn["request_id"], turn["role"], root=staging) is not None
                for entry in manifest["chunks"]
                for turn in self._read_chunk(
                    staging / "chunks" / entry["name"], entry["count"]
                )["turns"]
            )
        except ConversationError:
            return False

    def _manifest(self, *, root: Path | None = None) -> dict[str, Any]:
        root = root or self._main_directory()
        manifest = self._read_json(root / "manifest.json")
        if (
            not isinstance(manifest, dict)
            or set(manifest)
            != {"conversation_id", "created_at", "updated_at", "turn_count", "chunks"}
            or manifest.get("conversation_id") != MAIN_CONVERSATION_ID
            or not isinstance(manifest.get("turn_count"), int)
            or manifest["turn_count"] < 0
            or not isinstance(manifest.get("chunks"), list)
        ):
            raise ConversationError("conversation manifest is invalid")
        _timestamp(manifest["created_at"])
        _timestamp(manifest["updated_at"])
        total = 0
        for position, entry in enumerate(manifest["chunks"], start=1):
            if (
                not isinstance(entry, dict)
                or set(entry) != {"name", "count"}
                or entry.get("name") != f"{position:06d}.json"
                or not isinstance(entry.get("count"), int)
                or not 1 <= entry["count"] <= _CHUNK_MAX_TURNS
            ):
                raise ConversationError("conversation manifest is invalid")
            total += entry["count"]
        if total != manifest["turn_count"]:
            raise ConversationError("conversation manifest is invalid")
        return manifest

    def _slice(
        self, manifest: dict[str, Any], start: int, end: int
    ) -> list[dict[str, Any]]:
        """Load only chunks overlapping the requested chronological range."""
        turns: list[dict[str, Any]] = []
        offset = 0
        for entry in manifest["chunks"]:
            next_offset = offset + entry["count"]
            if next_offset > start and offset < end:
                chunk = self._read_chunk(
                    self._chunk_path(entry["name"]), entry["count"]
                )["turns"]
                turns.extend(chunk[max(0, start - offset) : min(entry["count"], end - offset)])
            offset = next_offset
        if len(turns) != end - start:
            raise ConversationError("conversation manifest is invalid")
        return turns

    def _read_chunk(self, path: Path, expected_count: int) -> dict[str, Any]:
        chunk = self._read_json(path)
        if (
            set(chunk) != {"turns"}
            or not isinstance(chunk["turns"], list)
            or len(chunk["turns"]) != expected_count
            or len(chunk["turns"]) > _CHUNK_MAX_TURNS
        ):
            raise ConversationError("conversation chunk is invalid")
        for turn in chunk["turns"]:
            _validate_turn(turn)
        return chunk

    def _request_entry(
        self, request_id: str, role: str, *, root: Path | None = None
    ) -> dict[str, Any] | None:
        path = self._request_path(request_id, role, root=root)
        if not path.exists():
            return None
        entry = self._read_json(path)
        if (
            set(entry) != {"request_id", "role", "text", "request_detail"}
            or entry.get("request_id") != request_id
            or entry.get("role") != role
            or not isinstance(entry.get("text"), str)
        ):
            raise ConversationError("conversation request index is invalid")
        _validate_request_detail(entry["request_detail"], request_id, role)
        return entry

    def _write_request_entry(
        self,
        request_id: str,
        role: str,
        text: str,
        detail: dict[str, Any] | None,
        *,
        root: Path | None = None,
    ) -> None:
        self._write(
            self._request_path(request_id, role, root=root),
            {
                "request_id": request_id,
                "role": role,
                "text": text,
                "request_detail": detail,
            },
        )

    def _encode_cursor(self, offset: int) -> str:
        raw = str(offset).encode("ascii")
        signature = hmac.digest(self._cursor_key, raw, "sha256")[:16]
        return base64.urlsafe_b64encode(raw + signature).decode("ascii").rstrip("=")

    def _decode_cursor(self, value: str, total: int) -> int:
        if not isinstance(value, str) or len(value) > 128:
            raise ConversationError("conversation cursor is invalid")
        try:
            decoded = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
            raw, signature = decoded[:-16], decoded[-16:]
            offset = int(raw.decode("ascii"))
        except (UnicodeDecodeError, ValueError) as error:
            raise ConversationError("conversation cursor is invalid") from error
        if not hmac.compare_digest(
            signature, hmac.digest(self._cursor_key, raw, "sha256")[:16]
        ) or not 0 <= offset <= total:
            raise ConversationError("conversation cursor is invalid")
        return offset

    def _main_directory(self) -> Path:
        return self._root / MAIN_CONVERSATION_ID

    def _legacy_main_path(self) -> Path:
        return self._root / "main.json"

    def _chunk_path(self, name: str) -> Path:
        if re.fullmatch(r"[0-9]{6}\.json", name) is None:
            raise ConversationError("conversation manifest is invalid")
        return self._main_directory() / "chunks" / name

    def _request_path(self, request_id: str, role: str, *, root: Path | None = None) -> Path:
        digest = hashlib.sha256(f"{request_id}:{role}".encode("utf-8")).hexdigest()
        return (root or self._main_directory()) / "requests" / f"{digest}.json"

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ConversationError("conversation is unavailable") from error
        if not isinstance(value, dict):
            raise ConversationError("conversation is unavailable")
        return value

    @staticmethod
    def _write(path: Path, record: dict[str, Any]) -> None:
        encoded = json.dumps(record, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
        if len(encoded) > _MAX_RECORD_BYTES:
            raise ConversationError("conversation record is too large")
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
