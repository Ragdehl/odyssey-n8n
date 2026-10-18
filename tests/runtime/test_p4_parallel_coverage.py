"""Independent prewrite provider reviews overlap only in DEV; vetoes remain absolute."""

from __future__ import annotations

import json
from threading import Lock
from time import perf_counter, sleep
from types import SimpleNamespace

from tests.runtime.test_whole_source_light_product_p4 import _actual_snapshot, _fixture, _speaker


def _client(records, *, delay=0.16):
    class ThreadSafeClient:
        def __init__(self):
            self.responses = self
            self.calls = []
            self.lock = Lock()

        def create(self, **kwargs):
            name = kwargs["text"]["format"]["name"]
            with self.lock:
                self.calls.append((name, perf_counter()))
            if name == "odyssey_p2_source_coverage_v1" or name.startswith("odyssey_speaker_full_"):
                sleep(delay)
            return SimpleNamespace(status="completed", output_text=json.dumps(records[name]))

    return ThreadSafeClient()


def test_independent_coverage_and_speaker_attestations_overlap_without_losing_any(tmp_path):
    source, route, plan, review = _actual_snapshot("maya_simple")
    repo, actor, executor, runtime = _fixture(tmp_path)
    records = {
        "odyssey_light_capability_route_v1": route,
        "odyssey_light_shared_semantic_plan_v1": plan,
        "odyssey_p2_source_coverage_v1": review,
        "odyssey_speaker_full_A": _speaker(source, plan, base=1),
        "odyssey_speaker_full_B": _speaker(source, plan),
    }
    client = _client(records)
    executor.client = client
    executor.parallel_speaker_reviews = True
    executor.parallel_coverage_speaker_reviews = True
    result = runtime.execute_product(source, "p4-parallel-coverage-safe", "main", actor)
    assert result["status"] == "completed"
    assert "(yo:" in repo.read_text("calendar/days/2026-10-15.md")
    started = dict(client.calls)
    assert len(started) == 5
    assert abs(started["odyssey_p2_source_coverage_v1"] - started["odyssey_speaker_full_A"]) < 0.09
    assert abs(started["odyssey_speaker_full_B"] - started["odyssey_speaker_full_A"]) < 0.09
    spans = result["operational"]["stages"][0]["substeps"]
    assert len([span for span in spans if span["name"].startswith("provider.")]) == 5
    provider_spans = sorted(
        (span for span in spans if span["name"].startswith("provider.")),
        key=lambda span: span["start_offset_ms"],
    )
    assert provider_spans[0]["name"].endswith("odyssey_light_capability_route_v1")
    assert any(span["name"].endswith("odyssey_p2_source_coverage_v1") for span in provider_spans)


def test_invalid_speaker_still_vetoes_before_any_canonical_write(tmp_path):
    source, route, plan, review = _actual_snapshot("maya_simple")
    repo, actor, executor, runtime = _fixture(tmp_path)
    before = {path: repo.read_text(path) for path in repo.list_markdown_paths()}
    wrong_speaker = _speaker(source, plan)
    wrong_speaker["facts"][0]["source_quote"] = "texto que nunca dijo el usuario"
    client = _client(
        {
            "odyssey_light_capability_route_v1": route,
            "odyssey_light_shared_semantic_plan_v1": plan,
            "odyssey_p2_source_coverage_v1": review,
            "odyssey_speaker_full_A": wrong_speaker,
            "odyssey_speaker_full_B": _speaker(source, plan),
        },
        delay=0.01,
    )
    executor.client = client
    executor.parallel_speaker_reviews = True
    executor.parallel_coverage_speaker_reviews = True
    result = runtime.execute_product(source, "p4-parallel-speaker-veto", "main", actor)
    assert result["status"] == "needs_attention"
    assert {path: repo.read_text(path) for path in repo.list_markdown_paths()} == before
    assert len(client.calls) == 5
