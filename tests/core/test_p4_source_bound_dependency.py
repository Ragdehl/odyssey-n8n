"""P4 E2 canonical handoff is non-authoritative and physically freshness-bound."""

from __future__ import annotations

from dataclasses import replace

import pytest

from odyssey_core.application import ApplicationStatus, DependentReferenceGuard
from odyssey_core.notes import parse_note, serialize_note
from odyssey_core.source_bound_dependency import (
    SourceBoundDependencyError,
    prove_source_bound_dependency,
)
from tests.runtime.test_whole_source_light_product_p4 import (
    SCHEMA,
    RecordedClient,
    _actual_snapshot,
    _fixture,
    _speaker,
)


@pytest.fixture
def grounded_proof(tmp_path):
    source, route, plan, review = _actual_snapshot("maya_simple")
    repo, actor, executor, _ = _fixture(tmp_path)
    executor.client = RecordedClient(
        [route, plan, review, _speaker(source, plan, base=1), _speaker(source, plan)]
    )
    result = executor(source, "p4-e2-source-antecedent", actor, "main")
    assert result.status is ApplicationStatus.COMPLETED
    assert len(result.canonical_reference_evidence) == 1
    return repo, result, source


def _bound(repo, result, source, **overrides):
    values = dict(
        complete_original_source=source + " Después la llamé.",
        antecedent_quote=source,
        dependent_quote=" Después la llamé.",
        exact_dependent_mention="la",
        predecessor=result,
        repository=repo,
        schema=SCHEMA,
    )
    return prove_source_bound_dependency(**(values | overrides))


def test_one_actual_core_persisted_reference_may_be_carried_but_not_used_as_authority(
    grounded_proof,
):
    repo, result, source = grounded_proof
    proof = _bound(repo, result, source)
    assert proof.evidence.stable_note_id == result.canonical_reference_evidence[0].stable_note_id
    assert proof.mention == "la"
    assert type(proof.core_write_guard()) is DependentReferenceGuard
    assert proof.core_write_guard().evidence is proof.evidence
    # Core guard alone does not authorize a write; a dependent semantic
    # reviewer, authenticated actor, preflight and Writer remain required.
    assert not hasattr(proof, "write")


@pytest.mark.parametrize(
    "modifications",
    [
        {"complete_original_source": "Ayer hablé con Maya. Después la llamé.".replace(".", "", 1)},
        {"antecedent_quote": "Ayer hablé con Maya"},
        {"dependent_quote": "Después la llamé."},
        {"exact_dependent_mention": "lo"},
        {"exact_dependent_mention": "la llamé"},
    ],
)
def test_changed_source_or_dependent_mention_fails_closed(grounded_proof, modifications):
    repo, result, source = grounded_proof
    # Multiword referring expressions are permitted if actually in source;
    # only altered, absent, ambiguous or non-boundary mentions must be vetoed.
    if modifications.get("exact_dependent_mention") == "la llamé":
        assert _bound(repo, result, source, **modifications).mention == "la llamé"
    else:
        with pytest.raises(SourceBoundDependencyError):
            _bound(repo, result, source, **modifications)


def test_repeated_antecedent_name_or_anaphor_is_ambiguous(grounded_proof):
    repo, result, source = grounded_proof
    with pytest.raises(SourceBoundDependencyError):
        _bound(repo, result, source + " Maya")
    with pytest.raises(SourceBoundDependencyError):
        _bound(
            repo,
            result,
            source,
            complete_original_source=source + " La llamé y la vi.",
            dependent_quote=" La llamé y la vi.",
        )


def test_partial_missing_or_duplicate_core_proof_cannot_be_promoted(grounded_proof):
    repo, result, source = grounded_proof
    variants = [
        replace(result, status=ApplicationStatus.PARTIAL),
        replace(result, canonical_reference_evidence=()),
        replace(
            result,
            canonical_reference_evidence=(
                *result.canonical_reference_evidence,
                *result.canonical_reference_evidence,
            ),
        ),
    ]
    for candidate in variants:
        with pytest.raises(SourceBoundDependencyError):
            _bound(repo, candidate, source)


