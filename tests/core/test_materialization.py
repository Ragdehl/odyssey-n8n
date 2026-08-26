"""Tests for the bounded Phase 16 UPDATE-only materialization slice."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from odyssey_core import (
    WRITER_CONTEXT_MODE,
    WRITER_MODEL,
    WRITER_REASONING_EFFORT,
    EntityRevisionMismatchError,
    MaterializationError,
    PersistenceOperation,
    WriterOutputError,
    WriterProviderError,
    WriterRequest,
    WriteTargetDecision,
    WriteTargetOutcome,
    build_openai_writer_payload,
    create_entity,
    materialize_update,
    update_entity,
)
from odyssey_core.request_planning import (
    KnowledgeReference,
    KnowledgeUnit,
    PropertyChange,
    SelectionCriteria,
    TagChange,
)
from odyssey_core.storage import VaultRepository

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads((ROOT / "config/note-schema.json").read_text(encoding="utf-8"))
NOW = "2026-08-25T10:00:00+02:00"


class FakeWriter:
    """Return one supplied writer response while retaining complete requests for assertions."""

    def __init__(self, response: object | Exception) -> None:
        """Set the deterministic response or failure returned from each writer call."""
        self.response = response
        self.requests: list[Any] = []

    def write(self, request: object) -> object:
        """Record one full-note request and return its configured result."""
        self.requests.append(request)
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


@pytest.fixture
def repository(tmp_path: Path) -> VaultRepository:
    """Provide one disposable vault containing the resolved existing person note."""
    (tmp_path / "people").mkdir()
    repo = VaultRepository(tmp_path)
    create_entity(
        repo,
        SCHEMA,
        path="people/bea.md",
        entity_id="person-bea",
        metadata={
            "name": "Bea",
            "type": "person",
            "relationship_to_user": "partner",
            "tags": ["idea"],
        },
        content="# Bea\n\n- Bea works at Airbus.\n- Bea lives in Toulouse.\n\nUnrelated *formatting*.",
        actor="test",
        now=NOW,
    )
    return repo


def unit(
    *,
    properties: tuple[PropertyChange, ...] = (),
    tags: tuple[TagChange, ...] = (),
    facts: tuple[str, ...] = (),
    intent: str = "amend",
    references: tuple[KnowledgeReference, ...] = (),
) -> KnowledgeUnit:
    """Build one already-validated unit aimed at the fixture target."""
    return KnowledgeUnit(
        SelectionCriteria("Bea", "Bea", "person", (), None),
        intent,
        properties,
        tags,
        facts,
        references,
    )


def decision() -> WriteTargetDecision:
    """Build the Phase 16.1 resolved UPDATE decision for the fixture note."""
    return WriteTargetDecision(WriteTargetOutcome.UPDATE, existing_note_id="person-bea")


def count_persistence(monkeypatch: pytest.MonkeyPatch, repository: VaultRepository) -> list[int]:
    """Count Phase 12 file replacements without changing repository behavior."""
    calls = [0]
    original = repository.replace_text

    def counted(*args: object, **kwargs: object) -> None:
        """Record the one final replacement before delegating to the repository."""
        calls[0] += 1
        original(*args, **kwargs)

    monkeypatch.setattr(repository, "replace_text", counted)
    return calls


def materialize(
    repository: VaultRepository,
    knowledge: KnowledgeUnit,
    writer: FakeWriter | None = None,
    rendered_facts: tuple[str, ...] | None = None,
):
    """Execute the public UPDATE materialization API with stable lifecycle inputs."""
    return materialize_update(
        knowledge,
        decision(),
        repository=repository,
        schema=SCHEMA,
        actor="phase16-test",
        now="2026-08-25T11:00:00+02:00",
        writer=writer,
        rendered_facts=rendered_facts,
    )


def test_exact_normalized_duplicate_skips_writer_and_persistence(
    repository: VaultRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A01: an exact list-item duplicate is a narrow deterministic no-change."""
    writer = FakeWriter({"operations": [{"op": "APPEND", "text": "must not run"}]})
    calls = count_persistence(monkeypatch, repository)
    before = repository.read_text("people/bea.md")

    result = materialize(repository, unit(facts=("  Bea   works at Airbus.  ",)), writer)

    assert result.operation is PersistenceOperation.NO_CHANGE
    assert writer.requests == []
    assert calls == [0]
    assert repository.read_text("people/bea.md") == before


