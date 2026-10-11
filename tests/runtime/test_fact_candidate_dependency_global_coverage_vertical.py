"""Real-model dependent Core global coverage and linked Markdown, opt-in only.

No provider API, deployments, or personal knowledge is used in these tests.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from odyssey_core.application import ApplicationStatus, execute_request
from odyssey_core.candidate_coverage import (
    CoreCandidateCoverageClaim,
    build_candidate_coverage_manifest,
    build_dependent_candidate_coverage_manifest,
    validate_candidate_coverage_manifest,
)
from odyssey_core.candidate_dependency_attestation import (
    DependentFactAttestationError,
    review_combined_persisted_dependency,
)
from odyssey_core.request_planning import RequestPlan, WriteAction
from tests.core.test_reference_preflight import EmptyIndex, UnresolvedReasoner
from tests.runtime.test_candidate_pending_state import NOW
from tests.runtime.test_fact_candidate_dependent_actual_core_vertical import _plans, _vault
from tests.runtime.test_fact_candidate_semantic_luna_vertical import SCHEMA
from tests.runtime.test_temporal_user_path_e2e import ConstantEmbedder


def _setup(case):
    source, context, raw = _plans(case)
    plans = tuple(model_plan for _, model_plan in raw)
    claims = tuple(
        CoreCandidateCoverageClaim(f"candidate-{i + 1}", "planned_fact", i) for i in range(2)
    )
    joined, manifest = build_dependent_candidate_coverage_manifest(source, context, plans, claims)
    return source, context, plans, claims, joined, manifest


@pytest.mark.parametrize("case", ("F23", "F26"))
def test_global_source_coverage_uses_actual_two_independent_core_plans(case):
    source, context, plans, claims, combined, manifest = _setup(case)
    assert len(combined.actions) == len(plans) == 2
    assert combined.actions == tuple(p.actions[0] for p in plans)
    assert tuple(c.fact_ordinal for c in manifest.claims) == (0, 1)
    assert manifest.dependency_attestation.candidate_ids == ("candidate-1", "candidate-2")
    assert manifest.dependency_attestation.may_write_notes is False
    validate_candidate_coverage_manifest(source, context, combined, manifest)
    # Without the independently replayed original-source proof the old
    # conservative lexical/proposition validators still block.
    with pytest.raises(ValueError):
        build_candidate_coverage_manifest(source, context, combined, claims)


@pytest.mark.parametrize("case,existing", (("F23", False), ("F26", True), ("F26", False)))
def test_complete_original_source_coverage_then_canonical_write_and_identity_audit(
    tmp_path: Path, case, existing
):
    source, context, plans, claims, combined, manifest = _setup(case)
    repo, index = _vault(tmp_path, existing_report=existing)
    result = execute_request(
        source,
        planner=SimpleNamespace(plan=lambda _: combined),
        repository=repo,
        schema=SCHEMA,
        context_index=index,
        semantic_index=EmptyIndex() if case == "F26" and not existing else object(),
        embedder=ConstantEmbedder(),
        contextual_reasoner=UnresolvedReasoner() if case == "F26" and not existing else object(),
        actor="synthetic-combined-dependent-core",
        now=NOW,
        context_limit=5,
        request_id_factory=lambda: f"global-covered-{case}",
        candidate_context=context,
        candidate_coverage_factory=lambda *_: manifest,
    )
    assert result.status is ApplicationStatus.COMPLETED
    assert len(result.action_results) == 2
    audited = review_combined_persisted_dependency(
        source, context, plans, manifest.dependency_attestation, result, repo
    )
    assert audited.canonical_reuse_verified
    assert audited.may_write_notes is False
    if case == "F23":
        assert result.affected_stable_note_ids == ("odyssey-id", "odyssey-id")
        note = repo.read_text("Odyssey.md")
        assert note.count("<!-- odyssey:fact request=global-covered-F23") == 2
    else:
        assert result.affected_stable_note_ids[0] != result.affected_stable_note_ids[1]
        document_id = result.affected_stable_note_ids[0]
        assert result.action_results[1].unit_results[1].stable_note_id == document_id
        note = repo.read_text("calendar/days/2026-10-04.md")
        assert note.count("<!-- odyssey:fact request=global-covered-F26") == 1
        assert "[[Ana|Ana]]" in note


@pytest.mark.parametrize("case", ("F23", "F26"))
def test_tampered_or_missing_dependency_proof_does_not_authorize_global_coverage(case):
    source, context, plans, claims, joined, manifest = _setup(case)
    for changed in (
        replace(manifest, dependency_attestation=None),
        replace(
            manifest,
            dependency_attestation=replace(manifest.dependency_attestation, source_digest="0" * 64),
        ),
        replace(
            manifest,
            dependency_attestation=replace(
                manifest.dependency_attestation, canonical_reuse_verified=True
            ),
        ),
        replace(
            manifest,
            dependency_attestation=replace(manifest.dependency_attestation, may_write_notes=True),
        ),
        replace(manifest, claims=tuple(reversed(claims))),
        replace(manifest, claims=(claims[0], claims[0])),
    ):
        with pytest.raises(ValueError):
            validate_candidate_coverage_manifest(source, context, joined, changed)


def test_swapped_facts_or_mutated_reference_helper_fail_even_with_original_proof():
    source, context, plans, claims, joined, manifest = _setup("F26")
    first, second = joined.actions
    swapped = RequestPlan((second, first), ())
    with pytest.raises(ValueError):
        validate_candidate_coverage_manifest(
            source,
            context,
            swapped,
            replace(
                manifest,
                plan_digest=__import__("hashlib").sha256(repr(swapped).encode()).hexdigest(),
            ),
        )
    parts = list(second.units)
    bad_helper = parts[1]
    parts[1] = replace(bad_helper, target=replace(bad_helper.target, query="otro documento"))
    with pytest.raises(ValueError):
        build_dependent_candidate_coverage_manifest(
            source, context, (plans[0], RequestPlan((WriteAction(tuple(parts)),), ())), claims
        )


def test_tampered_current_day_wikilink_cannot_pass_combined_audit(tmp_path):
    source, context, plans, claims, combined, manifest = _setup("F26")
    repo, index = _vault(tmp_path, existing_report=True)
    result = execute_request(
        source,
        planner=SimpleNamespace(plan=lambda _: combined),
        repository=repo,
        schema=SCHEMA,
        context_index=index,
        semantic_index=object(),
        embedder=ConstantEmbedder(),
        contextual_reasoner=object(),
        actor="isolated",
        now=NOW,
        context_limit=5,
        request_id_factory=lambda: "tampered-day",
        candidate_context=context,
        candidate_coverage_factory=lambda *_: manifest,
    )
    assert result.status is ApplicationStatus.COMPLETED
    day = tmp_path / "vault" / "calendar/days/2026-10-04.md"
    day.write_text(
        day.read_text(encoding="utf-8").replace("[[El informe|El informe]]", "[[Ana|El informe]]"),
        encoding="utf-8",
    )
    with pytest.raises(DependentFactAttestationError):
        review_combined_persisted_dependency(
            source, context, plans, manifest.dependency_attestation, result, repo
        )


@pytest.mark.parametrize("case", ("F23", "F26"))
def test_invalid_global_dependency_proof_blocks_before_any_markdown_write(tmp_path, case):
    """The existing Core application rechecks the manifest before acting."""
    source, context, _plans, _claims, combined, manifest = _setup(case)
    repo, index = _vault(tmp_path, existing_report=True)
    before = {p: repo.read_text(p) for p in repo.list_markdown_paths()}
    forged = replace(manifest, dependency_attestation=None)
    result = execute_request(
        source,
        planner=SimpleNamespace(plan=lambda _: combined),
        repository=repo,
        schema=SCHEMA,
        context_index=index,
        semantic_index=object(),
        embedder=ConstantEmbedder(),
        contextual_reasoner=object(),
        actor="untrusted-proof-test",
        now=NOW,
        context_limit=5,
        request_id_factory=lambda: "untrusted-proof",
        candidate_context=context,
        candidate_coverage_factory=lambda *_: forged,
    )
    assert result.status is ApplicationStatus.NEEDS_ATTENTION
    assert result.clarification_code == "CANDIDATE_COVERAGE_REVIEW_REQUIRED"
    assert result.action_results == ()
    assert {p: repo.read_text(p) for p in repo.list_markdown_paths()} == before


@pytest.mark.parametrize("case", ("F19", "F20"))
def test_conditional_and_correction_do_not_enter_dependency_coverage(case):
    from odyssey_core.candidate_dependency_attestation import attest_two_dependent_core_plans
    from odyssey_core.candidate_dependent_scope import CoreDependentScopeError
    from tests.core.test_candidate_dependencies_observed import _observed

    source, context = _observed(case)
    _safe_source, _safe_context, safe_entries = _plans("F23")
    with pytest.raises(CoreDependentScopeError):
        attest_two_dependent_core_plans(source, context, tuple(plan for _, plan in safe_entries))
