"""Provider-free guards for the frozen GPT-6 explainable contextual gate."""

from __future__ import annotations

import hashlib
from decimal import Decimal

import pytest

from benchmarks.contextual_explainable_v2 import run_live as runner


def test_gate_is_frozen_bounded_and_costed() -> None:
    """Pin GPT-6, the case mix, option oracle, call count, and conservative ceiling."""
    cases = runner.load_cases()
    ceiling, input_tokens = runner.conservative_cost_ceiling(cases)
    assert runner.MODEL == "gpt-6-luna"
    assert runner.REASONING_EFFORT == "medium"
    assert runner.MAX_OUTPUT_TOKENS == 256
    assert runner.MAX_PROVIDER_CALLS == 6
    assert cases[3]["id"] == "CTXE04_QUALIFIED_IDENTITY_OPTIONS"
    assert cases[3]["request"]["entity_type"] == "person"
    assert cases[3]["expected"] == {
        "outcomes": ["AMBIGUOUS", "UNRESOLVED"],
        "id": None,
        "ambiguous_ids": ["cloe", "bruno"],
    }
    assert hashlib.sha256(runner.CASES_PATH.read_bytes()).hexdigest() == (
        "d8460a37dc86df61ee630253f5db292a48afa5af1f769a42a8afd407ff04356f"
    )
    assert input_tokens == 76857
    assert ceiling == Decimal("0.00845370")
    assert runner.MAX_COST_USD == Decimal("0.00")
    assert runner.GATE_CONSUMED is True


def test_gate_accepts_safe_abstention_or_ambiguity_only_with_exact_options() -> None:
    """The product requirement is the exact grounded option set, not a forced outcome label."""
    case = runner.load_cases()[3]
    for outcome in ("AMBIGUOUS", "UNRESOLVED"):
        assert runner._passed(
            case, {"outcome": outcome, "id": None, "ambiguous_ids": ["cloe", "bruno"]}
        )
    assert not runner._passed(case, {"outcome": "UNRESOLVED", "id": None, "ambiguous_ids": []})
    assert not runner._passed(case, {"outcome": "RESOLVED", "id": "bruno", "ambiguous_ids": []})


def test_consumed_gate_refuses_before_provider_construction(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """The partially executed v2 gate is permanently closed before provider construction."""
    monkeypatch.setattr(runner, "OUTPUT_PATH", tmp_path / "result.jsonl")
    monkeypatch.setattr(
        runner,
        "OpenAIContextualReasoner",
        lambda *_args, **_kwargs: pytest.fail("provider constructed"),
    )
    with pytest.raises(SystemExit, match="permanently consumed"):
        runner.main(["--confirm-live-provider-calls"])


def test_gate_refuses_to_overwrite_even_when_budget_is_authorized(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """A frozen artifact path cannot be reused for a second provider run."""
    output = tmp_path / "result.jsonl"
    output.write_text("already used\n", encoding="utf-8")
    ceiling, _ = runner.conservative_cost_ceiling(runner.load_cases())
    monkeypatch.setattr(runner, "GATE_CONSUMED", False)
    monkeypatch.setattr(runner, "MAX_COST_USD", ceiling)
    monkeypatch.setattr(runner, "OUTPUT_PATH", output)
    monkeypatch.setattr(
        runner,
        "OpenAIContextualReasoner",
        lambda *_args, **_kwargs: pytest.fail("provider constructed"),
    )
    with pytest.raises(SystemExit, match="Refusing to overwrite"):
        runner.main(["--confirm-live-provider-calls"])
