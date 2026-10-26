"""Autonomous exact-property enrichment without per-note human approvals.

Uses a real, temporary local Git vault and the existing E3 mutation gate.
No provider calls, PROD filesystem writes, or real user notes.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from odyssey_core.git_history import GitHistoryRecorder
from odyssey_core.notes import Note, parse_note, serialize_note
from odyssey_core.schema_auto_backfill import (
    AutoBackfillError,
    AutomaticPropertyBackfill,
    choose_explicit_backfill,
    summarize_automatic_backfill,
)
from odyssey_core.schema_retrospection import scan_schema_sources
from odyssey_core.storage import VaultRepository

ROOT = Path(__file__).resolve().parents[2]
NOW = "2026-10-26T12:00:00+00:00"
ACTOR = {"human": None, "app": "odyssey-auto-backfill"}


def _git(vault: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=vault,
        text=True,
        capture_output=True,
        check=True,
        timeout=20,
    )
    return result.stdout.strip()


def _schema(kind: str = "string") -> dict:
    schema = json.loads((ROOT / "config/note-schema.json").read_text())
    person = next(row for row in schema["types"] if row["id"] == "person")
    person["properties"].append(
        {
            "id": "profesion",
            "value_type": kind,
            "description": "Profession actuelle",
            "required": False,
            "filterable": True,
        }
    )
    return schema


def _vault(tmp_path: Path, facts: list[str], *, kind: str = "string"):
    vault = tmp_path / "vault"
    vault.mkdir()
    schema = _schema(kind)
    for i, fact in enumerate(facts):
        note = Note(
            {
                "id": f"persona-{i}",
                "name": f"Persona {i}",
                "type": "person",
                "created_at": NOW,
                "updated_at": NOW,
                "created_by": ACTOR,
                "updated_by": ACTOR,
                "revision": 1,
                "schema_version": 3,
                "aliases": [],
                "tags": [],
            },
            "# Added 26-10-2026\n- "
            + fact
            + f"\n<!-- odyssey:fact request=source{i} ordinal=0 -->\n",
        )
        (vault / f"{i}.md").write_text(serialize_note(note))
    _git(vault, "init", "-q")
    _git(vault, "add", ".")
    _git(
        vault,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@localhost",
        "commit",
        "-q",
        "-m",
        "baseline",
    )
    repository = VaultRepository(vault)
    page = scan_schema_sources(
        repository=repository,
        schema=schema,
        kind="backfill_property",
        target_type_id="person",
        property_id="profesion",
        limit=25,
    )
    return repository, schema, page.eligible_notes


def test_automatic_batch_updates_only_supported_explicit_facts_and_produces_undo_history(tmp_path):
    repo, schema, sources = _vault(
        tmp_path,
        [
            "Profesión: Médica",
            "profesion: Arquitecta",
            "Profesion: Ingeniera",
            "La profesión de Berta es médica",
            "profesion: arquitecta\n- profesión: abogada",  # one fact with two lines, not trusted
            "Profesión: profesora",
        ],
    )
    before = {path: repo.read_text(path) for path in repo.list_markdown_paths()}
    service = AutomaticPropertyBackfill(
        repository=repo, schema=schema, history=GitHistoryRecorder(repo.root)
    )
    receipts = service.apply_batch(
        sources=sources,
        type_id="person",
        property_id="profesion",
        actor=ACTOR,
        now=NOW,
        request_prefix="auto-20261026",
    )
    assert [receipt.status for receipt in receipts] == [
        "updated",
        "updated",
        "updated",
        "no_evidence",
        "ambiguous",
        "updated",
    ]
    assert summarize_automatic_backfill(receipts).updated == 4
    assert summarize_automatic_backfill(receipts).ambiguous == 1
    assert summarize_automatic_backfill(receipts).no_evidence == 1
    assert summarize_automatic_backfill(receipts).undo_commits == 4
    assert all(receipt.undo_commit for receipt in receipts if receipt.status == "updated")
    changed = [path for path in repo.list_markdown_paths() if repo.read_text(path) != before[path]]
    assert changed == ["0.md", "1.md", "2.md", "5.md"]
    assert all(parse_note(repo.read_text(path)).metadata["revision"] == 2 for path in changed)
    assert all(
        parse_note(repo.read_text(path)).content == parse_note(before[path]).content
        for path in changed
    )
    assert parse_note(repo.read_text("0.md")).metadata["profesion"] == "Médica"
    assert _git(repo.root, "status", "--porcelain") == ""
    assert len(_git(repo.root, "log", "--format=%H").splitlines()) == 5
    # The baseline stays available for undo; writes do not delete raw facts.
    assert _git(repo.root, "show", "HEAD~4:0.md") == before["0.md"].rstrip("\n")


def test_auto_exact_evidence_never_uses_legacy_or_ambiguous_values(tmp_path):
    repo, schema, sources = _vault(
        tmp_path,
        [
            "Profesión: 10",
            "Profesión: Médica",
            "Profesión: Médica",
        ],
        kind="integer",
    )
    decision = [
        choose_explicit_backfill(
            source,
            type_id="person",
            definition=next(
                p
                for t in schema["types"]
                if t["id"] == "person"
                for p in t["properties"]
                if p["id"] == "profesion"
            ),
        )
        for source in sources
    ]
    assert [d.status for d in decision] == ["auto", "ambiguous", "ambiguous"]
    service = AutomaticPropertyBackfill(
        repository=repo, schema=schema, history=GitHistoryRecorder(repo.root)
    )
    receipts = service.apply_batch(
        sources=sources,
        type_id="person",
        property_id="profesion",
        actor=ACTOR,
        now=NOW,
        request_prefix="auto-integer",
    )
    assert [r.status for r in receipts] == ["updated", "ambiguous", "ambiguous"]
    assert parse_note(repo.read_text("0.md")).metadata["profesion"] == 10
    assert "profesion" not in parse_note(repo.read_text("1.md")).metadata


def test_changed_target_is_not_overwritten_and_replay_does_not_write_again(tmp_path):
    repo, schema, sources = _vault(tmp_path, ["Profesión: Médica"])
    service = AutomaticPropertyBackfill(
        repository=repo, schema=schema, history=GitHistoryRecorder(repo.root)
    )
    first = service.apply(
        source=sources[0],
        type_id="person",
        property_id="profesion",
        actor=ACTOR,
        now=NOW,
        request_id="auto-one",
    )
    assert first.status == "updated"
    assert (
        service.apply(
            source=sources[0],
            type_id="person",
            property_id="profesion",
            actor=ACTOR,
            now=NOW,
            request_id="auto-one-replay",
        ).status
        == "stale"
    )
    assert len(_git(repo.root, "log", "--format=%H").splitlines()) == 2


def test_uncommitted_source_and_missing_history_block_autonomy_before_writing(tmp_path):
    repo, schema, sources = _vault(tmp_path, ["Profesión: Médica"])
    before = repo.read_text("0.md")
    (repo.root / "0.md").write_text(before + "\nchanged")
    service = AutomaticPropertyBackfill(
        repository=repo, schema=schema, history=GitHistoryRecorder(repo.root)
    )
    assert (
        service.apply(
            source=sources[0],
            type_id="person",
            property_id="profesion",
            actor=ACTOR,
            now=NOW,
            request_id="blocked",
        ).status
        == "stale"
    )
    assert (repo.root / "0.md").read_text() == before + "\nchanged"
    (repo.root / "0.md").write_text(before)
    # A history root that is not a valid Git repository must prevent all writes.
    fake_root = tmp_path / "not-git"
    fake_root.mkdir()
    service.history = GitHistoryRecorder(fake_root)
    with pytest.raises(AutoBackfillError, match="undo history"):
        service.apply(
            source=sources[0],
            type_id="person",
            property_id="profesion",
            actor=ACTOR,
            now=NOW,
            request_id="blocked-history",
        )
    assert repo.read_text("0.md") == before


def test_stale_source_fact_and_duplicate_batch_identity_fail_closed(tmp_path):
    repo, schema, sources = _vault(tmp_path, ["Profesión: Médica"])
    service = AutomaticPropertyBackfill(
        repository=repo, schema=schema, history=GitHistoryRecorder(repo.root)
    )
    compromised = replace(sources[0], facts=())
    assert (
        service.apply(
            source=compromised,
            type_id="person",
            property_id="profesion",
            actor=ACTOR,
            now=NOW,
            request_id="stale-evidence",
        ).status
        == "no_evidence"
    )
    before = repo.read_text("0.md")
    with pytest.raises(AutoBackfillError, match="Repeated source"):
        service.apply_batch(
            sources=(sources[0], sources[0]),
            type_id="person",
            property_id="profesion",
            actor=ACTOR,
            now=NOW,
            request_prefix="duplicate",
        )
    assert repo.read_text("0.md") == before


def test_explicit_fast_path_never_overrides_a_later_free_prose_correction(tmp_path):
    repo, schema, sources = _vault(tmp_path, ["Profesión: médica"])
    from dataclasses import replace

    from odyssey_core.schema_retrospection import SourceFact

    # Full marked note context may indicate a later change, even when that
    # other fact is not in key: value form. A one-label regex must abstain.
    source = replace(
        sources[0],
        facts=(
            sources[0].facts[0],
            SourceFact("later:0", "Ya no ejerce la medicina, cambió de trabajo."),
        ),
    )
    definition = next(
        p
        for kind in schema["types"]
        if kind["id"] == "person"
        for p in kind["properties"]
        if p["id"] == "profesion"
    )
    assert (
        choose_explicit_backfill(source, type_id="person", definition=definition).status
        == "ambiguous"
    )
    service = AutomaticPropertyBackfill(
        repository=repo, schema=schema, history=GitHistoryRecorder(repo.root)
    )
    before = repo.read_text("0.md")
    assert (
        service.apply(
            source=source,
            type_id="person",
            property_id="profesion",
            actor=ACTOR,
            now=NOW,
            request_id="must-not-overwrite",
        ).status
        == "ambiguous"
    )
    assert repo.read_text("0.md") == before


def test_backfill_fails_closed_on_same_revision_edit_inside_persistence_boundary(
    tmp_path, monkeypatch
):
    from odyssey_core.notes import parse_note

    repo, schema, sources = _vault(tmp_path, ["Profesión: médica"])
    original = repo.read_text("0.md")
    manual = original.replace("Profesión: médica", "La profesión está en disputa")
    assert parse_note(manual).metadata["revision"] == sources[0].revision
    writer = AutomaticPropertyBackfill(
        repository=repo, schema=schema, history=GitHistoryRecorder(repo.root)
    )
    original_replace = repo.replace_text

    def concurrent_edit(path, text, **kwargs):
        (repo.root / path).write_text(manual)
        return original_replace(path, text, **kwargs)

    monkeypatch.setattr(repo, "replace_text", concurrent_edit)
    receipt = writer.apply(
        source=sources[0],
        type_id="person",
        property_id="profesion",
        actor=ACTOR,
        now=NOW,
        request_id="race-same-revision",
    )
    assert receipt.status == "stale"
    assert repo.read_text("0.md") == manual
    assert "profesion" not in parse_note(repo.read_text("0.md")).metadata
