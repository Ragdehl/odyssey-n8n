"""Serialize typed Odyssey application evidence for external callers."""

from __future__ import annotations

from typing import Any

from odyssey_core.application import (
    ActionResult,
    ActionStatus,
    ApplicationResult,
    ApplicationStatus,
    UnitResult,
)
from odyssey_core.observability import (
    OperationalEvidence,
    OperationalSpan,
    ProviderCallEvidence,
    reconcile_duration,
)
from odyssey_core.semantic_sets import IdentitySetMember, SemanticSetOutcome


def _span_response(span: OperationalSpan) -> dict[str, Any]:
    """Serialize one content-free timed child interval."""
    return {
        "name": span.name,
        "outcome": span.outcome.value,
        "start_offset_ms": span.start_offset_ms,
        "duration_ms": span.duration_ms,
        "error_category": span.error_category,
    }


def _coverage_response(
    total: float | None, intervals: list[tuple[float, float]]
) -> dict[str, float] | None:
    """Return a safe interval-union summary or explicit unavailable timing."""
    if total is None:
        return None
    coverage = reconcile_duration(total, tuple(intervals))
    return (
        None
        if coverage is None
        else {
            "attributed_ms": coverage.attributed_ms,
            "unattributed_ms": coverage.unattributed_ms,
            "coverage_pct": coverage.coverage_pct,
            "overlapping_ms": coverage.overlapping_ms,
        }
    )


def _call_response(call: ProviderCallEvidence) -> dict[str, Any]:
    """Keep every provider attempt and its timed phases in the existing call record."""
    result: dict[str, Any] = {
        "name": call.name,
        "outcome": call.outcome.value,
        "duration_ms": call.duration_ms,
        "model": call.model,
        "reasoning_effort": call.reasoning_effort,
        "usage": call.usage,
        "error_category": call.error_category,
        "validation_stage": call.validation_stage,
        "validation_code": call.validation_code,
        "attempt_count": call.attempt_count,
        "response_id": call.response_id,
        "provider_status": call.provider_status,
        "incomplete_reason": call.incomplete_reason,
        "output_text_chars": call.output_text_chars,
        "output_text_bytes": call.output_text_bytes,
        "parse_status": call.parse_status,
        "result_kind": call.result_kind,
        "result_counts": call.result_counts,
    }
    if call.start_offset_ms is not None:
        result["start_offset_ms"] = call.start_offset_ms
    if call.ordinal is not None:
        result["ordinal"] = call.ordinal
    if call.input_sizes is not None:
        result["input_sizes"] = call.input_sizes
    if call.substeps:
        result["substeps"] = [_span_response(span) for span in call.substeps]
        result["coverage"] = _coverage_response(
            call.duration_ms,
            [(span.start_offset_ms, span.duration_ms) for span in call.substeps],
        )
    return result


def _stage_response(stage: Any) -> dict[str, Any]:
    """Serialize one stage and reconcile only child intervals with known offsets."""
    response: dict[str, Any] = {
        "name": stage.name,
        "outcome": stage.outcome.value,
        "duration_ms": stage.duration_ms,
        "model": stage.model,
        "reasoning_effort": stage.reasoning_effort,
        "usage": stage.usage,
        "estimated_cost_usd": stage.estimated_cost_usd,
        "error_category": stage.error_category,
        "provider_calls": [_call_response(call) for call in stage.provider_calls],
    }
    if stage.start_offset_ms is not None:
        response["start_offset_ms"] = stage.start_offset_ms
    if stage.substeps:
        response["substeps"] = [_span_response(span) for span in stage.substeps]
    intervals = [(span.start_offset_ms, span.duration_ms) for span in stage.substeps]
    intervals += [
        (call.start_offset_ms, call.duration_ms)
        for call in stage.provider_calls
        if call.start_offset_ms is not None and call.duration_ms is not None
    ]
    if intervals and not any(
        call.duration_ms is not None and call.start_offset_ms is None
        for call in stage.provider_calls
    ):
        response["coverage"] = _coverage_response(stage.duration_ms, intervals)
    return response


def operational_to_response(evidence: OperationalEvidence) -> dict[str, Any]:
    """Project one bounded timed hierarchy for Chat or Notes without payload content."""
    operational: dict[str, Any] = {
        "total_duration_ms": evidence.total_duration_ms,
        "stages": [_stage_response(stage) for stage in evidence.stages],
    }
    measured_stages = [stage for stage in evidence.stages if stage.duration_ms is not None]
    if measured_stages and all(stage.start_offset_ms is not None for stage in measured_stages):
        operational["coverage"] = _coverage_response(
            evidence.total_duration_ms,
            [(stage.start_offset_ms, stage.duration_ms) for stage in measured_stages],
        )
    return operational


def application_result_to_response(result: ApplicationResult) -> dict[str, Any]:
    """Project an ApplicationResult into safe JSON-compatible public evidence.

    Args:
        result: Typed result returned by odyssey_core.execute_request.

    Returns:
        Stable response containing status, action evidence, affected note IDs, pending work,
        and bounded Git history. Provider payloads, prompts, exceptions, and hidden reasoning
        are never copied into the response.

    Raises:
        TypeError: If result is not an ApplicationResult.
    """
    if not isinstance(result, ApplicationResult):
        raise TypeError("runtime executor must return ApplicationResult")
    product_outcome, product_reason = _product_outcome(result)
    return {
        "request_id": result.request_id,
        "status": result.status.value,
        "product_outcome": product_outcome,
        "product_reason": product_reason,
        "planning_error": result.planning_error,
        "clarification_code": result.clarification_code,
        "presentation_intent": result.presentation_intent,
        "note_result_snapshot": (
            dict(result.note_result_snapshot) if result.note_result_snapshot is not None else None
        ),
        "affected_stable_note_ids": list(result.affected_stable_note_ids),
        "actions": [_serialize_action(action) for action in result.action_results],
        "pending_work": {
            "required": result.pending_work.required,
            "persisted": result.pending_work.persisted,
            "record_id": result.pending_work.record_id,
            "error": result.pending_work.error,
        },
        "history": {
            "status": result.history.status.value,
            "commit_sha": result.history.commit_sha,
            "reason": result.history.reason,
        },
        "operational": operational_to_response(result.operational),
    }


