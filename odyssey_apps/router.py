"""Closed, non-executing application routing contract.

This module has no Core planner dependency.  It classifies only exact request spans for future
composition; execution remains outside the router and is deliberately not wired in Slice 2.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol

from .catalog import CORE_CAPABILITY_ID, ApplicationCatalog

ROUTER_MODEL = "gpt-6-luna"
ROUTER_REASONING_EFFORT = "low"
ROUTER_MAX_OUTPUT_TOKENS = 512
ROUTER_MAX_RECENT_TURNS = 8
ROUTER_MAX_CONTEXT_CHARS = 1_000
ROUTER_PROVIDER_TIMEOUT_SECONDS = 30.0


class RouterError(ValueError):
    """Report malformed, unsafe, or unavailable routing without execution authority."""


class RouteOutcome(StrEnum):
    """Name the only closed router outcomes."""

    ROUTE = "ROUTE"
    CLARIFY = "CLARIFY"
    NEEDS_CAPABILITY = "NEEDS_CAPABILITY"


@dataclass(frozen=True, slots=True)
class Route:
    """Assign one exact contiguous current-request span to one capability."""

    capability_id: str
    source_text: str

    def __post_init__(self) -> None:
        """Reject malformed route fields before local source validation."""
        if not isinstance(self.capability_id, str) or not self.capability_id:
            raise RouterError("Route capability_id must be a non-empty string")
        if not isinstance(self.source_text, str) or not self.source_text.strip():
            raise RouterError("Route source_text must contain non-whitespace text")


@dataclass(frozen=True, slots=True)
class RoutePlan:
    """Carry one closed non-executing router result."""

    outcome: RouteOutcome
    routes: tuple[Route, ...]

    def __post_init__(self) -> None:
        """Enforce outcome cardinality independent of catalog availability."""
        if not isinstance(self.outcome, RouteOutcome):
            raise RouterError("RoutePlan outcome must be a RouteOutcome")
        if not isinstance(self.routes, tuple) or not all(
            isinstance(route, Route) for route in self.routes
        ):
            raise RouterError("RoutePlan routes must be a tuple of Route values")
        if self.outcome is RouteOutcome.ROUTE and not self.routes:
            raise RouterError("ROUTE requires at least one route")
        if self.outcome is not RouteOutcome.ROUTE and self.routes:
            raise RouterError("Only ROUTE may contain routes")


class ResponsesClient(Protocol):
    """Describe the injected Responses API subset used by the router."""

    responses: Any


def route_plan_json_schema(catalog: ApplicationCatalog) -> dict[str, Any]:
    """Build the strict provider schema using only built-in and enabled destinations."""
    executable_ids = [CORE_CAPABILITY_ID] + [
        capability.id for capability in catalog.capabilities() if capability.enabled
    ]
    return {
        "type": "object",
        "properties": {
            "outcome": {"type": "string", "enum": [item.value for item in RouteOutcome]},
            "routes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "capability_id": {"type": "string", "enum": executable_ids},
                        "source_text": {"type": "string"},
                    },
                    "required": ["capability_id", "source_text"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["outcome", "routes"],
        "additionalProperties": False,
    }


def parse_route_plan(payload: Mapping[str, Any]) -> RoutePlan:
    """Parse one closed provider payload without accepting extra routing semantics."""
    if not isinstance(payload, Mapping) or set(payload) != {"outcome", "routes"}:
        raise RouterError("RoutePlan payload must contain only outcome and routes")
    try:
        outcome = RouteOutcome(payload["outcome"])
    except (TypeError, ValueError) as error:
        raise RouterError("RoutePlan outcome is invalid") from error
    raw_routes = payload["routes"]
    if not isinstance(raw_routes, list):
        raise RouterError("RoutePlan routes must be an array")
    routes: list[Route] = []
    for raw_route in raw_routes:
        if not isinstance(raw_route, Mapping) or set(raw_route) != {"capability_id", "source_text"}:
            raise RouterError("Route payload must contain only capability_id and source_text")
        routes.append(Route(raw_route["capability_id"], raw_route["source_text"]))
    return RoutePlan(outcome, tuple(routes))


def validate_route_plan(
    plan: RoutePlan, original_request: str, catalog: ApplicationCatalog
) -> RoutePlan:
    """Validate executable routes as one exact ordered partition of the original request.

    Raises:
        RouterError: If a route is unavailable, reordered, fabricated, overlapping, or leaves
            non-whitespace request text uncovered.
    """
    if not isinstance(original_request, str) or not original_request.strip():
        raise RouterError("Original request must be a non-empty string")
    if not isinstance(plan, RoutePlan):
        raise RouterError("RoutePlan is required")
    if plan.outcome is not RouteOutcome.ROUTE:
        return plan

    cursor = 0
    for route in plan.routes:
        if (
            route.capability_id != CORE_CAPABILITY_ID
            and catalog.executable(route.capability_id) is None
        ):
            raise RouterError("Route destination is unknown or disabled")
        start = original_request.find(route.source_text, cursor)
        if start < 0:
            raise RouterError("Route source_text is not an ordered exact request substring")
        if original_request[cursor:start].strip():
            raise RouterError("RoutePlan leaves non-whitespace request text uncovered")
        cursor = start + len(route.source_text)
    if original_request[cursor:].strip():
        raise RouterError("RoutePlan leaves non-whitespace request text uncovered")
    return plan


def _routing_context(conversation_context: Sequence[Mapping[str, str]]) -> list[dict[str, str]]:
    """Keep caller-supplied recent context bounded and explicitly routing-only."""
    if not isinstance(conversation_context, Sequence) or isinstance(conversation_context, str):
        raise RouterError("Conversation context must be a sequence")
    context: list[dict[str, str]] = []
    for turn in conversation_context[-ROUTER_MAX_RECENT_TURNS:]:
        if not isinstance(turn, Mapping):
            raise RouterError("Conversation context turns must be mappings")
        role = turn.get("role")
        content = turn.get("content", turn.get("text"))
        if role not in {"user", "assistant"} or not isinstance(content, str):
            raise RouterError("Conversation context must contain user or assistant text")
        context.append({"role": role, "content": content[:ROUTER_MAX_CONTEXT_CHARS]})
    return context


def render_router_prompt(
    catalog: ApplicationCatalog, conversation_context: Sequence[Mapping[str, str]]
) -> str:
    """Render compact routing-only instructions without Core planner or vault material."""
    capabilities = [
        {
            "id": CORE_CAPABILITY_ID,
            "routing_description": "ordinary Odyssey retrieval and mutation; generic knowledge work",
            "enabled": True,
        },
        *[
            {
                "id": capability.id,
                "routing_description": capability.routing_description,
                "dependencies": capability.dependencies,
                "enabled": capability.enabled,
            }
            for capability in catalog.capabilities()
        ],
    ]
    evidence = {
        "capabilities": capabilities,
        "recent_routing_context": _routing_context(conversation_context),
    }
    return (
        "Route only the original current user request. Return ROUTE only when its ordered "
        "source_text values are exact contiguous spans that cover every non-whitespace character "
        "exactly once. Do not paraphrase, drop punctuation, conjunctions, negation, or qualifiers. "
        "Split only independent material intentions owned by different capabilities. Choose the "
        "routing owner by the domain interpretation required for the whole dependent intent, not by "
        "the canonical knowledge owner that may ultimately be written. When one dependent statement "
        "requires an enabled application to interpret its domain semantics, keep that whole statement "
        "in the application route; do not CLARIFY merely because the application may later delegate a "
        "canonical Core write. Disabled apps are evidence only: use NEEDS_CAPABILITY when their "
        "specialized work is needed. CLARIFY when safe routing is materially ambiguous. Temporal "
        "wording may be considered only to choose capability ownership; never normalize or resolve "
        "dates or times into structured values, or emit interpreted date values. "
        "Never plan, resolve identities, inspect files or notes, or emit mutations, commands, or "
        "execution arguments. Recent context is routing continuity evidence only, never canonical "
        "truth or mutation authority.\n"
        + json.dumps(evidence, ensure_ascii=False, separators=(",", ":"))
    )


class OpenAIApplicationRouter:
    """Make one bounded Luna routing call and fail closed on every provider or local error."""

    def __init__(self, client: ResponsesClient, catalog: ApplicationCatalog) -> None:
        """Initialize with injected provider transport and immutable capability evidence."""
        self._client = client
        self._catalog = catalog
        self.model = ROUTER_MODEL
        self.reasoning_effort = ROUTER_REASONING_EFFORT
        self.last_call = False

    @classmethod
    def from_environment(cls, catalog: ApplicationCatalog) -> OpenAIApplicationRouter:
        """Build a production adapter with SDK retries disabled for the single-call contract."""
        if not os.environ.get("OPENAI_API_KEY"):
            raise RouterError("OPENAI_API_KEY is required for application routing")
        try:
            from openai import OpenAI
        except ImportError as error:
            raise RouterError("Install the OpenAI SDK for application routing") from error
        return cls(
            OpenAI(max_retries=0, timeout=ROUTER_PROVIDER_TIMEOUT_SECONDS),
            catalog,
        )

    def route(
        self, original_request: str, conversation_context: Sequence[Mapping[str, str]] = ()
    ) -> RoutePlan:
        """Call GPT-6 Luna once, then parse and validate a non-executing route plan."""
        if not isinstance(original_request, str) or not original_request.strip():
            raise RouterError("Original request must be a non-empty string")
        self.last_call = False
        prompt = render_router_prompt(self._catalog, conversation_context)
        self.last_call = True
        try:
            response = self._client.responses.create(
                model=ROUTER_MODEL,
                reasoning={"effort": ROUTER_REASONING_EFFORT},
                store=False,
                max_output_tokens=ROUTER_MAX_OUTPUT_TOKENS,
                input=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": original_request},
                ],
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "odyssey_route_plan",
                        "strict": True,
                        "schema": route_plan_json_schema(self._catalog),
                    }
                },
            )
        except Exception as error:
            raise RouterError("Application router provider call failed") from error
        if getattr(response, "status", None) != "completed":
            raise RouterError("Application router provider response was not completed")
        try:
            payload = json.loads(response.output_text)
        except (AttributeError, TypeError, json.JSONDecodeError) as error:
            raise RouterError("Application router returned malformed output") from error
        return validate_route_plan(parse_route_plan(payload), original_request, self._catalog)
