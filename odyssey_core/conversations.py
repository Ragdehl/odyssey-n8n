"""Durable actor-scoped conversation records outside canonical personal knowledge."""

from __future__ import annotations

import hashlib
import json
import math
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
_PAGE_DEFAULT_TURNS = 40
_PAGE_MAX_TURNS = 50
_CHUNK_MAX_TURNS = 50
_MAX_DETAIL_BYTES = 16 * 1024
MAIN_CONVERSATION_ID = "main"
_RECENT_CONTEXT_MAX_BYTES = 4096
_RECENT_CONTEXT_MAX_TURNS = 16


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

    def load_or_create_main(self, actor_id: str, *, now: str) -> dict[str, Any]:
        """Return the actor's durable main conversation, creating it once when absent."""
        actor = _validate_actor(actor_id)
        directory = self._main_directory(actor)
        if directory.exists():
            return self.load_main_page(actor, limit=_PAGE_DEFAULT_TURNS)
        target = self._path(actor, MAIN_CONVERSATION_ID)
        if target.exists():
            self._migrate_main(actor)
            return self.load_main_page(actor, limit=_PAGE_DEFAULT_TURNS)
        directory.mkdir(parents=True)
        self._write(
            directory / "manifest.json",
            {
                "conversation_id": MAIN_CONVERSATION_ID,
                "actor_id": actor,
                "created_at": _timestamp(now),
                "turn_count": 0,
                "chunks": [],
                "request_index": {},
            },
        )
        return self.load_main_page(actor, limit=_PAGE_DEFAULT_TURNS)

    def load_main_page(
        self, actor_id: str, *, limit: int = _PAGE_DEFAULT_TURNS, before: str | None = None
    ) -> dict[str, Any]:
        """Return one chronological presentation page without loading a full transcript."""
        actor = _validate_actor(actor_id)
        if not isinstance(limit, int) or not 1 <= limit <= _PAGE_MAX_TURNS:
            raise ConversationError("conversation page limit is invalid")
        self.load_or_create_main(
            actor, now=datetime.now(UTC).isoformat()
        ) if not self._main_directory(actor).exists() else None
        manifest = self._main_manifest(actor)
        end = (
            manifest["turn_count"]
            if before is None
            else _decode_cursor(before, actor, manifest["turn_count"])
        )
        start = max(0, end - limit)
        page = self._main_slice(actor, manifest, start, end)
        return {
            "conversation_id": MAIN_CONVERSATION_ID,
            "turns": page,
            "has_older": start > 0,
            "before": _encode_cursor(actor, start) if start else None,
        }

    def load(self, actor_id: str, conversation_id: str) -> dict[str, Any]:
        """Load one validated actor-owned conversation without exposing internal actor data."""
        actor = _validate_actor(actor_id)
        if conversation_id == MAIN_CONVERSATION_ID and self._main_directory(actor).exists():
            return self.load_main_page(actor)
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
        request_detail: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Append one visible turn idempotently by request ID and role."""
        actor = _validate_actor(actor_id)
        _validate_id(request_id, "request_id")
        if role not in {"user", "assistant"} or not isinstance(text, str) or not text.strip():
            raise ConversationError("turn is invalid")
        if conversation_id == MAIN_CONVERSATION_ID:
            return self._append_main(
                actor,
                request_id=request_id,
                role=role,
                text=text,
                created_at=created_at,
                status=status,
                request_detail=request_detail,
            )
        if request_detail is not None:
            raise ConversationError("request detail is supported only for main assistant turns")
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

    def _append_main(
        self,
        actor: str,
        *,
        request_id: str,
        role: str,
        text: str,
        created_at: str,
        status: str | None,
        request_detail: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Append one main turn to its bounded tail chunk with lifetime idempotency."""
        self.load_or_create_main(actor, now=created_at)
        detail = _validate_request_detail(request_detail, request_id, role)
        manifest = self._main_manifest(actor)
        identity = f"{request_id}:{role}"
        existing = manifest["request_index"].get(identity)
        if existing is not None:
            if existing["text"] != text or existing.get("request_detail") != detail:
                raise ConversationError("request ID is already bound to another turn")
            return self.load_main_page(actor)
        turn = {
            "request_id": request_id,
            "role": role,
            "text": text,
            "created_at": _timestamp(created_at),
            "status": status,
        }
        if detail is not None:
            turn["request_detail"] = detail
        directory = self._main_directory(actor) / "chunks"
        chunks = manifest["chunks"]
        target = directory / (chunks[-1]["name"] if chunks else "000001.json")
        chunk = {"turns": []} if not chunks else self._read_chunk(target, chunks[-1]["count"])
        if len(chunk["turns"]) >= _CHUNK_MAX_TURNS:
            target = directory / f"{len(chunks) + 1:06d}.json"
            chunk = {"turns": []}
        chunk["turns"].append(turn)
        self._write(target, chunk)
        if chunks and target.name == chunks[-1]["name"]:
            chunks[-1]["count"] += 1
        else:
            chunks.append({"name": target.name, "count": 1})
        manifest["turn_count"] += 1
        manifest["request_index"][identity] = {"text": text, "request_detail": detail}
        self._write(self._main_directory(actor) / "manifest.json", manifest)
        return self.load_main_page(actor)

    def _main_directory(self, actor: str) -> Path:
        return self._actor_directory(actor) / MAIN_CONVERSATION_ID

    def _migrate_main(self, actor: str) -> None:
        """Copy a validated legacy main record into segmented state without deleting it."""
        legacy = self._read_internal(self._path(actor, MAIN_CONVERSATION_ID))
        _validate_record(legacy, actor, MAIN_CONVERSATION_ID)
        directory = self._main_directory(actor)
        staging = directory.with_name(f".{directory.name}.migrating")
        if staging.exists():
            raise ConversationError("conversation migration is incomplete")
        staging.mkdir(parents=True)
        chunks: list[dict[str, Any]] = []
        request_index: dict[str, Any] = {}
        for index in range(0, len(legacy["turns"]), _CHUNK_MAX_TURNS):
            name = f"{index // _CHUNK_MAX_TURNS + 1:06d}.json"
            self._write(
                staging / "chunks" / name,
                {"turns": legacy["turns"][index : index + _CHUNK_MAX_TURNS]},
            )
            chunks.append(
                {"name": name, "count": len(legacy["turns"][index : index + _CHUNK_MAX_TURNS])}
            )
        for turn in legacy["turns"]:
            request_index[f"{turn['request_id']}:{turn['role']}"] = {
                "text": turn["text"],
                "request_detail": turn.get("request_detail"),
            }
        self._write(
            staging / "manifest.json",
            {
                "conversation_id": MAIN_CONVERSATION_ID,
                "actor_id": actor,
                "created_at": legacy["created_at"],
                "turn_count": len(legacy["turns"]),
                "chunks": chunks,
                "request_index": request_index,
            },
        )
        os.replace(staging, directory)

    def _main_manifest(self, actor: str) -> dict[str, Any]:
        directory = self._main_directory(actor)
        manifest = self._read_internal(directory / "manifest.json")
        if (
            manifest.get("conversation_id") != MAIN_CONVERSATION_ID
            or manifest.get("actor_id") != actor
            or not isinstance(manifest.get("turn_count"), int)
            or not isinstance(manifest.get("chunks"), list)
            or not isinstance(manifest.get("request_index"), dict)
        ):
            raise ConversationError("conversation ownership is invalid")
        return manifest

    def _main_slice(
        self, actor: str, manifest: dict[str, Any], start: int, end: int
    ) -> list[dict[str, Any]]:
        """Read only chunks overlapping one requested chronological page."""
        turns: list[dict[str, Any]] = []
        offset = 0
        for entry in manifest["chunks"]:
            count = entry.get("count")
            name = entry.get("name")
            if (
                not isinstance(count, int)
                or not isinstance(name, str)
                or count < 1
                or not re.fullmatch(r"[0-9]{6}\\.json", name)
            ):
                raise ConversationError("conversation manifest is invalid")
            next_offset = offset + count
            if next_offset > start and offset < end:
                chunk = self._read_chunk(self._main_directory(actor) / "chunks" / name, count)[
                    "turns"
                ]
                turns.extend(chunk[max(0, start - offset) : min(count, end - offset)])
            offset = next_offset
        if offset != manifest["turn_count"] or len(turns) != end - start:
            raise ConversationError("conversation manifest is invalid")
        return turns

    def _read_chunk(self, path: Path, expected_count: int | None = None) -> dict[str, Any]:
        chunk = self._read_internal(path)
        if (
            set(chunk) != {"turns"}
            or not isinstance(chunk["turns"], list)
            or len(chunk["turns"]) > _CHUNK_MAX_TURNS
        ):
            raise ConversationError("conversation chunk is invalid")
        for turn in chunk["turns"]:
            _validate_turn(turn)
        if expected_count is not None and len(chunk["turns"]) != expected_count:
            raise ConversationError("conversation chunk is inconsistent")
        return chunk

    def recent_context(
        self,
        actor_id: str,
        conversation_id: str,
        *,
        exclude_request_id: str | None = None,
        max_turns: int = _RECENT_CONTEXT_MAX_TURNS,
        max_bytes: int = _RECENT_CONTEXT_MAX_BYTES,
    ) -> list[dict[str, str]]:
        """Return complete recent visible turns for one planner call without current-turn duplication."""
        if max_turns <= 0 or max_bytes <= 0:
            raise ConversationError("recent context bounds are invalid")
        if exclude_request_id is not None:
            _validate_id(exclude_request_id, "request_id")
        record = (
            self.load_main_page(actor_id, limit=_PAGE_MAX_TURNS)
            if conversation_id == MAIN_CONVERSATION_ID
            else self.load(actor_id, conversation_id)
        )
        selected: list[dict[str, str]] = []
        size = 0
        source = record["turns"]
        if conversation_id == MAIN_CONVERSATION_ID:
            manifest = self._main_manifest(_validate_actor(actor_id))
            source = []
            for entry in reversed(manifest["chunks"]):
                source = (
                    self._read_chunk(
                        self._main_directory(_validate_actor(actor_id)) / "chunks" / entry["name"],
                        entry["count"],
                    )["turns"]
                    + source
                )
                # A tail chunk is enough once the bounded selector fills.
                if len(source) >= max_turns:
                    break
        for turn in reversed(source):
            if turn["request_id"] == exclude_request_id:
                continue
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
        _validate_turn(turn)


