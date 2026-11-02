"""R33: exact source, no fabricated members, and three required user effects.

This is a frozen offline oracle and single-component Day proof; it is NOT a
passing GPT+Tasks+journal-note-link end-to-end test.
"""

import json
from pathlib import Path

from odyssey_core.notes import parse_note
from tests.runtime.test_p4_general_day_journal_fallback import _reviewed_day
from tests.runtime.test_whole_source_light_product_p4 import RecordedClient, _fixture

CATALOG = Path(__file__).resolve().parents[1] / "fixtures/odyssey_additional_regressions_v1.json"


def test_r33_freezes_literal_recollection_task_and_link_without_member_invention():
    cases = json.loads(CATALOG.read_text())["cases"]
    assert [c["id"] for c in cases] == [*(f"R{i}" for i in range(28, 33)), "R33"]
    case = cases[-1]
    assert case["source"] == "He conocido varias personas. Mañana tengo que escribirles."
    assert len(case["expected_units"]) == 3
    assert [c["state"] for c in case["expected_units"]] == ["candidate"] * 3
    assert "never an invented Person" in case["expectation"]
    assert "Day Note" in case["expectation"]
    assert "tomorrow" in case["expectation"]
    assert case["live_acceptance"] == "pending"


def test_existing_p4_day_authority_preserves_group_text_without_new_people(tmp_path):
    repo, actor, executor, product = _fixture(tmp_path)
    source = "He conocido varias personas."
    executor.client = RecordedClient(_reviewed_day(source, "2026-10-16"))
    result = product.execute_product(source, "r33-day-proof", "main", actor)
    assert result["status"] == "completed", result
    notes = [parse_note(repo.read_text(path)) for path in repo.list_markdown_paths()]
    days = [note for note in notes if note.metadata.get("type") == "calendar_day"]
    assert len(days) == 1
    assert "He conocido varias personas" in days[0].content
    assert "(yo: [[self|Persona autenticada]])" in days[0].content
    assert not any(note.metadata.get("name") == "varias personas" for note in notes)
    # The follow-up Task-to-Day edge is NOT proved here; R33 stays pending.
