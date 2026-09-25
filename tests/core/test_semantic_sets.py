"""Deterministic fact-grounding coverage for subject-independent semantic sets."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from odyssey_core.atomic_facts import render_atomic_facts
from odyssey_core.notes import Note, serialize_note
from odyssey_core.relationship_evidence import RelationshipEvidenceProjector
from odyssey_core.request_planning import SemanticSetIntent
from odyssey_core.semantic_sets import (
    IdentitySetMember,
    LiteralSetMember,
    SemanticSetBounds,
    SemanticSetOutcome,
    SetEvidenceSelection,
    SetMemberOccurrence,
    enumerate_semantic_set_candidates,
    resolve_semantic_set,
    serialize_semantic_set_candidate_payload,
)
from odyssey_core.storage import VaultRepository

ROOT = Path(__file__).resolve().parents[2]
INTENT = SemanticSetIntent("query", "kit básico para la bici", "piezas", "", True)


def schema() -> dict:
    """Load the active schema for disposable canonical Markdown fixtures."""
    return json.loads((ROOT / "config/note-schema.json").read_text(encoding="utf-8"))


def write(vault: Path, path: str, note_id: str, name: str, body: str) -> None:
    """Write one schema-valid temporary canonical Note without creating subject Notes."""
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
    """Render one marker-addressable visible fact."""
    return render_atomic_facts((text,), "semantic-set", (ordinal,), "2026-09-25")


class Select:
    """Choose deterministic exact occurrences after receiving candidate fact text."""

    def __init__(self, choose, *, uncertain: bool = False) -> None:
        self.choose, self.uncertain = choose, uncertain

    def select(self, request):
        """Return supplied IDs and exact spans only for selected candidate facts."""
        selected, occurrences = [], []
        for candidate in request.candidates:
            choices = self.choose(candidate)
            if choices:
                selected.append(candidate.id)
                occurrences.extend(
                    SetMemberOccurrence(candidate.id, kind, start, end)
                    for kind, start, end in choices
                )
        return SetEvidenceSelection(tuple(selected), tuple(occurrences), self.uncertain)


def run(vault: Path, selector: Select, *, bounds: SemanticSetBounds | None = None, intent=INTENT):
    """Resolve one set from the full bounded canonical fact scope."""
    return resolve_semantic_set(
        intent,
        repository=VaultRepository(vault),
        schema=schema(),
        selector=selector,
        bounds=bounds or SemanticSetBounds(),
    )


def test_text_only_subject_allows_paraphrase_but_grounds_exact_literal_spans(
    tmp_path: Path,
) -> None:
    """A semantic subject need not be a Note, while selected evidence spans remain exact."""
    vault = tmp_path / "vault"
    vault.mkdir()
    wording = "El pequeño kit de reparación contiene desmontables, parches y una llave Allen."
    write(vault, "projects/bike.md", "bike-project", "Proyecto bicicleta", fact(wording, 0))
    result = run(
        vault,
        Select(
            lambda candidate: [
                ("literal", candidate.text.index(value), candidate.text.index(value) + len(value))
                for value in ("desmontables", "parches", "llave Allen")
            ]
        ),
    )
    assert result.outcome is SemanticSetOutcome.ANSWERABLE
    assert result.grounded_set and result.grounded_set.subject_query == "kit básico para la bici"
    literals = [
        member for member in result.grounded_set.members if isinstance(member, LiteralSetMember)
    ]
    assert [member.value for member in literals] == ["desmontables", "parches", "llave Allen"]
    assert {member.evidence.source_note_id for member in literals} == {"bike-project"}
    assert not (vault / "kits").exists()


def test_text_only_subject_can_select_facts_from_multiple_source_notes(tmp_path: Path) -> None:
    """A textual container can draw exact members from distinct fact provenance sources."""
    vault = tmp_path / "vault"
    vault.mkdir()
    write(
        vault,
        "projects/tools.md",
        "tools",
        "Proyecto",
        fact("Guardé en la caja roja el taladro.", 0),
    )
    write(
        vault,
        "places/garage.md",
        "garage",
        "Garaje",
        fact("Las brocas de madera están también en esa caja roja del garaje.", 0),
    )
    intent = SemanticSetIntent("query", "la caja roja", "objetos guardados", "", True)
    result = run(
        vault,
        Select(
            lambda candidate: [
                ("literal", candidate.text.index(value), candidate.text.index(value) + len(value))
                for value in ("taladro", "brocas de madera")
                if value in candidate.text
            ]
        ),
        intent=intent,
    )
    assert result.outcome is SemanticSetOutcome.ANSWERABLE
    assert result.grounded_set
    literals = [
        member for member in result.grounded_set.members if isinstance(member, LiteralSetMember)
    ]
    assert {member.value for member in literals} == {"taladro", "brocas de madera"}
    assert {member.evidence.source_note_id for member in literals} == {"tools", "garage"}
    assert not (vault / "boxes").exists()


def test_identity_mixed_and_unselected_facts_preserve_only_exact_selected_evidence(
    tmp_path: Path,
) -> None:
    """Keep links as identities, literals as literals, and never include merely overlapping facts."""
    vault = tmp_path / "vault"
    vault.mkdir()
    write(vault, "people/ana.md", "ana", "Ana", "")
    write(
        vault, "people/self.md", "self", "Self", fact("Mi familia incluye [[ana]] y el perro.", 0)
    )
    write(
        vault,
        "notes/noise.md",
        "noise",
        "Ruido",
        fact("La familia de la novela incluye un taladro.", 0),
    )
    result = run(
        vault,
        Select(
            lambda candidate: (
                [
                    ("link", candidate.text.index("[[ana]]"), candidate.text.index("[[ana]]") + 7),
                    ("literal", candidate.text.index("perro"), candidate.text.index("perro") + 5),
                ]
                if "[[ana]]" in candidate.text
                else []
            )
        ),
        intent=SemanticSetIntent("self", None, "personas y animales de mi familia", "", True),
    )
    assert result.outcome is SemanticSetOutcome.ANSWERABLE
    assert result.grounded_set
    assert [
        m.stable_id for m in result.grounded_set.members if isinstance(m, IdentitySetMember)
    ] == ["ana"]
    assert [m.value for m in result.grounded_set.members if isinstance(m, LiteralSetMember)] == [
        "perro"
    ]


def test_scope_uncertainty_no_evidence_stale_and_overflow_fail_closed(tmp_path: Path) -> None:
    """Keep ambiguity, empty selection, stale sources, and complete-scan bounds explicit."""
    vault = tmp_path / "vault"
    vault.mkdir()
    write(vault, "projects/bike.md", "bike", "Bike", fact("El kit contiene parches.", 0))
    assert (
        run(vault, Select(lambda _candidate: [], uncertain=True)).outcome
        is SemanticSetOutcome.AMBIGUOUS_SET_SCOPE
    )
    assert (
        run(vault, Select(lambda _candidate: [])).outcome is SemanticSetOutcome.NO_RELEVANT_EVIDENCE
    )
    assert (
        run(vault, Select(lambda _candidate: []), bounds=SemanticSetBounds(facts=0)).outcome
        is SemanticSetOutcome.INCOMPLETE_EVIDENCE
    )

    class MutatingSelect(Select):
        def select(self, request):
            write(
                vault,
                "projects/bike.md",
                "bike",
                "Bike",
                fact("El kit contiene parches nuevos.", 0),
            )
            return super().select(request)

    assert (
        run(
            vault,
            MutatingSelect(
                lambda candidate: [
                    (
                        "literal",
                        candidate.text.index("parches"),
                        candidate.text.index("parches") + 7,
                    )
                ]
            ),
        ).outcome
        is SemanticSetOutcome.STALE_EVIDENCE
    )


@pytest.mark.parametrize(
    "selection",
    [
        SetEvidenceSelection(("unknown",), (SetMemberOccurrence("unknown", "literal", 0, 1),)),
        SetEvidenceSelection(("candidate-0", "candidate-0"), ()),
        SetEvidenceSelection(
            ("candidate-0",), (SetMemberOccurrence("candidate-0", "literal", 0, 999),)
        ),
        SetEvidenceSelection(
            ("candidate-0",),
            (
                SetMemberOccurrence("candidate-0", "literal", 0, 4),
                SetMemberOccurrence("candidate-0", "literal", 3, 6),
            ),
        ),
        SetEvidenceSelection(("candidate-0",), (SetMemberOccurrence("candidate-0", "link", 0, 3),)),
    ],
)
def test_invalid_selector_output_and_dangling_identity_fail_closed(
    tmp_path: Path, selection: SetEvidenceSelection
) -> None:
    """Reject untrusted selection data and never promote a dangling link to identity."""
    vault = tmp_path / "vault"
    vault.mkdir()
    write(vault, "notes/source.md", "source", "Source", fact("Elemento visible [[missing]].", 0))
    invalid = resolve_semantic_set(
        INTENT,
        repository=VaultRepository(vault),
        schema=schema(),
        selector=SimpleNamespace(select=lambda _request: selection),
    )
    assert invalid.outcome is SemanticSetOutcome.OPERATIONAL_FAILURE
    dangling = run(
        vault,
        Select(
            lambda candidate: [
                (
                    "link",
                    candidate.text.index("[[missing]]"),
                    candidate.text.index("[[missing]]") + 11,
                )
            ]
        ),
    )
    assert dangling.outcome is SemanticSetOutcome.INCOMPLETE_EVIDENCE


def test_literal_whitespace_and_member_overflow_do_not_make_grounded_members(
    tmp_path: Path,
) -> None:
    """Reject empty literal evidence and selector output that exceeds the member ceiling."""
    vault = tmp_path / "vault"
    vault.mkdir()
    write(vault, "notes/source.md", "source", "Source", fact("Pieza visible.", 0))
    whitespace = run(
        vault,
        Select(
            lambda candidate: [
                ("literal", candidate.text.index(" "), candidate.text.index(" ") + 1)
            ]
        ),
    )
    assert whitespace.outcome is SemanticSetOutcome.INCOMPLETE_EVIDENCE
    overflow = run(
        vault,
        Select(
            lambda candidate: [
                ("literal", candidate.text.index("Pieza"), candidate.text.index("Pieza") + 5)
            ]
        ),
        bounds=SemanticSetBounds(members=0),
    )
    assert overflow.outcome is SemanticSetOutcome.OPERATIONAL_FAILURE


def test_candidate_payload_exposes_text_not_source_identity_and_scans_all_facts(
    tmp_path: Path,
) -> None:
    """Keep source topology Core-owned while selector relevance need not be lexical equality."""
    vault = tmp_path / "vault"
    vault.mkdir()
    write(vault, "one.md", "one", "One", fact("Un hecho.", 0))
    write(vault, "two.md", "two", "Two", fact("Otro hecho.", 0))
    candidates = enumerate_semantic_set_candidates(
        RelationshipEvidenceProjector(VaultRepository(vault), schema()), bounds=SemanticSetBounds()
    )
    assert isinstance(candidates, tuple) and len(candidates) == 2
    payload = json.loads(serialize_semantic_set_candidate_payload(INTENT, candidates))
    assert payload["subject_query"] == "kit básico para la bici"
    assert all(set(item) == {"id", "text"} for item in payload["candidates"])
