"""Provider-free semantic WRITE values and deterministic lowering to Core actions."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from odyssey_core.context import ContextFilter
from odyssey_core.planner_capabilities import build_planner_capabilities, build_write_capabilities
from odyssey_core.request_planning import (
    SELF_TARGET,
    PropertyChange,
    RequestPlanningError,
    TagChange,
    WriteAction,
    planner_filter_array_json_schema,
    planner_property_changes_json_schema,
    validate_request_plan,
)


class SemanticWriteCompileError(ValueError):
    """Indicate a semantic WRITE value that cannot safely lower to the Core contract."""


class ApplyTo(StrEnum):
    """Express whether an operation applies to one identity or a deterministic matching set."""

    ONE = "one"
    ALL_MATCHING = "all_matching"


class IdentityBinding(StrEnum):
    """Describe whether an identity is the authenticated self or ordinary described identity."""

    SELF = "self"
    DESCRIBED = "described"


class CandidateScopeExtent(StrEnum):
    """Describe whether a candidate scope selects one member or its complete current set."""

    ONE_MEMBER = "one_member"
    COMPLETE_SET = "complete_set"


@dataclass(frozen=True, slots=True)
class ExistingSource:
    """Preserve the description of one existing non-recursive relationship source."""

    description: str


@dataclass(frozen=True, slots=True)
class CandidateScope:
    """Bound one described identity through self or one existing relationship source."""

    source: IdentityBinding | ExistingSource
    member_query: str
    extent: CandidateScopeExtent


@dataclass(frozen=True, slots=True)
class IdentityIntent:
    """Preserve semantic identity evidence without claiming a canonical identity."""

    description: str
    binding: IdentityBinding
    direct_name: str | None = None
    note_type: str | None = None
    filters: tuple[ContextFilter, ...] = ()
    candidate_scope: CandidateScope | None = None


@dataclass(frozen=True, slots=True)
class LiteralPart:
    """Keep one literal, non-reference span of a semantic fact."""

    text: str


@dataclass(frozen=True, slots=True)
class IdentityPart:
    """Keep one exact fact mention together with its independently selectable identity."""

    text: str
    identity: IdentityIntent


@dataclass(frozen=True, slots=True)
class SemanticFact:
    """Represent one ordered fact before Core assigns local reference markers."""

    parts: tuple[LiteralPart | IdentityPart, ...]


@dataclass(frozen=True, slots=True)
class SemanticWriteOperation:
    """Represent one semantic mutation target and its ordered payload without Core mechanics."""

    target: IdentityIntent
    apply_to: ApplyTo
    intent: str
    facts: tuple[SemanticFact, ...] = ()
    properties: tuple[PropertyChange, ...] = ()
    tag_changes: tuple[TagChange, ...] = ()
    destination_type: str | None = None


@dataclass(frozen=True, slots=True)
class SemanticWriteIntent:
    """Contain ordered semantic write operations for deterministic Core lowering."""

    operations: tuple[SemanticWriteOperation, ...]


def semantic_write_schema_definitions(schema: Mapping[str, Any]) -> dict[str, Any]:
    """Build the closed dynamic Structured Outputs definitions for Luna semantic WRITE.

    Note types, filters, writable properties, property value types, and destination types are
    projected from the canonical schema. The returned definitions are intended to be installed in
    the provider schema root so their ``#/$defs`` references remain valid.
    """
    retrieval = build_planner_capabilities(schema)
    writable = build_write_capabilities(schema)
    note_type = {
        "anyOf": [
            {"type": "null"},
            {"type": "string", "enum": list(retrieval["types"])},
        ]
    }
    candidate_scope = {
        "type": "object",
        "properties": {
            "source": {
                "anyOf": [
                    {
                        "type": "object",
                        "properties": {"kind": {"type": "string", "enum": ["SELF"]}},
                        "required": ["kind"],
                        "additionalProperties": False,
                    },
                    {
                        "type": "object",
                        "properties": {
                            "kind": {
                                "type": "string",
                                "enum": ["SOURCE_DESCRIPTION"],
                            },
                            "description": {"type": "string", "maxLength": 256},
                        },
                        "required": ["kind", "description"],
                        "additionalProperties": False,
                    },
                ]
            },
            "member_query": {"type": "string", "maxLength": 256},
            "extent": {
                "type": "string",
                "enum": ["one_member", "complete_set"],
            },
        },
        "required": ["source", "member_query", "extent"],
        "additionalProperties": False,
    }
    identity = {
        "type": "object",
        "properties": {
            "description": {"type": "string", "maxLength": 256},
            "binding": {"type": "string", "enum": ["self", "described"]},
            "direct_name": {"type": ["string", "null"]},
            "note_type": note_type,
            "filters": {"$ref": "#/$defs/filter_array"},
            "candidate_scope": {
                "anyOf": [
                    {"type": "null"},
                    {"$ref": "#/$defs/semantic_candidate_scope"},
                ]
            },
        },
        "required": [
            "description",
            "binding",
            "direct_name",
            "note_type",
            "filters",
            "candidate_scope",
        ],
        "additionalProperties": False,
    }
    literal_part = {
        "type": "object",
        "properties": {
            "kind": {"type": "string", "enum": ["literal"]},
            "text": {"type": "string"},
        },
        "required": ["kind", "text"],
        "additionalProperties": False,
    }
    identity_part = {
        "type": "object",
        "properties": {
            "kind": {"type": "string", "enum": ["identity"]},
            "text": {"type": "string", "maxLength": 256},
            "identity": {"$ref": "#/$defs/semantic_identity"},
        },
        "required": ["kind", "text", "identity"],
        "additionalProperties": False,
    }
    fact = {
        "type": "object",
        "properties": {
            "parts": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "anyOf": [
                        {"$ref": "#/$defs/semantic_literal_part"},
                        {"$ref": "#/$defs/semantic_identity_part"},
                    ]
                },
            }
        },
        "required": ["parts"],
        "additionalProperties": False,
    }
    operation = {
        "type": "object",
        "properties": {
            "target": {"$ref": "#/$defs/semantic_identity"},
            "apply_to": {"type": "string", "enum": ["one", "all_matching"]},
            "intent": {"type": "string", "enum": ["record", "amend", "remove", "delete"]},
            "facts": {
                "type": "array",
                "items": {"$ref": "#/$defs/semantic_fact"},
            },
            "properties": {"$ref": "#/$defs/semantic_property_changes"},
            "tag_changes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "op": {"type": "string", "enum": ["add", "remove"]},
                        "value": {"type": "string"},
                    },
                    "required": ["op", "value"],
                    "additionalProperties": False,
                },
            },
            "destination_type": {
                "anyOf": [
                    {"type": "null"},
                    {"type": "string", "enum": sorted(writable["types"])},
                ]
            },
        },
        "required": [
            "target",
            "apply_to",
            "intent",
            "facts",
            "properties",
            "tag_changes",
            "destination_type",
        ],
        "additionalProperties": False,
    }
    return {
        "filter_array": planner_filter_array_json_schema(retrieval),
        "semantic_candidate_scope": candidate_scope,
        "semantic_identity": identity,
        "semantic_literal_part": literal_part,
        "semantic_identity_part": identity_part,
        "semantic_fact": fact,
        "semantic_property_changes": planner_property_changes_json_schema(writable),
        "semantic_operation": operation,
    }


def semantic_write_action_json_schema() -> dict[str, Any]:
    """Return the closed write-action branch referencing semantic root definitions."""
    return {
        "type": "object",
        "properties": {
            "kind": {"type": "string", "enum": ["write"]},
            "operations": {
                "type": "array",
                "minItems": 1,
                "items": {"$ref": "#/$defs/semantic_operation"},
            },
        },
        "required": ["kind", "operations"],
        "additionalProperties": False,
    }


def decode_semantic_write_action(raw: Any) -> SemanticWriteIntent:
    """Decode one closed provider write action without accepting Core mechanical fields.

    Args:
        raw: Untrusted JSON-decoded Luna action.
    Returns:
        Immutable semantic WRITE intent preserving operation and fact-part order.

    Raises:
        SemanticWriteCompileError: If any object is open, correlated state is invalid, or the
            resulting meaning cannot compile through the existing Core contract.
    """
    if not isinstance(raw, dict) or set(raw) != {"kind", "operations"}:
        raise SemanticWriteCompileError("Semantic write action fields are invalid")
    if raw["kind"] != "write" or not isinstance(raw["operations"], list):
        raise SemanticWriteCompileError("Semantic write action is invalid")
    return SemanticWriteIntent(tuple(_decode_operation(item) for item in raw["operations"]))


def _decode_operation(raw: Any) -> SemanticWriteOperation:
    """Decode one closed semantic operation while retaining provider order."""
    required = {
        "target",
        "apply_to",
        "intent",
        "facts",
        "properties",
        "tag_changes",
        "destination_type",
    }
    if not isinstance(raw, dict) or set(raw) != required:
        raise SemanticWriteCompileError("Semantic write operation fields are invalid")
    try:
        apply_to = ApplyTo(raw["apply_to"])
    except (TypeError, ValueError) as error:
        raise SemanticWriteCompileError("Semantic write apply_to is invalid") from error
    facts = raw["facts"]
    properties = raw["properties"]
    tags = raw["tag_changes"]
    if (
        not isinstance(facts, list)
        or not isinstance(properties, list)
        or not isinstance(tags, list)
    ):
        raise SemanticWriteCompileError("Semantic write operation payload is invalid")
    return SemanticWriteOperation(
        target=_decode_identity(raw["target"]),
        apply_to=apply_to,
        intent=raw["intent"],
        facts=tuple(_decode_fact(item) for item in facts),
        properties=tuple(_decode_property(item) for item in properties),
        tag_changes=tuple(_decode_tag(item) for item in tags),
        destination_type=raw["destination_type"],
    )


def _decode_identity(raw: Any) -> IdentityIntent:
    """Decode one non-recursive semantic identity object."""
    required = {
        "description",
        "binding",
        "direct_name",
        "note_type",
        "filters",
        "candidate_scope",
    }
    if not isinstance(raw, dict) or set(raw) != required:
        raise SemanticWriteCompileError("Semantic identity fields are invalid")
    try:
        binding = IdentityBinding(raw["binding"])
    except (TypeError, ValueError) as error:
        raise SemanticWriteCompileError("Semantic identity binding is invalid") from error
    filters = raw["filters"]
    if not isinstance(filters, list):
        raise SemanticWriteCompileError("Semantic identity filters are invalid")
    decoded_filters = []
    for item in filters:
        if not isinstance(item, dict) or set(item) != {"field", "op", "value"}:
            raise SemanticWriteCompileError("Semantic identity filter fields are invalid")
        decoded_filters.append(ContextFilter(item["field"], item["op"], item["value"]))
    return IdentityIntent(
        description=raw["description"],
        binding=binding,
        direct_name=raw["direct_name"],
        note_type=raw["note_type"],
        filters=tuple(decoded_filters),
        candidate_scope=_decode_candidate_scope(raw["candidate_scope"]),
    )


def _decode_candidate_scope(raw: Any) -> CandidateScope | None:
    """Decode the closed SELF/source-description union without recursive identity."""
    if raw is None:
        return None
    if not isinstance(raw, dict) or set(raw) != {"source", "member_query", "extent"}:
        raise SemanticWriteCompileError("Candidate scope fields are invalid")
    source = raw["source"]
    if not isinstance(source, dict):
        raise SemanticWriteCompileError("Candidate source is invalid")
    if set(source) == {"kind"} and source["kind"] == "SELF":
        decoded_source: IdentityBinding | ExistingSource = IdentityBinding.SELF
    elif set(source) == {"kind", "description"} and source["kind"] == "SOURCE_DESCRIPTION":
        decoded_source = ExistingSource(source["description"])
    else:
        raise SemanticWriteCompileError("Candidate source fields are invalid")
    try:
        extent = CandidateScopeExtent(raw["extent"])
    except (TypeError, ValueError) as error:
        raise SemanticWriteCompileError("Candidate scope extent is invalid") from error
    return CandidateScope(decoded_source, raw["member_query"], extent)


def _decode_fact(raw: Any) -> SemanticFact:
    """Decode one fact and its closed ordered part union."""
    if not isinstance(raw, dict) or set(raw) != {"parts"} or not isinstance(raw["parts"], list):
        raise SemanticWriteCompileError("Semantic fact fields are invalid")
    parts: list[LiteralPart | IdentityPart] = []
    for part in raw["parts"]:
        if not isinstance(part, dict):
            raise SemanticWriteCompileError("Semantic fact part is invalid")
        if set(part) == {"kind", "text"} and part["kind"] == "literal":
            parts.append(LiteralPart(part["text"]))
        elif set(part) == {"kind", "text", "identity"} and part["kind"] == "identity":
            parts.append(IdentityPart(part["text"], _decode_identity(part["identity"])))
        else:
            raise SemanticWriteCompileError("Semantic fact part fields are invalid")
    return SemanticFact(tuple(parts))


def _decode_property(raw: Any) -> PropertyChange:
    """Decode a closed property change for authoritative Core revalidation."""
    if not isinstance(raw, dict) or set(raw) != {"field", "op", "value"}:
        raise SemanticWriteCompileError("Semantic property fields are invalid")
    return PropertyChange(raw["field"], raw["op"], raw["value"])


def _decode_tag(raw: Any) -> TagChange:
    """Decode a closed explicit tag change for authoritative Core revalidation."""
    if not isinstance(raw, dict) or set(raw) != {"op", "value"}:
        raise SemanticWriteCompileError("Semantic tag fields are invalid")
    return TagChange(raw["op"], raw["value"])


def compile_semantic_write(intent: SemanticWriteIntent, schema: Mapping[str, Any]) -> WriteAction:
    """Compile immutable semantic WRITE intent through the established request-plan validator.

    Args:
        intent: Provider-free semantic mutations whose ownership and decomposition are already set.
        schema: Active canonical schema used by the existing Core validator.

    Returns:
        One validated, fully lowered ``WriteAction`` with Core-owned indexes and lookup units.

    Raises:
        SemanticWriteCompileError: If intent is unsafe, unsupported, or rejected by Core validation.
    """
    if not isinstance(intent, SemanticWriteIntent) or not isinstance(intent.operations, tuple):
        raise SemanticWriteCompileError("Semantic WRITE intent is invalid")
    if not intent.operations or not all(
        isinstance(operation, SemanticWriteOperation) for operation in intent.operations
    ):
        raise SemanticWriteCompileError("Semantic WRITE intent requires operations")
    _validate_action_executable_shape(intent.operations)

    try:
        units = [_compile_operation(operation) for operation in intent.operations]
        plan = validate_request_plan(
            {"actions": [{"kind": "write", "units": units}], "limitations": []}, schema
        )
    except (RequestPlanningError, TypeError, ValueError) as error:
        raise SemanticWriteCompileError(
            "Semantic WRITE intent violates the Core contract"
        ) from error
    action = plan.actions[0]
    if not isinstance(
        action, WriteAction
    ):  # Defensive: the raw shape above is intentionally fixed.
        raise SemanticWriteCompileError("Semantic WRITE compiler did not produce a write action")
    return action


def _validate_action_executable_shape(
    operations: tuple[SemanticWriteOperation, ...],
) -> None:
    """Reject action-wide shapes the existing application cannot execute atomically."""
    if not all(
        isinstance(operation.apply_to, ApplyTo)
        and isinstance(operation.target, IdentityIntent)
        and (
            operation.target.candidate_scope is None
            or isinstance(operation.target.candidate_scope, CandidateScope)
        )
        for operation in operations
    ):
        raise SemanticWriteCompileError("Semantic WRITE operation target is invalid")
    apply_modes = {operation.apply_to for operation in operations}
    if len(apply_modes) > 1:
        raise SemanticWriteCompileError("One write action cannot mix one and all-matching")
    if sum(operation.apply_to is ApplyTo.ALL_MATCHING for operation in operations) > 1:
        raise SemanticWriteCompileError("One write action cannot contain multiple bulk operations")
    relational = [
        operation for operation in operations if operation.target.candidate_scope is not None
    ]
    if len(relational) > 1:
        raise SemanticWriteCompileError(
            "One write action cannot contain multiple material relational targets"
        )
    complete_sets = [
        operation
        for operation in operations
        if operation.target.candidate_scope is not None
        and operation.target.candidate_scope.extent is CandidateScopeExtent.COMPLETE_SET
    ]
    if complete_sets and len(operations) > 1:
        raise SemanticWriteCompileError(
            "A complete-set operation cannot share one material write action"
        )


def _compile_operation(operation: SemanticWriteOperation) -> dict[str, Any]:
    """Project one semantic operation into the existing untrusted raw unit shape."""
    if not isinstance(operation.apply_to, ApplyTo) or operation.intent not in {
        "record",
        "amend",
        "remove",
        "delete",
    }:
        raise SemanticWriteCompileError("Semantic WRITE operation is invalid")
    if not isinstance(operation.facts, tuple) or not isinstance(operation.properties, tuple):
        raise SemanticWriteCompileError("Semantic WRITE operation payload is invalid")
    if not isinstance(operation.tag_changes, tuple):
        raise SemanticWriteCompileError("Semantic WRITE operation payload is invalid")

    target = _compile_identity(operation.target, allow_self=True, allow_complete_set=True)
    _validate_operation_shape(operation, target)
    facts, references = _compile_facts(operation.facts, operation.target)
    return {
        "target": target,
        "cardinality": operation.apply_to.value,
        "intent": operation.intent,
        "properties": [_property_raw(change) for change in operation.properties],
        "tag_changes": [_tag_raw(change) for change in operation.tag_changes],
        "facts": facts,
        "references": references,
        "destination_type": operation.destination_type,
    }


def _validate_operation_shape(operation: SemanticWriteOperation, target: dict[str, Any]) -> None:
    """Reject semantic shapes that existing raw validation cannot faithfully represent."""
    has_payload = bool(
        operation.facts
        or operation.properties
        or operation.tag_changes
        or operation.destination_type is not None
    )
    if operation.intent == "delete" and has_payload:
        raise SemanticWriteCompileError("Delete cannot carry a mutation payload")
    if operation.intent in {"amend", "remove"} and not has_payload:
        raise SemanticWriteCompileError("Amend and remove require a mutation payload")
    if operation.apply_to is ApplyTo.ALL_MATCHING:
        if (
            operation.target.binding is IdentityBinding.SELF
            or operation.target.candidate_scope is not None
            or any(_fact_has_identity_part(fact) for fact in operation.facts)
            or (operation.target.note_type is None and not operation.target.filters)
        ):
            raise SemanticWriteCompileError("All-matching operation lacks deterministic authority")
    scope = operation.target.candidate_scope
    if scope is not None and scope.extent is CandidateScopeExtent.COMPLETE_SET:
        if (
            operation.apply_to is not ApplyTo.ONE
            or operation.intent != "record"
            or len(operation.facts) != 1
            or any(isinstance(part, IdentityPart) for part in operation.facts[0].parts)
            or operation.properties
            or operation.tag_changes
            or operation.destination_type is not None
        ):
            raise SemanticWriteCompileError("Complete set shape is unsupported")
    if operation.destination_type is not None:
        _safe_text(operation.destination_type)
        if operation.apply_to is not ApplyTo.ONE or operation.intent != "amend" or operation.facts:
            raise SemanticWriteCompileError("Type migration must be one metadata-only amendment")
    if target["relational_reference"] is not None and operation.apply_to is ApplyTo.ALL_MATCHING:
        raise SemanticWriteCompileError("Relational targets cannot be all matching")


def _compile_facts(
    facts: tuple[SemanticFact, ...], target: IdentityIntent
) -> tuple[list[str], list[dict[str, Any]]]:
    """Render semantic fact parts and create local semantic reference selections."""
    rendered: list[str] = []
    references: list[dict[str, Any]] = []
    reference_keys: list[tuple[IdentityIntent, str]] = []
    for fact in facts:
        if (
            not isinstance(fact, SemanticFact)
            or not isinstance(fact.parts, tuple)
            or not fact.parts
        ):
            raise SemanticWriteCompileError("Semantic fact is invalid")
        pieces: list[str] = []
        for part in fact.parts:
            if isinstance(part, LiteralPart):
                _safe_literal_text(part.text)
                pieces.append(part.text)
                continue
            if not isinstance(part, IdentityPart):
                raise SemanticWriteCompileError("Semantic fact part is invalid")
            _safe_text(part.text)
            selection = _compile_identity(part.identity, allow_self=False, allow_complete_set=False)
            if part.identity == target:
                raise SemanticWriteCompileError("Fact reference cannot select its own target")
            reference_key = (part.identity, part.text)
            reference_index = next(
                (
                    index
                    for index, existing_key in enumerate(reference_keys)
                    if existing_key == reference_key
                ),
                None,
            )
            if reference_index is None:
                reference_index = len(references)
                reference_keys.append(reference_key)
                references.append(
                    {"selection": selection, "role": "identity", "mention": part.text}
                )
            pieces.append(f"{{{{ref:{reference_index}}}}}")
        rendered.append("".join(pieces))
    return rendered, references


def _compile_identity(
    identity: IdentityIntent, *, allow_self: bool, allow_complete_set: bool
) -> dict[str, Any]:
    """Map one semantic identity losslessly to an existing target or reference selection."""
    if not isinstance(identity, IdentityIntent) or not isinstance(
        identity.binding, IdentityBinding
    ):
        raise SemanticWriteCompileError("Identity intent is invalid")
    _safe_text(identity.description)
    if identity.direct_name is not None:
        _safe_text(identity.direct_name)
    if identity.note_type is not None:
        _safe_text(identity.note_type)
    if not isinstance(identity.filters, tuple) or not all(
        isinstance(item, ContextFilter) for item in identity.filters
    ):
        raise SemanticWriteCompileError("Identity filters are invalid")
    if identity.binding is IdentityBinding.SELF:
        if (
            not allow_self
            or identity.direct_name is not None
            or identity.candidate_scope is not None
        ):
            raise SemanticWriteCompileError("Self identity has unsupported selectors")
        return {
            "entity": None,
            "query": identity.description,
            "type": identity.note_type,
            "filters": [_filter_raw(item) for item in identity.filters],
            "link_scope": None,
            "self_target": SELF_TARGET,
            "relational_reference": None,
            "semantic_set": None,
            "collection_subject": None,
        }
    if identity.binding is not IdentityBinding.DESCRIBED:
        raise SemanticWriteCompileError("Identity binding is invalid")
    relational_reference = _compile_candidate_scope(identity, allow_complete_set=allow_complete_set)
    if relational_reference is not None and (identity.direct_name is not None or identity.filters):
        raise SemanticWriteCompileError("Candidate scope conflicts with direct identity selectors")
    result = {
        "entity": identity.direct_name,
        "query": identity.description,
        "type": identity.note_type,
        "filters": [_filter_raw(item) for item in identity.filters],
        "link_scope": None,
        "self_target": None,
        "relational_reference": relational_reference,
        "semantic_set": None,
        "collection_subject": None,
    }
    if not allow_self:
        return {
            key: result[key]
            for key in ("entity", "query", "type", "filters", "relational_reference")
        }
    return result


def _compile_candidate_scope(
    identity: IdentityIntent, *, allow_complete_set: bool
) -> dict[str, str | None] | None:
    """Map non-recursive semantic scope fields to the existing relational reference value."""
    scope = identity.candidate_scope
    if scope is None:
        return None
    if not isinstance(scope, CandidateScope) or not isinstance(scope.extent, CandidateScopeExtent):
        raise SemanticWriteCompileError("Candidate scope is invalid")
    _safe_text(scope.member_query)
    if scope.extent is CandidateScopeExtent.COMPLETE_SET and not allow_complete_set:
        raise SemanticWriteCompileError("Fact references cannot select a complete set")
    if scope.source is IdentityBinding.SELF:
        source_kind, source_query = "self", None
    elif isinstance(scope.source, ExistingSource):
        _safe_text(scope.source.description)
        source_kind, source_query = "existing", scope.source.description
    else:
        raise SemanticWriteCompileError("Candidate scope source is invalid")
    return {
        "reference": scope.member_query,
        "source_kind": source_kind,
        "source_query": source_query,
        "members": "one" if scope.extent is CandidateScopeExtent.ONE_MEMBER else "complete_set",
    }


def _safe_text(value: object, *, preserve_outer_whitespace: bool = False) -> None:
    """Reject empty or representation-bearing wording without censoring semantic content."""
    if (
        not isinstance(value, str)
        or not value.strip()
        or (not preserve_outer_whitespace and value != value.strip())
        or len(value) > 256
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
        or "{{ref" in value
        or "[[" in value
        or "]]" in value
    ):
        raise SemanticWriteCompileError("Semantic wording is unsafe")


def _safe_literal_text(value: object) -> None:
    """Preserve arbitrary single-line fact spans while reserving Core reference syntax."""
    if (
        not isinstance(value, str)
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
        or "{{ref" in value
        or "[[" in value
        or "]]" in value
    ):
        raise SemanticWriteCompileError("Semantic literal text is unsafe")


def _fact_has_identity_part(fact: SemanticFact) -> bool:
    """Return whether one fact needs a reference selection unavailable to bulk writes."""
    return isinstance(fact, SemanticFact) and any(
        isinstance(part, IdentityPart) for part in fact.parts
    )


def _filter_raw(filter_value: ContextFilter) -> dict[str, Any]:
    """Serialize an existing immutable filter without introducing a second filter representation."""
    return {"field": filter_value.field, "op": filter_value.op, "value": filter_value.value}


def _property_raw(change: PropertyChange) -> dict[str, Any]:
    """Serialize an existing immutable property mutation for Core revalidation."""
    if not isinstance(change, PropertyChange):
        raise SemanticWriteCompileError("Property change is invalid")
    return {"field": change.field, "op": change.op, "value": change.value}


def _tag_raw(change: TagChange) -> dict[str, str]:
    """Serialize an existing immutable tag mutation for Core revalidation."""
    if not isinstance(change, TagChange):
        raise SemanticWriteCompileError("Tag change is invalid")
    return {"op": change.op, "value": change.value}
