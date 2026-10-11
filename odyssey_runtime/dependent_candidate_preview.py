"""Private opt-in chat delivery for independently planned dependent Core facts.

This module is intentionally *not* registered in the normal HTTP server,
router or production composition. It reuses the existing outer browser
request ID, actor-local conversation root, Core source/identity guard and
completed delivery result cache. Core alone owns all facts and mutations.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from odyssey_core.application import ApplicationResult, ApplicationStatus
from odyssey_core.candidate_dependency_admission import (
    DependentOperationAdmissionError,
    DependentOperationJournal,
)
from odyssey_core.storage import VaultRepository

from .delivery_results import LocalDeliveryResultStore
from .serialization import application_result_to_response

if TYPE_CHECKING:
    from .composition import RuntimeComposition

_REQUEST_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}\Z")

# The callback receives the trusted original message, stable browser
# operation ID, and the previously actor-resolved operational state root.
DependentCorePreviewExecutor = Callable[[str, str, Path], ApplicationResult]


@dataclass(slots=True)
class DependentCandidateChatPreview:
    """Explicit test-only runtime envelope, never a normal chat dispatcher.

    The current installed runtime may use one local canonical vault.
    Until actor-bound vault selection is proven end-to-end, preview requests
    requiring mapped multiuser or external principals are rejected.
    """

    runtime: RuntimeComposition
    core_executor: DependentCorePreviewExecutor

    def execute(
        self,
        source: str,
        request_id: str,
        conversation_id: str,
    ) -> dict[str, object]:
        """Replay completed dependent submissions, or safely run Core once.

        The same outer browser request ID must be reused for a network
        retry. The method has no public HTTP registration and cannot
        be called through ordinary RuntimeComposition.execute_product.

        Raises:
            ValueError: The original message, IDs, root or test executor
                is unavailable or invalid.
            DependentOperationAdmissionError: A tampered operational
                journal or an unresolvable state failure was detected.
        """
        if (
            not isinstance(source, str)
            or not source.strip()
            or not isinstance(request_id, str)
            or _REQUEST_ID.fullmatch(request_id) is None
            or not isinstance(conversation_id, str)
            or _REQUEST_ID.fullmatch(conversation_id) is None
            or not callable(self.core_executor)
        ):
            raise ValueError("Preview requires original source and stable validated message IDs")
        runtime = self.runtime
        resolver = runtime.conversation_root_resolver
        repository = runtime.vault_repository
        if resolver is None or not isinstance(repository, VaultRepository):
            raise ValueError("Preview requires explicit root-bound canonical repository and state")
        # This is a private local-only experiment; do not repurpose the
        # authenticated multiuser API without actor-specific vault selection.
        actor_root = resolver.resolve("odyssey-runtime")
        if not actor_root.is_dir() or actor_root.is_symlink():
            raise ValueError("Preview actor-root state must already exist and be trusted")
        if repository.contains_filesystem_path(actor_root):
            raise ValueError("Operational state must not reside in canonical Markdown")
        replay_store = LocalDeliveryResultStore(actor_root / "dependent-preview-deliveries")
        binding = replay_store.fingerprint(source, conversation_id)
        ledger = DependentOperationJournal(actor_root, repository)
        with runtime._execute_lock:
            previous = replay_store.load(request_id, binding)
            if previous is not None:
                receipt = ledger.inspect(request_id)
                if (
                    receipt is None
                    or receipt.state != "completed"
                    or receipt.source_digest != hashlib.sha256(source.encode("utf-8")).hexdigest()
                ):
                    raise DependentOperationAdmissionError(
                        "Cached dependent completion lacks original canonical operation proof"
                    )
                previous["delivery_replayed"] = True
                return previous
            try:
                result = self.core_executor(source, request_id, actor_root)
            except DependentOperationAdmissionError:
                receipt = ledger.inspect(request_id)
                if receipt is None:
                    raise
                # An already admitted, partially written operation cannot
                # be reported as completed or silently retried.
                return application_result_to_response(
                    ApplicationResult(
                        request_id,
                        ApplicationStatus.NEEDS_ATTENTION,
                        (),
                        (),
                        clarification_code="CANDIDATE_COVERAGE_REVIEW_REQUIRED",
                        planning_error="DEPENDENT_OPERATION_ALREADY_ADMITTED",
                    )
                )
            if not isinstance(result, ApplicationResult):
                raise ValueError("Dependent Core did not return a typed result")
            receipt = ledger.inspect(request_id)
            if (
                receipt is None
                or receipt.request_id != result.request_id
                or receipt.source_digest != hashlib.sha256(source.encode("utf-8")).hexdigest()
            ):
                raise DependentOperationAdmissionError(
                    "Original Core receipt or subordinate request ID is missing"
                )
            if result.status is ApplicationStatus.COMPLETED and receipt.state != "completed":
                result = replace(
                    result,
                    status=ApplicationStatus.NEEDS_ATTENTION,
                    planning_error="DEPENDENT_CANONICAL_AUDIT_UNVERIFIED",
                )
            # The real Core fact markers and journal retain their
            # subordinate execution ID; only the external chat delivery
            # envelope uses the original stable browser message ID.
            external_result = replace(result, request_id=request_id)
            response = application_result_to_response(external_result)
            if result.status is ApplicationStatus.COMPLETED and receipt.state == "completed":
                replay_store.save(
                    request_id,
                    binding,
                    response,
                    datetime.now(UTC).isoformat(),
                )
            return response
