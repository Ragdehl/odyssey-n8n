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
    RelationalReference,
    RequestPlan,
    SelectionCriteria,
    WriteAction,
)

ROOT = Path(__file__).resolve().parents[2]


def selection(
    query: str,
    *,
    self_target: str | None = None,
    relational_reference: RelationalReference | None = None,
) -> SelectionCriteria:
    """Build one semantic person lookup for evaluator fixtures."""
    return SelectionCriteria(None, query, "person", (), None, self_target, relational_reference)


def unit(
    query: str,
    fact: str,
    *,
    self_target: str | None = None,
    references: tuple[KnowledgeReference, ...] = (),
    lookup_only: bool = False,
    relational_reference: RelationalReference | None = None,
) -> KnowledgeUnit:
    """Build one immutable evaluated write unit."""
    return KnowledgeUnit(
        selection(query, self_target=self_target, relational_reference=relational_reference),
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


def test_active_schema_registry_captures_the_manual_rich_daughter_regression() -> None:
    """Keep historical v1 frozen while the pending current gate covers the DEV failure exactly."""
    import benchmarks.semantic_write_resolution_v1.run_live as runner

    registry = json.loads(runner.ACTIVE_REGISTRY_PATH.read_text(encoding="utf-8"))
    assert registry["version"] == "semantic-write-resolution-active-schema-2026-09-28"
    assert len(registry["cases"]) == 7
    daughter = registry["cases"][1]
    assert daughter == {
        "id": "SWR02-rich-daughter-target",
        "request": "Mi hija a la que le gusta ver detectives de animales adora el chocolate.",
        "expect": "descriptive_daughter_target",
    }
    assert registry["cases"][-2] == {
        "id": "SWR06-existing-source-relational-anchor",
        "request": "El amigo de Bruno que vive en Lyon se muda a Toulouse.",
        "expect": "qualified_existing_relation_target",
    }
    assert registry["cases"][-1] == {
        "id": "SWR07-qualified-event-member",
        "request": (
            "De las personas que estuvieron en la cena relacional de prueba, "
            "la que trabaja en Airbus Test se ha comprado un paraguas rojo."
        ),
        "expect": "qualified_existing_event_relation_target",
    }


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
    daughter = RequestPlan(
        (
            WriteAction(
                (
                    unit(
                        "mi hija a la que le gusta ver detectives de animales",
                        "Adora el chocolate.",
                        relational_reference=RelationalReference("mi hija", "self", None, "one"),
                    ),
                )
            ),
        ),
        (),
    )
    bad_daughter = RequestPlan(
        (
            WriteAction(
                (
                    unit(
                        "mi hija a la que le gusta ver detectives de animales",
                        "Adora el chocolate.",
                    ),
                )
            ),
        ),
        (),
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
                        relational_reference=RelationalReference("mi hijo", "self", None, "one"),
                    ),
                    unit("la amiga que vive en Lyon", "", lookup_only=True),
                )
            ),
        ),
        (),
    )
    assert evaluate(coworkers, "self_relationship_references").passed
    assert evaluate(child, "descriptive_child_target").passed
    assert evaluate(daughter, "descriptive_daughter_target").passed
    assert not evaluate(bad_daughter, "descriptive_daughter_target").passed
    assert evaluate(friend, "descriptive_friend_target").passed
    assert evaluate(mixed, "descriptive_target_and_reference").passed
    existing = RequestPlan(
        (
            WriteAction(
                (
                    unit(
                        "el amigo de Bruno que vive en Lyon",
                        "Se muda a Toulouse.",
                        relational_reference=RelationalReference(
                            "los amigos de Bruno", "existing", "Bruno", "one"
                        ),
                    ),
                )
            ),
        ),
        (),
    )
    assert evaluate(existing, "qualified_existing_relation_target").passed
    event_member = RequestPlan(
        (
            WriteAction(
                (
                    unit(
                        "la persona de la cena relacional de prueba que trabaja en Airbus Test",
                        "Se ha comprado un paraguas rojo.",
                        relational_reference=RelationalReference(
                            "las personas que estuvieron en la cena relacional de prueba",
                            "existing",
                            "cena relacional de prueba",
                            "one",
                        ),
                    ),
                )
            ),
        ),
        (),
    )
    assert evaluate(event_member, "qualified_existing_event_relation_target").passed
    assert evaluate(PlannerEscalation(), "fail_closed_ambiguous_pronoun").passed


def test_cost_ceiling_is_luna_only_and_bounded() -> None:
    """Price exactly seven Luna/low calls; no Sol allowance is part of this gate."""
    import benchmarks.semantic_write_resolution_v1.run_live as runner

    registry = json.loads(runner.ACTIVE_REGISTRY_PATH.read_text(encoding="utf-8"))
    schema = json.loads((ROOT / "config/note-schema.json").read_text(encoding="utf-8"))
    cost, input_bound = conservative_cost_ceiling(
        registry["cases"], registry["fixed_context"], schema
    )
    assert Decimal("0.09") < cost < Decimal("0.10")
    assert input_bound > 0

    assert runner.MAX_COST_USD == Decimal("0.00")


def test_over_budget_refuses_before_provider_construction(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Refuse before provider construction whenever the computed ceiling exceeds authorization."""
    import benchmarks.semantic_write_resolution_v1.run_live as runner

    monkeypatch.setattr(runner, "MAX_COST_USD", Decimal("0.05"))
    monkeypatch.setattr(runner, "OUTPUT_PATH", tmp_path / "must-not-exist.jsonl")
    monkeypatch.setattr(
        runner.OpenAILunaExperimentalPlanner,
        "from_environment",
        lambda *_args, **_kwargs: pytest.fail("provider constructed above authorization"),
    )
    with pytest.raises(SystemExit, match=r"exceeds \$0.05 authorization"):
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
