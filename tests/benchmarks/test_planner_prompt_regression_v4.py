"""Provider-free guards for the current-schema Core Luna v4 gate."""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal

import pytest

from benchmarks.planner_prompt_regression_v1 import run_live as base
from benchmarks.planner_prompt_regression_v3 import run_live as prior
from benchmarks.planner_prompt_regression_v4 import run_live


def test_v4_replaces_only_obsolete_journal_event_sentinels() -> None:
    old, old_context = base.load_gate_cases()
    cases, context = run_live.load_gate_cases()
    assert context == old_context
    assert len(cases) == len(old) == run_live.MAX_CALLS == 16
    replaced = {6, 7, 9}
    for index, (before, after) in enumerate(zip(old, cases, strict=True)):
        if index not in replaced:
            assert after == before
    assert [cases[index]["id"] for index in (6, 7, 9)] == [
        "CSWR01-qualified-bounded-source-member",
        "CSWR02-relational-target-one-bounded-reference",
        "CSWR03-relational-target-two-bounded-references",
    ]
    assert all("Directorio Faro" in cases[index]["request"] for index in replaced)
    assert all("cena relacional" not in cases[index]["request"].casefold() for index in replaced)
    assert (
        hashlib.sha256(run_live._matrix_payload(cases, context)).hexdigest()
        == run_live.MATRIX_SHA256
    )


def test_v4_pins_exact_journal_candidate_contract() -> None:
    _cases, context = run_live.load_gate_cases()
    schema = json.loads(run_live.SCHEMA_PATH.read_text(encoding="utf-8"))
    assert prior._contract_hashes(schema, context) == (
        run_live.PROMPT_SHA256,
        run_live.PROVIDER_SCHEMA_SHA256,
        run_live.TEACHING_SHA256,
    )


def test_v4_budget_is_complete_and_bounded() -> None:
    budget = run_live.budget_snapshot()
    assert budget["calls"] == 16
    assert budget["conservative_usd_upper"] == Decimal("0.2076192")
    assert budget["conservative_usd_upper"] <= run_live.AUTHORIZED_CEILING_USD == Decimal("0.210")


def test_v4_has_zero_provider_authority_without_explicit_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(run_live.AUTH_ENV, raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "presence-only")
    with pytest.raises(SystemExit, match=run_live.AUTH_ENV):
        run_live._preflight()


def test_v4_allows_no_regression_outside_the_three_replaced_obsolete_fixtures() -> None:
    assert run_live.ACCEPTED_FAILURE_IDS == frozenset()
    assert run_live._matrix_acceptable([])
    assert not run_live._matrix_acceptable(
        [{"case_id": "PPR16-unknown-self-project-member-write", "passed": False}]
    )
    assert not run_live._matrix_acceptable(
        [{"case_id": "CSWR03-relational-target-two-bounded-references", "passed": False}]
    )
