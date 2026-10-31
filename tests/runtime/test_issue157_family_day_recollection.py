"""Issue #157: past family/day knowledge is not an Events lifecycle write.

All fixtures are synthetic. Router/Planner model outputs are frozen proposals;
physical Core/E3 Markdown, identity resolution and delivery replay are real.
No assertion here replaces a fresh production GPT/DEV end-to-end gate.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from odyssey_core import create_entity
from odyssey_core.application import ApplicationResult, ApplicationStatus
from odyssey_core.atomic_facts import render_atomic_facts
from odyssey_core.notes import parse_note, serialize_note
from odyssey_runtime.whole_source_model_contract import capability_route_contract
from tests.runtime.test_whole_source_light_product_p4 import (
    SCHEMA,
    RecordedClient,
    _fixture,
)

SOURCE = "Hoy mis hijos, mi pareja y yo visitamos un jardín. Después visitamos un museo."
DAY = "2026-10-16"
PEOPLE = ("Nora", "Ivo", "Vera")
FACTS = ("Hoy mis hijos, mi pareja y yo visitamos un jardín.", "Después visitamos un museo.")


def _family(tmp_path, *, include_partner: bool = True):
    repo, actor, service, runtime = _fixture(tmp_path)
    for name in PEOPLE[: 3 if include_partner else 2]:
        create_entity(
            repo,
            SCHEMA,
            path=f"{name}.md",
            entity_id=f"person-{name}",
            metadata={"name": name, "type": "person"},
            content="",
            actor="synthetic",
            now="2026-10-16T08:00:00+02:00",
        )
    me = parse_note(repo.read_text("self.md"))
    family_facts = ["Mis hijos son [[Nora]] y [[Ivo]]."]
    if include_partner:
        family_facts.append("Mi pareja es [[Vera]].")
    body = render_atomic_facts(
        tuple(family_facts), "self-relations", tuple(range(len(family_facts))), DAY
    )
    repo.replace_text("self.md", serialize_note(replace(me, content=body)))
    service.context_index.rebuild(repo, SCHEMA, service.embedder)
    service.semantic_index.rebuild(repo, SCHEMA, service.embedder)
    service.event_delegate = lambda *_: pytest.fail(
        "Past recollection was delegated as a future Event"
    )
    return repo, actor, service, runtime


def _model_responses():
    route = {
        "capabilities": ["core", "temporal"],
        "self_relation_span": None,
        "self_relation_spans": ["mis hijos", "mi pareja"],
        "interpretation": "joint",
        "reason": "shared_subject",
        "app_scopes": [],
    }
    plan = {
        "entities": [],
        "facts": [
            {
                "meaning": text,
                "kind": "record",
                "subject": "family",
                "date": DAY,
                "daypart": None,
                "participants": list(PEOPLE),
                "source_evidence": text,
                "dependent_on_fact_index": None,
                "needs_clarification": False,
            }
            for text in FACTS
        ],
        "unresolved": [],
    }
    review = {
        "approved": True,
        "complete": True,
        "reason": None,
        "facts": [
            {
                "ordinal": i,
                "source_quote": text,
                "kind": "record",
                "reviewed_text": (
                    "{{ref:0}}, {{ref:1}} y {{ref:2}} visitamos un jardín." if i == 0 else text
                ),
                "date": DAY,
                "reference_names": list(PEOPLE) if i == 0 else [],
                "supported": True,
            }
            for i, text in enumerate(FACTS)
        ],
    }
    speaker = {
        "facts": [
            {
                "ordinal": i,
                "role": "self_participant",
                "assertion": "asserted",
                "source_quote": text,
            }
            for i, text in enumerate(FACTS)
        ]
    }
    return [route, plan, review, speaker, speaker]


def test_event_enabled_contract_supports_variable_groups_without_changing_legacy():
    base, _ = capability_route_contract(enable_events=False)
    enabled, prompt = capability_route_contract(enable_events=True)
    assert "self_relation_spans" not in base["properties"]
    assert "self_relation_spans" in enabled["required"]
    assert enabled["properties"]["self_relation_spans"]["items"]["type"] == "string"
    assert enabled["additionalProperties"] is False
    assert "already-completed shared experiences" in prompt
    assert "Events requires an actual scheduled/upcoming occurrence" in prompt
    assert "minimal, exact contiguous reference phrase" in prompt
    assert (
        "one described entity or a finite source-attested group of any canonical Note type"
        in prompt
    )
    assert "split them into their individual phrases" in prompt
    assert "MUST be null" in prompt
    assert "historical memory" in prompt


def test_current_router_core_writes_two_day_facts_with_all_verified_relations(tmp_path):
    repo, actor, service, runtime = _family(tmp_path)
    service.client = RecordedClient(_model_responses())
    result = runtime.execute_product(SOURCE, "issue157-recollection", "main", actor)
    assert result["status"] == "completed", result
    assert service.client.calls[0] == "odyssey_light_capability_route_events_v1"
    notes = [parse_note(repo.read_text(path)) for path in repo.list_markdown_paths()]
    days = [note for note in notes if note.metadata["id"] == f"date:{DAY}"]
    assert len(days) == 1
    body = days[0].content
    assert body.count("odyssey:fact request=issue157-recollection-") == 2
    assert "jardín" in body and "museo" in body
    assert all("[[" + name in body for name in PEOPLE)
    assert len([note for note in notes if note.metadata["type"] == "person"]) == 4
    current = {path: repo.read_text(path) for path in repo.list_markdown_paths()}
    replay = runtime.execute_product(SOURCE, "issue157-recollection", "main", actor)
    assert replay["delivery_replayed"] is True
    assert {path: repo.read_text(path) for path in repo.list_markdown_paths()} == current


@pytest.mark.parametrize(
    "case", ["missing_verified_partner", "unattested_relation", "duplicate_group", "excess_groups"]
)
def test_multiple_relation_proofs_fail_closed_without_any_write(tmp_path, case):
    repo, actor, service, runtime = _family(
        tmp_path, include_partner=case != "missing_verified_partner"
    )
    rows = _model_responses()
    if case == "unattested_relation":
        rows[0]["self_relation_spans"] = ["mis hijos", "mis amigos"]
    if case == "duplicate_group":
        rows[0]["self_relation_spans"] = ["mis hijos", "mis hijos"]
    if case == "excess_groups":
        rows[0]["self_relation_spans"] = ["mis hijos"] * 9
    service.client = RecordedClient(rows if case == "missing_verified_partner" else rows[:1])
    before = {path: repo.read_text(path) for path in repo.list_markdown_paths()}
    result = runtime.execute_product(SOURCE, f"issue157-{case}", "main", actor)
    assert result["status"] == "needs_attention"
    assert {path: repo.read_text(path) for path in repo.list_markdown_paths()} == before


def test_verified_and_unverified_mentions_can_share_one_literal_day(tmp_path):
    """Partial optional evidence is not an all-or-nothing write dependency."""
    repo, actor, service, runtime = _family(tmp_path, include_partner=False)
    rows = _model_responses()
    for row in rows[1]["facts"]:
        row["participants"] = []
    for item, original in zip(rows[2]["facts"], FACTS, strict=True):
        item["reviewed_text"] = original
        item["reference_names"] = []
    service.client = RecordedClient(rows)
    result = runtime.execute_product(SOURCE, "partial-hint-literal", "main", actor)
    assert result["status"] == "completed", result
    days = [
        parse_note(repo.read_text(p))
        for p in repo.list_markdown_paths()
        if parse_note(repo.read_text(p)).metadata.get("type") == "calendar_day"
    ]
    assert len(days) == 1
    assert "mis hijos" in days[0].content and "mi pareja" in days[0].content
    assert "[[Nora" not in days[0].content
    assert "[[Ivo" not in days[0].content
    assert "[[Vera" not in days[0].content


def test_stale_second_relationship_abstains_before_any_physical_write(tmp_path):
    """Changing any confirmed SELF group during GPT review invalidates all."""
    repo, actor, service, runtime = _family(tmp_path)
    client = RecordedClient(_model_responses())
    original = client.create

    def remove_partner_after_source_review(**kwargs):
        result = original(**kwargs)
        if kwargs["text"]["format"]["name"] == "odyssey_speaker_full_B":
            note = parse_note(repo.read_text("self.md"))
            body = render_atomic_facts(
                ("Mis hijos son [[Nora]] y [[Ivo]].",), "self-relations", (0,), DAY
            )
            repo.replace_text("self.md", serialize_note(replace(note, content=body)))
        return result

    client.create = remove_partner_after_source_review
    service.client = client
    outcome = runtime.execute_product(SOURCE, "issue157-stale-partner", "main", actor)
    assert outcome["status"] == "needs_attention", outcome
    assert not any(
        "odyssey:fact request=issue157-stale-partner" in repo.read_text(path)
        for path in repo.list_markdown_paths()
    )


def test_overlapping_relation_phrases_in_one_indivisible_fact_do_not_cross_assign_people(
    tmp_path,
):
    repo, actor, service, runtime = _family(tmp_path)
    prior = parse_note(repo.read_text("self.md"))
    mixed = render_atomic_facts(
        ("Mis hijos y mi pareja son [[Nora]], [[Ivo]] y [[Vera]].",),
        "self-relations",
        (0,),
        DAY,
    )
    repo.replace_text("self.md", serialize_note(replace(prior, content=mixed)))
    service.context_index.rebuild(repo, SCHEMA, service.embedder)
    service.semantic_index.rebuild(repo, SCHEMA, service.embedder)
    service.client = RecordedClient(_model_responses()[:1])
    before = {path: repo.read_text(path) for path in repo.list_markdown_paths()}
    outcome = runtime.execute_product(SOURCE, "issue157-overlapping-groups", "main", actor)
    assert outcome["status"] == "needs_attention"
    assert {path: repo.read_text(path) for path in repo.list_markdown_paths()} == before


def test_event_only_route_cannot_bypass_unverified_group_as_event(tmp_path):
    repo, actor, service, runtime = _family(tmp_path, include_partner=False)
    # One genuine future appointment may be handed to Events, but a Router
    # reply which simultaneously claims an ungrounded participant set cannot.
    service.client = RecordedClient(
        [
            {
                "capabilities": ["events", "temporal"],
                "interpretation": "joint",
                "reason": "single",
                "app_scopes": [],
                "self_relation_span": None,
                "self_relation_spans": ["mis hijos", "mi pareja"],
            }
        ]
    )
    before = {path: repo.read_text(path) for path in repo.list_markdown_paths()}
    outcome = runtime.execute_product(SOURCE, "issue157-unsafe-events", "main", actor)
    assert outcome["status"] == "needs_attention"
    assert {path: repo.read_text(path) for path in repo.list_markdown_paths()} == before


def test_router_must_not_invent_family_names_when_relation_evidence_is_absent(tmp_path):
    repo, actor, service, runtime = _family(tmp_path)
    replies = _model_responses()
    replies[0]["self_relation_spans"] = []
    replies[0]["self_relation_span"] = None
    service.client = RecordedClient(replies)
    before = {path: repo.read_text(path) for path in repo.list_markdown_paths()}
    outcome = runtime.execute_product(SOURCE, "issue157-no-relations", "main", actor)
    assert outcome["status"] == "needs_attention", outcome
    assert {path: repo.read_text(path) for path in repo.list_markdown_paths()} == before


def test_saved_real_gpt_router_v2_does_real_core_e3_day_and_family_readback(tmp_path, monkeypatch):
    """Real GPT ROUTER reply; remaining model phases frozen, E3/Markdown real."""
    import json
    import sys
    from pathlib import Path

    receipt = json.loads(
        (
            Path(__file__).resolve().parents[2]
            / "tests/fixtures/issue157_recorded_live_router_v2.json"
        ).read_text()
    )
    assert receipt["production_model"] == "gpt-6-luna"
    assert receipt["observed_source_sha"] == "fb137fabc80056fe827af7c2255cf2acdaed5b75"
    source = receipt["source"]
    route = receipt["recorded_immutable_router_output"]
    assert route["self_relation_spans"] == ["mis hijos", "mi pareja"]
    # Reuse the existing model-independent Core test harness without changing
    # its global source constants beyond this temporary isolated test.
    module = sys.modules[__name__]
    monkeypatch.setattr(module, "SOURCE", source)
    monkeypatch.setattr(
        module,
        "FACTS",
        (
            "Hoy hemos ido al jardín con mis hijos y mi pareja.",
            "Después hemos visitado el museo.",
        ),
    )
    repo, actor, service, runtime = _family(tmp_path)
    _suggested_router, *remaining_model_fakes = _model_responses()
    service.client = RecordedClient([route, *remaining_model_fakes])
    response = runtime.execute_product(source, "issue157-live-router-readback", "main", actor)
    assert response["status"] == "completed", response
    day = parse_note(repo.read_text(f"calendar/days/{DAY}.md"))
    assert day.content.count("odyssey:fact request=issue157-live-router-readback-") == 2
    assert all(f"[[{name}" in day.content for name in PEOPLE)
    assert "jardín" in day.content and "museo" in day.content
    before = {path: repo.read_text(path) for path in repo.list_markdown_paths()}
    assert runtime.execute_product(source, "issue157-live-router-readback", "main", actor)[
        "delivery_replayed"
    ]
    assert {path: repo.read_text(path) for path in repo.list_markdown_paths()} == before


def test_future_event_with_verified_partner_reaches_event_delegate_and_replays(tmp_path):
    """A valid scheduled Event must not be rejected for a proven relationship."""
    repo, actor, service, runtime = _family(tmp_path)
    source = "Mañana tengo una cita con mi pareja."
    routed = {
        "capabilities": ["events", "temporal"],
        "interpretation": "joint",
        "reason": "single",
        "app_scopes": [],
        "self_relation_span": "mi pareja",
        "self_relation_spans": ["mi pareja"],
    }
    received = []

    def event_delegate(original, delivery, identity):
        received.append((original, delivery, identity))
        return ApplicationResult(delivery, ApplicationStatus.COMPLETED, (), ())

    service.event_delegate = event_delegate
    service.client = RecordedClient([routed])
    result = runtime.execute_product(source, "issue157-verified-future-event", "main", actor)
    assert result["status"] == "completed", result
    assert len(received) == 1 and received[0] == (source, "issue157-verified-future-event", actor)
    assert result["execution_flow"]["routes"][0]["capability"] == "events"
    assert runtime.execute_product(source, "issue157-verified-future-event", "main", actor)[
        "delivery_replayed"
    ]
    assert len(received) == 1
    assert len([p for p in repo.list_markdown_paths() if "calendar/days/" in p]) == 0


def test_unknown_partner_in_future_event_is_not_delegated(tmp_path):
    """A Router's claimed relationship cannot substitute for SELF evidence."""
    repo, actor, service, runtime = _family(tmp_path, include_partner=False)
    source = "Mañana tengo una cita con mi pareja."
    route = {
        "capabilities": ["events", "temporal"],
        "interpretation": "joint",
        "reason": "single",
        "app_scopes": [],
        "self_relation_span": "mi pareja",
        "self_relation_spans": ["mi pareja"],
    }
    service.client = RecordedClient([route])
    before = {p: repo.read_text(p) for p in repo.list_markdown_paths()}
    result = runtime.execute_product(source, "issue157-unknown-future-partner", "main", actor)
    assert result["status"] == "needs_attention"
    assert before == {p: repo.read_text(p) for p in repo.list_markdown_paths()}


