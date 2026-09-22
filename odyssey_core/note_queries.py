"""Read-only, Markdown-grounded query projections for the Notes product surface."""

from __future__ import annotations

import base64
import hashlib
import json
import math
import sqlite3
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from odyssey_core.context import (
    ContextFilter,
    ContextIndex,
    ContextIndexError,
    _filter_definitions,
    _metadata_matches_filters,
    _normalize_filters,
)
from odyssey_core.filtering import supported_filter_operators
from odyssey_core.notes import NoteFormatError, NoteValidationError, parse_note, validate_note
from odyssey_core.semantic import TextEmbedder
from odyssey_core.storage import NoteUnavailableError, VaultRepository

_RANKING_VERSION = "ui2-feed-v1"
_PAGE_SIZE = 20
_MAX_PAGE_SIZE = 40
_CONTEXT_LIMIT = 320
_BACKLINK_OCCURRENCE_LIMIT = 6


class NotesQueryError(ValueError):
    """Indicate invalid Notes input or unavailable canonical knowledge."""


class StaleCursorError(NotesQueryError):
    """Indicate that a cursor cannot safely span the current index generation."""

    code = "STALE_CURSOR"


@dataclass(frozen=True, slots=True)
class NoteCapabilities:
    """Expose canonical note/filter capabilities without duplicating schema semantics."""

    types: tuple[Mapping[str, Any], ...]
    fields: tuple[Mapping[str, Any], ...]


@dataclass(frozen=True, slots=True)
class NoteSummary:
    """Contain a small, currently grounded note representation for result lists."""

    id: str
    name: str
    type: str
    tags: tuple[str, ...]
    created_at: str
    updated_at: str
    properties: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class NotePage:
    """Contain one bounded deterministic Notes result page."""

    mode: str
    sort: str
    ranking_version: str
    as_of: str
    applied_filters: tuple[ContextFilter, ...]
    items: tuple[NoteSummary, ...]
    total: int
    next_cursor: str | None
    unavailable_ids: tuple[str, ...] = ()
    snapshot_offset: int | None = None


@dataclass(frozen=True, slots=True)
class NoteLink:
    """Describe one Core-resolved explicit link in a currently grounded note."""

    target_id: str
    target_name: str
    target_type: str
    label: str
    occurrences: int


@dataclass(frozen=True, slots=True)
class NoteBodySegment:
    """Represent safe visible inline content, with an optional Core-resolved note target."""

    text: str
    target_id: str | None = None
    target_type: str | None = None


@dataclass(frozen=True, slots=True)
class NoteBodyBlock:
    """Represent one bounded presentation block from canonical Markdown body content."""

    kind: str
    segments: tuple[NoteBodySegment, ...]


@dataclass(frozen=True, slots=True)
class NoteDetail:
    """Contain one read-only validated note and its resolved literal links."""

    note: NoteSummary
    body: str
    body_blocks: tuple[NoteBodyBlock, ...]
    links: tuple[NoteLink, ...]


@dataclass(frozen=True, slots=True)
class Backlink:
    """Describe bounded current occurrence evidence from one explicit source note."""

    source: NoteSummary
    occurrences: int
    snippets: tuple[BacklinkOccurrence, ...]
    snippets_truncated: bool


@dataclass(frozen=True, slots=True)
class BacklinkOccurrence:
    """Keep one current body block that explicitly links to the requested target."""

    heading: tuple[NoteBodySegment, ...] | None
    block: NoteBodyBlock


@dataclass(frozen=True, slots=True)
class BacklinkPage:
    """Contain bounded current explicit backlinks for one stable note ID."""

    target_id: str
    items: tuple[Backlink, ...]
    total: int
    next_cursor: str | None


@dataclass(frozen=True, slots=True)
class _GroundedNote:
    """Keep one authoritative note with enough ordering evidence for Notes queries."""

    summary: NoteSummary
    path: str
    source_hash: str
    body: str
    aliases: tuple[str, ...]


def _normalized(value: str) -> str:
    """Return the stable case-insensitive comparison form used by Notes ordering."""
    return " ".join(value.casefold().split())


