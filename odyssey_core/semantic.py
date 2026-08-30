"""Disposable semantic candidate retrieval over validated Odyssey notes."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import sqlite3
import tempfile
from array import array
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, cast

from odyssey_core.notes import Note, NoteFormatError, NoteValidationError, parse_note, validate_note
from odyssey_core.storage import VaultRepository

DEFAULT_EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
_INDEX_MARKERS = {
    "application": "odyssey",
    "format": "semantic-entity-index",
    "format_version": "1",
}
_TECHNICAL_METADATA = {
    "id",
    "created_at",
    "updated_at",
    "created_by",
    "updated_by",
    "revision",
    "schema_version",
}
# Classification facets are useful to notes but are not evidence of entity identity.
_NON_IDENTITY_FACETS = frozenset({"tags"})
_WIKILINK_PATTERN = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")


class SemanticIndexError(RuntimeError):
    """Indicate that a derived semantic index cannot be built or queried safely."""


class TextEmbedder(Protocol):
    """Define the small embedding boundary used by indexing and retrieval."""

    @property
    def model_name(self) -> str:
        """Return the stable embedding model identifier."""

    @property
    def model_version(self) -> str:
        """Return the runtime/model version recorded with the derived index."""

    def embed_documents(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        """Embed note retrieval projections in input order."""

    def embed_queries(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        """Embed semantic lookup queries in input order."""


class FastEmbedTextEmbedder:
    """Provide local multilingual embeddings through the optional FastEmbed runtime.

    Args:
        model_name: FastEmbed model identifier. The Phase 10 benchmark-selected model is default.
        cache_dir: Optional derived-model cache location.
        local_files_only: Require a complete local model artifact instead of allowing a download.

    Raises:
        SemanticIndexError: If FastEmbed is unavailable or the model cannot load locally.
    """

    def __init__(
        self,
        model_name: str = DEFAULT_EMBEDDING_MODEL,
        cache_dir: Path | None = None,
        *,
        local_files_only: bool = True,
    ):
        try:
            from fastembed import TextEmbedding
            from fastembed import __version__ as fastembed_version
        except ImportError:
            raise SemanticIndexError(
                "FastEmbed is unavailable; install requirements-semantic.txt"
            ) from None
        try:
            self._model = TextEmbedding(
                model_name=model_name,
                cache_dir=str(cache_dir) if cache_dir is not None else None,
                local_files_only=local_files_only,
            )
        except Exception as error:
            raise SemanticIndexError(f"Unable to load embedding model: {model_name}") from error
        self._model_name = model_name
        self._model_version = f"fastembed-{fastembed_version}"

    @property
    def model_name(self) -> str:
        """Return the configured FastEmbed model identifier."""
        return self._model_name

    @property
    def model_version(self) -> str:
        """Return the FastEmbed runtime version used for model execution."""
        return self._model_version

    def embed_documents(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        """Embed semantic note projections locally in input order.

        Args:
            texts: Complete per-note retrieval projections.

        Returns:
            Dense normalized vectors in the same order as ``texts``.
        """
        return list(self._model.embed(list(texts)))

    def embed_queries(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        """Embed reference-and-context queries locally in input order.

        Args:
            texts: Query strings prepared by semantic candidate retrieval.

        Returns:
            Dense normalized vectors in the same order as ``texts``.
        """
        return list(self._model.query_embed(list(texts)))


@dataclass(frozen=True, slots=True)
class SemanticEntityCandidate:
    """Expose ranking evidence for one plausible existing note.

    Similarity is ranking evidence only. This value deliberately has no resolved, selected,
    confidence, or identity-decision field.

    Attributes:
        id: Stable logical note identifier.
        path: Vault-relative POSIX Markdown path.
        type: Canonical note type.
        primary_name: Canonical human-readable metadata name.
        similarity: Cosine similarity used only to rank this candidate set.
    """

    id: str
    path: str
    type: str
    primary_name: str
    similarity: float


@dataclass(frozen=True, slots=True)
class _ProjectedNote:
    path: str
    id: str
    type: str
    primary_name: str
    source_hash: str
    text: str


def _humanize_wikilinks(markdown: str) -> str:
    """Replace ordinary wikilinks with their human-readable label or target text."""

    def replace(match: re.Match[str]) -> str:
        return (match.group(2) or match.group(1)).strip()

    return _WIKILINK_PATTERN.sub(replace, markdown)


def build_semantic_retrieval_text(note: Note, path: str) -> str:
    """Build deterministic embedding text from a validated note and its storage path.

    Args:
        note: Canonically validated Odyssey note.
        path: Vault-relative POSIX Markdown path validated as technical source evidence.

    Returns:
        One human-readable projection containing name, aliases, type, useful domain metadata,
        and Markdown body with wikilinks replaced by visible link text.

    Raises:
        ValueError: If path or required validated metadata is unusable.

    Example:
        A body of ``"Partner of [[Xavi]]."`` contributes ``"Partner of Xavi."``.
    """
    if not isinstance(path, str) or not path.endswith(".md"):
        raise ValueError("Semantic projection requires a Markdown note path")
    primary_name = note.metadata.get("name")
    note_type = note.metadata.get("type")
    note_id = note.metadata.get("id")
    if (
        not isinstance(primary_name, str)
        or not primary_name.strip()
        or not isinstance(note_type, str)
        or not isinstance(note_id, str)
    ):
        raise ValueError("Semantic projection requires validated note identity and type")

    lines = [f"Name: {primary_name}"]
    aliases = note.metadata.get("aliases")
    if isinstance(aliases, list) and aliases:
        lines.append("Aliases: " + ", ".join(cast(list[str], aliases)))
    lines.append(f"Type: {note_type}")
    for key in sorted(note.metadata):
        if (
            key in _TECHNICAL_METADATA
            or key in _NON_IDENTITY_FACETS
            or key in {"aliases", "name", "type"}
        ):
            continue
        value = note.metadata[key]
        rendered = ", ".join(str(item) for item in value) if isinstance(value, list) else str(value)
        lines.append(f"{key.replace('_', ' ').title()}: {rendered}")
    body = _humanize_wikilinks(note.content).strip()
    if body:
        lines.append(body)
    return "\n".join(lines)


def _canonical_types(schema: dict[str, Any]) -> tuple[str, ...]:
    try:
        values = tuple(sorted(definition["id"] for definition in schema["types"]))
    except (KeyError, TypeError):
        raise ValueError("Supplied schema is not a usable canonical schema") from None
    if not values or not all(isinstance(value, str) for value in values):
        raise ValueError("Supplied schema is not a usable canonical schema")
    return values


def _normalized_vector(values: Iterable[float]) -> tuple[float, ...]:
    """Return a finite unit vector suitable for exact cosine comparison."""
    vector = tuple(float(value) for value in values)
    if not vector or not all(math.isfinite(value) for value in vector):
        raise SemanticIndexError("Embedding runtime returned an invalid vector")
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        raise SemanticIndexError("Embedding runtime returned a zero vector")
    return tuple(value / norm for value in vector)


def _vector_blob(vector: Sequence[float]) -> bytes:
    values = array("f", vector)
    if values.itemsize != 4:
        raise SemanticIndexError("Platform does not provide 32-bit float arrays")
    return values.tobytes()


def _blob_vector(blob: bytes) -> array[float]:
    values: array[float] = array("f")
    values.frombytes(blob)
    return values


class SemanticEntityIndex:
    """Own one disposable SQLite file containing validated note embeddings."""

    def __init__(self, path: Path):
        if not isinstance(path, Path):
            raise TypeError("Semantic index path must be a pathlib.Path")
        self.path = path

    def rebuild(
        self,
        repository: VaultRepository,
        schema: dict[str, Any],
        embedder: TextEmbedder,
    ) -> int:
        """Atomically replace the derived index from authoritative Markdown notes.

        The vault is only listed and read. Every source note must parse and validate before any
        replacement occurs, so a failed rebuild preserves an existing usable index.

        Args:
            repository: Read-only source of canonical Markdown text.
            schema: Canonical note schema used to validate every source note.
            embedder: Local embedding implementation and model identity.

        Returns:
            Number of indexed atomic notes.

        Raises:
            SemanticIndexError: If a note is invalid, IDs collide, embeddings are inconsistent,
                or the derived file cannot be replaced safely.
            VaultRepository exceptions: If canonical source listing or reads fail.
        """
        canonical_types = _canonical_types(schema)
        if repository.contains_filesystem_path(self.path):
            raise SemanticIndexError("Semantic index must be stored outside the Markdown vault")
        projected: list[_ProjectedNote] = []
        seen_ids: set[str] = set()
        for path in repository.list_markdown_paths():
            raw = repository.read_text(path)
            try:
                note = parse_note(raw)
                validate_note(note, schema)
            except (NoteFormatError, NoteValidationError) as error:
                raise SemanticIndexError(f"Cannot safely index invalid note: {path}") from error
            note_id = cast(str, note.metadata["id"])
            if note_id in seen_ids:
                raise SemanticIndexError(f"Cannot safely index duplicate note ID: {note_id}")
            seen_ids.add(note_id)
            if note.metadata.get("deleted") is True:
                continue
            projected.append(
                _ProjectedNote(
                    path=path,
                    id=note_id,
                    type=cast(str, note.metadata["type"]),
                    primary_name=cast(str, note.metadata["name"]),
                    source_hash=hashlib.sha256(raw.encode("utf-8")).hexdigest(),
                    text=build_semantic_retrieval_text(note, path),
                )
            )

        vectors = list(embedder.embed_documents([item.text for item in projected]))
        if len(vectors) != len(projected):
            raise SemanticIndexError("Embedding runtime returned the wrong number of vectors")
        normalized = [_normalized_vector(vector) for vector in vectors]
        dimensions = {len(vector) for vector in normalized}
        if len(dimensions) > 1:
            raise SemanticIndexError("Embedding runtime returned inconsistent dimensions")
        dimension = dimensions.pop() if dimensions else 0

        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{self.path.name}.", suffix=".tmp", dir=self.path.parent
        )
        os.close(descriptor)
        temporary = Path(temporary_name)
        try:
            with sqlite3.connect(temporary) as connection:
                connection.executescript(
                    """
                    CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                    CREATE TABLE notes (
                        id TEXT PRIMARY KEY,
                        path TEXT NOT NULL UNIQUE,
                        type TEXT NOT NULL,
                        primary_name TEXT NOT NULL,
                        source_hash TEXT NOT NULL,
                        embedding BLOB NOT NULL
                    );
                    """
                )
                connection.executemany(
                    "INSERT INTO metadata(key, value) VALUES (?, ?)",
                    (
                        *_INDEX_MARKERS.items(),
                        ("model_name", embedder.model_name),
                        ("model_version", embedder.model_version),
                        ("dimension", str(dimension)),
                        ("canonical_types", json.dumps(canonical_types)),
                    ),
                )
                connection.executemany(
                    """INSERT INTO notes(id, path, type, primary_name, source_hash, embedding)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    [
                        (
                            item.id,
                            item.path,
                            item.type,
                            item.primary_name,
                            item.source_hash,
                            _vector_blob(vector),
                        )
                        for item, vector in zip(projected, normalized, strict=True)
                    ],
                )
            os.replace(temporary, self.path)
        except (OSError, sqlite3.Error) as error:
            raise SemanticIndexError("Unable to rebuild semantic index") from error
        finally:
            temporary.unlink(missing_ok=True)
        return len(projected)

    def delete(self) -> None:
        """Delete this file only after verifying Odyssey semantic-index markers.

        Raises:
            SemanticIndexError: If the existing target is not a compatible Odyssey semantic index
                or cannot be deleted.
        """
        if not self.path.exists():
            return
        try:
            with sqlite3.connect(f"file:{self.path}?mode=ro", uri=True) as connection:
                metadata = dict(connection.execute("SELECT key, value FROM metadata"))
            if any(metadata.get(key) != value for key, value in _INDEX_MARKERS.items()):
                raise SemanticIndexError("Refusing to delete an unverified semantic index")
            self.path.unlink(missing_ok=True)
        except SemanticIndexError:
            raise
        except (OSError, sqlite3.Error) as error:
            raise SemanticIndexError("Refusing to delete an unverified semantic index") from error

    def find_candidates(
        self,
        embedder: TextEmbedder,
        reference: str,
        *,
        context: str = "",
        type: str | None = None,
        limit: int = 5,
    ) -> tuple[SemanticEntityCandidate, ...]:
        """Rank plausible indexed notes without making an identity decision.

        Args:
            embedder: Same local model/runtime identity used to build the index.
            reference: Already-extracted entity reference.
            context: Optional surrounding text that may disambiguate candidate ranking.
            type: Optional canonical type filter applied before top-N selection.
            limit: Positive maximum candidate count.

        Returns:
            Deterministically ordered candidate evidence, possibly empty.

        Raises:
            ValueError: If query, context, type, or limit is invalid.
            SemanticIndexError: If the index is absent, incompatible, corrupt, or cannot be read.
        """
        if not isinstance(reference, str) or not reference.strip():
            raise ValueError("Semantic entity reference must not be empty")
        if not isinstance(context, str):
            raise ValueError("Semantic entity context must be text")
        if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
            raise ValueError("Semantic candidate limit must be a positive integer")
        if type is not None and not isinstance(type, str):
            raise ValueError("Semantic candidate type must be canonical text")

        try:
            with sqlite3.connect(f"file:{self.path}?mode=ro", uri=True) as connection:
                metadata = dict(connection.execute("SELECT key, value FROM metadata"))
                canonical_types = json.loads(metadata["canonical_types"])
                if type is not None and type not in canonical_types:
                    raise ValueError(f"Unknown canonical note type: {type!r}")
                if metadata["model_name"] != embedder.model_name:
                    raise SemanticIndexError(
                        "Semantic index embedding model does not match query model"
                    )
                if metadata["model_version"] != embedder.model_version:
                    raise SemanticIndexError(
                        "Semantic index embedding version does not match query runtime"
                    )
                try:
                    dimension = int(metadata["dimension"])
                except (KeyError, TypeError, ValueError) as error:
                    raise SemanticIndexError(
                        "Semantic index has invalid embedding dimension metadata"
                    ) from error
                if dimension == 0:
                    return ()
                query_text = f"Reference: {reference.strip()}"
                if context.strip():
                    query_text += f"\nContext: {context.strip()}"
                query_vectors = list(embedder.embed_queries([query_text]))
                if len(query_vectors) != 1:
                    raise SemanticIndexError(
                        "Embedding runtime returned the wrong number of vectors"
                    )
                query_vector = _normalized_vector(query_vectors[0])
                if len(query_vector) != dimension:
                    raise SemanticIndexError(
                        "Query embedding dimension does not match semantic index"
                    )
                if type is None:
                    rows = connection.execute(
                        "SELECT id, path, type, primary_name, embedding FROM notes"
                    )
                else:
                    rows = connection.execute(
                        "SELECT id, path, type, primary_name, embedding FROM notes WHERE type = ?",
                        (type,),
                    )
                candidates = []
                for note_id, path, note_type, primary_name, blob in rows:
                    vector = _blob_vector(blob)
                    if len(vector) != len(query_vector):
                        raise SemanticIndexError("Stored embedding dimension is inconsistent")
                    similarity = sum(
                        left * right for left, right in zip(vector, query_vector, strict=True)
                    )
                    candidates.append(
                        SemanticEntityCandidate(
                            id=note_id,
                            path=path,
                            type=note_type,
                            primary_name=primary_name,
                            similarity=similarity,
                        )
                    )
        # JSONDecodeError is a ValueError subclass, so translate it before preserving
        # caller-facing validation errors raised by reference/type/limit validation.
        except json.JSONDecodeError as error:
            raise SemanticIndexError("Unable to read a compatible semantic index") from error
        except ValueError:
            raise
        except (OSError, sqlite3.Error, KeyError) as error:
            raise SemanticIndexError("Unable to read a compatible semantic index") from error

        candidates.sort(
            key=lambda candidate: (
                -candidate.similarity,
                candidate.primary_name.casefold(),
                candidate.path,
                candidate.id,
            )
        )
        return tuple(candidates[:limit])


def find_semantic_entity_candidates(
    index: SemanticEntityIndex,
    embedder: TextEmbedder,
    reference: str,
    *,
    context: str = "",
    type: str | None = None,
    limit: int = 5,
) -> tuple[SemanticEntityCandidate, ...]:
    """Return ranked semantic candidate evidence without resolving final identity.

    Args:
        index: Rebuildable derived semantic index.
        embedder: Local query embedding provider matching the built index.
        reference: Already-extracted entity reference.
        context: Optional original surrounding text useful for ranking.
        type: Optional canonical note type filter.
        limit: Positive maximum number of candidates.

    Returns:
        Ranked candidates whose similarity scores are evidence, never identity confidence.

    Raises:
        ValueError: If query constraints are invalid.
        SemanticIndexError: If retrieval cannot safely use the derived index or embedder.
    """
    return index.find_candidates(embedder, reference, context=context, type=type, limit=limit)
