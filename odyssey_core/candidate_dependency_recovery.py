"""Read-only recovery gate for separately planned, dependent Core facts.

A repeated request identifier cannot safely re-run both planned writes
after one of them persisted. The authoritative Markdown fact markers,
rather than an index, reveal a partial/completed/ambiguous prior attempt.

This intentionally neither rolls back nor automatically retries an action.
New-identity creation that failed before writing any marker and concurrent
races still require a stronger transactional boundary before activation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .atomic_facts import AtomicFactError, parse_atomic_facts
from .notes import NoteFormatError, NoteValidationError, parse_note, validate_note
from .storage import VaultRepository

MAX_DEPENDENT_RECOVERY_NOTES = 5000


class DependentRequestRecoveryError(ValueError):
    """A dependent operation cannot safely be retried without review."""


@dataclass(frozen=True, slots=True)
class DependentRequestRecovery:
    """State of one request's two immutable fact ordinals in canonical Notes."""

    request_id: str
    state: Literal["new", "partial", "complete", "conflict"]
    fact_ordinals: tuple[int, ...]
    stable_note_ids: tuple[str, ...]
    safe_to_retry_automatically: bool = False

    @property
    def may_start_new_request(self) -> bool:
        """A new unused request ID may start, subject to all other guards."""
        return self.state == "new"


def inspect_dependent_request_recovery(
    repository: VaultRepository,
    schema: dict,
    request_id: str,
) -> DependentRequestRecovery:
    """Conservatively scan original root-bound Notes for request fact markers.

    Raises:
        DependentRequestRecoveryError: Invalid repository/schema, malformed
            canonical metadata, duplicate stable IDs, or scan capacity hit.
            No physical Notes are changed.
    """
    if (
        not isinstance(repository, VaultRepository)
        or not isinstance(schema, dict)
        or not isinstance(request_id, str)
        or not request_id.strip()
    ):
        raise DependentRequestRecoveryError("Original Core request recovery inputs invalid")
    paths = repository.list_markdown_paths()
    if len(paths) > MAX_DEPENDENT_RECOVERY_NOTES:
        raise DependentRequestRecoveryError("Too many canonical Notes to verify replay safety")
    seen_ids: set[str] = set()
    matches: list[tuple[int, str]] = []
    for path in paths:
        try:
            note = parse_note(repository.read_text(path))
            validate_note(note, schema)
            identity = note.metadata.get("id")
            if not isinstance(identity, str) or not identity:
                raise DependentRequestRecoveryError("Canonical stable ID missing")
            if identity in seen_ids:
                raise DependentRequestRecoveryError("Duplicate canonical stable ID")
            seen_ids.add(identity)
            facts = parse_atomic_facts(note.content)
        except (
            NoteFormatError,
            NoteValidationError,
            AtomicFactError,
            OSError,
            ValueError,
        ) as error:
            raise DependentRequestRecoveryError(
                "Cannot establish original Markdown replay safety"
            ) from error
        matches.extend((fact.ordinal, identity) for fact in facts if fact.request_id == request_id)
    ordinals = tuple(item[0] for item in matches)
    ids = tuple(item[1] for item in matches)
    if not matches:
        state = "new"
    elif len(matches) == 1 and ordinals == (0,):
        state = "partial"
    elif len(matches) == 2 and set(ordinals) == {0, 1}:
        state = "complete"
    else:
        state = "conflict"
    return DependentRequestRecovery(
        request_id=request_id,
        state=state,
        fact_ordinals=ordinals,
        stable_note_ids=ids,
    )


def require_new_dependent_request(
    repository: VaultRepository,
    schema: dict,
    request_id: str,
) -> None:
    """Fail closed before any Core action on a prior partial/completed request."""
    state = inspect_dependent_request_recovery(repository, schema, request_id)
    if not state.may_start_new_request:
        raise DependentRequestRecoveryError(
            f"Dependent request already has {state.state} canonical fact markers"
        )
