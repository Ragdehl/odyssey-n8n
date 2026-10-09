"""Non-executing source-grounded fact candidates for Router v1 (inactive).

The candidate proposal is NOT an executable RoutePlan, a Core KnowledgeUnit,
or an identity/fact-write authority. Runtime still consumes Router v0. This
closed boundary allows later provider adapters and local semantic tests without
changing today's provider prompt or canonical mutation policy.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .router import RouterError

MAX_MESSAGE_CHARS = 4096
MAX_CANDIDATES = 26
MAX_ANCHORS_PER_CANDIDATE = 8
MAX_SCOPES_PER_CANDIDATE = 16
MAX_INHERITANCE_PER_CANDIDATE = 16
MAX_ANCHOR_CHARS = 400

# Source roles are grammatical/contextual hints, never NoteSchema or Core target types.
SOURCE_ROLES = frozenset(
    {
        "subject",
        "participants",
        "predicate",
        "predicate_relation",
        "object",
        "date",
        "date_scope",
        "time",
        "time_approx",
        "time_relation",
        "location",
        "polarity",
        "condition",
        "modality",
        "order",
        "transaction",
        "reference",
        "replacement",
    }
)
CANDIDATE_KINDS = frozenset(
    {
        "occurrence",
        "property",
        "relationship",
        "purchase_item",
        "plan",
        "negative",
        "conditional",
        "task",
    }
)
CANDIDATE_STATES = frozenset({"candidate", "ambiguous_identity"})


@dataclass(frozen=True, slots=True)
class SourceAnchor:
    """Identify one exact occurrence of original user text with local offsets.

    Offsets are computed locally. No provider supplied byte/character offset can
    be used to claim provenance or canonical authority.
    """

    text: str
    occurrence: int
    start: int
    end: int


@dataclass(frozen=True, slots=True)
class SourceRole:
    """Attach a non-authoritative grammatical/context role to an anchored phrase."""

    role: str
    anchor: SourceAnchor


@dataclass(frozen=True, slots=True)
class SourceInheritance:
    """Describe a proposed source-context dependency, never a write dependency."""

    role: str
    from_unit: int  # 1-based request-local candidate ordinal, NOT route index.


@dataclass(frozen=True, slots=True)
class FactCandidate:
    """Carry one independently interpretable assertion and its exact source evidence."""

    candidate_id: str
    kind: str
    anchors: tuple[SourceAnchor, ...]
    scopes: tuple[SourceRole, ...]
    inheritance: tuple[SourceInheritance, ...]
    state: str


@dataclass(frozen=True, slots=True)
class FactCandidateProposal:
    """Hold validated request-local candidates without execution or write authority."""

    source: str
    candidates: tuple[FactCandidate, ...]


def _keys(value: Any, expected: set[str], *, label: str) -> Mapping[str, Any]:
    """Require an exact mapping field set so extra authority cannot be smuggled in."""
    if not isinstance(value, Mapping) or set(value) != expected:
        raise RouterError(f"Invalid {label} fields")
    return value


def _bounded_array(value: Any, *, label: str, maximum: int, nonempty: bool) -> list[Any]:
    """Validate list shape and cardinality before following nested provider data."""
    if not isinstance(value, list) or len(value) > maximum or (nonempty and not value):
        raise RouterError(f"Invalid {label} count")
    return value


def _occurrence_offset(source: str, text: str, occurrence: int) -> int:
    """Return the requested exact (potentially overlapping) source occurrence."""
    if (
        not isinstance(text, str)
        or not text.strip()
        or len(text) > MAX_ANCHOR_CHARS
        or not isinstance(occurrence, int)
        or isinstance(occurrence, bool)
        or not 0 <= occurrence < MAX_MESSAGE_CHARS
    ):
        raise RouterError("Invalid source anchor")
    start = -1
    for _ in range(occurrence + 1):
        start = source.find(text, start + 1)
        if start < 0:
            raise RouterError("Source anchor does not match requested occurrence")
    return start


def resolve_source_anchor(source: str, raw: Mapping[str, Any]) -> SourceAnchor:
    """Resolve the provider's text + occurrence through immutable original source."""
    anchor = _keys(raw, {"text", "occurrence"}, label="source anchor")
    text = anchor["text"]
    ordinal = anchor["occurrence"]
    start = _occurrence_offset(source, text, ordinal)
    return SourceAnchor(text=text, occurrence=ordinal, start=start, end=start + len(text))


