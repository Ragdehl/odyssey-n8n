"""Core-owned, read-only whole-message source coverage contract (P3 candidate).

This validates a model-suggested semantic source review against an unchanged
message and another independently proposed plan. No model output is identity
proof, temporal authority, a canonical RequestPlan, or mutation permission.
Consumers MUST still execute through Core's ordinary identity preflight/Writer.

This opt-in contract is intentionally separate from legacy candidate_coverage:
the latter represents Router-fragment source candidates, not whole-message
atomic facts. Do not activate it as a DEV/PROD write gate without adversarial
coverage review and integration with E2 authenticated identity and E3 delivery.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .source_provenance import (
    AnchoredEvidence,
    SourceEvidenceError,
    anchor_literal_evidence,
)
from .temporal import normalize_iso_date

_REF = re.compile(r"\{\{ref:(\d+)\}\}")
_MAX_SOURCE = 4096
_MAX_FACTS = 16


class WholeMessageCoverageError(ValueError):
    """No mutation may follow an incomplete or ungrounded full-source review."""


@dataclass(frozen=True, slots=True)
class ReviewedFullSourceFact:
    """Atomic reviewed meaning without any canonical identity or write authority."""

    source_quote: str
    text: str
    kind: str
    date: str | None
    reference_names: tuple[str, ...]
    dependency: int | None
    # Original-source character offsets, allowing many supporting spans per
    # fact and shared spans across independent facts without note-type logic.
    source_spans: tuple[tuple[int, int], ...] = ()


@dataclass(frozen=True, slots=True)
class ReviewedFullSource:
    """One immutable complete-source proof constrained to two model outputs."""

    source_digest: str
    proposal_digest: str
    reviewed_facts: tuple[ReviewedFullSourceFact, ...]
    capabilities: frozenset[str]

    @property
    def has_write_authority(self) -> bool:
        """Never make an LLM source review itself a write permit."""
        return False


def _digest(value: object) -> str:
    return hashlib.sha256(repr(value).encode("utf-8")).hexdigest()


def anchor_planned_source_evidence(
    original: str, proposal: Mapping[str, Any]
) -> tuple[AnchoredEvidence, ...]:
    """Core preflight of *all* Planner literal evidence before another GPT call.

    Scope-independent: no note type, app, number-of-actions branching or
    semantic authority. A model cannot assert that Core has anchored evidence
    before this function succeeds on the exact original message.
    """
    if not isinstance(original, str) or not original.strip() or len(original) > _MAX_SOURCE:
        raise WholeMessageCoverageError("Invalid unchanged original source")
    if not isinstance(proposal, Mapping):
        raise WholeMessageCoverageError("Invalid typed original-source proposal")
    facts = proposal.get("facts")
    if not isinstance(facts, list) or not 1 <= len(facts) <= _MAX_FACTS:
        raise WholeMessageCoverageError("Invalid original-source cardinality")
    anchored = []
    for fact in facts:
        if not isinstance(fact, Mapping) or not {
            "source_evidence",
            "source_evidence_fragments",
            "source_evidence_context",
            "source_evidence_fragment_contexts",
        }.issubset(fact):
            raise WholeMessageCoverageError("Missing typed original-source evidence")
        try:
            anchored.append(
                anchor_literal_evidence(
                    original,
                    fact["source_evidence"],
                    fact["source_evidence_fragments"],
                    primary_context=fact["source_evidence_context"],
                    supporting_contexts=fact["source_evidence_fragment_contexts"],
                )
            )
        except SourceEvidenceError as error:
            raise WholeMessageCoverageError(str(error)) from error
    # No mutations to the untrusted proposal and no canonical identity claims.
    return tuple(anchored)


def validate_whole_message_coverage(
    source: str,
    proposal: Mapping[str, Any],
    review: Mapping[str, Any],
    capabilities: Sequence[str],
    *,
    verified_relationship_members: Sequence[str] = (),
    verified_relationship_groups: Sequence[tuple[str, tuple[str, ...]]] = (),
    core_anchored_evidence: bool = False,
) -> ReviewedFullSource:
    """Verify semantic proposal/reviewer agreement and literal source provenance.

    Scope, dates, occurrence order, exact source spans, fact cardinality,
    symbolic reference slots and dependencies must agree; the repository
    independently grounds all identities and application-specific permissions.
    No source-only model-generated canonical name or ID can be bound here.
    """
    if not isinstance(source, str) or not source.strip() or len(source) > _MAX_SOURCE:
        raise WholeMessageCoverageError("Invalid unchanged original source")
    if not isinstance(proposal, Mapping) or not isinstance(review, Mapping):
        raise WholeMessageCoverageError("Typed proposal and review required")
    cap = frozenset(capabilities)
    if not cap or not cap.issubset({"core", "tasks", "temporal"}):
        raise WholeMessageCoverageError("Invalid capability scope")
    facts = proposal.get("facts")
    judgments = review.get("facts")
    if (
        review.get("approved") is not True
        or review.get("complete") is not True
        or proposal.get("unresolved")
        or not isinstance(facts, list)
        or not isinstance(judgments, list)
        or not 1 <= len(facts) == len(judgments) <= _MAX_FACTS
    ):
        raise WholeMessageCoverageError("Whole message not completely accounted for")
    entities = proposal.get("entities")
    if not isinstance(entities, list) or not all(isinstance(e, Mapping) for e in entities):
        raise WholeMessageCoverageError("Invalid entity evidence")
    verified = set(verified_relationship_members)
    if not all(isinstance(name, str) and name.strip() for name in verified):
        raise WholeMessageCoverageError("Invalid relationship evidence")
    # Core supplies each source-quoted relation AND its verified members.
    # Names known somewhere in SELF do not prove membership in every fact.
    groups = tuple(verified_relationship_groups)
    if len(groups) > 8 or any(
        not isinstance(phrase, str)
        or phrase not in source
        or not isinstance(members, (tuple, list))
        or not members
        or not all(isinstance(name, str) and name in verified for name in members)
        for phrase, members in groups
    ):
        raise WholeMessageCoverageError("Invalid source-bound relationship groups")
    output: list[ReviewedFullSourceFact] = []
    evidence_spans: list[tuple[int, int]] = []
    anchored = anchor_planned_source_evidence(source, proposal) if core_anchored_evidence else ()

    for index, (fact, claim) in enumerate(zip(facts, judgments, strict=True)):
        if not isinstance(fact, Mapping) or not isinstance(claim, Mapping):
            raise WholeMessageCoverageError("Missing atomic fact shape")
        requested = fact.get("source_evidence")
        quote = requested if core_anchored_evidence else claim.get("source_quote")
        if core_anchored_evidence and "source_quote" in claim:
            raise WholeMessageCoverageError("Reviewer cannot author canonical evidence")
        text = claim.get("reviewed_text")
        kind = fact.get("kind")
        date = fact.get("date")
        if (
            not isinstance(requested, str)
            or not requested.strip()
            or not isinstance(quote, str)
            or not quote.strip()
            or len(quote) > _MAX_SOURCE
            or (not core_anchored_evidence and requested not in quote)
            or (not core_anchored_evidence and quote not in source)
            or not isinstance(text, str)
            or not text.strip()
            or len(text) > 320
            or claim.get("ordinal") != index
            or isinstance(claim.get("ordinal"), bool)
            or claim.get("kind") != kind
            or claim.get("date") != date
            or claim.get("supported") is not True
            or fact.get("needs_clarification") is not False
            or kind not in {"record", "task"}
        ):
            raise WholeMessageCoverageError("Atomic source evidence mismatch")
        if kind == "record" and "core" not in cap:
            raise WholeMessageCoverageError("Core operation omitted from route")
        if kind == "task" and "tasks" not in cap:
            raise WholeMessageCoverageError("Task without routing scope")
        if date is not None:
            try:
                normalize_iso_date(date)
            except ValueError as error:
                raise WholeMessageCoverageError("Invalid canonical date") from error
        # The exact same generic Core provenance check ran BEFORE semantic
        # review. Re-evaluate from untrusted data here to defend the write gate.
        if core_anchored_evidence:
            anchor = anchored[index]
        else:
            try:
                anchor = anchor_literal_evidence(source, quote)
            except SourceEvidenceError as error:
                raise WholeMessageCoverageError(str(error)) from error
        span = anchor.all_spans[0]
        support_spans = anchor.all_spans
        # Multiple facts may quote overlapping spans only if each records an
        # independently meaningful source assertion. This gate records evidence,
        # not a grammar-dependent assertion that overlaps are always invalid.
        evidence_spans.append(span)
        names = claim.get("reference_names")
        if (
            not isinstance(names, list)
            or len(names) > 8
            or len(set(names)) != len(names)
            or any(not isinstance(n, str) or not n.strip() or len(n) > 128 for n in names)
        ):
            raise WholeMessageCoverageError("Invalid typed person references")
        valid_names = {n for n in fact.get("participants", []) if isinstance(n, str)} | {
            e.get("mention") for e in entities if isinstance(e.get("mention"), str)
        }
        if not set(names).issubset(valid_names | verified):
            raise WholeMessageCoverageError("Source reviewer invented a participant")
        for name in names:
            if (
                not re.search(r"(?<!\w)" + re.escape(name) + r"(?!\w)", source, re.IGNORECASE)
                and name not in verified
            ):
                raise WholeMessageCoverageError("Participant absent from original source")
        if groups:
            # Relationship membership must be evidenced by THIS atomic fact's
            # planner-anchored primary assertion, never by a broader quote
            # selected by the second (untrusted) reviewer. Supporting context
            # and prior sentences are not a fact-to-fact identity handoff.
            # Elliptical continuations can be saved literally without links.
            direct = {name for phrase, members in groups if phrase in requested for name in members}
            for name in names:
                if (
                    name in verified
                    and name not in direct
                    and not re.search(
                        r"(?<!\w)" + re.escape(name) + r"(?!\w)", quote, re.IGNORECASE
                    )
                ):
                    raise WholeMessageCoverageError(
                        "Verified group member unsupported by this atomic source fact"
                    )
        references = [int(x) for x in _REF.findall(text)]
        if sorted(references) != list(range(len(names))) or len(references) != len(names):
            raise WholeMessageCoverageError("Symbolic Core references missing or repeated")
        if "[[" in text or "]]" in text or "<!--" in text:
            raise WholeMessageCoverageError("Source model tried to emit canonical Markdown")
        dependency = fact.get("dependent_on_fact_index")
        if dependency is not None and (
            not isinstance(dependency, int)
            or isinstance(dependency, bool)
            or not 0 <= dependency < index
        ):
            raise WholeMessageCoverageError("Invalid cross-operation dependency")
        if dependency is not None and not (set(names) & set(output[dependency].reference_names)):
            raise WholeMessageCoverageError("Cross-operation identity handoff has no shared person")
        output.append(
            ReviewedFullSourceFact(
                quote, text, kind, date, tuple(names), dependency, tuple(support_spans)
            )
        )
    if evidence_spans != sorted(evidence_spans):
        raise WholeMessageCoverageError("Fact evidence order differs from source order")
    return ReviewedFullSource(
        hashlib.sha256(source.encode("utf-8")).hexdigest(),
        _digest(proposal),
        tuple(output),
        cap,
    )
