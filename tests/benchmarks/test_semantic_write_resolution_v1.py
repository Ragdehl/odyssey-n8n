"""Deterministic guardrails for the Luna-only semantic WRITE-resolution gate."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from benchmarks.semantic_write_resolution_v1.evaluate import evaluate, load_registry
from benchmarks.semantic_write_resolution_v1.run_live import conservative_cost_ceiling
from odyssey_core.experimental_luna_planning import PlannerEscalation
from odyssey_core.request_planning import (
    KnowledgeReference,
    KnowledgeUnit,
    RequestPlan,
    SelectionCriteria,
    WriteAction,
)

ROOT = Path(__file__).resolve().parents[2]


def selection(query: str, *, self_target: str | None = None) -> SelectionCriteria:
    """Build one semantic person lookup for evaluator fixtures."""
    return SelectionCriteria(None, query, "person", (), None, self_target)


def unit(
    query: str,
    fact: str,
    *,
    self_target: str | None = None,
    references: tuple[KnowledgeReference, ...] = (),
    lookup_only: bool = False,
) -> KnowledgeUnit:
    """Build one immutable evaluated write unit."""
    return KnowledgeUnit(
        selection(query, self_target=self_target),
        "record",
        (),
        (),
        () if lookup_only else (fact,),
        references,
        "one",
        None,
        lookup_only,
    )


def test_registry_is_the_five_frozen_write_cases() -> None:
    """Keep this gate focused on the exact changed semantic WRITE surface."""
    registry = load_registry()
    assert registry["version"] == "semantic-write-resolution-v1"
    assert [case["id"] for case in registry["cases"]] == [
        "SWR01-self-coworkers",
        "SWR02-described-child-target",
        "SWR03-described-friend-target",
        "SWR04-target-and-described-reference",
        "SWR05-unsafe-pronoun",
    ]


def test_evaluator_accepts_intended_semantic_shapes() -> None:
    """Require self only for self facts and semantic lookup units for mentioned entities."""
    coworkers = RequestPlan(
        (
            WriteAction(
                (
                    unit(
                        "yo",
                        "{{ref:0}} y {{ref:1}} son mis compañeros de trabajo.",
                        self_target="self",
                        references=(
                            KnowledgeReference(1, "coworker", "Axel"),
                            KnowledgeReference(2, "coworker", "Denis"),
                        ),
                    ),
                    unit("Axel", "", lookup_only=True),
                    unit("Denis", "", lookup_only=True),
                )
            ),
        ),
        (),
    )
    child = RequestPlan(
        (WriteAction((unit("mi hijo al que le gusta el fútbol", "Adora el chocolate."),)),), ()
    )
    friend = RequestPlan(
        (WriteAction((unit("la amiga con la que cené ayer", "Se muda a París."),)),), ()
    )
    mixed = RequestPlan(
        (
            WriteAction(
                (
                    unit(
                        "mi hijo mayor",
                        "Fue al cine con {{ref:0}}.",
                        references=(
                            KnowledgeReference(1, "companion", "la amiga que vive en Lyon"),
                        ),
                    ),
                    unit("la amiga que vive en Lyon", "", lookup_only=True),
                )
            ),
        ),
        (),
    )
    assert evaluate(coworkers, "self_relationship_references").passed
    assert evaluate(child, "descriptive_child_target").passed
    assert evaluate(friend, "descriptive_friend_target").passed
    assert evaluate(mixed, "descriptive_target_and_reference").passed
    assert evaluate(PlannerEscalation(), "fail_closed_ambiguous_pronoun").passed


def test_cost_ceiling_is_luna_only_and_bounded() -> None:
    """Price exactly five Luna/low calls; no Sol allowance is part of this gate."""
    registry = load_registry()
    schema = json.loads((ROOT / "config/note-schema.json").read_text(encoding="utf-8"))
    cost, input_bound = conservative_cost_ceiling(
        registry["cases"], registry["fixed_context"], schema
    )
    assert Decimal("0") < cost < Decimal("0.07")
    assert input_bound > 0


def test_zero_authorization_refuses_before_provider_construction(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Keep the prepared gate un-runnable until a user explicitly approves its paid ceiling."""
    import benchmarks.semantic_write_resolution_v1.run_live as runner

    monkeypatch.setattr(runner, "OUTPUT_PATH", tmp_path / "must-not-exist.jsonl")
    monkeypatch.setattr(
        runner.OpenAILunaExperimentalPlanner,
        "from_environment",
        lambda *_args, **_kwargs: pytest.fail("provider constructed without authorization"),
    )
    with pytest.raises(SystemExit, match=r"exceeds \$0.00 authorization"):
        runner.main(["--confirm-live-provider-calls"])
    assert not runner.OUTPUT_PATH.exists()


def test_missing_confirmation_refuses_before_provider_construction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Require an explicit command-line confirmation even after a future budget approval."""
    import benchmarks.semantic_write_resolution_v1.run_live as runner

    monkeypatch.setattr(runner, "MAX_COST_USD", Decimal("1"))
    monkeypatch.setattr(
        runner.OpenAILunaExperimentalPlanner,
        "from_environment",
        lambda *_args, **_kwargs: pytest.fail("provider constructed without confirmation"),
    )
    with pytest.raises(SystemExit, match="without --confirm-live-provider-calls"):
        runner.main([])
