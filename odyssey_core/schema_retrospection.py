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
from odyssey_core.storage.repository import MAX_PHYSICAL_VERSION_PATHS

ScanKind = Literal["discover_type", "backfill_property"]
_MAX_PAGE = 25
_MAX_FACTS_PER_NOTE = 128
_MAX_FACT_TEXT = 4000
_MAX_NOTE_BYTES = 2_000_000


class SchemaRetrospectionError(ValueError):
    """Unreliable scan evidence; never silently continue or write."""


@dataclass(frozen=True, slots=True)
class RetrospectionCursor:
    inventory_hash: str
    offset: int
    # Bind each page to exactly one query+schema, not only the physical vault.
    context_hash: str = ""


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
    # No E3 locator. Can inform human/AI discovery but never authorize a link.
    legacy_text: str = ""


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
    # Provenance needed to assemble several pages without accepting a rewind.
    input_cursor: RetrospectionCursor | None
    context_hash: str
    source_note_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RetrospectionProgress:
    """Bounded read-only scan receipt; not a background/durable job."""

    kind: ScanKind
    target_type_id: str
    property_id: str | None
    inventory_hash: str
    context_hash: str
    scanned_paths: int
    eligible_notes: int
    skipped_existing_values: int
    legacy_sources: int
    seen_note_ids: frozenset[str]
    next_cursor: RetrospectionCursor | None
    # An operational SQLite receipt deliberately does not materialize its
    # entire 50k identity set. It MUST NOT be reused as a public accumulator
    # proof; only the owner can validate that external manifest.
    identity_proof: Literal["materialized", "external"] = "materialized"

    @property
    def complete(self) -> bool:
        return self.next_cursor is None


_MAX_PROGRESS_IDS = 10000
# Bounded *transient* whole-vault scan, separate from durable 10k-ID scan
# checkpoints and the much smaller 10k-candidate mutation journal.
_MAX_STAGED_SCAN_IDS = MAX_PHYSICAL_VERSION_PATHS
_MAX_STAGED_ID_BYTES = 12_000_000


def accumulate_schema_scan(
    page: RetrospectionPage, previous: RetrospectionProgress | None = None
) -> RetrospectionProgress:
    """Validate durable or public scan progress within its 10k identity budget."""
    return _accumulate_schema_scan(page, previous, max_ids=_MAX_PROGRESS_IDS)


def _accumulate_schema_scan(
    page: RetrospectionPage,
    previous: RetrospectionProgress | None = None,
    *,
    max_ids: int,
) -> RetrospectionProgress:
    """Validate page order and uniqueness across one entire scanned inventory.

    The public caller uses the original 10k bound. Only an unpublished,
    fully revalidated private staging transaction may use up to 50k physical
    IDs; the durable mutation plan still enforces its independent 10k cap.
    """
    if type(max_ids) is not int or not _MAX_PROGRESS_IDS <= max_ids <= _MAX_STAGED_SCAN_IDS:
        raise SchemaRetrospectionError("Invalid scan identity budget")
    if not isinstance(page, RetrospectionPage) or (
        page.input_cursor is not None and not isinstance(page.input_cursor, RetrospectionCursor)
    ):
        raise SchemaRetrospectionError("Invalid scan progress page")
    if previous is None:
        if page.input_cursor is not None:
            raise SchemaRetrospectionError("Progress must start at first page")
        seen: frozenset[str] = frozenset()
        scanned = eligible = skipped = legacy = 0
    else:
        if (
            not isinstance(previous, RetrospectionProgress)
            or previous.identity_proof != "materialized"
            or previous.complete
            or page.input_cursor != previous.next_cursor
            or page.kind != previous.kind
            or page.target_type_id != previous.target_type_id
            or page.property_id != previous.property_id
            or page.inventory_hash != previous.inventory_hash
            or page.context_hash != previous.context_hash
        ):
            raise SchemaRetrospectionError("Stale or out-of-order scan progress")
        seen = previous.seen_note_ids
        scanned = previous.scanned_paths
        eligible = previous.eligible_notes
        skipped = previous.skipped_existing_values
        legacy = previous.legacy_sources
    current = page.source_note_ids
    if (
        not 0 <= page.scanned_paths <= _MAX_PAGE
        or (
            page.scanned_paths == 0
            and (
                previous is not None
                or page.next_cursor is not None
                or page.eligible_notes
                or page.source_note_ids
                or page.skipped_existing_values
            )
        )
        or len(current) > page.scanned_paths
        or len(current) != len(set(current))
        or any(not isinstance(identifier, str) or not identifier for identifier in current)
        or seen.intersection(current)
        or len(seen) + len(current) > max_ids
        or page.skipped_existing_values < 0
        or page.scanned_paths < len(page.eligible_notes) + page.skipped_existing_values
        or (
            page.next_cursor is not None
            and (
                page.next_cursor.inventory_hash != page.inventory_hash
                or page.next_cursor.context_hash != page.context_hash
                or page.next_cursor.offset != scanned + page.scanned_paths
            )
        )
    ):
        raise SchemaRetrospectionError("Duplicate or inconsistent scan progress")
    return RetrospectionProgress(
        kind=page.kind,
        target_type_id=page.target_type_id,
        property_id=page.property_id,
        inventory_hash=page.inventory_hash,
        context_hash=page.context_hash,
        scanned_paths=scanned + page.scanned_paths,
        eligible_notes=eligible + len(page.eligible_notes),
        skipped_existing_values=skipped + page.skipped_existing_values,
        legacy_sources=legacy + sum(n.legacy_coverage_unverified for n in page.eligible_notes),
        seen_note_ids=seen.union(current),
        next_cursor=page.next_cursor,
    )


