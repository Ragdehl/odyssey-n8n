"""Fail-closed interpretation of user requests into safe Odyssey RequestPlans."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from odyssey_core.context import ContextFilter, validate_context_filters
from odyssey_core.planner_capabilities import LIMITATIONS, build_planner_capabilities

PLANNER_MODEL = "gpt-5.6-sol"
PLANNER_REASONING_EFFORT = "low"
_CURRENT_CONTEXT_KEYS = frozenset({"date", "time", "timezone"})
_CAPABILITY_PLACEHOLDER = "{{RETRIEVAL_CAPABILITIES}}"
_PROMPT_TEMPLATE = """You convert one user request into one strict JSON RequestPlan. Use the supplied current date, time, and timezone.

Hard filters can permanently remove valid notes: apply a deterministic restriction only when the request maps explicitly and safely to this capability contract. Otherwise preserve the meaning in `query`. Multiple RetrieveActions are only for genuinely independent candidate-set branches; ordinary semantic OR stays one query.

Use a canonical type restriction only when the request explicitly and safely identifies that canonical class; never infer a canonical type from semantic facets. CreateNoteAction is content-only user memory intent. Do not perform SQL, retrieval, persistence, ID generation, relationship inference, or note decomposition. Use limitation codes only with their defined meanings. Return strict structured JSON.

Planner retrieval capabilities (derived dynamically from the canonical schema):

