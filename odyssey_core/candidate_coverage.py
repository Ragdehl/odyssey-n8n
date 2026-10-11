"""Opt-in Core-only preflight for source-candidate coverage of a written plan.

A proposed source interpretation cannot silently disappear when Core plans a
subset. This verifies explicit accounting for every candidate and every planned
atomic fact *before* normal Core execution; only actual Markdown markers can
confirm persistence later. Claims must be independently reviewed by Core, never
copied directly from Router. Structural checks are not semantic attestation.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Literal

from .candidate_context import CoreCandidateContext
from .candidate_fact_readback import CandidateFactReadback
from .candidate_multi_participant import (
    validate_one_named_participant_fact,
    validate_two_named_participant_fact,
)
from .candidate_mutual_relation import validate_one_mutual_relationship_fact
from .candidate_property_evidence import validate_subject_property_fact
from .candidate_semantic_veto import veto_unsafe_literal_match
from .candidate_sequential_contacts import validate_two_sequential_contacts
from .request_planning import RequestPlan, WriteAction, plan_fact_ordinals

MAX_COVERAGE_CLAIMS = 26
MAX_COVERAGE_FACTS = 128
PENDING_REASONS = frozenset(
    {"ambiguous_identity", "needs_clarification", "needs_capability", "unsupported_scope"}
)


@dataclass(frozen=True, slots=True)
class CoreCandidateCoverageClaim:
    """Independently proposed ownership or explicit non-execution of one source unit.

    Legacy `fact_ordinal` supports the reviewed one-to-one shape. An explicitly
    reviewed `fact_ordinals` tuple permits variable candidate-to-fact edges:
    one candidate may support several facts; a fact may depend on several
    candidates. Neither shape is independent semantic certification.
    """

    candidate_id: str
    disposition: Literal["planned_fact", "pending"]
    fact_ordinal: int | None = None
    pending_reason: str | None = None
    fact_ordinals: tuple[int, ...] | None = None


@dataclass(frozen=True, slots=True)
class CoreCandidateCoverageManifest:
    """Bind full original source and unchanged Core plan to explicit claims."""

    source_digest: str
    plan_digest: str
    claims: tuple[CoreCandidateCoverageClaim, ...]


@dataclass(frozen=True, slots=True)
class CoreCandidateCoverageItem:
    """State structural mapping and independently observed persistence only."""

    candidate_id: str
    status: Literal["physically_written_claim", "planned_unverified", "pending"]
    fact_ordinal: int | None
    pending_reason: str | None
    fact_ordinals: tuple[int, ...] | None = None


@dataclass(frozen=True, slots=True)
class CoreCandidateCoverageReview:
    """Source and persistence coverage, complete only after canonical audit."""

    items: tuple[CoreCandidateCoverageItem, ...]
    pending_candidate_ids: tuple[str, ...]
    candidate_semantics_verified: bool
    fully_accounted_for_structurally: bool
    safe_to_report_all_candidates_complete: bool


def _digest(value: str) -> str:
    """Hash context/plan text without storing another user knowledge record."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def build_candidate_coverage_manifest(
    source: str,
    context: CoreCandidateContext,
    plan: RequestPlan,
    claims: tuple[CoreCandidateCoverageClaim, ...],
    *,
    canonical_binding: object | None = None,
) -> CoreCandidateCoverageManifest:
    """Build a plan-bound candidate checklist after explicit Core review.

    This builder does not infer candidate ownership or decide dispositions. The
    caller must supply every candidate claim; invalid or incomplete claims raise.
    """
    manifest = CoreCandidateCoverageManifest(_digest(source), _digest(repr(plan)), claims)
    validate_candidate_coverage_manifest(
        source, context, plan, manifest, canonical_binding=canonical_binding
    )
    return manifest


