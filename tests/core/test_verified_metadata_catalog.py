"""Fail-closed request-local verified Core metadata, never SQLite as authority."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from odyssey_core.identity import (
    ExactEntityLookupError,
    find_exact_entity_candidates_batch,
)
from odyssey_core.reference_preflight import ReferencePreflightError, _find_existing_identity
from odyssey_core.storage import VaultRepository
from odyssey_core.temporal import CalendarDayCollisionError, CalendarDayRepository
from odyssey_core.verified_metadata_catalog import scoped_verified_metadata_catalog
from tests.core.test_temporal import canonical_note


@pytest.fixture
def catalog_fixture(tmp_path):
    root = tmp_path / "vault"
    root.mkdir()
    repo = VaultRepository(root)
    schema = json.loads(
        (Path(__file__).resolve().parents[2] / "config/note-schema.json").read_text()
    )
    repo.create_text(
        "nerea.md", canonical_note(note_id="nerea-note", note_type="person", name="Nerea")
    )
    return root, repo, schema


def lookup(repo, schema, name="Nerea"):
    return find_exact_entity_candidates_batch(repo, schema, ((name, "person"),))[0]


def test_catalog_matches_baseline_and_reuses_verified_rows_without_rereading(catalog_fixture):
    _root, repo, schema = catalog_fixture
    baseline = lookup(repo, schema)
    original_read = repo.read_text
    reads = []

    def monitored_read(path):
        reads.append(path)
        return original_read(path)

    repo.read_text = monitored_read
    with repo.scoped_unchanged_reads(), scoped_verified_metadata_catalog():
        assert lookup(repo, schema) == baseline
        initial = len(reads)
        assert initial == 1
        assert lookup(repo, schema) == baseline
        assert _find_existing_identity(repo, schema, "nerea-note") == ("nerea.md", "Nerea")
        days = CalendarDayRepository(repo, schema)
        for _ in range(4):
            assert not days.resolve("2026-10-17").materialized
        assert len(reads) == initial, "Multiple filtered Core lookups must reuse verified facts"
    assert lookup(repo, schema) == baseline
    assert len(reads) > initial, "The next delivery must not inherit cache authority"


def test_external_edit_changes_alias_name_and_prevents_false_negative(catalog_fixture):
    root, repo, schema = catalog_fixture
    target = root / "nerea.md"
    with repo.scoped_unchanged_reads(), scoped_verified_metadata_catalog():
        assert len(lookup(repo, schema)) == 1
        original = target.read_text()
        target.write_text(original.replace('name: "Nerea"', 'name: "Nerea Nueva"'))
        assert not lookup(repo, schema)
        assert len(lookup(repo, schema, "Nerea Nueva")) == 1
        assert _find_existing_identity(repo, schema, "nerea-note") == ("nerea.md", "Nerea Nueva")


def test_new_misplaced_date_claim_detected_after_prior_negative(catalog_fixture):
    _root, repo, schema = catalog_fixture
    days = CalendarDayRepository(repo, schema)
    with repo.scoped_unchanged_reads(), scoped_verified_metadata_catalog():
        assert not days.resolve("2026-10-17").materialized
        repo.create_text(
            "misplaced.md",
            canonical_note(
                note_id="date:2026-10-17",
                note_type="calendar_day",
                name="Unexpected",
                properties={"date": "2026-10-17"},
            ),
        )
        with pytest.raises(CalendarDayCollisionError, match="claimed elsewhere"):
            days.resolve("2026-10-17")


def test_external_change_reuses_mtime_but_does_not_reuse_name(catalog_fixture):
    root, repo, schema = catalog_fixture
    file = root / "nerea.md"
    with repo.scoped_unchanged_reads(), scoped_verified_metadata_catalog():
        assert len(lookup(repo, schema)) == 1
        stamp = file.stat().st_mtime_ns
        current = file.read_text()
        # Same byte length, mtime deliberately restored, ctime differs.
        file.write_text(current.replace('name: "Nerea"', 'name: "Nerio"'))
        os.utime(file, ns=(stamp, stamp))
        assert lookup(repo, schema) == ()
        assert len(lookup(repo, schema, "Nerio")) == 1


def test_corrupt_note_after_valid_catalog_fails_closed(catalog_fixture):
    root, repo, schema = catalog_fixture
    with repo.scoped_unchanged_reads(), scoped_verified_metadata_catalog():
        assert lookup(repo, schema)
        (root / "broken.md").write_text("---\nid: missing-close", encoding="utf-8")
        with pytest.raises(ExactEntityLookupError):
            lookup(repo, schema)
        with pytest.raises(ReferencePreflightError):
            _find_existing_identity(repo, schema, "nerea-note")
        with pytest.raises(CalendarDayCollisionError):
            CalendarDayRepository(repo, schema).resolve("2026-10-17")


def test_external_symlink_swap_never_uses_stale_verified_identity(catalog_fixture, tmp_path):
    root, repo, schema = catalog_fixture
    with repo.scoped_unchanged_reads(), scoped_verified_metadata_catalog():
        assert lookup(repo, schema)
        (root / "nerea.md").unlink()
        outside = tmp_path / "outside.md"
        outside.write_text(canonical_note(note_id="fake", note_type="person", name="Nerea"))
        (root / "nerea.md").symlink_to(outside)
        assert not lookup(repo, schema)
        with pytest.raises(ReferencePreflightError):
            _find_existing_identity(repo, schema, "nerea-note")


def test_duplicated_stable_id_in_new_note_is_never_hidden(catalog_fixture):
    _root, repo, schema = catalog_fixture
    with repo.scoped_unchanged_reads(), scoped_verified_metadata_catalog():
        assert _find_existing_identity(repo, schema, "nerea-note")
        repo.create_text(
            "duplicate.md",
            canonical_note(note_id="nerea-note", note_type="person", name="Nerea Dos"),
        )
        with pytest.raises(ReferencePreflightError, match="duplicated"):
            _find_existing_identity(repo, schema, "nerea-note")


def test_schema_modified_in_place_never_reuses_previous_validation(catalog_fixture):
    _root, repo, schema = catalog_fixture
    with repo.scoped_unchanged_reads(), scoped_verified_metadata_catalog():
        assert lookup(repo, schema)
        schema["schema_version"] = 99
        with pytest.raises(ExactEntityLookupError):
            lookup(repo, schema)