def test_repeated_relationship_phrase_in_two_facts_persists_and_replays(tmp_path):
    """A repeated source occurrence is not an invented model duplicate."""
    repo, actor, service, runtime = _family(tmp_path)
    first = "Hoy mis hijos visitaron un jardín."
    second = "Después mis hijos visitaron un museo."
    source = first + " " + second
    replies = _model_responses()
    replies[0]["self_relation_spans"] = ["mis hijos", "mis hijos"]
    for index, statement in enumerate((first, second)):
        replies[1]["facts"][index].update(
            meaning=statement, source_evidence=statement, participants=list(PEOPLE[:2])
        )
        replies[2]["facts"][index].update(
            source_quote=statement,
            reviewed_text="{{ref:0}} y {{ref:1}} visitaron un lugar.",
            reference_names=list(PEOPLE[:2]),
        )
        for speaker in replies[3:]:
            speaker["facts"][index]["source_quote"] = statement
    service.client = RecordedClient(replies)
    result = runtime.execute_product(source, "issue157-repeated-group", "main", actor)
    assert result["status"] == "completed", result
    day_notes = [
        parse_note(repo.read_text(path))
        for path in repo.list_markdown_paths()
        if parse_note(repo.read_text(path)).metadata.get("type") == "calendar_day"
    ]
    assert len(day_notes) == 1
    body = day_notes[0].content
    assert body.count("odyssey:fact request=issue157-repeated-group-") == 2
    assert all("[[" + name in body for name in PEOPLE[:2])
    before = {path: repo.read_text(path) for path in repo.list_markdown_paths()}
    assert runtime.execute_product(source, "issue157-repeated-group", "main", actor)[
        "delivery_replayed"
    ]
    assert before == {path: repo.read_text(path) for path in repo.list_markdown_paths()}


