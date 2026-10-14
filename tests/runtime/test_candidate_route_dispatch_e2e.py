"""Route-local v1 Router -> conditional Temporal -> ordinary Core -> Markdown.

The fixture includes real previously captured GPT-6 Router evidence and the
existing canonical synthetic vault; no live models or personal Notes.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from odyssey_apps.fact_candidates import validate_fact_candidate_proposal
from odyssey_core.application import ApplicationStatus
from odyssey_core.candidate_coverage import (
    CoreCandidateCoverageClaim,
    build_candidate_coverage_manifest,
)
from odyssey_core.identity_boundary import AuthenticatedActorContext, SelfBindingRepository
from odyssey_core.notes import parse_note
from odyssey_core.temporal_interpretation import parse_temporal_interpretation
from odyssey_runtime.candidate_route_dispatch import (
    compile_candidate_route_bundle,
    execute_candidate_routed_message,
)
from odyssey_runtime.composition import _persistence_actor
from tests.apps.test_fact_candidates import CASES
from tests.benchmarks.test_recorded_real_models_source_replay import (
    _saved_router_outputs,
)
from tests.core.test_application_history import FakeHistoryRecorder
from tests.runtime.test_candidate_pending_state import NOW
from tests.runtime.test_fact_candidate_semantic_luna_vertical import SCHEMA
from tests.runtime.test_full_message_corpus_regression import fresh_corpus_vault
from tests.runtime.test_temporal_user_path_e2e import _day_plan, _linked_day_plan

USER_A = "11111111-1111-4111-8111-111111111111"
USER_B = "22222222-2222-4222-8222-222222222222"


class RecordedRouter:
    def __init__(self, case_id):
        self.case = next(c for c in CASES if c["id"] == case_id)
        self.payload = _saved_router_outputs()[case_id]
        self.calls = []

    def propose(self, source):
        self.calls.append(source)
        return validate_fact_candidate_proposal(source, self.payload)


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["id"])
def test_saved_real_router_v1_candidates_compile_as_local_routes(case):
    from odyssey_core.candidate_dependencies import CandidateDependencyError

    router = RecordedRouter(case["id"])
    if case["id"] == "F27":
        with pytest.raises(CandidateDependencyError):
            compile_candidate_route_bundle(router.propose(case["source"]))
        return
    bundle = compile_candidate_route_bundle(router.propose(case["source"]))
    assert bundle.original_source == case["source"]
    assert len(bundle.units) == len(bundle.plan.routes)
    assert "".join(route.source_text for route in bundle.plan.routes).strip() == case["source"]
    for item in bundle.units:
        assert item.route.source_text == item.context.source
        assert item.route.source_text == case["source"][item.original_start : item.original_end]
        assert item.context.candidates
        assert all(
            candidate.candidate_id.startswith("candidate-") for candidate in item.context.candidates
        )


@pytest.mark.parametrize("case_id", ["F09", "F10", "F16", "F23", "F25"])
def test_dateless_cases_skip_temporal_entirely(case_id):
    case = next(c for c in CASES if c["id"] == case_id)
    bundle = compile_candidate_route_bundle(RecordedRouter(case_id).propose(case["source"]))
    assert all(route.capability_id == "core" for route in bundle.plan.routes)


def test_eric_routes_are_independent_and_reference_waits_for_core():
    case = next(c for c in CASES if c["id"] == "F13")
    bundle = compile_candidate_route_bundle(RecordedRouter("F13").propose(case["source"]))
    assert len(bundle.plan.routes) == 3
    first, second, third = bundle.plan.routes
    assert "Eric" in first.source_text and "él" not in first.source_text
    assert "él" in second.source_text and "Eric" not in second.source_text
    assert "pan" in third.source_text and "Eric" not in third.source_text
    assert [r.depends_on for r in bundle.plan.routes] == [None, 0, None]
    assert [r.dependent_mention for r in bundle.plan.routes] == [None, "él", None]


def test_shared_residence_and_purchase_keep_single_scoped_core_request():
    for case_id in ("F09", "F11"):
        case = next(c for c in CASES if c["id"] == case_id)
        bundle = compile_candidate_route_bundle(RecordedRouter(case_id).propose(case["source"]))
        assert len(bundle.units) == 1
        assert len(bundle.units[0].context.candidates) == 2


def _source_temporal(text: str):
    from tests.runtime.test_fact_candidate_planning_vertical import _exact_date

    pairs = (("Ayer", "2026-10-03"), ("Mañana", "2026-10-05"), ("Hoy", "2026-10-04"))
    selected = [(w, date) for w, date in pairs if w in text]
    if len(selected) != 1:
        raise AssertionError("Unexpected route date semantics in fixture")
    word, date = selected[0]
    return parse_temporal_interpretation(
        {"mentions": [_exact_date(word, date)]},
        text,
        timezone="Europe/Paris",
    )


def _review_one_real_core_fact(source, context, plan, *, canonical_binding=None):
    assert len(context.candidates) == 1
    return build_candidate_coverage_manifest(
        source,
        context,
        plan,
        (CoreCandidateCoverageClaim("candidate-1", "planned_fact", fact_ordinal=0),),
        canonical_binding=canonical_binding,
    )


@pytest.mark.parametrize("dependent_target", ["Eric", "Luis"])
def test_three_scoped_eric_routes_reach_real_writer_and_link_safely(tmp_path, dependent_target):
    source = next(c for c in CASES if c["id"] == "F13")["source"]
    repo, context_index, semantic_index, embedder = fresh_corpus_vault(tmp_path)
    core_inputs = []
    temporal_inputs = []
    core_domains = []
    history = FakeHistoryRecorder()
    progress: list[str] = []
    state = tmp_path / "state"
    state.mkdir()
    bindings = SelfBindingRepository(state, repo, SCHEMA)
    bindings.bind(USER_A, "fixture-person-alex")
    actor = AuthenticatedActorContext(USER_A)
    prior = ({"role": "assistant", "text": "Previous authenticated turn."},)

    class Temporal:
        def interpret(self, scoped):
            temporal_inputs.append(scoped)
            assert scoped != source
            return _source_temporal(scoped)

    def planner_factory(context, domain):
        core_domains.append(domain)

        def plan(scoped):
            core_inputs.append(scoped)
            assert scoped != source
            if "hablé con Eric" in scoped:
                return _linked_day_plan("2026-10-03", "Hablé con {{ref:0}}.", "Eric", "2026-10-03")
            if "cine con él" in scoped:
                assert any(
                    evidence.kind == "canonical_reference"
                    and evidence.source_text == "él"
                    and evidence.value == "person:Eric"
                    for evidence in domain.evidence
                )
                return _linked_day_plan(
                    "2026-10-05",
                    "Iré al cine con {{ref:0}}.",
                    "él",
                    "2026-10-05",
                    target_name=dependent_target,
                )
            if "compré pan" in scoped:
                return _day_plan("2026-10-04", "Compré pan.", "2026-10-04")
            raise AssertionError(f"Unexpected source {scoped!r}")

        return SimpleNamespace(
            plan=lambda scoped, conversation_context=(): (
                plan(scoped)
                if tuple(conversation_context) == prior
                else (_ for _ in ()).throw(AssertionError("unexpected conversation context"))
            )
        )

    result = execute_candidate_routed_message(
        source,
        router=RecordedRouter("F13"),
        temporal=Temporal(),
        core_planner_factory=planner_factory,
        candidate_coverage_factory=_review_one_real_core_fact,
        repository=repo,
        schema=SCHEMA,
        context_index=context_index,
        semantic_index=semantic_index,
        embedder=embedder,
        contextual_reasoner=object(),
        actor=_persistence_actor("routed-real-core-test", actor),
        now=NOW,
        context_limit=5,
        request_id_factory=lambda: "three-route-eric-v1",
        history_recorder=history,
        progress_callback=lambda stage, _payload: progress.append(stage),
        authenticated_actor=actor,
        self_binding_repository=bindings,
        conversation_context=prior,
    )
    assert progress[:2] == ["routing.started", "routing.ready"]
    assert "temporal.started" in progress
    assert "temporal.ready" in progress
    assert "planner.started" in progress
    assert "planner.ready" in progress
    assert history.begin_calls >= 2
    assert history.record_calls >= 2
    if dependent_target != "Eric":
        assert result.status is ApplicationStatus.PARTIAL
        assert [item["status"] for item in result.execution_flow["routes"]] == [
            "completed",
            "needs_attention",
            "completed",
        ]
        all_notes = "\n".join(repo.read_text(path) for path in repo.list_markdown_paths())
        assert "Hablé con [[Eric|Eric]]." in all_notes
        assert "Compré pan." in all_notes
        assert "Iré al cine" not in all_notes
        return
    assert result.status is ApplicationStatus.COMPLETED, [
        (route["status"], route.get("reason")) for route in result.execution_flow["routes"]
    ]
    assert len(core_inputs) == len(temporal_inputs) == 3
    assert not any(original == source for original in core_inputs + temporal_inputs)
    all_notes = "\n".join(repo.read_text(path) for path in repo.list_markdown_paths())
    assert "Hablé con [[Eric|Eric]]." in all_notes
    assert "Iré al cine con [[Eric|Eric]]." in all_notes
    assert "Compré pan." in all_notes
    day = next(path for path in repo.list_markdown_paths() if path.endswith("2026-10-04.md"))
    assert parse_note(repo.read_text(day)).metadata["created_by"] == {
        "human": USER_A,
        "app": "routed-real-core-test",
    }


def test_hybrid_rejects_forged_authenticated_actor_before_router_or_core(tmp_path):
    """A direct dispatcher caller cannot replace trusted write provenance."""
    repo, context_index, semantic_index, embedder = fresh_corpus_vault(tmp_path)
    actor = AuthenticatedActorContext(USER_A)

    with pytest.raises(ValueError, match="does not match persistence provenance"):
        execute_candidate_routed_message(
            "Hoy encontré una mochila verde mientras ordenaba el armario.",
            router=SimpleNamespace(
                propose=lambda _: (_ for _ in ()).throw(AssertionError("router"))
            ),
            temporal=None,
            core_planner_factory=lambda *_: (_ for _ in ()).throw(AssertionError("planner")),
            candidate_coverage_factory=lambda *_: (_ for _ in ()).throw(AssertionError("coverage")),
            repository=repo,
            schema=SCHEMA,
            context_index=context_index,
            semantic_index=semantic_index,
            embedder=embedder,
            contextual_reasoner=object(),
            actor=_persistence_actor("test", AuthenticatedActorContext(USER_B)),
            now=NOW,
            context_limit=5,
            request_id_factory=lambda: "forged-actor",
            authenticated_actor=actor,
        )
