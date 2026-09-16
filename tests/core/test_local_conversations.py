"""Deterministic coverage for root-bound segmented UI-0 transcript state."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from odyssey_core.conversations import ConversationError
from odyssey_core.local_conversations import ConversationRootResolver, LocalConversationStore


NOW = "2026-09-16T10:00:00+00:00"


def _store(tmp_path: Path, actor: str = "actor-a") -> LocalConversationStore:
    resolver = ConversationRootResolver(tmp_path / "state")
    return LocalConversationStore(resolver.resolve(actor))


def _append(store: LocalConversationStore, index: int, *, detail: dict | None = None) -> None:
    store.append_turn(
        request_id=f"req-{index}",
        role="assistant" if index % 2 else "user",
        text=f"turn {index}",
        created_at=NOW,
        status="completed",
        request_detail=detail,
    )


def test_root_resolver_isolates_actors_while_store_has_no_actor_layout(tmp_path: Path) -> None:
    """The hosted resolver owns actor isolation and new store files contain no actor identity."""
    resolver = ConversationRootResolver(tmp_path / "state")
    first = LocalConversationStore(resolver.resolve("actor-a"))
    second = LocalConversationStore(resolver.resolve("actor-b"))
    assert resolver.resolve("actor-a") != resolver.resolve("actor-b")

    first.load_or_create_main(now=NOW)
    _append(first, 1)
    assert second.load_or_create_main(now=NOW)["turns"] == []

    stored = "\n".join(
        path.read_text(encoding="utf-8") for path in resolver.resolve("actor-a").rglob("*.json")
    )
    assert "actor-a" not in stored
    assert "actor_id" not in stored


def test_pages_context_and_append_read_only_required_chunks(tmp_path: Path, monkeypatch) -> None:
    """A 1,001-turn transcript remains complete without lifetime chunk deserialization."""
    store = _store(tmp_path)
    for index in range(1001):
        _append(store, index)

    reads: list[str] = []
    original = store._read_chunk

    def counted(path: Path, expected_count: int):
        reads.append(path.name)
        return original(path, expected_count)

    monkeypatch.setattr(store, "_read_chunk", counted)
    newest = store.load_main_page()
    assert [turn["text"] for turn in newest["turns"]] == [
        f"turn {index}" for index in range(961, 1001)
    ]
    assert newest["has_older"] is True
    assert len(set(reads)) == 2

    reads.clear()
    older = store.load_main_page(before=newest["before"])
    assert [turn["text"] for turn in older["turns"]] == [
        f"turn {index}" for index in range(921, 961)
    ]
    assert len(set(reads)) == 2

    reads.clear()
    context = store.recent_context()
    assert context == [
        {"role": "assistant" if index % 2 else "user", "text": f"turn {index}"}
        for index in range(985, 1001)
    ]
    assert len(set(reads)) == 2
    assert store.load_main_page(limit=50)["turns"][-1]["text"] == "turn 1000"


def test_page_contract_rejects_cross_root_or_malformed_cursor(tmp_path: Path) -> None:
    """Cursors are opaque, root-bound, and never expose filesystem names."""
    first = _store(tmp_path, "actor-a")
    second = _store(tmp_path, "actor-b")
    for index in range(41):
        _append(first, index)
    cursor = first.load_main_page()["before"]
    assert isinstance(cursor, str)
    assert "json" not in cursor and "/" not in cursor
    with pytest.raises(ConversationError, match="cursor"):
        second.load_or_create_main(now=NOW)
        second.load_main_page(before=cursor)
    with pytest.raises(ConversationError, match="cursor"):
        first.load_main_page(before="not-a-cursor")
    with pytest.raises(ConversationError, match="page limit"):
        first.load_main_page(limit=51)


def test_legacy_migration_preserves_safe_turns_and_recovers_incomplete_stage(
    tmp_path: Path,
) -> None:
    """Legacy actor-scoped input migrates once; an interrupted partial stage is safely retried."""
    store = _store(tmp_path)
    root = store._root
    root.mkdir(parents=True)
    legacy = {
        "conversation_id": "main",
        "actor_id": "actor-a",
        "created_at": NOW,
        "updated_at": NOW,
        "turns": [
            {
                "request_id": "req-1",
                "role": "user",
                "text": "Hola",
                "created_at": NOW,
                "status": None,
            },
            {
                "request_id": "req-1",
                "role": "assistant",
                "text": "Respuesta",
                "created_at": NOW,
                "status": "completed",
                "request_detail": {
                    "request_id": "req-1",
                    "operational": {"total_duration_ms": 1, "stages": []},
                },
            },
        ],
    }
    (root / "main.json").write_text(json.dumps(legacy), encoding="utf-8")
    (root / ".main.migrating" / "chunks").mkdir(parents=True)

    loaded = store.load_or_create_main(now=NOW)
    assert loaded["turns"] == legacy["turns"]
    assert (root / "main.json").exists()
    assert not (root / ".main.migrating").exists()
    assert store.load_or_create_main(now=NOW)["turns"] == legacy["turns"]


def test_request_detail_is_bounded_safe_and_excluded_from_context(tmp_path: Path) -> None:
    """Only allowlisted operational detail persists and it never enters planner context."""
    store = _store(tmp_path)
    detail = {
        "request_id": "req-1",
        "operational": {"total_duration_ms": 3, "stages": []},
        "changes": {"affected_stable_note_ids": ["note-1"], "units": []},
    }
    _append(store, 1, detail=detail)
    page = store.load_main_page()
    assert page["turns"][0]["request_detail"] == detail
    assert store.recent_context() == [{"role": "assistant", "text": "turn 1"}]
    with pytest.raises(ConversationError, match="request detail"):
        _append(store, 3, detail={**detail, "request_id": "req-3", "prompt": "secret"})
    with pytest.raises(ConversationError, match="request detail"):
        _append(
            store,
            5,
            detail={
                **detail,
                "request_id": "req-5",
                "operational": {
                    "total_duration_ms": 1,
                    "stages": [
                        {
                            "name": "x",
                            "outcome": "ok",
                            "provider_calls": [
                                {
                                    "name": "nested",
                                    "outcome": "ok",
                                    "provider_calls": [{"name": "raw", "outcome": "ok"}],
                                }
                            ],
                        }
                    ],
                },
            },
        )
    with pytest.raises(ConversationError, match="request detail"):
        _append(
            store,
            7,
            detail={"request_id": "wrong", "operational": {"total_duration_ms": 1, "stages": []}},
        )
