"""Automatic, evidence-backed optional property enrichment through Core/E3.

The application may choose *which* notes to enrich without per-note approval.
This narrow deterministic fast path only recognizes unequivocal atomic
"property: value" assertions for the exact registered property. An AI can
eventually interpret free prose under a separately evaluated contract; a model
confidence number alone cannot authorize a canonical write.

Run extraction over a finished read-only scan BEFORE applying any writes:
each write changes the inventory hash and rightly invalidates scan cursors.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal

from .atomic_facts import AtomicFactError, parse_atomic_facts
from .git_history import GitHistoryRecorder, HistoryStatus
from .mutation_gate import (
    CanonicalMutationError,
    CanonicalMutationGate,
    CanonicalPostwriteError,
    MutationCommand,
)
from .notes.validation import NoteValidationError, validate_field_value
from .persistence import PersistenceOperation, update_entity
from .schema_retrospection import SourceNote
from .storage import VaultRepository

Outcome = Literal["updated", "no_evidence", "ambiguous", "already_present", "stale", "blocked"]


class AutoBackfillError(ValueError):
    """Stop processing after an unsafe or partially committed operation."""

    def __init__(self, reason: str, *, physical_write: bool = False) -> None:
        super().__init__(reason)
        self.physical_write = physical_write


@dataclass(frozen=True, slots=True)
class BackfillChoice:
    """A source-backed automatic decision, without an LLM authority field."""

    status: Literal["auto", "no_evidence", "ambiguous"]
    property_id: str
    value: str | int | None = None
    source_locator: str | None = None


@dataclass(frozen=True, slots=True)
class AutoBackfillReceipt:
    """One verified automated action. No user note text is copied into receipts."""

    status: Outcome
    note_id: str
    property_id: str
    source_locator: str | None = None
    before_revision: int | None = None
    after_revision: int | None = None
    undo_commit: str | None = None


@dataclass(frozen=True, slots=True)
class AutoBackfillSummary:
    """One quiet batch result for the UI; no per-note approval prompts."""

    updated: int
    no_evidence: int
    ambiguous: int
    stale: int
    already_present: int
    undo_commits: int


def summarize_automatic_backfill(receipts: Sequence[AutoBackfillReceipt]) -> AutoBackfillSummary:
    """Summarize canonical outcomes without exposing source text to the browser."""
    return AutoBackfillSummary(
        updated=sum(item.status == "updated" for item in receipts),
        no_evidence=sum(item.status == "no_evidence" for item in receipts),
        ambiguous=sum(item.status == "ambiguous" for item in receipts),
        stale=sum(item.status == "stale" for item in receipts),
        already_present=sum(item.status == "already_present" for item in receipts),
        undo_commits=sum(item.undo_commit is not None for item in receipts),
    )


def _simple_label(value: str) -> str:
    # Locale-neutral spelling comparison; no guessed synonyms or fuzzy identity.
    text = unicodedata.normalize("NFKD", value)
    return re.sub(
        r"[^a-z0-9]+",
        "_",
        "".join(char for char in text if not unicodedata.combining(char)).lower(),
    ).strip("_")


def _explicit_value(raw: str, definition: dict[str, Any]) -> str | int | None:
    if not raw or len(raw) > 240 or "\r" in raw or "\n" in raw:
        return None
    kind = definition["value_type"]
    if kind == "integer":
        if not re.fullmatch(r"-?(?:0|[1-9][0-9]{0,15})", raw):
            return None
        value: str | int = int(raw)
    elif kind == "date":
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
            return None
        value = raw
    elif kind == "string":
        if raw != raw.strip() or not raw.strip():
            return None
        value = raw
    else:
        # Lists and partial dates are not proven by a plain colon assertion.
        return None
    try:
        validate_field_value(definition["id"], value, definition)
    except NoteValidationError:
        return None
    return value


def choose_explicit_backfill(
    source: SourceNote, *, type_id: str, definition: dict[str, Any]
) -> BackfillChoice:
    """Recognize grounded metadata-like facts, without trusting AI confidence.

    Other prose, legacy text and multiple conflicting declarations are not
    mutated.  These sources can later be interpreted by an evaluated model
    without requiring the user to manually review each non-match.
    """
    property_id = definition.get("id")
    if not isinstance(property_id, str) or not property_id or source.note_type != type_id:
        raise AutoBackfillError("Mismatched canonical source or property")
    recognized: list[tuple[str, str | int]] = []
    candidates: set[str] = set()
    for fact in source.facts:
        # Atomic facts are canonical, not free Markdown.  Only one complete
        # top-level key: value statement can justify a direct metadata value.
        body = fact.text.strip()
        match = re.fullmatch(r"([^:\n]{1,100}):[ \t]*(.{1,240})", body)
        if match is None or _simple_label(match.group(1)) != _simple_label(property_id):
            continue
        candidates.add(fact.locator)
        parsed = _explicit_value(match.group(2), definition)
        if parsed is not None:
            recognized.append((fact.locator, parsed))
    if not candidates:
        return BackfillChoice("no_evidence", property_id)
    # Legacy lines are not linkable evidence but may contradict a marked
    # value. Never ignore a competing field declaration just because it
    # predates Odyssey's atomic-fact markers.
    for line in source.legacy_text.splitlines():
        bare = line.strip().removeprefix("- ").strip()
        legacy = re.match(r"([^:\n]{1,100}):[ \t]*", bare)
        if legacy is not None and _simple_label(legacy.group(1)) == _simple_label(property_id):
            return BackfillChoice("ambiguous", property_id)
    # A matching declaration with unparseable value is still conflicting
    # evidence, not permission to ignore it and pick a different line.
    if len(candidates) != len(recognized) or len({str(v) for _, v in recognized}) != 1:
        return BackfillChoice("ambiguous", property_id)
    locator, value = recognized[0]
    return BackfillChoice("auto", property_id, value, locator)


class AutomaticPropertyBackfill:
    """Apply proven explicit fields autonomously via canonical mutation gate.

    Require local Git history for a reversible accepted operation. A failed
    history commit AFTER Markdown write is a partial outcome: halt immediately,
    never retry automatically or claim the write was rolled back.
    """

    def __init__(
        self,
        *,
        repository: VaultRepository,
        schema: dict[str, Any],
        history: GitHistoryRecorder,
    ) -> None:
        if not isinstance(repository, VaultRepository) or not isinstance(
            history, GitHistoryRecorder
        ):
            raise AutoBackfillError("Automatic writes require canonical vault and Git history")
        self.repository = repository
        self.schema = schema
        self.history = history
        self.gate = CanonicalMutationGate(repository, schema, history)

    def apply(
        self,
        *,
        source: SourceNote,
        type_id: str,
        property_id: str,
        actor: dict[str, str | None],
        now: str,
        request_id: str,
    ) -> AutoBackfillReceipt:
        definitions = [kind for kind in self.schema["types"] if kind["id"] == type_id]
        if len(definitions) != 1:
            raise AutoBackfillError("Target type not found")
        properties = [p for p in definitions[0]["properties"] if p["id"] == property_id]
        if len(properties) != 1 or properties[0].get("required", False):
            raise AutoBackfillError("Only registered optional properties may be enriched")
        decision = choose_explicit_backfill(source, type_id=type_id, definition=properties[0])
        if decision.status != "auto":
            return AutoBackfillReceipt(
                "ambiguous" if decision.status == "ambiguous" else "no_evidence",
                source.note_id,
                property_id,
            )
        assert decision.source_locator is not None and decision.value is not None
        command = MutationCommand(
            operation="schema_property_backfill",
            target_id=source.note_id,
            expected_revision=source.revision,
            expected_source_hash=source.source_hash,
            request_id=request_id,
            actor=actor,
            now=now,
            expected_type=type_id,
        )
        try:
            target = self.gate.prepare(command)
        except CanonicalMutationError:
            return AutoBackfillReceipt("stale", source.note_id, property_id)
        if property_id in target.note.metadata:
            return AutoBackfillReceipt("already_present", source.note_id, property_id)
        # The source version and exact evidence must still be present. Never
        # treat the LLM output or a scan receipt as current canonical authority.
        try:
            facts = parse_atomic_facts(target.note.content)
        except AtomicFactError as error:
            raise AutoBackfillError("Current canonical fact markup invalid") from error
        current_facts = tuple(item for item in facts if item.locator == decision.source_locator)
        if len(current_facts) != 1:
            raise AutoBackfillError("Exact source evidence disappeared")
        if not any(
            fact.locator == decision.source_locator and fact.text == current_facts[0].text
            for fact in source.facts
        ):
            raise AutoBackfillError("Exact source evidence differs from scan")
        # A history preflight must succeed before any autonomous Markdown edit.
        # GitHistoryRecorder uses a local vault Git root and baseline.
        try:
            snapshot = self.history.begin(request_id)
        except Exception as error:
            raise AutoBackfillError("Local undo history is unavailable") from error
        if target.path in snapshot.dirty_paths:
            raise AutoBackfillError("Source has unsaved changes in local history")
        try:
            receipt = self.gate.execute_prepared(
                command,
                target,
                lambda preflight: update_entity(
                    self.repository,
                    self.schema,
                    path=preflight.path,
                    expected_id=source.note_id,
                    expected_revision=source.revision,
                    set_metadata={property_id: decision.value},
                    actor=actor,
                    now=now,
                ),
            )
        except CanonicalPostwriteError as error:
            raise AutoBackfillError(
                "Post-write verification failed", physical_write=True
            ) from error
        except (CanonicalMutationError, NoteValidationError, ValueError):
            return AutoBackfillReceipt("stale", source.note_id, property_id)
        if receipt.persistence.operation is not PersistenceOperation.UPDATED:
            raise AutoBackfillError("Unexpected persistence result")
        if receipt.readback.metadata.get(property_id) != decision.value:
            raise AutoBackfillError("Readback property differs", physical_write=True)
        if receipt.history.status is not HistoryStatus.COMMITTED or not receipt.history.commit_sha:
            raise AutoBackfillError(
                "Physical write not safely recorded in undo history", physical_write=True
            )
        return AutoBackfillReceipt(
            "updated",
            source.note_id,
            property_id,
            decision.source_locator,
            receipt.before_revision,
            receipt.after_revision,
            receipt.history.commit_sha,
        )

    def apply_batch(
        self,
        *,
        sources: Sequence[SourceNote],
        type_id: str,
        property_id: str,
        actor: dict[str, str | None],
        now: str,
        request_prefix: str,
    ) -> tuple[AutoBackfillReceipt, ...]:
        """No per-note clicks. One receipt per note, halt on any partial write.

        Caller must have completed the source scan. Each row has its own
        physical CAS and history commit; a future scheduler persists batch
        continuation independently. A crash should not blindly replay rows.
        """
        if len(sources) > 25 or not request_prefix or len(request_prefix) > 72:
            raise AutoBackfillError("Automatic batch exceeds safe bounds")
        # Preflight the entire batch's identity before the first physical
        # write.  Discovering a repeated ID halfway through a job is too late.
        identities = [source.note_id for source in sources]
        if len(set(identities)) != len(identities):
            raise AutoBackfillError("Repeated source ID in automatic batch")
        receipts: list[AutoBackfillReceipt] = []
        for source in sources:
            receipt = self.apply(
                source=source,
                type_id=type_id,
                property_id=property_id,
                actor=actor,
                now=now,
                request_id=f"{request_prefix}-{len(receipts):02d}",
            )
            receipts.append(receipt)
        return tuple(receipts)