def test_physically_modified_source_or_reference_cannot_be_reused(grounded_proof):
    repo, result, source = grounded_proof
    proof = _bound(repo, result, source)
    for stable_id in (proof.evidence.stable_note_id, proof.evidence.source_note_id):
        for path in repo.list_markdown_paths():
            note = parse_note(repo.read_text(path))
            if note.metadata.get("id") == stable_id:
                repo.replace_text(
                    path,
                    serialize_note(replace(note, content=note.content + "\n- external edit\n")),
                )
                break
        else:
            raise AssertionError("Evidence target absent in fixture")
        with pytest.raises(SourceBoundDependencyError, match="changed"):
            _bound(repo, result, source)


def test_forged_or_unaffected_core_private_carrier_has_no_handoff_authority(grounded_proof):
    repo, result, source = grounded_proof
    candidates = [
        replace(result, action_results=()),
        replace(result, affected_stable_note_ids=()),
        replace(
            result,
            action_results=(replace(result.action_results[0], canonical_reference_evidence=()),),
        ),
    ]
    for candidate in candidates:
        with pytest.raises(SourceBoundDependencyError, match="materialized"):
            _bound(repo, candidate, source)


def test_core_dependency_guard_does_not_authorize_fact_without_reference_marker(grounded_proof):
    from odyssey_core.application import WritePreflightGuardError
    from odyssey_core.whole_source_compiler import plan_for_record

    repo, result, source = grounded_proof
    proof = _bound(repo, result, source)
    plan = plan_for_record(
        {
            "facts": [
                {
                    "kind": "record",
                    "date": "2026-10-16",
                    "reviewed_text": "Unrelated fact with no target.",
                    "reference_names": [],
                }
            ]
        },
        "2026-10-16",
    )
    with pytest.raises(WritePreflightGuardError, match="REFERENCE_MARKER_REQUIRED"):
        proof.core_write_guard()(plan.actions[0], (), repo, SCHEMA)


def test_alias_never_inherits_identity_without_independent_semantic_proof(grounded_proof):
    repo, result, source = grounded_proof
    carrier = replace(result.canonical_reference_evidence[0], canonical_name="Maya Contreras")
    with pytest.raises(SourceBoundDependencyError):
        _bound(repo, replace(result, canonical_reference_evidence=(carrier,)), source)


def test_whole_source_multiple_persisted_reference_occurrences_cannot_choose_last(tmp_path):
    source, route, plan, review = _actual_snapshot("maite_cross_app")
    repo, actor, executor, _ = _fixture(tmp_path)
    executor.client = RecordedClient(
        [
            route,
            plan,
            {
                "only_new_task_creations": True,
                "no_work_session_or_lifecycle_transition": True,
                "source_quote": source,
            },
            review,
            _speaker(source, plan, base=1),
            _speaker(source, plan),
        ]
    )
    result = executor(source, "p4-multiple-identity-guards", actor, "main")
    assert result.status is ApplicationStatus.COMPLETED
    assert len(result.action_results) == 2
    assert sum(len(a.canonical_reference_evidence) for a in result.action_results) == 2
    # It is NEVER acceptable to select the proof from the last action merely
    # because it is last in execution order; both independently wrote a link.
    assert result.canonical_reference_evidence == ()


def test_whole_source_single_antecedent_does_preserve_actual_proof(grounded_proof):
    _, result, _ = grounded_proof
    assert len(result.canonical_reference_evidence) == 1
    assert len(result.action_results) == 1
    assert (
        result.action_results[0].canonical_reference_evidence == result.canonical_reference_evidence
    )


@pytest.mark.parametrize("different_name", ["Ana", "Lucía", "René Dupont", "Zoe"])
def test_explicit_other_name_cannot_inherit_sole_core_person(grounded_proof, different_name):
    repo, result, source = grounded_proof
    after = f" Después debo llamar a {different_name}."
    with pytest.raises(SourceBoundDependencyError, match="Named dependent"):
        _bound(
            repo,
            result,
            source,
            complete_original_source=source + after,
            dependent_quote=after,
            exact_dependent_mention=different_name,
        )
