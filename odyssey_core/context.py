"""Deterministic local retrieval of grounded knowledge from atomic Odyssey notes."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import sqlite3
import tempfile
from array import array
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Any, cast

from odyssey_core.filtering import supported_filter_operators
from odyssey_core.notes import NoteFormatError, NoteValidationError, parse_note, validate_note
from odyssey_core.semantic import TextEmbedder
from odyssey_core.storage import VaultRepository

_INDEX_MARKERS = {"application": "odyssey", "format": "context-index", "format_version": "3"}
_TECHNICAL_METADATA = frozenset(
    {"id", "created_at", "updated_at", "created_by", "updated_by", "revision", "schema_version"}
)
_WIKILINK_PATTERN = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")


def _humanize_wikilinks(markdown: str) -> str:
    """Replace wikilinks with their visible label or target text."""
    return _WIKILINK_PATTERN.sub(lambda match: (match.group(2) or match.group(1)).strip(), markdown)


def _normalized_vector(values: Sequence[float]) -> tuple[float, ...]:
    """Return a finite unit vector suitable for exact cosine comparison."""
    vector = tuple(float(value) for value in values)
    if not vector or not all(math.isfinite(value) for value in vector):
        raise ContextIndexError("Embedding runtime returned an invalid vector")
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        raise ContextIndexError("Embedding runtime returned a zero vector")
    return tuple(value / norm for value in vector)


def _vector_blob(vector: Sequence[float]) -> bytes:
    """Serialize a normalized vector as portable float32 SQLite data."""
    values = array("f", vector)
    if values.itemsize != 4:
        raise ContextIndexError("Platform does not provide 32-bit float arrays")
    return values.tobytes()


def _blob_vector(blob: bytes) -> array[float]:
    """Deserialize one SQLite float32 vector blob."""
    values: array[float] = array("f")
    values.frombytes(blob)
    return values


class ContextIndexError(RuntimeError):
    """Indicate that the derived context index cannot be built or used safely."""


class ContextRetrievalError(RuntimeError):
    """Indicate that ranked context could not be grounded in the authoritative vault."""


@dataclass(frozen=True, slots=True)
class ContextFilter:
    """Represent one schema-validated deterministic retrieval constraint."""

    field: str
    op: str
    value: Any


@dataclass(frozen=True, slots=True)
class ContextItem:
    """Expose one authoritative note selected as knowledge context."""

    id: str
    path: str
    primary_name: str
    type: str
    tags: tuple[str, ...]
    metadata: Mapping[str, Any]
    content: str
    similarity: float


@dataclass(frozen=True, slots=True)
class ContextPackage:
    """Contain an interpreted retrieval query and its ranked grounded notes."""

    query: str
    items: tuple[ContextItem, ...]


@dataclass(frozen=True, slots=True)
class _ContextCandidate:
    id: str
    path: str
    type: str
    primary_name: str
    source_hash: str
    similarity: float


def build_context_retrieval_text(note: Any, path: str) -> str:
    """Build human-readable general-knowledge embedding text for one validated note.

    Args:
        note: Canonically validated Odyssey note.
        path: Vault-relative Markdown path used for the filename-derived name.

    Returns:
        Projection containing useful metadata, controlled tags, body text, and readable links.

    Raises:
        ValueError: If the path or required note metadata is unusable.
    """
    if not isinstance(path, str) or not path.endswith(".md"):
        raise ValueError("Context projection requires a Markdown note path")
    primary_name = PurePosixPath(path).stem
    note_type = note.metadata.get("type")
    if not primary_name or not isinstance(note_type, str):
        raise ValueError("Context projection requires a validated note type")
    lines = [f"Name: {primary_name}"]
    aliases = note.metadata.get("aliases")
    if isinstance(aliases, list) and aliases:
        lines.append("Aliases: " + ", ".join(cast(list[str], aliases)))
    lines.append(f"Type: {note_type}")
    tags = note.metadata.get("tags")
    if isinstance(tags, list) and tags:
        lines.append("Tags: " + ", ".join(cast(list[str], tags)))
    for key in sorted(note.metadata):
        if key in _TECHNICAL_METADATA or key in {"aliases", "tags", "type"}:
            continue
        value = note.metadata[key]
        rendered = ", ".join(str(item) for item in value) if isinstance(value, list) else str(value)
        lines.append(f"{key.replace('_', ' ').title()}: {rendered}")
    body = _humanize_wikilinks(note.content).strip()
    if body:
        lines.append(body)
    return "\n".join(lines)


def _canonical_values(schema: dict[str, Any], key: str) -> tuple[str, ...]:
    try:
        values = tuple(sorted(definition["id"] for definition in schema[key]))
    except (KeyError, TypeError):
        raise ValueError("Supplied schema is not a usable canonical schema") from None
    if not values or not all(isinstance(value, str) for value in values):
        raise ValueError("Supplied schema is not a usable canonical schema")
    return values


def _filter_definitions(schema: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Return schema-declared fields that the retrieval layer may filter."""
    definitions: dict[str, dict[str, Any]] = {}
    try:
        universal = schema["metadata_fields"]
        types = schema["types"]
    except (KeyError, TypeError):
        raise ValueError("Supplied schema is not a usable canonical schema") from None
    for definition in universal:
        if definition.get("filterable") is True:
            definitions[definition["id"]] = definition
    for note_type in types:
        for definition in note_type["properties"]:
            if definition.get("filterable") is True:
                field_id = definition["id"]
                existing = definitions.get(field_id)
                if existing is not None and (
                    existing.get("value_type") != definition.get("value_type")
                    or existing.get("constraints", {}) != definition.get("constraints", {})
                ):
                    raise ValueError(f"Schema declares conflicting filter field: {field_id!r}")
                definitions[field_id] = definition
    if not definitions:
        raise ValueError("Schema declares no filterable fields")
    return definitions


