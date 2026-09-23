"""Provider-free Slice 2 coverage for relationship evidence write preparation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import odyssey_core.application as application
from odyssey_core import (
    KnowledgeReference,
    KnowledgeUnit,
    RelationshipEvidenceProjector,
    RelationshipWriteBinding,
    RelationshipWritePreflightError,
    ResolvedRelationshipMember,
    SelectionCriteria,
    WriteAction,
    preflight_relationship_write_action,
    render_reference_facts,
)
from odyssey_core.atomic_facts import render_atomic_facts
from odyssey_core.notes import Note, parse_note, serialize_note
from odyssey_core.observability import SpanRecorder
from odyssey_core.storage import VaultRepository

ROOT = Path(__file__).resolve().parents[2]


class EmptyIndex:
    """Provide no semantic candidates for exact deterministic fixtures."""

    def find_candidates(self, *args: object, **kwargs: object) -> tuple[object, ...]:
        """Return no candidates without using a provider."""
        return ()


class EmptyEmbedder:
    """Satisfy the existing resolution seam without embedding."""

    model_name = "tests"
    model_version = "1"


class NoReasoner:
    """Reject contextual resolution when exact fixture identities should suffice."""

    def resolve(self, request: object) -> object:
        """Fail if this provider-free test reaches contextual reasoning."""
        raise AssertionError("relationship write fixture reached contextual resolution")


class ForbiddenWriter:
    """Reject writer invocation for atomic shared-fact and reference-only fixtures."""

    def write(self, request: object) -> object:
        """Fail because this slice must not require a writer for rendered atomic facts."""
        raise AssertionError("relationship write fixture invoked writer")


@pytest.fixture
def schema() -> dict:
    """Load the canonical schema used by the production validators."""
    return json.loads((ROOT / "config/note-schema.json").read_text(encoding="utf-8"))


def fact(text: str, request: str = "fixture", ordinal: int = 0) -> str:
    """Render one marker-addressable canonical fact fixture."""
    return render_atomic_facts((text,), request, (ordinal,), "2026-09-23")


def write(
    vault: Path,
    path: str,
    note_id: str,
    name: str,
    body: str,
    *,
    note_type: str = "person",
    properties: dict[str, object] | None = None,
) -> None:
    """Write one schema-valid disposable Markdown note."""
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
                    "updated_at": "2026-09-23T00:00:00Z",
                    "created_by": {"human": None, "app": "test"},
                    "updated_by": {"human": None, "app": "test"},
                    "revision": 1,
                    "schema_version": 3,
                    "aliases": [],
                    "tags": [],
                    **(properties or {}),
                },
                body,
            )
        ),
        encoding="utf-8",
    )


def reference_only(name: str) -> KnowledgeUnit:
    """Build one structurally no-write member unit for the ordinary preflight table."""
    return KnowledgeUnit(
        SelectionCriteria(name, name, "person", (), None), "record", (), (), (), ()
    )


def relationship_action(source_name: str, members: tuple[str, ...]) -> WriteAction:
    """Build one existing fact source plus ordered reference-only relationship members."""
    references = tuple(
        KnowledgeReference(index + 1, "member", name) for index, name in enumerate(members)
    )
    markers = ", ".join(f"{{{{ref:{index}}}}}" for index in range(len(members)))
    source = KnowledgeUnit(
        SelectionCriteria(source_name, source_name, "journal_entry", (), None),
        "record",
        (),
        (),
        (f"{markers} formamos parte del mismo grupo.",),
        references,
    )
    return WriteAction((source, *(reference_only(name) for name in members)))


def relationship_binding(
    source_id: str, locator: str, member_ids: tuple[str, ...]
) -> RelationshipWriteBinding:
    """Bind ordered no-write units to the Core-grounded relationship target IDs."""
    return RelationshipWriteBinding(
        0,
        source_id,
        locator,
        tuple(
            ResolvedRelationshipMember(index, stable_id)
            for index, stable_id in enumerate(member_ids, start=1)
        ),
    )


def preflight(
    vault: Path,
    schema: dict,
    action: WriteAction,
    binding: RelationshipWriteBinding,
) -> tuple:
    """Prepare one relationship write entirely through current Core preflight boundaries."""
    repository = VaultRepository(vault)
    return preflight_relationship_write_action(
        action,
        binding,
        relationship_projector=RelationshipEvidenceProjector(repository, schema),
        repository=repository,
        schema=schema,
        semantic_index=EmptyIndex(),
        embedder=EmptyEmbedder(),
        contextual_reasoner=NoReasoner(),
        semantic_limit=5,
    )


def shared_fixture(vault: Path) -> None:
    """Create an existing event and its complete grounded participant set."""
    for note_id, name in (("marta", "Marta"), ("juan", "Juan"), ("pedro", "Pedro")):
        write(vault, f"people/{note_id}.md", note_id, name, "")
    write(
        vault,
        "events/visit.md",
        "visit",
        "Visita",
        fact("Asistieron [[Marta]], [[Juan]] y [[Pedro]]."),
        note_type="journal_entry",
        properties={"entry_date": "2026-09-23"},
    )


def test_shared_fact_mutates_only_existing_natural_source(tmp_path: Path, schema: dict) -> None:
    """Persist one linked source fact while successful reference-only members remain byte-identical."""
    vault = tmp_path / "vault"
    vault.mkdir()
    shared_fixture(vault)
    repository = VaultRepository(vault)
    projector = RelationshipEvidenceProjector(repository, schema)
    locator = projector.facts_for_source("visit")[0].locator
    action = relationship_action("Visita", ("Marta", "Juan", "Pedro"))
    binding = relationship_binding("visit", locator, ("marta", "juan", "pedro"))
    before = {
        name: (vault / "people" / f"{name}.md").read_bytes() for name in ("marta", "juan", "pedro")
    }

    table = preflight(vault, schema, action, binding)
    rendering = render_reference_facts(action, table)
    results = application._execute_single_units(
        action,
        table,
        rendering.pending_references,
        rendering.rendered_facts,
        repository,
        schema,
        "test",
        "2026-09-23T12:00:00Z",
        ForbiddenWriter(),
        "relationship-request",
        ((0,), (), (), ()),
        None,
        SpanRecorder(0.0, lambda: 0.0),
    )

    assert rendering.rendered_facts[0] == (
        "[[people/marta|Marta]], [[people/juan|Juan]], [[people/pedro|Pedro]] formamos parte del mismo grupo.",
    )
    assert [item.operation for item in results] == [
        "UPDATED",
        "REFERENCE_BOUND",
        "REFERENCE_BOUND",
        "REFERENCE_BOUND",
    ]
    assert all(item.materially_affected is False for item in results[1:])
    assert application._affected_ids(
        application.ActionResult(
            0, "write", application.ActionStatus.COMPLETED, unit_results=tuple(results)
        )
    ) == ("visit",)
    assert all((vault / "people" / f"{name}.md").read_bytes() == before[name] for name in before)
    assert (
        parse_note((vault / "events/visit.md").read_text(encoding="utf-8")).metadata["revision"]
        == 2
    )


def test_unique_singular_target_is_pre_resolved_without_create(
    tmp_path: Path, schema: dict
) -> None:
    """Bind Chloe from current evidence without treating the relational phrase as a new identity."""
    vault = tmp_path / "vault"
    vault.mkdir()
    write(vault, "people/chloe.md", "chloe", "Chloe", "")
    write(
        vault,
        "events/source.md",
        "source",
        "Source",
        fact("Mi hija es [[Chloe]]."),
        note_type="journal_entry",
        properties={"entry_date": "2026-09-23"},
    )
    locator = (
        RelationshipEvidenceProjector(VaultRepository(vault), schema)
        .facts_for_source("source")[0]
        .locator
    )
    action = relationship_action("Source", ("Chloe",))
    table = preflight(vault, schema, action, relationship_binding("source", locator, ("chloe",)))
    assert table[1].stable_id == "chloe"
    assert table[1].reference_only is True
    assert all(item.outcome.value != "CREATE" for item in table)


def test_member_bindings_are_independent_of_evidence_link_order(
    tmp_path: Path, schema: dict
) -> None:
    """Render each member unit with its exact Core-grounded ID, regardless of fact ordering."""
    vault = tmp_path / "vault"
    vault.mkdir()
    shared_fixture(vault)
    locator = (
        RelationshipEvidenceProjector(VaultRepository(vault), schema)
        .facts_for_source("visit")[0]
        .locator
    )
    action = relationship_action("Visita", ("Pedro", "Marta", "Juan"))
    binding = relationship_binding("visit", locator, ("pedro", "marta", "juan"))

    rendering = render_reference_facts(action, preflight(vault, schema, action, binding))

    assert rendering.rendered_facts[0] == (
        "[[people/pedro|Pedro]], [[people/marta|Marta]], [[people/juan|Juan]] "
        "formamos parte del mismo grupo.",
    )


def test_forged_relationship_member_id_fails_closed(tmp_path: Path, schema: dict) -> None:
    """Reject a binding ID that is not part of the freshly complete relationship projection."""
    vault = tmp_path / "vault"
    vault.mkdir()
    shared_fixture(vault)
    write(vault, "people/chloe.md", "chloe", "Chloe", "")
    locator = (
        RelationshipEvidenceProjector(VaultRepository(vault), schema)
        .facts_for_source("visit")[0]
        .locator
    )
    action = relationship_action("Visita", ("Marta", "Juan", "Chloe"))
    before = {path: path.read_bytes() for path in vault.rglob("*.md")}

    with pytest.raises(RelationshipWritePreflightError, match="member set"):
        preflight(
            vault,
            schema,
            action,
            relationship_binding("visit", locator, ("marta", "juan", "chloe")),
        )

    assert {path: path.read_bytes() for path in vault.rglob("*.md")} == before


def test_duplicate_relationship_member_binding_fails_closed(tmp_path: Path, schema: dict) -> None:
    """Reject two no-write units that claim the same member in a distinct complete set."""
    vault = tmp_path / "vault"
    vault.mkdir()
    shared_fixture(vault)
    locator = (
        RelationshipEvidenceProjector(VaultRepository(vault), schema)
        .facts_for_source("visit")[0]
        .locator
    )
    action = relationship_action("Visita", ("Marta", "Marta", "Pedro"))
    binding = relationship_binding("visit", locator, ("marta", "marta", "pedro"))
    before = {path: path.read_bytes() for path in vault.rglob("*.md")}

    with pytest.raises(RelationshipWritePreflightError, match="member bindings"):
        preflight(vault, schema, action, binding)

    assert {path: path.read_bytes() for path in vault.rglob("*.md")} == before


@pytest.mark.parametrize(
    ("members", "member_ids"),
    (
        (("Marta", "Juan"), ("marta", "juan")),
        (("Marta", "Juan", "Pedro", "Chloe"), ("marta", "juan", "pedro", "chloe")),
    ),
)
def test_missing_or_extra_relationship_member_binding_fails_closed(
    tmp_path: Path, schema: dict, members: tuple[str, ...], member_ids: tuple[str, ...]
) -> None:
    """Require binding IDs to equal the complete current set, with no subset or addition."""
    vault = tmp_path / "vault"
    vault.mkdir()
    shared_fixture(vault)
    write(vault, "people/chloe.md", "chloe", "Chloe", "")
    locator = (
        RelationshipEvidenceProjector(VaultRepository(vault), schema)
        .facts_for_source("visit")[0]
        .locator
    )
    action = relationship_action("Visita", members)
    before = {path: path.read_bytes() for path in vault.rglob("*.md")}

    with pytest.raises(RelationshipWritePreflightError, match="member set"):
        preflight(vault, schema, action, relationship_binding("visit", locator, member_ids))

    assert {path: path.read_bytes() for path in vault.rglob("*.md")} == before


@pytest.mark.parametrize("failure", ("stale", "incomplete"))
def test_stale_or_incomplete_relationship_evidence_blocks_all_write_preparation(
    tmp_path: Path, schema: dict, failure: str
) -> None:
    """Reject stale source locators and missing set members before any source/member mutation."""
    vault = tmp_path / "vault"
    vault.mkdir()
    shared_fixture(vault)
    projector = RelationshipEvidenceProjector(VaultRepository(vault), schema)
    locator = projector.facts_for_source("visit")[0].locator
    action = relationship_action("Visita", ("Marta", "Juan", "Pedro"))
    binding = relationship_binding("visit", locator, ("marta", "juan", "pedro"))
    before = {path: path.read_bytes() for path in vault.rglob("*.md")}
    if failure == "stale":
        write(
            vault,
            "events/visit.md",
            "visit",
            "Visita",
            fact("Asistieron [[Marta]], [[Juan]] y [[Pedro]].")
            + "\n\n"
            + fact("Cambio.", "later", 1),
            note_type="journal_entry",
            properties={"entry_date": "2026-09-23"},
        )
    else:
        (vault / "people/pedro.md").unlink()
    before = {path: path.read_bytes() for path in vault.rglob("*.md")}
    with pytest.raises(RelationshipWritePreflightError):
        preflight(vault, schema, action, binding)
    for path, content in before.items():
        if path.exists():
            assert path.read_bytes() == content


def test_missing_natural_source_never_authorizes_create(tmp_path: Path, schema: dict) -> None:
    """Require an existing source unit and refuse any implicit self/group/event fallback."""
    vault = tmp_path / "vault"
    vault.mkdir()
    shared_fixture(vault)
    locator = (
        RelationshipEvidenceProjector(VaultRepository(vault), schema)
        .facts_for_source("visit")[0]
        .locator
    )
    action = relationship_action("No existe", ("Marta", "Juan", "Pedro"))
    with pytest.raises(RelationshipWritePreflightError, match="Natural relationship source"):
        preflight(
            vault,
            schema,
            action,
            relationship_binding("visit", locator, ("marta", "juan", "pedro")),
        )
