"""Read-only, bounded physical evidence for user-schema retrospective jobs."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from odyssey_core.notes import Note, serialize_note
from odyssey_core.schema_retrospection import (
    RetrospectionCursor,
    SchemaRetrospectionError,
    accumulate_schema_scan,
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
    assert "terminé Matilda" in second.eligible_notes[-1].legacy_text
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


def test_discovery_includes_existing_target_type_as_source_evidence(tmp_path: Path) -> None:
    repo, config = populated(tmp_path)
    note(tmp_path / "vault", "e/book.md", "book1", "libro", fact("Leí un libro"))
    page = scan_schema_sources(
        repository=repo, schema=config, kind="discover_type", target_type_id="libro", limit=25
    )
    assert page.scanned_paths == 5
    sources = {n.note_id: n for n in page.eligible_notes}
    assert "book1" in sources
    assert sources["book1"].note_type == "libro"
    assert sources["book1"].facts[0].text == "Leí un libro"


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
    assert "Solaris" in source.legacy_text
    assert "Mencioné Dune" not in source.legacy_text


def test_cursor_cannot_be_reused_for_another_property_or_new_schema(tmp_path: Path) -> None:
    repo, config = populated(tmp_path)
    first = scan_schema_sources(
        repository=repo, schema=config, kind="discover_type", target_type_id="libro", limit=1
    )
    cursor = first.next_cursor
    assert cursor is not None and len(cursor.context_hash) == 64
    with pytest.raises(SchemaRetrospectionError, match="cursor"):
        scan_schema_sources(
            repository=repo,
            schema=config,
            kind="backfill_property",
            target_type_id="person",
            property_id="profesion",
            limit=1,
            cursor=cursor,
        )
    changed = json.loads(json.dumps(config))
    next(kind for kind in changed["types"] if kind["id"] == "libro")["description"] = "Changed"
    with pytest.raises(SchemaRetrospectionError, match="cursor"):
        scan_schema_sources(
            repository=repo,
            schema=changed,
            kind="discover_type",
            target_type_id="libro",
            limit=1,
            cursor=cursor,
        )
    assert (
        scan_schema_sources(
            repository=repo,
            schema=config,
            kind="discover_type",
            target_type_id="libro",
            limit=1,
            cursor=cursor,
        ).scanned_paths
        == 1
    )


def test_duplicate_atomic_locator_fails_closed_before_downstream_identity_linking(
    tmp_path: Path,
) -> None:
    repo, config = populated(tmp_path)
    note(
        tmp_path / "vault",
        "e/ambiguous.md",
        "ambiguous",
        "concept",
        fact("Leí un libro", "same", 1) + fact("Mencioné otro", "same", 1),
    )
    with pytest.raises(SchemaRetrospectionError, match="Duplicate canonical fact locator"):
        scan_schema_sources(
            repository=repo,
            schema=config,
            kind="discover_type",
            target_type_id="libro",
        )


def test_large_canonical_note_is_not_loaded_into_unbounded_analysis(tmp_path: Path) -> None:
    repo, config = populated(tmp_path)
    note(tmp_path / "vault", "e/huge.md", "huge", "concept", "a" * 2_000_001)
    with pytest.raises(SchemaRetrospectionError, match="safe note size"):
        scan_schema_sources(
            repository=repo,
            schema=config,
            kind="discover_type",
            target_type_id="libro",
        )


def test_unmarked_evidence_never_gets_a_fabricated_locator(tmp_path: Path) -> None:
    repo, config = populated(tmp_path)
    page = scan_schema_sources(
        repository=repo, schema=config, kind="discover_type", target_type_id="libro", limit=25
    )
    legacy = next(item for item in page.eligible_notes if item.note_id == "legacy")
    assert legacy.facts == ()
    assert legacy.legacy_text == "Texto antiguo: terminé Matilda"
    assert legacy.legacy_coverage_unverified


def test_large_unmarked_text_is_rejected_instead_of_truncated(tmp_path: Path) -> None:
    repo, config = populated(tmp_path)
    note(tmp_path / "vault", "e/long.md", "long", "concept", "A" * 13000)
    with pytest.raises(SchemaRetrospectionError, match="Unmarked Markdown"):
        scan_schema_sources(
            repository=repo, schema=config, kind="discover_type", target_type_id="libro", limit=20
        )


def test_read_only_accumulator_reports_progress_and_legacy_coverage(tmp_path: Path) -> None:
    repo, config = populated(tmp_path)
    before = {p: repo.read_text(p) for p in repo.list_markdown_paths()}
    page1 = scan_schema_sources(
        repository=repo, schema=config, kind="discover_type", target_type_id="libro", limit=2
    )
    progress1 = accumulate_schema_scan(page1)
    assert progress1.scanned_paths == 2
    assert progress1.eligible_notes == 2
    assert progress1.legacy_sources == 0
    assert not progress1.complete
    page2 = scan_schema_sources(
        repository=repo,
        schema=config,
        kind="discover_type",
        target_type_id="libro",
        limit=2,
        cursor=progress1.next_cursor,
    )
    progress2 = accumulate_schema_scan(page2, progress1)
    assert progress2.complete
    assert (progress2.scanned_paths, progress2.eligible_notes, progress2.legacy_sources) == (
        4,
        4,
        1,
    )
    assert len(progress2.seen_note_ids) == 4
    assert {p: repo.read_text(p) for p in repo.list_markdown_paths()} == before


def test_accumulator_rejects_cross_page_duplicate_canonical_note_ids(tmp_path: Path) -> None:
    repo, config = populated(tmp_path)
    note(tmp_path / "vault", "e/copy.md", "ada", "concept", fact("Mismo ID físico"))
    first = scan_schema_sources(
        repository=repo, schema=config, kind="discover_type", target_type_id="libro", limit=4
    )
    progress = accumulate_schema_scan(first)
    second = scan_schema_sources(
        repository=repo,
        schema=config,
        kind="discover_type",
        target_type_id="libro",
        limit=4,
        cursor=progress.next_cursor,
    )
    with pytest.raises(SchemaRetrospectionError, match="Duplicate"):
        accumulate_schema_scan(second, progress)


def test_accumulator_rejects_skipped_or_repeated_or_other_query_page(tmp_path: Path) -> None:
    repo, config = populated(tmp_path)
    first = scan_schema_sources(
        repository=repo, schema=config, kind="discover_type", target_type_id="libro", limit=1
    )
    state = accumulate_schema_scan(first)
    with pytest.raises(SchemaRetrospectionError, match="first page"):
        accumulate_schema_scan(
            scan_schema_sources(
                repository=repo,
                schema=config,
                kind="discover_type",
                target_type_id="libro",
                limit=1,
                cursor=state.next_cursor,
            )
        )
    with pytest.raises(SchemaRetrospectionError, match="out-of-order"):
        accumulate_schema_scan(first, state)
    unrelated = scan_schema_sources(
        repository=repo,
        schema=config,
        kind="backfill_property",
        target_type_id="person",
        property_id="profesion",
        limit=2,
    )
    with pytest.raises(SchemaRetrospectionError, match="out-of-order"):
        accumulate_schema_scan(unrelated, state)


def test_accumulator_handles_truly_empty_canonical_vault(tmp_path: Path) -> None:
    root = tmp_path / "empty"
    root.mkdir()
    page = scan_schema_sources(
        repository=VaultRepository(root),
        schema=schema(),
        kind="discover_type",
        target_type_id="libro",
        limit=10,
    )
    progress = accumulate_schema_scan(page)
    assert progress.complete
    assert progress.scanned_paths == 0
    assert progress.eligible_notes == 0
    assert not progress.seen_note_ids


def test_public_scanner_never_accepts_stale_private_staging_snapshot(tmp_path):
    """The autonomous journal's provisional snapshot bypass is not a public API."""
    repo, config = populated(tmp_path)
    old_inventory = repo.note_version_snapshot()
    (repo.root / "e/new.md").parent.mkdir()
    note(
        repo.root,
        "e/new.md",
        "new",
        "person",
        fact("una profesión nueva", "newcase", 0),
    )
    with pytest.raises(TypeError, match="unexpected keyword"):
        scan_schema_sources(
            repository=repo,
            schema=config,
            kind="backfill_property",
            target_type_id="person",
            property_id="profesion",
            _staged_inventory=old_inventory,
        )
    result = scan_schema_sources(
        repository=repo,
        schema=config,
        kind="backfill_property",
        target_type_id="person",
        property_id="profesion",
        limit=25,
    )
    assert result.scanned_paths == 5
    assert "new" in result.source_note_ids
