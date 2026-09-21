"""Durable logical-delivery replay regression tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from odyssey_runtime.delivery_results import DeliveryResultError, LocalDeliveryResultStore


def _response(request_id: str = "web-delivery-1") -> dict[str, object]:
    """Return one bounded runtime response fixture without personal content."""
    return {
        "request_id": request_id,
        "status": "completed",
        "affected_stable_note_ids": ["note-1"],
        "actions": [],
    }


def test_completed_result_round_trips_without_persisting_request_text(tmp_path: Path) -> None:
    """Persist only a request hash and replay response, never the original request text."""
    store = LocalDeliveryResultStore(tmp_path / "results")
    request = "Remember synthetic evidence."
    fingerprint = store.fingerprint(request, "main")

    store.save("web-delivery-1", fingerprint, _response(), "2026-09-21T12:00:00Z")

    assert store.load("web-delivery-1", fingerprint) == _response()
    raw = next((tmp_path / "results").iterdir()).read_text(encoding="utf-8")
    assert request not in raw


def test_request_id_rebinding_and_corrupt_records_fail_closed(tmp_path: Path) -> None:
    """Reject a different logical request and tampered response under one stable ID."""
    store = LocalDeliveryResultStore(tmp_path / "results")
    fingerprint = store.fingerprint("first", "main")
    store.save("web-delivery-1", fingerprint, _response(), "2026-09-21T12:00:00Z")

    with pytest.raises(DeliveryResultError, match="already bound"):
        store.load("web-delivery-1", store.fingerprint("second", "main"))

    path = next((tmp_path / "results").iterdir())
    record = json.loads(path.read_text(encoding="utf-8"))
    record["response"]["status"] = "failed"
    path.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(DeliveryResultError, match="invalid"):
        store.load("web-delivery-1", fingerprint)


def test_result_bounds_and_identifiers_are_enforced(tmp_path: Path) -> None:
    """Reject unsafe identities, mismatched responses, and oversized replay state."""
    store = LocalDeliveryResultStore(tmp_path / "results")
    fingerprint = store.fingerprint("request", "main")

    with pytest.raises(DeliveryResultError, match="request ID"):
        store.save("../unsafe", fingerprint, _response("../unsafe"), "now")
    with pytest.raises(DeliveryResultError, match="response"):
        store.save("web-delivery-1", fingerprint, _response("other"), "now")
    oversized = _response()
    oversized["payload"] = "x" * (2 * 1024 * 1024)
    with pytest.raises(DeliveryResultError, match="too large"):
        store.save("web-delivery-1", fingerprint, oversized, "now")
