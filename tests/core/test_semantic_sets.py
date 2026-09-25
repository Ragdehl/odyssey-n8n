"""Deterministic Slice 1 semantic-set evidence contracts with disposable Markdown vaults."""

from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from odyssey_core.atomic_facts import render_atomic_facts
from odyssey_core.identity_boundary import SelfBindingError
from odyssey_core.notes import Note, serialize_note
from odyssey_core.relationship_evidence import RelationshipEvidenceProjector
from odyssey_core.request_planning import SemanticSetIntent
from odyssey_core.resolution import ExistingEntityOutcome
from odyssey_core.semantic_sets import (
    IdentitySetMember,
    LiteralSetMember,
    SemanticSetBounds,
    SemanticSetOutcome,
    SetEvidenceSelection,
    SetMemberOccurrence,
    enumerate_semantic_set_candidates,
    resolve_semantic_set,
    resolve_semantic_set_anchor,
    serialize_semantic_set_candidate_payload,
)
from odyssey_core.storage import VaultRepository

ROOT = Path(__file__).resolve().parents[2]
INTENT = SemanticSetIntent("self", None, "group", "", True)


def schema() -> dict:
    """Load the real canonical schema for isolated Markdown fixtures."""
    return json.loads((ROOT / "config/note-schema.json").read_text(encoding="utf-8"))


def write(vault: Path, path: str, note_id: str, name: str, body: str) -> None:
    """Write one schema-valid disposable canonical note."""
    target = vault / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        serialize_note(
            Note(
                {
                    "id": note_id,
                    "name": name,
                    "type": "person",
                    "created_at": "2026-01-01T00:00:00Z",
                    "updated_at": "2026-09-25T00:00:00Z",
                    "created_by": {"human": None, "app": "test"},
                    "updated_by": {"human": None, "app": "test"},
                    "revision": 1,
                    "schema_version": 3,
                    "aliases": [],
                    "tags": [],
                },
                body,
            )
        ),
        encoding="utf-8",
    )


def fact(text: str, ordinal: int) -> str:
    """Render one visible marker-addressable canonical fact."""
    return render_atomic_facts((text,), "semantic-set", (ordinal,), "2026-09-25")


class Select:
    """Use a deterministic candidate-text predicate as the injected selector."""

    def __init__(self, choose, *, uncertain: bool = False) -> None:
        self.choose = choose
        self.uncertain = uncertain

    def select(self, request):
        """Return the predeclared exact occurrences for supplied candidates."""
        occurrences = []
        ids = []
        for candidate in request.candidates:
            selected = self.choose(candidate)
            if selected:
                ids.append(candidate.id)
                occurrences.extend(
                    SetMemberOccurrence(candidate.id, kind, start, end)
                    for kind, start, end in selected
                )
        return SetEvidenceSelection(tuple(ids), tuple(occurrences), self.uncertain)


def run(vault: Path, selector: Select, *, bounds: SemanticSetBounds | None = None):
    """Resolve an isolated self anchor directly through the Slice 1 Core boundary."""
    return resolve_semantic_set(
        INTENT,
        anchor_id="self",
        repository=VaultRepository(vault),
        schema=schema(),
        selector=selector,
        bounds=bounds or SemanticSetBounds(),
    )


def test_multi_fact_identity_set_is_grounded_without_family_handler(tmp_path: Path) -> None:
    """Aggregate separate current facts using only supplied occurrence selections."""
    vault = tmp_path / "vault"
    vault.mkdir()
    for note_id in ("spouse", "parent-a", "parent-b", "sibling", "child-a", "child-b"):
        write(vault, f"people/{note_id}.md", note_id, note_id, "")
    write(
        vault,
        "people/self.md",
        "self",
        "Self",
        "\n\n".join(
            fact(text, ordinal)
            for ordinal, text in enumerate(
                (
                    "Mi pareja es [[spouse]].",
                    "Mis padres son [[parent-a]] y [[parent-b]].",
                    "Mi hermano es [[sibling]].",
                    "Mis hijos son [[child-a]] y [[child-b]].",
                )
            )
        ),
    )

    def links(candidate):
        return [
            ("link", match.start(), match.end())
            for match in re.finditer(r"\[\[[^]]+\]\]", candidate.text)
        ]

    result = run(vault, Select(links))
    assert result.outcome is SemanticSetOutcome.ANSWERABLE
    assert (
        result.grounded_set
        and result.grounded_set.completeness.value == "COMPLETE_WITHIN_SCANNED_SCOPE"
    )
    assert {
        member.stable_id
        for member in result.grounded_set.members
        if isinstance(member, IdentitySetMember)
    } == {"spouse", "parent-a", "parent-b", "sibling", "child-a", "child-b"}


