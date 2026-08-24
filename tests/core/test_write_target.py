"""Deterministic Phase 16.1 target-decision contract coverage."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

import pytest

from odyssey_core.context import ContextFilter
from odyssey_core.notes import Note, serialize_note
from odyssey_core.request_planning import KnowledgeUnit, SelectionCriteria
from odyssey_core.semantic import SemanticEntityCandidate
from odyssey_core.storage import VaultRepository
from odyssey_core.write_target import WriteTargetOutcome, decide_write_target

ROOT = Path(__file__).resolve().parents[2]


class FakeEmbedder:
    """Satisfy the resolver embedding protocol without loading a model."""

    model_name = "tests/fake"
    model_version = "1"

    def embed_queries(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        """Return stable vectors for the configured test index."""
        return [[1.0] for _ in texts]


class FakeIndex:
    """Return fixed semantic candidates through the established Phase 10 shape."""

    def __init__(self, candidates: tuple[SemanticEntityCandidate, ...] = ()) -> None:
        """Store the candidates exposed to the existing resolver."""
        self.candidates = candidates

    def find_candidates(self, embedder: object, reference: str, **kwargs: object):
        """Return configured candidates up to the resolver's explicit limit."""
        return self.candidates[: int(kwargs["limit"])]


class FakeReasoner:
    """Provide one injected deterministic Phase 11 contextual decision."""

    def __init__(self, output: object = {"outcome": "UNRESOLVED", "id": None}) -> None:
        """Store the raw decision and count calls for boundary assertions."""
        self.output = output
        self.calls = 0

    def resolve(self, request: object):
        """Return the configured decision without contacting a provider."""
        self.calls += 1
        return self.output, {"output_tokens": 1}


@pytest.fixture
def schema() -> dict:
    """Load the current canonical schema for valid synthetic notes."""
    return json.loads((ROOT / "config/note-schema.json").read_text(encoding="utf-8"))


def note(note_id: str, note_type: str, **metadata: object) -> Note:
    """Build one complete valid synthetic note."""
    return Note(
        {
            "id": note_id,
            "type": note_type,
            "created_at": "2026-08-24T12:00:00Z",
            "updated_at": "2026-08-24T12:00:00Z",
            "created_by": "pytest",
            "updated_by": "pytest",
            "revision": 1,
            "schema_version": 1,
            **metadata,
        },
        "Synthetic knowledge.",
    )  # type: ignore[arg-type]


def write_note(vault: Path, path: str, value: Note) -> None:
    """Persist a disposable fixture note in the temporary vault."""
    target = vault / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(serialize_note(value), encoding="utf-8")


def unit(
    query: str,
    *,
    entity: str | None = None,
    note_type: str | None = "person",
    intent: str = "record",
    filters: tuple[ContextFilter, ...] = (),
) -> KnowledgeUnit:
    """Build a prevalidated-shape write unit without any mutation execution payload."""
    return KnowledgeUnit(
        SelectionCriteria(entity, query, note_type, filters, None), intent, (), (), ("fact",), ()
    )


def decide(
    vault: Path,
    schema: dict,
    value: KnowledgeUnit,
    index: FakeIndex | None = None,
    reasoner: FakeReasoner | None = None,
):
    """Invoke the Phase 16.1 boundary with only synthetic local dependencies."""
    return decide_write_target(
        value,
        repository=VaultRepository(vault),
        schema=schema,
        semantic_index=index or FakeIndex(),  # type: ignore[arg-type]
        embedder=FakeEmbedder(),  # type: ignore[arg-type]
        contextual_reasoner=reasoner or FakeReasoner(),  # type: ignore[arg-type]
        semantic_limit=5,
    )


def test_e01_existing_nominal_entity_updates_without_provider(tmp_path: Path, schema: dict) -> None:
    """E01 selects a unique exact person for later update only."""
    write_note(tmp_path, "people/Marta.md", note("marta", "person"))
    reasoner = FakeReasoner()
    result = decide(
        tmp_path, schema, unit("Marta lives in Lyon", entity="Marta"), reasoner=reasoner
    )
    assert result.outcome is WriteTargetOutcome.UPDATE
    assert result.existing_note_id == "marta"
    assert result.target_type is None
    assert reasoner.calls == 0


@pytest.mark.parametrize(
    "query,entity", [("Marta lives in Lyon", "Marta"), ("la amiga de Marta", None)]
)
def test_e02_e03_unresolved_record_with_canonical_type_creates(
    tmp_path: Path, schema: dict, query: str, entity: str | None
) -> None:
    """E02/E03 authorize generic named and unnamed logical entity creation."""
    result = decide(tmp_path, schema, unit(query, entity=entity))
    assert result.outcome is WriteTargetOutcome.CREATE
    assert result.existing_note_id is None
    assert result.target_type == "person"