def _unmarked_text(body: str, facts: tuple[Any, ...]) -> str:
    """Expose remaining source text, with NO fabricated fact locator."""
    remaining = body
    for fact in reversed(facts):
        remaining = remaining[: fact.start] + remaining[fact.end :]
    # Capture-date headings alone are not facts. Other legacy Markdown and
    # headings remain as source evidence, not a claim of atomic provenance.
    return "\n".join(
        line for line in remaining.splitlines() if line.strip() and not line.startswith("# Added ")
    ).strip()


def _validated_source_note(*, path: str, raw: str, note: Any) -> SourceNote:
    """Reconstruct the same bounded canonical E3 evidence for scans and restarts."""
    try:
        parsed_facts = parse_atomic_facts(note.content)
    except AtomicFactError as error:
        raise SchemaRetrospectionError("Malformed fact evidence during scan") from error
    if len(parsed_facts) > _MAX_FACTS_PER_NOTE or any(
        len(fact.text) > _MAX_FACT_TEXT for fact in parsed_facts
    ):
        raise SchemaRetrospectionError("Fact evidence exceeds safe scan budget")
    locators = [fact.locator for fact in parsed_facts]
    if len(locators) != len(set(locators)):
        raise SchemaRetrospectionError("Duplicate canonical fact locator")
    legacy_text = _unmarked_text(note.content, parsed_facts)
    if len(legacy_text) > 12000:
        raise SchemaRetrospectionError("Unmarked Markdown exceeds safe scan budget")
    return SourceNote(
        note_id=note.metadata["id"],
        note_name=str(note.metadata["name"]),
        note_type=str(note.metadata["type"]),
        path=path,
        source_hash=hashlib.sha256(raw.encode("utf-8")).hexdigest(),
        revision=int(note.metadata["revision"]),
        facts=tuple(SourceFact(fact.locator, fact.text) for fact in parsed_facts),
        legacy_coverage_unverified=bool(legacy_text),
        legacy_text=legacy_text,
    )