{{RETRIEVAL_CAPABILITIES}}"""


class RequestPlanningError(ValueError):
    """Indicate malformed, unsupported, or unsafe RequestPlan model output."""


class ResponsesClient(Protocol):
    """Describe the injected subset of the OpenAI Responses client used by the planner."""

    responses: Any


@dataclass(frozen=True, slots=True)
class RetrievalPlan:
    """Represent one validated Phase 13-compatible retrieval request."""

    query: str
    type: str | None
    filters: tuple[ContextFilter, ...]


@dataclass(frozen=True, slots=True)
class RetrieveAction:
    """Represent one ordered, non-executing retrieval action."""

    plan: RetrievalPlan
    kind: str = "retrieve"


@dataclass(frozen=True, slots=True)
class CreateNoteAction:
    """Represent content-only memory intent without persistence details."""

    content: str
    kind: str = "create_note"


RequestAction = RetrieveAction | CreateNoteAction


@dataclass(frozen=True, slots=True)
class RequestPlan:
    """Contain an ordered, validated interpretation of one user request."""

    actions: tuple[RequestAction, ...]
    limitations: tuple[str, ...]


def render_request_planner_prompt(
    schema: Mapping[str, Any], current_context: Mapping[str, str]
) -> str:
    """Render the production planner prompt from current schema and caller context.

    Args:
        schema: Parsed canonical Odyssey schema.
        current_context: Current date, time, and timezone supplied at request time.

    Returns:
        A compact prompt containing dynamic planner capabilities.

    Raises:
        RequestPlanningError: If the runtime context is incomplete or malformed.
    """
    _validate_current_context(current_context)
    if _PROMPT_TEMPLATE.count(_CAPABILITY_PLACEHOLDER) != 1:
        raise RuntimeError("Request planner prompt template is invalid")
    capabilities = build_planner_capabilities(schema, current_context=current_context)
    return _PROMPT_TEMPLATE.replace(
        _CAPABILITY_PLACEHOLDER,
        json.dumps(capabilities, ensure_ascii=False, separators=(",", ":")),
    )


def request_plan_json_schema(schema: Mapping[str, Any]) -> dict[str, Any]:
    """Build the strict Structured Outputs schema for the current canonical schema.

    Args:
        schema: Parsed canonical Odyssey schema.

    Returns:
        Closed JSON Schema accepted by the Responses API for a RequestPlan.

    Raises:
        RequestPlanningError: If canonical capabilities cannot form a usable contract.
    """
    capabilities = build_planner_capabilities(schema)
    filters = capabilities["filters"]
    alternatives = []
    for field, definition in filters.items():
        scalar: dict[str, Any] = {
            "type": "integer" if definition["value_type"] == "integer" else "string"
        }
        if definition["controlled_values"]:
            scalar["enum"] = definition["controlled_values"]
        for operator in definition["operators"]:
            alternatives.append(
                {
                    "type": "object",
                    "properties": {
                        "field": {"type": "string", "enum": [field]},
                        "op": {"type": "string", "enum": [operator]},
                        "value": {"type": "array", "items": scalar} if operator == "in" else scalar,
                    },
                    "required": ["field", "op", "value"],
                    "additionalProperties": False,
                }
            )
    if not alternatives:
        raise RequestPlanningError("Canonical schema exposes no planner filters")
    retrieve = {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "type": {
                "anyOf": [{"type": "null"}, {"type": "string", "enum": list(capabilities["types"])}]
            },
            "filters": {"type": "array", "items": {"anyOf": alternatives}},
        },
        "required": ["query", "type", "filters"],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {
            "actions": {
                "type": "array",
                "items": {
                    "anyOf": [
                        {
                            "type": "object",
                            "properties": {"kind": {"const": "retrieve"}, "plan": retrieve},
                            "required": ["kind", "plan"],
                            "additionalProperties": False,
                        },
                        {
                            "type": "object",
                            "properties": {
                                "kind": {"const": "create_note"},
                                "content": {"type": "string"},
                            },
                            "required": ["kind", "content"],
                            "additionalProperties": False,
                        },
                    ]
                },
            },
            "limitations": {
                "type": "array",
                "items": {"type": "string", "enum": list(LIMITATIONS)},
            },
        },
        "required": ["actions", "limitations"],
        "additionalProperties": False,
    }


def validate_request_plan(payload: Any, schema: Mapping[str, Any]) -> RequestPlan:
    """Validate untrusted model output and return an immutable executable-safe plan.

    Args:
        payload: JSON-decoded model output.
        schema: Parsed canonical Odyssey schema.

    Returns:
        A locally validated RequestPlan, without performing any action.

    Raises:
        RequestPlanningError: If output is malformed, empty, or violates deterministic retrieval rules.
    """
    capabilities = build_planner_capabilities(schema)
    if not isinstance(payload, dict) or set(payload) != {"actions", "limitations"}:
        raise RequestPlanningError("RequestPlan must contain exactly actions and limitations")
    raw_actions, limitations = payload["actions"], payload["limitations"]
    if not isinstance(raw_actions, list) or not raw_actions:
        raise RequestPlanningError("RequestPlan actions must be a non-empty list")
    if (
        not isinstance(limitations, list)
        or len(limitations) != len(set(limitations))
        or not all(isinstance(item, str) and item in LIMITATIONS for item in limitations)
    ):
        raise RequestPlanningError("RequestPlan limitations are invalid")
    actions = tuple(_validate_action(action, schema, capabilities) for action in raw_actions)
    return RequestPlan(actions=actions, limitations=tuple(limitations))


class OpenAIRequestPlanner:
    """Plan requests with Sol/low while leaving all execution outside this boundary."""

    def __init__(
        self, client: ResponsesClient, schema: Mapping[str, Any], current_context: Mapping[str, str]
    ) -> None:
        """Initialize a planner with an injected client and runtime schema/context.

        Args:
            client: OpenAI-compatible Responses client supplied by composition code.
            schema: Current canonical Odyssey schema.
            current_context: Current date, time, and timezone for lifecycle interpretation.

        Raises:
            RequestPlanningError: If current context is malformed.
        """
        _validate_current_context(current_context)
        self._client = client
        self._schema = schema
        self._current_context = dict(current_context)

    @classmethod
    def from_environment(
        cls, schema: Mapping[str, Any], current_context: Mapping[str, str]
    ) -> OpenAIRequestPlanner:
        """Create a production planner using the environment-provided OpenAI API key.

        Args:
            schema: Current canonical Odyssey schema.
            current_context: Current date, time, and timezone for lifecycle interpretation.

        Returns:
            A planner backed by the OpenAI Responses API.

        Raises:
            RequestPlanningError: If the API key or OpenAI SDK is unavailable.
        """
        if not os.environ.get("OPENAI_API_KEY"):
            raise RequestPlanningError("OPENAI_API_KEY is required for request planning")
        try:
            from openai import OpenAI
        except ImportError as error:
            raise RequestPlanningError("Install the OpenAI SDK for request planning") from error
        return cls(OpenAI(), schema, current_context)

    def plan(self, request: str) -> RequestPlan:
        """Interpret one non-empty user request and fail closed on invalid model output.

        Args:
            request: User request to interpret.

        Returns:
            A validated RequestPlan that has not been executed.

        Raises:
            RequestPlanningError: If the request, provider response, JSON, or plan is invalid.
        """
        if not isinstance(request, str) or not request.strip():
            raise RequestPlanningError("Request text must be non-empty")
        try:
            response = self._client.responses.create(
                model=PLANNER_MODEL,
                reasoning={"effort": PLANNER_REASONING_EFFORT},
                store=False,
                input=[
                    {
                        "role": "system",
                        "content": render_request_planner_prompt(
                            self._schema, self._current_context
                        ),
                    },
                    {"role": "user", "content": request},
                ],
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "odyssey_request_plan",
                        "strict": True,
                        "schema": request_plan_json_schema(self._schema),
                    }
                },
            )
        except Exception as error:
            raise RequestPlanningError("Request planner provider call failed") from error
        try:
            payload = json.loads(response.output_text)
        except (AttributeError, TypeError, json.JSONDecodeError) as error:
            raise RequestPlanningError("Request planner returned malformed JSON") from error
        return validate_request_plan(payload, self._schema)


def _validate_current_context(current_context: Mapping[str, str]) -> None:
    """Reject incomplete dynamic date/time context before it reaches a planner prompt."""
    if set(current_context) != _CURRENT_CONTEXT_KEYS or not all(
        isinstance(value, str) and value.strip() for value in current_context.values()
    ):
        raise RequestPlanningError(
            "Current context must contain non-empty date, time, and timezone"
        )


def _validate_action(
    action: Any, schema: Mapping[str, Any], capabilities: Mapping[str, Any]
) -> RequestAction:
    """Validate one discriminated action without executing retrieval or persistence."""
    if not isinstance(action, dict):
        raise RequestPlanningError("RequestPlan action must be an object")
    if action.get("kind") == "create_note":
        content = action.get("content")
        if (
            set(action) != {"kind", "content"}
            or not isinstance(content, str)
            or not content.strip()
        ):
            raise RequestPlanningError("CreateNoteAction must contain only non-empty content")
        return CreateNoteAction(content=content.strip())
    if action.get("kind") != "retrieve" or set(action) != {"kind", "plan"}:
        raise RequestPlanningError("RequestPlan action kind is invalid")
    raw_plan = action["plan"]
    if not isinstance(raw_plan, dict) or set(raw_plan) != {"query", "type", "filters"}:
        raise RequestPlanningError("RetrieveAction must contain exactly one retrieval plan")
    query, note_type, raw_filters = raw_plan["query"], raw_plan["type"], raw_plan["filters"]
    if not isinstance(query, str) or not query.strip():
        raise RequestPlanningError("RetrievalPlan query must be non-empty")
    if note_type is not None and note_type not in capabilities["types"]:
        raise RequestPlanningError("RetrievalPlan type is invalid")
    if not isinstance(raw_filters, list):
        raise RequestPlanningError("RetrievalPlan filters must be a list")
    _validate_planner_filters(raw_filters, note_type, capabilities)
    try:
        validate_context_filters(dict(schema), raw_filters, note_type=note_type)
    except ValueError as error:
        raise RequestPlanningError("RetrievalPlan filters are invalid") from error
    return RetrieveAction(
        RetrievalPlan(
            query=query.strip(),
            type=note_type,
            filters=tuple(
                ContextFilter(item["field"], item["op"], item["value"]) for item in raw_filters
            ),
        )
    )


def _validate_planner_filters(
    filters: Sequence[Any], note_type: str | None, capabilities: Mapping[str, Any]
) -> None:
    """Restrict model filters to dynamic planner capabilities and compatible type scopes."""
    known = capabilities["filters"]
    candidates = set(capabilities["types"])
    if note_type is not None:
        candidates &= {note_type}
    for item in filters:
        if not isinstance(item, dict) or set(item) != {"field", "op", "value"}:
            raise RequestPlanningError("Each retrieval filter must contain field, op, and value")
        definition = known.get(item["field"])
        if definition is None or item["op"] not in definition["operators"]:
            raise RequestPlanningError("Retrieval filter field or operator is invalid")
        if item["op"] == "in":
            if not isinstance(item["value"], list) or not item["value"]:
                raise RequestPlanningError("The in operator requires a non-empty value list")
        elif isinstance(item["value"], list):
            raise RequestPlanningError("Only the in operator accepts a value list")
        if item["field"] == "type":
            values = item["value"] if isinstance(item["value"], list) else [item["value"]]
            candidates &= set(values)
    if not candidates:
        raise RequestPlanningError("RetrievalPlan type restrictions are contradictory")
    for item in filters:
        if item["field"] != "type" and not candidates <= set(known[item["field"]]["applies_to"]):
            raise RequestPlanningError("Retrieval filter is incompatible with its candidate types")
