"""Core-only, no-provider evidence for a narrowly scoped source pronoun.

The canonical reference is verified in actual disposable Markdown. Antecedent
and referent linguistic relationship remains a proposal, never a Note mutation.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

from odyssey_core.application import (
    ApplicationStatus,
    DependentReferenceGuard,
    execute_request,
)
from odyssey_core.candidate_reference_handoff import find_single_candidate_canonical_handoff
from odyssey_core.storage import VaultRepository
from tests.core.test_canonical_reference_evidence import _write_existing
from tests.runtime.test_fact_candidate_writes_e2e import _case
from tests.runtime.test_temporal_user_path_e2e import (
    NOW,
    SCHEMA,
    _calendar,
    _linked_day_plan,
    _visible_day,
)


def _setup_eric(tmp_path: Path):
    """Store a genuinely linked source fact and return its private Core carrier."""
    case, context = _case("F13")
    vault = tmp_path / "vault"
    _write_existing(vault)
    repo = VaultRepository(vault)
    plan = _linked_day_plan("2026-10-03", "Hablé con {{ref:0}}.", "Eric", "2026-10-03")
    result = execute_request(
        "Ayer hablé con Eric.",
        planner=SimpleNamespace(plan=lambda _: plan),
        repository=repo,
        schema=SCHEMA,
        context_index=object(),
        semantic_index=object(),
        embedder=object(),
        contextual_reasoner=object(),
        actor="synthetic-reference-candidate",
        now=NOW,
        context_limit=5,
        request_id_factory=lambda: "candidate-eric-predecessor",
    )
    assert result.status is ApplicationStatus.COMPLETED
    assert len(result.canonical_reference_evidence) == 1
    return case, context, repo, result


def test_unique_previous_core_link_can_be_carried_as_private_reference_evidence(
    tmp_path: Path,
) -> None:
    case, context, repo, first = _setup_eric(tmp_path)
    handoff = find_single_candidate_canonical_handoff(
        case["source"], context, "candidate-2", first, repo, SCHEMA
    )
    assert handoff is not None
    assert (handoff.antecedent_candidate_id, handoff.referring_candidate_id) == (
        "candidate-1",
        "candidate-2",
    )
    assert handoff.referring_span.text == "él"
    assert handoff.evidence.canonical_name == "Eric"
    assert handoff.evidence.stable_note_id == "eric-id"
    guard = handoff.write_guard()
    assert isinstance(guard, DependentReferenceGuard)
    assert guard.mention == "él"
    assert not hasattr(handoff, "execute")


def test_existing_core_guard_permits_a_real_linked_next_day_write(tmp_path: Path) -> None:
    """A real preflight + Markdown write is still entirely owned by existing Core."""
    case, context, repo, first = _setup_eric(tmp_path)
    handoff = find_single_candidate_canonical_handoff(
        case["source"], context, "candidate-2", first, repo, SCHEMA
    )
    assert handoff is not None
    plan = _linked_day_plan(
        "2026-10-05", "Iré al cine con {{ref:0}}.", "él", "2026-10-05", target_name="Eric"
    )
    result = execute_request(
        "Mañana iré al cine con él.",
        planner=SimpleNamespace(plan=lambda _: plan),
        repository=repo,
        schema=SCHEMA,
        context_index=object(),
        semantic_index=object(),
        embedder=object(),
        contextual_reasoner=object(),
        actor="synthetic-reference-candidate",
        now=NOW,
        context_limit=5,
        request_id_factory=lambda: "candidate-eric-dependent",
        write_preflight_guard=handoff.write_guard(),
    )
    assert result.status is ApplicationStatus.COMPLETED
    assert "date:2026-10-05" in result.affected_stable_note_ids
    visible = _visible_day(_calendar(repo, tmp_path), "2026-10-05")
    assert any("Iré al cine con " in fact and "Eric" in fact for fact in visible)


def test_multi_antecedent_and_ambiguous_pronoun_never_infer_one_from_missing_evidence(
    tmp_path: Path,
) -> None:
    _, _, repo, first = _setup_eric(tmp_path)
    case, context = _case("F27")
    assert (
        find_single_candidate_canonical_handoff(
            case["source"], context, "candidate-3", first, repo, SCHEMA
        )
        is None
    )
    assert (
        find_single_candidate_canonical_handoff(
            case["source"], context, "candidate-2", first, repo, SCHEMA
        )
        is None
    )


def test_stale_fact_or_changed_canonical_identity_withholds_handoff(tmp_path: Path) -> None:
    case, context, repo, first = _setup_eric(tmp_path)
    day_path = tmp_path / "vault" / "calendar" / "days" / "2026-10-03.md"
    before = day_path.read_text()
    day_path.write_text(before + "\n", encoding="utf-8")
    assert (
        find_single_candidate_canonical_handoff(
            case["source"], context, "candidate-2", first, repo, SCHEMA
        )
        is None
    )
    day_path.write_text(before, encoding="utf-8")
    eric = tmp_path / "vault" / "Eric.md"
    eric.write_text(eric.read_text() + "\n", encoding="utf-8")
    assert (
        find_single_candidate_canonical_handoff(
            case["source"], context, "candidate-2", first, repo, SCHEMA
        )
        is None
    )


def test_no_evidence_in_predecessor_means_no_guess(tmp_path: Path) -> None:
    case, context, repo, first = _setup_eric(tmp_path)
    without_proof = replace(first, canonical_reference_evidence=())
    assert (
        find_single_candidate_canonical_handoff(
            case["source"], context, "candidate-2", without_proof, repo, SCHEMA
        )
        is None
    )
    with_wrong_result = replace(first, status=ApplicationStatus.PARTIAL)
    assert (
        find_single_candidate_canonical_handoff(
            case["source"], context, "candidate-2", with_wrong_result, repo, SCHEMA
        )
        is None
    )


def test_original_source_and_candidate_id_are_strictly_bounded(tmp_path: Path) -> None:
    case, context, repo, first = _setup_eric(tmp_path)
    assert (
        find_single_candidate_canonical_handoff(
            case["source"], context, "candidate-3", first, repo, SCHEMA
        )
        is None
    )
    import pytest

    with pytest.raises(ValueError, match="full current source"):
        find_single_candidate_canonical_handoff(
            "Wrong full source", context, "candidate-2", first, repo, SCHEMA
        )


def test_multiple_named_roles_in_one_antecedent_are_not_collapsed_to_eric(tmp_path: Path) -> None:
    """Even with one earlier candidate, a group must not become one person."""
    case, context, repo, first = _setup_eric(tmp_path)
    original = context.candidates[0]
    from odyssey_core.candidate_context import CoreCandidateRole

    object_role = next(role for role in original.roles if role.role == "object")
    group = replace(
        original,
        roles=(*original.roles, CoreCandidateRole("participants", object_role.span)),
    )
    forged_context = replace(context, candidates=(group, *context.candidates[1:]))
    forged_context.validate(case["source"])
    assert (
        find_single_candidate_canonical_handoff(
            case["source"], forged_context, "candidate-2", first, repo, SCHEMA
        )
        is None
    )


def test_reference_source_role_must_be_inside_its_candidate_anchor(tmp_path: Path) -> None:
    """Do not bind an out-of-candidate reference role just because text was in request."""
    case, context, repo, first = _setup_eric(tmp_path)
    from odyssey_core.candidate_context import CoreCandidateRole

    later = context.candidates[1]
    first_anchor_role = context.candidates[0].roles[0]
    forged = replace(later, roles=(CoreCandidateRole("reference", first_anchor_role.span),))
    mixed = replace(context, candidates=(context.candidates[0], forged, context.candidates[2]))
    mixed.validate(case["source"])
    assert (
        find_single_candidate_canonical_handoff(
            case["source"], mixed, "candidate-2", first, repo, SCHEMA
        )
        is None
    )


def test_existing_guard_rechecks_staleness_at_the_last_instant(tmp_path: Path) -> None:
    """A handoff once valid loses validity when its source Markdown changes."""
    import pytest

    from odyssey_core.application import WritePreflightGuardError
    from odyssey_core.reference_preflight import UnitTargetPreflight
    from odyssey_core.write_target import WriteTargetOutcome

    case, context, repo, first = _setup_eric(tmp_path)
    proof = find_single_candidate_canonical_handoff(
        case["source"], context, "candidate-2", first, repo, SCHEMA
    )
    assert proof is not None
    plan = _linked_day_plan(
        "2026-10-05", "Iré al cine con {{ref:0}}.", "él", "2026-10-05", target_name="Eric"
    )
    targets = (
        UnitTargetPreflight(
            0,
            WriteTargetOutcome.CREATE,
            "date:2026-10-05",
            "2026-10-05",
            "calendar/days/2026-10-05.md",
        ),
        UnitTargetPreflight(
            1, WriteTargetOutcome.UPDATE, "eric-id", "Eric", "Eric.md", reference_only=True
        ),
    )
    proof.write_guard()(plan.actions[0], targets, repo, SCHEMA)
    day = tmp_path / "vault" / "calendar" / "days" / "2026-10-03.md"
    day.write_text(day.read_text() + "\n", encoding="utf-8")
    with pytest.raises(WritePreflightGuardError, match="CANONICAL_EVIDENCE_STALE"):
        proof.write_guard()(plan.actions[0], targets, repo, SCHEMA)


def _real_router_f13_context():
    """Read the frozen REAL GPT-6 Router F13 output, not an oracle fixture."""
    import json

    from benchmarks.fact_candidate_v2_live import run_remaining
    from odyssey_apps.fact_candidate_core import to_core_candidate_context
    from odyssey_apps.fact_candidates import validate_fact_candidate_proposal

    receipt = next(run_remaining.RESULTS.glob("*--F13.json"))
    observed = json.loads(receipt.read_text(encoding="utf-8"))
    assert observed["provider_status"] == "completed"
    assert observed["validation"] == "source_valid"
    case, _ = _case("F13")
    context = to_core_candidate_context(
        validate_fact_candidate_proposal(case["source"], json.loads(observed["raw_model_response"]))
    )
    return case["source"], context


def test_actual_router_unquoted_reference_role_binds_only_to_its_own_clause(tmp_path):
    """GPT-6's real F13 lacks an 'él' anchor but supplies a real source role."""
    _case, _oracle, repo, first = _setup_eric(tmp_path)
    source, context = _real_router_f13_context()
    referring = context.candidates[1]
    assert not any("él" in anchor.text for anchor in referring.anchors)
    assert [r.span.text for r in referring.roles if r.role == "reference"] == ["él"]
    proof = find_single_candidate_canonical_handoff(
        source, context, referring.candidate_id, first, repo, SCHEMA
    )
    assert proof is not None
    assert proof.evidence.stable_note_id == "eric-id"
    plan = _linked_day_plan(
        "2026-10-05", "Iré al cine con {{ref:0}}.", "él", "2026-10-05", target_name="Eric"
    )
    result = execute_request(
        "Mañana iré al cine con él.",
        planner=SimpleNamespace(plan=lambda _: plan),
        repository=repo,
        schema=SCHEMA,
        context_index=object(),
        semantic_index=object(),
        embedder=object(),
        contextual_reasoner=object(),
        actor="frozen-real-router-f13-reference-bridge",
        now=NOW,
        context_limit=5,
        request_id_factory=lambda: "real-router-f13-dependent",
        write_preflight_guard=proof.write_guard(),
    )
    assert result.status is ApplicationStatus.COMPLETED
    assert any("Eric" in fact for fact in _visible_day(_calendar(repo, tmp_path), "2026-10-05"))