def _parse_timestamp(value: str) -> datetime:
    """Return one validated lifecycle timestamp normalized to UTC."""
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise NotesQueryError("Canonical lifecycle timestamp is invalid") from error
    if parsed.tzinfo is None:
        raise NotesQueryError("Canonical lifecycle timestamp is not timezone-aware")
    return parsed.astimezone(UTC)


def _json_cursor(value: Mapping[str, Any]) -> str:
    """Encode one opaque, URL-safe cursor without exposing filesystem paths."""
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_cursor(cursor: str) -> Mapping[str, Any]:
    """Decode a bounded cursor or fail closed without accepting arbitrary JSON."""
    if not isinstance(cursor, str) or not cursor or len(cursor) > 4096:
        raise StaleCursorError("STALE_CURSOR")
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
        value = json.loads(raw)
    except (ValueError, json.JSONDecodeError) as error:
        raise StaleCursorError("STALE_CURSOR") from error
    if not isinstance(value, dict):
        raise StaleCursorError("STALE_CURSOR")
    return value


def _link_resolver(
    path_map: Mapping[str, _GroundedNote], basenames: Mapping[str, Sequence[_GroundedNote]]
) -> Callable[[str], _GroundedNote | None]:
    """Return the current Core-owned resolver for safe literal wikilink targets."""

    def resolve(target: str) -> _GroundedNote | None:
        target = target.strip()
        if (
            not target
            or "\\" in target
            or "\x00" in target
            or target.startswith("/")
            or ".." in target.split("/")
        ):
            return None
        target_key = target.removesuffix(".md").casefold()
        resolved = path_map.get(target_key)
        if resolved is None and "/" not in target:
            candidates = basenames.get(target_key, ())
            resolved = candidates[0] if len(candidates) == 1 else None
        return resolved

    return resolve


def _presentation_blocks(
    body: str, resolve: Callable[[str], _GroundedNote | None]
) -> tuple[NoteBodyBlock, ...]:
    """Project the Markdown subset Odyssey writes into safe, readable body blocks.

    Markdown and comments remain canonical storage, but this projection carries only visible text
    and Core-resolved stable IDs. The browser never receives a vault path or has to resolve a link.
    """
    visible = _without_comments(body)
    blocks: list[NoteBodyBlock] = []
    paragraph: list[str] = []

    def flush_paragraph() -> None:
        if not paragraph:
            return
        blocks.append(
            NoteBodyBlock("paragraph", _presentation_segments(" ".join(paragraph), resolve))
        )
        paragraph.clear()

    for raw_line in visible.splitlines():
        line = raw_line.strip()
        if not line:
            flush_paragraph()
            continue
        if heading := _heading_content(line):
            flush_paragraph()
            blocks.append(NoteBodyBlock("heading", _presentation_segments(heading, resolve)))
            continue
        if item := _list_item_content(line):
            flush_paragraph()
            blocks.append(NoteBodyBlock("list_item", _presentation_segments(item, resolve)))
            continue
        paragraph.append(line)
    flush_paragraph()
    return tuple(block for block in blocks if block.segments)


def _presentation_segments(
    text: str, resolve: Callable[[str], _GroundedNote | None]
) -> tuple[NoteBodySegment, ...]:
    """Replace literal wikilinks with visible labels and only Core-resolved stable targets."""
    segments: list[NoteBodySegment] = []
    offset = 0
    while (start := text.find("[[", offset)) >= 0:
        if start > offset:
            segments.append(NoteBodySegment(text[offset:start]))
        end = text.find("]]", start + 2)
        if end < 0:
            segments.append(NoteBodySegment(text[start + 2 :]))
            offset = len(text)
            break
        target, separator, raw_label = text[start + 2 : end].partition("|")
        target = target.strip()
        label = (raw_label if separator else target).strip()
        resolved = resolve(target)
        if resolved is None:
            if label:
                segments.append(NoteBodySegment(label))
        elif label:
            segments.append(NoteBodySegment(label, resolved.summary.id, resolved.summary.type))
        offset = end + 2
    if offset < len(text):
        segments.append(NoteBodySegment(text[offset:]))
    return tuple(segment for segment in segments if segment.text)


