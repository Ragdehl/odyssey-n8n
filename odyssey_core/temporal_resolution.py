"""Shared normalized temporal-resolution contract for Odyssey applications.

Application planners may interpret natural-language time inside their own model call.  This module
owns only the closed normalized shapes and deterministic validation reused by Calendar, Tasks, Events,
and later capabilities; it is not a natural-language parser and performs no routing or mutation.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from .temporal import DateRange, TemporalValueError, normalize_iso_date, normalize_iso_datetime


class TemporalResolutionKind(StrEnum):
    """Name the shared normalized temporal shapes available to application contracts."""

    EXACT_DATE = "EXACT_DATE"
    EXACT_DATETIME = "EXACT_DATETIME"
    DATE_RANGE = "DATE_RANGE"
    UNSPECIFIED = "UNSPECIFIED"


@dataclass(frozen=True, slots=True)
class TemporalResolution:
    """Carry one validated normalized temporal interpretation without domain-role semantics."""

    kind: TemporalResolutionKind
    exact_date: str | None = None
    exact_datetime: str | None = None
    date_range: DateRange | None = None
    timezone: str | None = None

    def __post_init__(self) -> None:
        """Fail closed when fields do not correlate with the declared temporal shape."""
        if not isinstance(self.kind, TemporalResolutionKind):
            raise TemporalValueError("Temporal resolution kind is invalid")
        if self.kind is TemporalResolutionKind.EXACT_DATE:
            if (
                self.exact_date is None
                or self.exact_datetime is not None
                or self.date_range is not None
                or self.timezone is not None
            ):
                raise TemporalValueError("Exact-date temporal resolution fields are invalid")
            object.__setattr__(self, "exact_date", normalize_iso_date(self.exact_date))
            return
        if self.kind is TemporalResolutionKind.EXACT_DATETIME:
            if (
                self.exact_datetime is None
                or self.timezone is None
                or self.exact_date is not None
                or self.date_range is not None
            ):
                raise TemporalValueError("Exact-date-time temporal resolution fields are invalid")
            object.__setattr__(
                self,
                "exact_datetime",
                normalize_iso_datetime(self.exact_datetime, timezone=self.timezone),
            )
            return
        if self.kind is TemporalResolutionKind.DATE_RANGE:
            if (
                self.date_range is None
                or self.exact_date is not None
                or self.exact_datetime is not None
                or self.timezone is not None
            ):
                raise TemporalValueError("Date-range temporal resolution fields are invalid")
            if not isinstance(self.date_range, DateRange):
                raise TemporalValueError("Temporal date range is invalid")
            return
        if any(
            value is not None
            for value in (self.exact_date, self.exact_datetime, self.date_range, self.timezone)
        ):
            raise TemporalValueError("Unspecified temporal resolution must not carry values")

    def calendar_date(self) -> str | None:
        """Return the local calendar date for an exact date or exact date-time resolution."""
        if self.kind is TemporalResolutionKind.EXACT_DATE:
            return self.exact_date
        if self.kind is TemporalResolutionKind.EXACT_DATETIME and self.exact_datetime is not None:
            return self.exact_datetime[:10]
        return None


def temporal_resolution_json_schema(
    *, allowed_kinds: Sequence[TemporalResolutionKind]
) -> dict[str, Any]:
    """Return a reusable strict provider-schema fragment for one temporal resolution."""
    kinds = _validated_allowed_kinds(allowed_kinds)
    return {
        "type": "object",
        "properties": {
            "kind": {"type": "string", "enum": [item.value for item in kinds]},
            "exact_date": {"type": ["string", "null"]},
            "exact_datetime": {"type": ["string", "null"]},
            "range_start": {"type": ["string", "null"]},
            "range_end_exclusive": {"type": ["string", "null"]},
        },
        "required": [
            "kind",
            "exact_date",
            "exact_datetime",
            "range_start",
            "range_end_exclusive",
        ],
        "additionalProperties": False,
    }


def parse_temporal_resolution(
    payload: Mapping[str, Any],
    *,
    allowed_kinds: Sequence[TemporalResolutionKind],
    timezone: str | None = None,
) -> TemporalResolution:
    """Decode one provider payload into the shared normalized temporal contract."""
    required = {"kind", "exact_date", "exact_datetime", "range_start", "range_end_exclusive"}
    if not isinstance(payload, Mapping) or set(payload) != required:
        raise TemporalValueError("Temporal resolution payload fields are invalid")
    kinds = _validated_allowed_kinds(allowed_kinds)
    try:
        kind = TemporalResolutionKind(payload["kind"])
    except (TypeError, ValueError) as error:
        raise TemporalValueError("Temporal resolution kind is invalid") from error
    if kind not in kinds:
        raise TemporalValueError("Temporal resolution kind is not allowed by this application")
    exact_date = payload["exact_date"]
    exact_datetime = payload["exact_datetime"]
    range_start = payload["range_start"]
    range_end = payload["range_end_exclusive"]
    if kind is TemporalResolutionKind.EXACT_DATE:
        if not isinstance(exact_date, str) or any(
            value is not None for value in (exact_datetime, range_start, range_end)
        ):
            raise TemporalValueError("Exact-date temporal payload fields are invalid")
        return TemporalResolution(kind, exact_date=exact_date)
    if kind is TemporalResolutionKind.EXACT_DATETIME:
        if not isinstance(exact_datetime, str) or any(
            value is not None for value in (exact_date, range_start, range_end)
        ):
            raise TemporalValueError("Exact-date-time temporal payload fields are invalid")
        if timezone is None:
            raise TemporalValueError("Exact date-time resolution requires timezone context")
        return TemporalResolution(kind, exact_datetime=exact_datetime, timezone=timezone)
    if kind is TemporalResolutionKind.DATE_RANGE:
        if (
            exact_date is not None
            or exact_datetime is not None
            or not isinstance(range_start, str)
            or not isinstance(range_end, str)
        ):
            raise TemporalValueError("Date-range temporal payload fields are invalid")
        return TemporalResolution(kind, date_range=DateRange(range_start, range_end))
    if any(value is not None for value in (exact_date, exact_datetime, range_start, range_end)):
        raise TemporalValueError("Unspecified temporal payload must not carry values")
    return TemporalResolution(kind)


def _validated_allowed_kinds(
    allowed_kinds: Sequence[TemporalResolutionKind],
) -> tuple[TemporalResolutionKind, ...]:
    """Normalize one explicit app-level subset without inventing capability support."""
    if not isinstance(allowed_kinds, Sequence) or isinstance(allowed_kinds, (str, bytes)):
        raise TemporalValueError("Allowed temporal kinds must be an ordered sequence")
    kinds = tuple(allowed_kinds)
    if not kinds or not all(isinstance(item, TemporalResolutionKind) for item in kinds):
        raise TemporalValueError("Allowed temporal kinds are invalid")
    if len(kinds) != len(set(kinds)):
        raise TemporalValueError("Allowed temporal kinds must be unique")
    return kinds