def test_literal_and_mixed_sets_preserve_exact_text_and_identity_provenance(tmp_path: Path) -> None:
    """Keep literal pieces as text and permit one fact to yield a mixed member set."""
    vault = tmp_path / "vault"
    vault.mkdir()
    write(vault, "people/ana.md", "ana", "Ana", "")
    body = fact("El kit incluye [[ana]], tornillo M4, arandela y llave Allen.", 0)
    write(vault, "kits/basic.md", "self", "Kit", body)

    def choose(candidate):
        text = candidate.text
        selected = [("link", text.index("[[ana]]"), text.index("[[ana]]") + len("[[ana]]"))]
        selected.extend(
            ("literal", text.index(value), text.index(value) + len(value))
            for value in ("tornillo M4", "arandela", "llave Allen")
        )
        return selected

    result = run(vault, Select(choose))
    assert result.outcome is SemanticSetOutcome.ANSWERABLE
    assert result.grounded_set
    assert [
        member.value
        for member in result.grounded_set.members
        if isinstance(member, LiteralSetMember)
    ] == ["tornillo M4", "arandela", "llave Allen"]
    identity = next(
        member for member in result.grounded_set.members if isinstance(member, IdentitySetMember)
    )
    assert identity.stable_id == "ana"
    assert identity.evidence.source_note_id == "self"


def test_scope_uncertainty_no_evidence_stale_and_bound_overflow_fail_closed(tmp_path: Path) -> None:
    """Return structured outcomes without presenting partial or changed evidence as complete."""
    vault = tmp_path / "vault"
    vault.mkdir()
    write(vault, "people/ana.md", "ana", "Ana", "")
    write(
        vault,
        "people/self.md",
        "self",
        "Self",
        fact("Mi amiga es [[ana]].", 0) + "\n\n" + fact("Dato dos.", 1),
    )
    link = Select(
        lambda candidate: (
            [
                (
                    "link",
                    candidate.text.index("[[ana]]"),
                    candidate.text.index("[[ana]]") + 7,
                )
            ]
            if "[[ana]]" in candidate.text
            else []
        )
    )
    assert (
        run(vault, Select(lambda candidate: [], uncertain=True)).outcome
        is SemanticSetOutcome.AMBIGUOUS_SET_SCOPE
    )
    assert (
        run(vault, Select(lambda candidate: [])).outcome is SemanticSetOutcome.NO_RELEVANT_EVIDENCE
    )
    assert (
        run(vault, link, bounds=SemanticSetBounds(facts=1)).outcome
        is SemanticSetOutcome.INCOMPLETE_EVIDENCE
    )

    class MutatingSelect(Select):
        def select(self, request):
            write(vault, "people/self.md", "self", "Self", fact("Mi amiga es [[ana]]. Cambió.", 0))
            return super().select(request)

    assert run(vault, MutatingSelect(link.choose)).outcome is SemanticSetOutcome.STALE_EVIDENCE


def test_dangling_or_malformed_selected_identity_link_is_incomplete(tmp_path: Path) -> None:
    """Never downgrade a selected link occurrence to an unverified literal member."""
    vault = tmp_path / "vault"
    vault.mkdir()
    write(vault, "people/self.md", "self", "Self", fact("Mi amiga es [[missing]].", 0))
    result = run(
        vault,
        Select(
            lambda candidate: [
                (
                    "link",
                    candidate.text.index("[[missing]]"),
                    candidate.text.index("[[missing]]") + len("[[missing]]"),
                )
            ]
        ),
    )
    assert result.outcome is SemanticSetOutcome.INCOMPLETE_EVIDENCE


def test_candidate_enumeration_includes_only_direct_and_incoming_one_hop_facts(
    tmp_path: Path,
) -> None:
    """Do not walk a discovered linked member's neighbours into the eligible scope."""
    vault = tmp_path / "vault"
    vault.mkdir()
    write(vault, "people/self.md", "self", "Self", fact("Direct fact.", 0))
    write(vault, "people/source.md", "source", "Source", fact("Source links [[self]].", 0))
    write(vault, "people/member.md", "member", "Member", fact("Member links [[source]].", 0))
    projector = RelationshipEvidenceProjector(VaultRepository(vault), schema())
    candidates = enumerate_semantic_set_candidates(projector, "self", bounds=SemanticSetBounds())
    assert isinstance(candidates, tuple)
    assert {candidate.fact.source.id for candidate in candidates} == {"self", "source"}


def test_selector_payload_contains_only_opaque_candidates_and_visible_text(tmp_path: Path) -> None:
    """Measure the bounded model-facing payload without leaking source identity or fact locators."""
    vault = tmp_path / "vault"
    vault.mkdir()
    write(vault, "people/self.md", "self", "Self", fact("El kit incluye arandela.", 0))
    candidates = enumerate_semantic_set_candidates(
        RelationshipEvidenceProjector(VaultRepository(vault), schema()),
        "self",
        bounds=SemanticSetBounds(),
    )
    assert isinstance(candidates, tuple)
    payload = json.loads(serialize_semantic_set_candidate_payload(INTENT, candidates))
    assert payload["candidates"] == [{"id": "candidate-0", "text": "El kit incluye arandela."}]
    assert len(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()) < 512


