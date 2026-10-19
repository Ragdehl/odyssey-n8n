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
from odyssey_core.request_planning import RequestPlan, WriteAction
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
class TaskPersonReference:
    """Private actor-bound Person handoff for ordinary Task CREATE."""

    source_dependency: SourceBoundDependency
    actor_id: str

    def require_current(
        self, actor_id: str, repository: VaultRepository, schema: dict[str, Any]
    ) -> SourceBoundDependency:
        """Reject actor changes and stale Core Markdown before Tasks planning."""
        proof = self.source_dependency.evidence
        if (
            not self.actor_id
            or self.actor_id != actor_id
            or proof.note_type != "person"
            or not _dependent_evidence_is_current(proof, repository, schema)
        ):
            raise TaskDependentTargetError("Person handoff is stale or belongs to another actor")
        return self.source_dependency


@dataclass(frozen=True, slots=True, repr=False)
class PreparedDependentSubtask:
    """One source-bound child title prepared by the ordinary Core planner.

    This is deliberately only a read-only preparation receipt.  It does not
    name a parent note or authorize persistence; that remains dependent on the
    later physical Core backlink and the UI mutation service's CAS command.
    """

    source_text: str
    operation: TaskOperation
    title: str

    def require_matches(self, source_text: str, operation: TaskOperation) -> str:
        """Return the prepared title only for its exact source and operation."""
        if (
            source_text != self.source_text
            or operation is not TaskOperation.CREATE
            or self.operation is not TaskOperation.CREATE
        ):
            raise TaskDependentTargetError("Prepared subtask source or operation changed")
        return self.title


@dataclass(frozen=True, slots=True, repr=False)
class TaskDependentTarget:
    """Private target proof, not an executable command or a public Note link."""

    source_dependency: SourceBoundDependency
    operation: TaskOperation
    prepared_subtask: PreparedDependentSubtask | None = None

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

    def with_prepared_subtask(self, prepared: PreparedDependentSubtask) -> TaskDependentTarget:
        """Bind an already validated child title to this exact parent-operation proof."""
        if self.operation is not TaskOperation.CREATE:
            raise TaskDependentTargetError("Only dependent Task CREATE accepts a child title")
        prepared.require_matches(self.source_dependency.dependent_quote.strip(), self.operation)
        return TaskDependentTarget(self.source_dependency, self.operation, prepared)

    def require_prepared_subtask_title(self, source_text: str) -> str:
        """Return the immutable prewrite title for this exact dependent CREATE."""
        if self.prepared_subtask is None:
            raise TaskDependentTargetError("Dependent subtask title was not prepared")
        return self.prepared_subtask.require_matches(source_text, self.operation)


def prepare_dependent_subtask_title(
    *, source_text: str, interpretation: TaskInterpretation, plan: RequestPlan
) -> PreparedDependentSubtask:
    """Validate the ordinary Core plan's one safe subtask title before any write.

    The UI service can only persist a pending title plus one physical parent
    link.  Reject every plan shape that would lose an extra property, fact,
    reference, target, or action rather than silently narrowing model output.
    """
    if (
        not isinstance(interpretation, TaskInterpretation)
        or interpretation.operation is not TaskOperation.CREATE
        or interpretation.source_text != source_text
        or len(interpretation.relationship_mentions) != 1
        or interpretation.relationship_mentions[0].role is not TaskRelationshipRole.PARENT_TASK
        or not isinstance(plan, RequestPlan)
        or len(plan.actions) != 1
        or not isinstance(plan.actions[0], WriteAction)
    ):
        raise TaskDependentTargetError("Dependent subtask plan is not one parent-linked CREATE")
    action = plan.actions[0]
    primaries = [unit for unit in action.units if not unit.reference_lookup_only]
    if len(primaries) != 1 or len(action.units) != 2:
        raise TaskDependentTargetError("Dependent subtask plan has unsupported targets")
    primary = primaries[0]
    helper = next(unit for unit in action.units if unit.reference_lookup_only)
    parent = interpretation.relationship_mentions[0]
    title = primary.target.entity
    if (
        not isinstance(title, str)
        or title != title.strip()
        or not title
        or len(title) > 240
        or source_text.count(title) != 1
        or title.casefold() == parent.text.casefold()
        or primary.target.type != TASK_TYPE
        or primary.intent != "record"
        or primary.cardinality != "one"
        or primary.destination_type is not None
        or not primary.force_create
        or primary.tag_changes
        or primary.fact_temporal_anchors not in {(), ((), ())}
        or len(primary.properties) != 1
        or primary.properties[0].field != "status"
        or primary.properties[0].op != "set"
        or primary.properties[0].value != "pending"
        or len(primary.references) != 1
        or primary.references[0].role != "parent_task"
        or primary.references[0].mention != parent.text
        or primary.references[0].target_index not in range(len(action.units))
        or action.units[primary.references[0].target_index] is not helper
        or helper.target.type != TASK_TYPE
        or helper.target.query != parent.text
        or helper.target.entity is not None
        or helper.intent != "record"
        or helper.properties
        or helper.tag_changes
        or helper.facts
        or helper.references
        or helper.fact_temporal_anchors
        or helper.cardinality != "one"
        or helper.destination_type is not None
        or helper.force_create
        or len(primary.facts) != 2
    ):
        raise TaskDependentTargetError("Dependent subtask plan would discard unsupported semantics")
    title_fact = next((fact for fact in primary.facts if "{{ref:" not in fact), None)
    parent_fact = next((fact for fact in primary.facts if "{{ref:0}}" in fact), None)
    if (
        title_fact is None
        or title_fact.strip().rstrip(".!?").strip() != title
        or parent_fact != "Tarea superior: {{ref:0}}."
    ):
        raise TaskDependentTargetError("Dependent subtask title or parent fact is not exact")
    return PreparedDependentSubtask(source_text, TaskOperation.CREATE, title)


