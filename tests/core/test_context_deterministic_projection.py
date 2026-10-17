"""All deterministic SQLite projections remain rebuildable from canonical Notes."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from odyssey_core.atomic_facts import render_atomic_facts
from odyssey_core.context import ContextIndex, ContextIndexError
from odyssey_core.notes import Note, serialize_note
from odyssey_core.storage import VaultRepository
from tests.core.test_context import KeywordEmbedder, note

SCHEMA = json.loads((Path(__file__).resolve().parents[2] / "config/note-schema.json").read_text())


def write(repo, path, value):
    raw = serialize_note(value)
    if (repo.root / path).exists():
        repo.replace_text(path, raw)
    else:
        (repo.root / path).parent.mkdir(parents=True, exist_ok=True)
        repo.create_text(path, raw)


def rows(index, query):
    with sqlite3.connect(index.path) as db:
        return db.execute(query).fetchall()


def test_every_metadata_field_alias_atomic_fact_and_forward_backlinks(tmp_path):
    (tmp_path / "vault").mkdir()
    repo = VaultRepository(tmp_path / "vault")
    person = note(
        "nerea", "person", "Nerea.", name="Nerea", aliases=["Béa", "Beatriz"], tags=["colegio"]
    )
    content = render_atomic_facts(
        (
            "Hoy vi a [[people/nerea|Nerea]] y [[people/missing|otra persona]].",
            "Comenté lo ocurrido a [[people/nerea|Nerea]].",
        ),
        "r-facts",
        (0, 1),
        "2026-10-17",
    )
    project = note("odyssey", "project", content, name="Odyssey")
    write(repo, "people/nerea.md", person)
    write(repo, "projects/odyssey.md", project)
    index = ContextIndex(tmp_path / "context.sqlite3")
    index.rebuild(repo, SCHEMA, KeywordEmbedder())
    attributes = dict(
        rows(index, "SELECT field,value_json FROM note_attributes WHERE note_id='nerea'")
    )
    assert json.loads(attributes["name"]) == "Nerea"
    assert json.loads(attributes["aliases"]) == ["Béa", "Beatriz"]
    assert json.loads(attributes["tags"]) == ["colegio"]
    assert json.loads(attributes["created_by"]) == {"human": None, "app": "pytest"}
    assert json.loads(attributes["schema_version"]) == 3
    assert rows(
        index, "SELECT alias,normalized FROM note_aliases WHERE note_id='nerea' ORDER BY alias"
    ) == [("Beatriz", "beatriz"), ("Béa", "béa")]
    facts = rows(
        index,
        "SELECT locator, fact_text, temporal_anchors FROM note_facts WHERE note_id='odyssey' ORDER BY ordinal",
    )
    assert [item[0] for item in facts] == ["r-facts:0", "r-facts:1"]
    assert "people/missing" in facts[0][1]
    assert [json.loads(item[2]) for item in facts] == [[], []]
    # Raw mentions keep unresolved provenance, but graph/backlinks never invent a target.
    assert rows(
        index,
        "SELECT target_text,target_id FROM note_mentions WHERE source_id='odyssey' ORDER BY target_text",
    ) == [
        ("calendar/days/2026-10-17", None),
        ("people/missing", None),
        ("people/nerea", "nerea"),
    ]
    assert rows(
        index, "SELECT target_id,occurrence_count FROM note_links WHERE source_id='odyssey'"
    ) == [("nerea", 2)]
    assert rows(index, "SELECT source_id FROM note_links WHERE target_id='nerea'") == [("odyssey",)]
    assert rows(
        index,
        "SELECT fact_locator,target_id FROM note_fact_links WHERE note_id='odyssey' ORDER BY fact_locator,target_text",
    ) == [("r-facts:0", None), ("r-facts:0", "nerea"), ("r-facts:1", "nerea")]


def test_incremental_fact_and_mentions_resolve_new_target_and_match_rebuild(tmp_path):
    (tmp_path / "vault").mkdir()
    repo = VaultRepository(tmp_path / "vault")
    project = note(
        "odyssey",
        "project",
        render_atomic_facts(("Preparé [[people/ana|Ana]].",), "r-one", (0,), "2026-10-17"),
        name="Odyssey",
    )
    write(repo, "project.md", project)
    index = ContextIndex(tmp_path / "incremental.sqlite3")
    index.rebuild(repo, SCHEMA, KeywordEmbedder())
    assert rows(index, "SELECT target_id FROM note_fact_links") == [(None,)]
    assert rows(index, "SELECT target_id FROM note_mentions WHERE target_text = 'people/ana'") == [
        (None,)
    ]
    write(repo, "people/ana.md", note("ana", "person", "Ana.", name="Ana"))
    assert index.refresh_notes(repo, SCHEMA, KeywordEmbedder(), note_ids=("ana",)) == 1
    assert rows(index, "SELECT target_id FROM note_fact_links") == [("ana",)]
    assert rows(index, "SELECT target_id FROM note_links") == [("ana",)]
    new_fact = render_atomic_facts(("Ya no hay enlaces.",), "r-two", (0,), "2026-10-17")
    write(repo, "project.md", note("odyssey", "project", new_fact, name="Odyssey"))
    assert index.refresh_notes(repo, SCHEMA, KeywordEmbedder(), note_ids=("odyssey",)) == 1
    assert rows(index, "SELECT locator FROM note_facts") == [("r-two:0",)]
    assert rows(index, "SELECT * FROM note_fact_links") == []
    assert rows(index, "SELECT * FROM note_links") == []
    rebuilt = ContextIndex(tmp_path / "rebuilt.sqlite3")
    rebuilt.rebuild(repo, SCHEMA, KeywordEmbedder())
    tables = (
        "note_attributes",
        "note_aliases",
        "note_facts",
        "note_fact_links",
        "note_links",
        "note_mentions",
    )
    for table in tables:
        assert rows(index, f"SELECT * FROM {table} ORDER BY 1,2") == rows(
            rebuilt, f"SELECT * FROM {table} ORDER BY 1,2"
        )
    # Deleted Notes cannot leave stale alias, fact, or links behind.
    write(repo, "project.md", note("odyssey", "project", new_fact, name="Odyssey", deleted=True))
    index.refresh_notes(repo, SCHEMA, KeywordEmbedder(), note_ids=("odyssey",))
    for table in tables:
        assert not rows(
            index,
            f"SELECT * FROM {table} WHERE {('note_id' if table in ('note_attributes', 'note_aliases', 'note_facts', 'note_fact_links') else 'source_id')}='odyssey'",
        )


def test_metadata_only_incremental_updates_attribute_without_mutating_fact_or_link(tmp_path):
    (tmp_path / "vault").mkdir()
    repo = VaultRepository(tmp_path / "vault")
    original = note("nerea", "person", "Known body.", name="Nerea", aliases=["Bea"])
    write(repo, "nerea.md", original)
    index = ContextIndex(tmp_path / "context.sqlite3")
    index.rebuild(repo, SCHEMA, KeywordEmbedder())
    old_hash = rows(index, "SELECT source_hash FROM notes WHERE id='nerea'")[0][0]
    changed = Note({**original.metadata, "revision": 2}, original.content)
    write(repo, "nerea.md", changed)
    index.refresh_existing_note(
        repo, SCHEMA, KeywordEmbedder(), path="nerea.md", expected_source_hash=old_hash
    )
    assert rows(index, "SELECT alias FROM note_aliases") == [("Bea",)]
    assert (
        json.loads(
            rows(index, "SELECT value_json FROM note_attributes WHERE field='revision'")[0][0]
        )
        == 2
    )
    assert rows(index, "SELECT * FROM note_facts") == []


def test_legacy_malformed_atomic_marker_is_indexed_as_unverified_not_a_fact(tmp_path):
    (tmp_path / "vault").mkdir()
    repo = VaultRepository(tmp_path / "vault")
    write(repo, "good.md", note("good", "concept", "Original.", name="Good"))
    index = ContextIndex(tmp_path / "context.sqlite3")
    index.rebuild(repo, SCHEMA, KeywordEmbedder())
    write(
        repo,
        "bad.md",
        note("bad", "concept", "<!-- odyssey:fact request=r ordinal=0 -->", name="Bad"),
    )
    index.rebuild(repo, SCHEMA, KeywordEmbedder())
    assert rows(index, "SELECT note_id,status FROM note_fact_integrity ORDER BY note_id") == [
        ("bad", "malformed"),
        ("good", "valid"),
    ]
    assert rows(index, "SELECT locator FROM note_facts WHERE note_id='bad'") == []
    assert rows(index, "SELECT body_text FROM note_projection WHERE note_id='bad'") == [
        ("<!-- odyssey:fact request=r ordinal=0 -->",)
    ]


def test_future_person_properties_are_automatically_projected_without_schema_migration(tmp_path):
    """Birthday/relationship can be added later; no per-property index code is necessary."""
    (tmp_path / "vault").mkdir()
    repo = VaultRepository(tmp_path / "vault")
    schema = json.loads(json.dumps(SCHEMA))
    person_type = next(t for t in schema["types"] if t["id"] == "person")
    person_type["properties"].extend(
        [
            {
                "id": "birthday",
                "value_type": "date",
                "required": False,
                "filterable": True,
                "description": "Birthday if known",
            },
            {
                "id": "relationship",
                "value_type": "string",
                "required": False,
                "filterable": False,
                "description": "User-authored relationship if known",
            },
        ]
    )
    write(
        repo,
        "nerea.md",
        note(
            "nerea",
            "person",
            "Nerea.",
            name="Nerea",
            birthday="1988-03-02",
            relationship="amiga del colegio",
        ),
    )
    index = ContextIndex(tmp_path / "custom-context.sqlite3")
    index.rebuild(repo, schema, KeywordEmbedder())
    attribute = dict(
        rows(index, "SELECT field,value_json FROM note_attributes WHERE note_id='nerea'")
    )
    assert json.loads(attribute["birthday"]) == "1988-03-02"
    assert json.loads(attribute["relationship"]) == "amiga del colegio"
    assert rows(index, "SELECT value FROM properties WHERE field='birthday'") == [("1988-03-02",)]
    # Non-filterable but canonical attributes are still in the complete projection.
    assert rows(index, "SELECT value FROM properties WHERE field='relationship'") == []


def test_version_4_sqlite_requires_rebuild_not_unverified_partial_refresh(tmp_path):
    (tmp_path / "vault").mkdir()
    repo = VaultRepository(tmp_path / "vault")
    write(repo, "nerea.md", note("nerea", "person", "A.", name="Nerea"))
    index = ContextIndex(tmp_path / "context.sqlite3")
    index.rebuild(repo, SCHEMA, KeywordEmbedder())
    with sqlite3.connect(index.path) as db:
        db.execute("UPDATE metadata SET value='4' WHERE key='format_version'")
    write(repo, "nerea.md", note("nerea", "person", "Changed.", name="Nerea"))
    with pytest.raises(ContextIndexError, match="incompatible"):
        index.refresh_notes(repo, SCHEMA, KeywordEmbedder(), note_ids=("nerea",))
    index.rebuild(repo, SCHEMA, KeywordEmbedder())
    assert rows(index, "SELECT fact_text FROM note_facts") == []
    assert rows(index, "SELECT value FROM metadata WHERE key='format_version'") == [("5",)]


def test_name_alias_change_on_incremental_refresh_matches_rebuild(tmp_path):
    (tmp_path / "vault").mkdir()
    repo = VaultRepository(tmp_path / "vault")
    write(repo, "nerea.md", note("nerea", "person", "Person.", name="Nerea", aliases=["Béa"]))
    index = ContextIndex(tmp_path / "incremental.sqlite3")
    index.rebuild(repo, SCHEMA, KeywordEmbedder())
    write(repo, "nerea.md", note("nerea", "person", "Person.", name="Nerea", aliases=["Nere"]))
    index.refresh_notes(repo, SCHEMA, KeywordEmbedder(), note_ids=("nerea",))
    assert rows(index, "SELECT alias,normalized FROM note_aliases") == [("Nere", "nere")]
    rebuilt = ContextIndex(tmp_path / "rebuilt.sqlite3")
    rebuilt.rebuild(repo, SCHEMA, KeywordEmbedder())
    for table in ("note_attributes", "note_aliases", "note_facts", "note_links", "note_mentions"):
        assert rows(index, f"SELECT * FROM {table} ORDER BY 1,2") == rows(
            rebuilt, f"SELECT * FROM {table} ORDER BY 1,2"
        )


def test_fact_temporal_anchors_remain_derived_and_queryable(tmp_path):
    from odyssey_core.temporal import TemporalAnchor

    (tmp_path / "vault").mkdir()
    repo = VaultRepository(tmp_path / "vault")
    anchor = TemporalAnchor.from_value("2026-10-18T15:30:00+02:00")
    content = render_atomic_facts(
        ("Visitaré a Ana.",),
        "r-temporal",
        (2,),
        "2026-10-17T11:40:00+02:00",
        temporal_anchors=((anchor,),),
    )
    write(repo, "nerea.md", note("nerea", "person", content, name="Nerea"))
    index = ContextIndex(tmp_path / "context.sqlite3")
    index.rebuild(repo, SCHEMA, KeywordEmbedder())
    assert rows(index, "SELECT locator, recorded_at, temporal_anchors FROM note_facts") == [
        ("r-temporal:2", "2026-10-17T11:40:00+02:00", '["2026-10-18T15:30:00+02:00"]')
    ]


def test_two_same_basename_targets_leave_fact_links_unresolved(tmp_path):
    (tmp_path / "vault").mkdir()
    repo = VaultRepository(tmp_path / "vault")
    text = render_atomic_facts(("Hablé con [[ana|Ana]].",), "r-ambiguous", (0,), "2026-10-17")
    write(repo, "source.md", note("source", "concept", text, name="Source"))
    write(repo, "group1/ana.md", note("ana-one", "person", "Hi.", name="Ana Uno"))
    write(repo, "group2/ana.md", note("ana-two", "person", "Hi.", name="Ana Dos"))
    index = ContextIndex(tmp_path / "context.sqlite3")
    index.rebuild(repo, SCHEMA, KeywordEmbedder())
    assert rows(index, "SELECT target_id FROM note_fact_links WHERE note_id='source'") == [(None,)]
    assert rows(index, "SELECT target_id FROM note_mentions WHERE target_text='ana'") == [(None,)]
    assert rows(index, "SELECT * FROM note_links WHERE source_id='source'") == []
    # Explicit full path is grounded even with basename collisions.
    updated = render_atomic_facts(
        ("Hablé con [[group1/ana|Ana]].",), "r-resolved", (0,), "2026-10-17"
    )
    write(repo, "source.md", note("source", "concept", updated, name="Source"))
    index.refresh_notes(repo, SCHEMA, KeywordEmbedder(), note_ids=("source",))
    assert rows(index, "SELECT target_id FROM note_fact_links WHERE note_id='source'") == [
        ("ana-one",)
    ]


def test_casefold_colliding_full_paths_do_not_forge_one_link_target(tmp_path):
    (tmp_path / "vault").mkdir()
    repo = VaultRepository(tmp_path / "vault")
    body = render_atomic_facts(("Vi a [[people/ana|Ana]].",), "r-case", (0,), "2026-10-17")
    write(repo, "source.md", note("source", "concept", body, name="Source"))
    write(repo, "people/ana.md", note("ana-lower", "person", "Lower.", name="Ana lower"))
    write(repo, "people/Ana.md", note("ana-upper", "person", "Upper.", name="Ana upper"))
    index = ContextIndex(tmp_path / "context.sqlite3")
    index.rebuild(repo, SCHEMA, KeywordEmbedder())
    assert rows(index, "SELECT target_id FROM note_fact_links WHERE note_id='source'") == [(None,)]
    assert rows(index, "SELECT target_id FROM note_mentions WHERE target_text='people/ana'") == [
        (None,)
    ]
    assert rows(index, "SELECT source_id FROM note_links WHERE source_id='source'") == []


def test_alias_sql_key_follows_same_unicode_whitespace_rule_as_exact_core_identity(tmp_path):
    from odyssey_core.identity import find_exact_entity_candidates_batch

    (tmp_path / "vault").mkdir()
    repo = VaultRepository(tmp_path / "vault")
    write(repo, "nerea.md", note("nerea", "person", ".", name="Nerea", aliases=["Béa   Carrero"]))
    index = ContextIndex(tmp_path / "context.sqlite3")
    index.rebuild(repo, SCHEMA, KeywordEmbedder())
    assert rows(index, "SELECT normalized FROM note_aliases") == [("béa carrero",)]
    result = find_exact_entity_candidates_batch(repo, SCHEMA, (("BÉA CARRERO", "person"),))[0]
    assert len(result) == 1 and result[0].id == "nerea"