def _anchored_candidate(source: str, raw: Mapping[str, Any], index: int) -> FactCandidate:
    """Validate one proposed semantic unit without inferring identities or dates."""
    raw = _keys(
        raw,
        {"kind", "anchors", "scoped_source", "inheritance", "state"},
        label="candidate",
    )
    kind, state = raw["kind"], raw["state"]
    if (
        not isinstance(kind, str)
        or not isinstance(state, str)
        or kind not in CANDIDATE_KINDS
        or state not in CANDIDATE_STATES
    ):
        raise RouterError("Unknown fact-candidate kind or state")
    anchors = tuple(
        resolve_source_anchor(source, item)
        for item in _bounded_array(
            raw["anchors"],
            label="source anchors",
            maximum=MAX_ANCHORS_PER_CANDIDATE,
            nonempty=True,
        )
    )
    if len({(a.start, a.end) for a in anchors}) != len(anchors):
        raise RouterError("Duplicated source anchor on one fact candidate")
    scopes: list[SourceRole] = []
    for item in _bounded_array(
        raw["scoped_source"],
        label="scopes",
        maximum=MAX_SCOPES_PER_CANDIDATE,
        nonempty=False,
    ):
        scope = _keys(item, {"role", "anchor"}, label="scope")
        role = scope["role"]
        if not isinstance(role, str) or role not in SOURCE_ROLES:
            raise RouterError("Unknown source context role")
        scopes.append(SourceRole(role, resolve_source_anchor(source, scope["anchor"])))
    inheritance: list[SourceInheritance] = []
    for item in _bounded_array(
        raw["inheritance"],
        label="inheritance",
        maximum=MAX_INHERITANCE_PER_CANDIDATE,
        nonempty=False,
    ):
        dependency = _keys(item, {"role", "from_unit"}, label="inheritance")
        role, predecessor = dependency["role"], dependency["from_unit"]
        if not isinstance(role, str) or role not in SOURCE_ROLES:
            raise RouterError("Unknown inherited context role")
        # This initial v1 representation inherits from earlier units. A later
        # shared lexical scope may itself point backward in the source string.
        if (
            not isinstance(predecessor, int)
            or isinstance(predecessor, bool)
            or not 1 <= predecessor < index
        ):
            raise RouterError("Invalid source dependency: predecessor must be earlier")
        inheritance.append(SourceInheritance(role, predecessor))
    if len({(edge.role, edge.from_unit) for edge in inheritance}) != len(inheritance):
        raise RouterError("Duplicate source-context inheritance")
    return FactCandidate(
        candidate_id=f"candidate-{index}",
        kind=kind,
        anchors=anchors,
        scopes=tuple(scopes),
        inheritance=tuple(inheritance),
        state=state,
    )


def validate_fact_candidate_proposal(
    source: str, payload: Mapping[str, Any]
) -> FactCandidateProposal:
    """Fail closed on ungrounded, ambiguous-shaped, or authority-bearing proposals.

    Args:
        source: The unchanged current user message, not a prior conversation turn.
        payload: Closed semantic-unit JSON generated by an untrusted interpreter.

    Returns:
        Validated request-local candidates with locally resolved source offsets.

    Raises:
        RouterError: When the input, any source occurrence, role, predecessor, or
            proposal field is malformed. Nothing is executed or persisted.
    """
    if not isinstance(source, str) or not source.strip() or len(source) > MAX_MESSAGE_CHARS:
        raise RouterError("Fact source request is invalid or too long")
    envelope = _keys(payload, {"version", "units"}, label="fact candidate proposal")
    if type(envelope["version"]) is not int or envelope["version"] != 1:
        raise RouterError("Unsupported fact candidate proposal version")
    rows = _bounded_array(
        envelope["units"], label="fact candidates", maximum=MAX_CANDIDATES, nonempty=True
    )
    units = tuple(
        _anchored_candidate(source, item, index) for index, item in enumerate(rows, start=1)
    )
    return FactCandidateProposal(source, units)


