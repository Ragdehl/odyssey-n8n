"""Compatibility adapter for Calendar's Core-owned fixed-destination capture boundary."""

from __future__ import annotations

from typing import Any

from odyssey_core.fixed_fact_capture import FixedFactCaptureResult, FixedFactCaptureService
from odyssey_core.git_history import HistoryRecorder
from odyssey_core.persistence import ActorInput
from odyssey_core.storage import VaultRepository

CalendarLiteralCaptureResult = FixedFactCaptureResult


class CalendarLiteralCaptureService:
    """Preserve the historical Calendar API while Core owns all capture semantics."""

    def __init__(
        self,
        repository: VaultRepository,
        schema: dict[str, Any],
        history: HistoryRecorder | None,
    ) -> None:
        self._core = FixedFactCaptureService(repository, schema, history)

    def capture(
        self,
        *,
        date: str,
        literal: str,
        request_id: str,
        actor: ActorInput,
        now: str,
    ) -> CalendarLiteralCaptureResult:
        """Delegate the legacy literal-only call to the Core-managed Day destination."""
        return self._core.capture_calendar_day(
            date=date,
            capture_text=literal,
            request_id=request_id,
            actor=actor,
            now=now,
        )
