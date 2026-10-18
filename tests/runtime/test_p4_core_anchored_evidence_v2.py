"""End-to-end disposable Core Writer checks for generic anchored provenance v2."""

from __future__ import annotations

import copy

import pytest

from odyssey_core.notes import parse_note
from tests.runtime.test_p4_multitask_batch import (
    CREATE_AUDIT,
    PLAN,
    REVIEW,
    ROUTE,
    SCOPE,
    SOURCE,
)
from tests.runtime.test_whole_source_light_product_p4 import (
    RecordedClient,
    _actual_snapshot,
    _fixture,
    _speaker,
)


class TracedRecordedClient(RecordedClient):
    def __init__(self, rows):
        super().__init__(rows)
        self.speaker_payloads = []

    def create(self, **kwargs):
        import json

        if kwargs["text"]["format"]["name"].startswith("odyssey_speaker_full_"):
            self.speaker_payloads.append(json.loads(kwargs["input"][1]["content"]))
        return super().create(**kwargs)


def _anchored(plan, review):
    plan = copy.deepcopy(plan)
    review = copy.deepcopy(review)
    for item in plan["facts"]:
        item["source_evidence_fragments"] = []
        item["source_evidence_context"] = None
        item["source_evidence_fragment_contexts"] = []
    for item in review["facts"]:
        item.pop("source_quote")
    return plan, review


@pytest.mark.parametrize("scenario", ["two_dates", "maite_cross_app"])
def test_core_owned_evidence_for_mixed_note_types_and_cross_app_with_replay(tmp_path, scenario):
    source, route, raw_plan, raw_review = _actual_snapshot(scenario)
    plan, review = _anchored(raw_plan, raw_review)
    repo, actor, service, runtime = _fixture(tmp_path)
    service.core_anchored_coverage_enabled = True
    replies = [route, plan]
    if scenario == "maite_cross_app":
        replies.append(
            {
                "only_new_task_creations": True,
                "no_work_session_or_lifecycle_transition": True,
                "source_quote": source,
            }
        )
    replies += [review, _speaker(source, plan, base=1), _speaker(source, plan)]
    service.client = RecordedClient(replies)
    delivery = "p4-anchor-mixed-" + scenario
    actual = runtime.execute_product(source, delivery, "main", actor)
    assert actual["status"] == "completed", actual
    names = service.client.calls
    assert "odyssey_light_shared_semantic_plan_v2" in names
    assert "odyssey_p4_source_coverage_v2" in names
    assert len(actual["execution_flow"]["routes"][0]["writes"]) >= 2
    persisted = {p: repo.read_text(p) for p in repo.list_markdown_paths()}
    assert runtime.execute_product(source, delivery, "main", actor)["delivery_replayed"] is True
    assert persisted == {p: repo.read_text(p) for p in repo.list_markdown_paths()}


def test_same_generic_contract_writes_two_tasks_with_shared_full_source_span(tmp_path):
    plan, review = _anchored(PLAN, REVIEW)
    plan["facts"][1]["source_evidence"] = "tengo que llamar al electricista y revisar la factura"
    plan["facts"][0]["source_evidence_fragments"] = ["El 31 de octubre de 2026"]
    plan["facts"][1]["source_evidence_fragments"] = [
        "El 31 de octubre de 2026",
        "revisar la factura",
    ]
    plan["facts"][0]["source_evidence_fragment_contexts"] = [None]
    plan["facts"][1]["source_evidence_fragment_contexts"] = [None, None]
    repo, actor, service, runtime = _fixture(tmp_path)
    service.core_anchored_coverage_enabled = True
    service.task_create_batch_enabled = True
    service.client = TracedRecordedClient(
        [
            ROUTE,
            SCOPE,
            plan,
            CREATE_AUDIT,
            review,
            _speaker(SOURCE, plan, assertion="planned", base=1),
            _speaker(SOURCE, plan, assertion="planned"),
        ]
    )
    response = runtime.execute_product(SOURCE, "p4-anchored-shared", "main", actor)
    assert response["status"] == "completed", response
    notes = [parse_note(repo.read_text(p)) for p in repo.list_markdown_paths()]
    assert len([n for n in notes if n.metadata.get("type") == "task"]) == 2
    assert len(response["execution_flow"]["routes"][0]["writes"]) == 2
    assert len(service.client.speaker_payloads) == 2
    for payload in service.client.speaker_payloads:
        assert payload["facts"][1]["source_evidence_fragments"] == [
            "El 31 de octubre de 2026",
            "revisar la factura",
        ]
        assert payload["facts"][1]["source_evidence_context"] is None
        assert payload["facts"][1]["source_evidence_fragment_contexts"] == [None, None]


@pytest.mark.parametrize("fault", ["invented_support", "reviewer_quote", "unsupported"])
def test_no_note_is_written_when_anchored_provenance_is_untrusted(tmp_path, fault):
    plan, review = _anchored(PLAN, REVIEW)
    if fault == "invented_support":
        plan["facts"][1]["source_evidence_fragments"] = ["no está en el texto"]
    elif fault == "reviewer_quote":
        review["facts"][1]["source_quote"] = "invented"
    else:
        review["facts"][0]["supported"] = False
    repo, actor, service, runtime = _fixture(tmp_path)
    service.core_anchored_coverage_enabled = True
    service.task_create_batch_enabled = True
    service.client = RecordedClient(
        [
            ROUTE,
            SCOPE,
            plan,
            CREATE_AUDIT,
            review,
            _speaker(SOURCE, plan, assertion="planned", base=1),
            _speaker(SOURCE, plan, assertion="planned"),
        ]
    )
    before = {p: repo.read_text(p) for p in repo.list_markdown_paths()}
    result = runtime.execute_product(SOURCE, "p4-anchor-veto-" + fault, "main", actor)
    assert result["status"] == "needs_attention"
    assert before == {p: repo.read_text(p) for p in repo.list_markdown_paths()}
    if fault == "invented_support":
        # Provenance fails directly after Planner: neither task-creation audit
        # nor semantic Reviewer nor any speaker gets invented evidence.
        assert service.client.calls == [
            "odyssey_light_capability_route_v1",
            "odyssey_task_only_scope_v1",
            "odyssey_light_shared_semantic_plan_v2",
        ]