def _validate_turn(turn: Any) -> None:
    allowed = {"request_id", "role", "text", "created_at", "status", "request_detail"}
    if (
        not isinstance(turn, dict)
        or not set(turn) <= allowed
        or not {"request_id", "role", "text", "created_at", "status"} <= set(turn)
    ):
        raise ConversationError("conversation turn is invalid")
    _validate_id(turn["request_id"], "request_id")
    if turn["role"] not in {"user", "assistant"} or not isinstance(turn["text"], str):
        raise ConversationError("conversation turn is invalid")
    _timestamp(turn["created_at"])
    _validate_request_detail(turn.get("request_detail"), turn["request_id"], turn["role"])


def _validate_request_detail(value: Any, request_id: str, role: str) -> dict[str, Any] | None:
    if value is None:
        return None
    if role != "assistant" or not isinstance(value, dict) or value.get("request_id") != request_id:
        raise ConversationError("request detail is invalid")
    try:
        encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise ConversationError("request detail is invalid") from error
    if len(encoded) > _MAX_DETAIL_BYTES or set(value) - {
        "request_id",
        "operational",
        "changes",
        "estimated_cost",
    }:
        raise ConversationError("request detail is invalid")
    operational = value.get("operational")
    if (
        not isinstance(operational, dict)
        or set(operational) - {"total_duration_ms", "stages"}
        or not isinstance(operational.get("stages"), list)
        or len(operational["stages"]) > 16
    ):
        raise ConversationError("request detail is invalid")
    if operational.get("total_duration_ms") is not None and not _safe_number(
        operational.get("total_duration_ms")
    ):
        raise ConversationError("request detail is invalid")
    for stage in operational["stages"]:
        _validate_detail_stage(stage, allow_calls=True)
    if "changes" in value:
        _validate_detail_changes(value["changes"])
    if "estimated_cost" in value:
        _validate_estimated_cost(value["estimated_cost"])
    return json.loads(encoded)