def validate_candidate_coverage_manifest(
    source: str,
    context: CoreCandidateContext,
    plan: RequestPlan,
    manifest: CoreCandidateCoverageManifest,
    *,
    canonical_binding: object | None = None,
) -> None:
    """Reject omitted candidates, invented ordinals, ambiguity and stale plans.

    Raises:
        ValueError: Any missing/duplicate candidate, unidentified write fact,
            unreviewed complex write, stale input or ungrounded disposition.
    """
    if not isinstance(context, CoreCandidateContext) or not isinstance(plan, RequestPlan):
        raise ValueError("Core source context and validated plan required")
    context.validate(source)
    if (
        not isinstance(manifest, CoreCandidateCoverageManifest)
        or manifest.source_digest != _digest(source)
        or manifest.plan_digest != _digest(repr(plan))
    ):
        raise ValueError("Coverage manifest is stale or mismatched")
    claims = manifest.claims
    if not isinstance(claims, tuple) or not 1 <= len(claims) <= MAX_COVERAGE_CLAIMS:
        raise ValueError("Coverage claim count is invalid")
    expected_ids = tuple(candidate.candidate_id for candidate in context.candidates)
    if any(not isinstance(claim, CoreCandidateCoverageClaim) for claim in claims):
        raise ValueError("Coverage claims require typed Core candidate evidence")
    if (
        len(claims) != len(expected_ids)
        or tuple(claim.candidate_id for claim in claims) != expected_ids
    ):
        raise ValueError("Every source candidate requires one ordered coverage claim")
    ordinals = plan_fact_ordinals(plan)
    fact_ordinals: set[int] = set()
    for action in plan.actions:
        if isinstance(action, WriteAction):
            for unit in action.units:
                # Reference-only helper units are eligible ONLY if claimed
                # later by a source-validated grouped or sequential fact. They never own
                # a separately planned fact or mutation.
                if (
                    unit.intent != "record"
                    or unit.properties
                    or unit.tag_changes
                    or unit.destination_type is not None
                    or unit.force_create
                    or (unit.reference_lookup_only and (unit.facts or unit.references))
                    or (not unit.reference_lookup_only and not unit.facts)
                ):
                    raise ValueError("Complex Core write requires reviewed coverage capability")
    for per_unit in ordinals:
        fact_ordinals.update(per_unit)
    if len(fact_ordinals) > MAX_COVERAGE_FACTS:
        raise ValueError("Fact coverage exceeds review budget")
    facts_by_ordinal: dict[int, str] = {}
    write_unit_ordinals = iter(ordinals)
    for action in plan.actions:
        if isinstance(action, WriteAction):
            for unit in action.units:
                numbered = next(write_unit_ordinals)
                if len(numbered) != len(unit.facts):
                    raise ValueError("Core fact ordinals do not match plan fact text")
                for fact_index, ordinal in enumerate(numbered):
                    facts_by_ordinal[ordinal] = unit.facts[fact_index]
    owners_by_ordinal: dict[int, tuple[int, int, int]] = {}
    next_ordinals = iter(ordinals)
    for action_index, action in enumerate(plan.actions):
        if isinstance(action, WriteAction):
            for unit_index, _unit in enumerate(action.units):
                for fact_index, ordinal in enumerate(next(next_ordinals)):
                    owners_by_ordinal[ordinal] = action_index, unit_index, fact_index
    # A reviewed edge set, not an assumption about candidate/write cardinality.
    # Legacy one-to-one claims remain strict, including their uniqueness rule.
    graph_mode = any(claim.fact_ordinals is not None for claim in claims)
    claimed_ordinals: set[int] = set()
    claimed_pairs: list[tuple[int, int]] = []
    for index, (candidate, claim) in enumerate(zip(context.candidates, claims, strict=True)):
        if not isinstance(claim, CoreCandidateCoverageClaim):
            raise ValueError("Coverage claim must be Core-owned typed evidence")
        if claim.disposition == "pending":
            if (
                claim.fact_ordinal is not None
                or claim.fact_ordinals is not None
                or not isinstance(claim.pending_reason, str)
                or claim.pending_reason not in PENDING_REASONS
                or (candidate.state == "ambiguous_identity")
                != (claim.pending_reason == "ambiguous_identity")
            ):
                raise ValueError("Pending candidate requires a compatible unresolved reason")
            continue
        if claim.disposition != "planned_fact":
            raise ValueError("Unknown coverage disposition")
        if candidate.state == "ambiguous_identity":
            raise ValueError("Ambiguous identity cannot be claimed as a planned write")
        if candidate.kind in {"conditional", "negative"} or any(
            role.role in {"condition", "polarity", "replacement", "modality"}
            for role in candidate.roles
        ):
            raise ValueError("Sensitive scoped fact requires specialized semantic coverage proof")
        if graph_mode:
            if (
                claim.fact_ordinal is not None
                or not isinstance(claim.fact_ordinals, tuple)
                or not claim.fact_ordinals
                or len(claim.fact_ordinals) > MAX_COVERAGE_FACTS
                or len(set(claim.fact_ordinals)) != len(claim.fact_ordinals)
            ):
                raise ValueError("Graph claims require nonempty unique fact ordinal tuples")
            linked_ordinals = claim.fact_ordinals
        else:
            if claim.fact_ordinals is not None:
                raise ValueError("Legacy fact claims must use one ordinal")
            linked_ordinals = (claim.fact_ordinal,)
        if claim.pending_reason is not None:
            raise ValueError("Planned coverage cannot also be pending")
        for ordinal in linked_ordinals:
            if (
                not isinstance(ordinal, int)
                or isinstance(ordinal, bool)
                or ordinal not in fact_ordinals
                or (not graph_mode and ordinal in claimed_ordinals)
            ):
                raise ValueError("Coverage fact ordinal is missing, duplicate or invented")
            claimed_pairs.append((index, ordinal))
            claimed_ordinals.add(ordinal)
    if claimed_ordinals != fact_ordinals:
        raise ValueError("Every planned atomic fact needs original source evidence")
    # Canonical referents require separately certified identity evidence across
    # shared/expanded graph edges. Preserve existing narrow reference guards
    # rather than treating lexical overlap as proof of a link.
    if graph_mode and any(
        unit.references or unit.reference_lookup_only
        for action in plan.actions
        if isinstance(action, WriteAction)
        for unit in action.units
    ):
        raise ValueError("Shared/expanded referenced Core facts need reviewed identity provenance")
    # Check typed dispositions, negative/sensitive scopes and complete coverage
    # BEFORE lexical evidence, so a later ambiguous candidate cannot be hidden
    # behind an earlier unrelated wrong lexical mapping.
    claimed_helpers: set[tuple[int, int]] = set()
    for index, ordinal in claimed_pairs:
        action_index, unit_index, fact_index = owners_by_ordinal[ordinal]
        action = plan.actions[action_index]
        unit = action.units[unit_index]
        original = facts_by_ordinal[ordinal]
        # Let the source-veto see the lexical name chosen by Core, never
        # confuse transient {{ref:N}} placeholders with grounded identity.
        lexical = original
        for ref_index, ref in enumerate(unit.references):
            lexical = lexical.replace(f"{{{{ref:{ref_index}}}}}", ref.mention)
        if context.verified_inherited_event is not None:
            from .scoped_event_evidence import validate_event_target_fact

            validate_event_target_fact(
                source,
                context.candidates[index],
                unit,
                lexical,
                context.verified_inherited_event,
            )
        if context.candidates[index].kind == "property":
            other_subjects = tuple(
                role.span.text
                for other_index, other in enumerate(context.candidates)
                if other_index != index and other.kind == "property"
                for role in other.roles
                if role.role == "subject"
            )
            lexical = validate_subject_property_fact(
                source,
                context.candidates[index],
                unit,
                lexical,
                other_source_subjects=other_subjects,
                inherited_subject=context.verified_inherited_subject,
            )
        veto_unsafe_literal_match(
            source, context, index, lexical, canonical_binding=canonical_binding
        )
        if unit.references:
            if len(unit.facts) == 1:
                if context.candidates[index].kind == "relationship":
                    validate_one_mutual_relationship_fact(
                        source, context.candidates[index], plan, action_index, unit_index
                    )
                elif len(unit.references) == 1:
                    validate_one_named_participant_fact(
                        source,
                        context.candidates[index],
                        plan,
                        action_index,
                        unit_index,
                        canonical_binding=canonical_binding,
                    )
                else:
                    validate_two_named_participant_fact(
                        source, context.candidates[index], plan, action_index, unit_index
                    )
                if fact_index != 0:
                    raise ValueError("Grouped source claim has wrong Core fact")
            elif len(unit.facts) == 2:
                validate_two_sequential_contacts(context, plan, action_index, unit_index)
                if index != fact_index:
                    raise ValueError("Sequential Core facts are swapped across source candidates")
            else:
                raise ValueError("Unreviewed linked Core write shape")
            for reference in unit.references:
                helper_key = action_index, reference.target_index
                if len(unit.facts) == 2 and fact_index != 0:
                    continue  # These helpers were already claimed by first fact.
                if helper_key in claimed_helpers:
                    raise ValueError("Core participant helper is used by multiple source facts")
                claimed_helpers.add(helper_key)
    for action_index, action in enumerate(plan.actions):
        if isinstance(action, WriteAction):
            for unit_index, unit in enumerate(action.units):
                if unit.reference_lookup_only and (action_index, unit_index) not in claimed_helpers:
                    raise ValueError("Unclaimed canonical reference helper in Core plan")


