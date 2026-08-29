"""Focused provider-free coverage for Phase 17D update semantics."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from odyssey_core import (
    StructuredPropertyChangeContext,
    WriterOutputError,
    WriteTargetDecision,
    WriteTargetOutcome,
    create_entity,
    materialize_update,
)
from odyssey_core.request_planning import (
    KnowledgeUnit,
    PropertyChange,
    RequestPlanningError,
    SelectionCriteria,
    validate_request_plan,
)
from odyssey_core.storage import VaultRepository

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads((ROOT / "config/note-schema.json").read_text(encoding="utf-8"))
NOW = "2026-08-29T10:00:00+02:00"


class FakeWriter:
    """Return fixed writer operations and retain the bounded request."""

    def __init__(self, operations: list[dict[str, str]]) -> None:
        self.operations = operations
        self.requests: list[object] = []

    def write(self, request: object) -> object:
        """Record one request and return the configured operations."""
        self.requests.append(request)
        return {"operations": self.operations}


def raw_unit(
    *,
    semantics: str,
    intent: str = "amend",
    cardinality: str = "one",
    destination: str | None = None,
) -> dict:
    """Build one valid raw unit whose semantic discriminator can be varied."""
    return {
        "target": {
            "entity": "Marta",
            "query": "Marta",
            "type": "person",
            "filters": [],
            "link_scope": None,
        },
        "cardinality": cardinality,
        "destination_type": destination,
        "intent": intent,
        "update_semantics": semantics,
        "properties": [],
        "tag_changes": [],
        "facts": [] if intent == "delete" else ["Marta trabaja en Thales."],
        "references": [],
    }


def plan(raw: dict) -> object:
    """Validate one raw semantic unit through the production RequestPlan boundary."""
    return validate_request_plan(
        {"actions": [{"kind": "write", "units": [raw]}], "limitations": []}, SCHEMA
    )


def test_planner_validates_explicit_update_semantics() -> None:
    """Permit non-ordinary semantics only for a single non-migration amend."""
    assert (
        plan(raw_unit(semantics="transition")).actions[0].units[0].update_semantics == "transition"
    )  # type: ignore[union-attr]
    assert (
        plan(raw_unit(semantics="correction")).actions[0].units[0].update_semantics == "correction"
    )  # type: ignore[union-attr]
    assert plan(raw_unit(semantics="ordinary")).actions[0].units[0].update_semantics == "ordinary"  # type: ignore[union-attr]
    for invalid in (
        raw_unit(semantics="transition", intent="record"),
        raw_unit(semantics="correction", intent="remove"),
        raw_unit(semantics="transition", intent="delete"),
        raw_unit(semantics="transition", cardinality="all_matching")
        | {
            "target": {
                "entity": None,
                "query": "Marta",
                "type": "person",
                "filters": [],
                "link_scope": None,
            }
        },
        raw_unit(semantics="correction", destination="journal_entry"),
    ):
        with pytest.raises(RequestPlanningError, match="Non-ordinary"):
            plan(invalid)


@pytest.fixture
def repository(tmp_path: Path) -> VaultRepository:
    """Provide one note with a structured current relationship and unrelated Markdown."""
    (tmp_path / "people").mkdir()
    repository = VaultRepository(tmp_path)
    create_entity(
        repository,
        SCHEMA,
        path="people/marta.md",
        entity_id="marta",
        metadata={"name": "Marta", "type": "person", "relationship_to_user": "compañera"},
        content="Marta trabaja en Airbus.\nTexto sin relación.",
        actor="test",
        now=NOW,
    )
    return repository


def unit(
    *, semantics: str = "ordinary", facts: tuple[str, ...] = (), value: str = "jefa"
) -> KnowledgeUnit:
    """Build one authorized existing-note relationship update."""
    return KnowledgeUnit(
        SelectionCriteria("Marta", "Marta", "person", (), None),
        "amend",
        (PropertyChange("relationship_to_user", "set", value),),
        (),
        facts,
        (),
        update_semantics=semantics,
    )


def materialize(
    repository: VaultRepository, knowledge: KnowledgeUnit, writer: FakeWriter | None = None
) -> object:
    """Execute one update with stable deterministic lifecycle inputs."""
    return materialize_update(
        knowledge,
        WriteTargetDecision(WriteTargetOutcome.UPDATE, existing_note_id="marta"),
        repository=repository,
        schema=SCHEMA,
        actor="test",
        now="2026-08-29T11:00:00+02:00",
        writer=writer,
    )


def test_transition_reconciles_property_history_with_authoritative_context(
    repository: VaultRepository,
) -> None:
    """Keep an old true property value in the body while deterministically setting the current value."""
    writer = FakeWriter(
        [
            {"op": "APPEND", "text": "Marta era mi compañera de trabajo."},
            {"op": "APPEND", "text": "Marta ahora es mi jefa."},
        ]
    )
    materialize(
        repository, unit(semantics="transition", facts=("Marta ahora es mi jefa.",)), writer
    )
    request = writer.requests[0]
    assert request.update_semantics == "transition"  # type: ignore[union-attr]
    assert request.structured_property_changes == (
        StructuredPropertyChangeContext(
            "relationship_to_user", True, "compañera", "set", True, "jefa"
        ),
    )  # type: ignore[union-attr]
    raw = repository.read_text("people/marta.md")
    assert (
        'relationship_to_user: "jefa"' in raw
        and "compañera de trabajo" in raw
        and "ahora es mi jefa" in raw
    )


def test_correction_does_not_historicize_old_property(repository: VaultRepository) -> None:
    """Change a current property without asserting its false prior value as history."""
    materialize(repository, unit(semantics="correction"))
    raw = repository.read_text("people/marta.md")
    assert 'relationship_to_user: "jefa"' in raw and "compañera" not in raw


def test_ordinary_property_change_is_conservative_and_exact_noop_is_quiet(
    repository: VaultRepository,
) -> None:
    """Provide differing property context for ordinary reconciliation but skip exact no-op noise."""
    writer = FakeWriter([{"op": "APPEND", "text": "Marta era mi compañera de trabajo."}])
    materialize(repository, unit(), writer)
    assert writer.requests[0].update_semantics == "ordinary"  # type: ignore[union-attr]
    noop_writer = FakeWriter([{"op": "APPEND", "text": "must not run"}])
    materialize(repository, unit(value="jefa"), noop_writer)
    assert noop_writer.requests == []


def test_transition_and_ordinary_cannot_raw_remove_but_explicit_remove_can(
    repository: VaultRepository,
) -> None:
    """Keep removal authority limited to corrections and explicit remove requests."""
    for semantics in ("transition", "ordinary"):
        with pytest.raises(WriterOutputError, match="removal authority"):
            materialize(
                repository,
                unit(semantics=semantics, facts=("Marta trabaja en Thales.",)),
                FakeWriter([{"op": "REMOVE", "old": "Marta trabaja en Airbus."}]),
            )
    remove = KnowledgeUnit(
        SelectionCriteria("Marta", "Marta", "person", (), None),
        "remove",
        (),
        (),
        ("Marta trabaja en Airbus.",),
        (),
    )
    materialize(
        repository, remove, FakeWriter([{"op": "REMOVE", "old": "Marta trabaja en Airbus."}])
    )
    assert "Airbus" not in repository.read_text("people/marta.md")