def _safe_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value >= 0
    )


def _validate_detail_stage(value: Any, *, allow_calls: bool) -> None:
    allowed = {
        "name",
        "outcome",
        "duration_ms",
        "model",
        "reasoning_effort",
        "error_category",
        "usage",
        "provider_calls",
    }
    if (
        not isinstance(value, dict)
        or set(value) - allowed
        or not isinstance(value.get("name"), str)
        or not isinstance(value.get("outcome"), str)
        or len(value["name"]) > 80
        or len(value["outcome"]) > 80
    ):
        raise ConversationError("request detail is invalid")
    for key in ("model", "reasoning_effort", "error_category"):
        if value.get(key) is not None and (
            not isinstance(value[key], str) or len(value[key]) > 120
        ):
            raise ConversationError("request detail is invalid")
    if value.get("duration_ms") is not None and not _safe_number(value["duration_ms"]):
        raise ConversationError("request detail is invalid")
    if value.get("usage") is not None:
        usage = value["usage"]
        if (
            not isinstance(usage, dict)
            or set(usage)
            - {
                "input_tokens",
                "cached_input_tokens",
                "cache_write_tokens",
                "output_tokens",
                "reasoning_tokens",
            }
            or any(
                not isinstance(number, int) or isinstance(number, bool) or number < 0
                for number in usage.values()
            )
        ):
            raise ConversationError("request detail is invalid")
    calls = value.get("provider_calls", [])
    if not isinstance(calls, list) or len(calls) > 16 or (not allow_calls and calls):
        raise ConversationError("request detail is invalid")
    for call in calls:
        _validate_detail_stage(call, allow_calls=False)


