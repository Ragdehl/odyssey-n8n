"""Calendar-owned mutation orchestration over Core canonical persistence primitives."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from odyssey_core.git_history import GitHistoryResult, HistoryRecorder, HistoryStatus
from odyssey_core.materialization import capture_calendar_day_literal
from odyssey_core.persistence import ActorInput, PersistenceOperation
from odyssey_core.storage import VaultRepository


@dataclass(frozen=True, slots=True)
class CalendarLiteralCaptureResult:
    """Return bounded evidence for one exact Day-owned literal capture."""

    note_id: str
    changed: bool
    history: GitHistoryResult


class CalendarLiteralCaptureService:
    """Coordinate Calendar literal capture while Core owns persistence and Git implementation."""

    def __init__(
        self,
        repository: VaultRepository,
        schema: dict[str, Any],
        history: HistoryRecorder | None,
    ) -> None:
        """Bind the authoritative Core repository, schema, and optional history recorder."""
        self.repository = repository
        self.schema = schema
        self.history = history

    def capture(
        self,
        *,
        date: str,
        literal: str,
        request_id: str,
        actor: ActorInput,
        now: str,
    ) -> CalendarLiteralCaptureResult:
        """Capture untouched routed wording on one exact Day and record request-level history."""
        snapshot = self._begin_history(request_id)
        result = capture_calendar_day_literal(
            repository=self.repository,
            schema=self.schema,
            date=date,
            literal=literal,
            actor=actor,
            now=now,
            request_id=request_id,
        )
        history = self._record_history(request_id, snapshot, result.id)
        return CalendarLiteralCaptureResult(
            result.id,
            result.operation is not PersistenceOperation.NO_CHANGE,
            history,
        )

    def _begin_history(self, request_id: str) -> object | None:
        """Begin existing Core history without making Git a mutation authority."""
        if self.history is None:
            return None
        try:
            return self.history.begin(request_id)
        except Exception:
            return None

    def _record_history(
        self, request_id: str, snapshot: object | None, note_id: str
    ) -> GitHistoryResult:
        """Record the same affected-note Git evidence used by established Core mutations."""
        if self.history is None:
            return GitHistoryResult.disabled()
        if snapshot is None:
            return GitHistoryResult(HistoryStatus.FAILED, reason="history snapshot failed")
        try:
            return self.history.record(
                request_id=request_id,
                snapshot=snapshot,
                affected_stable_note_ids=(note_id,),
                repository=self.repository,
                schema=self.schema,
            )
        except Exception:
            return GitHistoryResult(HistoryStatus.FAILED, reason="history record failed")
