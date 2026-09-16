"""Durable actor-scoped conversation records outside canonical personal knowledge."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

_SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}\Z")
_MAX_RECORD_BYTES = 256 * 1024
_MAX_TURNS = 200


class ConversationError(ValueError):
    """Indicate invalid, unavailable, or cross-actor conversation state."""


@dataclass(frozen=True, slots=True)
class ConversationSummary:
    """Bounded list projection for one actor-owned conversation."""

    conversation_id: str
    title: str
    created_at: str
    updated_at: str
    turn_count: int


class ConversationRepository:
    """Persist visible conversation turns as validated JSON under durable state.

    Records are deliberately outside the vault and indexes. Actor ownership is checked on every
    read/write, and writes use a temporary file plus atomic replace so a partial record is never
    presented as a resumable conversation.
    """

    def __init__(self, root: Path) -> None:
        self._root = root / "conversations"
        self._root.mkdir(parents=True, exist_ok=True)

    def create(
        self, actor_id: str, *, now: str, conversation_id: str | None = None
    ) -> dict[str, Any]:
        """Create one empty actor-owned conversation and return its public record."""
        actor = _validate_actor(actor_id)
        identifier = conversation_id or f"conv-{uuid4()}"
        _validate_id(identifier, "conversation_id")
        target = self._path(actor, identifier)
        if target.exists():
            raise ConversationError("conversation already exists")
        record = {
            "conversation_id": identifier,
            "actor_id": actor,
            "created_at": _timestamp(now),
            "updated_at": _timestamp(now),
            "turns": [],
        }
        self._write(target, record)
        return self._public(record)

    def load(self, actor_id: str, conversation_id: str) -> dict[str, Any]:
        """Load one validated actor-owned conversation without exposing internal actor data."""
        actor = _validate_actor(actor_id)
        path = self._path(actor, conversation_id)
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as error:
            raise ConversationError("conversation not found") from error
        except (OSError, json.JSONDecodeError) as error:
            raise ConversationError("conversation is unavailable") from error
        _validate_record(record, actor, conversation_id)
        return self._public(record)

    def list(self, actor_id: str) -> list[ConversationSummary]:
        """Return deterministic summaries for only one validated actor."""
        actor = _validate_actor(actor_id)
        directory = self._actor_directory(actor)
        if not directory.exists():
            return []
        summaries = []
        for path in sorted(directory.glob("*.json")):
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
                _validate_record(record, actor, path.stem)
            except (OSError, json.JSONDecodeError, ConversationError):
                continue
            turns = record["turns"]
            first_user = next(
                (t["text"] for t in turns if t["role"] == "user"), "Nueva conversación"
            )
            summaries.append(
                ConversationSummary(
                    record["conversation_id"],
                    _title(first_user),
                    record["created_at"],
                    record["updated_at"],
                    len(turns),
                )
            )
        return sorted(summaries, key=lambda item: item.updated_at, reverse=True)

    def append_turn(
        self,
        actor_id: str,
        conversation_id: str,
        *,
        request_id: str,
        role: str,
        text: str,
        created_at: str,
        status: str | None = None,
    ) -> dict[str, Any]:
        """Append one visible turn idempotently by request ID and role."""
        actor = _validate_actor(actor_id)
        _validate_id(request_id, "request_id")
        if role not in {"user", "assistant"} or not isinstance(text, str) or not text.strip():
            raise ConversationError("turn is invalid")
        path = self._path(actor, conversation_id)
        record = self.load(actor, conversation_id)
        internal = self._read_internal(path)
        for turn in internal["turns"]:
            if turn["request_id"] == request_id and turn["role"] == role:
                if turn["text"] != text:
                    raise ConversationError("request ID is already bound to another turn")
                return record
        if len(internal["turns"]) >= _MAX_TURNS:
            raise ConversationError("conversation turn limit reached")
        internal["turns"].append(
            {
                "request_id": request_id,
                "role": role,
                "text": text,
                "created_at": _timestamp(created_at),
                "status": status,
            }
        )
        internal["updated_at"] = _timestamp(created_at)
        self._write(path, internal)
        return self._public(internal)

    def context(
        self, actor_id: str, conversation_id: str, *, max_turns: int = 8, max_bytes: int = 12000
    ) -> list[dict[str, str]]:
        """Return a bounded recent evidence slice for context-on-demand planning."""
        record = self.load(actor_id, conversation_id)
        selected: list[dict[str, str]] = []
        size = 0
        for turn in reversed(record["turns"]):
            item = {"role": turn["role"], "text": turn["text"]}
            cost = len(json.dumps(item, ensure_ascii=False).encode("utf-8"))
            if len(selected) >= max_turns or size + cost > max_bytes:
                break
            selected.append(item)
            size += cost
        return list(reversed(selected))

    def _actor_directory(self, actor: str) -> Path:
        return self._root / hashlib.sha256(actor.encode("utf-8")).hexdigest()

    def _path(self, actor: str, conversation_id: str) -> Path:
        _validate_id(conversation_id, "conversation_id")
        return self._actor_directory(actor) / f"{conversation_id}.json"

    def _read_internal(self, path: Path) -> dict[str, Any]:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ConversationError("conversation is unavailable") from error

    @staticmethod
    def _public(record: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in record.items() if key != "actor_id"}

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


def _validate_actor(actor: str) -> str:
    if not isinstance(actor, str) or not actor.strip() or len(actor) > 256:
        raise ConversationError("actor is invalid")
    return actor.strip()


def _validate_id(value: str, name: str) -> None:
    if not isinstance(value, str) or _SAFE_ID.fullmatch(value) is None:
        raise ConversationError(f"{name} is invalid")


def _timestamp(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as error:
        raise ConversationError("timestamp is invalid") from error
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.isoformat()


def _validate_record(record: Any, actor: str, conversation_id: str) -> None:
    if (
        not isinstance(record, dict)
        or record.get("actor_id") != actor
        or record.get("conversation_id") != conversation_id
    ):
        raise ConversationError("conversation ownership is invalid")
    if not isinstance(record.get("turns"), list) or len(record["turns"]) > _MAX_TURNS:
        raise ConversationError("conversation turns are invalid")
    for turn in record["turns"]:
        if not isinstance(turn, dict) or set(turn) != {
            "request_id",
            "role",
            "text",
            "created_at",
            "status",
        }:
            raise ConversationError("conversation turn is invalid")
        _validate_id(turn["request_id"], "request_id")
        if turn["role"] not in {"user", "assistant"} or not isinstance(turn["text"], str):
            raise ConversationError("conversation turn is invalid")
        _timestamp(turn["created_at"])


def _title(value: str) -> str:
    compact = " ".join(value.split())
    return compact[:80] + ("…" if len(compact) > 80 else "")
