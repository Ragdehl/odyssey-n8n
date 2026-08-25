"""UPDATE-only Phase 16 materialization through bounded writer operations."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from odyssey_core.notes import Note, parse_note, validate_note
from odyssey_core.persistence import EntityPersistenceResult, PersistenceOperation, update_entity
from odyssey_core.request_planning import KnowledgeUnit, PropertyChange, TagChange
from odyssey_core.storage import VaultRepository
from odyssey_core.write_target import WriteTargetDecision, WriteTargetOutcome

WRITER_MODEL = "gpt-5.6-luna"
WRITER_REASONING_EFFORT = "medium"
WRITER_CONTEXT_MODE = "FULL_NOTE"
_WRITER_INSTRUCTIONS = (
    "You are Odyssey's bounded Markdown writer. You receive already-interpreted facts and a fixed "
    "UPDATE intent. Do not resolve identity, choose a note ID or path, add metadata, properties, "
    "tags, dates, URLs, wikilinks, or facts not supplied. Return the smallest faithful bounded "
    "operations against the supplied current Markdown body. Every old span must be exact. Do not "
    "rewrite the whole body. Use NO_CHANGE only when every supplied fact is already represented, "
    "and then return it as the only operation. Use APPEND for independent facts, REPLACE for "
    "corrections or temporal changes, and REMOVE only for exact supplied content. Preserve "
    "unrelated information. Return only the requested Structured Outputs object."
)


class MaterializationError(RuntimeError):
    """Indicate that a resolved UPDATE cannot be safely materialized or persisted."""


class WriterProviderError(MaterializationError):
    """Indicate that the bounded writer could not provide a usable response."""


class WriterOutputError(MaterializationError):
    """Indicate malformed, unsafe, or conflicting bounded writer operations."""


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

    Returns:
        The one Phase 12 persistence result.

    Raises:
        MaterializationError: If target or staged mutation is unsafe.
        WriterProviderError: If the injected writer fails.
        WriterOutputError: If bounded operations cannot safely apply.
    """
    if unit.intent == "delete":
        raise MaterializationError("Whole-note delete materialization is not implemented")
    path, existing = _load_existing_target(repository, schema, decision)
    set_metadata, remove_metadata = _stage_structured_mutations(
        existing, unit.properties, unit.tag_changes
    )
    remaining_facts = (
        unit.facts
        if unit.intent == "remove"
        else tuple(
            fact for fact in unit.facts if not is_exact_normalized_duplicate(existing.content, fact)
        )
    )
    content = existing.content
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
        content = apply_writer_operations(
            existing.content, validate_writer_output(output, existing.content)
        )
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
    """Stage canonical properties and explicit controlled tags without persistence."""
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
        if change.op == "add" and change.value not in tags:
            tags.append(change.value)
        elif change.op == "remove":
            tags = [tag for tag in tags if tag != change.value]
        elif change.op != "add":
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
