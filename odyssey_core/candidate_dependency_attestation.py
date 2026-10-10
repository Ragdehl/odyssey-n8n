"""Core-owned source-to-plan dependency attestation for coordinated facts.

This verifies a bounded syntactic semantic correspondence across two
independently compiled plans. It never substitutes for Core's canonical
identity resolution, full-source coverage, or physical Markdown readback.
Neither Router's proposals nor lexical overlap confer write authority.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from hashlib import sha256

from .candidate_context import CoreCandidateContext
from .candidate_dependent_scope import preview_dependent_clause_scopes
from .candidate_semantic_veto import normalized_words
from .request_planning import KnowledgeUnit, RequestPlan, WriteAction


class DependentFactAttestationError(ValueError):
    """Source/plan dependency is not independently demonstrated."""


@dataclass(frozen=True, slots=True)
class CoreDependentFactAttestation:
    """Immutable read-only result bound to full source and both Core plans."""

    source_digest: str
    plan_digests: tuple[str, str]
    candidate_ids: tuple[str, str]
    relation: str
    source_antecedent: str
    plan_referent: str
    canonical_reuse_verified: bool = False
    may_write_notes: bool = False


def _words_equal(first: str | None, second: str | None) -> bool:
    """Compare ordered, accent-normalized identity tokens, never word bags."""
    if not first or not second:
        return False

    def tokens(value: str) -> tuple[str, ...]:
        normalized = unicodedata.normalize("NFKD", value.casefold())
        plain = "".join(c for c in normalized if not unicodedata.combining(c))
        return tuple(re.findall(r"[^\\W_]+", plain))

    return tokens(first) == tokens(second)


def _unpack_plan(plan: RequestPlan) -> tuple[KnowledgeUnit, tuple[KnowledgeUnit, ...]]:
    """Read exactly one factual write and distinct reference-only helpers."""
    if not isinstance(plan, RequestPlan) or len(plan.actions) != 1:
        raise DependentFactAttestationError("Expected independently compiled Core plan")
    action = plan.actions[0]
    if not isinstance(action, WriteAction):
        raise DependentFactAttestationError("Core planner did not choose a write")
    active = tuple(unit for unit in action.units if not unit.reference_lookup_only)
    helpers = tuple(unit for unit in action.units if unit.reference_lookup_only)
    if (
        len(active) != 1
        or action.units[0] != active[0]
        or len(active[0].facts) != 1
        or len(action.units) != len(helpers) + 1
        or any(helper.facts or helper.references for helper in helpers)
        or active[0].intent != "record"
        or active[0].properties
        or active[0].tag_changes
        or active[0].destination_type is not None
        or active[0].force_create
        or len(active[0].references) != len(helpers)
        or {ref.target_index for ref in active[0].references} != set(range(1, len(helpers) + 1))
        or any(f"{{{{ref:{index}}}}}" not in active[0].facts[0] for index in range(len(helpers)))
        or "{{ref:" in active[0].facts[0].replace("{{ref:0}}", "").replace("{{ref:1}}", "")
    ):
        raise DependentFactAttestationError("Unreviewed Core target or reference mechanics")
    return active[0], helpers


def _roles(unit, role: str) -> tuple[str, ...]:
    return tuple(item.span.text for item in unit.explicit_roles if item.role == role)


def _single(values: tuple[str, ...], *, label: str) -> str:
    if len(values) != 1 or not values[0].strip():
        raise DependentFactAttestationError("No unique original " + label)
    return values[0]


def _lexicalized(unit: KnowledgeUnit) -> str:
    value = unit.facts[0]
    for index, ref in enumerate(unit.references):
        value = value.replace(f"{{{{ref:{index}}}}}", ref.mention)
    return value


def _shared_subject_property(
    units,
    current: tuple[KnowledgeUnit, KnowledgeUnit],
    helpers: tuple[tuple[KnowledgeUnit, ...], ...],
) -> tuple[str, str]:
    """Prove original inherited subject and two nonidentical attributes."""
    first, second = units
    first_write, next_write = current
    first_subject = _single(_roles(first, "subject"), label="property subject")
    inherited = tuple(r for r in second.inherited_roles if r.role == "subject")
    if (
        len(inherited) != 1
        or inherited[0].span.text != first_subject
        or inherited[0].source_candidate_id != first.candidate_id
        or not all(_words_equal(first_write.target.query, unit.target.query) for unit in current)
        or first_write.target != next_write.target
        or not _words_equal(first_write.target.query, first_subject)
        or first_write.target.type is None
        or _single(_roles(first, "predicate"), label="first predicate")
        != _single(
            tuple(r.span.text for r in second.inherited_roles if r.role == "predicate"),
            label="inherited predicate",
        )
    ):
        raise DependentFactAttestationError("Property subject or inherited predicate mismatched")
    first_object = _single(_roles(first, "object"), label="first property object")
    second_object = _single(_roles(second, "object"), label="second property object")
    first_location = _single(_roles(first, "location"), label="first location")
    second_location = _single(_roles(second, "location"), label="second location")
    if (
        _words_equal(first_location, second_location)
        or normalized_words(first_object) - {"un", "una", "el", "la"} == frozenset()
        or normalized_words(second_object)
        not in (
            frozenset({"otro"}),
            frozenset({"otra"}),
            frozenset({"otros"}),
            frozenset({"otras"}),
        )
    ):
        raise DependentFactAttestationError("No uniquely signaled other-instance relation")
    first_predicate = _single(_roles(first, "predicate"), label="first predicate")
    if not all(
        unit.facts[0].strip().casefold().startswith(first_predicate.casefold() + " ")
        for unit in current
    ):
        # A shared target cannot legitimize an extra, ungrounded grammatical
        # subject smuggled into either independent fact.
        raise DependentFactAttestationError("Property fact has an unverified subject prefix")
    previous = normalized_words(_lexicalized(first_write))
    following = normalized_words(_lexicalized(next_write))
    head = normalized_words(first_object) - {"un", "una", "el", "la"}
    if (
        not head <= previous
        or not head <= following
        or not normalized_words(first_location) <= previous
        or not normalized_words(second_location) <= following
        or not normalized_words(second_object) <= following
        or not normalized_words(first_location).isdisjoint(following)
        or not normalized_words(second_location).isdisjoint(previous)
    ):
        raise DependentFactAttestationError("Property content or location lost or swapped")
    if len(helpers[0]) > 1 or helpers[1]:
        raise DependentFactAttestationError("Unexpected project attribute identity helpers")
    if helpers[0]:
        if (
            len(first_write.references) != 1
            or not _words_equal(first_write.references[0].mention, first_location)
            or not _words_equal(helpers[0][0].target.query, first_location)
        ):
            raise DependentFactAttestationError("Property component helper not source-grounded")
    return first_subject, first_write.target.query


def _unique_previous_typed_identity(
    units,
    current: tuple[KnowledgeUnit, KnowledgeUnit],
    helpers: tuple[tuple[KnowledgeUnit, ...], ...],
) -> tuple[str, str]:
    """Require one preceding named document and an exact Core referent match."""
    first, second = units
    first_write, next_write = current
    antecedent = _single(_roles(first, "subject"), label="preceding subject")
    pronoun = _single(_roles(second, "reference"), label="anaphoric reference")
    other_people = _roles(second, "participants")
    if (
        len(first.explicit_roles) < 3
        or len(second.unresolved_references) != 1
        or second.unresolved_references[0].text != pronoun
        or len(first.inherited_roles) != 0
        or len(first_write.references) != 0
        or helpers[0]
        or not first_write.target.type
        or first_write.target.type == "calendar_day"
        or not _words_equal(first_write.target.query, antecedent)
        or len(next_write.references) != 2
        or len(helpers[1]) != 2
        or next_write.target.type != "calendar_day"
        or len(other_people) != 1
        or not next_write.fact_temporal_anchors
        or not first_write.fact_temporal_anchors
        or not first_write.fact_temporal_anchors[0]
        or not next_write.fact_temporal_anchors[0]
        or first_write.fact_temporal_anchors[0][0].date
        >= next_write.fact_temporal_anchors[0][0].date
    ):
        raise DependentFactAttestationError("Document temporal/identity source is not unique")
    first_document_ref, person_ref = next_write.references
    doc_helper, person_helper = helpers[1]
    if (
        not _words_equal(first_document_ref.mention, antecedent)
        or not _words_equal(doc_helper.target.query, first_write.target.query)
        or doc_helper.target.type != first_write.target.type
        or not _words_equal(person_ref.mention, other_people[0])
        or not _words_equal(person_helper.target.query, other_people[0])
        or person_helper.target.type != "person"
        or not normalized_words(_single(_roles(first, "predicate"), label="first predicate"))
        <= normalized_words(first_write.facts[0])
        or not normalized_words(_single(_roles(second, "predicate"), label="second predicate"))
        <= normalized_words(next_write.facts[0])
        or not normalized_words(other_people[0]) <= normalized_words(_lexicalized(next_write))
    ):
        raise DependentFactAttestationError("Core reference helper does not match source identity")
    # The antecedent remains *lexical* here. The ordinary canonical
    # target resolver must still prove the actual stable note ID.
    return antecedent, doc_helper.target.query


def attest_two_dependent_core_plans(
    source: str, context: CoreCandidateContext, plans: tuple[RequestPlan, ...]
) -> CoreDependentFactAttestation:
    """Cross-check original source dependencies against independently made plans.

    Provenance is grounded by the existing Core clause-scoping validator;
    the original source is never silently rewritten. A successful check
    records evidence only. It does NOT certify canonical target identity,
    unlock the ordinary original-source coverage guard or authorize writes.
    """
    preview = preview_dependent_clause_scopes(source, context)
    if not isinstance(plans, tuple) or len(plans) != 2 or len(preview.units) != 2:
        raise DependentFactAttestationError("Two independently compiled plans required")
    first, second = (_unpack_plan(plan) for plan in plans)
    units = preview.units
    candidate_kinds = tuple(c.kind for c in context.candidates)
    if candidate_kinds == ("property", "property"):
        relation = "shared_subject"
        antecedent, referent = _shared_subject_property(
            units, (first[0], second[0]), (first[1], second[1])
        )
    elif candidate_kinds == ("occurrence", "occurrence"):
        relation = "source_anaphora"
        antecedent, referent = _unique_previous_typed_identity(
            units, (first[0], second[0]), (first[1], second[1])
        )
    else:
        raise DependentFactAttestationError("Unreviewed heterogeneous source dependency")
    return CoreDependentFactAttestation(
        sha256(source.encode("utf-8")).hexdigest(),
        tuple(sha256(repr(p).encode("utf-8")).hexdigest() for p in plans),
        tuple(unit.candidate_id for unit in units),
        relation,
        antecedent,
        referent,
    )


def review_persisted_dependency(
    source: str,
    context: CoreCandidateContext,
    plans: tuple[RequestPlan, ...],
    evidence: CoreDependentFactAttestation,
    results: tuple[object, object],
    repository: object,
) -> CoreDependentFactAttestation:
    """Verify a previously attested relation against actual canonical Notes.

    This post-write audit is deliberately separate from write permission.
    The antecedent must still be a single, persistent canonical Note; for
    shared-subject facts the two Core executions must change that same note.
    For source anaphora the second *newly recorded* Day fact must contain
    a wikilink to the precise note ID physically affected by the first
    execution, not merely a similar name or an unrelated previous backlink.

    Raises:
        DependentFactAttestationError: Any stale, missing, ambiguous or
            inconsistent source, plan, canonical target or fact marker.
    """
    import re

    from .application import ApplicationResult, ApplicationStatus
    from .notes import parse_note
    from .storage import VaultRepository

    current = attest_two_dependent_core_plans(source, context, plans)
    if current != evidence:
        raise DependentFactAttestationError("Stale or forged dependency proof")
    if (
        not isinstance(repository, VaultRepository)
        or not isinstance(results, tuple)
        or len(results) != 2
        or any(
            not isinstance(result, ApplicationResult)
            or result.status is not ApplicationStatus.COMPLETED
            or len(result.affected_stable_note_ids) != 1
            for result in results
        )
    ):
        raise DependentFactAttestationError("Need two completed single-target canonical writes")

    notes = []
    for path in repository.list_markdown_paths():
        parsed = parse_note(repository.read_text(path))
        identity = parsed.metadata.get("id")
        if isinstance(identity, str):
            notes.append((identity, path, parsed))
    by_id = {}
    for identity, path, parsed in notes:
        if identity in by_id:
            raise DependentFactAttestationError("Duplicate canonical note stable ID")
        by_id[identity] = (path, parsed)

    first_id = results[0].affected_stable_note_ids[0]
    second_id = results[1].affected_stable_note_ids[0]
    if first_id not in by_id or second_id not in by_id:
        raise DependentFactAttestationError("Written canonical note is missing")
    source_path, first_note = by_id[first_id]
    destination_path, second_note = by_id[second_id]
    if first_note.metadata.get("type") != plans[0].actions[0].units[0].target.type:
        raise DependentFactAttestationError("First target changed canonical type")

    for result in results:
        # Facts have a Core request provenance marker which binds them
        # to THIS model result, not a pre-existing similarly worded note.
        raw = repository.read_text(by_id[result.affected_stable_note_ids[0]][0])
        matches = re.findall(
            r"(?m)^- (.+)\n  <!-- odyssey:fact request="
            + re.escape(result.request_id)
            + r" ordinal=0\b[^\n]* -->",
            raw,
        )
        if len(matches) != 1:
            raise DependentFactAttestationError("Unique actual Core fact marker not found")
    if evidence.relation == "shared_subject":
        if first_id != second_id or source_path != destination_path:
            raise DependentFactAttestationError("Shared source subject changed canonical identity")
    elif evidence.relation == "source_anaphora":
        # Require the wikilink in the CURRENT second fact, not anywhere
        # else in the Day (and not only a coincidentally equal display name).
        raw_day = repository.read_text(destination_path)
        fact = re.findall(
            r"(?m)^- (.+)\n  <!-- odyssey:fact request="
            + re.escape(results[1].request_id)
            + r" ordinal=0\b[^\n]* -->",
            raw_day,
        )
        destination = source_path.removesuffix(".md")
        if (
            second_note.metadata.get("type") != "calendar_day"
            or first_id == second_id
            or len(fact) != 1
            or not re.search(r"\[\[" + re.escape(destination) + r"(?:\||\]\])", fact[0])
        ):
            raise DependentFactAttestationError(
                "Second fact does not link same canonical antecedent"
            )
    else:
        raise DependentFactAttestationError("Unrecognized dependency relation")
    return CoreDependentFactAttestation(
        evidence.source_digest,
        evidence.plan_digests,
        evidence.candidate_ids,
        evidence.relation,
        evidence.source_antecedent,
        evidence.plan_referent,
        canonical_reuse_verified=True,
        may_write_notes=False,
    )
