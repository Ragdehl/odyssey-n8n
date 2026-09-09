"""Cost-aware production request planning with a validated Luna first pass.

The first pass deliberately reuses the exact Luna prompt/schema boundary validated in Phase 20.2E.
A locally invalid/incomplete Luna result may fall back once to the established Sol planner. A safe
Luna ESCALATE does not authorize stronger-model guessing: it becomes a normal user clarification.
"""

from __future__ import annotations

from time import perf_counter
from typing import Any

from odyssey_core.experimental_luna_planning import (
    OpenAILunaExperimentalPlanner,
    PlannerEscalation,
)
from odyssey_core.observability import (
    OperationalOutcome,
    ProviderCallEvidence,
    normalize_provider_usage,
)
from odyssey_core.request_planning import (
    OpenAIRequestPlanner,
    PlannerClarification,
    PlannerResult,
    RequestPlan,
    RequestPlanningError,
)

LUNA_FIRST_REASONING_EFFORT = "low"
LUNA_PROVIDER_STAGE = "planner.luna"


class LunaFirstRequestPlanner:
    """Plan with Luna first and use Sol only after a fail-closed Luna result.

    Safe PLAN and CLARIFY results from Luna are returned directly. Luna ESCALATE is converted to the
    existing non-executing clarification result so missing user authority is never guessed by Sol.
    Only a bounded ``RequestPlanningError`` from the validated Luna provider boundary triggers one Sol
    attempt. Generic provider/network exceptions propagate without a second call.
    """

    def __init__(self, luna: Any, sol: Any) -> None:
        self._luna = luna
        self._sol = sol
        self.model = "luna-first"
        self.reasoning_effort = LUNA_FIRST_REASONING_EFFORT
        self.last_usage: dict[str, int] | None = None
        self.last_attempt_count = 0
        self.last_response_id: str | None = None
        self.last_provider_status: str | None = None
        self.last_provider_calls: tuple[ProviderCallEvidence, ...] = ()

    @classmethod
    def from_environment(
        cls, schema: dict[str, Any], current_context: dict[str, str]
    ) -> LunaFirstRequestPlanner:
        """Build the validated Luna first pass and established Sol fallback from environment."""
        return cls(
            OpenAILunaExperimentalPlanner.from_environment(schema, current_context),
            OpenAIRequestPlanner.from_environment(schema, current_context),
        )

    def plan(self, request: str) -> PlannerResult:
        """Return a validated plan/clarification with at most one Luna and one Sol call."""
        if not isinstance(request, str) or not request.strip():
            raise RequestPlanningError("Request text must be non-empty")
        self._reset_evidence()

        luna_started = perf_counter()
        try:
            result = self._luna.plan(request)
        except RequestPlanningError as error:
            self._append_call(
                LUNA_PROVIDER_STAGE,
                self._luna,
                OperationalOutcome.FAILED,
                luna_started,
                error,
            )
            return self._plan_with_sol(request)
        except Exception as error:
            self._append_call(
                LUNA_PROVIDER_STAGE,
                self._luna,
                OperationalOutcome.FAILED,
                luna_started,
                error,
            )
            raise
        self._append_call(
            LUNA_PROVIDER_STAGE, self._luna, OperationalOutcome.COMPLETED, luna_started
        )

        if isinstance(result, PlannerEscalation):
            self._sync_final_metadata(self._luna)
            return PlannerClarification("UNRECOGNIZED_REQUEST")
        if isinstance(result, (RequestPlan, PlannerClarification)):
            self._sync_final_metadata(self._luna)
            return result
        raise TypeError("Luna first pass returned an unsupported planner result")

    def _plan_with_sol(self, request: str) -> PlannerResult:
        """Make the single bounded Sol fallback after a fail-closed Luna result."""
        sol_started = perf_counter()
        try:
            result = self._sol.plan(request)
        except Exception as error:
            self._append_call(
                "planner.sol_fallback",
                self._sol,
                OperationalOutcome.FAILED,
                sol_started,
                error,
            )
            self._sync_final_metadata(self._sol)
            raise
        self._append_call(
            "planner.sol_fallback",
            self._sol,
            OperationalOutcome.COMPLETED,
            sol_started,
        )
        self._sync_final_metadata(self._sol)
        if not isinstance(result, (RequestPlan, PlannerClarification)):
            raise TypeError("Sol fallback returned an unsupported planner result")
        return result

    def _reset_evidence(self) -> None:
        """Clear request-scoped provider metadata before a new logical planning call."""
        self.last_usage = None
        self.last_attempt_count = 0
        self.last_response_id = None
        self.last_provider_status = None
        self.last_provider_calls = ()

    def _append_call(
        self,
        name: str,
        provider: Any,
        outcome: OperationalOutcome,
        started: float,
        error: Exception | None = None,
    ) -> None:
        """Retain bounded per-model evidence without provider payload or prompt content."""
        evidence = ProviderCallEvidence(
            name=name,
            outcome=outcome,
            duration_ms=max(0.0, (perf_counter() - started) * 1000),
            model=getattr(provider, "model", None),
            reasoning_effort=getattr(provider, "reasoning_effort", None),
            usage=normalize_provider_usage(getattr(provider, "last_usage", None)),
            error_category=type(error).__name__ if error is not None else None,
            attempt_count=getattr(provider, "last_attempt_count", 1),
            response_id=getattr(provider, "last_response_id", None),
            provider_status=getattr(provider, "last_provider_status", None),
        )
        self.last_provider_calls = (*self.last_provider_calls, evidence)
        self.last_attempt_count = len(self.last_provider_calls)

    def _sync_final_metadata(self, provider: Any) -> None:
        """Expose final-attempt metadata while per-model usage stays in provider-call evidence."""
        self.last_usage = None
        self.last_response_id = getattr(provider, "last_response_id", None)
        self.last_provider_status = getattr(provider, "last_provider_status", None)
