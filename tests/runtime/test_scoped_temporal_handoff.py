"""Cross-fragment Temporal proof, no invented sibling request or untrusted date."""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest

from odyssey_apps.fact_candidates import validate_fact_candidate_proposal
from odyssey_core.domain_interpretation import DomainInterpretation, InheritedTemporalReference
from odyssey_core.request_planning import PlannerClarification
from odyssey_runtime.candidate_route_dispatch import execute_candidate_routed_message
from odyssey_runtime.scoped_temporal_handoff import ScopedTemporalHandoff
from tests.apps.test_fact_candidates import CASES
from tests.benchmarks.test_recorded_real_models_source_replay import _saved_router_outputs
from tests.runtime.test_candidate_pending_state import NOW
from tests.runtime.test_candidate_route_dispatch_e2e import (
    _review_one_real_core_fact,
    _source_temporal,
)
from tests.runtime.test_fact_candidate_semantic_luna_vertical import SCHEMA
from tests.runtime.test_full_message_corpus_regression import fresh_corpus_vault
from tests.runtime.test_temporal_user_path_e2e import _day_plan, _linked_day_plan

SOURCE = next(x["source"] for x in CASES if x["id"] == "F06")
SAVED = _saved_router_outputs()["F06"]


class Router:
    def propose(self, source):
        assert source == SOURCE
        return validate_fact_candidate_proposal(source, SAVED)


@pytest.mark.parametrize("first_writes", [False, True])
def test_core_receives_verified_temporal_from_prior_fragment_and_writes_day(tmp_path, first_writes):
    repo, ctx, semantic, embedder = fresh_corpus_vault(tmp_path)
    temporal_calls = []
    core_calls = []

    class Temporal:
        def interpret(self, source):
            temporal_calls.append(source)
            assert source == "Hoy vi a Ana"
            return _source_temporal(source)

    def core_factory(context, domain):
        def plan(source):
            assert source == context.source
            core_calls.append((source, domain))
            if source == "Hoy vi a Ana":
                assert domain is not None and not domain.inherited_temporal
                return (
                    _linked_day_plan("2026-10-04", "Vi a {{ref:0}}.", "Ana", "2026-10-04")
                    if first_writes
                    else PlannerClarification("UNREPRESENTABLE_REQUEST")
                )
            assert source == " y compré pan."
            assert domain is not None
            assert not domain.evidence
            assert len(domain.inherited_temporal) == 1
            inherited = domain.inherited_temporal[0]
            assert (inherited.source_text, inherited.value, inherited.origin_route_index) == (
                "Hoy",
                "2026-10-04",
                0,
            )
            assert [(proof.source_text, proof.value) for proof in domain.temporal_references()] == [
                ("Hoy", "2026-10-04")
            ]
            assert "Hoy" not in source
            return _day_plan("2026-10-04", "Compré pan.", "2026-10-04")

        return SimpleNamespace(plan=plan)

    result = execute_candidate_routed_message(
        SOURCE,
        router=Router(),
        temporal=Temporal(),
        core_planner_factory=core_factory,
        candidate_coverage_factory=_review_one_real_core_fact,
        repository=repo,
        schema=SCHEMA,
        context_index=ctx,
        semantic_index=semantic,
        embedder=embedder,
        contextual_reasoner=object(),
        actor="synthetic-temporal-handoff",
        now=NOW,
        context_limit=5,
        request_id_factory=lambda: "f06-temporal-handoff-e2e",
    )
    assert temporal_calls == ["Hoy vi a Ana"]
    assert [source for source, _ in core_calls] == ["Hoy vi a Ana", " y compré pan."]
    assert [item["status"] for item in result.execution_flow["routes"]] == [
        "completed" if first_writes else "needs_attention",
        "completed",
    ]
    texts = "\n".join(repo.read_text(path) for path in repo.list_markdown_paths())
    assert "Compré pan." in texts
    if first_writes:
        assert "Vi a [[Ana|Ana]]." in texts


def test_inherited_date_needs_actual_predecessor_temporal_result():
    from odyssey_runtime.candidate_route_dispatch import compile_candidate_route_bundle

    compiled = compile_candidate_route_bundle(validate_fact_candidate_proposal(SOURCE, SAVED))
    second = compiled.units[1]
    handoff = ScopedTemporalHandoff(SOURCE)
    assert (
        handoff.inherited(
            second.context,
            current_route_index=1,
            start=second.original_start,
            end=second.original_end,
        )
        == ()
    )