def reload_staged_backfill_source(
    *,
    repository: VaultRepository,
    schema: dict[str, Any],
    path: str,
    note_id: str,
    source_hash: str,
    revision: int,
    type_id: str,
    property_id: str,
) -> SourceNote:
    """Reconstruct a staged source without trusting saved Markdown snippets.

    The durable plan holds only physical path, canonical ID, revision and SHA.
    This recheck happens per note after other staged notes have been changed.
    It must NOT reuse a whole-inventory scan cursor after canonical writes.
    """
    if (
        not isinstance(repository, VaultRepository)
        or not isinstance(path, str)
        or not isinstance(note_id, str)
        or not isinstance(source_hash, str)
        or not isinstance(revision, int)
        or type(revision) is not int
    ):
        raise SchemaRetrospectionError("Invalid saved source reference")
    try:
        before = repository.file_version(path)
        if int(before[3]) > _MAX_NOTE_BYTES:
            raise SchemaRetrospectionError("Staged source too large")
        raw = repository.read_text(path)
        if len(raw.encode("utf-8")) > _MAX_NOTE_BYTES:
            raise SchemaRetrospectionError("Staged source too large")
        note = parse_note(raw)
        validate_note(note, schema)
        after = repository.file_version(path)
    except (OSError, ValueError, NoteFormatError, NoteValidationError) as error:
        raise SchemaRetrospectionError("Staged canonical source unavailable") from error
    if (
        before != after
        or note.metadata.get("deleted") is True
        or note.metadata.get("id") != note_id
        or note.metadata.get("type") != type_id
        or property_id in note.metadata
        or note.metadata.get("revision") != revision
        or hashlib.sha256(raw.encode("utf-8")).hexdigest() != source_hash
    ):
        raise SchemaRetrospectionError("Staged canonical source changed")
    return _validated_source_note(path=path, raw=raw, note=note)


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
    """Read a bounded page with mandatory live whole-inventory freshness checks.

    In contrast to the journal-only preliminary helper, no caller can pass
    a saved snapshot to bypass fresh vault enumeration and per-page rechecks.
    """
    return _scan_schema_sources_page(
        repository=repository,
        schema=schema,
        kind=kind,
        target_type_id=target_type_id,
        property_id=property_id,
        limit=limit,
        cursor=cursor,
    )


@dataclass(frozen=True, slots=True)
class _StagedScanInventory:
    """One transaction's provisional inventory; NEVER valid outside full end recheck.

    This is intentionally consumed only by LocalBackfillJob.stage. Every
    public scan remains responsible for its own physical pre/post proof.
    """

    versions: dict[str, tuple[object, ...]]
    paths: tuple[str, ...]
    inventory_hash: str


def _staged_scan_inventory(repository: VaultRepository) -> _StagedScanInventory:
    versions = repository.note_version_snapshot()
    paths = tuple(sorted(versions))
    fingerprint = hashlib.sha256(
        json.dumps([(path, versions[path]) for path in paths], sort_keys=True).encode()
    ).hexdigest()
    return _StagedScanInventory(versions, paths, fingerprint)


@dataclass(frozen=True, slots=True)
class _StagedScanPage:
    """Private indexed portion of a physically attested scan manifest."""

    offset: int
    total_paths: int
    files: tuple[tuple[str, tuple[object, ...]], ...]
    inventory_hash: str


