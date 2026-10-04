"""Regression coverage for the shared Temporal v1 application contract."""

from __future__ import annotations

import pytest

from odyssey_core.temporal import DateRange, TemporalValueError, normalize_iso_datetime
from odyssey_core.temporal_resolution import (
    TemporalResolution,
    TemporalResolutionKind,
    parse_temporal_resolution,
    temporal_resolution_json_schema,
)

ALL_V1_KINDS = tuple(TemporalResolutionKind)
TASK_SHAPES = (
    TemporalResolutionKind.EXACT_DATE,
    TemporalResolutionKind.EXACT_DATETIME,
    TemporalResolutionKind.UNSPECIFIED,
)


def payload(**overrides: object) -> dict[str, object]:
    """Build one complete strict Temporal v1 provider payload."""
    result: dict[str, object] = {
        "kind": "UNSPECIFIED",
        "exact_date": None,
        "exact_datetime": None,
        "range_start": None,
        "range_end_exclusive": None,
    }
    result.update(overrides)
    return result


def test_exact_datetime_is_canonical_and_timezone_validated() -> None:
    """Accept a real Paris wall time and normalize it to second precision."""
    assert (
        normalize_iso_datetime("2026-10-05T15:00+02:00", timezone="Europe/Paris")
        == "2026-10-05T15:00:00+02:00"
    )
    resolution = parse_temporal_resolution(
        payload(kind="EXACT_DATETIME", exact_datetime="2026-10-05T15:00:00+02:00"),
        allowed_kinds=TASK_SHAPES,
        timezone="Europe/Paris",
    )
    assert resolution == TemporalResolution(
        TemporalResolutionKind.EXACT_DATETIME,
        exact_datetime="2026-10-05T15:00:00+02:00",
        timezone="Europe/Paris",
    )
    assert resolution.calendar_date() == "2026-10-05"


def test_exact_datetime_rejects_naive_or_wrong_zone_offset() -> None:
    """Keep the canonical Core primitive strict even when provider decoding is tolerant."""
    with pytest.raises(TemporalValueError, match="explicit UTC offset"):
        normalize_iso_datetime("2026-10-05T15:00:00", timezone="Europe/Paris")
    with pytest.raises(TemporalValueError, match="does not match"):
        normalize_iso_datetime("2026-12-05T15:00:00+02:00", timezone="Europe/Paris")


def test_provider_exact_datetime_localizes_unambiguous_wall_time() -> None:
    """Resolve provider-local wall time with runtime timezone before constructing Core value."""
    resolution = parse_temporal_resolution(
        payload(kind="EXACT_DATETIME", exact_datetime="2026-10-05T15:00:00"),
        allowed_kinds=TASK_SHAPES,
        timezone="Europe/Paris",
    )
    assert resolution.exact_datetime == "2026-10-05T15:00:00+02:00"


def test_provider_exact_datetime_rejects_ambiguous_or_nonexistent_local_wall_time() -> None:
    """Never guess a DST fold or normalize a local clock time that does not exist."""
    for value in ("2026-10-25T02:30:00", "2026-03-29T02:30:00"):
        with pytest.raises(TemporalValueError, match="ambiguous or nonexistent"):
            parse_temporal_resolution(
                payload(kind="EXACT_DATETIME", exact_datetime=value),
                allowed_kinds=TASK_SHAPES,
                timezone="Europe/Paris",
            )


def test_exact_datetime_rejects_nonexistent_dst_wall_time() -> None:
    """Never normalize a local clock time skipped by a daylight-saving transition."""
    with pytest.raises(TemporalValueError, match="does not match"):
        normalize_iso_datetime("2026-03-29T02:30:00+01:00", timezone="Europe/Paris")
    with pytest.raises(TemporalValueError, match="does not match"):
        normalize_iso_datetime("2026-03-29T02:30:00+02:00", timezone="Europe/Paris")


def test_exact_datetime_accepts_either_real_dst_fold_when_the_instant_is_already_resolved() -> None:
    """Value validation accepts either real offset; source-level ambiguity belongs to the app."""
    assert (
        normalize_iso_datetime("2026-10-25T02:30:00+02:00", timezone="Europe/Paris")
        == "2026-10-25T02:30:00+02:00"
    )
    assert (
        normalize_iso_datetime("2026-10-25T02:30:00+01:00", timezone="Europe/Paris")
        == "2026-10-25T02:30:00+01:00"
    )


def test_shared_contract_keeps_date_range_and_unspecified_distinct() -> None:
    """Preserve the existing Calendar shapes while adding exact date-time as a sibling shape."""
    exact = parse_temporal_resolution(
        payload(kind="EXACT_DATE", exact_date="2026-10-05"),
        allowed_kinds=ALL_V1_KINDS,
    )
    ranged = parse_temporal_resolution(
        payload(kind="DATE_RANGE", range_start="2026-10-05", range_end_exclusive="2026-10-08"),
        allowed_kinds=ALL_V1_KINDS,
    )
    unspecified = parse_temporal_resolution(payload(), allowed_kinds=ALL_V1_KINDS)

    assert exact == TemporalResolution(TemporalResolutionKind.EXACT_DATE, exact_date="2026-10-05")
    assert ranged == TemporalResolution(
        TemporalResolutionKind.DATE_RANGE,
        date_range=DateRange("2026-10-05", "2026-10-08"),
    )
    assert unspecified == TemporalResolution(TemporalResolutionKind.UNSPECIFIED)


def test_application_subset_cannot_silently_accept_unsupported_temporal_shape() -> None:
    """An app opts into Temporal shapes explicitly instead of inheriting every future addition."""
    calendar_shapes = (
        TemporalResolutionKind.EXACT_DATE,
        TemporalResolutionKind.DATE_RANGE,
        TemporalResolutionKind.UNSPECIFIED,
    )
    schema = temporal_resolution_json_schema(allowed_kinds=calendar_shapes)
    assert schema["properties"]["kind"]["enum"] == [
        "EXACT_DATE",
        "DATE_RANGE",
        "UNSPECIFIED",
    ]
    with pytest.raises(TemporalValueError, match="not allowed"):
        parse_temporal_resolution(
            payload(kind="EXACT_DATETIME", exact_datetime="2026-10-05T15:00:00+02:00"),
            allowed_kinds=calendar_shapes,
            timezone="Europe/Paris",
        )


def test_exact_datetime_requires_explicit_runtime_timezone_context() -> None:
    """Do not accept a wall-clock instant when the owning app omitted timezone context."""
    with pytest.raises(TemporalValueError, match="requires timezone context"):
        parse_temporal_resolution(
            payload(kind="EXACT_DATETIME", exact_datetime="2026-10-05T15:00:00+02:00"),
            allowed_kinds=TASK_SHAPES,
        )


@pytest.mark.parametrize(
    "candidate",
    [
        TemporalResolution(
            TemporalResolutionKind.EXACT_DATE,
            exact_date="2026-10-05",
        ),
        TemporalResolution(
            TemporalResolutionKind.EXACT_DATETIME,
            exact_datetime="2026-10-05T15:00:00+02:00",
            timezone="Europe/Paris",
        ),
        TemporalResolution(
            TemporalResolutionKind.DATE_RANGE,
            date_range=DateRange("2026-10-05", "2026-10-08"),
        ),
        TemporalResolution(TemporalResolutionKind.UNSPECIFIED),
    ],
)
def test_temporal_resolution_public_shapes_construct_directly(
    candidate: TemporalResolution,
) -> None:
    """Keep every v1 normalized shape usable without a provider adapter."""
    assert isinstance(candidate, TemporalResolution)