def test_temporal_handoff_rejects_false_provenance_and_forward_reference():
    from odyssey_runtime.candidate_route_dispatch import compile_candidate_route_bundle

    compiled = compile_candidate_route_bundle(validate_fact_candidate_proposal(SOURCE, SAVED))
    first, second = compiled.units
    handoff = ScopedTemporalHandoff(SOURCE)
    handoff.remember(
        _source_temporal(first.context.source),
        route_index=0,
        start=first.original_start,
        end=first.original_end,
    )
    valid = handoff.inherited(
        second.context,
        current_route_index=1,
        start=second.original_start,
        end=second.original_end,
    )
    assert len(valid) == 1

    bad = replace(valid[0], original_sha256="0" * 64)
    assert bad != valid[0]
    tampered = replace(
        second.context,
        source_provenance=(replace(second.context.source_provenance[0], original_sha256="f" * 64),),
    )
    with pytest.raises(ValueError, match="forged"):
        handoff.inherited(
            tampered,
            current_route_index=1,
            start=second.original_start,
            end=second.original_end,
        )
    with pytest.raises(ValueError, match="earlier route"):
        handoff.inherited(
            second.context,
            current_route_index=0,
            start=second.original_start,
            end=second.original_end,
        )
    with pytest.raises(ValueError, match="original route"):
        handoff.remember(
            _source_temporal(first.context.source),
            route_index=0,
            start=second.original_start,
            end=second.original_end,
        )


def test_nonlocal_temporal_source_is_rejected_without_typed_proof():
    from odyssey_core.domain_interpretation import DomainEvidence

    with pytest.raises(ValueError, match="not grounded"):
        DomainInterpretation(
            "temporal",
            " y compré pan.",
            "TEMPORAL_RESOLUTION",
            (DomainEvidence("temporal_reference", "Hoy", "2026-10-04"),),
        )
    with pytest.raises(ValueError, match="invalid"):
        InheritedTemporalReference("Hoy", "not-a-date", 0, 3, "0" * 64, 0)


def test_missing_predecessor_temporal_blocks_inherited_date_before_core(tmp_path):
    from odyssey_core.temporal_interpretation import TemporalInterpreterError

    repo, ctx, semantic, embedder = fresh_corpus_vault(tmp_path)
    planner_inputs = []

    class Temporal:
        def interpret(self, source):
            assert source == "Hoy vi a Ana"
            raise TemporalInterpreterError("No verified Temporal output")

    def core_factory(context, domain):
        def plan(source):
            planner_inputs.append(source)
            return _day_plan("2026-10-04", "Unverified date.", "2026-10-04")

        return SimpleNamespace(plan=plan)

    result = execute_candidate_routed_message(
        SOURCE,
        router=Router(),
        temporal=Temporal(),
        core_planner_factory=core_factory,
        candidate_coverage_factory=_review_one_real_core_fact,
        repository=repo,
        schema=SCHEMA,
        context_index=ctx,
        semantic_index=semantic,
        embedder=embedder,
        contextual_reasoner=object(),
        actor="no-temporal-proof-test",
        now=NOW,
        context_limit=5,
        request_id_factory=lambda: "missing-date-negative",
    )
    assert planner_inputs == []
    assert result.status.value == "failed"
    assert all(
        "odyssey:fact request=" not in repo.read_text(path) for path in repo.list_markdown_paths()
    )


def test_inherited_temporal_prompt_is_scoped_and_does_not_change_plain_prompts():
    from odyssey_core.experimental_luna_planning import render_luna_experimental_prompt
    from tests.runtime.test_fact_candidate_semantic_luna_vertical import CLOCK

    context = " y compré pan."
    reference = InheritedTemporalReference(
        "Hoy", "2026-10-04", 0, 3, __import__("hashlib").sha256(SOURCE.encode()).hexdigest(), 0
    )
    domain = DomainInterpretation("temporal", context, "TEMPORAL_RESOLUTION", (), (reference,))
    prompt = render_luna_experimental_prompt(SCHEMA, CLOCK, domain_interpretation=domain)
    assert "inherited_temporal" in prompt
    assert '"source_text":"Hoy"' in prompt
    assert "2026-10-04" in prompt
    assert "Hoy vi a Ana y compré pan." not in prompt
    plain = render_luna_experimental_prompt(SCHEMA, CLOCK)
    assert "inherited_temporal" not in plain


def _datetime_mention(word, value):
    return {
        "temporal_text": word,
        "temporal": {
            "kind": "EXACT_DATETIME",
            "exact_date": None,
            "exact_datetime": value,
            "range_start": None,
            "range_end_exclusive": None,
        },
    }