def _filter_registry(definitions: Mapping[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Serialize filter definitions deterministically for index compatibility checks."""
    return [
        {
            "field": field,
            "value_type": definition["value_type"],
            "constraints": definition.get("constraints", {}),
        }
        for field, definition in sorted(definitions.items())
    ]


def _is_date(value: Any) -> bool:
    """Return whether a value is a normalized ISO calendar date."""
    if not isinstance(value, str) or len(value) != 10:
        return False
    try:
        return date.fromisoformat(value).isoformat() == value
    except ValueError:
        return False


def _is_date_time(value: Any) -> bool:
    """Return whether a value is a timezone-aware ISO date-time."""
    if not isinstance(value, str) or "T" not in value:
        return False
    try:
        return datetime.fromisoformat(value).tzinfo is not None
    except ValueError:
        return False


def _canonical_subtypes(schema: dict[str, Any]) -> set[str]:
    """Return all subtype IDs from their authoritative per-type registries."""
    try:
        return {subtype["id"] for note_type in schema["types"] for subtype in note_type["subtypes"]}
    except (KeyError, TypeError):
        raise ValueError("Supplied schema is not a usable canonical schema") from None


def _normalize_property_value(
    definition: dict[str, Any], value: Any, *, allow_date_boundary: bool = False
) -> str | int:
    """Validate and normalize one indexed or queried property value.

    Date-times become fixed-width UTC text so SQLite lexical ordering is chronological. Integers
    remain integers for bound query parameters and are stored canonically by SQLite's TEXT column.
    """
    value_type = definition["value_type"]
    constraints = definition.get("constraints", {})
    if value_type == "integer":
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError("Filter value must be an integer")
        return value
    if value_type == "date":
        if not _is_date(value):
            raise ValueError("Filter date value must be YYYY-MM-DD")
        return value
    if value_type in {"string", "array[string]"}:
        if not isinstance(value, str):
            raise ValueError("Filter value must be text")
        if constraints.get("format") != "date-time":
            return value
        if _is_date(value):
            if not allow_date_boundary:
                raise ValueError("Date-only values are valid only for date-time range bounds")
            parsed = datetime.combine(date.fromisoformat(value), time.min, tzinfo=UTC)
        elif _is_date_time(value):
            parsed = datetime.fromisoformat(value).astimezone(UTC)
        else:
            raise ValueError("Filter date-time value must be timezone-aware ISO text")
        return parsed.isoformat(timespec="microseconds").replace("+00:00", "Z")
    raise ValueError(f"Unsupported filter field value type: {value_type!r}")


def _validate_filter_value(
    definition: dict[str, Any], op: str, value: Any
) -> tuple[str | int, ...]:
    """Validate one filter value and return its canonical SQLite text values."""
    value_type = definition["value_type"]
    values = value if op == "in" else (value,)
    if op == "in" and (
        isinstance(value, (str, bytes)) or not isinstance(value, Sequence) or not value
    ):
        raise ValueError("Filter 'in' requires a non-empty sequence")
    if op == "contains" and value_type != "array[string]":
        raise ValueError("Filter 'contains' requires an array[string] field")
    if op != "contains" and value_type == "array[string]":
        raise ValueError("Array fields support only the 'contains' operator")
    result: list[str | int] = []
    for item in values:
        result.append(
            _normalize_property_value(
                definition, item, allow_date_boundary=op in {"gt", "gte", "lt", "lte"}
            )
        )
    return tuple(result)


def _normalize_filters(
    schema: dict[str, Any],
    filters: Sequence[ContextFilter | Mapping[str, Any]],
    note_type: str | None,
    required_tags: Sequence[str],
) -> tuple[tuple[str, str, tuple[str | int, ...]], ...]:
    """Validate convenience and structured filters into safe SQL inputs."""
    definitions = _filter_definitions(schema)
    if isinstance(filters, (str, bytes)) or not isinstance(filters, Sequence):
        raise ValueError("Context filters must be a sequence")
    raw_filters: list[ContextFilter | Mapping[str, Any]] = list(filters)
    if note_type is not None:
        raw_filters.append(ContextFilter("type", "eq", note_type))
    if isinstance(required_tags, (str, bytes)) or not isinstance(required_tags, Sequence):
        raise ValueError("Required tags must be a sequence of canonical tag IDs")
    required_tag_values = tuple(required_tags)
    if not all(isinstance(tag, str) for tag in required_tag_values):
        raise ValueError("Required tags must be a sequence of canonical tag IDs")
    if len(set(required_tag_values)) != len(required_tag_values):
        raise ValueError("Required tags must not contain duplicates")
    raw_filters.extend(ContextFilter("tags", "contains", tag) for tag in required_tag_values)
    canonical_types = set(_canonical_values(schema, "types"))
    canonical_tags = set(_canonical_values(schema, "tags"))
    canonical_subtypes = _canonical_subtypes(schema)
    normalized: list[tuple[str, str, tuple[str | int, ...]]] = []
    for raw in raw_filters:
        if isinstance(raw, ContextFilter):
            field, op, value = raw.field, raw.op, raw.value
        elif isinstance(raw, Mapping):
            field, op, value = raw.get("field"), raw.get("op"), raw.get("value")
        else:
            raise ValueError("Each context filter must be a ContextFilter or mapping")
        if not isinstance(field, str) or field not in definitions:
            raise ValueError(f"Unknown or unsupported context filter field: {field!r}")
        definition = definitions[field]
        valid_operators = set(supported_filter_operators(definition))
        if not isinstance(op, str) or op not in valid_operators:
            raise ValueError(f"Unsupported operator {op!r} for context field {field!r}")
        values = _validate_filter_value(definition, op, value)
        registry = definition.get("constraints", {}).get("registry")
        if registry == "types" and any(item not in canonical_types for item in values):
            raise ValueError(f"Unknown canonical note type in filter: {values}")
        if registry == "tags" and any(item not in canonical_tags for item in values):
            raise ValueError(f"Unknown canonical tag in filter: {values}")
        if registry == "types[].subtypes" and any(
            item not in canonical_subtypes for item in values
        ):
            raise ValueError(f"Unknown canonical subtype in filter: {values}")
        normalized.append((field, op, values))
    return tuple(normalized)


def validate_context_filters(
    schema: dict[str, Any],
    filters: Sequence[ContextFilter | Mapping[str, Any]],
    *,
    note_type: str | None = None,
) -> tuple[tuple[str, str, tuple[str | int, ...]], ...]:
    """Validate RequestPlan-compatible filters with Phase 13's retrieval rules.

    Args:
        schema: Canonical schema defining supported deterministic fields.
        filters: Structured filter objects emitted by a caller.
        note_type: Optional canonical type restriction from the retrieval plan.

    Returns:
        Canonical filter tuples accepted by the Phase 13 retrieval boundary.

    Raises:
        ValueError: If a field, operator, value, or type restriction is unsupported.
    """
    return _normalize_filters(schema, filters, note_type, ())


def find_filtered_note_ids(
    repository: VaultRepository,
    schema: dict[str, Any],
    filters: Sequence[ContextFilter | Mapping[str, Any]],
    *,
    note_type: str | None = None,
) -> frozenset[str]:
    """Return current validated note IDs satisfying deterministic selection filters.

    This is the authoritative-vault counterpart to the context index's filter contract.  It is
    intended for identity-sensitive callers that must restrict candidates without treating ranked
    context retrieval as identity evidence.

    Args:
        repository: Authoritative Markdown vault to inspect.
        schema: Canonical schema defining valid notes and filter semantics.
        filters: Schema-validated deterministic constraints from a selection contract.
        note_type: Optional canonical type restriction applied alongside ``filters``.

    Returns:
        Stable IDs of every current valid note that satisfies all restrictions.

    Raises:
        ValueError: If filters or the type restriction are not canonical.
        ContextRetrievalError: If a note cannot safely participate in the selection.
    """
    normalized_filters = _normalize_filters(schema, filters, note_type, ())
    matching_ids: set[str] = set()
    for path in repository.list_markdown_paths():
        try:
            note = parse_note(repository.read_text(path))
            validate_note(note, schema)
        except (NoteFormatError, NoteValidationError, OSError) as error:
            raise ContextRetrievalError(
                "Cannot safely inspect a note for deterministic target filtering"
            ) from error
        if _metadata_matches_filters(
            note.metadata, normalized_filters, _filter_definitions(schema)
        ):
            note_id = note.metadata["id"]
            assert isinstance(note_id, str)
            matching_ids.add(note_id)
    return frozenset(matching_ids)


def _metadata_matches_filters(
    metadata: Mapping[str, Any],
    filters: tuple[tuple[str, str, tuple[str | int, ...]], ...],
    definitions: Mapping[str, dict[str, Any]],
) -> bool:
    """Return whether validated metadata satisfies normalized deterministic filters."""
    for field, op, expected in filters:
        actual = metadata.get(field)
        if actual is None:
            return False
        definition = definitions[field]
        if op == "contains":
            if not isinstance(actual, list) or expected[0] not in actual:
                return False
            continue
        try:
            actual = _normalize_property_value(definition, actual)
        except ValueError:
            return False
        if op == "in":
            if actual not in expected:
                return False
        elif op == "eq" and actual != expected[0]:
            return False
        elif op == "gt" and not actual > expected[0]:
            return False
        elif op == "gte" and not actual >= expected[0]:
            return False
        elif op == "lt" and not actual < expected[0]:
            return False
        elif op == "lte" and not actual <= expected[0]:
            return False
    return True


class ContextIndex:
    """Own one disposable SQLite file containing atomic-note context embeddings."""

    def __init__(self, path: Path):
        if not isinstance(path, Path):
            raise TypeError("Context index path must be a pathlib.Path")
        self.path = path

    def rebuild(
        self, repository: VaultRepository, schema: dict[str, Any], embedder: TextEmbedder
    ) -> int:
        """Atomically rebuild context embeddings from every valid authoritative note.

        Args:
            repository: Authoritative Markdown vault access.
            schema: Canonical schema used to validate every note.
            embedder: Local embedding implementation.

        Returns:
            Number of indexed notes.

        Raises:
            ContextIndexError: If source notes, IDs, vectors, or derived storage are unsafe.
        """
        canonical_types = _canonical_values(schema, "types")
        canonical_tags = _canonical_values(schema, "tags")
        canonical_subtypes = tuple(sorted(_canonical_subtypes(schema)))
        filter_definitions = _filter_definitions(schema)
        if repository.contains_filesystem_path(self.path):
            raise ContextIndexError("Context index must be stored outside the Markdown vault")
        projected: list[tuple[str, str, str, str, str, tuple[str, ...], str]] = []
        properties: list[tuple[str, str, str | int, str]] = []
        seen_ids: set[str] = set()
        for path in repository.list_markdown_paths():
            raw = repository.read_text(path)
            try:
                note = parse_note(raw)
                validate_note(note, schema)
            except (NoteFormatError, NoteValidationError) as error:
                raise ContextIndexError(f"Cannot safely index invalid note: {path}") from error
            note_id = cast(str, note.metadata["id"])
            if note_id in seen_ids:
                raise ContextIndexError(f"Cannot safely index duplicate note ID: {note_id}")
            seen_ids.add(note_id)
            note_tags = tuple(cast(list[str], note.metadata.get("tags", [])))
            if any(tag not in canonical_tags for tag in note_tags):
                raise ContextIndexError(f"Cannot safely index unknown tag in note: {path}")
            projected.append(
                (
                    note_id,
                    path,
                    cast(str, note.metadata["type"]),
                    PurePosixPath(path).stem,
                    hashlib.sha256(raw.encode("utf-8")).hexdigest(),
                    note_tags,
                    build_context_retrieval_text(note, path),
                )
            )
            for field, definition in filter_definitions.items():
                value = note.metadata.get(
                    field, note.metadata.get("tags") if field == "tags" else None
                )
                if value is None:
                    continue
                values = value if isinstance(value, list) else [value]
                properties.extend(
                    (
                        note_id,
                        field,
                        _normalize_property_value(definition, item),
                        definition["value_type"],
                    )
                    for item in values
                )
        vectors = list(embedder.embed_documents([item[6] for item in projected]))
        if len(vectors) != len(projected):
            raise ContextIndexError("Embedding runtime returned the wrong number of vectors")
        normalized = [_normalized_vector(vector) for vector in vectors]
        dimensions = {len(vector) for vector in normalized}
        if len(dimensions) > 1:
            raise ContextIndexError("Embedding runtime returned inconsistent dimensions")
        dimension = dimensions.pop() if dimensions else 0
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{self.path.name}.", suffix=".tmp", dir=self.path.parent
        )
        os.close(descriptor)
        temporary = Path(temporary_name)
        try:
            with sqlite3.connect(temporary) as connection:
                connection.executescript("""
                    CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                    CREATE TABLE notes (
                        id TEXT PRIMARY KEY, path TEXT NOT NULL UNIQUE, type TEXT NOT NULL,
                        primary_name TEXT NOT NULL, source_hash TEXT NOT NULL, tags TEXT NOT NULL,
                        embedding BLOB NOT NULL
                    );
                    CREATE TABLE properties (
                        note_id TEXT NOT NULL,
                        field TEXT NOT NULL,
                        value TEXT NOT NULL,
                        value_type TEXT NOT NULL,
                        FOREIGN KEY(note_id) REFERENCES notes(id)
                    );
                """)
                connection.executemany(
                    "INSERT INTO metadata(key, value) VALUES (?, ?)",
                    (
                        *_INDEX_MARKERS.items(),
                        ("model_name", embedder.model_name),
                        ("model_version", embedder.model_version),
                        ("dimension", str(dimension)),
                        ("canonical_types", json.dumps(canonical_types)),
                        ("canonical_tags", json.dumps(canonical_tags)),
                        ("canonical_subtypes", json.dumps(canonical_subtypes)),
                        (
                            "filter_definitions",
                            json.dumps(_filter_registry(filter_definitions), sort_keys=True),
                        ),
                    ),
                )
                connection.executemany(
                    "INSERT INTO notes VALUES (?, ?, ?, ?, ?, ?, ?)",
                    [
                        (
                            item[0],
                            item[1],
                            item[2],
                            item[3],
                            item[4],
                            json.dumps(item[5]),
                            _vector_blob(vector),
                        )
                        for item, vector in zip(projected, normalized, strict=True)
                    ],
                )
                connection.executemany(
                    "INSERT INTO properties(note_id, field, value, value_type) VALUES (?, ?, ?, ?)",
                    properties,
                )
            os.replace(temporary, self.path)
        except (OSError, sqlite3.Error) as error:
            raise ContextIndexError("Unable to rebuild context index") from error
        finally:
            temporary.unlink(missing_ok=True)
        return len(projected)

    def delete(self) -> None:
        """Delete this file only after verifying its context-index markers."""
        if not self.path.exists():
            return
        try:
            with sqlite3.connect(f"file:{self.path}?mode=ro", uri=True) as connection:
                metadata = dict(connection.execute("SELECT key, value FROM metadata"))
            if any(metadata.get(key) != value for key, value in _INDEX_MARKERS.items()):
                raise ContextIndexError("Refusing to delete an unverified context index")
            self.path.unlink(missing_ok=True)
        except ContextIndexError:
            raise
        except (OSError, sqlite3.Error) as error:
            raise ContextIndexError("Refusing to delete an unverified context index") from error

    def find_candidates(
        self,
        schema: dict[str, Any],
        embedder: TextEmbedder,
        query: str,
        *,
        limit: int,
        type: str | None = None,
        required_tags: Sequence[str] = (),
        filters: Sequence[ContextFilter | Mapping[str, Any]] = (),
    ) -> tuple[_ContextCandidate, ...]:
        """Return deterministic ranking candidates after exact type/tag filtering."""
        if not isinstance(query, str) or not query.strip():
            raise ValueError("Context query must not be empty")
        if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
            raise ValueError("Context limit must be a positive integer")
        filter_definitions = _filter_definitions(schema)
        normalized_filters = _normalize_filters(schema, filters, type, required_tags)
        try:
            with sqlite3.connect(f"file:{self.path}?mode=ro", uri=True) as connection:
                metadata = dict(connection.execute("SELECT key, value FROM metadata"))
                if any(metadata.get(key) != value for key, value in _INDEX_MARKERS.items()):
                    raise ContextIndexError("Context index markers are incompatible")
                try:
                    stored_types = tuple(sorted(json.loads(metadata["canonical_types"])))
                    stored_tags = tuple(sorted(json.loads(metadata["canonical_tags"])))
                    stored_subtypes = tuple(sorted(json.loads(metadata["canonical_subtypes"])))
                except (KeyError, TypeError, json.JSONDecodeError) as error:
                    raise ContextIndexError(
                        "Context index is incompatible or stale; rebuild is required"
                    ) from error
                current_types = _canonical_values(schema, "types")
                current_tags = _canonical_values(schema, "tags")
                current_subtypes = tuple(sorted(_canonical_subtypes(schema)))
                if (
                    stored_types != current_types
                    or stored_tags != current_tags
                    or stored_subtypes != current_subtypes
                ):
                    raise ContextIndexError(
                        "Context index is incompatible or stale with the canonical type/tag/"
                        "subtype registries; rebuild is required"
                    )
                stored_filter_definitions = json.loads(metadata["filter_definitions"])
                current_filter_definitions = _filter_registry(_filter_definitions(schema))
                if stored_filter_definitions != current_filter_definitions:
                    raise ContextIndexError(
                        "Context index is incompatible or stale with the schema filter registry; "
                        "rebuild is required"
                    )
                if (
                    metadata["model_name"] != embedder.model_name
                    or metadata["model_version"] != embedder.model_version
                ):
                    raise ContextIndexError(
                        "Context index embedding model does not match query model"
                    )
                dimension = int(metadata["dimension"])
                if dimension == 0:
                    return ()
                vector_values = list(embedder.embed_queries([f"Query: {query.strip()}"]))
                if len(vector_values) != 1:
                    raise ContextIndexError(
                        "Embedding runtime returned the wrong number of vectors"
                    )
                query_vector = _normalized_vector(vector_values[0])
                if len(query_vector) != dimension:
                    raise ContextIndexError(
                        "Query embedding dimension does not match context index"
                    )
                clauses: list[str] = []
                parameters: list[Any] = []
                for field, op, values in normalized_filters:
                    definition = filter_definitions[field]
                    value_expression = (
                        "CAST(p.value AS INTEGER)"
                        if definition["value_type"] == "integer"
                        else "p.value"
                    )
                    if op == "in":
                        placeholders = ", ".join("?" for _ in values)
                        value_clause = f"{value_expression} IN ({placeholders})"
                    else:
                        sql_operator = {
                            "eq": "=",
                            "contains": "=",
                            "gt": ">",
                            "gte": ">=",
                            "lt": "<",
                            "lte": "<=",
                        }[op]
                        value_clause = f"{value_expression} {sql_operator} ?"
                    clauses.append(
                        "EXISTS (SELECT 1 FROM properties p "
                        "WHERE p.note_id = n.id AND p.field = ? AND p.value_type = ? AND "
                        + value_clause
                        + ")"
                    )
                    parameters.extend([field, definition["value_type"], *values])
                where = " WHERE " + " AND ".join(clauses) if clauses else ""
                rows = connection.execute(
                    "SELECT n.id, n.path, n.type, n.primary_name, n.source_hash, n.tags, n.embedding "
                    "FROM notes n" + where,
                    parameters,
                )
                candidates = []
                for (
                    note_id,
                    path,
                    note_type,
                    primary_name,
                    source_hash,
                    _encoded_tags,
                    blob,
                ) in rows:
                    vector = _blob_vector(blob)
                    if len(vector) != dimension:
                        raise ContextIndexError("Stored embedding dimension is inconsistent")
                    candidates.append(
                        _ContextCandidate(
                            note_id,
                            path,
                            note_type,
                            primary_name,
                            source_hash,
                            sum(
                                left * right
                                for left, right in zip(vector, query_vector, strict=True)
                            ),
                        )
                    )
        except ValueError:
            raise
        except (OSError, sqlite3.Error, KeyError, TypeError, json.JSONDecodeError) as error:
            raise ContextIndexError("Unable to read a compatible context index") from error
        candidates.sort(
            key=lambda item: (-item.similarity, item.primary_name.casefold(), item.path, item.id)
        )
        return tuple(candidates[:limit])


def get_context(
    repository: VaultRepository,
    schema: dict[str, Any],
    context_index: ContextIndex,
    embedder: TextEmbedder,
    *,
    query: str,
    limit: int,
    type: str | None = None,
    required_tags: Sequence[str] = (),
    filters: Sequence[ContextFilter | Mapping[str, Any]] = (),
) -> ContextPackage:
    """Retrieve ranked, authoritative atomic notes for an interpreted knowledge query.

    Args:
        repository: Authoritative Markdown vault.
        schema: Canonical note schema.
        context_index: Rebuildable derived context index.
        embedder: Local embedding implementation matching the index.
        query: Already-interpreted non-empty retrieval need.
        limit: Explicit positive context budget.
        type: Optional exact canonical note type filter.
        required_tags: Optional controlled tags; every tag must be present.
        filters: Optional schema-declared structured constraints. Each filter is a
            ``ContextFilter`` or mapping with ``field``, ``op``, and ``value`` keys.

    Returns:
        Immutable package containing current validated note content and provenance.

    Raises:
        ContextRetrievalError: If a selected candidate is stale, invalid, or mismatched.
        ValueError: If query or filters are invalid.
    """
    candidates = context_index.find_candidates(
        schema,
        embedder,
        query,
        limit=limit,
        type=type,
        required_tags=required_tags,
        filters=filters,
    )
    items: list[ContextItem] = []
    for candidate in candidates:
        try:
            raw = repository.read_text(candidate.path)
        except OSError as error:
            raise ContextRetrievalError(f"Unable to load indexed note: {candidate.path}") from error
        if hashlib.sha256(raw.encode("utf-8")).hexdigest() != candidate.source_hash:
            raise ContextRetrievalError(
                f"Context index is stale for selected note: {candidate.path}"
            )
        try:
            note = parse_note(raw)
            validate_note(note, schema)
        except (NoteFormatError, NoteValidationError) as error:
            raise ContextRetrievalError(
                f"Selected note is no longer valid: {candidate.path}"
            ) from error
        if (note.metadata.get("id"), note.metadata.get("type")) != (candidate.id, candidate.type):
            raise ContextRetrievalError(
                f"Indexed note identity disagrees with source: {candidate.path}"
            )
        metadata = {
            key: value
            for key, value in note.metadata.items()
            if key not in _TECHNICAL_METADATA | {"type", "tags"}
        }
        tags = tuple(cast(list[str], note.metadata.get("tags", [])))
        items.append(
            ContextItem(
                candidate.id,
                candidate.path,
                candidate.primary_name,
                candidate.type,
                tags,
                MappingProxyType(metadata),
                note.content,
                candidate.similarity,
            )
        )
    return ContextPackage(query=query.strip(), items=tuple(items))