def review_candidate_coverage(
    source: str,
    context: CoreCandidateContext,
    plan: RequestPlan,
    manifest: CoreCandidateCoverageManifest,
    readback: CandidateFactReadback,
) -> CoreCandidateCoverageReview:
    """Correlate checked plan claims with verified Markdown markers, not model guesses.

    Physically observed facts are still not independently checked for semantic
    equivalence to their source candidate. Pending candidates stay visible even
    if the ordinary Core application reports request-level completion.
    """
    validate_candidate_coverage_manifest(source, context, plan, manifest)
    if not isinstance(readback, CandidateFactReadback) or (
        readback.candidate_ids != tuple(c.candidate_id for c in context.candidates)
        or readback.candidate_coverage != "unverified"
        or readback.safe_to_report_all_candidates_complete
    ):
        raise ValueError("Readback does not match unverified candidate context")
    statuses = {fact.ordinal: fact.status for fact in readback.persisted_facts}
    claimed = {
        ordinal
        for claim in manifest.claims
        if claim.disposition == "planned_fact"
        for ordinal in (
            claim.fact_ordinals if claim.fact_ordinals is not None else (claim.fact_ordinal,)
        )
    }
    if claimed - statuses.keys():
        raise ValueError("Core write receipts missing planned fact ordinals")
    items: list[CoreCandidateCoverageItem] = []
    pending: list[str] = []
    for claim in manifest.claims:
        if claim.disposition == "pending":
            pending.append(claim.candidate_id)
            items.append(
                CoreCandidateCoverageItem(claim.candidate_id, "pending", None, claim.pending_reason)
            )
        else:
            mapped = (
                claim.fact_ordinals if claim.fact_ordinals is not None else (claim.fact_ordinal,)
            )
            verified = all(statuses.get(ordinal) == "verified_in_markdown" for ordinal in mapped)
            state = "physically_written_claim" if verified else "planned_unverified"
            if not verified:
                pending.append(claim.candidate_id)
            items.append(
                CoreCandidateCoverageItem(
                    claim.candidate_id,
                    state,
                    mapped[0] if len(mapped) == 1 else None,
                    None,
                    mapped if claim.fact_ordinals is not None else None,
                )
            )
    return CoreCandidateCoverageReview(
        tuple(items),
        tuple(pending),
        candidate_semantics_verified=False,
        fully_accounted_for_structurally=True,
        safe_to_report_all_candidates_complete=False,
    )
