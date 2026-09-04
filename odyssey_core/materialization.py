"""Deterministic CREATE and bounded-writer UPDATE materialization."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from odyssey_core.atomic_facts import (
    append_atomic_facts,
    find_unique_atomic_fact,
    normalize_atomic_fact,
    parse_atomic_facts,
    remove_atomic_fact,
    render_atomic_facts,
)
from odyssey_core.fact_selection import AtomicFactSelector, FactCandidate, validate_fact_selection
from odyssey_core.notes import Note, parse_note, validate_note
from odyssey_core.persistence import (
    EntityPersistenceResult,
    PersistenceOperation,
    create_entity,
    migrate_entity,
    normalize_actor_provenance,
    soft_delete_entity,
    update_entity,
)
from odyssey_core.reference_binding import (
    ReferenceBindingError,
    required_bound_wikilinks,
    validate_rendered_facts,
)
from odyssey_core.reference_preflight import UnitTargetPreflight
from odyssey_core.request_planning import KnowledgeUnit, PropertyChange, TagChange
from odyssey_core.storage import VaultRepository
from odyssey_core.write_target import WriteTargetDecision, WriteTargetOutcome

WRITER_MODEL = "gpt-5.6-luna"
WRITER_REASONING_EFFORT = "medium"
WRITER_CONTEXT_MODE = "FULL_NOTE"
_WRITER_INSTRUCTIONS = (
    "You are Odyssey's bounded Markdown writer. You receive already-interpreted facts and a fixed "
    "UPDATE intent. Do not resolve identity, choose a note ID or path, add metadata, properties, "
    "tags, dates, URLs, or facts not supplied. Supplied facts may contain Core-bound wikilinks: "
    "preserve their exact targets and display text, do not invent additional wikilinks, and do not "
    "resolve or alter link identity. Return the smallest faithful bounded "
    "operations against the supplied current Markdown body. Every old span must be exact. Do not "
    "rewrite the whole body. Use NO_CHANGE only when every supplied fact is already represented, "
    "and then return it as the only operation. Use APPEND for independent facts, REPLACE for "
    "corrections or temporal changes, and REMOVE only for exact supplied content. Preserve "
    "unrelated information. For record/amend, do not drop a supplied bound wikilink while "
    "representing its fact; an explicit remove may remove that fact. Return only the requested "
    "Structured Outputs object."
)


class MaterializationError(RuntimeError):
    """Indicate that a resolved UPDATE cannot be safely materialized or persisted."""


class WriterProviderError(MaterializationError):
    """Indicate that the bounded writer could not provide a usable response."""


class WriterOutputError(MaterializationError):
    """Indicate malformed, unsafe, or conflicting bounded writer operations."""


def materialize_create(
    unit: KnowledgeUnit,
    preflight: UnitTargetPreflight,
    *,
    unit_index: int,
    repository: VaultRepository,
    schema: dict[str, Any],
    actor: str,
    now: str,
    rendered_facts: tuple[str, ...] | None = None,
    request_id: str | None = None,
    fact_ordinals: tuple[int, ...] | None = None,
) -> EntityPersistenceResult:
    """Materialize one preflight-authorized CREATE without semantic rendering.

    Args:
        unit: Validated record unit containing canonical mutations and prepared facts.
        preflight: Matching Phase 16.5B CREATE identity and path allocation.
        unit_index: Ordered WriteAction index of ``unit``; must match ``preflight.unit_index``.
        repository: Authoritative Markdown repository.
        schema: Active canonical note schema.
        actor: Application identity recorded by Phase 12 persistence.
        now: Explicit canonical lifecycle timestamp.
        rendered_facts: Phase 16.5C facts, required when the unit has references.

    Returns:
        The one Phase 12 CREATE persistence result at revision 1.

    Raises:
        MaterializationError: If the unit, preflight, references, metadata, or body is unsafe.
        NoteValidationError: If the staged note cannot satisfy the canonical schema.
        EntityAlreadyExistsError: If the preallocated ID already exists.
        NoteAlreadyExistsError: If the preallocated path is occupied.
    """
    _validate_create_preconditions(unit, preflight, unit_index)
    if unit.references and rendered_facts is None:
        raise MaterializationError("References require safe pre-writer rendered_facts")
    if rendered_facts is not None:
        try:
            validate_rendered_facts(unit, rendered_facts)
        except ReferenceBindingError as error:
            raise MaterializationError("Rendered facts do not match the KnowledgeUnit") from error

    prepared_facts = rendered_facts if rendered_facts is not None else unit.facts
    if any("{{ref:" in fact for fact in prepared_facts):
        raise MaterializationError("Raw reference markers cannot reach CREATE persistence")
    metadata = _stage_create_metadata(unit, preflight)
    content = (
        render_atomic_facts(prepared_facts, request_id, fact_ordinals or (), now)
        if request_id is not None and prepared_facts
        else "\n".join(prepared_facts)
    )
    _validate_create_candidate(metadata, content, preflight.stable_id or "", actor, now, schema)
    return create_entity(
        repository,
        schema,
        path=preflight.path or "",
        entity_id=preflight.stable_id or "",
        metadata=metadata,
        content=content,
        actor=actor,
        now=now,
    )


def _validate_create_preconditions(
    unit: KnowledgeUnit, preflight: UnitTargetPreflight, unit_index: int
) -> None:
    """Validate the immutable CREATE hand-off without resolving or allocating anything."""
    if not isinstance(unit, KnowledgeUnit):
        raise MaterializationError("CREATE materialization requires a KnowledgeUnit")
    if unit.intent != "record":
        raise MaterializationError("CREATE materialization requires record intent")
    if not isinstance(preflight, UnitTargetPreflight):
        raise MaterializationError("CREATE materialization requires target preflight")
    if not isinstance(unit_index, int) or isinstance(unit_index, bool) or unit_index < 0:
        raise MaterializationError("CREATE materialization requires a non-negative unit index")
    if preflight.unit_index != unit_index:
        raise MaterializationError("CREATE preflight unit_index does not match the KnowledgeUnit")
    if preflight.outcome is not WriteTargetOutcome.CREATE:
        raise MaterializationError("CREATE materialization requires CREATE preflight")
    if not isinstance(unit.target.type, str) or not unit.target.type.strip():
        raise MaterializationError("CREATE target requires a canonical type")
    if not isinstance(preflight.stable_id, str) or not preflight.stable_id.strip():
        raise MaterializationError("CREATE preflight requires a preallocated stable ID")
    if not isinstance(preflight.canonical_name, str) or not preflight.canonical_name.strip():
        raise MaterializationError("CREATE preflight requires a canonical name")
    if (
        not isinstance(preflight.path, str)
        or not preflight.path
        or preflight.path.startswith(("/", "\\"))
        or "\\" in preflight.path
        or any(part in {"", ".", ".."} for part in preflight.path.split("/"))
        or not preflight.path.endswith(".md")
    ):
        raise MaterializationError("CREATE preflight requires a safe Markdown path")


def _stage_create_metadata(unit: KnowledgeUnit, preflight: UnitTargetPreflight) -> dict[str, Any]:
    """Stage canonical CREATE metadata from empty domain state and explicit mutations."""
    metadata: dict[str, Any] = {
        "name": preflight.canonical_name,
        "type": unit.target.type,
    }
    for change in unit.properties:
        if not isinstance(change, PropertyChange) or change.field in {"name", "type", "tags"}:
            raise MaterializationError("CREATE property mutation is not canonical")
        if change.op == "set":
            metadata[change.field] = change.value
        elif change.op == "remove":
            metadata.pop(change.field, None)
        else:
            raise MaterializationError("KnowledgeUnit property mutation is invalid")
    tags: list[str] = []
    for change in unit.tag_changes:
        if not isinstance(change, TagChange):
            raise MaterializationError("CREATE tag mutation is invalid")
        if change.op == "add":
            if change.value not in tags:
                tags.append(change.value)
        elif change.op == "remove":
            tags = [tag for tag in tags if tag != change.value]
        else:
            raise MaterializationError("CREATE tag mutation is invalid")
    if tags:
        metadata["tags"] = tags

    return metadata


def _validate_create_candidate(
    metadata: dict[str, Any],
    content: str,
    entity_id: str,
    actor: str,
    now: str,
    schema: dict[str, Any],
) -> None:
    """Validate the complete staged CREATE note before invoking persistence."""
    lifecycle = {
        "id": entity_id,
        "created_at": now,
        "updated_at": now,
        "created_by": normalize_actor_provenance(actor),
        "updated_by": normalize_actor_provenance(actor),
        "revision": 1,
        "schema_version": schema.get("schema_version"),
    }
    validate_note(Note(metadata={**metadata, **lifecycle}, content=content), schema)


@dataclass(frozen=True, slots=True)
class WriterRequest:
    """Describe full authoritative context for one bounded writer call."""

    note_id: str
    note_type: str
    intent: str
    facts: tuple[str, ...]
    current_body: str


@dataclass(frozen=True, slots=True)
class WriterOperation:
    """Represent one validated bounded mutation of an authoritative Markdown body."""

    op: str
    text: str | None = None
    old: str | None = None
    new: str | None = None


class BoundedNoteWriter(Protocol):
    """Define the injected provider boundary for one full-note bounded UPDATE decision."""

    def write(self, request: WriterRequest) -> object:
        """Return untrusted structured writer output for one supplied full-note request."""


class OpenAILunaWriter:
    """Call the selected Luna-medium Responses API writer policy once per request."""

    def __init__(self, *, timeout_seconds: float = 120.0) -> None:
        """Configure the bounded writer transport timeout.

        Args:
            timeout_seconds: Maximum time to wait for one Responses API call.
        """
        self.timeout_seconds = timeout_seconds

    def write(self, request: WriterRequest) -> object:
        """Call Luna with full authoritative context and return unvalidated JSON.

        Args:
            request: Already-resolved target and remaining free-text facts.

        Raises:
            WriterProviderError: If credentials, transport, response state, or JSON are unusable.
        """
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise WriterProviderError("OPENAI_API_KEY is required for the bounded writer")
        http_request = urllib.request.Request(
            "https://api.openai.com/v1/responses",
            data=json.dumps(build_openai_writer_payload(request), ensure_ascii=False).encode(
                "utf-8"
            ),
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(http_request, timeout=self.timeout_seconds) as response:
                response_body = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
            raise WriterProviderError("OpenAI bounded writer request failed") from error
        if not isinstance(response_body, dict):
            raise WriterProviderError("OpenAI bounded writer response was not an object")
        if response_body.get("status") != "completed":
            raise WriterProviderError("OpenAI bounded writer response did not complete")
        try:
            output = json.loads(_response_output_text(response_body))
        except (TypeError, json.JSONDecodeError) as error:
            raise WriterProviderError("OpenAI bounded writer output was not valid JSON") from error
        if not isinstance(output, dict):
            raise WriterProviderError("OpenAI bounded writer output was not a JSON object")
        return output


def build_openai_writer_payload(request: WriterRequest) -> dict[str, Any]:
    """Build the strict no-storage Responses payload for the selected writer policy.

    Args:
        request: Full authoritative note context and remaining facts to reconcile.

    Returns:
        JSON-compatible Luna/medium Structured Outputs payload.
    """
    return {
        "model": WRITER_MODEL,
        "store": False,
        "reasoning": {"effort": WRITER_REASONING_EFFORT},
        "input": [
            {"role": "system", "content": _WRITER_INSTRUCTIONS},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "mode": "UPDATE",
                        "canonical_note_id": request.note_id,
                        "canonical_note_type": request.note_type,
                        "write_intent": request.intent,
                        "facts": list(request.facts),
                        "current_authoritative_markdown_body": request.current_body,
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
            },
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "odyssey_bounded_update",
                "strict": True,
                "schema": writer_output_json_schema(),
            }
        },
    }


def writer_output_json_schema() -> dict[str, Any]:
    """Return the provider-compatible closed schema for UPDATE-only bounded operations."""
    operation = {
        "type": "object",
        "properties": {
            "op": {"type": "string", "enum": ["NO_CHANGE", "APPEND", "REPLACE", "REMOVE"]},
            "text": {"type": ["string", "null"]},
            "old": {"type": ["string", "null"]},
            "new": {"type": ["string", "null"]},
        },
        "required": ["op", "text", "old", "new"],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {"operations": {"type": "array", "minItems": 1, "items": operation}},
        "required": ["operations"],
        "additionalProperties": False,
    }


def materialize_update(
    unit: KnowledgeUnit,
    decision: WriteTargetDecision,
    *,
    repository: VaultRepository,
    schema: dict[str, Any],
    actor: str,
    now: str,
    writer: BoundedNoteWriter | None = None,
    rendered_facts: tuple[str, ...] | None = None,
    request_id: str | None = None,
    fact_ordinals: tuple[int, ...] | None = None,
    fact_selector: AtomicFactSelector | None = None,
) -> EntityPersistenceResult:
    """Materialize one resolved existing-note UPDATE with one guarded persistence operation.

    Args:
        unit: Validated Phase 15 properties, tags, and free-text facts.
        decision: Phase 16.1 decision identifying the existing target.
        repository: Authoritative Markdown repository.
        schema: Active canonical note schema.
        actor: Application identity recorded by Phase 12 persistence.
        now: Explicit canonical lifecycle timestamp.
        writer: Injected writer required only for remaining non-duplicate facts.
        rendered_facts: Core-rendered facts from Phase 16.5C. Required when references exist.

    Returns:
        The one Phase 12 persistence result.

    Raises:
        MaterializationError: If target or staged mutation is unsafe.
        WriterProviderError: If the injected writer fails.
        WriterOutputError: If bounded operations cannot safely apply.
    """
    if unit.references and rendered_facts is None:
        raise MaterializationError("References require safe pre-writer rendered_facts")
    if rendered_facts is not None:
        try:
            validate_rendered_facts(unit, rendered_facts)
        except ReferenceBindingError as error:
            raise MaterializationError("Rendered facts do not match the KnowledgeUnit") from error
    if unit.intent == "delete":
        raise MaterializationError("Whole-note delete materialization is not implemented")
    path, existing = _load_existing_target(repository, schema, decision)
    set_metadata, remove_metadata = _stage_structured_mutations(
        existing, unit.properties, unit.tag_changes
    )
    prepared_facts = rendered_facts if rendered_facts is not None else unit.facts
    remaining_facts = (
        prepared_facts
        if unit.intent == "remove"
        else tuple(
            fact
            for fact in prepared_facts
            if not is_exact_normalized_duplicate(existing.content, fact)
        )
    )
    content = existing.content
    if request_id is not None and unit.intent == "remove":
        try:
            existing_atomic = parse_atomic_facts(existing.content)
            targets = tuple(
                target
                for description in prepared_facts
                if (target := find_unique_atomic_fact(existing.content, description)) is not None
            )
        except ValueError as error:
            raise MaterializationError("Existing atomic facts are malformed") from error
        if len(targets) == len(prepared_facts) and len({target.start for target in targets}) == len(
            targets
        ):
            for target in sorted(targets, key=lambda item: item.start, reverse=True):
                content = remove_atomic_fact(content, target)
            remaining_facts = ()
        elif existing_atomic:
            if fact_selector is None or len(prepared_facts) != 1:
                raise MaterializationError("Atomic fact removal is ambiguous or lacks a selector")
            candidates = tuple(FactCandidate(fact.locator, fact.text) for fact in existing_atomic)
            selected = validate_fact_selection(
                fact_selector.select(
                    decision.existing_note_id or "", prepared_facts[0], candidates
                ),
                candidates,
            )
            if selected.outcome != "MATCH":
                raise MaterializationError(f"Atomic fact selector returned {selected.outcome}")
            target = next(fact for fact in existing_atomic if fact.locator == selected.locator)
            content = remove_atomic_fact(content, target)
            remaining_facts = ()
    if request_id is not None and unit.intent != "remove":
        if fact_ordinals is None or len(fact_ordinals) != len(prepared_facts):
            raise MaterializationError("Atomic UPDATE requires one deterministic ordinal per fact")
        try:
            existing_atomic = parse_atomic_facts(existing.content)
            known = {normalize_atomic_fact(item.text) for item in existing_atomic}
            replayed_ordinals = {
                item.ordinal for item in existing_atomic if item.request_id == request_id
            }
        except ValueError as error:
            raise MaterializationError("Existing atomic facts are malformed") from error
        additions = tuple(
            fact
            for fact, ordinal in zip(prepared_facts, fact_ordinals, strict=True)
            if ordinal not in replayed_ordinals and normalize_atomic_fact(fact) not in known
        )
        addition_ordinals = tuple(
            ordinal
            for fact, ordinal in zip(prepared_facts, fact_ordinals, strict=True)
            if ordinal not in replayed_ordinals and normalize_atomic_fact(fact) not in known
        )
        if additions:
            content = append_atomic_facts(
                existing.content, additions, request_id, addition_ordinals, now
            )
        remaining_facts = ()
    if remaining_facts:
        if writer is None:
            raise MaterializationError("A bounded writer is required for non-duplicate facts")
        try:
            output = writer.write(
                WriterRequest(
                    decision.existing_note_id or "",
                    existing.metadata["type"],
                    unit.intent,
                    remaining_facts,
                    existing.content,
                )
            )
        except MaterializationError:
            raise
        except Exception as error:
            raise WriterProviderError("Bounded writer failed") from error
        operations = validate_writer_output(output, existing.content)
        content = apply_writer_operations(existing.content, operations)
        _validate_bound_wikilinks(existing.content, content, remaining_facts, unit.intent)
    _validate_staged_note(existing, schema, set_metadata, remove_metadata, content)
    if not set_metadata and not remove_metadata and content == existing.content:
        return EntityPersistenceResult(
            PersistenceOperation.NO_CHANGE,
            decision.existing_note_id or "",
            path,
            existing.metadata["revision"],
        )
    return update_entity(
        repository,
        schema,
        path=path,
        expected_id=decision.existing_note_id or "",
        expected_revision=existing.metadata["revision"],
        set_metadata=set_metadata,
        remove_metadata=remove_metadata,
        content=content,
        actor=actor,
        now=now,
    )


def materialize_delete(
    unit: KnowledgeUnit,
    decision: WriteTargetDecision,
    *,
    repository: VaultRepository,
    schema: dict[str, Any],
    actor: str,
    now: str,
) -> EntityPersistenceResult:
    """Materialize one resolved single-note DELETE through Core lifecycle persistence.

    Args:
        unit: Validated factless ``delete`` unit with ``cardinality=one``.
        decision: Existing active target selected before this materialization boundary.
        repository: Authoritative Markdown repository.
        schema: Active canonical note schema.
        actor: Application identity recorded by Core lifecycle metadata.
        now: Explicit canonical lifecycle timestamp.

    Returns:
        The dedicated revision-guarded soft-delete persistence result.

    Raises:
        MaterializationError: If the planned delete or resolved target is unsafe.
    """
    if unit.intent != "delete" or unit.cardinality != "one":
        raise MaterializationError(
            "Delete materialization requires intent=delete and cardinality=one"
        )
    if unit.properties or unit.tag_changes or unit.facts or unit.references:
        raise MaterializationError("Delete materialization requires an empty mutation payload")
    path, existing = _load_existing_target(repository, schema, decision)
    return soft_delete_entity(
        repository,
        schema,
        path=path,
        expected_id=decision.existing_note_id or "",
        expected_revision=existing.metadata["revision"],
        actor=actor,
        now=now,
    )


def materialize_type_migration(
    unit: KnowledgeUnit,
    decision: WriteTargetDecision,
    *,
    repository: VaultRepository,
    schema: dict[str, Any],
    actor: str,
    now: str,
) -> EntityPersistenceResult:
    """Migrate one resolved active note in place without a writer or link rewrite.

    Args:
        unit: Validated ``amend`` unit with one destination type.
        decision: Already-resolved existing source identity.
        repository: Authoritative Markdown repository.
        schema: Active canonical schema.
        actor: Lifecycle updater identity.
        now: Canonical update timestamp.

    Returns:
        The single revision-guarded migration persistence result.

    Raises:
        MaterializationError: If the migration is lossy, incomplete, or otherwise unsupported.
    """
    if unit.destination_type is None:
        raise MaterializationError("Type migration requires destination_type")
    if unit.intent != "amend" or unit.cardinality != "one":
        raise MaterializationError("Type migration requires intent=amend and cardinality=one")
    if unit.facts or unit.references:
        raise MaterializationError("Initial type migration supports metadata-only mutations")
    path, existing = _load_existing_target(repository, schema, decision)
    if existing.metadata.get("deleted") is True:
        raise MaterializationError("Type migration requires an active source note")
    metadata = dict(existing.metadata)
    metadata["type"] = unit.destination_type
    set_metadata, remove_metadata = _stage_structured_mutations(
        existing, unit.properties, unit.tag_changes
    )
    metadata.update(set_metadata)
    for field in remove_metadata:
        metadata.pop(field, None)
    destination = Note(metadata=metadata, content=existing.content)
    try:
        validate_note(destination, schema)
    except Exception as error:
        raise MaterializationError("Type migration destination note is invalid") from error
    return migrate_entity(
        repository,
        schema,
        path=path,
        expected_id=decision.existing_note_id or "",
        expected_revision=existing.metadata["revision"],
        destination=destination,
        actor=actor,
        now=now,
    )


def _validate_bound_wikilinks(
    original_body: str, rendered_body: str, facts: tuple[str, ...], intent: str
) -> None:
    """Ensure bounded writer operations preserve prepared links and never invent new links."""
    required = required_bound_wikilinks(facts)
    original = required_bound_wikilinks((original_body,))
    actual = required_bound_wikilinks((rendered_body,))
    if intent == "remove":
        if any(count > original[link] for link, count in actual.items()):
            raise WriterOutputError("Writer output invented an unbound wikilink")
        return
    for link, count in required.items():
        if actual[link] < count:
            raise WriterOutputError("Writer output dropped a required bound wikilink")
    allowed = original + required
    if any(count > allowed[link] for link, count in actual.items()):
        raise WriterOutputError("Writer output invented an unbound wikilink")


def validate_writer_output(output: object, body: str) -> tuple[WriterOperation, ...]:
    """Validate untrusted writer output against the exact supplied authoritative body."""
    if not isinstance(output, Mapping) or set(output) != {"operations"}:
        raise WriterOutputError("Writer output has an invalid schema")
    raw_operations = output["operations"]
    if not isinstance(raw_operations, list) or not raw_operations:
        raise WriterOutputError("Writer output requires non-empty operations")
    operations = tuple(_validate_operation(item) for item in raw_operations)
    if any(operation.op == "NO_CHANGE" for operation in operations) and len(operations) != 1:
        raise WriterOutputError("NO_CHANGE cannot be combined with mutations")
    ranges: list[tuple[int, int]] = []
    for operation in operations:
        if operation.old is None:
            continue
        start = body.find(operation.old)
        if start < 0:
            raise WriterOutputError("Writer operation references a missing exact span")
        if body.find(operation.old, start + 1) >= 0:
            raise WriterOutputError("Writer operation exact span is ambiguous")
        ranges.append((start, start + len(operation.old)))
    ranges.sort()
    if any(later[0] < earlier[1] for earlier, later in zip(ranges, ranges[1:], strict=False)):
        raise WriterOutputError("Writer operations have overlapping exact spans")
    return operations


def apply_writer_operations(body: str, operations: tuple[WriterOperation, ...]) -> str:
    """Apply validated operations without shifting later exact positions.

    Args:
        body: Exact body used for validation.
        operations: Validated operations grounded in that body.

    Returns:
        New body with unrelated Markdown preserved exactly.
    """
    replacements: list[tuple[int, int, str]] = []
    appends: list[str] = []
    for operation in operations:
        if operation.op == "APPEND":
            assert operation.text is not None
            appends.append(operation.text)
        elif operation.op == "REPLACE":
            assert operation.old is not None and operation.new is not None
            start = body.find(operation.old)
            replacements.append((start, start + len(operation.old), operation.new))
        elif operation.op == "REMOVE":
            assert operation.old is not None
            start = body.find(operation.old)
            replacements.append((start, start + len(operation.old), ""))
    result = body
    for start, end, replacement in sorted(replacements, reverse=True):
        result = result[:start] + replacement + result[end:]
    for text in appends:
        result += ("\n" if result and not result.endswith("\n") else "") + text
    return result


def is_exact_normalized_duplicate(body: str, fact: str) -> bool:
    """Return whether a fact matches a body line under the narrow exact duplicate rule."""
    normalized_fact = _normalize_exact_text(fact)
    return bool(normalized_fact) and any(
        normalized_fact == _normalize_exact_text(line) for line in body.splitlines()
    )


def _load_existing_target(
    repository: VaultRepository, schema: dict[str, Any], decision: WriteTargetDecision
) -> tuple[str, Note]:
    """Load the one schema-valid authoritative note selected by an UPDATE decision."""
    if decision.outcome is not WriteTargetOutcome.UPDATE or not decision.existing_note_id:
        raise MaterializationError("Materialization requires one resolved UPDATE target")
    found: list[tuple[str, Note]] = []
    for path in repository.list_markdown_paths():
        note = parse_note(repository.read_text(path))
        validate_note(note, schema)
        if note.metadata.get("id") == decision.existing_note_id:
            found.append((path, note))
    if len(found) != 1:
        raise MaterializationError("Resolved UPDATE target is unavailable or non-unique")
    return found[0]


def _stage_structured_mutations(
    existing: Note, properties: tuple[PropertyChange, ...], tag_changes: tuple[TagChange, ...]
) -> tuple[dict[str, Any], tuple[str, ...]]:
    """Stage canonical property and explicit free-form tag mutations without persistence."""
    set_metadata: dict[str, Any] = {}
    remove_metadata: list[str] = []
    for change in properties:
        if change.op == "set":
            set_metadata[change.field] = change.value
        elif change.op == "remove":
            remove_metadata.append(change.field)
        else:
            raise MaterializationError("KnowledgeUnit property mutation is invalid")
    tags = list(existing.metadata.get("tags", []))
    for change in tag_changes:
        if not isinstance(change, TagChange):
            raise MaterializationError("KnowledgeUnit tag mutation is invalid")
        if change.op == "add":
            if change.value not in tags:
                tags.append(change.value)
        elif change.op == "remove":
            tags = [tag for tag in tags if tag != change.value]
        else:
            raise MaterializationError("KnowledgeUnit tag mutation is invalid")
    if tag_changes:
        if tags:
            set_metadata["tags"] = tags
        else:
            remove_metadata.append("tags")
    if set(set_metadata) & set(remove_metadata):
        raise MaterializationError("Structured mutations both set and remove one field")
    return set_metadata, tuple(remove_metadata)


def _validate_staged_note(
    existing: Note,
    schema: dict[str, Any],
    set_metadata: Mapping[str, Any],
    remove_metadata: tuple[str, ...],
    content: str,
) -> None:
    """Validate complete in-memory structured and body changes before persistence."""
    metadata = dict(existing.metadata)
    metadata.update(set_metadata)
    for field in remove_metadata:
        metadata.pop(field, None)
    validate_note(Note(metadata=metadata, content=content), schema)


def _validate_operation(item: object) -> WriterOperation:
    """Validate one operation after dropping provider-required null fields."""
    if not isinstance(item, Mapping):
        raise WriterOutputError("Writer operation is not an object")
    provider_fields = {"op", "text", "old", "new"}
    if not set(item).issubset(provider_fields):
        raise WriterOutputError("Writer operation has an invalid schema")
    compact = {key: value for key, value in item.items() if value is not None}
    op = compact.get("op")
    required = {
        "NO_CHANGE": {"op"},
        "APPEND": {"op", "text"},
        "REPLACE": {"op", "old", "new"},
        "REMOVE": {"op", "old"},
    }
    if not isinstance(op, str) or op not in required or set(compact) != required[op]:
        raise WriterOutputError("Writer operation has an invalid schema")
    if any(
        not isinstance(value, str) or not value.strip()
        for key, value in compact.items()
        if key != "op"
    ):
        raise WriterOutputError("Writer operation text must be non-empty")
    if op == "REPLACE" and compact["old"] == compact["new"]:
        raise WriterOutputError("Writer replacement cannot be an identity operation")
    return WriterOperation(op, compact.get("text"), compact.get("old"), compact.get("new"))


def _normalize_exact_text(value: str) -> str:
    """Normalize only whitespace and one leading unordered-list marker."""
    collapsed = " ".join(value.strip().split())
    for marker in ("- ", "* ", "+ "):
        if collapsed.startswith(marker):
            return collapsed[len(marker) :]
    return collapsed


def _response_output_text(response: Mapping[str, Any]) -> str:
    """Extract exactly one Responses output-text item from a completed response."""
    texts = [
        content.get("text")
        for item in response.get("output", [])
        if isinstance(item, Mapping) and item.get("type") == "message"
        for content in item.get("content", [])
        if isinstance(content, Mapping) and content.get("type") == "output_text"
    ]
    if len(texts) != 1 or not isinstance(texts[0], str):
        raise WriterProviderError("OpenAI bounded writer response lacked one output-text item")
    return texts[0]
