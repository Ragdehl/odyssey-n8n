"""Provider-free guards for the fixed-fact enrichment v1 live gate."""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal

import pytest

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


def test_fixed_fact_v1_pins_separate_model_contract() -> None:
    schema = json.loads(run_live.SCHEMA_PATH.read_text(encoding="utf-8"))
    assert run_live.contract_hashes(schema) == (
        run_live.PROMPT_SHA256,
        run_live.PROVIDER_SCHEMA_SHA256,
    )


def test_fixed_fact_v1_budget_is_bounded() -> None:
    budget = run_live.budget_snapshot()
    assert budget["calls"] == 3
    assert budget["conservative_usd_upper"] == Decimal("0.009069")
    assert budget["conservative_usd_upper"] <= run_live.AUTHORIZED_CEILING_USD == Decimal("0.012")


def test_fixed_fact_v1_has_zero_provider_authority_without_explicit_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(run_live.AUTH_ENV, raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "presence-only")
    with pytest.raises(SystemExit, match=run_live.AUTH_ENV):
        run_live._preflight()


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