def _without_comments(body: str) -> str:
    """Remove storage-only HTML comments without regex backtracking over note text."""
    visible: list[str] = []
    offset = 0
    while (start := body.find("<!--", offset)) >= 0:
        visible.append(body[offset:start])
        end = body.find("-->", start + 4)
        if end < 0:
            return "".join(visible)
        offset = end + 3
    visible.append(body[offset:])
    return "".join(visible)


def _heading_content(line: str) -> str | None:
    """Return visible ATX heading content for Odyssey's bounded Markdown subset."""
    count = len(line) - len(line.lstrip("#"))
    if not 1 <= count <= 6 or len(line) == count or not line[count].isspace():
        return None
    return line[count:].strip() or None


def _list_item_content(line: str) -> str | None:
    """Return visible unordered or ordered list content for the supported Markdown subset."""
    if line[0] in "-*+" and len(line) > 2 and line[1].isspace():
        return line[2:].strip() or None
    digits = len(line) - len(line.lstrip("0123456789"))
    if (
        not digits
        or len(line) <= digits + 1
        or line[digits] not in ".)"
        or not line[digits + 1].isspace()
    ):
        return None
    return line[digits + 2 :].strip() or None


def _aggregate_links(blocks: Sequence[NoteBodyBlock]) -> dict[tuple[str, str], int]:
    """Count presentation-safe resolved link occurrences without reading derived link rows."""
    result: dict[tuple[str, str], int] = {}
    for block in blocks:
        for segment in block.segments:
            if segment.target_id is not None:
                key = (segment.target_id, segment.text)
                result[key] = result.get(key, 0) + 1
    return result


def _backlink_occurrences(
    body: str, target_id: str, resolve: Callable[[str], _GroundedNote | None]
) -> tuple[int, tuple[BacklinkOccurrence, ...], bool]:
    """Project only current visible blocks that literally resolve to one backlink target.

    The index identifies a source candidate and preserves source ordering, but every displayed
    occurrence is re-derived from current canonical Markdown. This prevents a flattened index
    snippet or an unrelated source-note prefix from becoming user-facing knowledge evidence.
    """
    heading: tuple[NoteBodySegment, ...] | None = None
    snippets: list[BacklinkOccurrence] = []
    count = 0
    block_count = 0
    for block in _presentation_blocks(body, resolve):
        if block.kind == "heading":
            heading = block.segments
            continue
        occurrences = sum(segment.target_id == target_id for segment in block.segments)
        if not occurrences:
            continue
        count += occurrences
        block_count += 1
        if len(snippets) < _BACKLINK_OCCURRENCE_LIMIT:
            snippets.append(BacklinkOccurrence(heading, block))
    return count, tuple(snippets), block_count > len(snippets)


def _presentation_text(blocks: Sequence[NoteBodyBlock]) -> str:
    """Flatten visible presentation blocks for bounded non-Markdown detail metadata."""
    return " ".join("".join(segment.text for segment in block.segments) for block in blocks).strip()


