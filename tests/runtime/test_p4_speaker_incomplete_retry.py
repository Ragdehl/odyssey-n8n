"""Mechanical missing-row speaker retry; semantic disagreements remain fail-closed."""

from __future__ import annotations

from odyssey_core.notes import parse_note
from tests.runtime.test_whole_source_light_product_p4 import (
    RecordedClient,
    _actual_snapshot,
    _fixture,
    _speaker,
)


def test_one_incomplete_speaker_review_can_be_retried_prewrite_once(tmp_path):
    source, route, plan, review = _actual_snapshot("maya_simple")
    repo, actor, service, runtime = _fixture(tmp_path)
    before = {p: repo.read_text(p) for p in repo.list_markdown_paths()}
    service.client = RecordedClient(
        [
            route,
            plan,
            review,
            {"facts": []},
            _speaker(source, plan),
            _speaker(source, plan, base=1),
        ]
    )
    events = []
    service.prewrite_diagnostic = lambda request, gate, flags: events.append((gate, flags))
    result = runtime.execute_product(source, "p4-speaker-retry", "main", actor)
    assert result["status"] == "completed", result
    assert service.client.calls[-3:] == [
        "odyssey_speaker_full_A",
        "odyssey_speaker_full_B",
        "odyssey_speaker_full_A",
    ]
    assert (
        "speaker_count_retry",
        {"reviewer_a": True, "reviewer_b": False, "expected_facts": 1},
    ) in events
    notes = [parse_note(repo.read_text(p)) for p in repo.list_markdown_paths()]
    assert len(notes) > len(before)
    assert any("odyssey:fact request=p4-speaker-retry" in n.content for n in notes)


def test_still_incomplete_after_one_retry_never_creates_a_fact(tmp_path):
    source, route, plan, review = _actual_snapshot("maya_simple")
    repo, actor, service, runtime = _fixture(tmp_path)
    before = {p: repo.read_text(p) for p in repo.list_markdown_paths()}
    service.client = RecordedClient(
        [
            route,
            plan,
            review,
            {"facts": []},
            _speaker(source, plan),
            {"facts": []},
        ]
    )
    result = runtime.execute_product(source, "p4-speaker-still-missing", "main", actor)
    assert result["status"] == "needs_attention"
    assert service.client.calls.count("odyssey_speaker_full_A") == 2
    assert {p: repo.read_text(p) for p in repo.list_markdown_paths()} == before


def test_full_length_semantic_disagreement_never_retries_or_writes(tmp_path):
    source, route, plan, review = _actual_snapshot("maya_simple")
    repo, actor, service, runtime = _fixture(tmp_path)
    before = {p: repo.read_text(p) for p in repo.list_markdown_paths()}
    service.client = RecordedClient(
        [
            route,
            plan,
            review,
            _speaker(source, plan),
            _speaker(source, plan, role="other"),
        ]
    )
    events = []
    service.prewrite_diagnostic = lambda request, gate, flags: events.append(gate)
    result = runtime.execute_product(source, "p4-speaker-disagrees", "main", actor)
    assert result["status"] == "needs_attention"
    assert service.client.calls.count("odyssey_speaker_full_A") == 1
    assert service.client.calls.count("odyssey_speaker_full_B") == 1
    assert "speaker_count_retry" not in events
    assert "speaker_contract" in events
    assert {p: repo.read_text(p) for p in repo.list_markdown_paths()} == before
