"""Deterministic fact-grounding coverage for subject-independent semantic sets."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from odyssey_core.atomic_facts import render_atomic_facts
from odyssey_core.identity_boundary import AuthenticatedActorContext
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
    parse_semantic_set_selection,
    resolve_semantic_set,
    semantic_set_selection_schema,
    serialize_semantic_set_candidate_payload,
)
from odyssey_core.storage import VaultRepository

ROOT = Path(__file__).resolve().parents[2]
INTENT = SemanticSetIntent("query", "kit básico para la bici", "piezas", "", True)
ACTOR = AuthenticatedActorContext("8c1a06bc-17cc-4f81-a026-e3ba04c971e5")


class SelfBinding:
    """Bind the disposable authenticated actor to the fixture self Note."""

    def __init__(self, person_note_id: str = "self") -> None:
        self.person_note_id = person_note_id

    def resolve(self, stable_user_id: str) -> SimpleNamespace:
        """Return the fixed current self binding only for the test actor."""
        assert stable_user_id == ACTOR.stable_user_id
        return SimpleNamespace(person_note_id=self.person_note_id)


def schema() -> dict:
    """Load the active schema for disposable canonical Markdown fixtures."""
    return json.loads((ROOT / "config/note-schema.json").read_text(encoding="utf-8"))


def write(
    vault: Path, path: str, note_id: str, name: str, body: str, note_type: str = "person"
) -> None:
    """Write one schema-valid temporary canonical Note without creating subject Notes."""
    target = vault / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        serialize_note(
            Note(
                {
                    "id": note_id,
                    "name": name,
                    "type": note_type,
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


def run(
    vault: Path,
    selector: Select,
    *,
    bounds: SemanticSetBounds | None = None,
    intent=INTENT,
    query: str | None = None,
    collection_subject: str | None = None,
    binding: SelfBinding | None = None,
):
    """Resolve one set from the full bounded canonical fact scope."""
    return resolve_semantic_set(
        intent,
        repository=VaultRepository(vault),
        schema=schema(),
        selector=selector,
        bounds=bounds or SemanticSetBounds(),
        query=query,
        collection_subject=collection_subject,
        authenticated_actor=ACTOR if collection_subject == "self" else None,
        self_binding_repository=binding,
    )


def test_collection_uses_lossless_query_without_planner_ontology(tmp_path: Path) -> None:
    """Core grounds all supported members from full wording without a generated subject/type."""
    vault = tmp_path / "vault"
    vault.mkdir()
    values = tuple(f"part-{index}" for index in range(8))
    wording = "El kit contiene " + ", ".join(values) + "."
    write(vault, "kit.md", "kit", "Kit", fact(wording, 0))

    class FullQuerySelector(Select):
        """Assert the only model-facing semantic authority is the complete request."""

        def select(self, request):
            """Choose every exact visible value from supplied current facts."""
            assert request.query == "What are all the parts in my kit?"
            assert request.intent is None
            return super().select(request)

    selector = FullQuerySelector(
        lambda candidate: [
            (
                "literal",
                candidate.text.index(value),
                candidate.text.index(value) + len(value),
            )
            for value in values
        ]
    )
    result = resolve_semantic_set(
        query="What are all the parts in my kit?",
        repository=VaultRepository(vault),
        schema=schema(),
        selector=selector,
    )

    assert result.outcome is SemanticSetOutcome.ANSWERABLE
    assert result.grounded_set is not None
    assert result.grounded_set.subject_kind is None
    assert [member.value for member in result.grounded_set.members] == list(values)


def test_selector_contract_contains_only_supplied_ids_exact_spans_and_uncertainty() -> None:
    """The provider cannot return canonical identity, path, or invented evidence authority."""
    selector_schema = semantic_set_selection_schema()
    assert set(selector_schema["properties"]) == {
        "supplied_fact_ids",
        "member_occurrences",
        "scope_uncertain",
    }
    assert selector_schema["additionalProperties"] is False
    parsed = parse_semantic_set_selection(
        {
            "supplied_fact_ids": ["candidate-0"],
            "member_occurrences": [
                {"candidate_id": "candidate-0", "kind": "literal", "start": 1, "end": 5}
            ],
            "scope_uncertain": False,
        }
    )
    assert parsed.member_occurrences == (SetMemberOccurrence("candidate-0", "literal", 1, 5),)
    with pytest.raises(ValueError):
        parse_semantic_set_selection(
            {
                "supplied_fact_ids": [],
                "member_occurrences": [],
                "scope_uncertain": False,
                "note_id": "invented",
            }
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


def test_self_collection_uses_bound_note_and_literal_one_hop_evidence_only(tmp_path: Path) -> None:
    """Bind self in Core while excluding similarly worded third-party family facts."""
    vault = tmp_path / "vault"
    vault.mkdir()
    write(vault, "people/ana.md", "ana", "Ana", "")
    write(vault, "people/bruno.md", "bruno", "Bruno", "")
    write(vault, "people/self.md", "self", "Self", fact("Mis hijos son [[Bruno]].", 0))
    write(
        vault,
        "people/evidence.md",
        "evidence",
        "Evidence",
        fact("Mi madre es [[Ana]] y soy [[Self]].", 0),
    )
    write(
        vault,
        "people/noise.md",
        "noise",
        "Noise",
        fact("Mis hijos son [[Ana]] y [[Bruno]].", 0),
    )
    seen_sources: list[str] = []

    class SelfSelector(Select):
        """Select exact identity links while recording the Core-supplied self scope."""

        def select(self, request):
            seen_sources.extend(candidate.id for candidate in request.candidates)
            return super().select(request)

    result = run(
        vault,
        SelfSelector(
            lambda candidate: [
                ("link", candidate.text.index(link), candidate.text.index(link) + len(link))
                for link in ("[[Bruno]]", "[[Ana]]")
                if link in candidate.text
            ]
        ),
        intent=None,
        query="¿Quiénes son mis hijos y mis padres?",
        collection_subject="self",
        binding=SelfBinding(),
    )

    assert result.outcome is SemanticSetOutcome.ANSWERABLE
    assert result.grounded_set and result.grounded_set.subject_kind == "self"
    assert {
        member.stable_id
        for member in result.grounded_set.members
        if isinstance(member, IdentitySetMember)
    } == {
        "ana",
        "bruno",
    }
    # `candidate-*` reveals no source identity to a selector.  The count proves only the direct
    # self fact and literal incoming fact were eligible; the noise fact never entered scope.
    assert seen_sources == ["candidate-0", "candidate-1"]


def test_batching_scans_late_evidence_beyond_old_source_and_fact_limits(tmp_path: Path) -> None:
    """An empty first payload cannot end complete canonical collection discovery."""
    vault = tmp_path / "vault"
    vault.mkdir()
    for index in range(66):
        value = "late-member" if index == 65 else f"noise-{index}"
        write(
            vault,
            f"notes/{index:03}.md",
            f"note-{index:03}",
            f"Note {index}",
            fact(f"El kit incluye {value}.", 0),
        )
    requests: list[tuple[str, ...]] = []

    class LateSelector(Select):
        """Emit a member only from the final selector batch."""

        def select(self, request):
            requests.append(tuple(candidate.id for candidate in request.candidates))
            return super().select(request)

    result = run(
        vault,
        LateSelector(
            lambda candidate: (
                [
                    (
                        "literal",
                        candidate.text.index("late-member"),
                        candidate.text.index("late-member") + len("late-member"),
                    )
                ]
                if "late-member" in candidate.text
                else []
            )
        ),
        intent=None,
        query="¿Qué incluye el kit?",
        collection_subject="query",
    )

    assert result.outcome is SemanticSetOutcome.ANSWERABLE
    assert result.grounded_set and [member.value for member in result.grounded_set.members] == [
        "late-member"
    ]
    assert [len(request) for request in requests] == [64, 2]


def test_batching_treats_aggregate_bytes_as_batches_and_oversized_fact_as_unavailable(
    tmp_path: Path,
) -> None:
    """Keep aggregate evidence reachable but reject one fact that cannot form a legal payload."""
    vault = tmp_path / "vault"
    vault.mkdir()
    for index in range(3):
        value = f"member-{index}"
        write(
            vault,
            f"notes/{index}.md",
            f"note-{index}",
            f"Note {index}",
            fact(f"{value} " + "x" * 6_000, 0),
        )
    calls = 0

    class ByteSelector(Select):
        """Count legal bounded batch calls without selecting a member."""

        def select(self, request):
            nonlocal calls
            calls += 1
            return super().select(request)

    aggregate = run(
        vault,
        ByteSelector(lambda _candidate: []),
        intent=None,
        query="¿Qué miembros hay?",
        collection_subject="query",
    )
    assert aggregate.outcome is SemanticSetOutcome.NO_RELEVANT_EVIDENCE
    assert calls == 2

    write(vault, "notes/large.md", "large", "Large", fact("x" * (16 * 1024), 0))
    too_large = run(
        vault,
        Select(lambda _candidate: []),
        intent=None,
        query="¿Qué miembros hay?",
        collection_subject="query",
    )
    assert (too_large.outcome, too_large.reason) == (
        SemanticSetOutcome.INCOMPLETE_EVIDENCE,
        "evidence_item_too_large",
    )


@pytest.mark.parametrize("change", ["add", "delete"])
def test_complete_collection_rejects_inventory_addition_or_deletion_during_batches(
    tmp_path: Path, change: str
) -> None:
    """A changed eligible inventory never turns an already scanned prefix into a complete set."""
    vault = tmp_path / "vault"
    vault.mkdir()
    write(vault, "notes/first.md", "first", "First", fact("El kit incluye llave.", 0))
    write(vault, "notes/second.md", "second", "Second", fact("El kit incluye cinta.", 0))

    class InventoryMutation(Select):
        """Change the disposable canonical inventory after Core captured its scan snapshot."""

        def select(self, request):
            if change == "add":
                write(vault, "notes/added.md", "added", "Added", fact("El kit incluye bomba.", 0))
            else:
                (vault / "notes/second.md").unlink()
            return super().select(request)

    result = run(
        vault,
        InventoryMutation(lambda _candidate: []),
        intent=None,
        query="¿Qué incluye el kit?",
        collection_subject="query",
    )

    assert (result.outcome, result.reason) == (
        SemanticSetOutcome.STALE_EVIDENCE,
        "inventory_changed",
    )


def test_selector_failure_is_a_structured_operational_collection_outcome(tmp_path: Path) -> None:
    """Provider/selector failure never escapes as a partial collection answer."""
    vault = tmp_path / "vault"
    vault.mkdir()
    write(vault, "notes/kit.md", "kit", "Kit", fact("El kit incluye llave.", 0))

    class FailingSelector:
        """Simulate a bounded selector transport failure without a provider call."""

        def select(self, request):
            raise TimeoutError("synthetic selector timeout")

    result = run(
        vault,
        FailingSelector(),
        intent=None,
        query="¿Qué incluye el kit?",
        collection_subject="query",
    )

    assert (result.outcome, result.reason) == (
        SemanticSetOutcome.OPERATIONAL_FAILURE,
        "selector_failure",
    )


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


def test_typed_people_use_non_person_one_hop_sources_but_reject_other_member_types(
    tmp_path: Path,
) -> None:
    """Typed members are complete person candidates while any Note type may supply link evidence."""
    vault = tmp_path / "vault"
    vault.mkdir()
    write(vault, "people/marta.md", "marta", "Marta", "")
    write(vault, "people/pedro.md", "pedro", "Pedro", "")
    write(
        vault,
        "projects/italy.md",
        "italy",
        "Viaje Italia",
        fact("Viajé a Italia con [[marta]].", 0),
        "project",
    )
    write(
        vault,
        "projects/work.md",
        "work",
        "Trabajo",
        fact("Trabajo para [[italy]] con [[pedro]].", 0),
        "project",
    )
    intent = SemanticSetIntent(
        "self", None, "personas con las que viajé a Italia", "", True, "person"
    )
    result = run(
        vault,
        Select(
            lambda candidate: (
                [("link", candidate.text.index("[[marta]]"), candidate.text.index("[[marta]]") + 9)]
                if "[[marta]]" in candidate.text
                else []
            )
        ),
        intent=intent,
    )
    assert result.outcome is SemanticSetOutcome.ANSWERABLE
    assert result.grounded_set
    assert [
        member.stable_id
        for member in result.grounded_set.members
        if isinstance(member, IdentitySetMember)
    ] == ["marta"]

    wrong = run(
        vault,
        Select(
            lambda candidate: (
                [("link", candidate.text.index("[[italy]]"), candidate.text.index("[[italy]]") + 9)]
                if "[[italy]]" in candidate.text
                else []
            )
        ),
        intent=intent,
    )
    assert wrong.outcome is SemanticSetOutcome.INCOMPLETE_EVIDENCE
    assert result.grounded_set.scanned_source_note_count >= 2
