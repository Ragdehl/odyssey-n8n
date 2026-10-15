"""Opt-in Core-only preflight for source-candidate coverage of a written plan.

A proposed source interpretation cannot silently disappear when Core plans a
subset. This verifies explicit accounting for every candidate and every planned
atomic fact *before* normal Core execution; only actual Markdown markers can
confirm persistence later. Claims must be independently reviewed by Core, never
copied directly from Router. Structural checks are not semantic attestation.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from typing import Literal

from .candidate_context import CoreCandidateContext
from .candidate_correction_chain import correction_chain
from .candidate_fact_readback import CandidateFactReadback
from .candidate_multi_participant import (
    validate_one_named_participant_fact,
    validate_two_named_participant_fact,
)
from .candidate_mutual_relation import validate_one_mutual_relationship_fact
from .candidate_property_evidence import validate_subject_property_fact
from .candidate_semantic_veto import veto_unsafe_literal_match
from .candidate_sequential_contacts import validate_two_sequential_contacts
from .candidate_speaker_evidence import CoreSpeakerEvidence, validate_speaker_evidence
from .request_planning import RequestPlan, WriteAction, plan_fact_ordinals

MAX_COVERAGE_CLAIMS = 26
MAX_COVERAGE_FACTS = 128
PENDING_REASONS = frozenset(
    {
        "ambiguous_identity",
        "needs_clarification",
        "needs_capability",
        "unsupported_scope",
        "superseded_by_correction",
    }
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
    speaker_evidence: tuple[CoreSpeakerEvidence, ...] = ()


@dataclass(frozen=True, slots=True)
class CoreCandidateCoverageItem:
    """State structural mapping and independently observed persistence only."""

    candidate_id: str
    status: Literal["physically_written_claim", "planned_unverified", "pending", "superseded"]
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
    speaker_evidence: tuple[CoreSpeakerEvidence, ...] = (),
) -> CoreCandidateCoverageManifest:
    """Build a plan-bound candidate checklist after explicit Core review.

    This builder does not infer candidate ownership or decide dispositions. The
    caller must supply every candidate claim; invalid or incomplete claims raise.
    """
    manifest = CoreCandidateCoverageManifest(
        _digest(source), _digest(repr(plan)), claims, speaker_evidence
    )
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
    if (
        context.hybrid_interpretation_mode
        and any(candidate.kind == "task" for candidate in context.candidates)
        and any(isinstance(action, WriteAction) for action in plan.actions)
    ):
        raise ValueError("Hybrid task needs specialized Tasks capability, not an ordinary Day fact")
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
    speaker_refs = validate_speaker_evidence(source, context, plan, manifest.speaker_evidence)
    speaker_proofs = {proof.fact_ordinal: proof for proof in manifest.speaker_evidence}
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
                or (
                    claim.pending_reason == "superseded_by_correction"
                    and (
                        context.verified_correction_temporal is None
                        or not context.hybrid_interpretation_mode
                        or correction_chain(context.candidates) is None
                        or index >= len(context.candidates) - 1
                        or any(
                            (other.disposition, other.pending_reason)
                            != ("pending", "superseded_by_correction")
                            for other in claims[:-1]
                        )
                        or claims[-1].disposition != "planned_fact"
                        or claims[-1].fact_ordinal != 0
                        or plan_fact_ordinals(plan) != ((0,),)
                    )
                )
            ):
                raise ValueError("Pending candidate requires a compatible unresolved reason")
            continue
        if claim.disposition != "planned_fact":
            raise ValueError("Unknown coverage disposition")
        if candidate.state == "ambiguous_identity":
            raise ValueError("Ambiguous identity cannot be claimed as a planned write")
        correction_final = (
            context.verified_correction_temporal is not None
            and context.hybrid_interpretation_mode
            and correction_chain(context.candidates) is not None
            and index == len(context.candidates) - 1
        )
        sensitive_literal = (
            context.hybrid_interpretation_mode and context.verified_sensitive_temporal is not None
        )
        if (
            (
                candidate.kind in {"conditional", "negative"}
                or any(
                    role.role in {"condition", "polarity", "replacement", "modality"}
                    for role in candidate.roles
                )
            )
            and not correction_final
            and not sensitive_literal
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
    # N:M reference-bearing plans need source-group evidence. Outside an exact
    # scoped group, retain the established refusal rather than treating a graph
    # edge as canonical identity proof.
    if (
        graph_mode
        and any(
            unit.references or unit.reference_lookup_only
            for action in plan.actions
            if isinstance(action, WriteAction)
            for unit in action.units
        )
        and not context.scoped_route_source
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
        # Approximate source time must remain literal in its own fact.
        # The approximate evidence cannot become an exact instant or be
        # discarded because an independently dated sibling has a clock.
        approximate_roles = [
            role.span for role in context.candidates[index].roles if role.role == "time_approx"
        ]
        if approximate_roles:
            from .temporal_approximation_handoff import TEMPORAL_APPROXIMATE_LITERAL

            temporal = context.verified_route_temporal

            def proven_approximate_span(
                span, lexical=lexical, temporal=temporal, unit=unit
            ) -> bool:
                if span.text not in lexical or temporal is None:
                    return False
                if any(
                    item.kind == TEMPORAL_APPROXIMATE_LITERAL and item.source_text == span.text
                    for item in temporal.evidence
                ):
                    return True
                # E2: an approximate *daypart* can accompany a proven
                # exact-date source phrase without becoming an exact hour.
                # It must be inside that same original Temporal quote and
                # attached to a matching, exclusively dated Day fact.
                if unit.target.type != "calendar_day" or len(unit.fact_temporal_anchors) != 1:
                    return False
                for item in temporal.temporal_references():
                    anchor = item.temporal_anchor()
                    start = source.find(item.source_text)
                    if (
                        anchor.time is None
                        and unit.target.query == anchor.date
                        and start >= 0
                        and start <= span.start < span.end <= start + len(item.source_text)
                        and len(unit.fact_temporal_anchors[0]) == 1
                        and unit.fact_temporal_anchors[0][0].date == anchor.date
                        and unit.fact_temporal_anchors[0][0].time is None
                    ):
                        return True
                return False

            if any(not proven_approximate_span(span) for span in approximate_roles):
                raise ValueError(
                    "Approximate time must be represented literally with Core Temporal provenance"
                )
        if context.verified_sensitive_temporal is not None:
            from .candidate_sensitive_statement import validate_sensitive_group_statement

            validate_sensitive_group_statement(source, context, plan, claims)
        if context.verified_correction_temporal is not None:
            from .candidate_corrected_plan import validate_corrected_plan_fact

            validate_corrected_plan_fact(source, context, index, unit, lexical, claims)
        if context.verified_inherited_event is not None:
            from .scoped_event_evidence import validate_event_target_fact

            validate_event_target_fact(
                source,
                context.candidates[index],
                unit,
                lexical,
                context.verified_inherited_event,
            )
        property_of_mixed_group = (
            context.hybrid_interpretation_mode
            and context.candidates[index].kind == "property"
            and len(unit.facts) > 1
            and any(other.kind != "property" for other in context.candidates)
            and not unit.references
            and not unit.reference_lookup_only
            and len(claimed_pairs) == len(fact_ordinals)
            and len({claim_ordinal for _, claim_ordinal in claimed_pairs}) == len(fact_ordinals)
        )
        # Independent properties and occurrences can be stored in the SAME
        # canonical Note using separate Core facts. The property proof must
        # inspect only its OWN fact/anchor, not an unrelated second event.
        # The original plan, graph, targets and readback remain unmodified.
        property_unit = unit
        if property_of_mixed_group:
            own_anchors = (
                unit.fact_temporal_anchors[fact_index] if unit.fact_temporal_anchors else ()
            )
            if own_anchors:
                raise ValueError("Property claim includes another event's time")
            property_unit = replace(
                unit,
                facts=(unit.facts[fact_index],),
                fact_temporal_anchors=(),
            )
        if (
            context.candidates[index].kind == "property"
            and len(unit.facts) > 1
            and not property_of_mixed_group
        ):
            from .candidate_grouped_property import validate_shared_subject_property

            lexical = validate_shared_subject_property(
                source,
                context,
                index,
                unit,
                lexical,
            )
        elif context.candidates[index].kind == "property":
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
                property_unit,
                lexical,
                other_source_subjects=other_subjects,
                inherited_subject=context.verified_inherited_subject,
            )
        independent_actor_helper: int | None = None
        if (
            context.hybrid_interpretation_mode
            and context.verified_route_temporal is not None
            and len(unit.facts) > 1
            and unit.references
            and all(candidate.kind == "occurrence" for candidate in context.candidates)
            and not any(
                role.role == "participants"
                for candidate in context.candidates
                for role in candidate.roles
            )
        ):
            from .candidate_independent_linked_events import (
                validate_independent_linked_event_fact,
            )

            independent_actor_helper = validate_independent_linked_event_fact(
                source, context, plan, action_index, unit_index, fact_index, index
            )
        grouped_participant_helpers: tuple[int, ...] | None = None
        if context.scoped_route_source and (
            (
                len(unit.facts) > 1
                and any(
                    role.role == "participants"
                    for candidate in context.candidates
                    for role in candidate.roles
                )
            )
            or (
                context.hybrid_interpretation_mode
                and context.candidates[index].kind == "occurrence"
                and not any(role.role == "reference" for role in context.candidates[index].roles)
                and (
                    any(role.role == "participants" for role in context.candidates[index].roles)
                    or any(
                        edge.role == "participants" for edge in context.candidates[index].inherits
                    )
                )
            )
        ):
            # General Core source-ownership proof: check each reviewed
            # candidate/fact independently, for any number of participants,
            # facts or independent named links. Never branch on a phrase,
            # name, two candidates or three total lookup/write units.
            from .candidate_group_participants import validate_group_participant_fact

            grouped_participant_helpers = validate_group_participant_fact(
                source,
                context,
                index,
                action,
                unit_index,
                unit,
                original,
                lexical,
            )
        if context.verified_sensitive_temporal is not None:
            pass  # Whole-source literal has its own strict N:1 validator.
        elif context.verified_group_temporal is not None:
            from .candidate_grouped_temporal import validate_grouped_dated_occurrence

            # The weekday is carried by the independently selected Day Note,
            # not duplicated in each fact text. The Temporal proof replaces
            # ONLY the local-token overlap veto, never independent review.
            validate_grouped_dated_occurrence(source, context, index, unit, lexical)
        else:
            veto_unsafe_literal_match(
                source, context, index, lexical, canonical_binding=canonical_binding
            )
        if independent_actor_helper is not None:
            helper_key = action_index, independent_actor_helper
            if helper_key in claimed_helpers:
                raise ValueError("The same linked actor helper owns two independent events")
            claimed_helpers.add(helper_key)
        elif ordinal in speaker_refs:
            # The same Core-reviewed speaker evidence is consumed by coverage
            # and canonical reference helper claiming; named-person validators
            # must not reinterpret synthetic 'yo' as a named entity.
            proof = speaker_proofs[ordinal]
            if proof.candidate_id != context.candidates[index].candidate_id:
                raise ValueError("Speaker proof belongs to another source candidate")
            helper_key = action_index, speaker_refs[ordinal][2]
            if helper_key in claimed_helpers:
                raise ValueError("Speaker reference helper has duplicated ownership")
            claimed_helpers.add(helper_key)
        elif unit.references and grouped_participant_helpers is None:
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
                        allow_independent_sibling_units=context.hybrid_interpretation_mode,
                    )
                elif context.hybrid_interpretation_mode:
                    raise ValueError(
                        "Hybrid multi-reference roles require general source-owned proof"
                    )
                else:
                    validate_two_named_participant_fact(
                        source, context.candidates[index], plan, action_index, unit_index
                    )
                if fact_index != 0:
                    raise ValueError("Grouped source claim has wrong Core fact")
            elif context.hybrid_interpretation_mode:
                # A language-specific two-contact pilot is NOT a normative
                # hybrid validation rule. Refuse links without appropriate
                # source-group ownership evidence rather than interpreting
                # a model-generated pair through fixed Spanish phrases.
                raise ValueError(
                    "Referenced Core facts require general per-fact source-owned participants"
                )
            elif len(unit.facts) == 2:
                # Legacy atomic-mode compatibility, not hybrid architecture.
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
        elif grouped_participant_helpers is not None:
            for helper_index in grouped_participant_helpers:
                helper_key = action_index, helper_index
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
            superseded = claim.pending_reason == "superseded_by_correction"
            if not superseded:
                pending.append(claim.candidate_id)
            items.append(
                CoreCandidateCoverageItem(
                    claim.candidate_id,
                    "superseded" if superseded else "pending",
                    None,
                    claim.pending_reason,
                )
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