class NotesQueryService:
    """Serve bounded Notes projections while retaining Markdown as the only read authority."""

    def __init__(
        self, repository: VaultRepository, schema: dict[str, Any], context_index: ContextIndex
    ) -> None:
        """Bind one authoritative vault, validated schema, and rebuildable index projection."""
        self.repository = repository
        self.schema = schema
        self.context_index = context_index

    def capabilities(self) -> NoteCapabilities:
        """Project canonical types and Core-supported filters for browser controls."""
        fields: list[Mapping[str, Any]] = []
        for field, definition in sorted(_filter_definitions(self.schema).items()):
            applies_to = tuple(
                item["id"]
                for item in self.schema["types"]
                if any(property_["id"] == field for property_ in item["properties"])
            )
            fields.append(
                {
                    "id": field,
                    "value_type": definition["value_type"],
                    "operators": supported_filter_operators(definition),
                    "applies_to": applies_to,
                    "format": definition.get("constraints", {}).get("format"),
                }
            )
        return NoteCapabilities(
            types=tuple({"id": item["id"], "name": item["name"]} for item in self.schema["types"]),
            fields=tuple(fields),
        )

    def query(
        self,
        *,
        mode: str = "feed",
        query: str = "",
        filters: Sequence[ContextFilter | Mapping[str, Any]] = (),
        sort: str = "relevance",
        page_size: int = _PAGE_SIZE,
        cursor: str | None = None,
        snapshot_ids: Sequence[str] = (),
        as_of: str | None = None,
        embedder: TextEmbedder | None = None,
    ) -> NotePage:
        """Return a current, bounded Notes page under the approved deterministic contract.

        Every indexed row selected for a page is reread and validated before it is returned. A
        changed source hash therefore rejects the query rather than allowing SQLite to become a
        knowledge authority.
        """
        if mode not in {"feed", "local", "intelligent", "snapshot"}:
            raise NotesQueryError("Notes query mode is unsupported")
        if sort not in {"relevance", "updated_desc", "created_desc", "created_asc"}:
            raise NotesQueryError("Notes sort is unsupported")
        if (
            not isinstance(page_size, int)
            or isinstance(page_size, bool)
            or not 1 <= page_size <= _MAX_PAGE_SIZE
        ):
            raise NotesQueryError("Notes page size is unsupported")
        if not isinstance(query, str) or len(query.encode("utf-8")) > 4096:
            raise NotesQueryError("Notes query is invalid")
        normalized_filters = _normalize_filters(self.schema, filters, None, ())
        applied = tuple(
            ContextFilter(field, op, value if op != "in" else list(value))
            for field, op, value in normalized_filters
        )
        fingerprint = self._fingerprint(mode, query, applied, sort, snapshot_ids)
        saved_cursor = _decode_cursor(cursor) if cursor is not None else None
        cursor_as_of = saved_cursor.get("as_of") if saved_cursor is not None else None
        current_as_of = (
            as_of
            or (cursor_as_of if isinstance(cursor_as_of, str) else None)
            or datetime.now(UTC).isoformat(timespec="microseconds")
        )
        if mode == "snapshot":
            return self._historical_snapshot_page(
                query=query,
                filters=applied,
                sort=sort,
                page_size=page_size,
                cursor=cursor,
                snapshot_ids=snapshot_ids,
                as_of=current_as_of,
                fingerprint=fingerprint,
            )
        generation, notes = self._grounded_index_notes()
        offset = 0
        if saved_cursor is not None:
            saved = saved_cursor
            if (
                saved.get("v") != 1
                or saved.get("generation") != generation
                or saved.get("fingerprint") != fingerprint
                or saved.get("as_of") != current_as_of
                or not isinstance(saved.get("offset"), int)
                or saved["offset"] < 0
            ):
                raise StaleCursorError("STALE_CURSOR")
            offset = saved["offset"]
        selected = [note for note in notes if self._matches(note, normalized_filters)]
        if mode == "local":
            selected = self._local_rank(selected, query)
        elif mode == "intelligent":
            selected = self._intelligent_rank(selected, query, embedder)
        else:
            selected = self._feed_rank(selected, current_as_of)
        selected = self._sort(selected, sort, current_as_of, mode)
        page = selected[offset : offset + page_size]
        next_offset = offset + len(page)
        next_cursor = (
            _json_cursor(
                {
                    "v": 1,
                    "generation": generation,
                    "fingerprint": fingerprint,
                    "as_of": current_as_of,
                    "offset": next_offset,
                }
            )
            if next_offset < len(selected)
            else None
        )
        return NotePage(
            mode,
            sort,
            _RANKING_VERSION,
            current_as_of,
            applied,
            tuple(item.summary for item in page),
            len(selected),
            next_cursor,
        )

    def _historical_snapshot_page(
        self,
        *,
        query: str,
        filters: tuple[ContextFilter, ...],
        sort: str,
        page_size: int,
        cursor: str | None,
        snapshot_ids: Sequence[str],
        as_of: str,
        fingerprint: str,
    ) -> NotePage:
        """Replay durable stable-ID membership from current Markdown without recomputation.

        A saved result set is not a current search. It therefore bypasses index ranking and filters
        entirely, retaining missing IDs as unavailable positions while only current canonical
        Markdown supplies details for members that still exist.
        """
        del query
        if (
            len(snapshot_ids) > 64
            or len(set(snapshot_ids)) != len(snapshot_ids)
            or not all(isinstance(item, str) and item for item in snapshot_ids)
        ):
            raise NotesQueryError("Historical result snapshot is invalid")
        notes = self._grounded_vault_notes()
        generation = hashlib.sha256(
            "".join(f"{item.summary.id}:{item.source_hash}" for item in notes.values()).encode()
        ).hexdigest()
        offset = 0
        if cursor is not None:
            saved = _decode_cursor(cursor)
            if (
                saved.get("v") != 1
                or saved.get("generation") != generation
                or saved.get("fingerprint") != fingerprint
                or saved.get("as_of") != as_of
                or not isinstance(saved.get("offset"), int)
                or saved["offset"] < 0
            ):
                raise StaleCursorError("STALE_CURSOR")
            offset = saved["offset"]
        ids = tuple(snapshot_ids)
        position_ids = ids[offset : offset + page_size]
        available = tuple(notes[item].summary for item in position_ids if item in notes)
        unavailable = tuple(item for item in position_ids if item not in notes)
        next_offset = offset + len(position_ids)
        next_cursor = (
            _json_cursor(
                {
                    "v": 1,
                    "generation": generation,
                    "fingerprint": fingerprint,
                    "as_of": as_of,
                    "offset": next_offset,
                }
            )
            if next_offset < len(ids)
            else None
        )
        return NotePage(
            "snapshot",
            sort,
            _RANKING_VERSION,
            as_of,
            filters,
            available,
            len(ids),
            next_cursor,
            unavailable,
            offset,
        )

    def detail(self, note_id: str) -> NoteDetail:
        """Return one current note with safe presentation blocks and resolved literal links."""
        notes = self._grounded_vault_notes()
        current = notes.get(note_id)
        if current is None:
            raise NotesQueryError("Note is unavailable")
        path_map = {note.path.removesuffix(".md").casefold(): note for note in notes.values()}
        basenames: dict[str, list[_GroundedNote]] = {}
        for note in notes.values():
            basenames.setdefault(
                note.path.removesuffix(".md").rsplit("/", 1)[-1].casefold(), []
            ).append(note)
        resolve = _link_resolver(path_map, basenames)
        body_blocks = _presentation_blocks(current.body, resolve)
        links = _aggregate_links(body_blocks)
        return NoteDetail(
            current.summary,
            _presentation_text(body_blocks),
            body_blocks,
            tuple(
                NoteLink(
                    target_id,
                    notes[target_id].summary.name,
                    notes[target_id].summary.type,
                    label,
                    count,
                )
                for (target_id, label), count in sorted(
                    links.items(),
                    key=lambda item: (
                        _normalized(notes[item[0][0]].summary.name),
                        item[0][0],
                        item[0][1],
                    ),
                )
            ),
        )

    def backlinks(
        self, target_id: str, *, page_size: int = _PAGE_SIZE, cursor: str | None = None
    ) -> BacklinkPage:
        """Return explicit current backlinks, ordered by reliable source-note chronology."""
        if not isinstance(page_size, int) or not 1 <= page_size <= _MAX_PAGE_SIZE:
            raise NotesQueryError("Notes page size is unsupported")
        generation, all_notes = self._grounded_index_notes()
        if target_id not in {note.summary.id for note in all_notes}:
            raise NotesQueryError("Note is unavailable")
        offset = 0
        fingerprint = hashlib.sha256(f"backlinks:{target_id}".encode()).hexdigest()
        if cursor is not None:
            saved = _decode_cursor(cursor)
            if (
                saved.get("generation") != generation
                or saved.get("fingerprint") != fingerprint
                or not isinstance(saved.get("offset"), int)
            ):
                raise StaleCursorError("STALE_CURSOR")
            offset = saved["offset"]
        source_ids: set[str] = set()
        try:
            with sqlite3.connect(f"file:{self.context_index.path}?mode=ro", uri=True) as connection:
                rows = connection.execute(
                    "SELECT source_id FROM note_links WHERE target_id = ?",
                    (target_id,),
                )
                source_ids.update(str(source_id) for (source_id,) in rows)
        except sqlite3.Error as error:
            raise NotesQueryError("Notes index is unavailable") from error
        by_id = {note.summary.id: note for note in all_notes}
        path_map = {note.path.removesuffix(".md").casefold(): note for note in all_notes}
        basenames: dict[str, list[_GroundedNote]] = {}
        for note in all_notes:
            basenames.setdefault(
                note.path.removesuffix(".md").rsplit("/", 1)[-1].casefold(), []
            ).append(note)
        resolve = _link_resolver(path_map, basenames)
        evidence = []
        for source_id in source_ids:
            source = by_id.get(source_id)
            if source is None:
                continue
            count, snippets, snippets_truncated = _backlink_occurrences(
                source.body, target_id, resolve
            )
            if count:
                evidence.append((source, count, snippets, snippets_truncated))
        ranked = sorted(
            evidence,
            key=lambda item: (
                -_parse_timestamp(item[0].summary.updated_at).timestamp(),
                _normalized(item[0].summary.name),
                item[0].summary.id,
            ),
        )
        page = ranked[offset : offset + page_size]
        next_offset = offset + len(page)
        next_cursor = (
            _json_cursor(
                {
                    "v": 1,
                    "generation": generation,
                    "fingerprint": fingerprint,
                    "offset": next_offset,
                }
            )
            if next_offset < len(ranked)
            else None
        )
        return BacklinkPage(
            target_id,
            tuple(
                Backlink(note.summary, count, snippets, snippets_truncated)
                for note, count, snippets, snippets_truncated in page
            ),
            len(ranked),
            next_cursor,
        )

    def _grounded_index_notes(self) -> tuple[str, list[_GroundedNote]]:
        """Load index ordering evidence only after every row agrees with current Markdown."""
        try:
            with sqlite3.connect(f"file:{self.context_index.path}?mode=ro", uri=True) as connection:
                markers = dict(connection.execute("SELECT key, value FROM metadata"))
                if markers.get("format_version") != "4":
                    raise NotesQueryError("Notes index requires rebuild")
                rows = list(
                    connection.execute(
                        "SELECT id, path, type, primary_name, source_hash, tags FROM notes ORDER BY id"
                    )
                )
        except sqlite3.Error as error:
            raise NotesQueryError("Notes index is unavailable") from error
        notes: list[_GroundedNote] = []
        digester = hashlib.sha256(_RANKING_VERSION.encode())
        for note_id, path, note_type, name, source_hash, encoded_tags in rows:
            try:
                raw = self.repository.read_text(path)
                note = parse_note(raw)
                validate_note(note, self.schema)
            except (NoteUnavailableError, NoteFormatError, NoteValidationError) as error:
                raise NotesQueryError("Indexed note is unavailable or invalid") from error
            if (
                note.metadata.get("deleted") is True
                or hashlib.sha256(raw.encode("utf-8")).hexdigest() != source_hash
            ):
                raise NotesQueryError("Notes index is stale; rebuild is required")
            if (note.metadata.get("id"), note.metadata.get("type"), note.metadata.get("name")) != (
                note_id,
                note_type,
                name,
            ):
                raise NotesQueryError("Indexed note identity disagrees with Markdown")
            tags = tuple(note.metadata.get("tags", []))
            if json.loads(encoded_tags) != list(tags):
                raise NotesQueryError("Notes index tag projection disagrees with Markdown")
            summary = NoteSummary(
                note_id,
                name,
                note_type,
                tags,
                str(note.metadata["created_at"]),
                str(note.metadata["updated_at"]),
                {
                    key: value
                    for key, value in note.metadata.items()
                    if key
                    not in {
                        "id",
                        "name",
                        "type",
                        "created_at",
                        "updated_at",
                        "created_by",
                        "updated_by",
                        "revision",
                        "schema_version",
                        "deleted",
                        "aliases",
                        "tags",
                    }
                },
            )
            notes.append(
                _GroundedNote(
                    summary,
                    path,
                    source_hash,
                    note.content,
                    tuple(note.metadata.get("aliases", [])),
                )
            )
            digester.update(note_id.encode())
            digester.update(source_hash.encode())
        return digester.hexdigest(), notes

    def _grounded_vault_notes(self) -> dict[str, _GroundedNote]:
        """Read every active canonical note for one current link-resolution boundary."""
        result: dict[str, _GroundedNote] = {}
        for path in self.repository.list_markdown_paths():
            try:
                raw = self.repository.read_text(path)
                note = parse_note(raw)
                validate_note(note, self.schema)
            except (NoteUnavailableError, NoteFormatError, NoteValidationError) as error:
                raise NotesQueryError("Canonical note is unavailable or invalid") from error
            if note.metadata.get("deleted") is True:
                continue
            note_id = str(note.metadata["id"])
            if note_id in result:
                raise NotesQueryError("Duplicate canonical note identity")
            result[note_id] = _GroundedNote(
                NoteSummary(
                    note_id,
                    str(note.metadata["name"]),
                    str(note.metadata["type"]),
                    tuple(note.metadata.get("tags", [])),
                    str(note.metadata["created_at"]),
                    str(note.metadata["updated_at"]),
                    {
                        key: value
                        for key, value in note.metadata.items()
                        if key
                        not in {
                            "id",
                            "name",
                            "type",
                            "created_at",
                            "updated_at",
                            "created_by",
                            "updated_by",
                            "revision",
                            "schema_version",
                            "deleted",
                            "aliases",
                            "tags",
                        }
                    },
                ),
                path,
                hashlib.sha256(raw.encode()).hexdigest(),
                note.content,
                tuple(note.metadata.get("aliases", [])),
            )
        return result

    def _matches(
        self, note: _GroundedNote, filters: Sequence[tuple[str, str, tuple[str | int, ...]]]
    ) -> bool:
        """Apply the shared Core filter contract to current canonical metadata."""
        metadata = dict(note.summary.properties) | {
            "type": note.summary.type,
            "tags": list(note.summary.tags),
            "created_at": note.summary.created_at,
            "updated_at": note.summary.updated_at,
            "aliases": list(note.aliases),
        }
        return _metadata_matches_filters(metadata, filters, _filter_definitions(self.schema))

    def _feed_rank(self, notes: list[_GroundedNote], as_of: str) -> list[_GroundedNote]:
        """Apply the fixed UI-2 activity/connected-degree relevance calculation."""
        now = _parse_timestamp(as_of)
        own = {note.summary.id: self._activity_band(note.summary.updated_at, now) for note in notes}
        neighbors: dict[str, set[str]] = {note.summary.id: set() for note in notes}
        try:
            with sqlite3.connect(f"file:{self.context_index.path}?mode=ro", uri=True) as connection:
                for source, target in connection.execute(
                    "SELECT source_id, target_id FROM note_links"
                ):
                    if source in neighbors and target in neighbors:
                        neighbors[source].add(target)
                        neighbors[target].add(source)
        except sqlite3.Error as error:
            raise NotesQueryError("Notes index is unavailable") from error
        scores = {
            note.summary.id: 100 * own[note.summary.id]
            + 5 * max((own[item] for item in neighbors[note.summary.id]), default=0)
            + min(4, int(math.log2(1 + len(neighbors[note.summary.id]))))
            for note in notes
        }
        return sorted(
            notes,
            key=lambda note: (
                -scores[note.summary.id],
                -_parse_timestamp(note.summary.updated_at).timestamp(),
                -_parse_timestamp(note.summary.created_at).timestamp(),
                _normalized(note.summary.name),
                note.summary.id,
            ),
        )

    @staticmethod
    def _activity_band(updated_at: str, now: datetime) -> int:
        """Map lifecycle age to the approved clamped deterministic activity band."""
        age = max(0.0, (now - _parse_timestamp(updated_at)).total_seconds()) / 86400
        return 4 if age < 7 else 3 if age < 30 else 2 if age < 90 else 1 if age < 365 else 0

    def _local_rank(self, notes: list[_GroundedNote], query: str) -> list[_GroundedNote]:
        """Apply the five approved zero-provider lexical tiers and stable tie ordering."""
        tokens = tuple(token for token in _normalized(query).split() if token)
        if not tokens:
            return self._feed_rank(notes, datetime.now(UTC).isoformat())
        scored: list[tuple[int, int, _GroundedNote]] = []
        needle = " ".join(tokens)
        for note in notes:
            name, aliases = (
                _normalized(note.summary.name),
                tuple(_normalized(item) for item in note.aliases),
            )
            property_text = " ".join(str(value) for value in note.summary.properties.values())
            tier = 0
            evidence = 0
            text = _normalized(
                " ".join((note.summary.name, *note.aliases, *note.summary.tags, property_text))
            )
            if name == needle:
                tier, evidence = 5, 1
            elif needle in aliases:
                tier, evidence = 4, 1
            elif name.startswith(needle) or any(alias.startswith(needle) for alias in aliases):
                tier, evidence = 3, 1
            elif all(token in text for token in tokens):
                tier, evidence = 2, sum(text.count(token) for token in tokens)
            elif all(token in _normalized(note.body) for token in tokens):
                tier, evidence = 1, sum(_normalized(note.body).count(token) for token in tokens)
            if tier:
                scored.append((tier, min(evidence, 32), note))
        return [
            entry[2]
            for entry in sorted(
                scored,
                key=lambda entry: (
                    -entry[0],
                    -entry[1],
                    -_parse_timestamp(entry[2].summary.updated_at).timestamp(),
                    _normalized(entry[2].summary.name),
                    entry[2].summary.id,
                ),
            )
        ]

    def _intelligent_rank(
        self, notes: list[_GroundedNote], query: str, embedder: TextEmbedder | None
    ) -> list[_GroundedNote]:
        """Use existing whole-note cosine evidence only for one explicit semantic action."""
        if not query.strip() or embedder is None:
            raise NotesQueryError("Intelligent Notes search requires an explicit semantic query")
        try:
            candidates = self.context_index.find_candidates(
                self.schema, embedder, query, limit=_CONTEXT_LIMIT
            )
        except (ContextIndexError, ValueError) as error:
            raise NotesQueryError("Intelligent Notes search is unavailable") from error
        similarity = {item.id: item.similarity for item in candidates}
        exact = _normalized(query)
        return sorted(
            (note for note in notes if note.summary.id in similarity),
            key=lambda note: (
                0
                if _normalized(note.summary.name) == exact
                else 1
                if exact in {_normalized(alias) for alias in note.aliases}
                else 2,
                -similarity[note.summary.id],
                -_parse_timestamp(note.summary.updated_at).timestamp(),
                _normalized(note.summary.name),
                note.summary.id,
            ),
        )

    def _sort(
        self, notes: list[_GroundedNote], sort: str, as_of: str, mode: str
    ) -> list[_GroundedNote]:
        """Apply explicit chronological sorts without altering relevance order."""
        if sort == "relevance":
            return notes
        reverse = sort != "created_asc"
        value = (
            (lambda note: _parse_timestamp(note.summary.updated_at).timestamp())
            if sort == "updated_desc"
            else (lambda note: _parse_timestamp(note.summary.created_at).timestamp())
        )
        return sorted(
            notes,
            key=lambda note: (
                (-value(note)) if reverse else value(note),
                _normalized(note.summary.name),
                note.summary.id,
            ),
        )

    @staticmethod
    def _fingerprint(
        mode: str,
        query: str,
        filters: Sequence[ContextFilter],
        sort: str,
        snapshot_ids: Sequence[str],
    ) -> str:
        """Return a canonical request identity used to reject mixed-generation pages."""
        value = {
            "mode": mode,
            "query": query.strip(),
            "filters": [
                {"field": item.field, "op": item.op, "value": item.value} for item in filters
            ],
            "sort": sort,
            "snapshot_ids": list(snapshot_ids),
        }
        return hashlib.sha256(
            json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
        ).hexdigest()
