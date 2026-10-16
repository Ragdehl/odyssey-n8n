"""Tasks E2 adaptor: a Core-linked Task is NOT automatically a Task mutation.

Two independent semantic attestations must agree on the exact source referent,
while current Core Markdown proves the actual linked Task. This adapter never
plans/writes notes, and the standard E3/WorkSession/Task service remains owner
of mutations. The private proof must be freshly checked at time of use.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from odyssey_core.application import ApplicationResult, _dependent_evidence_is_current
from odyssey_core.source_bound_dependency import (
    SourceBoundDependency,
    SourceBoundDependencyError,
    prove_source_bound_dependency,
)
from odyssey_core.storage import VaultRepository

from .interpretation import (
    TaskActivityTarget,
    TaskInterpretation,
    TaskOperation,
    TaskRelationshipRole,
)
from .schema import TASK_TYPE


class TaskDependentTargetError(ValueError):
    """Cannot authorize a dependent Task target without current E2 evidence."""


@dataclass(frozen=True, slots=True, repr=False)
class TaskDependentTarget:
    """Private target proof, not an executable command or a public Note link."""

    source_dependency: SourceBoundDependency
    operation: TaskOperation

    @property
    def task_id(self) -> str:
        return self.source_dependency.evidence.stable_note_id

    def require_current(self, repository: VaultRepository, schema: dict[str, Any]) -> str:
        """Revalidate predecessor source and Task identity immediately before mutation."""
        proof = self.source_dependency.evidence
        if proof.note_type != TASK_TYPE or not _dependent_evidence_is_current(
            proof, repository, schema
        ):
            raise TaskDependentTargetError("Task target proof expired or has wrong Note type")
        return proof.stable_note_id


def prove_dependent_task_target(
    *,
    full_source: str,
    antecedent_source: str,
    dependent_source: str,
    dependent_mention: str,
    core_predecessor: ApplicationResult,
    interpretation: TaskInterpretation,
    attestations: tuple[Mapping[str, object], Mapping[str, object]],
    repository: VaultRepository,
    schema: dict[str, Any],
) -> TaskDependentTarget:
    """Validate both semantic reviewers AND physically grounded Task identity.

    Reviewers must independently attest that the exact mention in the dependent
    scope refers to the uniquely linked Task in the prior source. Neither
    reviewer supplies Note IDs, mutation commands, or canonical paths.
    """
    if not isinstance(interpretation, TaskInterpretation):
        raise TaskDependentTargetError("Typed Tasks interpretation required")
    parent_create = interpretation.operation is TaskOperation.CREATE
    if (
        interpretation.source_text != dependent_source.strip()
        or dependent_source.strip().count(dependent_mention) != 1
        or (
            parent_create
            and (
                len(interpretation.relationship_mentions) != 1
                or interpretation.relationship_mentions[0].role
                is not TaskRelationshipRole.PARENT_TASK
                or interpretation.relationship_mentions[0].text != dependent_mention
            )
        )
        or (
            not parent_create
            and (
                interpretation.task_reference != dependent_mention
                or interpretation.operation
                not in {
                    TaskOperation.START_WORK_SESSION,
                    TaskOperation.STOP_WORK_SESSION,
                    TaskOperation.EDIT_WORK_SESSION,
                    TaskOperation.ADD_WORK_SESSION_ACTIVITY,
                }
                or (
                    interpretation.operation is TaskOperation.ADD_WORK_SESSION_ACTIVITY
                    and interpretation.activity_target is not TaskActivityTarget.TASK
                )
            )
        )
    ):
        raise TaskDependentTargetError("Task interpreter has no uniquely grounded operation")
    if not isinstance(attestations, tuple) or len(attestations) != 2:
        raise TaskDependentTargetError("Two distinct Task-target reviews required")
    required = {
        "full_source_quote": full_source,
        "antecedent_quote": antecedent_source,
        "dependent_quote": dependent_source,
        "dependent_mention": dependent_mention,
        "one_target": True,
        "same_target": True,
        "target_type": TASK_TYPE,
        "operation": "CREATE_SUBTASK" if parent_create else interpretation.operation.value,
        "operation_supported": True,
    }
    if any(not isinstance(att, Mapping) or dict(att) != required for att in attestations):
        raise TaskDependentTargetError("Uncorroborated or altered Task reference semantics")
    try:
        source_proof = prove_source_bound_dependency(
            complete_original_source=full_source,
            antecedent_quote=antecedent_source,
            dependent_quote=dependent_source,
            exact_dependent_mention=dependent_mention,
            predecessor=core_predecessor,
            repository=repository,
            schema=schema,
        )
    except SourceBoundDependencyError as error:
        raise TaskDependentTargetError("Core predecessor is not currently grounded") from error
    if source_proof.evidence.note_type != TASK_TYPE:
        raise TaskDependentTargetError("Core linked a non-Task canonical identity")
    return TaskDependentTarget(source_proof, interpretation.operation)
