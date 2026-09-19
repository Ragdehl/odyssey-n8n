"""Tests for bounded body-free historical Notes result snapshots."""

from __future__ import annotations

import pytest

from odyssey_core.note_result_snapshots import (
    NoteResultSnapshotError,
    validate_note_result_snapshot,
)


def payload(**changes):
    """Build one valid v1 snapshot fixture."""
    value = {
        "version": 1,
        "query": "people in Toulouse",
        "filters": [{"field": "tags", "op": "contains", "value": "travel"}],
        "sort": "relevance",
        "ranking_version": "ui2-feed-v1",
        "executed_at": "2026-09-19T10:00:00Z",
        "note_ids": ["a", "b"],
        "total": 2,
        "truncated": False,
    }
    return value | changes


def test_snapshot_round_trip_preserves_only_bounded_membership_metadata():
    """Serialize stable IDs/order without note bodies, paths, or provider material."""
    snapshot = validate_note_result_snapshot(payload())
    assert snapshot and snapshot.note_ids == ("a", "b")
    assert validate_note_result_snapshot(snapshot.to_payload()) == snapshot
    assert "body" not in snapshot.to_payload()


@pytest.mark.parametrize(
    "changes",
    [
        {"query": "x" * 513},
        {"filters": [{}] * 17},
        {"note_ids": [str(i) for i in range(65)], "total": 65, "truncated": True},
        {"note_ids": ["a", "a"], "total": 2},
        {"truncated": True},
        {"unexpected": "x"},
    ],
)
def test_snapshot_bounds_and_malformed_payloads_fail_closed(changes):
    """Reject malformed, oversized, duplicate, or inconsistent durable snapshots."""
    with pytest.raises(NoteResultSnapshotError):
        validate_note_result_snapshot(payload(**changes))


def test_snapshot_truncation_is_explicit_and_consistent():
    """Require a historical prefix to disclose that not all matched members were saved."""
    snapshot = validate_note_result_snapshot(payload(total=3, truncated=True))
    assert snapshot and snapshot.truncated is True
