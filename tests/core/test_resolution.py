"""Focused deterministic tests for the Phase 11B.2 production resolver."""

from __future__ import annotations

import inspect
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from odyssey_core.contextual import ContextualProviderError, ContextualResolutionError
from odyssey_core.identity import ExactEntityLookupError
from odyssey_core.notes import Note, serialize_note
from odyssey_core.resolution import (
    ExistingEntityOutcome,
    ResolutionSource,
    build_provider_evidence,
    resolve_existing_entity,
)
from odyssey_core.semantic import SemanticEntityCandidate
from odyssey_core.storage import VaultRepository

ROOT = Path(__file__).resolve().parents[2]


class FakeEmbedder:
    """Satisfy the semantic protocol without loading a model."""

    model_name = "tests/fake"
    model_version = "1"

    def embed_queries(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        """Return a stable vector for the fake semantic index."""
        return [[1.0] for _ in texts]


class FakeIndex:
    """Return predetermined retrieval candidates while preserving the Phase 10 call shape."""

    def __init__(self, candidates: tuple[SemanticEntityCandidate, ...] = ()) -> None:
        self.candidates = candidates
        self.calls = 0

    def find_candidates(
        self, embedder: object, reference: str, **kwargs: object
    ) -> tuple[SemanticEntityCandidate, ...]:
        """Return configured candidates and record one local retrieval invocation."""
        self.calls += 1
        return self.candidates[: int(kwargs["limit"])]


class FakeReasoner:
    """Return one deterministic provider-like decision and retain requests for assertions."""

    def __init__(self, output: object, usage: dict[str, Any] | None = None) -> None:
        self.output = output
        self.usage = usage or {"output_tokens": 3}
        self.requests = []

    def resolve(self, request: object) -> tuple[object, dict[str, Any]]:
        """Return the configured raw output exactly once per orchestration call."""
        self.requests.append(request)
        return self.output, self.usage  # type: ignore[return-value]


@pytest.fixture
def schema() -> dict[str, Any]:
    """Load the canonical note schema used by production validation."""
    return json.loads((ROOT / "config/note-schema.json").read_text(encoding="utf-8"))


def valid_note(note_id: str, note_type: str, content: str, **metadata: object) -> Note:
    """Create one valid note fixture with the schema's required lifecycle fields."""
    values = {
        "id": note_id,
        "type": note_type,
        "created_at": "2026-08-16T12:00:00Z",
        "updated_at": "2026-08-16T12:00:00Z",
        "created_by": "pytest",
        "updated_by": "pytest",
        "revision": 1,
        "schema_version": 1,
        **metadata,
    }
    return Note(metadata=values, content=content)  # type: ignore[arg-type]


def write_note(vault: Path, path: str, note: Note) -> None:
    """Write one controlled canonical Markdown fixture."""
    target = vault / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(serialize_note(note), encoding="utf-8")


def candidate(note_id: str, path: str, name: str) -> SemanticEntityCandidate:
    """Build one retrieval-only candidate fixture without exposing its score downstream."""
    return SemanticEntityCandidate(note_id, path, "person", name, 0.99)


def run_resolution(
    vault: Path,
    schema: dict[str, Any],
    reference: str,
    index: FakeIndex,
    reasoner: object,
    *,
    context: str = "",
    type: str | None = "person",
    semantic_limit: int,
) -> object:
    """Invoke the production boundary with the fixture dependencies."""
    return resolve_existing_entity(
        reference,
        context,
        type=type,
        repository=VaultRepository(vault),
        schema=schema,
        semantic_index=index,  # type: ignore[arg-type]
        embedder=FakeEmbedder(),  # type: ignore[arg-type]
        contextual_reasoner=reasoner,  # type: ignore[arg-type]
        semantic_limit=semantic_limit,
    )


def test_exact_unique_short_circuits_without_contextual_call(
    tmp_path: Path, schema: dict[str, Any]
) -> None:
    """Resolve one exact primary name locally and never invoke the provider."""
    write_note(tmp_path, "people/Ada.md", valid_note("ada", "person", "Engineer."))
    reasoner = FakeReasoner({"outcome": "RESOLVED", "id": "ada"})
    result = run_resolution(tmp_path, schema, "Ada", FakeIndex(), reasoner, semantic_limit=5)
    assert result.outcome is ExistingEntityOutcome.RESOLVED
    assert result.id == "ada"
    assert result.source is ResolutionSource.EXACT_LOCAL
    assert result.candidate_ids == ()
    assert reasoner.requests == []


def test_semantic_limit_is_an_explicit_required_orchestration_choice() -> None:
    """Prevent a retrieval-count default from becoming an implicit production policy."""
    parameter = inspect.signature(resolve_existing_entity).parameters["semantic_limit"]
    assert parameter.default is inspect.Parameter.empty


def test_exact_absent_uses_one_contextual_call(tmp_path: Path, schema: dict[str, Any]) -> None:
    """Pass validated semantic evidence through one contextual decision."""
    write_note(tmp_path, "people/Ada.md", valid_note("ada", "person", "Engineer."))
    index = FakeIndex((candidate("ada", "people/Ada.md", "Ada"),))
    reasoner = FakeReasoner({"outcome": "RESOLVED", "id": "ada"})
    result = run_resolution(
        tmp_path, schema, "the engineer", index, reasoner, context="At work", semantic_limit=5
    )
    assert result.id == "ada"
    assert result.source is ResolutionSource.CONTEXTUAL
    assert len(reasoner.requests) == 1
    assert result.candidate_ids == ("ada",)


def test_ambiguous_exact_candidates_are_never_dropped_by_semantic_top_n(
    tmp_path: Path, schema: dict[str, Any]
) -> None:
    """Keep every exact alias collision even when retrieval returns only one collision."""
    write_note(
        tmp_path,
        "people/Ada One.md",
        valid_note("ada-one", "person", "Colleague.", aliases=["Ada"]),
    )
    write_note(
        tmp_path, "people/Ada Two.md", valid_note("ada-two", "person", "Neighbor.", aliases=["Ada"])
    )
    index = FakeIndex((candidate("ada-one", "people/Ada One.md", "Ada One"),))
    reasoner = FakeReasoner({"outcome": "AMBIGUOUS", "id": None})
    result = run_resolution(tmp_path, schema, "Ada", index, reasoner, semantic_limit=5)
    request = reasoner.requests[0]
    assert result.outcome is ExistingEntityOutcome.AMBIGUOUS
    assert result.candidate_ids == ("ada-one", "ada-two")
    assert [item.id for item in request.candidates] == ["ada-one", "ada-two"]


def test_no_semantic_candidates_is_local_unresolved(tmp_path: Path, schema: dict[str, Any]) -> None:
    """Return a legitimate local abstention without making a provider call."""
    reasoner = FakeReasoner({"outcome": "RESOLVED", "id": "never"})
    result = run_resolution(tmp_path, schema, "missing", FakeIndex(), reasoner, semantic_limit=5)
    assert result.outcome is ExistingEntityOutcome.UNRESOLVED
    assert result.id is None
    assert result.source is ResolutionSource.LOCAL_NO_CANDIDATES
    assert result.candidate_ids == ()
    assert reasoner.requests == []


def test_usage_metadata_has_a_strict_operational_allowlist(
    tmp_path: Path, schema: dict[str, Any]
) -> None:
    """Retain known counters while dropping arbitrary provider content and credentials."""
    write_note(tmp_path, "people/Ada.md", valid_note("ada", "person", "Engineer."))
    index = FakeIndex((candidate("ada", "people/Ada.md", "Ada"),))
    reasoner = FakeReasoner(
        {"outcome": "RESOLVED", "id": "ada"},
        {
            "response_id": "resp-1",
            "input_tokens": 1000,
            "cached_input_tokens": 10,
            "cache_write_tokens": 20,
            "output_tokens": 30,
            "reasoning_tokens": 5,
            "prompt": "private content",
            "response_text": "private content",
            "authorization": "Bearer secret",
            "candidate_evidence": "private content",
        },
    )

    result = run_resolution(tmp_path, schema, "unknown", index, reasoner, semantic_limit=5)

    assert result.usage == {
        "response_id": "resp-1",
        "input_tokens": 1000,
        "cached_input_tokens": 10,
        "cache_write_tokens": 20,
        "output_tokens": 30,
        "reasoning_tokens": 5,
    }


@pytest.mark.parametrize(
    "output",
    [
        {"outcome": "MAYBE", "id": None},
        {"outcome": "RESOLVED", "id": "outside"},
        {"outcome": "AMBIGUOUS", "id": "candidate"},
    ],
)
def test_invalid_contextual_output_fails_closed(
    tmp_path: Path, schema: dict[str, Any], output: object
) -> None:
    """Reject malformed or unsafe provider decisions rather than inventing a result."""
    write_note(tmp_path, "people/Ada.md", valid_note("ada", "person", "Engineer."))
    index = FakeIndex((candidate("ada", "people/Ada.md", "Ada"),))
    with pytest.raises(ContextualResolutionError):
        run_resolution(tmp_path, schema, "unknown", index, FakeReasoner(output), semantic_limit=5)


def test_provider_failure_is_not_converted_to_unresolved(
    tmp_path: Path, schema: dict[str, Any]
) -> None:
    """Propagate provider failures and perform no implicit retry."""
    write_note(tmp_path, "people/Ada.md", valid_note("ada", "person", "Engineer."))
    index = FakeIndex((candidate("ada", "people/Ada.md", "Ada"),))

    class FailingReasoner:
        """Raise one transport-like failure for the orchestration test."""

        calls = 0

        def resolve(self, request: object) -> tuple[dict[str, Any], dict[str, Any]]:
            """Raise without exposing request contents."""
            self.calls += 1
            raise ContextualProviderError("provider unavailable")

    reasoner = FailingReasoner()
    with pytest.raises(ContextualProviderError):
        run_resolution(tmp_path, schema, "unknown", index, reasoner, semantic_limit=5)
    assert reasoner.calls == 1


def test_provider_evidence_is_deterministic_and_minimized(schema: dict[str, Any]) -> None:
    """Retain identity evidence while removing lifecycle and retrieval-only information."""
    note = valid_note(
        "ada",
        "person",
        "Links: [[people/Xavi]], [[people/Xavi|mi amigo]], [[people/Xavi#Section]], "
        "[[people/Xavi#Section|mi amigo]], and [[Xavi]].",
        aliases=["A. Lovelace"],
        relationship_to_user="colleague",
    )
    first = build_provider_evidence(note, "people/Ada Lovelace.md")
    second = build_provider_evidence(note, "people/Ada Lovelace.md")
    assert first == second
    assert all(
        field not in first for field in ("created_at", "updated_at", "revision", "schema_version")
    )
    assert (
        "0.99" not in first and "rank" not in first.casefold() and "score" not in first.casefold()
    )
    assert "Name: Ada Lovelace" in first
    assert "Aliases: A. Lovelace" in first
    assert "Relationship To User: colleague" in first
    assert "Xavi" in first and "[[" not in first
    assert "people/" not in first
    assert "Section" not in first
    assert "mi amigo" in first


def test_provider_evidence_excludes_controlled_tags(schema: dict[str, Any]) -> None:
    """Keep classification facets outside contextual identity evidence."""
    note = valid_note("ada", "person", "Known colleague.", tags=["review", "reference"])
    evidence = build_provider_evidence(note, "people/Ada Lovelace.md")
    assert "Tags" not in evidence
    assert "review" not in evidence
    assert "reference" not in evidence


def test_invalid_candidate_note_is_rejected_before_provider_evidence(
    tmp_path: Path, schema: dict[str, Any]
) -> None:
    """Fail safely before the reasoner sees a malformed semantic candidate note."""
    (tmp_path / "people").mkdir()
    (tmp_path / "people/Ada.md").write_text("---\nid: ada\ntype: person\n---\n", encoding="utf-8")
    index = FakeIndex((candidate("ada", "people/Ada.md", "Ada"),))
    reasoner = FakeReasoner({"outcome": "RESOLVED", "id": "ada"})
    with pytest.raises(ExactEntityLookupError):
        run_resolution(tmp_path, schema, "unknown", index, reasoner, semantic_limit=5)
    assert reasoner.requests == []
