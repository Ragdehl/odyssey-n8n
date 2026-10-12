"""Conservative hybrid source groups with all original Router candidates preserved.

The five real-model replies are frozen under benchmarks; never contact API
or use real personal Notes. The old atomic compiler stays the default.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from odyssey_core.application import ApplicationStatus
from odyssey_core.candidate_attribution import OpenAICoreCandidateAttributor
from odyssey_core.candidate_dependencies import CandidateDependencyError
from odyssey_core.experimental_luna_planning import OpenAILunaExperimentalPlanner
from odyssey_core.temporal_interpretation import OpenAITemporalInterpreter
from odyssey_runtime.candidate_route_dispatch import execute_candidate_routed_message
from odyssey_runtime.hybrid_group_compiler import compile_hybrid_candidate_bundle
from odyssey_runtime.source_scope_compiler import (
    compile_candidate_route_bundle,
    validate_bundle_original_provenance,
)
from tests.apps.test_fact_candidates import CASES
from tests.runtime.test_candidate_pending_state import NOW
from tests.runtime.test_candidate_route_dispatch_e2e import RecordedRouter
from tests.runtime.test_fact_candidate_semantic_luna_vertical import CLOCK, SCHEMA
from tests.runtime.test_full_message_corpus_regression import ROOT, fresh_corpus_vault
from tests.runtime.test_scoped_route_recorded_real_replay import FrozenProvider

GROUP_COUNTS = {
    "F01": 2,
    "F02": 1,
    "F03": 1,
    "F04": 1,
    "F05": 1,
    "F06": 2,
    "F07": 1,
    "F08": 1,
    "F09": 1,
    "F10": 1,
    "F11": 1,
    "F12": 1,
    "F13": 3,
    "F14": 2,
    "F15": 3,
    "F16": 1,
    "F17": 1,
    "F18": 2,
    "F19": 1,
    "F20": 1,
    "F21": 1,
    "F22": 3,
    "F23": 1,
    "F24": 1,
    "F25": 1,
    "F26": 2,
}


@pytest.mark.parametrize("case", CASES, ids=lambda row: row["id"])
def test_all_real_router_messages_compile_with_lossless_hybrid_source(case):
    router = RecordedRouter(case["id"])
    if case["id"] == "F27":
        with pytest.raises(CandidateDependencyError):
            compile_hybrid_candidate_bundle(router.propose(case["source"]))
        return
    proposal = router.propose(case["source"])
    actual = compile_hybrid_candidate_bundle(proposal)
    strict = compile_candidate_route_bundle(proposal)
    assert actual.original_source == case["source"]
    assert len(actual.units) == GROUP_COUNTS[case["id"]]
    assert len(actual.units) <= len(strict.units)
    assert "".join(route.source_text for route in actual.plan.routes) == case["source"]
    assert tuple(
        candidate for unit in actual.units for candidate in unit.original_candidate_ids
    ) == tuple(f"candidate-{n}" for n in range(1, len(proposal.candidates) + 1))
    assert all(
        len(scoped.context.candidates) == len(scoped.original_candidate_ids)
        for scoped in actual.units
    )
    validate_bundle_original_provenance(actual)


@pytest.mark.parametrize("case_id", ["F03", "F04", "F16", "F21", "F23"])
def test_semantic_dependency_groups_are_single_exact_core_source(case_id):
    case = next(row for row in CASES if row["id"] == case_id)
    bundle = compile_hybrid_candidate_bundle(RecordedRouter(case_id).propose(case["source"]))
    assert len(bundle.units) == 1
    assert bundle.units[0].context.source == case["source"]
    assert len(bundle.units[0].context.candidates) == 2
    assert not bundle.units[0].context.source_provenance
    assert bundle.units[0].route.depends_on is None


@pytest.mark.parametrize(
    "case_id,groups",
    [
        ("F06", 2),
        ("F13", 3),
        ("F14", 2),
        ("F22", 3),
    ],
)
def test_unrelated_or_ambiguous_sources_are_not_merged(case_id, groups):
    case = next(row for row in CASES if row["id"] == case_id)
    bundle = compile_hybrid_candidate_bundle(RecordedRouter(case_id).propose(case["source"]))
    assert len(bundle.units) == groups
    assert all(len(u.context.candidates) == 1 for u in bundle.units)
    if case_id == "F13":
        assert bundle.units[1].route.depends_on == 0
    if case_id == "F14":
        assert bundle.units[1].context.candidates[0].state == "ambiguous_identity"


@pytest.mark.parametrize("case_id", ["F03", "F04", "F16", "F21", "F23"])
def test_five_genuine_model_hybrid_outputs_replay_through_real_core_and_writer(
    case_id: str,
    tmp_path: Path,
):
    """Core receives whole grouped source; each real Note write is audited."""
    case = next(row for row in CASES if row["id"] == case_id)
    frozen = json.loads(
        (ROOT / f"benchmarks/application_router/hybrid_grouped_v1/{case_id}.json").read_text(
            encoding="utf-8"
        )
    )
    assert frozen["source_sha256"] == hashlib.sha256(case["source"].encode()).hexdigest()
    provider = FrozenProvider(frozen["saved_genuine_provider_outputs"])
    repo, context, semantic, embedder = fresh_corpus_vault(tmp_path)
    before = {path: repo.read_text(path) for path in repo.list_markdown_paths()}
    core_sources: list[str] = []

    def planner_factory(hints, domain):
        actual = OpenAILunaExperimentalPlanner(
            provider, SCHEMA, CLOCK, candidate_context=hints, domain_interpretation=domain
        )

        class Observed:
            def plan(self, source):
                core_sources.append(source)
                return actual.plan(source)

            def __getattr__(self, attr):
                return getattr(actual, attr)

        return Observed()

    result = execute_candidate_routed_message(
        case["source"],
        router=RecordedRouter(case_id),
        temporal=OpenAITemporalInterpreter(
            provider,
            CLOCK,
            max_output_tokens=1536,
            scoped_date_time_context=True,
        ),
        core_planner_factory=planner_factory,
        core_candidate_attributor=OpenAICoreCandidateAttributor(provider),
        repository=repo,
        schema=SCHEMA,
        context_index=context,
        semantic_index=semantic,
        embedder=embedder,
        contextual_reasoner=object(),
        actor="hybrid-five-real-replay",
        now=NOW,
        context_limit=5,
        request_id_factory=lambda: f"hybrid-saved-five-{case_id}",
        bundle_compiler=compile_hybrid_candidate_bundle,
    )
    assert len(provider.calls) == len(frozen["saved_genuine_provider_outputs"])
    assert all(text == case["source"] for text in core_sources)
    if case_id in ("F16", "F04"):
        assert result.status is ApplicationStatus.COMPLETED, result.execution_flow
        assert [r["status"] for r in result.execution_flow["routes"]] == ["completed"]
        actual_paths = {
            path
            for path in repo.list_markdown_paths()
            if repo.read_text(path) != before.get(path, "")
        }
        if case_id == "F16":
            assert "Ana.md" in actual_paths and "Luis.md" in actual_paths
            assert "Compró entradas para el concierto." in repo.read_text("Ana.md")
            assert "También compró entradas para el concierto." in repo.read_text("Luis.md")
        else:
            assert any(path.startswith("calendar/days/") for path in actual_paths)
            assert len(actual_paths) >= 2
    else:
        assert result.status is not ApplicationStatus.COMPLETED
        assert all(repo.read_text(p) == v for p, v in before.items())
        assert not [path for path in repo.list_markdown_paths() if path not in before]
        # F21 now composes both dates with their common clock and reaches
        # Core; the original one-response capture contains no Core response.
        assert core_sources == [case["source"]]


@pytest.mark.parametrize("count", [1, 3, 5, 8])
def test_unbounded_semantic_count_does_not_create_false_shared_groups(count: int):
    """One, three, five and eight self-contained actions keep N routes."""
    from odyssey_apps.fact_candidates import (
        FactCandidate,
        FactCandidateProposal,
        SourceAnchor,
    )

    parts = [f"Hice tarea {index}." for index in range(count)]
    source = " ".join(parts)
    candidates = []
    for index in range(count):
        quoted = f"tarea {index}"
        start = source.index(quoted)
        candidates.append(
            FactCandidate(
                f"candidate-{index + 1}",
                "occurrence",
                (SourceAnchor(quoted, 0, start, start + len(quoted)),),
                (),
                (),
                "candidate",
            )
        )
    bundle = compile_hybrid_candidate_bundle(FactCandidateProposal(source, tuple(candidates)))
    assert len(bundle.units) == count
    assert "".join(unit.route.source_text for unit in bundle.units) == source
    assert all(len(item.context.candidates) == 1 for item in bundle.units)


def test_hybrid_context_rejects_wrong_original_span_even_for_shared_group():
    from dataclasses import replace

    from odyssey_apps.router import RouterError
    from odyssey_runtime.source_scope_compiler import validate_bundle_original_provenance

    source = next(c["source"] for c in CASES if c["id"] == "F04")
    bundle = compile_hybrid_candidate_bundle(RecordedRouter("F04").propose(source))
    bad = replace(bundle.units[0], original_start=1)
    with pytest.raises((ValueError, RouterError)):
        validate_bundle_original_provenance(replace(bundle, units=(bad,)))


def test_hybrid_and_atomic_are_distinct_opt_in_modes():
    source = next(c["source"] for c in CASES if c["id"] == "F16")
    proposal = RecordedRouter("F16").propose(source)
    original = compile_candidate_route_bundle(proposal)
    hybrid = compile_hybrid_candidate_bundle(proposal)
    assert len(original.units) == 2
    assert len(hybrid.units) == 1
    assert len(hybrid.units[0].context.candidates) == 2
    assert set(hybrid.units[0].original_candidate_ids) == {"candidate-1", "candidate-2"}


def test_independent_second_fact_survives_failed_first_core_plan(tmp_path: Path):
    """F06: don't merge unrelated actions merely because both happened today."""
    from types import SimpleNamespace

    from odyssey_core.request_planning import PlannerClarification
    from odyssey_core.temporal_interpretation import parse_temporal_interpretation
    from tests.runtime.test_candidate_route_dispatch_e2e import _review_one_real_core_fact
    from tests.runtime.test_fact_candidate_planning_vertical import _exact_date
    from tests.runtime.test_temporal_user_path_e2e import _day_plan

    source = next(row["source"] for row in CASES if row["id"] == "F06")
    repo, context, semantic, embedder = fresh_corpus_vault(tmp_path)
    observed = []

    class Temporal:
        def interpret(self, fragment, **kwargs):
            assert fragment == "Hoy vi a Ana"
            assert not kwargs
            return parse_temporal_interpretation(
                {"mentions": [_exact_date("Hoy", "2026-10-04")]},
                fragment,
                timezone="Europe/Paris",
            )

    def factory(hints, domain):
        def plan(fragment):
            observed.append((fragment, domain))
            if "vi a Ana" in fragment:
                return PlannerClarification("UNREPRESENTABLE_REQUEST")
            assert fragment == " y compré pan."
            assert domain is not None
            return _day_plan("2026-10-04", "Compré pan.", "2026-10-04")

        return SimpleNamespace(plan=plan)

    result = execute_candidate_routed_message(
        source,
        router=RecordedRouter("F06"),
        temporal=Temporal(),
        core_planner_factory=factory,
        candidate_coverage_factory=_review_one_real_core_fact,
        repository=repo,
        schema=SCHEMA,
        context_index=context,
        semantic_index=semantic,
        embedder=embedder,
        contextual_reasoner=object(),
        actor="hybrid-independent-failure",
        now=NOW,
        context_limit=5,
        request_id_factory=lambda: "f06-independent-hybrid",
        bundle_compiler=compile_hybrid_candidate_bundle,
    )
    assert len(observed) == 2
    assert result.status is ApplicationStatus.PARTIAL
    text = "\n".join(repo.read_text(path) for path in repo.list_markdown_paths())
    assert "Compré pan." in text
    assert "Vi a Ana." not in text
