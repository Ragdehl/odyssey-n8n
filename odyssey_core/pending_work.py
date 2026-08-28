"""Durable, non-knowledge evidence for incomplete validated Odyssey requests."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .bulk_update import BulkUpdateResult
from .context import ContextFilter, ContextItem, ContextPackage
from .request_planning import (
    DelegateAction,
    KnowledgeUnit,
    LinkScope,
    NoteSelector,
    RequestPlan,
    RetrieveAction,
    SelectionCriteria,
    WriteAction,
)

if TYPE_CHECKING:
    from .application import ActionResult, ApplicationResult, UnitResult


_FORMAT = "odyssey_pending_work"
_FORMAT_VERSION = 1
_SAFE_REQUEST_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}\Z")


class PendingWorkError(RuntimeError):
    """Indicate a contained pending-work persistence or record-validation failure."""


class PendingWorkRepository:
    """Create and inspect deterministic open pending-work records beneath one existing root."""

    def __init__(self, root: Path | str) -> None:
        """Configure an existing directory used exclusively for pending JSON records.

        Args:
            root: Existing pending-work directory, such as ``state/pending``.

        Raises:
            PendingWorkError: If the root is missing or is not a directory.
        """
        path = Path(root)
        if not path.is_dir():
            raise PendingWorkError("pending root is unavailable")
        self._root = path.resolve()

    def record(
        self, *, user_request: str, plan: RequestPlan, result: ApplicationResult, created_at: str
    ) -> str:
        """Persist one create-only projection of incomplete actions for a validated request.

        Args:
            user_request: Exact raw application request.
            plan: Validated plan executed by the application boundary.
            result: Corresponding post-plan application evidence.
            created_at: Explicit application timestamp for deterministic records.

        Returns:
            The request ID used as the durable record ID.

        Raises:
            PendingWorkError: If the record is unsafe, duplicate, or cannot be serialized/written.
        """
        payload = project_pending_work(
            user_request=user_request, plan=plan, result=result, created_at=created_at
        )
        request_id = result.request_id
        target = self._path_for(request_id)
        encoded = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        try:
            with target.open("xb") as handle:
                handle.write(encoded)
        except FileExistsError as error:
            raise PendingWorkError("pending record already exists") from error
        except OSError as error:
            raise PendingWorkError("pending record could not be created") from error
        return request_id

    def read(self, request_id: str) -> dict[str, Any]:
        """Read and minimally validate one supported open pending-work record.

        Args:
            request_id: Safe durable record identifier.

        Returns:
            Validated JSON object for the requested record.

        Raises:
            PendingWorkError: If the record is unavailable, malformed, or incompatible.
        """
        path = self._path_for(request_id)
        if path.is_symlink():
            raise PendingWorkError("pending record must not be a symlink")
        try:
            with path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise PendingWorkError("pending record could not be read") from error
        _validate_record(payload, request_id)
        return payload

    def list_ids(self) -> tuple[str, ...]:
        """Return safe pending-record identifiers in lexical order.

        Raises:
            PendingWorkError: If the configured pending root cannot be listed safely.
        """
        try:
            entries = list(self._root.iterdir())
        except OSError as error:
            raise PendingWorkError("pending root could not be listed") from error
        if any(path.is_symlink() for path in entries):
            raise PendingWorkError("pending root contains a symlink")
        names = [path.name for path in entries if path.is_file() and path.suffix == ".json"]
        ids = [name.removesuffix(".json") for name in names]
        if any(_SAFE_REQUEST_ID.fullmatch(record_id) is None for record_id in ids):
            raise PendingWorkError("pending root contains an unsafe record name")
        return tuple(sorted(ids))

    def _path_for(self, request_id: str) -> Path:
        """Return the contained JSON path derived exactly from one safe request ID."""
        if not isinstance(request_id, str) or _SAFE_REQUEST_ID.fullmatch(request_id) is None:
            raise PendingWorkError("unsafe pending request ID")
        target = self._root / f"{request_id}.json"
        if target.parent != self._root:
            raise PendingWorkError("unsafe pending request ID")
        return target


def project_pending_work(
    *, user_request: str, plan: RequestPlan, result: ApplicationResult, created_at: str
) -> dict[str, Any]:
    """Project validated incomplete request evidence into the Phase 17B JSON contract.

    Only actions whose typed status is not ``completed`` are retained. For example, a complete
    independent write is omitted while a dependent deferred write preserves its whole action table.

    Raises:
        PendingWorkError: If supplied values cannot form a safe supported record.
    """
    if not isinstance(user_request, str) or not isinstance(created_at, str) or not created_at:
        raise PendingWorkError("pending record has invalid request metadata")
    if not isinstance(plan, RequestPlan):
        raise PendingWorkError("pending record requires a RequestPlan")
    if len(plan.actions) != len(result.action_results):
        raise PendingWorkError("pending record action evidence does not match plan")
    incomplete = []
    for action, evidence in zip(plan.actions, result.action_results, strict=True):
        if evidence.status.value != "completed":
            incomplete.append(
                {
                    "action_index": evidence.action_index,
                    "planned_action": _action(action),
                    "execution_result": _action_result(evidence),
                }
            )
    if not incomplete:
        raise PendingWorkError("pending record requires incomplete actions")
    return {
        "format": _FORMAT,
        "format_version": _FORMAT_VERSION,
        "request_id": result.request_id,
        "created_at": created_at,
        "status": "open",
        "user_request": user_request,
        "application_status": result.status.value,
        "planner_limitations": list(plan.limitations),
        "affected_stable_note_ids": list(result.affected_stable_note_ids),
        "incomplete_actions": incomplete,
    }


def _selection(value: SelectionCriteria | None) -> dict[str, Any] | None:
    """Project a validated selection and optional link scope into JSON values."""
    if value is None:
        return None
    return {
        "entity": value.entity,
        "query": value.query,
        "type": value.type,
        "filters": [_filter(item) for item in value.filters],
        "link_scope": _link_scope(value.link_scope),
    }


def _filter(value: ContextFilter) -> dict[str, Any]:
    """Project one public deterministic context filter."""
    return {"field": value.field, "op": value.op, "value": _json_value(value.value)}


def _link_scope(value: LinkScope | None) -> dict[str, Any] | None:
    """Project optional validated graph traversal intent without executing it."""
    if value is None:
        return None
    anchor: NoteSelector = value.anchor
    return {
        "anchor": {
            "entity": anchor.entity,
            "query": anchor.query,
            "type": anchor.type,
            "filters": [_filter(item) for item in anchor.filters],
        },
        "direction": value.direction,
        "max_depth": value.max_depth,
    }


def _action(value: Any) -> dict[str, Any]:
    """Project one supported validated planner action using only public semantic fields."""
    if isinstance(value, RetrieveAction):
        return {"kind": value.kind, "plan": _selection(value.plan)}
    if isinstance(value, WriteAction):
        return {"kind": value.kind, "units": [_unit(item) for item in value.units]}
    if isinstance(value, DelegateAction):
        return {
            "kind": value.kind,
            "request": value.request,
            "selection": _selection(value.selection),
        }
    raise PendingWorkError("unsupported planned action")


def _unit(value: KnowledgeUnit) -> dict[str, Any]:
    """Project a complete validated write unit so local reference indexes remain meaningful."""
    return {
        "target": _selection(value.target),
        "intent": value.intent,
        "properties": [
            {"field": item.field, "op": item.op, "value": _json_value(item.value)}
            for item in value.properties
        ],
        "tag_changes": [{"op": item.op, "value": item.value} for item in value.tag_changes],
        "facts": list(value.facts),
        "references": [
            {"target_index": item.target_index, "role": item.role, "mention": item.mention}
            for item in value.references
        ],
        "cardinality": value.cardinality,
        "destination_type": value.destination_type,
    }


def _action_result(value: ActionResult) -> dict[str, Any]:
    """Project typed application evidence without exceptions, providers, or hidden state."""
    payload: dict[str, Any] = {
        "action_index": value.action_index,
        "kind": value.kind,
        "status": value.status.value,
        "reason": value.reason,
        "unit_results": [_unit_result(item) for item in value.unit_results],
        "bulk_result": _bulk(value.bulk_result),
        "delegated_request": value.delegated_request,
        "delegated_selection": _selection(value.delegated_selection),
    }
    if value.retrieval is not None:
        payload["retrieval"] = _context(value.retrieval)
    return payload


def _unit_result(value: UnitResult) -> dict[str, Any]:
    """Project one write-unit result including every dependency evidence item."""
    return {
        "unit_index": value.unit_index,
        "status": value.status.value,
        "operation": value.operation,
        "stable_note_id": value.stable_note_id,
        "reason": value.reason,
        "candidates": list(value.candidates),
        "dependencies": [
            {
                "source_unit_index": item.source_unit_index,
                "target_unit_index": item.target_unit_index,
                "reason": item.reason,
                "candidate_stable_ids": list(item.candidate_stable_ids),
            }
            for item in value.dependencies
        ],
    }


def _bulk(value: BulkUpdateResult | None) -> dict[str, Any] | None:
    """Project frozen bulk selection and per-note evidence without recomputing membership."""
    if value is None:
        return None
    return {
        "requested_cardinality": value.requested_cardinality,
        "selected_note_ids": list(value.selected_note_ids),
        "succeeded": [
            {
                "stable_id": item.stable_id,
                "result": {
                    "operation": item.result.operation.value,
                    "id": item.result.id,
                    "path": item.result.path,
                    "revision": item.result.revision,
                },
            }
            for item in value.succeeded
        ],
        "failed": [
            {"stable_id": item.stable_id, "error_type": item.error_type, "reason": item.reason}
            for item in value.failed
        ],
        "status": value.status,
    }


def _context(value: ContextPackage) -> dict[str, Any]:
    """Project public retrieval evidence when an incomplete retrieval supplied it."""
    return {"query": value.query, "items": [_context_item(item) for item in value.items]}


def _context_item(value: ContextItem) -> dict[str, Any]:
    """Project public grounded context fields into JSON-compatible evidence."""
    return {
        "id": value.id,
        "path": value.path,
        "primary_name": value.primary_name,
        "type": value.type,
        "tags": list(value.tags),
        "metadata": _json_value(value.metadata),
        "content": value.content,
        "similarity": value.similarity,
    }


def _json_value(value: Any) -> Any:
    """Return an explicitly accepted JSON value or reject arbitrary runtime objects."""
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, tuple | list):
        return [_json_value(item) for item in value]
    if isinstance(value, Mapping) and all(isinstance(key, str) for key in value):
        return {key: _json_value(item) for key, item in value.items()}
    raise PendingWorkError("unsupported JSON value in pending evidence")


def _validate_record(payload: Any, request_id: str) -> None:
    """Fail closed on unsupported top-level records while keeping validation intentionally small."""
    if not isinstance(payload, dict):
        raise PendingWorkError("pending record must be an object")
    required = {
        "format",
        "format_version",
        "request_id",
        "created_at",
        "status",
        "user_request",
        "application_status",
        "planner_limitations",
        "affected_stable_note_ids",
        "incomplete_actions",
    }
    if (
        not required.issubset(payload)
        or payload["format"] != _FORMAT
        or payload["format_version"] != _FORMAT_VERSION
    ):
        raise PendingWorkError("unsupported pending record format")
    if payload["request_id"] != request_id or _SAFE_REQUEST_ID.fullmatch(request_id) is None:
        raise PendingWorkError("pending record request ID is invalid")
    if payload["status"] != "open":
        raise PendingWorkError("unsupported pending record status")
    if not all(
        isinstance(payload[key], str)
        for key in ("created_at", "user_request", "application_status")
    ):
        raise PendingWorkError("pending record has invalid request fields")
    if not all(
        isinstance(payload[key], list)
        for key in ("planner_limitations", "affected_stable_note_ids", "incomplete_actions")
    ):
        raise PendingWorkError("pending record has invalid collection fields")
    if not all(isinstance(item, str) for item in payload["planner_limitations"]):
        raise PendingWorkError("pending record has invalid planner limitations")
    if not all(isinstance(item, str) for item in payload["affected_stable_note_ids"]):
        raise PendingWorkError("pending record has invalid affected IDs")
    if not payload["incomplete_actions"] or not all(
        isinstance(item, dict)
        and isinstance(item.get("action_index"), int)
        and isinstance(item.get("planned_action"), dict)
        and isinstance(item["planned_action"].get("kind"), str)
        and isinstance(item.get("execution_result"), dict)
        and isinstance(item["execution_result"].get("status"), str)
        for item in payload["incomplete_actions"]
    ):
        raise PendingWorkError("pending record has invalid incomplete actions")