def fact_candidate_json_schema() -> dict[str, Any]:
    """Build a strict structured-output proposal schema, without Core write fields."""
    anchor = {
        "type": "object",
        "properties": {
            "text": {"type": "string", "maxLength": MAX_ANCHOR_CHARS},
            "occurrence": {"type": "integer", "minimum": 0},
        },
        "required": ["text", "occurrence"],
        "additionalProperties": False,
    }
    scoped = {
        "type": "object",
        "properties": {"role": {"type": "string", "enum": sorted(SOURCE_ROLES)}, "anchor": anchor},
        "required": ["role", "anchor"],
        "additionalProperties": False,
    }
    edge = {
        "type": "object",
        "properties": {
            "role": {"type": "string", "enum": sorted(SOURCE_ROLES)},
            "from_unit": {"type": "integer", "minimum": 1},
        },
        "required": ["role", "from_unit"],
        "additionalProperties": False,
    }
    unit = {
        "type": "object",
        "properties": {
            "kind": {"type": "string", "enum": sorted(CANDIDATE_KINDS)},
            "anchors": {
                "type": "array",
                "items": anchor,
                "minItems": 1,
                "maxItems": MAX_ANCHORS_PER_CANDIDATE,
            },
            "scoped_source": {
                "type": "array",
                "items": scoped,
                "maxItems": MAX_SCOPES_PER_CANDIDATE,
            },
            "inheritance": {
                "type": "array",
                "items": edge,
                "maxItems": MAX_INHERITANCE_PER_CANDIDATE,
            },
            "state": {"type": "string", "enum": sorted(CANDIDATE_STATES)},
        },
        "required": ["kind", "anchors", "scoped_source", "inheritance", "state"],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {
            "version": {"type": "integer", "enum": [1]},
            "units": {"type": "array", "items": unit, "minItems": 1, "maxItems": MAX_CANDIDATES},
        },
        "required": ["version", "units"],
        "additionalProperties": False,
    }


def _inherited_source_anchor(
    proposal: FactCandidateProposal, edge: SourceInheritance
) -> SourceAnchor | None:
    """Follow only same-role original text across source-context inheritance.

    A role transition like report subject -> message object stays in the validated
    candidate plan but is not presented as a verified or direct same-role link.
    """
    prior = proposal.candidates[edge.from_unit - 1]
    for scope in prior.scopes:
        if scope.role == edge.role:
            return scope.anchor
    for earlier in prior.inheritance:
        if earlier.role == edge.role:
            return _inherited_source_anchor(proposal, earlier)
    return None


def as_candidate_preview(proposal: FactCandidateProposal) -> dict[str, Any]:
    """Project source-grounded candidates for the *local-only* existing preview.

    Only the browser's preview subset of roles is shown. This projection does NOT
    enter normal request_detail or indicate a verified Core identity or saved note.
    """
    allowed = {
        "subject",
        "participants",
        "object",
        "location",
        "time",
        "date",
        "predicate",
        "condition",
    }
    candidates = []
    for item in proposal.candidates:
        roles = [
            {
                "role": scope.role,
                "source": scope.anchor.text[:160],
                "occurrence": scope.anchor.occurrence,
                "provenance": "explicit",
                "authority": None,
            }
            for scope in item.scopes
            if scope.role in allowed and len(scope.anchor.text) <= 160
        ]
        for edge in item.inheritance:
            if edge.role not in allowed:
                continue
            original = _inherited_source_anchor(proposal, edge)
            if original is not None and len(original.text) <= 160:
                roles.append(
                    {
                        "role": edge.role,
                        "source": original.text,
                        "occurrence": original.occurrence,
                        "provenance": "inherited",
                        "authority": None,
                    }
                )
        roles = roles[:8]
        first = next((a for a in item.anchors if len(a.text) <= 240), None)
        if first is None or not roles:
            continue
        candidates.append(
            {
                "id": item.candidate_id,
                "source": first.text,
                "occurrence": first.occurrence,
                "roles": roles,
                "dependency_target": None,
            }
        )
    return {"version": 1, "user_message": proposal.source, "candidates": candidates}


