"""Read-only, bounded physical evidence for user-schema retrospective jobs."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from odyssey_core.notes import Note, serialize_note
from odyssey_core.schema_retrospection import (
    RetrospectionCursor,
    SchemaRetrospectionError,
    scan_schema_sources,
)
from odyssey_core.storage import VaultRepository

ROOT = Path(__file__).resolve().parents[2]


def schema() -> dict:
    result = json.loads((ROOT / "config/note-schema.json").read_text())
    kind = next(t for t in result["types"] if t["id"] == "person")
    kind["properties"].append(
        {
            "id": "profesion",
            "value_type": "string",
            "description": "Profession",
            "required": False,
            "filterable": True,
        }
    )
    result["types"].append(
        {"id": "libro", "name": "Libro", "description": "Obras", "examples": [], "properties": []}
    )
    return result


def note(
    vault: Path,
    path: str,
    note_id: str,
    note_type: str,
    content: str,
    *,
    properties: dict | None = None,
) -> None:
    target = vault / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        serialize_note(
            Note(
                {
                    "id": note_id,
                    "name": note_id,
                    "type": note_type,
                    "created_at": "2026-01-01T00:00:00Z",
                    "updated_at": "2026-01-01T00:00:00Z",
                    "created_by": {"human": None, "app": "tests"},
                    "updated_by": {"human": None, "app": "tests"},
                    "revision": 1,
                    "schema_version": 3,
                    "aliases": [],
                    "tags": [],
                    **(properties or {}),
                },
                content,
            )
        ),
        encoding="utf-8",
    )


def fact(text: str, request: str = "req", ordinal: int = 0) -> str:
    return (
        f"# Added 01-01-2026\n- {text}\n<!-- odyssey:fact request={request} ordinal={ordinal} -->\n"
    )


def populated(tmp_path: Path) -> tuple[VaultRepository, dict]:
    root = tmp_path / "vault"
    root.mkdir()
    note(root, "a/person.md", "ada", "person", fact("Ada es traductora", "capture", 0))
    note(root, "b/project.md", "project", "project", fact("Leí Dune", "capture", 1))
    note(
        root,
        "c/person.md",
        "bea",
        "person",
        fact("Béa es pintora"),
        properties={"profesion": "Pintora"},
    )
    note(root, "d/old.md", "legacy", "concept", "Texto antiguo: terminé Matilda\n")
    return VaultRepository(root), schema()


def test_discovery_scans_all_existing_types_in_bounded_resumable_pages(tmp_path: Path) -> None:
    repo, config = populated(tmp_path)
    first = scan_schema_sources(
        repository=repo, schema=config, kind="discover_type", target_type_id="libro", limit=2
    )
    assert first.scanned_paths == 2
    assert [(x.note_id, x.note_type) for x in first.eligible_notes] == [
        ("ada", "person"),
        ("project", "project"),
    ]
    assert [(f.locator, f.text) for f in first.eligible_notes[1].facts] == [
        ("capture:1", "Leí Dune")
    ]
    assert len(first.eligible_notes[1].source_hash) == 64
    assert first.eligible_notes[1].revision == 1
    assert not first.eligible_notes[1].legacy_coverage_unverified
    assert first.eligible_notes[1].note_name == "project"
    assert first.next_cursor is not None
    second = scan_schema_sources(
        repository=repo,
        schema=config,
        kind="discover_type",
        target_type_id="libro",
        limit=2,
        cursor=first.next_cursor,
    )
    assert [x.note_id for x in second.eligible_notes] == ["bea", "legacy"]
    assert second.eligible_notes[-1].facts == ()  # no stable locator for legacy text
    assert second.eligible_notes[-1].legacy_coverage_unverified
    assert second.next_cursor is None
    assert second.inventory_hash == first.inventory_hash
    assert repo.read_text("b/project.md").find("Leí Dune") >= 0


def test_property_backfill_only_targets_matching_type_without_prior_value(tmp_path: Path) -> None:
    repo, config = populated(tmp_path)
    page = scan_schema_sources(
        repository=repo,
        schema=config,
        kind="backfill_property",
        target_type_id="person",
        property_id="profesion",
        limit=10,
    )
    assert [n.note_id for n in page.eligible_notes] == ["ada"]
    assert page.skipped_existing_values == 1
    assert page.scanned_paths == 4
    assert page.next_cursor is None
    assert page.eligible_notes[0].facts[0].text == "Ada es traductora"


def test_existing_null_is_not_overwritten_or_treated_as_missing(tmp_path: Path) -> None:
    repo, config = populated(tmp_path)
    root = tmp_path / "vault"
    note(
        root,
        "e/person-null.md",
        "existing-null",
        "person",
        fact("Trabaja en algo"),
        properties={"profesion": None},
    )
    # An explicitly stored null may be invalid under the canonical type and
    # must fail rather than be silently backfilled or skipped as if valid.
    with pytest.raises(SchemaRetrospectionError, match="invalid"):
        scan_schema_sources(
            repository=repo,
            schema=config,
            kind="backfill_property",
            target_type_id="person",
            property_id="profesion",
            limit=20,
        )


def test_rejects_stale_cursor_after_mutation_or_new_file(tmp_path: Path) -> None:
    repo, config = populated(tmp_path)
    before = scan_schema_sources(
        repository=repo, schema=config, kind="discover_type", target_type_id="libro", limit=1
    )
    assert before.next_cursor is not None
    root = tmp_path / "vault"
    note(root, "b/project.md", "project", "project", fact("Leí Dune y luego It"))
    with pytest.raises(SchemaRetrospectionError, match="Stale"):
        scan_schema_sources(
            repository=repo,
            schema=config,
            kind="discover_type",
            target_type_id="libro",
            limit=1,
            cursor=before.next_cursor,
        )
    after = scan_schema_sources(
        repository=repo, schema=config, kind="discover_type", target_type_id="libro", limit=1
    )
    note(root, "z/new.md", "new", "concept", fact("Terminé Solito"))
    with pytest.raises(SchemaRetrospectionError, match="Stale"):
        scan_schema_sources(
            repository=repo,
            schema=config,
            kind="discover_type",
            target_type_id="libro",
            limit=1,
            cursor=after.next_cursor,
        )


def test_wrong_mode_unknown_field_or_bad_cursor_fails_closed(tmp_path: Path) -> None:
    repo, config = populated(tmp_path)
    for kwargs in (
        {"kind": "backfill_property", "target_type_id": "person", "property_id": "fake"},
        {"kind": "backfill_property", "target_type_id": "libro"},
        {"kind": "discover_type", "target_type_id": "missing"},
        {"kind": "discover_type", "target_type_id": "libro", "property_id": "profesion"},
        {"kind": "discover_type", "target_type_id": "libro", "limit": 0},
        {"kind": "discover_type", "target_type_id": "libro", "limit": True},
        {"kind": "discover_type", "target_type_id": "libro", "limit": 26},
        {
            "kind": "discover_type",
            "target_type_id": "libro",
            "cursor": RetrospectionCursor("0" * 64, 1),
        },
    ):
        with pytest.raises(SchemaRetrospectionError):
            scan_schema_sources(repository=repo, schema=config, **kwargs)


def test_corrupt_fact_markup_does_not_get_silently_skipped(tmp_path: Path) -> None:
    repo, config = populated(tmp_path)
    note(
        tmp_path / "vault",
        "e/bad.md",
        "bad",
        "concept",
        "<!-- odyssey:fact request=crash ordinal=0 -->",
    )
    with pytest.raises(SchemaRetrospectionError, match="Malformed fact"):
        scan_schema_sources(
            repository=repo, schema=config, kind="discover_type", target_type_id="libro", limit=20
        )


def test_no_user_data_written_by_scans(tmp_path: Path) -> None:
    repo, config = populated(tmp_path)
    paths = repo.list_markdown_paths()
    before = {p: repo.read_text(p) for p in paths}
    first = scan_schema_sources(
        repository=repo, schema=config, kind="discover_type", target_type_id="libro", limit=25
    )
    second = scan_schema_sources(
        repository=repo,
        schema=config,
        kind="backfill_property",
        target_type_id="person",
        property_id="profesion",
        limit=25,
    )
    assert first.scanned_paths == second.scanned_paths == 4
    assert {p: repo.read_text(p) for p in paths} == before
    assert repo.list_markdown_paths() == paths


def test_discovery_excludes_already_created_target_entities(tmp_path: Path) -> None:
    repo, config = populated(tmp_path)
    note(tmp_path / "vault", "e/book.md", "book1", "libro", fact("Leí un libro"))
    page = scan_schema_sources(
        repository=repo, schema=config, kind="discover_type", target_type_id="libro", limit=25
    )
    assert page.scanned_paths == 5
    assert "book1" not in {n.note_id for n in page.eligible_notes}


def test_mixed_atomic_and_unmarked_body_reports_incomplete_coverage(tmp_path: Path) -> None:
    repo, config = populated(tmp_path)
    note(
        tmp_path / "vault",
        "e/mixed.md",
        "mixed",
        "concept",
        fact("Mencioné Dune") + "Aparte también leí Solaris\n",
    )
    page = scan_schema_sources(
        repository=repo, schema=config, kind="discover_type", target_type_id="libro", limit=25
    )
    source = next(n for n in page.eligible_notes if n.note_id == "mixed")
    assert len(source.facts) == 1
    assert source.legacy_coverage_unverified
