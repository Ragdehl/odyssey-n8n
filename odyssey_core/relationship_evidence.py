"""Project bounded relationship evidence from current canonical Markdown."""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Any

from odyssey_core.atomic_facts import AtomicFactError, parse_atomic_facts
from odyssey_core.notes import NoteFormatError, NoteValidationError, parse_note, validate_note
from odyssey_core.storage import NoteUnavailableError, VaultRepository

_TECHNICAL_METADATA = frozenset(
    {
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
)


class RelationshipEvidenceError(RuntimeError):
    """Indicate canonical evidence that cannot safely participate in resolution."""


class EvidenceDirection(Enum):
    """Describe the entity-relative direction of one canonical fact snippet."""

    DIRECT = "direct"
    INCOMING = "incoming"
    OUTGOING = "outgoing"


class TargetProjectionStatus(Enum):
    """Describe whether one selected fact establishes a complete target set."""

    COMPLETE = "complete"
    INCOMPLETE = "incomplete"
    SOURCE_UNAVAILABLE = "source_unavailable"
    FACT_UNAVAILABLE = "fact_unavailable"


@dataclass(frozen=True, slots=True)
class CanonicalIdentity:
    """Expose one current validated stable identity and canonical source provenance."""

    id: str
    path: str
    name: str
    type: str
    source_hash: str


@dataclass(frozen=True, slots=True)
class CanonicalFact:
    """Represent one bounded visible canonical fact block and its re-grounding data."""

    source: CanonicalIdentity
    locator: str
    text: str


@dataclass(frozen=True, slots=True)
class RelationshipEvidence:
    """Bind one current fact occurrence to its entity-relative evidence direction.

    Incoming and outgoing evidence carries the resolved literal linked target. Direct evidence is
    source-local, so its target is absent rather than invented as a self-link.
    """

    fact: CanonicalFact
    direction: EvidenceDirection
    target: CanonicalIdentity | None


@dataclass(frozen=True, slots=True)
class TargetProjection:
    """Return either every grounded direct target of one source fact or no target set."""

    status: TargetProjectionStatus
    source: CanonicalIdentity | None
    fact: CanonicalFact | None
    targets: tuple[CanonicalIdentity, ...]
    evidence: tuple[RelationshipEvidence, ...]

    @property
    def complete(self) -> bool:
        """Report whether the selected canonical fact established its entire target set."""
        return self.status is TargetProjectionStatus.COMPLETE

    @property
    def unique_target(self) -> CanonicalIdentity | None:
        """Return the sole grounded target only when the selected fact is complete and singular."""
        return self.targets[0] if self.complete and len(self.targets) == 1 else None


@dataclass(frozen=True, slots=True)
class EntityEvidenceCandidateProjection:
    """Expose all valid one-hop candidates in the supplied current canonical scope."""

    entity: CanonicalIdentity
    properties: Mapping[str, Any]
    direct: tuple[RelationshipEvidence, ...]
    incoming: tuple[RelationshipEvidence, ...]
    outgoing: tuple[RelationshipEvidence, ...]


@dataclass(frozen=True, slots=True)
class _GroundedFact:
    """Keep a source fact plus literal link targets resolved in one vault snapshot."""

    fact: CanonicalFact
    targets: tuple[CanonicalIdentity, ...] | None


@dataclass(frozen=True, slots=True)
class _GroundedNote:
    """Keep one active validated note used only while producing an evidence projection."""

    identity: CanonicalIdentity
    properties: Mapping[str, Any]
    facts: tuple[_GroundedFact, ...]


def _safe_link_target(value: str) -> str | None:
    """Return a normalized literal wikilink target or reject unsafe path syntax."""
    target = value.strip()
    if (
        not target
        or "\\" in target
        or "\x00" in target
        or target.startswith("/")
        or ".." in target.split("/")
    ):
        return None
    return target.removesuffix(".md").casefold()


def _literal_link_targets(text: str) -> tuple[str, ...] | None:
    """Parse every literal wikilink target or reject malformed link syntax in a fact."""
    targets: list[str] = []
    offset = 0
    while (start := text.find("[[", offset)) >= 0:
        end = text.find("]]", start + 2)
        if end < 0:
            return None
        target, _separator, _label = text[start + 2 : end].partition("|")
        safe_target = _safe_link_target(target)
        if safe_target is None:
            return None
        targets.append(safe_target)
        offset = end + 2
    return tuple(targets)


def _visible_fact_texts(body: str) -> tuple[str, ...]:
    """Return bounded visible fact blocks without making hidden markup evidence."""
    try:
        parse_atomic_facts(body)
    except AtomicFactError as error:
        raise RelationshipEvidenceError("Canonical atomic fact markup is invalid") from error

    facts: list[str] = []
    paragraph: list[str] = []

    def flush_paragraph() -> None:
        if paragraph:
            facts.append(" ".join(paragraph))
            paragraph.clear()

    for raw_line in body.splitlines():
        line = raw_line.strip()
        if not line:
            flush_paragraph()
            continue
        if line.startswith("<!--") and line.endswith("-->"):
            continue
        if line.startswith("#") and len(line) > 1 and line[1].isspace():
            flush_paragraph()
            continue
        if len(line) > 2 and line[0] in "-*+" and line[1].isspace():
            flush_paragraph()
            facts.append(line[2:].strip())
            continue
        digits = len(line) - len(line.lstrip("0123456789"))
        if (
            digits
            and len(line) > digits + 2
            and line[digits] in ".)"
            and line[digits + 1].isspace()
        ):
            flush_paragraph()
            facts.append(line[digits + 2 :].strip())
            continue
        if raw_line[:1].isspace():
            # Indented continuation/markup is deliberately not a separate fact block.
            continue
        paragraph.append(line)
    flush_paragraph()
    return tuple(item for item in facts if item)


def _build_link_resolver(
    paths: Mapping[str, _GroundedNote], basenames: Mapping[str, tuple[_GroundedNote, ...]]
) -> Callable[[str], CanonicalIdentity | None]:
    """Build the one-hop literal resolver over one validated canonical snapshot."""

    def resolve(target: str) -> CanonicalIdentity | None:
        direct = paths.get(target)
        if direct is not None:
            return direct.identity
        if "/" not in target:
            candidates = basenames.get(target, ())
            if len(candidates) == 1:
                return candidates[0].identity
        return None

    return resolve


class RelationshipEvidenceProjector:
    """Project one-hop relationship and bounded entity context evidence from Markdown.

    The projector intentionally reads and validates the authoritative vault for every call. It does
    not consume a link index as knowledge evidence and it never follows links beyond the selected
    literal targets.
    """

    def __init__(self, repository: VaultRepository, schema: dict[str, Any]) -> None:
        """Bind the authoritative vault and canonical schema used to re-ground all evidence."""
        self.repository = repository
        self.schema = schema

    def facts_for_source(self, source_id: str) -> tuple[CanonicalFact, ...]:
        """List visible current canonical fact blocks for one stable source identity.

        The returned locator is source-hash-bound. A later call must reselect it from the current
        source rather than treating a previous projection as durable knowledge.
        """
        source = self._load_notes().get(source_id)
        if source is None:
            return ()
        return tuple(item.fact for item in source.facts)

    def all_visible_facts(self) -> tuple[CanonicalFact, ...]:
        """Return every active current visible fact block in canonical path/locator order.

        This is a discovery primitive only. Callers still impose their own explicit fact, source,
        and serialized-byte bounds before passing any candidate to a semantic selector.
        """
        notes = self._load_notes()
        return tuple(
            item.fact
            for _note_id, note in sorted(notes.items(), key=lambda item: item[1].identity.path)
            for item in note.facts
        )

    def project_targets(self, source_id: str, fact_locator: str) -> TargetProjection:
        """Resolve every literal direct target in one selected canonical fact or fail closed.

        A complete result contains all unique targets in their first literal-link order. A malformed,
        ambiguous, stale, or unavailable target makes the complete set unavailable, preventing a
        caller from treating a partial subset as a valid universal reference.
        """
        notes = self._load_notes()
        source = notes.get(source_id)
        if source is None:
            return TargetProjection(TargetProjectionStatus.SOURCE_UNAVAILABLE, None, None, (), ())
        selected = next((item for item in source.facts if item.fact.locator == fact_locator), None)
        if selected is None:
            return TargetProjection(
                TargetProjectionStatus.FACT_UNAVAILABLE, source.identity, None, (), ()
            )
        if selected.targets is None or not selected.targets:
            return TargetProjection(
                TargetProjectionStatus.INCOMPLETE, source.identity, selected.fact, (), ()
            )
        evidence = tuple(
            RelationshipEvidence(selected.fact, EvidenceDirection.OUTGOING, target)
            for target in selected.targets
        )
        return TargetProjection(
            TargetProjectionStatus.COMPLETE,
            source.identity,
            selected.fact,
            selected.targets,
            evidence,
        )

    def resolve_link_occurrence(
        self, source_id: str, fact_locator: str, start: int, end: int
    ) -> CanonicalIdentity | None:
        """Resolve one exact current wikilink span to its stable target identity.

        The caller supplies only a current Core candidate locator and exact fact span.  This method
        rereads the full canonical snapshot and returns ``None`` for stale, malformed, ambiguous,
        dangling, or non-link occurrences so callers cannot treat display text as identity proof.
        """
        if not isinstance(start, int) or not isinstance(end, int) or start < 0 or end <= start:
            return None
        notes = self._load_notes()
        source = notes.get(source_id)
        if source is None:
            return None
        selected = next((item for item in source.facts if item.fact.locator == fact_locator), None)
        if selected is None or end > len(selected.fact.text):
            return None
        link_text = selected.fact.text[start:end]
        if not (link_text.startswith("[[") and link_text.endswith("]]")):
            return None
        target_text = link_text[2:-2].partition("|")[0].partition("#")[0]
        target = _safe_link_target(target_text)
        if target is None:
            return None
        path_matches = tuple(
            note.identity
            for note in notes.values()
            if note.identity.path.removesuffix(".md").casefold() == target
        )
        if len(path_matches) == 1:
            return path_matches[0]
        if "/" in target:
            return None
        basename_matches = tuple(
            note.identity
            for note in notes.values()
            if note.identity.path.removesuffix(".md").rsplit("/", 1)[-1].casefold() == target
        )
        return basename_matches[0] if len(basename_matches) == 1 else None

    def project_entity_evidence_candidates(
        self,
        entity_id: str,
        *,
        discovered_backlink_source_ids: Iterable[str] | None = None,
    ) -> EntityEvidenceCandidateProjection | None:
        """Return all valid one-hop candidates for later request-aware context selection.

        ``discovered_backlink_source_ids`` is an optional derived-index candidate set. Each source
        is still loaded from current Markdown and must still contain a literal link to the requested
        entity before it enters the returned evidence. Omitting it scans the current vault snapshot.
        This method deliberately does not rank candidates against a request, reduce their count, or
        construct a final ``ContextPackage``. The supplied discovery scope and one-hop rule bound
        candidate topology; later retrieval owns request-aware reduction and final context limits.
        """
        notes = self._load_notes()
        entity = notes.get(entity_id)
        if entity is None:
            return None
        direct = tuple(
            RelationshipEvidence(item.fact, EvidenceDirection.DIRECT, None)
            for item in entity.facts
            if item.targets == ()
        )
        outgoing = tuple(
            RelationshipEvidence(item.fact, EvidenceDirection.OUTGOING, target)
            for item in entity.facts
            if item.targets
            for target in item.targets
        )
        if discovered_backlink_source_ids is None:
            incoming_sources = tuple(
                note for note_id, note in notes.items() if note_id != entity_id
            )
        else:
            requested = tuple(discovered_backlink_source_ids)
            if not all(isinstance(item, str) and item for item in requested):
                raise ValueError("Backlink discovery source IDs must be non-empty strings")
            incoming_sources = tuple(
                notes[note_id]
                for note_id in dict.fromkeys(requested)
                if note_id in notes and note_id != entity_id
            )
        incoming = tuple(
            RelationshipEvidence(item.fact, EvidenceDirection.INCOMING, entity.identity)
            for note in incoming_sources
            for item in note.facts
            if item.targets and any(target.id == entity_id for target in item.targets)
        )
        direct = tuple(sorted(direct, key=lambda item: item.fact.locator))
        incoming = tuple(
            sorted(
                incoming,
                key=lambda item: (item.fact.source.path, item.fact.locator, item.target.id),
            )
        )
        outgoing = tuple(
            sorted(outgoing, key=lambda item: (item.fact.locator, item.target.path, item.target.id))
        )
        return EntityEvidenceCandidateProjection(
            entity.identity,
            entity.properties,
            direct,
            incoming,
            outgoing,
        )

    def _load_notes(self) -> dict[str, _GroundedNote]:
        """Read active Markdown once, validate it, then resolve literal links within that snapshot."""
        unlinked: dict[str, tuple[CanonicalIdentity, Mapping[str, Any], tuple[str, ...]]] = {}
        paths: dict[str, tuple[CanonicalIdentity, Mapping[str, Any], tuple[str, ...]]] = {}
        basenames: dict[
            str, list[tuple[CanonicalIdentity, Mapping[str, Any], tuple[str, ...]]]
        ] = {}
        for path in self.repository.list_markdown_paths():
            try:
                raw = self.repository.read_text(path)
                note = parse_note(raw)
                validate_note(note, self.schema)
            except (NoteUnavailableError, NoteFormatError, NoteValidationError) as error:
                raise RelationshipEvidenceError(
                    "Canonical note is unavailable or invalid"
                ) from error
            if note.metadata.get("deleted") is True:
                continue
            note_id = str(note.metadata["id"])
            if note_id in unlinked:
                raise RelationshipEvidenceError("Duplicate canonical note identity")
            identity = CanonicalIdentity(
                note_id,
                path,
                str(note.metadata["name"]),
                str(note.metadata["type"]),
                hashlib.sha256(raw.encode("utf-8")).hexdigest(),
            )
            properties = MappingProxyType(
                {
                    key: value
                    for key, value in note.metadata.items()
                    if key not in _TECHNICAL_METADATA
                }
            )
            record = (identity, properties, _visible_fact_texts(note.content))
            unlinked[note_id] = record
            path_key = path.removesuffix(".md").casefold()
            if path_key in paths:
                raise RelationshipEvidenceError("Duplicate canonical note path")
            paths[path_key] = record
            basenames.setdefault(path_key.rsplit("/", 1)[-1], []).append(record)

        provisional = {
            note_id: _GroundedNote(identity, properties, ())
            for note_id, (identity, properties, _facts) in unlinked.items()
        }
        path_notes = {path: provisional[record[0].id] for path, record in paths.items()}
        basename_notes = {
            name: tuple(provisional[record[0].id] for record in records)
            for name, records in basenames.items()
        }
        resolve = _build_link_resolver(path_notes, basename_notes)
        grounded: dict[str, _GroundedNote] = {}
        for note_id, (identity, properties, texts) in unlinked.items():
            facts: list[_GroundedFact] = []
            for index, text in enumerate(texts):
                locator = (
                    f"s:{identity.source_hash}:b:{index}:"
                    f"{hashlib.sha256(text.encode('utf-8')).hexdigest()}"
                )
                fact = CanonicalFact(identity, locator, text)
                literal_targets = _literal_link_targets(text)
                if literal_targets is None:
                    targets = None
                else:
                    resolved: list[CanonicalIdentity] = []
                    seen: set[str] = set()
                    for target in literal_targets:
                        target_identity = resolve(target)
                        if target_identity is None:
                            resolved = []
                            targets = None
                            break
                        if target_identity.id not in seen:
                            seen.add(target_identity.id)
                            resolved.append(target_identity)
                    else:
                        targets = tuple(resolved)
                facts.append(_GroundedFact(fact, targets))
            grounded[note_id] = _GroundedNote(identity, properties, tuple(facts))
        return grounded
