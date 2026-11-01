"""Immutable results of three *consumed* Router pilots, not current approval.

Their model requests changed and the obsolete caller was retired. This suite
checks retained evidence while active Router source/schema safety lives in
odyssey_apps.fact_candidates and the current whole-source Core regressions.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from benchmarks.fact_candidate_v2_live import run_remaining

ROOT = Path(__file__).resolve().parents[2]
HERE = ROOT / "benchmarks/fact_candidate_v2_live"
ARCHIVED_RESULTS = {
    "20261010T185618Z.json": (
        "df5ed03bd2a87b6d9b538d7928b732a45e2ab47d84cdfd7e551f4e6122b1bb56",
        None,
    ),
    "20261010T191859Z.json": (
        "94ab47ee4d4acd44d3e55f8f2bc19f0f5551f381324ef2262001885133706038",
        "v2",
    ),
    "20261010T193754Z.json": (
        "a5a9211c0c610075f1d84e8752b45bbb16647c8c0e0774201ccf7ca26b23875f",
        "v3",
    ),
}
FROZEN_ENVELOPES = {
    "prompt_v2_requests.json": "221c793a0218fc87dfb157bfea214501b223fd228aedf5851bd8deb00f350e69",
    "prompt_v3_requests.json": "0f9b71e49363649f7016a628cc319ad67476ad4d8debc1a1b90b5ca97c816f07",
}


def authentic_json(path: Path, sha256: str) -> dict:
    """Never re-anchor an old provider receipt to a changed prompt/response."""
    payload = path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != sha256:
        raise ValueError("Archived Router evidence digest changed")
    return json.loads(payload)


def test_all_consumed_receipts_preserve_negative_semantic_review() -> None:
    assert not (HERE / "run_live.py").exists()
    assert len(list((HERE / "results").glob("*.json"))) == len(ARCHIVED_RESULTS)
    assert run_remaining.HERE == HERE
    assert run_remaining.ROOT == ROOT
    for name, (digest, revision) in ARCHIVED_RESULTS.items():
        receipt = authentic_json(HERE / "results" / name, digest)
        assert receipt.get("prompt_revision") == revision
        assert receipt["mode"] == "LIVE_SYNTHETIC_ROUTER"
        assert receipt["model"] == "gpt-6-luna"
        assert receipt["reasoning"] == "low"
        assert receipt["cases"] == ["F14", "F27", "F09", "F10"]
        assert receipt["call_limit"] == len(receipt["results"]) == 4
        assert receipt["budget_ceiling_usd"] == 0.02
        assert 0 < receipt["conservative_reservation_usd"] < receipt["budget_ceiling_usd"]
        assert receipt["live_model_quality_verified"] is False
        assert receipt["oracle_comparison"]["all_fixture_matches"] is False
        assert receipt["oracle_comparison"]["human_semantic_review_required"] is True
        assert all(row["result"] == "source_valid" for row in receipt["results"])


def test_frozen_request_envelopes_are_preserved_without_new_calls() -> None:
    for name, digest in FROZEN_ENVELOPES.items():
        snapshot = authentic_json(HERE / name, digest)
        assert [row["id"] for row in snapshot["calls"]] == ["F14", "F27", "F09", "F10"]
        assert all(
            row["request"]["model"] == "gpt-6-luna"
            and row["request"]["store"] is False
            and row["request"]["text"]["format"]["strict"] is True
            for row in snapshot["calls"]
        )


def test_modified_receipt_cannot_be_replayed_as_evidence(tmp_path: Path) -> None:
    name, (digest, _) = next(iter(ARCHIVED_RESULTS.items()))
    path = tmp_path / name
    path.write_bytes((HERE / "results" / name).read_bytes() + b" ")
    with pytest.raises(ValueError, match="digest changed"):
        authentic_json(path, digest)
