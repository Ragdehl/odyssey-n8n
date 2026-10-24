"""No-private-content runtime projection for WorkSession nested timing spans."""

from __future__ import annotations

from time import perf_counter

from odyssey_core.observability import (
    OperationalEvidence,
    OperationalOutcome,
    OperationalSpan,
    OperationalStage,
    SpanRecorder,
)
from odyssey_runtime.composition import _work_session_resolution_substeps
from odyssey_runtime.serialization import operational_to_response


def test_work_session_resolution_substeps_are_bounded_and_private():
    assert _work_session_resolution_substeps(None) == ()
    recorder = SpanRecorder(perf_counter(), perf_counter)
    assert _work_session_resolution_substeps(recorder) == ()
    recorder.spans = (
        OperationalSpan(
            "contextual_provider", OperationalOutcome.FAILED, 1.0, 181.5, "RuntimeError"
        ),
        OperationalSpan("exact_lookup", OperationalOutcome.COMPLETED, 0.0, 0.1),
        OperationalSpan("private-message", OperationalOutcome.COMPLETED, 1.0, 999.0),
        OperationalSpan("candidate_validation", OperationalOutcome.COMPLETED, 0.2, 0.2),
    )
    projected = _work_session_resolution_substeps(recorder)
    assert [s.name for s in projected] == [
        "contextual_provider",
        "exact_lookup",
        "candidate_validation",
    ]
    assert [s.duration_ms for s in projected] == [181.5, 0.1, 0.2]
    assert projected[0].outcome is OperationalOutcome.FAILED
    assert projected[0].error_category == "RuntimeError"
    assert all("private" not in s.name for s in projected)
    assert all(s.start_offset_ms >= 0 for s in projected)


def test_work_session_substeps_do_not_double_count_total_or_expose_candidates():
    recorder = SpanRecorder(perf_counter(), perf_counter)
    recorder.spans = (
        OperationalSpan("exact_lookup", OperationalOutcome.COMPLETED, 0.0, 1.0),
        OperationalSpan("semantic_search", OperationalOutcome.COMPLETED, 1.0, 2.0),
        OperationalSpan("contextual_provider", OperationalOutcome.COMPLETED, 3.0, 187.0),
    )
    nested = _work_session_resolution_substeps(recorder)
    evidence = OperationalEvidence(
        200.0,
        (
            OperationalStage(
                "tasks.work_session_resolution",
                OperationalOutcome.COMPLETED,
                200.0,
                substeps=nested,
            ),
        ),
    )
    projected = operational_to_response(evidence)
    assert projected["total_duration_ms"] == 200.0
    assert len(projected["stages"]) == 1
    stage = projected["stages"][0]
    assert stage["duration_ms"] == 200.0
    assert [span["name"] for span in stage["substeps"]] == [
        "exact_lookup",
        "semantic_search",
        "contextual_provider",
    ]
    assert stage["coverage"]["attributed_ms"] == 190.0
    assert stage["coverage"]["unattributed_ms"] == 10.0
    assert "candidates" not in str(stage) and "reference" not in str(stage)