def _validate_detail_changes(value: Any) -> None:
    if (
        not isinstance(value, dict)
        or set(value) - {"affected_stable_note_ids", "units"}
        or not isinstance(value.get("affected_stable_note_ids"), list)
        or not isinstance(value.get("units"), list)
        or len(value["affected_stable_note_ids"]) > 64
        or len(value["units"]) > 64
    ):
        raise ConversationError("request detail is invalid")
    if any(
        not isinstance(item, str) or len(item) > 128 for item in value["affected_stable_note_ids"]
    ):
        raise ConversationError("request detail is invalid")
    for unit in value["units"]:
        if (
            not isinstance(unit, dict)
            or set(unit) - {"stable_note_id", "operation", "status"}
            or not isinstance(unit.get("status"), str)
            or len(unit["status"]) > 80
            or (
                unit.get("stable_note_id") is not None
                and (
                    not isinstance(unit["stable_note_id"], str) or len(unit["stable_note_id"]) > 128
                )
            )
            or (
                unit.get("operation") is not None
                and (not isinstance(unit["operation"], str) or len(unit["operation"]) > 80)
            )
        ):
            raise ConversationError("request detail is invalid")


def _validate_estimated_cost(value: Any) -> None:
    if (
        not isinstance(value, dict)
        or set(value) - {"status", "amount_usd", "pricing_basis"}
        or value.get("status") not in {"estimated", "unavailable"}
        or not isinstance(value.get("pricing_basis"), str)
        or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value["pricing_basis"])
    ):
        raise ConversationError("request detail is invalid")
    if value["status"] == "estimated" and not _safe_number(value.get("amount_usd")):
        raise ConversationError("request detail is invalid")


def _encode_cursor(actor: str, offset: int) -> str:
    return (
        __import__("base64")
        .urlsafe_b64encode(
            json.dumps({"a": hashlib.sha256(actor.encode()).hexdigest(), "o": offset}).encode()
        )
        .decode()
        .rstrip("=")
    )


def _decode_cursor(value: str, actor: str, total: int) -> int:
    try:
        payload = json.loads(
            __import__("base64").urlsafe_b64decode(value + "=" * (-len(value) % 4))
        )
    except Exception as error:
        raise ConversationError("conversation cursor is invalid") from error
    if (
        not isinstance(payload, dict)
        or payload.get("a") != hashlib.sha256(actor.encode()).hexdigest()
        or not isinstance(payload.get("o"), int)
        or not 0 <= payload["o"] <= total
    ):
        raise ConversationError("conversation cursor is invalid")
    return payload["o"]


def _title(value: str) -> str:
    compact = " ".join(value.split())
    return compact[:80] + ("…" if len(compact) > 80 else "")