def test_ambiguous_existing_anchor_returns_ambiguous_reference() -> None:
    """Leave two equally valid existing anchors unresolved for the later clarification slice."""
    intent = SemanticSetIntent("existing", "Marta", "familia", "", False)
    outcome, anchor_id = resolve_semantic_set_anchor(
        intent,
        authenticated_actor=None,
        self_binding_repository=None,
        existing_resolver=lambda _query: SimpleNamespace(
            outcome=ExistingEntityOutcome.AMBIGUOUS, id=None
        ),
    )
    assert outcome is SemanticSetOutcome.AMBIGUOUS_REFERENCE
    assert anchor_id is None


def test_self_anchor_binding_returns_the_bound_identity_or_fails_closed() -> None:
    """Use only the existing self-binding authority for a first-person semantic anchor."""
    binding = SimpleNamespace(resolve=lambda _user_id: SimpleNamespace(person_note_id="self"))
    outcome, anchor_id = resolve_semantic_set_anchor(
        INTENT,
        authenticated_actor=SimpleNamespace(stable_user_id="actor"),
        self_binding_repository=binding,
        existing_resolver=lambda _query: pytest.fail("self anchor must not resolve by name"),
    )
    assert (outcome, anchor_id) == (SemanticSetOutcome.ANSWERABLE, "self")

    def unavailable(_user_id: str) -> None:
        raise SelfBindingError("missing binding")

    outcome, anchor_id = resolve_semantic_set_anchor(
        INTENT,
        authenticated_actor=SimpleNamespace(stable_user_id="actor"),
        self_binding_repository=SimpleNamespace(resolve=unavailable),
        existing_resolver=lambda _query: pytest.fail("self anchor must not resolve by name"),
    )
    assert (outcome, anchor_id) == (SemanticSetOutcome.AMBIGUOUS_REFERENCE, None)


@pytest.mark.parametrize(
    ("selection", "bounds"),
    [
        (
            SetEvidenceSelection(("unknown",), (SetMemberOccurrence("unknown", "literal", 0, 1),)),
            SemanticSetBounds(),
        ),
        (SetEvidenceSelection(("candidate-0", "candidate-0"), ()), SemanticSetBounds()),
        (
            SetEvidenceSelection(
                ("candidate-0",), (SetMemberOccurrence("candidate-0", "literal", 0, 999),)
            ),
            SemanticSetBounds(),
        ),
        (
            SetEvidenceSelection(
                ("candidate-0",),
                (
                    SetMemberOccurrence("candidate-0", "literal", 0, 3),
                    SetMemberOccurrence("candidate-0", "literal", 1, 4),
                ),
            ),
            SemanticSetBounds(),
        ),
        (
            SetEvidenceSelection(
                ("candidate-0",), (SetMemberOccurrence("candidate-0", "link", 0, 3),)
            ),
            SemanticSetBounds(),
        ),
        (
            SetEvidenceSelection(
                ("candidate-0",), (SetMemberOccurrence("candidate-0", "literal", 0, 1),)
            ),
            SemanticSetBounds(members=0),
        ),
    ],
)
def test_invalid_selector_evidence_never_escapes_candidate_boundaries(
    tmp_path: Path, selection: SetEvidenceSelection, bounds: SemanticSetBounds
) -> None:
    """Reject malformed, duplicate, out-of-fact, overlapping, and oversized proposals."""
    vault = tmp_path / "vault"
    vault.mkdir()
    write(vault, "people/self.md", "self", "Self", fact("Elemento visible.", 0))
    selector = SimpleNamespace(select=lambda _request: selection)

    result = resolve_semantic_set(
        INTENT,
        anchor_id="self",
        repository=VaultRepository(vault),
        schema=schema(),
        selector=selector,
        bounds=bounds,
    )

    assert result.outcome is SemanticSetOutcome.OPERATIONAL_FAILURE
    assert result.reason == "invalid_selection"


def test_whitespace_literal_is_not_grounded_as_a_set_member(tmp_path: Path) -> None:
    """Reject a selected whitespace-only literal after canonical re-grounding."""
    vault = tmp_path / "vault"
    vault.mkdir()
    write(vault, "people/self.md", "self", "Self", fact("Kit: tornillo.", 0))
    result = run(
        vault,
        Select(
            lambda candidate: [
                ("literal", candidate.text.index(" "), candidate.text.index(" ") + 1)
            ]
        ),
    )

    assert result.outcome is SemanticSetOutcome.INCOMPLETE_EVIDENCE
    assert result.reason == "empty_literal"
