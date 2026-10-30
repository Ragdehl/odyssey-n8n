"""Read-only, source-exact Core handoff after a durable identity clarification.

This is a trusted semantic *input*, never a reviewed RequestPlan or write
authorization. Reuse the existing v2 pending and E3 readback evidence; there is
no separate store, model call, parser, or identity-resolution pathway here.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from .candidate_pending_state import CandidatePendingRepository, CandidatePendingStateError
from .storage import VaultRepository


class CandidateContinuationContextError(ValueError):
    """Reject an unavailable, stale, or ungrounded read-only handoff."""


@dataclass(frozen=True, slots=True)
class CoreCompletedFactMarker:
    """Verified prior physical result: context only, never a new plan action."""

    ordinal: int
    note_id: str
    fact_digest: str


@dataclass(frozen=True, slots=True)
class CoreCandidateContinuationContext:
    """Immutable original-source slice, chosen identity, and previous write proof.

    This does not authorize running a Planner, applying a model answer or E3
    mutation. The caller must separately review *all* proposed semantics and
    recheck source, identity, physical facts and replay immediately before E3.
    """

    conversation_id: str
    original_request_id: str
    original_source: str
    candidate_id: str
    source_start: int
    source_end: int
    reference_start: int
    reference_end: int
    selected_note_id: str
    selected_name: str
    selected_identity_guard: str
    captured_at: str
    completed_facts: tuple[CoreCompletedFactMarker, ...]
    pending_record_digest: str

    @property
    def pending_source(self) -> str:
        return self.original_source[self.source_start : self.source_end]

    @property
    def reference_text(self) -> str:
        return self.original_source[self.reference_start : self.reference_end]

    @property
    def source_digest(self) -> str:
        return hashlib.sha256(self.original_source.encode("utf-8")).hexdigest()

    @property
    def may_execute(self) -> bool:
        return False

    def review_payload(self) -> dict[str, object]:
        """Bounded exact source for a future independent semantic reviewer.

        Already-written facts are listed as opaque provenance markers: they
        must not be re-planned. The selected ID remains a Core-only binding;
        external model prompts should use the canonical display name as a hint,
        not interpret stable IDs as language or as write permission.
        """
        return {
            "original_source": self.original_source,
            "pending_source": self.pending_source,
            "pending_candidate_id": self.candidate_id,
            "pending_span": [self.source_start, self.source_end],
            "reference_text": self.reference_text,
            "reference_span": [self.reference_start, self.reference_end],
            "selected_identity_name": self.selected_name,
            "captured_at": self.captured_at,
            "already_written_fact_ordinals": [marker.ordinal for marker in self.completed_facts],
        }


def prepare_selected_candidate_continuation(
    repository: CandidatePendingRepository,
    *,
    conversation_id: str,
    request_id: str,
    vault: VaultRepository,
    schema: dict[str, Any],
) -> CoreCandidateContinuationContext:
    """Only emit immutable source evidence after actor-scoped canonical rechecks.

    The caller must get the repository from its authenticated actor's private
    state root. Unsupported multi-pending ambiguity never gets silently reduced
    to one clause. Other pending reasons cannot be resolved by choosing a name.
    """
    if not isinstance(repository, CandidatePendingRepository):
        raise CandidateContinuationContextError("Candidate state owner is invalid")
    try:
        decision = repository.selected_for_core_review(
            conversation_id=conversation_id,
            request_id=request_id,
            vault=vault,
            schema=schema,
        )
        if (
            decision.outcome != "choice_ready_for_core_review"
            or not decision.selected_note_id
            or not decision.selected_guard
            or not decision.captured_at
        ):
            raise CandidateContinuationContextError("Selected candidate needs Core review")
        record = repository.read(request_id)
        pending = record["pending"]
        if (
            record["status"] != "selected"
            or record["conversation_id"] != conversation_id
            or record["selected_note_id"] != decision.selected_note_id
            or record["selected_guard"] != decision.selected_guard
            or record["created_at"] != decision.captured_at
            or len(pending) != 1
            or pending[0]["reason"] != "ambiguous_identity"
            or not pending[0]["reference_text"]
        ):
            raise CandidateContinuationContextError("Source selection is not uniquely grounded")
        item = pending[0]
        selected = [
            option
            for option in record["options"]
            if option["id"] == decision.selected_note_id
            and option["guard"] == decision.selected_guard
        ]
        if len(selected) != 1:
            raise CandidateContinuationContextError("Canonical selection evidence is missing")
        markers = tuple(
            CoreCompletedFactMarker(m["ordinal"], m["note_id"], m["fact_digest"])
            for m in record["completed_fact_markers"]
        )
        source = record["original_request"]
        if (
            source[item["start"] : item["end"]] != decision.pending_source_text
            or source[item["reference_start"] : item["reference_end"]] != item["reference_text"]
        ):
            raise CandidateContinuationContextError("Original source offsets differ")
        # Explicitly bind the entire selected workflow state (not just text)
        # so an eventual independent review can reject any state replacement.
        digest = hashlib.sha256(
            json.dumps(record, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode(
                "utf-8"
            )
        ).hexdigest()
        return CoreCandidateContinuationContext(
            conversation_id=conversation_id,
            original_request_id=request_id,
            original_source=source,
            candidate_id=item["id"],
            source_start=item["start"],
            source_end=item["end"],
            reference_start=item["reference_start"],
            reference_end=item["reference_end"],
            selected_note_id=decision.selected_note_id,
            selected_name=selected[0]["label"],
            selected_identity_guard=decision.selected_guard,
            captured_at=decision.captured_at,
            completed_facts=markers,
            pending_record_digest=digest,
        )
    except CandidatePendingStateError as error:
        raise CandidateContinuationContextError("Candidate evidence is unavailable") from error


def validate_selected_continuation_current(
    prepared: CoreCandidateContinuationContext,
    repository: CandidatePendingRepository,
    *,
    vault: VaultRepository,
    schema: dict[str, Any],
) -> None:
    """Recheck *all* source, identity and physical readback evidence before E3.

    A previously prepared context never remains canonical merely because it
    was once observed. The eventual semantic reviewer and writer must not use
    it after source state, selected canonical identity or completed facts drift.
    Even a successful check does NOT attest a proposed plan's meaning.
    """
    if not isinstance(prepared, CoreCandidateContinuationContext):
        raise CandidateContinuationContextError("Typed continuation input required")
    current = prepare_selected_candidate_continuation(
        repository,
        conversation_id=prepared.conversation_id,
        request_id=prepared.original_request_id,
        vault=vault,
        schema=schema,
    )
    if current != prepared:
        raise CandidateContinuationContextError("Prepared continuation evidence is stale")
