"""Exact-source Event target identity, even when GPT shortens note names."""

from pathlib import Path

from odyssey_apps.events.execution import current_exact_event
from odyssey_core import create_entity
from tests.apps.events.test_event_calendar_vertical import CLOCK, setup


def test_source_quote_selects_only_original_canonical_event(tmp_path: Path):
    schema, repo = setup(tmp_path)
    for index, marker in enumerate(("ABCD1234", "EFGH5678")):
        create_entity(
            repo,
            schema,
            path=f"event-{index}.md",
            entity_id=f"source-{index}",
            metadata={
                "type": "event",
                "name": "Excursión escolar",
                "event_status": "scheduled",
                "start_date": "2026-10-26",
            },
            content=f"- Excursión escolar E5 {marker} el lunes.",
            actor="fixture",
            now=CLOCK,
        )
    assert current_exact_event(repo, schema, "Excursión escolar E5 ABCD1234")[0] == "source-0"
    assert current_exact_event(repo, schema, "Excursión escolar E5 EFGH5678")[0] == "source-1"
    assert current_exact_event(repo, schema, "Excursión escolar") is None
    assert current_exact_event(repo, schema, "Otra excursión E5 ABCD1234") is None