def _scan_schema_sources_page(
    *,
    repository: VaultRepository,
    schema: dict[str, Any],
    kind: ScanKind,
    target_type_id: str,
    property_id: str | None = None,
    limit: int = 20,
    cursor: RetrospectionCursor | None = None,
    _staged_inventory: _StagedScanInventory | _StagedScanPage | None = None,
    _identity_witness: list[tuple[str, str, bool]] | None = None,
) -> RetrospectionPage:
    """Internal staged-page builder; results are PROVISIONAL with inventory.

    This bypass is strictly for LocalBackfillJob.stage, which MUST check a
    fresh full vault snapshot after processing every page and BEFORE publishing
    any plan. The public scan_schema_sources always verifies each page.
    Every selected source is still checked before/after parsing, and Core
    revalidates source CAS for each later physical write.
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

    # The journal stages all pages without writing, so it can reuse one
    # private snapshot and perform ONE final full-vault equality check before
    # publishing its plan. Standalone/interactive scans still verify the
    # entire vault at the start and end of EVERY page as before.
    if _staged_inventory is None:
        # The public API always obtains a fresh physical inventory per page.
        current = _staged_scan_inventory(repository)
    elif isinstance(_staged_inventory, (_StagedScanInventory, _StagedScanPage)):
        current = _staged_inventory
    else:
        raise SchemaRetrospectionError("Invalid private staging inventory")
    page_manifest = current if isinstance(current, _StagedScanPage) else None
    if page_manifest is not None:
        versions = dict(page_manifest.files)
        path_count = page_manifest.total_paths
        if (
            not 0 <= page_manifest.offset < path_count <= _MAX_STAGED_SCAN_IDS
            or not 1 <= len(page_manifest.files) <= limit
            or page_manifest.offset + len(page_manifest.files) > path_count
            or len(versions) != len(page_manifest.files)
        ):
            raise SchemaRetrospectionError("Invalid staged page manifest")
    else:
        versions = current.versions
        paths = current.paths
        path_count = len(paths)
    inventory_hash = current.inventory_hash
    # A single vault can be queried for multiple schema operations. A cursor
    # from one query must never silently skip files in another query.
    context_hash = hashlib.sha256(
        json.dumps(
            {"kind": kind, "target": target_type_id, "property": property_id, "schema": schema},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    offset = 0
    if cursor is not None:
        if (
            not isinstance(cursor, RetrospectionCursor)
            or cursor.inventory_hash != inventory_hash
            or cursor.context_hash != context_hash
            or type(cursor.offset) is not int
            or not 0 <= cursor.offset < path_count
        ):
            raise SchemaRetrospectionError("Stale or invalid scan cursor")
        offset = cursor.offset

    candidates: list[SourceNote] = []
    existing_count = 0
    if page_manifest is not None:
        if offset != page_manifest.offset:
            raise SchemaRetrospectionError("Staged scan cursor/manifest mismatch")
        selected = [path for path, _ in page_manifest.files]
    else:
        selected = paths[offset : offset + limit]
    seen_ids: set[str] = set()
    source_ids: list[str] = []
    for path in selected:
        # A physical version snapshot supplies the file size before parsing.
        # Reject oversized files BEFORE read_text allocates their full body.
        if int(versions[path][3]) > _MAX_NOTE_BYTES:
            raise SchemaRetrospectionError("Canonical source exceeds safe note size")
        if repository.file_version(path) != versions[path]:
            raise SchemaRetrospectionError("Canonical source changed during scan")
        raw = repository.read_text(path)
        if len(raw.encode("utf-8")) > _MAX_NOTE_BYTES:
            raise SchemaRetrospectionError("Canonical source exceeds safe note size")
        try:
            note = parse_note(raw)
            validate_note(note, schema)
        except (NoteFormatError, NoteValidationError) as error:
            raise SchemaRetrospectionError("Canonical source invalid during scan") from error
        if repository.file_version(path) != versions[path]:
            raise SchemaRetrospectionError("Canonical source changed during scan")
        # Private in-process witness for a write-free staging transaction.
        # Unlike the public source_note_ids list, it includes deleted notes
        # with positional path/ID/state and is NEVER returned to the browser.
        if _identity_witness is not None:
            _identity_witness.append(
                (path, note.metadata["id"], note.metadata.get("deleted") is True)
            )
        if note.metadata.get("deleted") is True:
            continue
        note_id = note.metadata["id"]
        if not isinstance(note_id, str) or note_id in seen_ids:
            raise SchemaRetrospectionError("Duplicate canonical source identity")
        seen_ids.add(note_id)
        source_ids.append(note_id)
        if kind == "backfill_property":
            if note.metadata["type"] != target_type_id:
                continue
            if property_id in note.metadata:  # an explicit empty/null value is still user-owned
                existing_count += 1
                continue
        candidates.append(_validated_source_note(path=path, raw=raw, note=note))
    # One page may overlap other writers; never publish mixed-time evidence
    # even if the selected notes themselves didn't change.
    if _staged_inventory is None and repository.note_version_snapshot() != versions:
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
            RetrospectionCursor(inventory_hash, next_offset, context_hash)
            if next_offset < path_count
            else None
        ),
        inventory_hash=inventory_hash,
        input_cursor=cursor,
        context_hash=context_hash,
        source_note_ids=tuple(source_ids),
    )