def test_router_scalar_claim_cannot_disagree_with_multiple_verified_groups(tmp_path):
    repo, actor, service, runtime = _family(tmp_path)
    rows = _model_responses()
    rows[0]["self_relation_span"] = "mis hijos"
    service.client = RecordedClient(rows[:1])
    before = {path: repo.read_text(path) for path in repo.list_markdown_paths()}
    outcome = runtime.execute_product(SOURCE, "issue157-scalar-mismatch", "main", actor)
    assert outcome["status"] == "needs_attention"
    assert before == {path: repo.read_text(path) for path in repo.list_markdown_paths()}


@pytest.mark.parametrize(
    "relation_explicit", [False, True], ids=["unverified_refused", "verified_trip_saved"]
)
def test_additional_family_trip_source_preserves_both_places_and_three_people(
    tmp_path, relation_explicit
):
    """R29: the user's exact multi-place visit, with recorded AI and real Core/E3."""
    from copy import deepcopy

    from scripts.odyssey_r0_browser_campaign import additional_cases

    source = next(x.source for x in additional_cases() if x.id == "R29")
    parts = source.split(" Hemos visto ")
    assert len(parts) == 2
    factual = (parts[0], "Hemos visto " + parts[1])
    rows = deepcopy(_model_responses())
    rows[0]["self_relation_spans"] = ["mis hijos", "mi mujer"]
    rows[1]["facts"] = [
        {
            **rows[1]["facts"][i],
            "meaning": part,
            "source_evidence": part,
            "participants": list(PEOPLE) if i == 0 else [],
        }
        for i, part in enumerate(factual)
    ]
    rows[2]["facts"] = [
        {
            **rows[2]["facts"][i],
            "source_quote": part,
            "reviewed_text": (
                part.replace("mis hijos y mi mujer", "{{ref:0}}, {{ref:1}} y {{ref:2}}")
                if i == 0
                else part
            ),
            "reference_names": list(PEOPLE) if i == 0 else [],
        }
        for i, part in enumerate(factual)
    ]
    for speaker in rows[3:]:
        speaker["facts"] = [
            {**speaker["facts"][i], "source_quote": part} for i, part in enumerate(factual)
        ]
    repo, actor, executor, runtime = _family(tmp_path)
    # Only explicitly verified relationships may supply canonical identities.
    # This is test data, not a product-level string-to-person routing rule.
    if relation_explicit:
        my_note = parse_note(repo.read_text("self.md"))
        assert "Mi pareja es" in my_note.content
        repo.replace_text(
            "self.md",
            serialize_note(
                replace(my_note, content=my_note.content.replace("Mi pareja es", "Mi mujer es"))
            ),
        )
        executor.context_index.rebuild(repo, SCHEMA, executor.embedder)
        executor.semantic_index.rebuild(repo, SCHEMA, executor.embedder)
    executor.client = RecordedClient(rows)
    before = {path: repo.read_text(path) for path in repo.list_markdown_paths()}
    result = runtime.execute_product(source, "r29-multiplace-1", "main", actor)
    if not relation_explicit:
        assert result["status"] == "needs_attention", result
        assert {path: repo.read_text(path) for path in repo.list_markdown_paths()} == before
        return
    assert result["status"] == "completed", result
    note = parse_note(repo.read_text(f"calendar/days/{DAY}.md"))
    assert all(name in note.content for name in ("Notre Dame", "Louvre", "Paris"))
    assert all("[[" + name in note.content for name in PEOPLE)
    assert note.content.count("odyssey:fact request=r29-multiplace-1") == 2
    snap = {p: repo.read_text(p) for p in repo.list_markdown_paths()}
    assert runtime.execute_product(source, "r29-multiplace-1", "main", actor)["delivery_replayed"]
    assert snap == {p: repo.read_text(p) for p in repo.list_markdown_paths()}