def test_production_writer_payload_is_luna_medium_full_note_and_no_storage() -> None:
    """The runtime writer policy remains the selected single Phase 16.3 policy."""
    payload = build_openai_writer_payload(
        WriterRequest("person-bea", "person", "amend", ("Bea plays piano.",), "# Bea")
    )
    assert (WRITER_MODEL, WRITER_REASONING_EFFORT, WRITER_CONTEXT_MODE) == (
        "gpt-5.6-luna",
        "medium",
        "FULL_NOTE",
    )
    assert payload["model"] == WRITER_MODEL and payload["store"] is False
    assert payload["reasoning"] == {"effort": "medium"}
    assert "current_authoritative_markdown_body" in payload["input"][1]["content"]


def test_append_uses_full_note_context_and_one_persistence_call(
    repository: VaultRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A02: an independent fact appends once while preserving existing Markdown."""
    writer = FakeWriter({"operations": [{"op": "APPEND", "text": "- Bea plays piano."}]})
    calls = count_persistence(monkeypatch, repository)

    result = materialize(repository, unit(facts=("Bea plays piano.",)), writer)

    assert result.operation is PersistenceOperation.UPDATED
    assert calls == [1]
    assert (
        writer.requests[0].current_body
        == "# Bea\n\n- Bea works at Airbus.\n- Bea lives in Toulouse.\n\nUnrelated *formatting*."
    )
    body = repository.read_text("people/bea.md")
    assert "Bea works at Airbus." in body and "Bea plays piano." in body


def test_remove_exact_existing_fact_reaches_writer_and_persists_once(
    repository: VaultRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A remove fact is not swallowed by the positive-update duplicate shortcut."""
    writer = FakeWriter({"operations": [{"op": "REMOVE", "old": "- Bea works at Airbus.\n"}]})
    calls = count_persistence(monkeypatch, repository)

    result = materialize(repository, unit(intent="remove", facts=("Bea works at Airbus.",)), writer)

    assert result.operation is PersistenceOperation.UPDATED
    assert len(writer.requests) == 1
    assert calls == [1]
    assert "Bea works at Airbus." not in repository.read_text("people/bea.md")


@pytest.mark.parametrize(
    ("fact", "response", "present", "absent"),
    [
        (
            "Bea works at Thales.",
            {"operations": [{"op": "REPLACE", "old": "Airbus", "new": "Thales"}]},
            "Thales",
            "Airbus",
        ),
        (
            "Bea no longer lives in Toulouse.",
            {"operations": [{"op": "REMOVE", "old": "- Bea lives in Toulouse.\n"}]},
            "Unrelated",
            "Bea lives in Toulouse",
        ),
        (
            "Bea stopped piano.",
            {
                "operations": [
                    {
                        "op": "REPLACE",
                        "old": "Bea lives in Toulouse.",
                        "new": "Bea stopped playing piano.",
                    }
                ]
            },
            "stopped playing",
            "lives in Toulouse",
        ),
    ],
)
def test_replace_remove_and_negation_apply_exact_spans(
    repository: VaultRepository, fact: str, response: object, present: str, absent: str
) -> None:
    """A03-A05: replacements and removals preserve unrelated authoritative text."""
    result = materialize(repository, unit(facts=(fact,)), FakeWriter(response))
    body = repository.read_text("people/bea.md")
    assert result.operation is PersistenceOperation.UPDATED
    assert present in body and absent not in body
    assert "Unrelated *formatting*." in body


def test_replace_and_append_apply_once(
    repository: VaultRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A06: multiple non-overlapping operations apply safely in one persistence call."""
    writer = FakeWriter(
        {
            "operations": [
                {"op": "REPLACE", "old": "Airbus", "new": "Thales"},
                {"op": "APPEND", "text": "- Bea plays piano."},
            ]
        }
    )
    calls = count_persistence(monkeypatch, repository)

    materialize(repository, unit(facts=("Bea works at Thales.", "Bea plays piano.")), writer)

    body = repository.read_text("people/bea.md")
    assert calls == [1]
    assert "Thales" in body and "plays piano" in body and "Airbus" not in body


def test_property_only_and_tag_only_updates_skip_writer(
    repository: VaultRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A07-A08: canonical properties and controlled tags mutate deterministically."""
    calls = count_persistence(monkeypatch, repository)
    result = materialize(
        repository, unit(properties=(PropertyChange("relationship_to_user", "set", "friend"),))
    )
    assert result.operation is PersistenceOperation.UPDATED and calls == [1]
    result = materialize(
        repository, unit(tags=(TagChange("add", "review"), TagChange("remove", "idea")))
    )
    assert result.operation is PersistenceOperation.UPDATED and calls == [2]
    raw = repository.read_text("people/bea.md")
    assert 'relationship_to_user: "friend"' in raw and 'tags: ["review"]' in raw


def test_structured_and_free_text_commit_together(
    repository: VaultRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A09: deterministic and writer changes result in exactly one persisted update."""
    calls = count_persistence(monkeypatch, repository)
    writer = FakeWriter({"operations": [{"op": "APPEND", "text": "- Bea plays piano."}]})

    materialize(
        repository,
        unit(
            properties=(PropertyChange("relationship_to_user", "set", "friend"),),
            facts=("Bea plays piano.",),
        ),
        writer,
    )

    raw = repository.read_text("people/bea.md")
    assert calls == [1] and 'relationship_to_user: "friend"' in raw and "plays piano" in raw


@pytest.mark.parametrize(
    "response",
    [
        {"operations": [{"op": "REPLACE", "old": "missing", "new": "new"}]},
        {
            "operations": [
                {"op": "REPLACE", "old": "Airbus", "new": "Thales"},
                {"op": "REMOVE", "old": "Airbus"},
            ]
        },
        {"operations": [{"op": "NO_CHANGE"}, {"op": "APPEND", "text": "x"}]},
        {"operations": [{"op": "APPEND", "old": None, "new": None, "text": None}]},
    ],
)
def test_invalid_writer_operations_fail_closed(
    repository: VaultRepository, monkeypatch: pytest.MonkeyPatch, response: object
) -> None:
    """A10-A13: malformed, absent, conflicting, and ambiguous output persists nothing."""
    calls = count_persistence(monkeypatch, repository)
    before = repository.read_text("people/bea.md")
    with pytest.raises(WriterOutputError):
        materialize(repository, unit(facts=("new fact",)), FakeWriter(response))
    assert calls == [0] and repository.read_text("people/bea.md") == before


def test_provider_failure_persists_nothing(
    repository: VaultRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A12: provider failures leave both structure and body untouched."""
    calls = count_persistence(monkeypatch, repository)
    before = repository.read_text("people/bea.md")
    with pytest.raises(WriterProviderError):
        materialize(
            repository,
            unit(
                properties=(PropertyChange("relationship_to_user", "set", "friend"),),
                facts=("new fact",),
            ),
            FakeWriter(WriterProviderError("offline")),
        )
    assert calls == [0] and repository.read_text("people/bea.md") == before


def test_structured_schema_failure_persists_nothing(
    repository: VaultRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Invalid deterministic structure fails before the one persistence operation."""
    calls = count_persistence(monkeypatch, repository)
    before = repository.read_text("people/bea.md")
    with pytest.raises(ValueError):
        materialize(
            repository, unit(properties=(PropertyChange("birth_date", "set", "not-a-date"),))
        )
    assert calls == [0] and repository.read_text("people/bea.md") == before


def test_writer_no_change_and_unrelated_formatting_are_preserved(
    repository: VaultRepository,
) -> None:
    """A14: a valid no-change leaves unrelated Markdown byte-for-byte unchanged."""
    before = repository.read_text("people/bea.md")
    result = materialize(
        repository,
        unit(facts=("Bea is a person.",)),
        FakeWriter({"operations": [{"op": "NO_CHANGE"}]}),
    )
    assert result.operation is PersistenceOperation.NO_CHANGE
    assert repository.read_text("people/bea.md") == before


def test_changed_target_revision_fails_closed_before_materializer_persistence(
    repository: VaultRepository,
) -> None:
    """A changed authoritative revision after loading prevents the planned update."""

    class StaleWriter:
        """Simulate an independent valid update while the writer is deciding."""

        def write(self, request: object) -> object:
            """Advance the fixture revision before returning an otherwise valid operation."""
            update_entity(
                repository,
                SCHEMA,
                path="people/bea.md",
                expected_id="person-bea",
                set_metadata={"relationship_to_user": "colleague"},
                actor="other-writer",
                now="2026-08-25T10:30:00+02:00",
            )
            return {"operations": [{"op": "APPEND", "text": "- Bea plays piano."}]}

    with pytest.raises(EntityRevisionMismatchError):
        materialize(repository, unit(facts=("Bea plays piano.",)), StaleWriter())
    raw = repository.read_text("people/bea.md")
    assert 'relationship_to_user: "colleague"' in raw and "plays piano" not in raw


def test_non_update_decision_is_rejected(repository: VaultRepository) -> None:
    """UPDATE-only materialization never allocates or creates an entity."""
    with pytest.raises(MaterializationError):
        materialize_update(
            unit(),
            WriteTargetDecision(WriteTargetOutcome.CREATE, target_type="person"),
            repository=repository,
            schema=SCHEMA,
            actor="test",
            now=NOW,
        )


def test_update_with_references_without_rendered_facts_fails_closed(
    repository: VaultRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Raw marker facts cannot reach the writer without an explicit renderer result."""
    calls = count_persistence(monkeypatch, repository)
    writer = FakeWriter({"operations": [{"op": "APPEND", "text": "must not run"}]})

    with pytest.raises(MaterializationError, match="rendered_facts"):
        materialize(
            repository,
            unit(
                facts=("Bea works with {{ref:0}}.",),
                references=(KnowledgeReference(1, "colleague", "Ada"),),
            ),
            writer,
        )

    assert writer.requests == []
    assert calls == [0]


def test_update_passes_rendered_reference_facts_to_writer(
    repository: VaultRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Prepared Core links reach the writer and are persisted in one bounded update."""
    calls = count_persistence(monkeypatch, repository)
    link = "[[products/Leche Pascual - id|Leche Pascual]]"
    writer = FakeWriter({"operations": [{"op": "APPEND", "text": f"- Bea buys {link}."}]})

    result = materialize(
        repository,
        unit(
            facts=("Bea buys {{ref:0}}.",),
            references=(KnowledgeReference(1, "product", "Leche Pascual"),),
        ),
        writer,
        rendered_facts=(f"Bea buys {link}.",),
    )

    assert result.operation is PersistenceOperation.UPDATED
    assert writer.requests[0].facts == (f"Bea buys {link}.",)
    assert link in repository.read_text("people/bea.md")
    assert calls == [1]


@pytest.mark.parametrize(
    "response",
    [
        {"operations": [{"op": "APPEND", "text": "- Bea buys milk."}]},
        {"operations": [{"op": "APPEND", "text": "- Bea buys [[other/id|Milk]]."}]},
    ],
)
def test_writer_cannot_drop_or_invent_bound_wikilinks(
    repository: VaultRepository, response: object
) -> None:
    """Reject output that drops a required link or introduces an unrelated link."""
    link = "[[products/Leche Pascual - id|Leche Pascual]]"
    with pytest.raises(WriterOutputError, match="wikilink"):
        materialize(
            repository,
            unit(
                facts=("Bea buys {{ref:0}}.",),
                references=(KnowledgeReference(1, "product", "Leche Pascual"),),
            ),
            FakeWriter(response),
            rendered_facts=(f"Bea buys {link}.",),
        )


def test_delete_intent_is_rejected_without_persistence(
    repository: VaultRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Whole-note delete remains explicitly unsupported rather than becoming NO_CHANGE."""
    calls = count_persistence(monkeypatch, repository)
    before = repository.read_text("people/bea.md")

    with pytest.raises(MaterializationError, match="delete materialization is not implemented"):
        materialize(repository, unit(intent="delete"))

    assert calls == [0]
    assert repository.read_text("people/bea.md") == before
