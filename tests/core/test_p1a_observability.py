"""Provider-free P1A oracles for planner attempts and interval reconciliation."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from odyssey_core.application import _MeasuredEmbedder
from odyssey_core.cost_aware_planning import LunaFirstRequestPlanner
from odyssey_core.experimental_luna_planning import OpenAILunaExperimentalPlanner
from odyssey_core.observability import (
    OperationalEvidence,
    OperationalOutcome,
    OperationalSpan,
    OperationalStage,
    reconcile_duration,
)
from odyssey_core.request_planning import OpenAIRequestPlanner, PlannerClarification, RequestPlan
from odyssey_runtime.serialization import operational_to_response

ROOT = Path(__file__).resolve().parents[2]
CONTEXT = {"date": "2026-09-22", "time": "20:00", "timezone": "Europe/Paris"}


class ManualClock:
    """Advance only when a fake provider performs a frozen operation."""

    def __init__(self) -> None:
        self.seconds = 0.0

    def __call__(self) -> float:
        """Return the current deterministic monotonic instant."""
        return self.seconds

    def advance_ms(self, duration_ms: float) -> None:
        """Advance one fake external call by an exact interval."""
        self.seconds += duration_ms / 1000


class FakeResponses:
    """Return one frozen Responses envelope per call without network access."""

    def __init__(self, clock: ManualClock, payload: dict, duration_ms: float, usage: dict) -> None:
        self.clock = clock
        self.payload = payload
        self.duration_ms = duration_ms
        self.usage = usage
        self.calls = 0

    def create(self, **kwargs: object) -> SimpleNamespace:
        """Advance fake provider time and expose bounded usage metadata."""
        self.calls += 1
        self.clock.advance_ms(self.duration_ms)
        return SimpleNamespace(
            id=f"resp_{self.calls}",
            status="completed",
            output_text=json.dumps({"result": self.payload}),
            usage=self.usage,
        )


def _selection(query: str) -> dict:
    """Build the frozen supported direct READ planner oracle."""
    return {
        "outcome": "PLAN",
        "actions": [
            {
                "kind": "retrieve",
                "plan": {
                    "entity": None,
                    "query": query,
                    "type": None,
                    "filters": [],
                    "link_scope": None,
                    "self_target": None,
                },
            }
        ],
        "limitations": [],
        "clarification_code": None,
        "presentation_intent": "answer",
    }


def _clarification() -> dict:
    """Build the provider-complete inherited CLARIFY payload."""
    return {
        "outcome": "CLARIFY",
        "actions": None,
        "limitations": None,
        "clarification_code": "UNRECOGNIZED_REQUEST",
        "presentation_intent": None,
    }


def _planner_pair(
    clock: ManualClock, luna_query: str
) -> tuple[LunaFirstRequestPlanner, FakeResponses, FakeResponses]:
    """Assemble production planner classes with fake clocks and frozen provider envelopes."""
    schema = json.loads((ROOT / "config/note-schema.json").read_text(encoding="utf-8"))
    luna_api = FakeResponses(
        clock,
        _selection(luna_query),
        3104,
        {"input_tokens": 11842, "cached_input_tokens": 8200, "output_tokens": 284},
    )
    sol_api = FakeResponses(
        clock,
        _selection("Marta"),
        4191,
        {"input_tokens": 11403, "cached_input_tokens": 0, "output_tokens": 391},
    )
    planner = LunaFirstRequestPlanner(
        OpenAILunaExperimentalPlanner(SimpleNamespace(responses=luna_api), schema, CONTEXT, clock),
        OpenAIRequestPlanner(SimpleNamespace(responses=sol_api), schema, CONTEXT, clock),
        clock,
    )
    return planner, luna_api, sol_api


def test_first_attempt_planner_success_keeps_provider_and_validation_phases() -> None:
    """A valid direct READ uses Luna once and preserves the actual timed call."""
    clock = ManualClock()
    planner, luna_api, sol_api = _planner_pair(clock, "Marta")

    result = planner.plan("¿Dónde trabaja Marta?")

    assert isinstance(result, RequestPlan)
    assert luna_api.calls == 1 and sol_api.calls == 0
    assert len(planner.last_provider_calls) == 1
    attempt = planner.last_provider_calls[0]
    assert (attempt.name, attempt.ordinal, attempt.model, attempt.reasoning_effort) == (
        "planner.luna",
        1,
        "gpt-5.6-luna",
        "low",
    )
    assert attempt.duration_ms == pytest.approx(3104)
    assert attempt.usage == {
        "input_tokens": 11842,
        "cached_input_tokens": 8200,
        "output_tokens": 284,
    }
    assert [span.name for span in attempt.substeps] == [
        "input_build",
        "provider",
        "parse",
        "validate",
    ]
    assert attempt.substeps[1].duration_ms == pytest.approx(3104)
    assert attempt.parse_status == "succeeded"
    assert attempt.result_kind == "plan"
    assert attempt.input_sizes and attempt.input_sizes["user_request_bytes"] > 0
    assert not any("Marta" in str(value) for value in attempt.input_sizes.values())


def test_first_attempt_clarification_skips_sol_with_provider_complete_payload() -> None:
    """A valid Luna CLARIFY retains its own attempt evidence without fallback."""
    clock = ManualClock()
    schema = json.loads((ROOT / "config/note-schema.json").read_text(encoding="utf-8"))
    luna_api = FakeResponses(
        clock,
        _clarification(),
        1200,
        {"input_tokens": 11800, "cached_input_tokens": 0, "output_tokens": 48},
    )
    sol_api = FakeResponses(
        clock,
        _selection("Marta"),
        4200,
        {"input_tokens": 10800, "cached_input_tokens": 0, "output_tokens": 100},
    )
    planner = LunaFirstRequestPlanner(
        OpenAILunaExperimentalPlanner(SimpleNamespace(responses=luna_api), schema, CONTEXT, clock),
        OpenAIRequestPlanner(SimpleNamespace(responses=sol_api), schema, CONTEXT, clock),
        clock,
    )

    result = planner.plan("...???...")

    assert result == PlannerClarification("UNRECOGNIZED_REQUEST")
    assert luna_api.calls == 1 and sol_api.calls == 0
    assert len(planner.last_provider_calls) == 1
    assert planner.last_provider_calls[0].result_kind == "clarify"


def test_luna_validation_failure_then_sol_success_preserves_both_attempts() -> None:
    """A real local validation error keeps its safe code and independent fallback cost evidence."""
    clock = ManualClock()
    planner, luna_api, sol_api = _planner_pair(clock, "")

    result = planner.plan("¿Dónde trabaja Marta?")

    assert isinstance(result, RequestPlan)
    assert luna_api.calls == sol_api.calls == 1
    first, second = planner.last_provider_calls
    assert [(call.name, call.ordinal, call.model) for call in (first, second)] == [
        ("planner.luna", 1, "gpt-5.6-luna"),
        ("planner.sol_fallback", 2, "gpt-5.6-sol"),
    ]
    assert (first.duration_ms, second.duration_ms) == pytest.approx((3104, 4191))
    assert first.start_offset_ms == pytest.approx(0)
    assert second.start_offset_ms == pytest.approx(3104)
    assert first.outcome is OperationalOutcome.FAILED
    assert first.provider_status == "completed"
    assert first.substeps[1].outcome is OperationalOutcome.COMPLETED
    assert first.parse_status == "succeeded"
    assert (first.validation_stage, first.validation_code) == ("SELECTION", "EMPTY_QUERY")
    assert first.error_category == "LocalPlannerValidationError"
    assert first.usage and first.usage["input_tokens"] == 11842
    assert second.outcome is OperationalOutcome.COMPLETED
    assert second.usage and second.usage["input_tokens"] == 11403
    assert [span.name for span in second.substeps] == [
        "input_build",
        "provider",
        "parse",
        "validate",
    ]
    assert [span.name for span in planner.last_spans] == ["fallback_decision"]
    assert clock.seconds * 1000 == pytest.approx(7295)


def test_interval_union_reports_residual_and_overlap_without_false_precision() -> None:
    """Sequential and overlapping child work reconcile against one measured parent wall."""
    sequential = reconcile_duration(9000, ((0, 3100), (3200, 5530)))
    assert sequential is not None
    assert sequential.attributed_ms == pytest.approx(8630)
    assert sequential.unattributed_ms == pytest.approx(370)
    assert sequential.coverage_pct == pytest.approx(95.8888888889)
    overlap = reconcile_duration(1000, ((0, 600), (400, 500)))
    assert overlap is not None
    assert (overlap.attributed_ms, overlap.unattributed_ms, overlap.overlapping_ms) == (
        900,
        100,
        200,
    )
    assert reconcile_duration(1000, ((900, 200),)) is None
    assert reconcile_duration(1000, ((-1, 2),)) is None
    assert reconcile_duration(float("nan"), ()) is None


def test_serialized_coverage_exposes_unattributed_time() -> None:
    """One bounded JSON hierarchy carries coverage without relying on a UI formatter."""
    evidence = OperationalEvidence(
        total_duration_ms=1000,
        stages=(
            OperationalStage(
                "planner",
                OperationalOutcome.COMPLETED,
                900,
                start_offset_ms=20,
                substeps=(
                    OperationalSpan("input_build", OperationalOutcome.COMPLETED, 0, 50),
                    OperationalSpan("provider", OperationalOutcome.COMPLETED, 60, 800),
                ),
            ),
        ),
    )
    operational = operational_to_response(evidence)
    assert operational["coverage"] == {
        "attributed_ms": 900,
        "unattributed_ms": 100,
        "coverage_pct": 90,
        "overlapping_ms": 0,
    }
    assert operational["stages"][0]["coverage"]["unattributed_ms"] == 50


def test_repeated_embedding_invocations_keep_independent_ordinals() -> None:
    """Three scaling I/O operations are visible separately within one action."""
    from odyssey_core.observability import SpanRecorder

    clock = ManualClock()

    class FakeEmbedder:
        """Charge one deterministic duration for each local embedding operation."""

        def embed_queries(self, texts: list[str]) -> list[list[float]]:
            """Return one fake vector after advancing the injected clock."""
            clock.advance_ms(7)
            return [[1.0] for _ in texts]

    recorder = SpanRecorder(clock(), clock)
    measured = _MeasuredEmbedder(FakeEmbedder(), recorder)
    for _ in range(3):
        measured.embed_queries(["synthetic"])
    assert [span.name for span in recorder.spans] == [
        "embedding.query[0]",
        "embedding.query[1]",
        "embedding.query[2]",
    ]
    assert [span.duration_ms for span in recorder.spans] == pytest.approx([7, 7, 7])
