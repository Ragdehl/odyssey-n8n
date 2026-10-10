"""Reuse Core's persisted canonical reference proof for one scoped pronoun.

This narrow optional bridge is not an identity resolver. It abstains unless a
single immediately preceding source candidate has a uniquely persisted Core
reference and the current canonical source/identity guards remain valid.
Other candidate layouts require independent Core semantic identity proof.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .application import (
    ApplicationResult,
    ApplicationStatus,
    CanonicalReferenceEvidence,
    DependentReferenceGuard,
    _dependent_evidence_is_current,
)
from .candidate_context import CoreCandidateContext, CoreSourceSpan
from .storage import VaultRepository


@dataclass(frozen=True, slots=True)
class CandidateCanonicalReferenceHandoff:
    """Private, freshness-bound proof of ONE Core identity; no candidate fact proof.

    Never serialize this carrier: it contains canonical IDs and content guards.
    The original source-to-candidate semantic attribution remains unverified.
    """

    antecedent_candidate_id: str
    referring_candidate_id: str
    referring_span: CoreSourceSpan
    evidence: CanonicalReferenceEvidence

    def write_guard(self) -> DependentReferenceGuard:
        """Return Core's existing time-of-use guard, NOT a new write authority."""
        return DependentReferenceGuard(self.referring_span.text, self.evidence)


def _has_exact_name(candidate, name: str) -> bool:
    """Require the persisted canonical name literally in the preceding source."""
    if not isinstance(name, str) or not name.strip() or len(name) > 200:
        return False
    pattern = re.compile(r"(?<!\w)" + re.escape(name) + r"(?!\w)")
    return any(pattern.search(span.text) for span in candidate.anchors)


def find_single_candidate_canonical_handoff(
    source: str,
    context: CoreCandidateContext,
    referring_candidate_id: str,
    preceding_result: ApplicationResult,
    repository: VaultRepository,
    schema: dict[str, object],
) -> CandidateCanonicalReferenceHandoff | None:
    """Find a uniquely proven canonical link without guessing source identity.

    The **only** currently supported shape is source candidate 1 directly
    followed by candidate 2 with one explicit `reference` role and one exact,
    persisted canonical reference in the predecessor result. F14's multiple
    possible antecedents, additional references, edits, stale guards and absent
    Core evidence all abstain. Nothing writes or calls a provider.

    The carrier alone never authorizes recording facts. A consumer must keep
    source/plan ownership checks and execute Core's existing preflight guard.
    """
    if not isinstance(context, CoreCandidateContext):
        raise ValueError("A Core-owned source context is required")
    context.validate(source)
    if (
        not isinstance(preceding_result, ApplicationResult)
        or not isinstance(repository, VaultRepository)
        or not isinstance(schema, dict)
        or not isinstance(referring_candidate_id, str)
    ):
        raise ValueError("Canonical reference handoff requires typed Core evidence")
    if len(context.candidates) < 2 or referring_candidate_id != context.candidates[1].candidate_id:
        return None
    preceding, referring = context.candidates[:2]
    if (
        preceding.state != "candidate"
        or referring.state != "candidate"
        or preceding_result.status is not ApplicationStatus.COMPLETED
    ):
        return None
    references = [role.span for role in referring.roles if role.role == "reference"]
    if (
        len(references) != 1
        or any(edge.role == "reference" for edge in referring.inherits)
        or len(preceding_result.canonical_reference_evidence) != 1
        or len(preceding_result.action_results) != 1
        or len(preceding_result.action_results[0].canonical_reference_evidence) != 1
    ):
        return None
    pronoun = references[0]
    evidence = preceding_result.canonical_reference_evidence[0]
    # Source roles identify the particular named occurrence; an antecedent
    # anchor merely mentioning Eric among several participants is insufficient.
    antecedent_identity_roles = [
        role.span for role in preceding.roles if role.role in {"subject", "object", "participants"}
    ]
    if (
        len(antecedent_identity_roles) != 1
        or antecedent_identity_roles[0].text != evidence.source_mention
        or not any(
            anchor.start <= antecedent_identity_roles[0].start
            and anchor.end >= antecedent_identity_roles[0].end
            for anchor in preceding.anchors
        )
        or not any(
            anchor.start <= pronoun.start and anchor.end >= pronoun.end
            for anchor in referring.anchors
        )
    ):
        return None
    if (
        evidence != preceding_result.action_results[0].canonical_reference_evidence[0]
        or not isinstance(evidence, CanonicalReferenceEvidence)
        or not pronoun.text.strip()
        or pronoun.start < min(anchor.end for anchor in preceding.anchors)
        or not _has_exact_name(preceding, evidence.source_mention)
        or evidence.source_mention != evidence.canonical_name
        or not _dependent_evidence_is_current(evidence, repository, schema)
    ):
        return None
    return CandidateCanonicalReferenceHandoff(
        preceding.candidate_id, referring.candidate_id, pronoun, evidence
    )
