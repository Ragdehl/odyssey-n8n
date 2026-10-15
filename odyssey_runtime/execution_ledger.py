"""E2 read-only joined execution ledger, never a new delivery/mutation authority.

Sources are the EXISTING validated diagnostic checkpoints and Core result
receipts; no payload text, prompts, inferred routes, or synthetic successes.
An unavailable optional checkpoint does not erase verified physical writes.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from odyssey_core.application import ApplicationResult, UnitStatus
from odyssey_core.stage_presentation import stage_view_for

_MAX = 64


def project_execution_ledger(
    result: ApplicationResult, checkpoint: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    """Bounded stable projection of stages, route statuses and write receipts."""
    if not isinstance(result, ApplicationResult):
        raise TypeError("Core ApplicationResult is required for execution ledger")
    if checkpoint is not None and checkpoint.get("request_id") != result.request_id:
        raise ValueError("Cannot merge different request IDs in one execution ledger")
    events: list[dict[str, object]] = []
    if checkpoint is not None:
        for item in checkpoint.get("events", ())[-_MAX:]:
            # The source is an actor-scoped, validated LocalExecutionCheckpointStore.
            events.append(
                {
                    "sequence": item["sequence"],
                    "stage": item["stage"],
                    "outcome": item["outcome"],
                    "observed_at": item["observed_at"],
                }
            )
    stages = tuple(
        {
            "name": stage.name,
            "outcome": stage.outcome.value,
            "duration_ms": stage.duration_ms,
            "start_offset_ms": stage.start_offset_ms,
            "error_category": stage.error_category,
            "provider_call_count": len(stage.provider_calls),
            "stage_view": stage_view_for(stage.name).to_response(),
            # The real route-result aggregator supplies this exact owner. A
            # standalone Core stage or Router boundary keeps None.
            "route_index": stage.route_index,
        }
        for stage in result.operational.stages[:_MAX]
    )
    routes = []
    flow = result.execution_flow
    if isinstance(flow, Mapping) and isinstance(flow.get("routes"), (list, tuple)):
        for index, route in enumerate(flow["routes"][:32]):
            if not isinstance(route, Mapping):
                continue
            # Do not transport route.text, input, notes, or semantic payloads.
            routes.append(
                {
                    "route_index": index,
                    "capability": str(route.get("capability", ""))[:40],
                    "status": str(route.get("status", "unknown"))[:40],
                    "depends_on": route.get("depends_on")
                    if type(route.get("depends_on")) is int
                    else None,
                }
            )
    affected = tuple(result.affected_stable_note_ids[:_MAX])
    verified = set(affected)
    receipts = []
    for action in result.action_results[:_MAX]:
        for unit in action.unit_results[:_MAX]:
            note_id = unit.stable_note_id
            if (
                unit.status is UnitStatus.SUCCEEDED
                and unit.materially_affected
                and note_id
                and note_id in verified
            ):
                receipts.append(
                    {
                        "action_index": action.action_index,
                        "unit_index": unit.unit_index,
                        "stable_note_id": note_id,
                        "operation": (unit.operation or action.kind)[:48],
                        "status": unit.status.value,
                    }
                )
    return {
        "version": 1,
        "request_id": result.request_id,
        "status": result.status.value,
        "events": events,
        "event_sequence": checkpoint.get("sequence") if checkpoint is not None else None,
        "events_truncated": bool(checkpoint.get("truncated")) if checkpoint is not None else False,
        "stages": list(stages),
        "routes": routes,
        "write_receipts": receipts[:_MAX],
        # Preserve affected IDs even when a partial failure omitted individual
        # unit details; these come from the authoritative Core result.
        "affected_stable_note_ids": list(affected),
    }
