"""Serialize typed Odyssey application evidence for external callers."""

from __future__ import annotations

from typing import Any

from odyssey_core.application import ActionResult, ApplicationResult, UnitResult


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
    return {
        "request_id": result.request_id,
        "status": result.status.value,
        "planning_error": result.planning_error,
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
        "operational": {
            "total_duration_ms": result.operational.total_duration_ms,
            "stages": [
                {
                    "name": stage.name,
                    "outcome": stage.outcome.value,
                    "duration_ms": stage.duration_ms,
                    "model": stage.model,
                    "reasoning_effort": stage.reasoning_effort,
                    "usage": stage.usage,
                    "estimated_cost_usd": stage.estimated_cost_usd,
                    "error_category": stage.error_category,
                }
                for stage in result.operational.stages
            ],
        },
    }


def _serialize_action(action: ActionResult) -> dict[str, Any]:
    """Serialize one action while retaining only caller-useful semantic evidence."""
    serialized: dict[str, Any] = {
        "action_index": action.action_index,
        "kind": action.kind,
        "status": action.status.value,
        "reason": action.reason,
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
