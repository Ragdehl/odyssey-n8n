"""E2-compatible proof of source-attested speaker participation for full messages.

The LLM may propose participation but CANNOT bind a note id. Two independent
reviewers must agree on fact, source span, role and assertion mode; a separate
trusted authenticated SELF binding remains necessary during Core write.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any

from .request_planning import KnowledgeReference, KnowledgeUnit, SelectionCriteria, WriteAction


class WholeMessageSpeakerError(ValueError):
    """A speaker role is unsupported, unsafe or contradictory."""


@dataclass(frozen=True, slots=True)
class AttestedSpeakerFact:
    ordinal: int
    role: str
    assertion: str
    source_quote: str


@dataclass(frozen=True, slots=True)
class AttestedSpeakerReview:
    facts: tuple[AttestedSpeakerFact, ...]

    def requires_self_link(self, ordinal: int) -> bool:
        return self.facts[ordinal].role == "self_participant" and self.facts[ordinal].assertion in {
            "asserted",
            "planned",
        }


def validate_dual_speaker_review(
    source: str,
    source_facts: Sequence[Mapping[str, Any]],
    first: Mapping[str, Any],
    second: Mapping[str, Any],
) -> AttestedSpeakerReview:
    """Fail closed when independent provider judgments disagree or source changed."""
    if not isinstance(source, str) or not source.strip() or len(source) > 4096:
        raise WholeMessageSpeakerError("Original source is invalid")
    if (
        not 1 <= len(source_facts) <= 16
        or not isinstance(first, Mapping)
        or not isinstance(second, Mapping)
    ):
        raise WholeMessageSpeakerError("Full-source review shape is invalid")
    a, b = first.get("facts"), second.get("facts")
    if (
        not isinstance(a, list)
        or not isinstance(b, list)
        or len(a) != len(source_facts)
        or len(b) != len(source_facts)
    ):
        raise WholeMessageSpeakerError("Independent source review count changed")
    # Providers commonly serialize ordinals as 1..N even when asked for 0..N-1.
    # Normalize ONLY a complete contiguous sequence in a single known base;
    # never reorder, infer omitted items or accept mixed conventions.
    bases = []
    for claims in (a, b):
        ordinals = [item.get("ordinal") if isinstance(item, Mapping) else None for item in claims]
        if ordinals == list(range(len(source_facts))):
            bases.append(0)
        elif ordinals == list(range(1, len(source_facts) + 1)):
            bases.append(1)
        else:
            raise WholeMessageSpeakerError("Model ordinal sequence is incomplete")
    results = []
    for ordinal, base in enumerate(source_facts):
        evidence = base.get("source_evidence")
        if not isinstance(evidence, str) or not evidence or evidence not in source:
            raise WholeMessageSpeakerError("Planner evidence is absent from unchanged source")
        claims = (a[ordinal], b[ordinal])
        verified = []
        for claim, number_base in zip(claims, bases, strict=True):
            if not isinstance(claim, Mapping) or set(claim) != {
                "ordinal",
                "role",
                "assertion",
                "source_quote",
            }:
                raise WholeMessageSpeakerError("Unexpected speaker evidence schema")
            number, role, assertion, quote = (
                claim.get(k) for k in ("ordinal", "role", "assertion", "source_quote")
            )
            if (
                not isinstance(number, int)
                or isinstance(number, bool)
                or number != ordinal + number_base
                or role not in {"self_participant", "other", "uncertain"}
                or assertion not in {"asserted", "planned", "conditional", "negated", "uncertain"}
                or not isinstance(quote, str)
                or not quote.strip()
                or quote not in evidence
                or quote not in source
            ):
                raise WholeMessageSpeakerError("Source-attested grammatical claim is invalid")
            if role == "self_participant" and assertion == "uncertain":
                raise WholeMessageSpeakerError(
                    "An uncertain assertion cannot authorize a speaker link"
                )
            verified.append((role, assertion, quote))
        if verified[0][:2] != verified[1][:2]:
            raise WholeMessageSpeakerError("Independent reviewers disagree on speaker or assertion")
        role, assertion, quote = verified[0]
        # Nonactual claims may remain in planning evidence; they cannot be
        # promoted into an accomplished event by adding a SELF reference.
        results.append(AttestedSpeakerFact(ordinal, role, assertion, quote))
    return AttestedSpeakerReview(tuple(results))


def attach_speaker_to_day_action(
    action: WriteAction,
    self_attributed: Sequence[bool],
) -> WriteAction:
    """Add one SELF-bound reference helper; never make SELF the Day fact owner.

    Source-attribution MUST be reviewed before calling this pure compiler.
    The ordinary Core preflight resolves the helper using the authenticated
    SelfBindingRepository and the normal Writer creates its backlinks.
    """
    if not isinstance(action, WriteAction) or not action.units:
        raise WholeMessageSpeakerError("Expected one Core Day write")
    primary = action.units[0]
    if (
        primary.target.type != "calendar_day"
        or len(primary.facts) != len(self_attributed)
        or any(type(item) is not bool for item in self_attributed)
        or primary.reference_lookup_only
    ):
        raise WholeMessageSpeakerError("Speaker proof is not aligned with Calendar facts")
    if not any(self_attributed):
        return action
    if any(unit.target.self_target == "self" for unit in action.units):
        raise WholeMessageSpeakerError("Duplicate authenticated SELF helper")
    self_index = len(action.units)
    marker_index = len(primary.references)
    # Each marker in a fact requires an occurrence-aligned reference list.
    # A single symbolic helper can be referenced by multiple facts, but
    # each distinct marker index is one occurrence into canonical Writer.
    adjusted = []
    position = marker_index
    for fact, speaker in zip(primary.facts, self_attributed, strict=True):
        if speaker:
            adjusted.append(fact.rstrip(".") + " (yo: {{ref:" + str(position) + "}}).")
            position += 1
        else:
            adjusted.append(fact)
    refs = (
        *primary.references,
        *(KnowledgeReference(self_index, "person", "yo") for speaker in self_attributed if speaker),
    )
    helper = KnowledgeUnit(
        SelectionCriteria(None, "yo", "person", (), None, self_target="self"),
        "record",
        (),
        (),
        (),
        (),
        reference_lookup_only=True,
    )
    return replace(
        action,
        units=(replace(primary, facts=tuple(adjusted), references=refs), *action.units[1:], helper),
    )
