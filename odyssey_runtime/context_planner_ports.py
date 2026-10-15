"""E2 context-aware construction of the ONE ordinary Core Planner.

`Protocol` declares the structural port; the concrete adapter uses the
existing GPT-5.6 Luna planner and does not make identity/write decisions.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol, runtime_checkable

from odyssey_core.execution_context import ExecutionContext
from odyssey_core.experimental_luna_planning import OpenAILunaExperimentalPlanner


@runtime_checkable
class ContextAwareCorePlannerFactory(Protocol):
    """A Core planner factory consuming the validated, read-only E2 context."""

    def create_for_context(self, context: ExecutionContext) -> object:
        """Construct the ordinary Core planner, not an alternate Writer."""
        ...


class OpenAILunaContextPlannerFactory:
    """Composition adapter; preserves current Luna model/prompt and schemas.

    Existing roles/domains are supplied to the same planner constructor as the
    former two-argument lambda. Note candidates remain contextual hints only.
    """

    def __init__(
        self,
        *,
        client: object,
        schema: Mapping[str, Any],
        clock: Mapping[str, str],
    ) -> None:
        self._client = client
        self._schema = schema
        self._clock = clock

    def create_for_context(self, context: ExecutionContext) -> OpenAILunaExperimentalPlanner:
        if not isinstance(context, ExecutionContext) or context.candidates is None:
            raise ValueError("Luna context factory requires a validated Core candidate context")
        return OpenAILunaExperimentalPlanner(
            self._client,
            self._schema,
            self._clock,
            candidate_context=context.candidates,
            domain_interpretation=context.domains[0] if context.domains else None,
        )
