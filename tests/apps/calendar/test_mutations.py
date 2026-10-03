"""Calendar literal capture over Core canonical persistence and provenance."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from odyssey_apps.calendar import CalendarLiteralCaptureService
from odyssey_core.atomic_facts import parse_atomic_facts
from odyssey_core.notes import parse_note
from odyssey_core.storage import VaultRepository

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def schema() -> dict:
    """Load the canonical schema with Calendar-managed Day ownership."""
    return json.loads((ROOT / "config/note-schema.json").read_text(encoding="utf-8"))


def service(tmp_path: Path, schema: dict) -> tuple[Path, CalendarLiteralCaptureService]:
    """Build one isolated Calendar capture service without Git side effects."""
    vault = tmp_path / "vault"
    vault.mkdir()
    return vault, CalendarLiteralCaptureService(VaultRepository(vault), schema, None)


def test_first_exact_day_capture_is_atomic_and_preserves_original_route_text(
    tmp_path: Path, schema: dict
) -> None:
    """Create the semantic Day already containing the untouched user wording at revision one."""
    vault, captures = service(tmp_path, schema)
    result = captures.capture(
        date="2026-10-03",
        literal="Mañana viene el fontanero",
        request_id="route-1-test",
        actor={"human": "user-1", "app": "calendar"},
        now="2026-10-02T17:00:00+02:00",
    )
    note = parse_note((vault / "calendar/days/2026-10-03.md").read_text(encoding="utf-8"))
    facts = parse_atomic_facts(note.content)

    assert result.note_id == "date:2026-10-03" and result.changed is True
    assert note.metadata["revision"] == 1
    assert [fact.text for fact in facts] == ["Mañana viene el fontanero"]
    assert facts[0].request_id == "route-1-test" and facts[0].ordinal == 0
    assert "[[calendar/days/2026-10-02|02-10-2026]]" in note.content


def test_replay_and_duplicate_literal_do_not_create_duplicate_facts(
    tmp_path: Path, schema: dict
) -> None:
    """Keep request replay and exact duplicate capture deterministically idempotent."""
    vault, captures = service(tmp_path, schema)
    common = {
        "date": "2026-10-03",
        "literal": "Mañana viene el fontanero",
        "actor": {"human": "user-1", "app": "calendar"},
        "now": "2026-10-02T17:00:00+02:00",
    }
    first = captures.capture(request_id="route-1-test", **common)
    replay = captures.capture(request_id="route-1-test", **common)
    duplicate = captures.capture(request_id="route-2-test", **common)
    note = parse_note((vault / "calendar/days/2026-10-03.md").read_text(encoding="utf-8"))

    assert first.changed is True
    assert replay.changed is False and duplicate.changed is False
    assert note.metadata["revision"] == 1
    assert [fact.text for fact in parse_atomic_facts(note.content)] == ["Mañana viene el fontanero"]


def test_second_distinct_literal_appends_under_existing_capture_chronology(
    tmp_path: Path, schema: dict
) -> None:
    """Append a later fact without replacing Day identity or duplicating same-day Added headings."""
    vault, captures = service(tmp_path, schema)
    actor = {"human": "user-1", "app": "calendar"}
    captures.capture(
        date="2026-10-03",
        literal="Mañana viene el fontanero",
        request_id="r1",
        actor=actor,
        now="2026-10-02T17:00:00+02:00",
    )
    second = captures.capture(
        date="2026-10-03",
        literal="Mañana llega el paquete",
        request_id="r2",
        actor=actor,
        now="2026-10-02T18:00:00+02:00",
    )
    note = parse_note((vault / "calendar/days/2026-10-03.md").read_text(encoding="utf-8"))

    assert second.changed is True and note.metadata["revision"] == 2
    assert [fact.text for fact in parse_atomic_facts(note.content)] == [
        "Mañana viene el fontanero",
        "Mañana llega el paquete",
    ]
    assert note.content.count("# Added") == 1


def test_same_day_first_capture_does_not_precreate_empty_self_link(
    tmp_path: Path, schema: dict
) -> None:
    """Keep a Day captured on itself at revision one despite its navigable Added self-reference."""
    vault, captures = service(tmp_path, schema)
    result = captures.capture(
        date="2026-10-02",
        literal="Hoy viene el fontanero",
        request_id="same-day",
        actor={"human": "user-1", "app": "calendar"},
        now="2026-10-02T17:00:00+02:00",
    )
    note = parse_note((vault / "calendar/days/2026-10-02.md").read_text(encoding="utf-8"))

    assert result.changed is True
    assert note.metadata["revision"] == 1
    assert [fact.text for fact in parse_atomic_facts(note.content)] == ["Hoy viene el fontanero"]
    assert "[[calendar/days/2026-10-02|02-10-2026]]" in note.content


def test_calendar_capture_delegates_request_history_to_core_recorder(
    tmp_path: Path, schema: dict
) -> None:
    """Record the exact affected Day through the shared request-level history boundary."""
    from odyssey_core.git_history import GitHistoryResult, GitHistorySnapshot, HistoryStatus

    vault = tmp_path / "vault-history"
    vault.mkdir()
    calls: list[object] = []

    class History:
        def begin(self, request_id: str) -> GitHistorySnapshot:
            calls.append(("begin", request_id))
            return GitHistorySnapshot(frozenset())

        def record(self, **kwargs):  # type: ignore[no-untyped-def]
            calls.append(("record", kwargs["request_id"], kwargs["affected_stable_note_ids"]))
            return GitHistoryResult(HistoryStatus.COMMITTED, commit_sha="a" * 40)

    captures = CalendarLiteralCaptureService(VaultRepository(vault), schema, History())
    result = captures.capture(
        date="2026-10-03",
        literal="Mañana viene el fontanero",
        request_id="route-history",
        actor={"human": "user-1", "app": "calendar"},
        now="2026-10-02T17:00:00+02:00",
    )

    assert result.history.status is HistoryStatus.COMMITTED
    assert calls == [
        ("begin", "route-history"),
        ("record", "route-history", ("date:2026-10-03",)),
    ]
