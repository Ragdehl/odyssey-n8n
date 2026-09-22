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


def test_append_idempotency_and_context_bounds_fail_closed(tmp_path: Path) -> None:
    """The operational request index avoids rescans and invalid planner bounds cannot widen reads."""
    store = _store(tmp_path)
    _append(store, 1)
    _append(store, 1)
    assert len(store.load_main_page()["turns"]) == 1
    with pytest.raises(ConversationError, match="already bound"):
        store.append_turn(
            request_id="req-1",
            role="assistant",
            text="different",
            created_at=NOW,
        )
    with pytest.raises(ConversationError, match="bounds"):
        store.recent_context(max_turns=0)
    with pytest.raises(ConversationError, match="bounds"):
        store.recent_context(max_bytes=0)


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


def test_completed_migration_stage_is_published_without_rewriting_it(tmp_path: Path) -> None:
    """A fully indexed staged migration is safe to publish after an interruption."""
    store = _store(tmp_path)
    root = store._root
    stage = root / ".main.migrating"
    turn = {
        "request_id": "req-staged",
        "role": "assistant",
        "text": "staged reply",
        "created_at": NOW,
        "status": "completed",
    }
    store._write(stage / "chunks" / "000001.json", {"turns": [turn]})
    store._write_request_entry("req-staged", "assistant", "staged reply", None, root=stage)
    store._write(
        stage / "manifest.json",
        {
            "conversation_id": "main",
            "created_at": NOW,
            "updated_at": NOW,
            "turn_count": 1,
            "chunks": [{"name": "000001.json", "count": 1}],
        },
    )
    (root / "main.json").write_text(
        json.dumps(
            {
                "conversation_id": "main",
                "actor_id": "actor-a",
                "created_at": NOW,
                "updated_at": NOW,
                "turns": [turn],
            }
        ),
        encoding="utf-8",
    )

    assert store.load_or_create_main(now=NOW)["turns"] == [turn]
    assert (root / "main").exists()
    assert not stage.exists()


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


def test_request_detail_preserves_only_bounded_operational_summary(tmp_path: Path) -> None:
    """The inspector-safe allowlist retains bounded provider, change, and cost evidence."""
    store = _store(tmp_path)
    detail = {
        "request_id": "req-9",
        "operational": {
            "total_duration_ms": 12.5,
            "stages": [
                {
                    "name": "planner",
                    "outcome": "completed",
                    "duration_ms": 4,
                    "model": "gpt-5-mini",
                    "reasoning_effort": "low",
                    "usage": {"input_tokens": 10, "output_tokens": 2},
                    "provider_calls": [
                        {
                            "name": "planner-model",
                            "outcome": "completed",
                            "usage": {"input_tokens": 10, "output_tokens": 2},
                        }
                    ],
                }
            ],
        },
        "changes": {
            "affected_stable_note_ids": ["note-1"],
            "units": [{"stable_note_id": "note-1", "operation": "update", "status": "done"}],
        },
        "estimated_cost": {
            "status": "estimated",
            "amount_usd": 0.01,
            "pricing_basis": "2026-09-16",
        },
    }
    _append(store, 9, detail=detail)
    assert store.load_main_page()["turns"][0]["request_detail"] == detail
    with pytest.raises(ConversationError, match="request detail"):
        _append(
            store,
            11,
            detail={
                **detail,
                "request_id": "req-11",
                "operational": {"total_duration_ms": float("inf"), "stages": []},
            },
        )


@pytest.mark.parametrize(
    "detail",
    [
        {"operational": {"total_duration_ms": 1, "stages": [{"name": "x" * 81, "outcome": "ok"}]}},
        {
            "operational": {
                "total_duration_ms": 1,
                "stages": [{"name": "x", "outcome": "ok", "model": "x" * 121}],
            }
        },
        {
            "operational": {
                "total_duration_ms": 1,
                "stages": [{"name": "x", "outcome": "ok", "duration_ms": True}],
            }
        },
        {
            "operational": {
                "total_duration_ms": 1,
                "stages": [{"name": "x", "outcome": "ok", "usage": {"input_tokens": True}}],
            }
        },
        {
            "operational": {"total_duration_ms": 1, "stages": []},
            "changes": {"affected_stable_note_ids": ["x" * 129], "units": []},
        },
        {
            "operational": {"total_duration_ms": 1, "stages": []},
            "changes": {
                "affected_stable_note_ids": [],
                "units": [{"stable_note_id": "note-1", "status": 1}],
            },
        },
    ],
)
def test_request_detail_rejects_unbounded_nested_fields(tmp_path: Path, detail: dict) -> None:
    """Nested inspector data rejects oversized, non-numeric, and non-operational values."""
    store = _store(tmp_path)
    with pytest.raises(ConversationError, match="request detail"):
        store.append_turn(
            request_id="req-invalid",
            role="assistant",
            text="reply",
            created_at=NOW,
            request_detail={"request_id": "req-invalid", **detail},
        )


def test_assistant_snapshot_is_durable_idempotent_and_excluded_from_recent_context(
    tmp_path: Path,
) -> None:
    """Persist result membership beside visible text without entering planner continuity."""
    store = _store(tmp_path)
    snapshot = {
        "version": 1,
        "query": "people",
        "filters": [],
        "sort": "relevance",
        "ranking_version": "ui2-feed-v1",
        "executed_at": NOW,
        "note_ids": ["person-1"],
        "total": 1,
        "truncated": False,
    }
    kwargs = {
        "request_id": "snapshot-1",
        "role": "assistant",
        "text": "Found notes.",
        "created_at": NOW,
        "note_result_snapshot": snapshot,
    }
    store.append_turn(**kwargs)
    store.append_turn(**kwargs)
    assert store.load_main_page()["turns"][0]["note_result_snapshot"] == snapshot
    assert store.recent_context() == [{"role": "assistant", "text": "Found notes."}]


def test_affected_note_snapshot_is_durable_and_excluded_from_recent_context(tmp_path: Path) -> None:
    """Preserve mutation membership across reload without leaking it into planner continuity."""
    store = _store(tmp_path)
    snapshot = {
        "version": 2,
        "kind": "affected_notes",
        "executed_at": NOW,
        "note_ids": ["first", "second"],
        "total": 2,
        "truncated": False,
    }
    store.append_turn(
        request_id="affected-1",
        role="assistant",
        text="La información se ha guardado.",
        created_at=NOW,
        note_result_snapshot=snapshot,
    )

    assert store.load_main_page()["turns"][0]["note_result_snapshot"] == snapshot
    assert store.recent_context() == [
        {"role": "assistant", "text": "La información se ha guardado."}
    ]
