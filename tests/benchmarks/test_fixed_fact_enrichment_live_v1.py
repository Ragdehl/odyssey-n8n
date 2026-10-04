"""Provider-free guards for the fixed-fact enrichment v1 live gate."""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal

from benchmarks.fixed_fact_enrichment_live_v1 import run_live
from odyssey_core.semantic_write import (
    CandidateScope,
    CandidateScopeExtent,
    IdentityBinding,
    IdentityIntent,
    IdentityPart,
    LiteralPart,
    SemanticFact,
)


def test_fixed_fact_v1_registry_is_frozen_and_small() -> None:
    cases = run_live.load_cases()
    assert len(cases) == run_live.MAX_CALLS == 3
    assert [case["id"] for case in cases] == [
        "FFE01-nickname-occurrence",
        "FFE02-complete-self-set",
        "FFE03-mixed-canonical-day-content",
    ]
    assert hashlib.sha256(run_live.CASES_PATH.read_bytes()).hexdigest() == run_live.CASES_SHA256


def _retained_v1_artifact() -> dict:
    return json.loads((run_live.RESULTS_DIR / "8a1a4fdee6e5.json").read_text(encoding="utf-8"))


def test_fixed_fact_v1_retained_evidence_matches_frozen_contract() -> None:
    artifact = _retained_v1_artifact()
    assert artifact["prompt_sha256"] == run_live.PROMPT_SHA256
    assert artifact["provider_schema_sha256"] == run_live.PROVIDER_SCHEMA_SHA256
    assert artifact["cases_sha256"] == run_live.CASES_SHA256


def test_fixed_fact_v1_retains_the_observed_blocking_failure() -> None:
    artifact = _retained_v1_artifact()
    assert artifact["provider_attempts"] == artifact["completed_provider_responses"] == 3
    assert artifact["automatic_retries"] == 0
    assert artifact["acceptable"] is False
    assert artifact["failed_case_ids"] == ["FFE02-complete-self-set"]
    assert Decimal(artifact["estimated_standard_cost_usd"]) < run_live.AUTHORIZED_CEILING_USD


def test_fixed_fact_v1_is_consumed_historical_evidence() -> None:
    assert list(run_live.RESULTS_DIR.glob("*.json"))


def _described(text: str, scope: CandidateScope | None = None) -> IdentityPart:
    return IdentityPart(
        text,
        IdentityIntent(
            text,
            IdentityBinding.DESCRIBED,
            note_type="person",
            candidate_scope=scope,
        ),
    )


def test_fixed_fact_v1_oracles_require_identity_and_complete_self_set() -> None:
    bea = _described("bea")
    case = {"expect": "nickname_identity"}
    passed, findings = run_live.evaluate(
        SemanticFact((LiteralPart("He vaciado el garaje con "), bea, LiteralPart("."))), case
    )
    assert passed, findings

    children = _described(
        "mis hijos",
        CandidateScope(IdentityBinding.SELF, "mis hijos", CandidateScopeExtent.COMPLETE_SET),
    )
    case = {"expect": "complete_self_set"}
    passed, findings = run_live.evaluate(
        SemanticFact((LiteralPart("He ordenado el garaje con "), children, LiteralPart("."))), case
    )
    assert passed, findings