def test_prior_date_is_transmitted_to_temporal_for_second_local_clock(tmp_path):
    from odyssey_core.temporal_interpretation import parse_temporal_interpretation
    from tests.runtime.test_fact_candidate_planning_vertical import _exact_date

    case = next(row for row in CASES if row["id"] == "F04")
    repo, ctx, semantic, embedder = fresh_corpus_vault(tmp_path)
    temporal_calls = []
    core_calls = []

    class Router04:
        def propose(self, source):
            assert source == case["source"]
            return validate_fact_candidate_proposal(source, _saved_router_outputs()["F04"])

    class Temporal:
        def interpret(self, source, *, inherited_temporal=()):
            temporal_calls.append((source, inherited_temporal))
            if "Mañana" in source:
                assert not inherited_temporal
                return parse_temporal_interpretation(
                    {
                        "mentions": [
                            _exact_date("Mañana", "2026-10-05"),
                            _datetime_mention("a las 12", "2026-10-05T12:00:00+02:00"),
                        ]
                    },
                    source,
                    timezone="Europe/Paris",
                )
            assert [(x.source_text, x.value) for x in inherited_temporal] == [
                ("Mañana", "2026-10-05")
            ]
            return parse_temporal_interpretation(
                {"mentions": [_datetime_mention("a las 18", "2026-10-05T18:00:00+02:00")]},
                source,
                timezone="Europe/Paris",
            )

    def core_factory(context, domain):
        def plan(source):
            core_calls.append((source, domain))
            assert domain is not None
            assert source == context.source and source != case["source"]
            return PlannerClarification("UNREPRESENTABLE_REQUEST")

        return SimpleNamespace(plan=plan)

    execute_candidate_routed_message(
        case["source"],
        router=Router04(),
        temporal=Temporal(),
        core_planner_factory=core_factory,
        candidate_coverage_factory=_review_one_real_core_fact,
        repository=repo,
        schema=SCHEMA,
        context_index=ctx,
        semantic_index=semantic,
        embedder=embedder,
        contextual_reasoner=object(),
        actor="test-inherited-temporal-clock",
        now=NOW,
        context_limit=5,
        request_id_factory=lambda: "f04-temporal-to-temporal",
    )
    assert len(temporal_calls) == len(core_calls) == 2
    assert temporal_calls[1][0] == " y luego a las 18 iremos al cine."
    second_domain = core_calls[1][1]
    assert second_domain.inherited_temporal[0].value == "2026-10-05"
    assert [(item.source_text, item.value) for item in second_domain.temporal_references()] == [
        ("a las 18", "2026-10-05T18:00:00+02:00"),
        ("Mañana", "2026-10-05"),
    ]


def test_temporal_provider_cannot_contradict_exact_inherited_day():
    import json

    from odyssey_core.temporal_interpretation import (
        OpenAITemporalInterpreter,
        TemporalInterpreterError,
    )
    from tests.runtime.test_fact_candidate_semantic_luna_vertical import CLOCK

    recorded_calls = []

    class Responses:
        def create(self, **kwargs):
            recorded_calls.append(kwargs)
            return SimpleNamespace(
                status="completed",
                output_text=json.dumps(
                    {"mentions": [_datetime_mention("a las 18", "2026-10-06T18:00:00+02:00")]}
                ),
                usage=None,
                id="fake-inherited-time",
            )

    reference = InheritedTemporalReference(
        "Mañana",
        "2026-10-05",
        0,
        6,
        __import__("hashlib").sha256("Mañana iremos".encode()).hexdigest(),
        0,
    )
    interpreter = OpenAITemporalInterpreter(
        SimpleNamespace(responses=Responses()),
        CLOCK,
        max_output_tokens=1536,
        scoped_date_time_context=True,
    )
    with pytest.raises(TemporalInterpreterError, match="disagrees"):
        interpreter.interpret(" y a las 18 iremos al cine.", inherited_temporal=(reference,))
    assert len(recorded_calls) == 1
    assert recorded_calls[0]["max_output_tokens"] == 1536
    assert recorded_calls[0]["input"][1]["content"] == " y a las 18 iremos al cine."
    assert "Verified preceding route Temporal results" in recorded_calls[0]["input"][0]["content"]
    assert "Scoped date/time composition" in recorded_calls[0]["input"][0]["content"]
    assert "2026-10-05" in recorded_calls[0]["input"][0]["content"]
