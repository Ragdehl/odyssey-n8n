"""Deterministic tests for actor-scoped durable conversation state."""

from pathlib import Path

import pytest

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


def test_conversation_context_is_bounded_and_keeps_recent_order(tmp_path: Path) -> None:
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
    assert repository.context("actor", "conv-1", max_turns=2) == [
        {"role": "user", "text": "mensaje 2"},
        {"role": "user", "text": "mensaje 3"},
    ]


def test_conversation_rejects_path_like_identifiers(tmp_path: Path) -> None:
    repository = ConversationRepository(tmp_path / "state")
    with pytest.raises(ConversationError):
        repository.create("actor", now="2026-09-16T10:00:00+00:00", conversation_id="../escape")
