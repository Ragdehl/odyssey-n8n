"""Bounded in-memory product progress for the browser's transient processing indicator."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from threading import RLock
from typing import Any

MAX_PROGRESS_RECORDS = 128
MAX_DETAILS = 6
MAX_DETAIL_LENGTH = 120


@dataclass(frozen=True, slots=True)
class ProductProgress:
    """One latest-only user-safe progress snapshot."""

    request_id: str
    stage: str
    progress: int
    details: tuple[str, ...]
    sequence: int
    complete: bool = False

    def to_response(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "stage": self.stage,
            "progress": self.progress,
            "details": list(self.details),
            "sequence": self.sequence,
            "complete": self.complete,
        }


class ProductProgressStore:
    """Keep only bounded latest progress; never retain prompts, plans, or reasoning."""

    def __init__(self, max_records: int = MAX_PROGRESS_RECORDS) -> None:
        if not isinstance(max_records, int) or max_records < 1:
            raise ValueError("max_records must be positive")
        self._max_records = max_records
        self._lock = RLock()
        self._records: OrderedDict[tuple[str, str], ProductProgress] = OrderedDict()

    def begin(self, actor: str, request_id: str) -> ProductProgress:
        return self.update(actor, request_id, "starting", 0)

    def update(
        self,
        actor: str,
        request_id: str,
        stage: str,
        progress: int,
        details: tuple[str, ...] = (),
        *,
        complete: bool = False,
    ) -> ProductProgress:
        if not actor or not request_id or not stage:
            raise ValueError("progress identity and stage must be non-empty")
        if not isinstance(progress, int) or not 0 <= progress <= 100:
            raise ValueError("progress must be between 0 and 100")
        safe_details = tuple(
            value.strip()[:MAX_DETAIL_LENGTH]
            for value in details[:MAX_DETAILS]
            if isinstance(value, str) and value.strip()
        )
        key = (actor, request_id)
        with self._lock:
            previous = self._records.get(key)
            sequence = 1 if previous is None else previous.sequence + 1
            snapshot = ProductProgress(
                request_id,
                stage,
                max(progress, previous.progress if previous is not None else 0),
                safe_details,
                sequence,
                complete,
            )
            self._records[key] = snapshot
            self._records.move_to_end(key)
            while len(self._records) > self._max_records:
                self._records.popitem(last=False)
            return snapshot

    def read(self, actor: str, request_id: str) -> ProductProgress | None:
        with self._lock:
            snapshot = self._records.get((actor, request_id))
            if snapshot is not None:
                self._records.move_to_end((actor, request_id))
            return snapshot
