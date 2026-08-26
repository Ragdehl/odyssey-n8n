"""Offline checks for the focused Phase 16.5A planner-contract benchmark."""

from __future__ import annotations

from benchmarks.phase15_1_schema_write_planning.benchmark import load_cases as load_phase15_cases
from benchmarks.phase16_5_reference_occurrence.run_benchmark import (
    _RecordingResponses,
    load_cases,
    load_suite_cases,
)


def test_reference_occurrence_benchmark_is_small_and_contract_focused() -> None:
    """Keep the live evidence at ten synthetic Sol/low cases with no model fallback."""
    cases = load_cases()
    assert len(cases) == 10
    assert len({case["id"] for case in cases}) == 10
    assert {case["expected"].get("reference_count") for case in cases} >= {0, 1, 2}
    assert len(load_phase15_cases()) == 15
    assert len(load_suite_cases("late_phase15")) == 6
    assert len(load_suite_cases("occurrence")) == 10
    assert len(load_suite_cases("phase15_1")) == 15


def test_recording_responses_clears_previous_response_on_provider_failure() -> None:
    """Prevent usage or raw output from leaking across mixed-success benchmark calls."""

    class Responses:
        def __init__(self) -> None:
            self.calls = 0

        def create(self, **kwargs):
            self.calls += 1
            if self.calls == 2:
                raise RuntimeError("synthetic provider failure")
            return type("Response", (), {"output_text": "{}"})()

    recorder = _RecordingResponses(Responses())
    recorder.create()
    assert recorder.last_response is not None
    try:
        recorder.create()
    except RuntimeError:
        pass
    assert recorder.last_response is None