def test_real_router_reference_in_other_source_clause_fails_closed(tmp_path):
    from odyssey_core.candidate_context import CoreCandidateRole

    _case, _oracle, repo, first = _setup_eric(tmp_path)
    source, context = _real_router_f13_context()
    old = context.candidates[1]
    unrelated = next(role.span for role in context.candidates[2].roles if role.role == "date")
    substituted = replace(
        old,
        roles=tuple(
            CoreCandidateRole("reference", unrelated) if r.role == "reference" else r
            for r in old.roles
        ),
    )
    forged = replace(
        context, candidates=(context.candidates[0], substituted, context.candidates[2])
    )
    forged.validate(source)
    assert (
        find_single_candidate_canonical_handoff(source, forged, "candidate-2", first, repo, SCHEMA)
        is None
    )


def test_real_router_reference_competing_candidate_in_same_clause_fails_closed(tmp_path):
    _case, _oracle, repo, first = _setup_eric(tmp_path)
    source, context = _real_router_f13_context()
    peer = replace(
        context.candidates[2],
        anchors=(context.candidates[1].anchors[0],),
    )
    forged = replace(context, candidates=(context.candidates[0], context.candidates[1], peer))
    forged.validate(source)
    assert (
        find_single_candidate_canonical_handoff(source, forged, "candidate-2", first, repo, SCHEMA)
        is None
    )
