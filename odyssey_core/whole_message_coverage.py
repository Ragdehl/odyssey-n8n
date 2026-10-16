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


def validate_whole_message_coverage(
    source: str,
    proposal: Mapping[str, Any],
    review: Mapping[str, Any],
    capabilities: Sequence[str],
    *,
    verified_relationship_members: Sequence[str] = (),
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
    output: list[ReviewedFullSourceFact] = []
    evidence_spans: list[tuple[int, int]] = []
    for index, (fact, claim) in enumerate(zip(facts, judgments, strict=True)):
        if not isinstance(fact, Mapping) or not isinstance(claim, Mapping):
            raise WholeMessageCoverageError("Missing atomic fact shape")
        requested = fact.get("source_evidence")
        quote = claim.get("source_quote")
        text = claim.get("reviewed_text")
        kind = fact.get("kind")
        date = fact.get("date")
        if (
            not isinstance(requested, str)
            or not requested.strip()
            or not isinstance(quote, str)
            or not quote.strip()
            or len(quote) > _MAX_SOURCE
            or requested not in quote
            or quote not in source
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
        # A source review cannot map a fact to a wholly different sentence.
        occurrences = list(re.finditer(re.escape(quote), source))
        if len(occurrences) != 1:
            raise WholeMessageCoverageError("Source quote is ambiguous or absent")
        span = occurrences[0].span()
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
        output.append(ReviewedFullSourceFact(quote, text, kind, date, tuple(names), dependency))
    if evidence_spans != sorted(evidence_spans):
        raise WholeMessageCoverageError("Fact evidence order differs from source order")
    return ReviewedFullSource(
        hashlib.sha256(source.encode("utf-8")).hexdigest(),
        _digest(proposal),
        tuple(output),
        cap,
    )