def verify_dependent_task_semantics(
    *,
    full_source: str,
    antecedent_source: str,
    dependent_source: str,
    dependent_mention: str,
    interpretation: TaskInterpretation,
    attestations: tuple[Mapping[str, object], Mapping[str, object]],
) -> None:
    """Pure E2 prewrite check: reject model disagreement BEFORE Core writes.

    Canonical identity is deliberately NOT selected here. The later
    prove_dependent_task_target binds the evidence to physical Core Markdown.
    """
    if not isinstance(interpretation, TaskInterpretation):
        raise TaskDependentTargetError("Typed Tasks interpretation required")
    parent_create = (
        interpretation.operation is TaskOperation.CREATE
        and len(interpretation.relationship_mentions) == 1
        and interpretation.relationship_mentions[0].role is TaskRelationshipRole.PARENT_TASK
    )
    person_create = (
        interpretation.operation is TaskOperation.CREATE
        and not interpretation.relationship_mentions
    )
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
        or (person_create and interpretation.task_reference is not None)
        or (
            not parent_create
            and not person_create
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
        "target_type": "person" if person_create else TASK_TYPE,
        "operation": (
            "CREATE"
            if person_create
            else "CREATE_SUBTASK"
            if parent_create
            else interpretation.operation.value
        ),
        "operation_supported": True,
    }
    if any(not isinstance(att, Mapping) or dict(att) != required for att in attestations):
        raise TaskDependentTargetError("Uncorroborated or altered Task reference semantics")


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
    verify_dependent_task_semantics(
        full_source=full_source,
        antecedent_source=antecedent_source,
        dependent_source=dependent_source,
        dependent_mention=dependent_mention,
        interpretation=interpretation,
        attestations=attestations,
    )
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


def prove_dependent_person_reference(
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
) -> SourceBoundDependency:
    """Bind reviewed Task CREATE wording to one current Core Person receipt."""
    verify_dependent_task_semantics(
        full_source=full_source,
        antecedent_source=antecedent_source,
        dependent_source=dependent_source,
        dependent_mention=dependent_mention,
        interpretation=interpretation,
        attestations=attestations,
    )
    if interpretation.operation is not TaskOperation.CREATE or interpretation.relationship_mentions:
        raise TaskDependentTargetError("Dependent Person requires ordinary Task CREATE")
    try:
        proof = prove_source_bound_dependency(
            complete_original_source=full_source,
            antecedent_quote=antecedent_source,
            dependent_quote=dependent_source,
            exact_dependent_mention=dependent_mention,
            predecessor=core_predecessor,
            repository=repository,
            schema=schema,
        )
    except SourceBoundDependencyError as error:
        raise TaskDependentTargetError("Core Person receipt is not current") from error
    if proof.evidence.note_type != "person":
        raise TaskDependentTargetError("Core receipt does not identify a Person")
    return proof
