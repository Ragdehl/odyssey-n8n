"""Durable, per-actor post-receipt diagnostics, without provider or Markdown."""

from __future__ import annotations

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest

from odyssey_runtime.deferred_diagnostics import (
    DeferredDiagnosticStore,
    project_receipt_diagnostic_evidence,
)
from odyssey_runtime.delivery_results import DeliveryResultError, LocalDeliveryResultStore

REQUEST_ID = "deferred-c4-demo"
FINGERPRINT = "a" * 64


def _base(actor, suffix="original"):
    root = actor / "delivery-results"
    store = LocalDeliveryResultStore(root)
    reply = {"request_id": REQUEST_ID, "status": "needs_attention", "message": suffix}
    digest = store._response_digest(reply)
    store.save(REQUEST_ID, FINGERPRINT, reply, "2026-10-29T15:00:00Z")
    return digest, reply


def test_claim_and_result_never_modify_base_receipt(tmp_path):
    root = tmp_path / "actor-a"
    digest, base = _base(root)
    state = DeferredDiagnosticStore(root / "c4-diagnostics")
    assert state.read(REQUEST_ID, FINGERPRINT, digest) == {"status": "unavailable"}
    assert state.claim(REQUEST_ID, FINGERPRINT, digest) is True
    assert state.claim(REQUEST_ID, FINGERPRINT, digest) is False
    assert state.read(REQUEST_ID, FINGERPRINT, digest) == {"status": "pending"}
    diagnosed = {"verified_stage_only": True, "evidence_stage": "application.router"}
    state.finish(REQUEST_ID, FINGERPRINT, digest, diagnosed)
    assert state.read(REQUEST_ID, FINGERPRINT, digest) == {
        "status": "completed",
        "diagnosis": diagnosed,
    }
    state.finish(REQUEST_ID, FINGERPRINT, digest, diagnosed)
    with pytest.raises(DeliveryResultError):
        state.finish(REQUEST_ID, FINGERPRINT, digest, {"unexpected": "change"})
    assert LocalDeliveryResultStore(root / "delivery-results").load(REQUEST_ID, FINGERPRINT) == base


def test_actor_and_receipt_digest_are_non_interchangeable(tmp_path):
    actor_a = tmp_path / "actor-a"
    actor_b = tmp_path / "actor-b"
    digest, _ = _base(actor_a)
    other_digest, _ = _base(actor_b, suffix="different answer")
    state = DeferredDiagnosticStore(actor_a / "c4-diagnostics")
    assert state.claim(REQUEST_ID, FINGERPRINT, digest)
    assert DeferredDiagnosticStore(actor_b / "c4-diagnostics").read(
        REQUEST_ID, FINGERPRINT, other_digest
    ) == {"status": "unavailable"}
    with pytest.raises(DeliveryResultError):
        state.read(REQUEST_ID, FINGERPRINT, other_digest)
    with pytest.raises(DeliveryResultError):
        state.claim(REQUEST_ID, "b" * 64, digest)


def test_concurrent_claimers_only_one_wins(tmp_path):
    state = DeferredDiagnosticStore(tmp_path / "c4")
    digest = "c" * 64
    with ThreadPoolExecutor(max_workers=12) as pool:
        results = list(
            pool.map(
                lambda _: state.claim(REQUEST_ID, FINGERPRINT, digest),
                range(40),
            )
        )
    assert sum(results) == 1


def test_crash_after_claim_never_resubmits_provider_call(tmp_path):
    state = DeferredDiagnosticStore(tmp_path / "c4")
    digest = "f" * 64
    assert state.claim(REQUEST_ID, FINGERPRINT, digest)
    restarted = DeferredDiagnosticStore(tmp_path / "c4")
    assert not restarted.claim(REQUEST_ID, FINGERPRINT, digest)
    assert restarted.read(REQUEST_ID, FINGERPRINT, digest) == {"status": "pending"}
    restarted.finish(REQUEST_ID, FINGERPRINT, digest, None)
    assert restarted.read(REQUEST_ID, FINGERPRINT, digest) == {"status": "unavailable"}


def test_corrupt_terminal_never_claims_success(tmp_path):
    state = DeferredDiagnosticStore(tmp_path / "c4")
    digest = "f" * 64
    assert state.claim(REQUEST_ID, FINGERPRINT, digest)
    _, path = state._paths(REQUEST_ID)
    path.write_text(
        json.dumps(
            {
                "request_id": REQUEST_ID,
                "fingerprint": FINGERPRINT,
                "response_sha256": hashlib.sha256(b"bad").hexdigest(),
                "status": "completed",
                "diagnosis": {"wrong": True},
                "version": 1,
            }
        )
    )
    with pytest.raises(DeliveryResultError):
        state.read(REQUEST_ID, FINGERPRINT, digest)


def test_racing_claimers_never_read_a_partially_published_claim(tmp_path, monkeypatch):
    """A reservation is visible only after its complete content is durable."""
    import os

    state = DeferredDiagnosticStore(tmp_path / "c4")
    original_link = os.link
    paused = Event()
    proceed = Event()

    def delay_first_link(source, destination):
        if str(destination).endswith(".claim") and not paused.is_set():
            paused.set()
            assert proceed.wait(timeout=4)
        return original_link(source, destination)

    monkeypatch.setattr(os, "link", delay_first_link)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(state.claim, REQUEST_ID, FINGERPRINT, "b" * 64)
        assert paused.wait(timeout=4)
        second = pool.submit(state.claim, REQUEST_ID, FINGERPRINT, "b" * 64)
        assert second.result(timeout=4) is True
        proceed.set()
        assert first.result(timeout=4) is False
    assert state.read(REQUEST_ID, FINGERPRINT, "b" * 64) == {"status": "pending"}


def test_receipt_stage_evidence_rejects_false_status_and_write_claims():
    stage = {
        "name": "candidate.source_boundary_review",
        "outcome": "failed",
        "route_index": None,
        "parent_stage": None,
        "stage_view": {"version": 1, "label": "Core · revisión", "icon": "core"},
    }
    response = {
        "request_id": REQUEST_ID,
        "status": "needs_attention",
        "product_reason": "SOURCE_UNVERIFIED",
        "affected_stable_note_ids": [],
        "execution_ledger": {
            "version": 1,
            "request_id": REQUEST_ID,
            "status": "needs_attention",
            "affected_stable_note_ids": [],
            "stages": [stage],
        },
    }
    evidence = project_receipt_diagnostic_evidence(response)
    assert evidence["write_evidence"] == "UNKNOWN"
    assert evidence["stages"] == [stage]
    assert not any("note" in key for key in evidence)
    mismatch = json.loads(json.dumps(response))
    mismatch["affected_stable_note_ids"] = ["invented-note"]
    assert project_receipt_diagnostic_evidence(mismatch) is None
    mismatch = json.loads(json.dumps(response))
    mismatch["execution_ledger"]["status"] = "failed"
    assert project_receipt_diagnostic_evidence(mismatch) is None