def _product_outcome(result: ApplicationResult) -> tuple[str, str | None]:
    """Reduce internal execution outcomes to the three user-facing decisions."""
    if result.clarification_code is not None:
        return "CLARIFY", result.clarification_code
    for action in result.action_results:
        collection = action.semantic_set
        if collection is not None:
            if collection.outcome in {
                SemanticSetOutcome.AMBIGUOUS_REFERENCE,
                SemanticSetOutcome.AMBIGUOUS_SET_SCOPE,
            }:
                return "CLARIFY", collection.outcome.value
            if collection.outcome is not SemanticSetOutcome.ANSWERABLE:
                return "CANNOT_ANSWER", collection.outcome.value
        if action.reason in {
            "relational_evidence_ambiguous",
            "relational_singular_ambiguous",
            "ambiguous_existing_target",
        } or any(unit.reason == "ambiguous_existing_target" for unit in action.unit_results):
            return "CLARIFY", "AMBIGUOUS_REFERENCE"
    if result.status is not ApplicationStatus.COMPLETED:
        return (
            "CANNOT_ANSWER",
            "OPERATIONAL_FAILURE"
            if result.status is ApplicationStatus.FAILED
            else "INCOMPLETE_EVIDENCE",
        )
    for action in result.action_results:
        if action.status is not ActionStatus.COMPLETED:
            return "CANNOT_ANSWER", "INCOMPLETE_EVIDENCE"
        if (
            result.presentation_intent != "note_set"
            and action.retrieval is not None
            and not (action.retrieval.items or action.retrieval.related_items)
        ):
            return "CANNOT_ANSWER", "NO_RELEVANT_EVIDENCE"
    if result.presentation_intent != "answer":
        if result.note_result_snapshot is None:
            return "CANNOT_ANSWER", "INCOMPLETE_EVIDENCE"
        if result.note_result_snapshot.get("total") == 0:
            return "CANNOT_ANSWER", "NO_RELEVANT_EVIDENCE"
    return "ANSWER", None


def _serialize_action(action: ActionResult) -> dict[str, Any]:
    """Serialize one action while retaining only caller-useful semantic evidence."""
    serialized: dict[str, Any] = {
        "action_index": action.action_index,
        "kind": action.kind,
        "status": action.status.value,
        "reason": action.reason,
        "candidate_note_ids": list(action.candidate_note_ids),
        "units": [_serialize_unit(unit) for unit in action.unit_results],
    }
    if action.retrieval is not None:
        serialized["retrieval"] = {
            "query": action.retrieval.query,
            "items": [
                {
                    "id": item.id,
                    "path": item.path,
                    "primary_name": item.primary_name,
                    "type": item.type,
                    "tags": list(item.tags),
                    "metadata": dict(item.metadata),
                    "content": item.content,
                    "similarity": item.similarity,
                }
                for item in action.retrieval.items
            ],
            "related_items": [
                {
                    "id": item.id,
                    "target_id": item.target_id,
                    "target_name": item.target_name,
                    "direction": item.direction,
                    "source_id": item.source_id,
                    "source_path": item.source_path,
                    "source_name": item.source_name,
                    "source_type": item.source_type,
                    "content": item.content,
                    "similarity": item.similarity,
                }
                for item in action.retrieval.related_items
            ],
        }
    if action.semantic_set is not None:
        grounded = action.semantic_set.grounded_set
        serialized["collection"] = {
            "outcome": action.semantic_set.outcome.value,
            "reason": action.semantic_set.reason,
            "completeness": grounded.completeness.value if grounded is not None else None,
            "members": [
                {
                    "kind": "identity" if isinstance(member, IdentitySetMember) else "literal",
                    "value": (
                        member.display_name
                        if isinstance(member, IdentitySetMember)
                        else member.value
                    ),
                    "stable_note_id": (
                        member.stable_id if isinstance(member, IdentitySetMember) else None
                    ),
                    "source_note_id": member.evidence.source_note_id,
                }
                for member in grounded.members
            ]
            if grounded is not None and action.semantic_set.outcome is SemanticSetOutcome.ANSWERABLE
            else [],
        }
    if action.bulk_result is not None:
        serialized["bulk"] = {
            "succeeded": [item.stable_id for item in action.bulk_result.succeeded],
            "failed": [
                {"stable_note_id": item.stable_id, "reason": item.reason}
                for item in action.bulk_result.failed
            ],
        }
    if action.delegated_request is not None:
        serialized["delegated_request"] = action.delegated_request
    return serialized


def _serialize_unit(unit: UnitResult) -> dict[str, Any]:
    """Serialize one bounded write-unit outcome without raw exception details."""
    return {
        "unit_index": unit.unit_index,
        "status": unit.status.value,
        "operation": unit.operation,
        "stable_note_id": unit.stable_note_id,
        "reason": unit.reason,
        "candidates": list(unit.candidates),
        "dependencies": [
            {
                "source_unit_index": dependency.source_unit_index,
                "target_unit_index": dependency.target_unit_index,
                "reason": dependency.reason,
                "candidate_stable_ids": list(dependency.candidate_stable_ids),
            }
            for dependency in unit.dependencies
        ],
    }
