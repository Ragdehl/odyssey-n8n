"""Deterministic tests for actor-scoped durable conversation state."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import odyssey_core.conversations as conversations
from odyssey_core.conversations import ConversationError, ConversationRepository


def test_conversation_round_trip_is_actor_scoped_and_idempotent(tmp_path: Path) -> None:
    repository = ConversationRepository(tmp_path / "state")
    created = repository.create(
        "user@example", now="2026-09-16T10:00:00+02:00", conversation_id="conv-1"
    )
    repository.append_turn(
        "user@example",
        "conv-1",
        request_id="req-1",
        role="user",
        text="Hola",
        created_at="2026-09-16T10:00:01+02:00",
    )
    repository.append_turn(
        "user@example",
        "conv-1",
        request_id="req-1",
        role="user",
        text="Hola",
        created_at="2026-09-16T10:00:01+02:00",
    )

    loaded = repository.load("user@example", "conv-1")
    assert loaded["conversation_id"] == created["conversation_id"]
    assert len(loaded["turns"]) == 1
    assert repository.list("user@example")[0].turn_count == 1
    with pytest.raises(ConversationError):
        repository.load("other@example", "conv-1")


def test_recent_context_is_bounded_and_keeps_recent_order(tmp_path: Path) -> None:
    repository = ConversationRepository(tmp_path / "state")
    repository.create("actor", now="2026-09-16T10:00:00+00:00", conversation_id="conv-1")
    for index in range(4):
        repository.append_turn(
            "actor",
            "conv-1",
            request_id=f"req-{index}",
            role="user",
            text=f"mensaje {index}",
            created_at=f"2026-09-16T10:00:0{index + 1}+00:00",
        )
    assert repository.recent_context("actor", "conv-1", max_turns=2) == [
        {"role": "user", "text": "mensaje 2"},
        {"role": "user", "text": "mensaje 3"},
    ]


def test_conversation_rejects_path_like_identifiers(tmp_path: Path) -> None:
    repository = ConversationRepository(tmp_path / "state")
    with pytest.raises(ConversationError):
        repository.create("actor", now="2026-09-16T10:00:00+00:00", conversation_id="../escape")


def test_conversation_rejects_duplicate_and_conflicting_idempotent_turns(tmp_path: Path) -> None:
    repository = ConversationRepository(tmp_path / "state")
    repository.create("actor", now="2026-09-16T10:00:00Z", conversation_id="conv-1")

    with pytest.raises(ConversationError, match="already exists"):
        repository.create("actor", now="2026-09-16T10:00:00Z", conversation_id="conv-1")

    repository.append_turn(
        "actor",
        "conv-1",
        request_id="req-1",
        role="user",
        text="Primero",
        created_at="2026-09-16T10:00:01Z",
    )
    with pytest.raises(ConversationError, match="already bound"):
        repository.append_turn(
            "actor",
            "conv-1",
            request_id="req-1",
            role="user",
            text="Distinto",
            created_at="2026-09-16T10:00:02Z",
        )

    record = repository.append_turn(
        "actor",
        "conv-1",
        request_id="req-1",
        role="assistant",
        text="Respuesta",
        created_at="2026-09-16T10:00:03Z",
        status="completed",
    )
    assert [turn["role"] for turn in record["turns"]] == ["user", "assistant"]


@pytest.mark.parametrize("actor", ["", "   ", "x" * 257])
def test_conversation_rejects_invalid_actor_ids(tmp_path: Path, actor: str) -> None:
    repository = ConversationRepository(tmp_path / "state")
    with pytest.raises(ConversationError, match="actor is invalid"):
        repository.create(actor, now="2026-09-16T10:00:00Z", conversation_id="conv-1")


@pytest.mark.parametrize(
    ("request_id", "role", "text", "created_at"),
    [
        ("../req", "user", "Hola", "2026-09-16T10:00:01Z"),
        ("req-1", "system", "Hola", "2026-09-16T10:00:01Z"),
        ("req-1", "user", "   ", "2026-09-16T10:00:01Z"),
        ("req-1", "user", "Hola", "not-a-timestamp"),
    ],
)
def test_conversation_rejects_invalid_turn_fields(
    tmp_path: Path, request_id: str, role: str, text: str, created_at: str
) -> None:
    repository = ConversationRepository(tmp_path / "state")
    repository.create("actor", now="2026-09-16T10:00:00Z", conversation_id="conv-1")
    with pytest.raises(ConversationError):
        repository.append_turn(
            "actor",
            "conv-1",
            request_id=request_id,
            role=role,
            text=text,
            created_at=created_at,
        )


def test_conversation_load_and_list_fail_closed_on_corrupt_records(tmp_path: Path) -> None:
    repository = ConversationRepository(tmp_path / "state")
    repository.create("actor", now="2026-09-16T10:00:00Z", conversation_id="conv-1")
    path = repository._path("actor", "conv-1")
    path.write_text("{not-json", encoding="utf-8")

    with pytest.raises(ConversationError, match="unavailable"):
        repository.load("actor", "conv-1")
    assert repository.list("actor") == []


def test_conversation_rejects_cross_actor_and_malformed_records(tmp_path: Path) -> None:
    repository = ConversationRepository(tmp_path / "state")
    repository.create("actor", now="2026-09-16T10:00:00Z", conversation_id="conv-1")
    path = repository._path("actor", "conv-1")

    path.write_text(
        json.dumps(
            {
                "conversation_id": "conv-1",
                "actor_id": "someone-else",
                "created_at": "2026-09-16T10:00:00+00:00",
                "updated_at": "2026-09-16T10:00:00+00:00",
                "turns": [],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ConversationError, match="ownership"):
        repository.load("actor", "conv-1")

    path.write_text(
        json.dumps(
            {
                "conversation_id": "conv-1",
                "actor_id": "actor",
                "created_at": "2026-09-16T10:00:00+00:00",
                "updated_at": "2026-09-16T10:00:00+00:00",
                "turns": [{"unexpected": "shape"}],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ConversationError, match="turn is invalid"):
        repository.load("actor", "conv-1")


def test_conversation_list_handles_empty_actor_and_bounded_title(tmp_path: Path) -> None:
    repository = ConversationRepository(tmp_path / "state")
    assert repository.list("missing-actor") == []

    repository.create("actor", now="2026-09-16T10:00:00", conversation_id="conv-empty")
    assert repository.list("actor")[0].title == "Nueva conversación"

    repository.create("actor", now="2026-09-16T10:00:01Z", conversation_id="conv-title")
    repository.append_turn(
        "actor",
        "conv-title",
        request_id="req-title",
        role="user",
        text="  " + "palabra " * 20 + "  ",
        created_at="2026-09-16T10:00:02Z",
    )
    summary = repository.list("actor")[0]
    assert summary.conversation_id == "conv-title"
    assert summary.title.endswith("…")
    assert len(summary.title) == 81


def test_recent_context_respects_byte_budget_and_excludes_current_turn(tmp_path: Path) -> None:
    repository = ConversationRepository(tmp_path / "state")
    repository.create("actor", now="2026-09-16T10:00:00Z", conversation_id="conv-1")
    repository.append_turn(
        "actor",
        "conv-1",
        request_id="req-1",
        role="user",
        text="mensaje demasiado largo para este presupuesto",
        created_at="2026-09-16T10:00:01Z",
    )
    assert repository.recent_context("actor", "conv-1", max_turns=8, max_bytes=1) == []
    repository.append_turn(
        "actor",
        "conv-1",
        request_id="req-2",
        role="user",
        text="¿Y dónde vive?",
        created_at="2026-09-16T10:00:02Z",
    )
    assert repository.recent_context("actor", "conv-1", exclude_request_id="req-2") == [
        {"role": "user", "text": "mensaje demasiado largo para este presupuesto"}
    ]


def test_main_conversation_is_stable_per_actor(tmp_path: Path) -> None:
    """One actor reopens the same durable main conversation without a chat-list decision."""
    repository = ConversationRepository(tmp_path / "state")
    first = repository.load_or_create_main("actor", now="2026-09-16T10:00:00Z")
    second = repository.load_or_create_main("actor", now="2026-09-16T10:01:00Z")
    assert first["conversation_id"] == "main"
    assert second["conversation_id"] == "main"


def test_conversation_turn_and_record_size_limits_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = ConversationRepository(tmp_path / "state")
    repository.create("actor", now="2026-09-16T10:00:00Z", conversation_id="conv-turns")
    monkeypatch.setattr(conversations, "_MAX_TURNS", 1)
    repository.append_turn(
        "actor",
        "conv-turns",
        request_id="req-1",
        role="user",
        text="uno",
        created_at="2026-09-16T10:00:01Z",
    )
    with pytest.raises(ConversationError, match="turn limit"):
        repository.append_turn(
            "actor",
            "conv-turns",
            request_id="req-2",
            role="user",
            text="dos",
            created_at="2026-09-16T10:00:02Z",
        )

    monkeypatch.setattr(conversations, "_MAX_TURNS", 200)
    repository.create("actor", now="2026-09-16T10:01:00Z", conversation_id="conv-size")
    monkeypatch.setattr(conversations, "_MAX_RECORD_BYTES", 64)
    with pytest.raises(ConversationError, match="too large"):
        repository.append_turn(
            "actor",
            "conv-size",
            request_id="req-size",
            role="user",
            text="x" * 200,
            created_at="2026-09-16T10:01:01Z",
        )
    assert repository.load("actor", "conv-size")["turns"] == []


def test_conversation_normalizes_naive_timestamp_to_utc(tmp_path: Path) -> None:
    repository = ConversationRepository(tmp_path / "state")
    created = repository.create("actor", now="2026-09-16T10:00:00", conversation_id="conv-1")
    assert created["created_at"] == "2026-09-16T10:00:00+00:00"
