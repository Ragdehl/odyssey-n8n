"""Conservative, source-grounded vetoes for experimental candidate fact matches.

A token overlap, even after passing all vetoes, is NEVER semantic approval.
These inexpensive checks only reject demonstrable lexical mismatches, newly
invented denial and unsupported pronoun identity bindings before Core writes.
"""

from __future__ import annotations

import re
import unicodedata

from .candidate_context import CoreCandidateContext

_NEGATION = frozenset({"no", "nunca", "jamas", "not", "never", "ne", "pas", "jamais"})


class CandidateSemanticVeto(ValueError):
    """A candidate/fact match lacks basic safe source evidence."""


def normalized_words(text: str) -> frozenset[str]:
    """Extract Unicode-case/accent-normalized words without identity guessing."""
    if not isinstance(text, str):
        raise CandidateSemanticVeto("Source and fact text must be strings")
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    plain = "".join(char for char in decomposed if not unicodedata.combining(char))
    return frozenset(re.findall(r"[^\W_]+", plain))


def candidate_distinctive_overlap(
    context: CoreCandidateContext, candidate_index: int, fact_text: str
) -> bool:
    """Require a distinctive content word in a candidate and its planned fact.

    This rule is intentionally conservative and can reject valid paraphrases.
    It does not consider an overlapping word proof of factual equivalence.
    """
    current = set().union(
        *(normalized_words(anchor.text) for anchor in context.candidates[candidate_index].anchors)
    )
    other = set().union(
        *(
            normalized_words(anchor.text)
            for index, candidate in enumerate(context.candidates)
            if index != candidate_index
            for anchor in candidate.anchors
        )
    )
    return bool({word for word in current - other if len(word) >= 3} & normalized_words(fact_text))


def veto_unsafe_literal_match(
    source: str,
    context: CoreCandidateContext,
    candidate_index: int,
    fact_text: str,
) -> None:
    """Reject obvious source contradiction, cross-candidate swap, or pronoun alias.

    This is negative-evidence-only. The function MUST NOT certify that a fact is
    correct, including when it passes. Pronoun candidates require a separate
    Core-verified identity attestation not provided by this first-pass pilot.
    """
    candidate = context.candidates[candidate_index]
    if any(role.role == "reference" for role in candidate.roles) or any(
        edge.role == "reference" for edge in candidate.inherits
    ):
        raise CandidateSemanticVeto("Unverified source reference requires Core identity evidence")
    if not candidate_distinctive_overlap(context, candidate_index, fact_text):
        raise CandidateSemanticVeto("Candidate fact lacks distinctive original source evidence")
    # Only reject NEW denial vocabulary that never occurs in the original
    # request. Negation scope within mixed clauses is not resolved here.
    new_denials = (normalized_words(fact_text) & _NEGATION) - (normalized_words(source) & _NEGATION)
    if new_denials:
        raise CandidateSemanticVeto("Planned fact introduces an unsupported negation")
