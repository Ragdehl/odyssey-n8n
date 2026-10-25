"""Bounded read-only evidence pages for post-approval schema enrichment.

This is NOT a classifier, a job scheduler or a mutation pathway. Use one canonical
vault and its composed schema. A future orchestrator may interpret the returned
facts, but must get independent authorization and E3/CAS to write anything.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Literal

from odyssey_core.atomic_facts import AtomicFactError, parse_atomic_facts
from odyssey_core.notes import NoteFormatError, NoteValidationError, parse_note, validate_note
from odyssey_core.storage import VaultRepository

ScanKind = Literal["discover_type", "backfill_property"]
_MAX_PAGE = 25
_MAX_FACTS_PER_NOTE = 128
_MAX_FACT_TEXT = 4000


class SchemaRetrospectionError(ValueError):
    """Unreliable scan evidence; never silently continue or write."""


@dataclass(frozen=True, slots=True)
class RetrospectionCursor:
    inventory_hash: str
    offset: int


@dataclass(frozen=True, slots=True)
class SourceFact:
    locator: str
    text: str


@dataclass(frozen=True, slots=True)
class SourceNote:
    note_id: str
    note_name: str
    note_type: str
    path: str
    source_hash: str
    revision: int
    facts: tuple[SourceFact, ...]
    # Legacy plain Markdown is not silently treated as E3-linkable evidence.
    legacy_coverage_unverified: bool


@dataclass(frozen=True, slots=True)
class RetrospectionPage:
    kind: ScanKind
    target_type_id: str
    property_id: str | None
    scanned_paths: int
    eligible_notes: tuple[SourceNote, ...]
    skipped_existing_values: int
    next_cursor: RetrospectionCursor | None
    inventory_hash: str


def _contains_unmarked_content(body: str, facts: tuple[Any, ...]) -> bool:
    """Conservatively flag real text outside Core's addressable atomic facts."""
    remaining = body
    for fact in reversed(facts):
        remaining = remaining[: fact.start] + remaining[fact.end :]
    return any(line.strip() and not line.startswith("# Added ") for line in remaining.splitlines())


def scan_schema_sources(
    *,
    repository: VaultRepository,
    schema: dict[str, Any],
    kind: ScanKind,
    target_type_id: str,
    property_id: str | None = None,
    limit: int = 20,
    cursor: RetrospectionCursor | None = None,
) -> RetrospectionPage:
    """Read ≤25 physical notes, preserving source hash and atomic fact locators.

    The cursor binds the whole vault file-version inventory. Even if a file
    changes without changing its name, subsequent pages reject as stale. Each
    selected file is checked before/after parsing, so a mixed-time batch is
    never silently considered complete. No network, model or write occurs.
    """
    if (
        not isinstance(repository, VaultRepository)
        or type(limit) is not int
        or not 1 <= limit <= _MAX_PAGE
        or kind not in ("discover_type", "backfill_property")
        or not isinstance(target_type_id, str)
    ):
        raise SchemaRetrospectionError("Schema scan arguments invalid")
    try:
        types = {item["id"]: item for item in schema["types"]}
    except (KeyError, TypeError):
        raise SchemaRetrospectionError("Composed schema unavailable") from None
    if target_type_id not in types:
        raise SchemaRetrospectionError("Unknown schema scan target")
    if kind == "discover_type":
        if property_id is not None:
            raise SchemaRetrospectionError("Type discovery does not scan properties")
    elif not isinstance(property_id, str) or property_id not in {
        item["id"] for item in types[target_type_id]["properties"]
    }:
        raise SchemaRetrospectionError("Backfill property does not exist on target type")

    versions = repository.note_version_snapshot()
    paths = sorted(versions)
    inventory_hash = hashlib.sha256(
        json.dumps([(path, versions[path]) for path in paths], sort_keys=True).encode()
    ).hexdigest()
    offset = 0
    if cursor is not None:
        if (
            not isinstance(cursor, RetrospectionCursor)
            or cursor.inventory_hash != inventory_hash
            or type(cursor.offset) is not int
            or not 0 <= cursor.offset < len(paths)
        ):
            raise SchemaRetrospectionError("Stale or invalid scan cursor")
        offset = cursor.offset

    candidates: list[SourceNote] = []
    existing_count = 0
    selected = paths[offset : offset + limit]
    seen_ids: set[str] = set()
    for path in selected:
        if repository.file_version(path) != versions[path]:
            raise SchemaRetrospectionError("Canonical source changed during scan")
        raw = repository.read_text(path)
        try:
            note = parse_note(raw)
            validate_note(note, schema)
        except (NoteFormatError, NoteValidationError) as error:
            raise SchemaRetrospectionError("Canonical source invalid during scan") from error
        if repository.file_version(path) != versions[path]:
            raise SchemaRetrospectionError("Canonical source changed during scan")
        if note.metadata.get("deleted") is True:
            continue
        note_id = note.metadata["id"]
        if not isinstance(note_id, str) or note_id in seen_ids:
            raise SchemaRetrospectionError("Duplicate canonical source identity")
        seen_ids.add(note_id)
        if kind == "discover_type" and note.metadata["type"] == target_type_id:
            # An entity already represented by the newly activated type must
            # not be rediscovered as a new candidate from its own note.
            continue
        if kind == "backfill_property":
            if note.metadata["type"] != target_type_id:
                continue
            if property_id in note.metadata:  # an explicit empty/null value is still user-owned
                existing_count += 1
                continue
        try:
            parsed_facts = parse_atomic_facts(note.content)
        except AtomicFactError as error:
            raise SchemaRetrospectionError("Malformed fact evidence during scan") from error
        if len(parsed_facts) > _MAX_FACTS_PER_NOTE or any(
            len(fact.text) > _MAX_FACT_TEXT for fact in parsed_facts
        ):
            raise SchemaRetrospectionError("Fact evidence exceeds safe scan budget")
        candidates.append(
            SourceNote(
                note_id=note_id,
                note_name=str(note.metadata["name"]),
                note_type=str(note.metadata["type"]),
                path=path,
                source_hash=hashlib.sha256(raw.encode("utf-8")).hexdigest(),
                revision=int(note.metadata["revision"]),
                facts=tuple(SourceFact(fact.locator, fact.text) for fact in parsed_facts),
                legacy_coverage_unverified=_contains_unmarked_content(note.content, parsed_facts),
            )
        )
    # One page may overlap other writers; never publish mixed-time evidence
    # even if the selected notes themselves didn't change.
    if repository.note_version_snapshot() != versions:
        raise SchemaRetrospectionError("Vault changed during scan")
    next_offset = offset + len(selected)
    return RetrospectionPage(
        kind=kind,
        target_type_id=target_type_id,
        property_id=property_id,
        scanned_paths=len(selected),
        eligible_notes=tuple(candidates),
        skipped_existing_values=existing_count,
        next_cursor=(
            RetrospectionCursor(inventory_hash, next_offset) if next_offset < len(paths) else None
        ),
        inventory_hash=inventory_hash,
    )
