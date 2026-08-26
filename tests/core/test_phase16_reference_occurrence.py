"""Deterministic Phase 16.5A reference-occurrence contract tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from odyssey_core.request_planning import (
    KnowledgeReference,
    RequestPlanningError,
    WriteAction,
    validate_request_plan,
)

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads((ROOT / "config/note-schema.json").read_text(encoding="utf-8"))


def selection(query: str, note_type: str = "concept") -> dict:
    """Build one complete direct-note target fixture."""
    return {"entity": None, "query": query, "type": note_type, "filters": [], "link_scope": None}


def raw_unit(
    query: str,
    *,
    facts: list[str],
    references: list[dict] | None = None,
    intent: str = "record",
    note_type: str = "concept",
) -> dict:
    """Build one raw KnowledgeUnit with the closed occurrence contract."""
    return {
        "target": selection(query, note_type),
        "intent": intent,
        "properties": [],
        "tag_changes": [],
        "facts": facts,
        "references": [] if references is None else references,
    }


def plan(*units: dict):
    """Validate one write action through the production planner boundary."""
    return validate_request_plan(
        {"actions": [{"kind": "write", "units": list(units)}], "limitations": []}, SCHEMA
    ).actions[0]


def reference(target_index: int, role: str, mention: str) -> dict:
    """Build one occurrence-preserving reference fixture."""
    return {"target_index": target_index, "role": role, "mention": mention}


def test_one_reference_in_one_fact() -> None:
    """Preserve one marker, target index, role, and human-readable mention."""
    action = plan(
        raw_unit(
            "purchase",
            facts=["Bought {{ref:0}}."],
            references=[reference(1, "product", "Leche Pascual")],
        ),
        raw_unit("Leche Pascual", facts=[]),
    )

    assert isinstance(action, WriteAction)
    assert action.units[0].facts == ("Bought {{ref:0}}.",)
    assert action.units[0].references == (KnowledgeReference(1, "product", "Leche Pascual"),)


def test_two_references_in_one_fact_and_repeated_occurrence() -> None:
    """Allow two local references and repeated use of one marker."""
    action = plan(
        raw_unit(
            "purchase",
            facts=["Bought {{ref:1}} at {{ref:0}}; {{ref:1}} was my usual choice."],
            references=[
                reference(1, "store", "Carrefour Balma"),
                reference(2, "product", "Leche Pascual"),
            ],
        ),
        raw_unit("Carrefour Balma", facts=[]),
        raw_unit("Leche Pascual", facts=[]),
    )

    assert isinstance(action, WriteAction)
    assert action.units[0].references[0].mention == "Carrefour Balma"
    assert action.units[0].facts[0].count("{{ref:1}}") == 2


@pytest.mark.parametrize(
    ("fact", "mention"),
    [
        ("Compré {{ref:0}} en Toulouse.", "Leche Pascual"),
        ("J'ai acheté {{ref:0}} à Carrefour Balma.", "Leche Pascual"),
        ("Compré {{ref:0}} en la tienda de la esquina.", "la tienda de la esquina"),
    ],
)
def test_spanish_french_and_contextual_mentions_are_preserved(fact: str, mention: str) -> None:
    """Keep language and contextual wording instead of substituting canonical queries."""
    action = plan(
        raw_unit(
            "purchase",
            facts=[fact],
            references=[reference(1, "product", mention)],
        ),
        raw_unit("Leche Pascual", facts=[]),
    )

    assert isinstance(action, WriteAction)
    assert action.units[0].references[0].mention == mention


def test_reference_only_target_unit_is_valid() -> None:
    """Permit a factless record unit when another unit references it."""
    action = plan(
        raw_unit(
            "purchase",
            facts=["Bought {{ref:0}}."],
            references=[reference(1, "store", "Carrefour Balma")],
        ),
        raw_unit("Carrefour Balma", facts=[]),
    )

    assert isinstance(action, WriteAction)
    assert action.units[1].facts == ()


def test_only_semantic_references_are_marked_not_every_entity_name() -> None:
    """Leave unrelated named context unmarked while preserving the actual relationship target."""
    action = plan(
        raw_unit(
            "Laura",
            facts=["Laura es responsable de {{ref:0}} y trabaja con Marta en Airbus."],
            references=[reference(1, "responsibility", "Marta")],
        ),
        raw_unit("Marta", facts=[]),
    )

    assert isinstance(action, WriteAction)
    assert action.units[0].facts == (
        "Laura es responsable de {{ref:0}} y trabaja con Marta en Airbus.",
    )
    assert len(action.units[0].references) == 1


def test_target_identification_context_does_not_become_fact_reference() -> None:
    """Do not mark Marta when her wording only identifies the target entity."""
    action = plan(
        raw_unit(
            "la amiga de Marta",
            facts=["Ahora trabaja en Airbus."],
            references=[],
            intent="amend",
        ),
    )

    assert isinstance(action, WriteAction)
    assert action.units[0].references == ()
    assert action.units[0].facts == ("Ahora trabaja en Airbus.",)


@pytest.mark.parametrize(
    "bad_unit",
    [
        raw_unit(
            "source",
            facts=["Bought {{ref:x}}."],
            references=[reference(1, "product", "Leche")],
        ),
        raw_unit(
            "source",
            facts=["Bought {{ref:1}}."],
            references=[reference(1, "product", "Leche")],
        ),
        raw_unit(
            "source",
            facts=["Bought Leche."],
            references=[reference(1, "product", "Leche")],
        ),
        raw_unit("source", facts=["Bought {{ref:0}}."], references=[]),
        raw_unit(
            "source",
            facts=["Bought {{ref:0}}."],
            references=[reference(1, "product", " ")],
        ),
        raw_unit(
            "source",
            facts=["Bought [[Leche]]."],
            references=[],
        ),
    ],
)
def test_malformed_out_of_range_or_orphan_occurrences_fail_closed(bad_unit: dict) -> None:
    """Reject malformed markers, missing occurrences, raw wikilinks, and invalid mentions."""
    with pytest.raises(RequestPlanningError):
        plan(bad_unit, raw_unit("Leche", facts=[]))


def test_self_reference_remains_invalid_even_with_a_valid_occurrence() -> None:
    """Occurrence preservation does not weaken the existing self-reference prohibition."""
    with pytest.raises(RequestPlanningError):
        plan(
            raw_unit(
                "source",
                facts=["Related to {{ref:0}}."],
                references=[reference(0, "related", "source")],
            )
        )