class OpenAIFactCandidateRouter:
    """Opt-in, non-executing Router v1 proposal adapter with an injected provider.

    It is intentionally NOT used by ``odyssey_runtime.routing``. A live model
    regression and reviewed adapter to Temporal/Core must precede activation.
    """

    def __init__(self, client: Any) -> None:
        """Accept a caller-supplied SDK-compatible client without credentials or setup."""
        self._client = client
        self.last_usage: Any | None = None
        self.last_error_category: str | None = None

    def propose(self, source: str) -> FactCandidateProposal:
        """Ask Luna once for source-only proposed units, then fail closed locally.

        Args:
            source: Complete unchanged current message. Conversation and personal
                Notes are intentionally not supplied in this v1 interpretation.

        Returns:
            Non-executable, source-anchored candidates, NOT Router v0 routes.

        Raises:
            RouterError: Invalid source, provider error, malformed output or
                failed local source validation. No write or route is attempted.
        """
        if not isinstance(source, str) or not source.strip() or len(source) > MAX_MESSAGE_CHARS:
            raise RouterError("Fact source request is invalid or too long")
        from .router import ROUTER_MODEL, ROUTER_REASONING_EFFORT

        self.last_usage = None
        self.last_error_category = None
        try:
            reply = self._client.responses.create(
                model=ROUTER_MODEL,
                reasoning={"effort": ROUTER_REASONING_EFFORT},
                store=False,
                max_output_tokens=4096,
                input=[
                    {
                        "role": "system",
                        "content": (
                            "Interpret only the original CURRENT request as independently manageable "
                            "semantic fact candidates. Return strict JSON version 1. Each candidate "
                            "uses one or more original exact quoted substrings as anchors, with "
                            "zero-based occurrence indices for duplicate substrings. No rewriting of "
                            "source, invented text or resolved Note identity. Source roles are only "
                            "grammatical/context scopes; they are NOT Core targets, canonical fact "
                            "types, or proof of identity. Preserve shared or omitted source context "
                            "as typed inheritance from EARLIER semantic units, using one-based "
                            "unit indices; inherited source context is NOT a Core write dependency. "
                            "A later source phrase may supply time/date wording to an earlier unit: "
                            "anchor it to its actual position, never convert it to an ISO date. "
                            "Keep polarity, condition, correction, modality, transaction, object, "
                            "and participants independently scoped. Mutual relationships form one "
                            "unit; independent properties and purchase items may form separate units "
                            "while sharing a transaction. Mark ambiguous_identity where a referent "
                            "cannot be safely established from the source. Do not select NoteSchema "
                            "types, create Notes, plan Core writes, bind identities, execute apps, "
                            "normalize dates, or return Markdown."
                        ),
                    },
                    {"role": "user", "content": source},
                ],
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "odyssey_fact_candidate_proposal_v1",
                        "strict": True,
                        "schema": fact_candidate_json_schema(),
                    }
                },
            )
        except Exception as error:
            self.last_error_category = type(error).__name__[:100]
            raise RouterError("Fact candidate provider call failed") from error
        self.last_usage = getattr(reply, "usage", None)
        if getattr(reply, "status", None) != "completed":
            self.last_error_category = "IncompleteProviderResponse"
            raise RouterError("Fact candidate response incomplete")
        try:
            import json

            raw = json.loads(reply.output_text)
        except (TypeError, ValueError, AttributeError) as error:
            self.last_error_category = "MalformedProviderJSON"
            raise RouterError("Fact candidate output is not valid JSON") from error
        try:
            return validate_fact_candidate_proposal(source, raw)
        except (RouterError, TypeError, ValueError) as error:
            self.last_error_category = "InvalidSourceEvidence"
            raise RouterError("Fact candidate output lacks grounded source evidence") from error
