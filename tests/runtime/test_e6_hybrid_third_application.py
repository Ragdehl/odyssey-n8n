"""E6.3: third scoped application traverses the real hybrid compiler and runtime.

This is a synthetic non-writing Projects-like fixture using the EXISTING
source-only 'plan' candidate kind. It does not activate a new provider schema
or a real Projects domain.
"""

from functools import partial
from types import SimpleNamespace

import pytest

from odyssey_apps.catalog import ApplicationDescriptor
from odyssey_apps.fact_candidates import FactCandidate, FactCandidateProposal, SourceAnchor
from odyssey_apps.router import RouterError
from odyssey_core.application import ApplicationResult, ApplicationStatus
from odyssey_runtime.candidate_route_dispatch import execute_candidate_routed_message
from odyssey_runtime.hybrid_group_compiler import compile_hybrid_candidate_bundle
from odyssey_runtime.registered_scoped_app import RegisteredScopedApp, registered_app_index
from tests.runtime.test_candidate_pending_state import NOW
from tests.runtime.test_fact_candidate_semantic_luna_vertical import SCHEMA
from tests.runtime.test_full_message_corpus_regression import fresh_corpus_vault

SOURCE = "Planificar el proyecto experimental Alpha."
DESCRIPTOR = ApplicationDescriptor("projects", "synthetic plan classification", ("core",))


def _proposal(source=SOURCE):
    return FactCandidateProposal(
        source,
        (
            FactCandidate(
                "candidate-1",
                "plan",
                (SourceAnchor(source, 0, 0, len(source)),),
                (),
                (),
                "candidate",
            ),
        ),
    )


def _app(execute=None):
    def fake(source, locator, actor, history):
        return ApplicationResult(locator, ApplicationStatus.COMPLETED, (), ())

    return RegisteredScopedApp(DESCRIPTOR, "plan", execute or fake)


def _call(
    tmp_path,
    app,
    *,
    compiled_apps=None,
    bound_apps=None,
    proposal=None,
    actor="synthetic-application",
):
    repo, ctx, semantic, embedder = fresh_corpus_vault(tmp_path)
    original = {p: repo.read_text(p) for p in repo.list_markdown_paths()}
    seen = []
    obj = proposal or _proposal()

    def absent_core(*args, **kwargs):
        pytest.fail("Unregistered App must never fall back to Core to write")

    result = execute_candidate_routed_message(
        obj.source,
        router=SimpleNamespace(propose=lambda _: obj),
        temporal=None,
        core_planner_factory=absent_core,
        candidate_coverage_factory=absent_core,
        repository=repo,
        schema=SCHEMA,
        context_index=ctx,
        semantic_index=semantic,
        embedder=embedder,
        contextual_reasoner=object(),
        actor=actor,
        now=NOW,
        context_limit=5,
        request_id_factory=lambda: "e6-project-synthetic",
        bundle_compiler=partial(
            compile_hybrid_candidate_bundle,
            registered_apps=compiled_apps if compiled_apps is not None else (app,),
        ),
        registered_scoped_apps=bound_apps if bound_apps is not None else (app,),
    )
    assert {p: repo.read_text(p) for p in repo.list_markdown_paths()} == original
    return result, seen


def test_third_registered_app_routes_through_real_hybrid_without_a_core_writer(tmp_path):
    seen = []

    def execution(source, locator, actor, history):
        seen.append((source, actor, history))
        return ApplicationResult(locator, ApplicationStatus.COMPLETED, (), ())

    app = _app(execution)
    proposal = _proposal()
    ordinary = compile_hybrid_candidate_bundle(proposal)
    hybrid = compile_hybrid_candidate_bundle(proposal, registered_apps=(app,))
    assert [x.capability_id for x in ordinary.plan.routes] == ["core"]
    assert [x.capability_id for x in hybrid.plan.routes] == ["projects"]
    assert [u.context.source for u in hybrid.units] == [SOURCE]
    result, _ = _call(tmp_path, app)
    assert result.status == ApplicationStatus.COMPLETED
    assert seen == [(SOURCE, None, ())]


def test_routed_third_app_must_also_be_explicitly_bound_before_execution(tmp_path):
    app = _app()
    with pytest.raises(RouterError):
        _call(tmp_path, app, bound_apps=())


@pytest.mark.parametrize("kind", ("event", "task", "nonsense"))
def test_extra_app_cannot_claim_reserved_or_unknown_candidate_kind(kind):
    with pytest.raises(ValueError):
        RegisteredScopedApp(DESCRIPTOR, kind, lambda *args: None)


def test_extra_app_rejects_ambiguous_or_duplicate_route_ownership():
    app = _app()
    with pytest.raises(ValueError):
        registered_app_index((app, app))
    another = RegisteredScopedApp(
        ApplicationDescriptor("other", "another synthetic application"),
        "plan",
        lambda *args: None,
    )
    with pytest.raises(ValueError):
        registered_app_index((app, another))


def test_wrong_candidate_kind_cannot_route_to_registered_app(tmp_path):
    app = _app()
    source = "Dejé una nota sobre un hecho."
    proposal = FactCandidateProposal(
        source,
        (
            FactCandidate(
                "candidate-1",
                "occurrence",
                (SourceAnchor(source, 0, 0, len(source)),),
                (),
                (),
                "candidate",
            ),
        ),
    )
    result = compile_hybrid_candidate_bundle(proposal, registered_apps=(app,))
    assert result.plan.routes[0].capability_id == "core"


def test_ambiguous_registered_app_source_fails_closed_instead_of_core_fallback():
    app = _app()
    source = SOURCE
    proposal = FactCandidateProposal(
        source,
        (
            FactCandidate(
                "candidate-1",
                "plan",
                (SourceAnchor(source, 0, 0, len(source)),),
                (),
                (),
                "ambiguous_identity",
            ),
        ),
    )
    with pytest.raises(RouterError, match="independent authorized source group"):
        compile_hybrid_candidate_bundle(proposal, registered_apps=(app,))


def test_mixed_core_and_registered_app_group_fails_closed():
    app = _app()
    source = "Planificar experimento compartido"
    proposal = FactCandidateProposal(
        source,
        (
            FactCandidate(
                "candidate-1",
                "plan",
                (SourceAnchor("Planificar", 0, 0, 10),),
                (),
                (),
                "candidate",
            ),
            FactCandidate(
                "candidate-2",
                "occurrence",
                (SourceAnchor("experimento compartido", 0, 11, len(source)),),
                (),
                (),
                "candidate",
            ),
        ),
    )
    with pytest.raises(RouterError, match="independent authorized source group"):
        compile_hybrid_candidate_bundle(proposal, registered_apps=(app,))


def test_dispatcher_refuses_when_compiler_omits_trusted_app_registration(tmp_path):
    """Opposite mismatch: Projects registered in dispatcher but Core compiler."""
    app = _app()
    with pytest.raises(RouterError, match="misrouted by compiler"):
        _call(tmp_path, app, compiled_apps=(), bound_apps=(app,))
