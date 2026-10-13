"""Non-writing, durable ambiguity from genuine multi-person Core evidence.

For independently written earlier facts that mention multiple existing
people, a later singular reference must NOT inherit one guessed identity.
The original later source clause is stored as v2 pending source work with
Core-verified options. No Core plan, Day fact or guessed identity is written.
"""

from __future__ import annotations

import re
from collections.abc import Callable

from odyssey_apps.router import Route
from odyssey_core.application import (
    ApplicationResult,
    ApplicationStatus,
    PendingWorkStatus,
    _dependent_evidence_is_current,
)
from odyssey_core.candidate_pending_projection import (
    CandidatePendingItem,
    CandidatePendingPreview,
)
from odyssey_core.clarification import ClarificationOption
from odyssey_core.observability import (
    OperationalEvidence,
    OperationalOutcome,
    OperationalStage,
)
from odyssey_core.storage import VaultRepository
from odyssey_runtime.source_scope_compiler import ScopedCandidateRoute


class AmbiguousSourcePendingError(ValueError):
    """Uncertain source or canonical options must not become a clarification."""


def preserve_unresolved_dependent_reference(
    *,
    original_source: str,
    route: Route,
    scoped: ScopedCandidateRoute,
    predecessor_source: str,
    predecessor: ApplicationResult,
    locator: str,
    repository: VaultRepository,
    schema: dict,
    recorder: Callable[[CandidatePendingPreview, tuple[ClarificationOption, ...]], str],
) -> ApplicationResult:
    """Record one source-exact unresolved reference with multiple verified choices.

    The options come exclusively from independent Core canonical linked-fact
    evidence in the COMPLETED prior route. Router's lexical last mention is
    NEVER an identity choice. Date and event wording remain the ORIGINAL
    source for later user clarification and fresh Temporal/Core planning.
    """
    if not (
        isinstance(original_source, str)
        and isinstance(route, Route)
        and isinstance(scoped, ScopedCandidateRoute)
        and scoped.route == route
        and isinstance(predecessor, ApplicationResult)
        and predecessor.status is ApplicationStatus.COMPLETED
        and isinstance(repository, VaultRepository)
        and isinstance(schema, dict)
        and callable(recorder)
        and route.depends_on is not None
        and isinstance(locator, str)
        and locator
    ):
        raise AmbiguousSourcePendingError("Pending reference lacks a validated route contract")
    if (
        len(scoped.context.candidates) != 1
        or len(scoped.original_candidate_ids) != 1
        or not scoped.context.hybrid_interpretation_mode
    ):
        raise AmbiguousSourcePendingError("Ambiguous reference is not source-scoped")
    candidate = scoped.context.candidates[0]
    references = [role.span for role in candidate.roles if role.role == "reference"]
    if (
        candidate.state != "ambiguous_identity"
        or len(references) != 1
        or references[0].text != route.dependent_mention
        or not any(
            role.role in {"participants", "subject", "object"} and role.span == references[0]
            for role in candidate.roles
        )
        or not any(role.role == "predicate" for role in candidate.roles)
    ):
        raise AmbiguousSourcePendingError("Source does not establish one unresolved reference")
    bounded = [
        *candidate.anchors,
        *(
            role.span
            for role in candidate.roles
            if role.role
            in {
                "date",
                "date_scope",
                "time",
                "time_approx",
                "predicate",
                "object",
                "reference",
                "participants",
            }
        ),
    ]
    start = min(x.start for x in bounded)
    end = max(x.end for x in bounded)
    fragment = scoped.context.source[start:end]
    if (
        not 0 <= start < end <= len(scoped.context.source)
        or end - start > 400
        or any(char in fragment for char in ".;!?\n\r")
        or scoped.original_start + end > len(original_source)
        or original_source[scoped.original_start + start : scoped.original_start + end] != fragment
        or not start <= references[0].start < references[0].end <= end
    ):
        raise AmbiguousSourcePendingError("Pending statement has no exact original source clause")
    options = []
    seen: set[str] = set()
    for evidence in predecessor.canonical_reference_evidence:
        if (
            evidence.note_type != "person"
            or evidence.stable_note_id in seen
            or re.search(
                r"(?<!\w)" + re.escape(evidence.source_mention) + r"(?!\w)", predecessor_source
            )
            is None
            or evidence.canonical_name != evidence.source_mention
            or not _dependent_evidence_is_current(evidence, repository, schema)
        ):
            raise AmbiguousSourcePendingError(
                "Prior canonical Person evidence not uniquely verified"
            )
        seen.add(evidence.stable_note_id)
        options.append(
            ClarificationOption(
                evidence.stable_note_id,
                evidence.canonical_name,
                "person",
            )
        )
    if len(options) < 2:
        raise AmbiguousSourcePendingError("Need multiple independently proven antecedents")
    if len(options) > 4:
        options = []  # v2 UI cap: preserve pending source, not a fake incomplete shortlist
    reference = references[0]
    preview = CandidatePendingPreview(
        request_id=locator,
        original_request=original_source,
        request_status=ApplicationStatus.NEEDS_ATTENTION.value,
        pending=(
            CandidatePendingItem(
                scoped.original_candidate_ids[0],
                fragment,
                scoped.original_start + start,
                scoped.original_start + end,
                "ambiguous_identity",
                reference.text,
                scoped.original_start + reference.start,
                scoped.original_start + reference.end,
            ),
        ),
        physically_verified_fact_count=0,
    )
    record_id = recorder(preview, tuple(options))
    if record_id != locator:
        raise AmbiguousSourcePendingError("Pending recorder did not confirm exact route locator")
    return ApplicationResult(
        locator,
        ApplicationStatus.NEEDS_ATTENTION,
        (),
        (),
        clarification_code="AMBIGUOUS_REFERENCE_REQUIRES_CHOICE",
        pending_work=PendingWorkStatus(
            required=True,
            persisted=True,
            record_id=record_id,
        ),
        operational=OperationalEvidence(
            stages=(
                OperationalStage(
                    "candidate.pending_identity",
                    OperationalOutcome.COMPLETED,
                    0.0,
                ),
            )
        ),
        execution_flow={
            "pending_source": fragment,
            "pending_reference": reference.text,
            "pending_option_labels": [option.label for option in options],
        },
    )