def test_e04_contextual_identity_resolves_through_existing_stack(
    tmp_path: Path, schema: dict
) -> None:
    """E04 maps an existing contextual decision to later update authorization."""
    write_note(tmp_path, "people/Marta friend.md", note("friend", "person"))
    index = FakeIndex(
        (
            SemanticEntityCandidate(
                "friend", "people/Marta friend.md", "person", "Marta friend", 1.0
            ),
        )
    )
    result = decide(
        tmp_path,
        schema,
        unit("la amiga de Marta", entity=None),
        index,
        FakeReasoner({"outcome": "RESOLVED", "id": "friend"}),
    )
    assert result.outcome is WriteTargetOutcome.UPDATE
    assert result.existing_note_id == "friend"


def test_e05_e11_ambiguity_never_creates(tmp_path: Path, schema: dict) -> None:
    """E05/E11 leave cross- and same-type exact collisions for clarification."""
    write_note(tmp_path, "people/Marta García.md", note("garcia", "person", aliases=["Marta"]))
    write_note(tmp_path, "people/Marta López.md", note("lopez", "person", aliases=["Marta"]))
    result = decide(
        tmp_path,
        schema,
        unit("Marta", entity="Marta"),
        reasoner=FakeReasoner({"outcome": "UNRESOLVED", "id": None}),
    )
    assert result.outcome is WriteTargetOutcome.NEEDS_CLARIFICATION
    assert result.reason == "ambiguous_existing_target"


@pytest.mark.parametrize("intent", ["amend", "remove", "delete"])
def test_e06_e08_unresolved_non_record_never_creates(
    tmp_path: Path, schema: dict, intent: str
) -> None:
    """E06-E08 require clarification for every unresolved non-record intent."""
    result = decide(tmp_path, schema, unit("Marta", entity="Marta", intent=intent))
    assert result.outcome is WriteTargetOutcome.NEEDS_CLARIFICATION


def test_e09_null_type_never_creates(tmp_path: Path, schema: dict) -> None:
    """E09 refuses an unresolved record whose planner did not select a type."""
    assert (
        decide(tmp_path, schema, unit("something", note_type=None)).outcome
        is WriteTargetOutcome.NEEDS_CLARIFICATION
    )


def test_e10_type_narrows_same_name_across_canonical_types(tmp_path: Path, schema: dict) -> None:
    """E10 applies the planner's canonical type as exact identity narrowing."""
    write_note(tmp_path, "people/Marta.md", note("person-marta", "person"))
    write_note(tmp_path, "projects/Marta.md", note("project-marta", "project"))
    result = decide(tmp_path, schema, unit("Marta", entity="Marta", note_type="project"))
    assert result.outcome is WriteTargetOutcome.UPDATE
    assert result.existing_note_id == "project-marta"


def test_e12_existing_delete_selects_only(tmp_path: Path, schema: dict) -> None:
    """E12 selects an existing delete target without deleting or changing its file."""
    path = "people/Marta.md"
    write_note(tmp_path, path, note("marta", "person"))
    before = (tmp_path / path).read_text(encoding="utf-8")
    result = decide(tmp_path, schema, unit("Marta", entity="Marta", intent="delete"))
    assert result.outcome is WriteTargetOutcome.UPDATE
    assert (tmp_path / path).read_text(encoding="utf-8") == before


def test_unfiltered_target_skips_filter_id_scan(
    tmp_path: Path, schema: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Leave unfiltered candidate selection entirely to the existing resolver."""

    def fail_if_called(*args: object, **kwargs: object) -> frozenset[str]:
        raise AssertionError("unfiltered target invoked the filter-ID scan")

    monkeypatch.setattr("odyssey_core.write_target.find_filtered_note_ids", fail_if_called)

    result = decide(tmp_path, schema, unit("Marta"))

    assert result.outcome is WriteTargetOutcome.CREATE
    assert result.target_type == "person"


def test_filters_narrow_exact_candidates_without_similarity_approximation(
    tmp_path: Path, schema: dict
) -> None:
    """Use validated target filters to restrict exact candidates before selection."""
    write_note(
        tmp_path,
        "people/Marta one.md",
        note("one", "person", aliases=["Marta"], relationship_to_user="friend"),
    )
    write_note(
        tmp_path,
        "people/Marta two.md",
        note("two", "person", aliases=["Marta"], relationship_to_user="colleague"),
    )
    result = decide(
        tmp_path,
        schema,
        unit(
            "Marta",
            entity="Marta",
            filters=(ContextFilter("relationship_to_user", "eq", "colleague"),),
        ),
    )
    assert result.outcome is WriteTargetOutcome.UPDATE
    assert result.existing_note_id == "two"


def test_invalid_input_fails_closed_without_allocating_or_persisting(
    tmp_path: Path, schema: dict
) -> None:
    """Reject an invalid target type with no selected identity or materialization side effect."""
    result = decide(tmp_path, schema, unit("Marta", entity="Marta", note_type="unknown"))
    assert result.outcome is WriteTargetOutcome.NEEDS_CLARIFICATION
    assert result.existing_note_id is None
    assert result.target_type is None
    assert list(tmp_path.rglob("*.md")) == []
