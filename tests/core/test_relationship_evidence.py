"""Provider-free Slice 1 coverage for Markdown-grounded relationship evidence."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from odyssey_core.atomic_facts import render_atomic_facts
from odyssey_core.notes import Note, serialize_note
from odyssey_core.relationship_evidence import (
    EntityContextLimits,
    EvidenceDirection,
    RelationshipEvidenceProjector,
    TargetProjectionStatus,
)
from odyssey_core.storage import VaultRepository

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def schema() -> dict:
    """Load the canonical schema used by the real Core validators."""
    return json.loads((ROOT / "config/note-schema.json").read_text(encoding="utf-8"))


def write(
    vault: Path,
    path: str,
    note_id: str,
    name: str,
    body: str,
    *,
    updated: str = "2026-09-23T00:00:00Z",
    note_type: str = "person",
    properties: dict[str, object] | None = None,
) -> None:
    """Write one schema-valid disposable canonical Markdown fixture."""
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
                    "updated_at": updated,
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


def projector(vault: Path, schema: dict) -> RelationshipEvidenceProjector:
    """Build the Slice 1 projector against a disposable authoritative vault."""
    return RelationshipEvidenceProjector(VaultRepository(vault), schema)


def fact(body: str, request: str = "fixture", ordinal: int = 0) -> str:
    """Render one canonical, marker-addressable fact fixture."""
    return render_atomic_facts((body,), request, (ordinal,), "2026-09-23")


def test_unique_singular_target_uses_one_current_literal_link_hop(
    tmp_path: Path, schema: dict
) -> None:
    """Resolve Chloe from Edgar's fact without inventing a relation-named identity or second hop."""
    vault = tmp_path / "vault"
    vault.mkdir()
    write(vault, "people/chloe.md", "chloe", "Chloe", fact("Chloe conoce a [[Marta]]."))
    write(vault, "people/marta.md", "marta", "Marta", "")
    write(vault, "people/edgar.md", "edgar", "Edgar", fact("Mi hija es [[Chloe]]."))

    evidence = projector(vault, schema)
    source_fact = evidence.facts_for_source("edgar")[0]
    result = evidence.project_targets("edgar", source_fact.locator)

    assert result.status is TargetProjectionStatus.COMPLETE
    assert result.complete is True
    assert result.unique_target and result.unique_target.id == "chloe"
    assert [(target.id, target.path) for target in result.targets] == [("chloe", "people/chloe.md")]
    assert [item.target.id for item in result.evidence] == ["chloe"]
    assert result.evidence[0].direction is EvidenceDirection.OUTGOING
    assert "hija" not in {target.id for target in result.targets}
    assert "marta" not in {target.id for target in result.targets}
    assert result.fact and result.fact.source.source_hash == result.source.source_hash

    write(
        vault,
        "people/edgar.md",
        "edgar",
        "Edgar",
        fact("Mi hija es [[Chloe]].") + "\n\n" + fact("Edgar vive en Madrid.", "edgar", 1),
    )
    stale_fact = projector(vault, schema).project_targets("edgar", source_fact.locator)
    assert stale_fact.status is TargetProjectionStatus.FACT_UNAVAILABLE


def test_complete_finite_set_preserves_literal_order_and_rejects_partial_members(
    tmp_path: Path, schema: dict
) -> None:
    """Return all grounded participants or an empty incomplete result when one link is stale."""
    vault = tmp_path / "vault"
    vault.mkdir()
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
    evidence = projector(vault, schema)
    source_fact = evidence.facts_for_source("visit")[0]
    complete = evidence.project_targets("visit", source_fact.locator)
    assert complete.complete is True
    assert complete.unique_target is None
    assert [target.id for target in complete.targets] == ["marta", "juan", "pedro"]

    (vault / "people" / "pedro.md").unlink()
    incomplete = projector(vault, schema).project_targets("visit", source_fact.locator)
    assert incomplete.status is TargetProjectionStatus.INCOMPLETE
    assert incomplete.complete is False
    assert incomplete.targets == ()
    assert incomplete.evidence == ()


def test_entity_context_regrounds_bounded_incoming_outgoing_and_stale_discovery(
    tmp_path: Path, schema: dict
) -> None:
    """Surface fact snippets, never whole source notes, and reject stale backlink candidates."""
    vault = tmp_path / "vault"
    vault.mkdir()
    write(vault, "people/airbus.md", "airbus", "Airbus", "")
    write(
        vault,
        "people/oriol.md",
        "oriol",
        "Oriol",
        fact("Oriol vive en Barcelona.") + "\n\n" + fact("Oriol conoce a [[Airbus]].", "oriol", 1),
    )
    write(
        vault,
        "people/meritxell.md",
        "meritxell",
        "Meritxell",
        fact("Mi hermano [[Oriol]] trabaja en Airbus.") + "\n\nProsa que no debe entrar completa.",
    )
    write(vault, "people/stale.md", "stale", "Stale", fact("Antes enlazaba a [[Oriol]]."))
    for index in range(8):
        write(
            vault,
            f"people/link-{index}.md",
            f"link-{index}",
            f"Link {index}",
            fact(f"Mención {index} de [[Oriol]].", f"many-{index}"),
        )

    bounded = projector(vault, schema).project_entity_context(
        "oriol", limits=EntityContextLimits(max_direct=2, max_incoming=3, max_outgoing=2)
    )
    assert bounded is not None
    assert len(bounded.incoming) == 3
    assert bounded.incoming_truncated is True

    context = projector(vault, schema).project_entity_context(
        "oriol", limits=EntityContextLimits(max_direct=2, max_incoming=9, max_outgoing=2)
    )
    assert context is not None
    assert context.entity.path == "people/oriol.md"
    assert [(item.direction, item.fact.text, item.target) for item in context.direct] == [
        (EvidenceDirection.DIRECT, "Oriol vive en Barcelona.", None)
    ]
    assert len(context.incoming) == 9
    assert context.incoming_truncated is True
    assert all(
        "Prosa que no debe entrar completa" not in item.fact.text for item in context.incoming
    )
    meritxell = next(item for item in context.incoming if item.fact.source.id == "meritxell")
    assert meritxell.fact.text == "Mi hermano [[Oriol]] trabaja en Airbus."
    assert meritxell.fact.source.path == "people/meritxell.md"
    assert meritxell.fact.source.source_hash
    assert [(item.direction, item.target.id) for item in context.outgoing] == [
        (EvidenceDirection.OUTGOING, "airbus")
    ]

    write(vault, "people/stale.md", "stale", "Stale", fact("Ya no enlaza a [[Airbus]]."))
    stale_only = projector(vault, schema).project_entity_context(
        "oriol", discovered_backlink_source_ids=("stale",)
    )
    assert stale_only is not None
    assert stale_only.incoming == ()
