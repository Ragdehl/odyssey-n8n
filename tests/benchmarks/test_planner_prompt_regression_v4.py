"""Provider-free guards for the three-case current-schema Core Luna v4 gate."""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal

import pytest

from benchmarks.planner_prompt_regression_v1 import run_live as base
from benchmarks.planner_prompt_regression_v3 import run_live as prior
from benchmarks.planner_prompt_regression_v4 import run_live


def test_v4_runs_only_the_three_current_bounded_source_successors() -> None:
    cases, context = run_live.load_gate_cases()
    _old, old_context = base.load_gate_cases()
    assert context == old_context
    assert len(cases) == run_live.MAX_CALLS == 3
    assert [case["id"] for case in cases] == [
        "CSWR01-qualified-bounded-source-member",
        "CSWR02-relational-target-one-bounded-reference",
        "CSWR03-relational-target-two-bounded-references",
    ]
    assert all("Directorio Faro" in case["request"] for case in cases)
    assert all("cena relacional" not in case["request"].casefold() for case in cases)
    assert (
        hashlib.sha256(run_live._matrix_payload(cases, context)).hexdigest()
        == run_live.MATRIX_SHA256
    )


def test_v4_keeps_exact_v3_model_facing_contract() -> None:
    _cases, context = run_live.load_gate_cases()
    schema = json.loads(run_live.SCHEMA_PATH.read_text(encoding="utf-8"))
    assert prior._contract_hashes(schema, context) == (
        run_live.PROMPT_SHA256,
        run_live.PROVIDER_SCHEMA_SHA256,
        run_live.TEACHING_SHA256,
    )


def test_v4_budget_is_three_calls_and_bounded() -> None:
    budget = run_live.budget_snapshot()
    assert budget["calls"] == 3
    assert budget["conservative_usd_upper"] == Decimal("0.0388728")
    assert budget["conservative_usd_upper"] <= run_live.AUTHORIZED_CEILING_USD == Decimal("0.040")


def test_v4_has_zero_provider_authority_without_explicit_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(run_live.AUTH_ENV, raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "presence-only")
    with pytest.raises(SystemExit, match=run_live.AUTH_ENV):
        run_live._preflight()
