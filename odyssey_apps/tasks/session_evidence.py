"""Tasks-owned E2 read-only carrier for one physically persisted Work Session.

A Work Session START result is not a canonical Note identifier supplied by
Router. This bridge verifies the actual domain result against current Markdown
and rechecks it at the consumer. The existing WorkSessionService.stop/edit gate
still owns CAS and mutation; the carrier never writes or resolves anaphora.
"""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass

from .schema import TASK_TYPE, WORK_SESSION_TYPE
from .work_sessions import (
    TaskWorkSessionService,
    WorkSessionError,
    WorkSessionMutationResult,
)


class CanonicalSessionEvidenceError(ValueError):
    """The previous Work Session write is not a unique and current target."""


@dataclass(frozen=True, slots=True, repr=False)
class CanonicalSessionEvidence:
    """Private, short-lived E2 handoff; never serialized into E3/UI or model text."""

    session_id: str
    task_id: str
    source_path: str
    source_hash: str
    revision: int
    started_at: str
    creator_delivery_step: str
    vault_root: str
    task_source_hash: str

    def require_current(self, service: TaskWorkSessionService) -> tuple[int, str]:
        """Check typed unique canonical Note and parent at each consumer boundary.

        The actual domain mutation MUST still use these tokens with its own
        readback/CAS; this check alone does not authorize a stop or edit.
        """
        if not isinstance(service, TaskWorkSessionService):
            raise CanonicalSessionEvidenceError("Untrusted Work Session service")
        if str(service.repository._root) != self.vault_root:
            raise CanonicalSessionEvidenceError(
                "Session proof belongs to another actor-local vault"
            )
        try:
            path, note, raw = service._load_unique(self.session_id, WORK_SESSION_TYPE)
            task_path, task, task_raw = service._load_unique(self.task_id, TASK_TYPE)
        except (WorkSessionError, ValueError, OSError) as error:
            raise CanonicalSessionEvidenceError("Session or Task identity unavailable") from error
        current_hash = hashlib.sha256(raw.encode()).hexdigest()
        if (
            path != self.source_path
            or not task_path
            or note.metadata.get("id") != self.session_id
            or note.metadata.get("task_id") != self.task_id
            or task.metadata.get("id") != self.task_id
            or note.metadata.get("ended_at") is not None
            or note.metadata.get("started_at") != self.started_at
            or note.metadata.get("revision") != self.revision
            or not hmac.compare_digest(
                hashlib.sha256(task_raw.encode()).hexdigest(), self.task_source_hash
            )
            or not hmac.compare_digest(current_hash, self.source_hash)
        ):
            raise CanonicalSessionEvidenceError("Session source or ownership changed")
        return self.revision, self.source_hash


def prove_created_session(
    *,
    result: WorkSessionMutationResult,
    expected_task_id: str,
    creator_delivery_step: str,
    service: TaskWorkSessionService,
) -> CanonicalSessionEvidence:
    """Admit only a returned Task START result with physical current readback.

    Called directly after a *trusted* WorkSessionService.start() returned to
    its authenticated per-delivery executor; origin step is correlation only,
    not a claim that canonical Markdown contains a delivery-request ID.
    """
    if (
        not isinstance(result, WorkSessionMutationResult)
        or result.operation != "work_session_started"
        or result.previous_source_hash is not None
        or not isinstance(expected_task_id, str)
        or not expected_task_id
        or result.task_id != expected_task_id
        or result.session.task_id != expected_task_id
        or result.session.ended_at is not None
        or not isinstance(creator_delivery_step, str)
        or not creator_delivery_step
        or len(creator_delivery_step) > 128
        or not isinstance(service, TaskWorkSessionService)
    ):
        raise CanonicalSessionEvidenceError("Unverified Work Session creation receipt")
    session = result.session
    if (
        not isinstance(session.id, str)
        or not session.id
        or not isinstance(session.revision, int)
        or isinstance(session.revision, bool)
        or session.revision < 1
        or not isinstance(session.source_hash, str)
        or len(session.source_hash) != 64
        or not isinstance(session.started_at, str)
        or not session.started_at
    ):
        raise CanonicalSessionEvidenceError("Malformed Work Session readback receipt")
    try:
        _path, _task, task_raw = service._load_unique(expected_task_id, TASK_TYPE)
    except (WorkSessionError, ValueError, OSError) as error:
        raise CanonicalSessionEvidenceError("Session parent Task is unverified") from error
    proof = CanonicalSessionEvidence(
        session.id,
        expected_task_id,
        result.path,
        session.source_hash,
        session.revision,
        session.started_at,
        creator_delivery_step,
        str(service.repository._root),
        hashlib.sha256(task_raw.encode()).hexdigest(),
    )
    proof.require_current(service)
    return proof
