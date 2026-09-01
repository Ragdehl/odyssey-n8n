"""Deterministic tests for the Phase 17E reduction harness boundary."""

from types import SimpleNamespace

import pytest

from benchmarks.phase17e_retrieval.reduction import (
    REASONING_EFFORTS,
    select_cases,
    selector_schema,
    validate_selection,
)
from benchmarks.phase17e_retrieval.run_answer_path import (
    aggregate_rows,
    answer_schema,
    checkpoint_identity,
    evaluate_support,
    load_checkpoint,
    validate_answer,
    write_checkpoint,
)


def test_answer_contract_and_oracle() -> None:
    """Answer validation and local oracle remain closed and deterministic."""
    assert answer_schema()["additionalProperties"] is False
    response = validate_answer(
        {"answer": "Marta trabaja en Thales.", "supporting_locators": ["marta#fact-0"]},
        {"marta#fact-0"},
    )
    assert evaluate_support(
        response, {"marta#fact-0": "Trabaja en Thales."}, ("Trabaja en Thales.",)
    )


def test_answer_rejects_invalid_support() -> None:
    """Unknown, duplicate, and absent support citations fail closed."""
    with pytest.raises(ValueError):
        validate_answer({"answer": "x", "supporting_locators": ["unknown"]}, {"known"})
    with pytest.raises(ValueError):
        validate_answer({"answer": "x", "supporting_locators": ["known", "known"]}, {"known"})


def test_answer_aggregates_split_selector_branches() -> None:
    """Answer-path summaries keep SELECT and ESCALATE measurements separate."""
    row = {
        "decision": "SELECT",
        "required_evidence_supported": True,
        "sol_input_tokens": 10,
        "sol_output_tokens": 2,
        "sol_reasoning_tokens": 0,
        "evidence_fact_count": 1,
        "evidence_text_tokens": 4,
    }
    summary = aggregate_rows(
        [row, {**row, "decision": "ESCALATE", "required_evidence_supported": False}]
    )
    assert summary["select"]["case_count"] == 1
    assert summary["escalate"]["correct"] == 0
    assert summary["overall"]["case_count"] == 2


def test_checkpoint_round_trip_and_incompatible_inputs_fail_closed(tmp_path) -> None:
    """Completed rows resume only when model and persisted input identities match."""
    luna = tmp_path / "luna.json"
    ranking = tmp_path / "ranking.json"
    output = tmp_path / "answers.json"
    luna.write_text("luna", encoding="utf-8")
    ranking.write_text("ranking", encoding="utf-8")
    identity = checkpoint_identity(luna, ranking)
    row = {"case": "q1", "required_evidence_supported": True}
    write_checkpoint(output, identity, [row], "CHECKPOINT")
    assert load_checkpoint(output, identity) == {"q1": row}
    ranking.write_text("changed", encoding="utf-8")
    with pytest.raises(ValueError, match="incompatible"):
        load_checkpoint(output, checkpoint_identity(luna, ranking))


def test_case_filter_preserves_frozen_order() -> None:
    """Repeated case selection returns requested cases in corpus order."""
    cases = tuple(SimpleNamespace(id=value) for value in ("q1", "scale-100", "q2"))
    assert [case.id for case in select_cases(cases, ("q2", "q1"))] == ["q1", "q2"]


def test_case_filter_defaults_to_full_suite() -> None:
    """No case arguments preserve the complete benchmark suite."""
    cases = tuple(SimpleNamespace(id=value) for value in ("q1", "q2"))
    assert select_cases(cases, None) == cases


def test_case_filter_rejects_unknown_id() -> None:
    """A typo cannot silently produce an empty or partial live run."""
    with pytest.raises(ValueError, match="unknown benchmark case ids"):
        select_cases((SimpleNamespace(id="q1"),), ("missing",))


def test_reasoning_efforts_are_staged() -> None:
    """The CLI exposes the staged benchmark configurations without production changes."""
    assert REASONING_EFFORTS == ("none", "low", "medium", "high")


def test_selector_schema_is_closed() -> None:
    """The model contract permits only the decision and supplied locator list."""
    assert selector_schema()["additionalProperties"] is False


def test_selection_rejects_unknown_locator() -> None:
    """Unknown model-selected locators fail closed."""
    with pytest.raises(ValueError, match="unknown locator"):
        validate_selection({"decision": "SELECT", "locators": ["missing"]}, {"known"})
