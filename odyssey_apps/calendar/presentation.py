"""Calendar-owned public projections for the runtime transport boundary."""

from __future__ import annotations

from collections.abc import Sequence

from odyssey_core.note_queries import NoteBodyBlock, NoteBodySegment, NoteSummary

from .queries import CalendarDayView, CalendarMonth, CalendarSchedule, CalendarScheduleItem


def calendar_to_response(
    value: CalendarMonth | CalendarDayView | CalendarSchedule,
) -> dict[str, object]:
    """Serialize a Calendar query result without exposing paths or Markdown authority."""
    if isinstance(value, CalendarMonth):
        return {
            "kind": "calendar_month",
            "month": value.month,
            "days": [
                {
                    "date": item.date,
                    "materialized": item.materialized,
                    "has_content": item.has_content,
                    "journal_count": item.journal_count,
                    "captured_fact_count": item.captured_fact_count,
                    "reference_count": item.reference_count,
                    "task_count": item.task_count,
                    "preview_total": item.preview_total,
                    "previews": [
                        {
                            "kind": preview.kind,
                            "source_type": preview.source_type,
                            "label": preview.label,
                            **({"text": preview.text} if preview.text is not None else {}),
                        }
                        for preview in item.previews
                    ],
                }
                for item in value.days
            ],
        }
    if isinstance(value, CalendarSchedule):
        return {
            "kind": "calendar_schedule",
            "start_date": value.start_date,
            "day_count": value.day_count,
            "days": [
                {
                    "date": day.date,
                    "all_day": [_schedule_item_to_response(item) for item in day.all_day],
                    "timed": [_schedule_item_to_response(item) for item in day.timed],
                }
                for day in value.days
            ],
        }
    if isinstance(value, CalendarDayView):
        return {
            "kind": "calendar_day",
            "date": value.date,
            "materialized": value.materialized,
            "content": [_block_to_response(block) for block in value.content],
            "journals": [
                {
                    "source": _summary_to_response(item.source),
                    "content": [_block_to_response(block) for block in item.content],
                }
                for item in value.journals
            ],
            "captures": [
                {
                    "source": _summary_to_response(item.source),
                    "facts": [_block_to_response(block) for block in item.facts],
                }
                for item in value.captures
            ],
            "references": [
                {
                    "source": _summary_to_response(item.source),
                    "blocks": [_block_to_response(block) for block in item.blocks],
                }
                for item in value.references
            ],
            "tasks": [
                {
                    "source": _summary_to_response(item.source),
                    "roles": list(item.roles),
                    "mutation": {
                        "revision": item.revision,
                        "source_hash": item.source_hash,
                    },
                }
                for item in value.tasks
            ],
        }
    raise TypeError("Calendar response is invalid")


def _schedule_item_to_response(item: CalendarScheduleItem) -> dict[str, object]:
    """Serialize one grounded schedule item without exposing canonical storage details."""
    return {
        "kind": item.kind,
        "source_id": item.source_id,
        "source_type": item.source_type,
        "label": item.label,
        "role": item.role,
        **({"text": item.text} if item.text is not None else {}),
        **({"start_time": item.start_time} if item.start_time is not None else {}),
        **({"end_time": item.end_time} if item.end_time is not None else {}),
    }


def _block_to_response(block: NoteBodyBlock) -> dict[str, object]:
    """Serialize one Core-resolved Calendar content block."""
    return {"kind": block.kind, "segments": _segments_to_response(block.segments)}


def _segments_to_response(segments: Sequence[NoteBodySegment]) -> list[dict[str, object]]:
    """Serialize visible text and only stable Core-resolved link targets."""
    return [
        {
            "text": segment.text,
            **(
                {"target_id": segment.target_id, "target_type": segment.target_type}
                if segment.target_id is not None
                else {}
            ),
        }
        for segment in segments
    ]


def _summary_to_response(value: NoteSummary) -> dict[str, object]:
    """Serialize one stable Core Note summary for Calendar navigation."""
    return {
        "id": value.id,
        "name": value.name,
        "type": value.type,
        "tags": list(value.tags),
        "created_at": value.created_at,
        "updated_at": value.updated_at,
        "properties": dict(value.properties),
    }
