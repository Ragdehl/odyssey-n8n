"""Read-only provenance verification for facts written by ordinary Odyssey Core.

A request/ordinal marker proves only physical existence of one Core-written
fact. It never proves which Router candidate was semantically satisfied.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .application import ApplicationResult
from .atomic_facts import AtomicFactError, normalize_atomic_fact, parse_atomic_facts
from .candidate_context import CoreCandidateContext
from .candidate_write_observation import observe_candidate_write_outcomes
from .notes import NoteFormatError, NoteValidationError, parse_note, validate_note
from .request_planning import RequestPlan, WriteAction
from .storage import VaultRepository

MAX_PROVENANCE_NOTE_SCAN = 5000


@dataclass(frozen=True, slots=True)
class PersistedFactEvidence:
    """Record whether one planned fact was independently observed in Markdown."""

    ordinal: int
    action_index: int
    unit_index: int
    status: str  # 'verified_in_markdown' or 'not_verified'
    note_id: str | None


@dataclass(frozen=True, slots=True)
class CandidateCoverageItem:
    """Track unresolved source candidates independently of Core's write count."""

    candidate_id: str
    status: str  # 'unproven' or 'ambiguous_identity', never 'saved' from readback


@dataclass(frozen=True, slots=True)
class CandidateFactReadback:
    """Distinguish physical Core fact receipts from unproven candidate coverage."""

    request_id: str
    core_request_status: str
    persisted_facts: tuple[PersistedFactEvidence, ...]
    candidate_ids: tuple[str, ...]
    candidate_progress: tuple[CandidateCoverageItem, ...]
    unresolved_candidate_ids: tuple[str, ...]
    candidate_coverage: str  # always 'unverified' until independent semantic attestation
    safe_to_report_all_candidates_complete: bool


def readback_core_facts(
    source: str,
    context: CoreCandidateContext,
    plan: RequestPlan,
    result: ApplicationResult,
    repository: VaultRepository,
    schema: dict[str, Any],
) -> CandidateFactReadback:
    """Cross-check Core's own success receipts with current canonical fact markers.

    Args:
        source: Unchanged current message.
        context: Core-validated, unverified Router candidate hints.
        plan: Independently validated Core RequestPlan for that message.
        result: Core execution result using the same plan and request ID.
        repository: Root-bound canonical Markdown repository (tests use tmp_path).
        schema: Current canonical NoteSchema used to validate readback notes.

    Returns:
        At most 128 individual fact receipts. Only an unambiguous atomic marker,
        matching Core result stable ID, exact request ID, ordinal and fact text
        counts as physically verified. Source candidate coverage stays unknown.

    Raises:
        ValueError: Wrong/mismatched envelopes, oversized note scan or invalid
            repository/schema. Nothing is persisted or executed here.
    """
    if not isinstance(repository, VaultRepository) or not isinstance(schema, dict):
        raise ValueError("Canonical repository and NoteSchema required")
    observed = observe_candidate_write_outcomes(source, context, plan, result)
    expected: dict[int, tuple[str, str | None, int, int]] = {}
    for receipt in observed.observed_core_write_units:
        action = plan.actions[receipt.action_index]
        if not isinstance(action, WriteAction):
            raise ValueError("Internal write unit type mismatch")
        unit = action.units[receipt.unit_index]
        current = result.action_results[receipt.action_index]
        unit_result = next(
            (u for u in current.unit_results if u.unit_index == receipt.unit_index), None
        )
        stable_id = (
            unit_result.stable_note_id
            if unit_result is not None
            and receipt.status == "succeeded"
            and not receipt.reference_lookup_only
            else None
        )
        for ordinal, text in zip(receipt.fact_ordinals, unit.facts, strict=True):
            expected[ordinal] = (text, stable_id, receipt.action_index, receipt.unit_index)

    # Only inspect original root-bound canonical Markdown; never search an index
    # or infer a fact's existence from unit status or plan count alone.
    matched: dict[int, list[tuple[str, str]]] = {ordinal: [] for ordinal in expected}
    note_paths = repository.list_markdown_paths()
    if len(note_paths) > MAX_PROVENANCE_NOTE_SCAN:
        raise ValueError("Canonical fact readback exceeds bounded note scan")
    stable_ids = {stable_id for _, stable_id, _, _ in expected.values() if stable_id}
    duplicate_id_counts: dict[str, int] = {}
    for path in note_paths:
        try:
            note = parse_note(repository.read_text(path))
            validate_note(note, schema)
        except (NoteFormatError, NoteValidationError, OSError, ValueError):
            # Corrupt/unavailable canonical notes cannot be used as proof.
            continue
        note_id = note.metadata.get("id")
        if not isinstance(note_id, str) or note_id not in stable_ids:
            continue
        duplicate_id_counts[note_id] = duplicate_id_counts.get(note_id, 0) + 1
        try:
            facts = parse_atomic_facts(note.content)
        except (AtomicFactError, ValueError):
            continue
        for fact in facts:
            if fact.request_id != result.request_id or fact.ordinal not in expected:
                continue
            # Verify the *exact* plan fact; references requiring Core rendering
            # intentionally do not pass this narrow literal proof.
            text, stable_id, _, _ = expected[fact.ordinal]
            if note_id == stable_id and normalize_atomic_fact(fact.text) == normalize_atomic_fact(
                text
            ):
                matched[fact.ordinal].append((note_id, path))
    receipts = []
    for ordinal, (_, stable_id, action_index, unit_index) in sorted(expected.items()):
        candidates = matched[ordinal]
        unique = (
            stable_id is not None
            and duplicate_id_counts.get(stable_id) == 1
            and len(candidates) == 1
        )
        receipts.append(
            PersistedFactEvidence(
                ordinal,
                action_index,
                unit_index,
                "verified_in_markdown" if unique else "not_verified",
                stable_id if unique else None,
            )
        )
    return CandidateFactReadback(
        request_id=result.request_id,
        core_request_status=observed.core_request_status,
        persisted_facts=tuple(receipts),
        candidate_ids=observed.candidate_ids,
        candidate_progress=tuple(
            CandidateCoverageItem(
                candidate_id=item.candidate_id,
                status="ambiguous_identity" if item.state == "ambiguous_identity" else "unproven",
            )
            for item in context.candidates
        ),
        unresolved_candidate_ids=observed.ambiguous_candidate_ids,
        candidate_coverage="unverified",
        safe_to_report_all_candidates_complete=False,
    )
