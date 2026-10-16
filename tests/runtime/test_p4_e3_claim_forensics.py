"""E3 claim forensics are immutable, actor-local and cannot authorize blind retry."""

from __future__ import annotations

import json
from uuid import uuid4

import pytest

from odyssey_runtime.delivery_results import DeliveryResultError, LocalDeliveryResultStore


def _store(tmp_path):
    store = LocalDeliveryResultStore(tmp_path / str(uuid4()) / "delivery-results")
    request = "p4-synthetic"
    fingerprint = store.fingerprint("Crear tarea ejemplo", "main")
    return store, request, fingerprint


def test_unseen_then_claim_is_uncertain_and_inspection_has_zero_side_effects(tmp_path):
    store, request, fingerprint = _store(tmp_path)
    assert store.inspect_mutation_claim(request, fingerprint) == {
        "state": "unseen",
        "receipt_verified": False,
        "claim_pending": False,
        "replay_permitted": False,
    }
    store.claim_mutation(request, fingerprint)
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    result = store.inspect_mutation_claim(request, fingerprint)
    assert result == {
        "state": "unresolved_attempt",
        "receipt_verified": False,
        "claim_pending": True,
        "replay_permitted": False,
    }
    assert {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()} == before
    with pytest.raises(DeliveryResultError, match="unresolved prior attempt"):
        store.claim_mutation(request, fingerprint)


def test_persisted_result_confirms_safe_replay_even_if_claim_cleanup_crashed(tmp_path):
    store, request, fingerprint = _store(tmp_path)
    store.claim_mutation(request, fingerprint)
    store.save(
        request,
        fingerprint,
        {"request_id": request, "status": "completed"},
        "2026-10-16T20:00:00+02:00",
    )
    assert (
        store.inspect_mutation_claim(request, fingerprint)["state"]
        == "receipt_confirmed_with_stale_claim"
    )
    assert store.inspect_mutation_claim(request, fingerprint)["replay_permitted"] is True
    store.finish_mutation_claim(request)
    assert store.inspect_mutation_claim(request, fingerprint)["state"] == "receipt_confirmed"


def test_conflicting_fingerprint_and_tampered_claim_are_rejected(tmp_path):
    store, request, fingerprint = _store(tmp_path)
    store.claim_mutation(request, fingerprint)
    wrong = store.fingerprint("Otra petición", "main")
    with pytest.raises(DeliveryResultError):
        store.inspect_mutation_claim(request, wrong)
    claim_path = next(tmp_path.rglob("*.claim"))
    claim = json.loads(claim_path.read_text())
    claim["fingerprint"] = wrong
    claim_path.write_text(json.dumps(claim))
    with pytest.raises(DeliveryResultError):
        store.inspect_mutation_claim(request, fingerprint)


def test_forensics_do_not_create_actor_roots(tmp_path):
    store, request, fingerprint = _store(tmp_path)
    store.inspect_mutation_claim(request, fingerprint)
    assert not list(tmp_path.iterdir())
