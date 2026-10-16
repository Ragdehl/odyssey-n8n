"""Opt-in production-owned whole-source P4 coordinator.

Router and independent GPT reviews supply UNTRUSTED hints. Core alone
compiles source-bound facts and performs canonical preflight, identity resolution,
reference binding, Task lifecycle validation, Writer and Git. A guarded outer
request ID protects the full multi-write delivery against blind retries.

This first version supports Core record/Task CREATE and delegates a *single*
Tasks-owned request to the ordinary Tasks interpreter/domain service; mixed
Work Session + Core requests are not yet supported and must fail closed.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime
from types import SimpleNamespace
from typing import Any
from zoneinfo import ZoneInfo

from odyssey_apps.tasks import (
    TaskLifecycleGuard,
    TaskOperation,
)
from odyssey_core.application import ApplicationResult, ApplicationStatus, execute_request
from odyssey_core.identity_boundary import AuthenticatedActorContext, SelfBindingRepository
from odyssey_core.notes import parse_note, scoped_note_decode_cache
from odyssey_core.storage import VaultRepository
from odyssey_core.whole_message_coverage import (
    WholeMessageCoverageError,
    validate_whole_message_coverage,
)
from odyssey_core.whole_message_identity_guard import (
    UnprovenPersonIdentityError,
    reject_unproven_person_collisions,
)
from odyssey_core.whole_message_relationship_proof import (
    WholeSourceRelationshipError,
    recheck_self_relationship,
    verify_self_relationship,
)
from odyssey_core.whole_message_speaker_proof import (
    WholeMessageSpeakerError,
    validate_dual_speaker_review,
)
from odyssey_core.whole_source_compiler import (
    WholeSourceCompilationError,
    compile_reviewed_operations,
)
from odyssey_core.whole_source_readback import assert_reviewed_markdown
from odyssey_runtime.whole_source_model_contract import (
    MIXED_TASK_CREATE_PROMPT,
    MIXED_TASK_CREATE_SCHEMA,
    PLAN_SCHEMA,
    PLANNER_INSTRUCTIONS,
    PROMPT_SOURCE_REVIEW,
    PROMPT_SPEAKER_A,
    PROMPT_SPEAKER_B,
    REVIEW_SCHEMA,
    ROUTE_SCHEMA,
    ROUTER_INSTRUCTIONS,
    SPEAKER_SCHEMA,
    TASK_ONLY_SCOPE_PROMPT,
    TASK_ONLY_SCOPE_SCHEMA,
)

ROUTER_MODEL = "gpt-6-luna"
PLANNER_MODEL = "gpt-5.6-luna"
MAX_SOURCE_NOTES = 5000


class WholeSourceLightError(ValueError):
    """A model suggestion or physical state is insufficient to authorize a source write."""


@dataclass
class WholeSourceLightExecutor:
    repository: VaultRepository
    schema: dict[str, Any]
    context_index: Any
    semantic_index: Any
    embedder: Any
    reasoner: Any
    bindings: SelfBindingRepository
    refresh_affected_indexes: Callable[[tuple[str, ...]], None]
    task_delegate: Callable[[str, str, AuthenticatedActorContext], ApplicationResult]
    client: Any
    progress: Callable[[str, dict[str, object]], None] | None = None
    timezone: str = "Europe/Paris"
    now: Callable[[], datetime] | None = None

    def _ask(self, model: str, instructions: str, payload: dict, schema: dict, name: str) -> dict:
        answer = self.client.responses.create(
            model=model,
            reasoning={"effort": "low"},
            store=False,
            max_output_tokens=1700,
            input=[
                {"role": "system", "content": instructions},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            text={
                "format": {"type": "json_schema", "name": name, "strict": True, "schema": schema}
            },
        )
        if answer.status != "completed":
            raise WholeSourceLightError("Provider response was not complete")
        result = json.loads(answer.output_text)
        if not isinstance(result, dict):
            raise WholeSourceLightError("Provider response shape is invalid")
        return result

    def _note_hints(self, source: str) -> list[dict]:
        # Source hints are NEVER canonical ID selections. Bound cost; no fixed
        # entity names, no DEV-only IDs or relationship inference from words.
        words = set(re.findall(r"[\wÀ-ÿ]+", source.casefold()))
        paths = self.repository.list_markdown_paths()
        if len(paths) > MAX_SOURCE_NOTES:
            raise WholeSourceLightError("Canonical hint scan budget exceeded")
        hints = []
        for path in paths:
            note = parse_note(self.repository.read_text(path))
            if note.metadata.get("type") not in {"person", "project"} or note.metadata.get(
                "deleted"
            ):
                continue
            name = str(note.metadata["name"])
            parts = re.findall(r"[\wÀ-ÿ]+", name.casefold())
            if parts and len(parts[0]) >= 3 and parts[0] in words:
                hints.append(
                    {"name": name, "type": note.metadata["type"], "id": str(note.metadata["id"])}
                )
            if len(hints) > 24:
                raise WholeSourceLightError("Source hint budget exceeded")
        return hints

    def __call__(
        self, source: str, delivery: str, actor: AuthenticatedActorContext, conversation_id: str
    ) -> ApplicationResult:
        # No trust caching: only parsed representations of byte-for-byte
        # identical canonical Markdown, and only within this one delivery.
        with scoped_note_decode_cache():
            return self._execute_source(source, delivery, actor, conversation_id)

    def _execute_source(
        self, source: str, delivery: str, actor: AuthenticatedActorContext, conversation_id: str
    ) -> ApplicationResult:
        if not isinstance(actor, AuthenticatedActorContext) or conversation_id != "main":
            raise WholeSourceLightError("Authenticated main conversation required")
        if not isinstance(source, str) or not source.strip() or len(source) > 4096:
            raise WholeSourceLightError("Invalid original source")
        instant = self.now() if self.now is not None else datetime.now(ZoneInfo(self.timezone))
        clock = {
            "date": instant.date().isoformat(),
            "time": instant.time().isoformat(timespec="seconds"),
            "timezone": self.timezone,
        }
        now = instant.isoformat()
        # Require current trusted SELF before any provider plan. No synthetic
        # string identity or inferred speaker-to-note mapping is permitted.
        self.bindings.resolve(actor.stable_user_id)
        if self.progress is not None:
            self.progress("routing.started", {})
        route = self._ask(
            ROUTER_MODEL,
            ROUTER_INSTRUCTIONS,
            {"original_source": source, "clock": clock},
            ROUTE_SCHEMA,
            "odyssey_light_capability_route_v1",
        )
        capabilities = route.get("capabilities")
        if (
            not isinstance(capabilities, list)
            or not capabilities
            or not set(capabilities) <= {"core", "tasks", "temporal"}
        ):
            return self._abstain(delivery)
        # Router can only propose an exact source span, never relationship
        # membership or a Note ID. Core re-grounds the group in CURRENT SELF.
        relationship = None
        relation_span = route.get("self_relation_span")
        if relation_span is not None:
            try:
                relationship = verify_self_relationship(
                    source,
                    relation_span,
                    repository=self.repository,
                    schema=self.schema,
                    actor=actor,
                    bindings=self.bindings,
                )
            except (WholeSourceRelationshipError, ValueError):
                return self._abstain(delivery)
        group_members = (
            [{"name": name} for _id, name in relationship.members]
            if relationship is not None
            else []
        )
        if self.progress is not None:
            self.progress("routing.ready", {"route_count": 1})
        if "tasks" in capabilities and "core" not in capabilities:
            # The router is a fallible hypothesis, NOT source coverage proof.
            # An independent model must attest this is exactly one Tasks-only
            # operation; otherwise no semantic unit may be silently dropped.
            scope = self._ask(
                PLANNER_MODEL,
                TASK_ONLY_SCOPE_PROMPT,
                {"original_source": source},
                TASK_ONLY_SCOPE_SCHEMA,
                "odyssey_task_only_scope_v1",
            )
            if (
                scope.get("only_task_semantics") is not True
                or scope.get("exactly_one_operation") is not True
                or scope.get("source_quote") != source
            ):
                return self._abstain(delivery)
            # Share the SAME domain service with Task UI for WORK SESSION;
            # ordinary task lifecycle remains Tasks interpreter → Core writer.
            if self.progress is not None:
                self.progress("action.delegate.started", {})
            return self.task_delegate(source, delivery, actor)
        if "core" not in capabilities:
            return self._abstain(delivery)
        if self.progress is not None:
            self.progress("planner.started", {})
        proposed = self._ask(
            PLANNER_MODEL,
            PLANNER_INSTRUCTIONS,
            {
                "original_source": source,
                "clock": clock,
                "routing_hint": route,
                "known_notes": self._note_hints(source),
                "verified_family": group_members,
            },
            PLAN_SCHEMA,
            "odyssey_light_shared_semantic_plan_v1",
        )
        proposed["_allowed_capabilities"] = capabilities
        if any(
            isinstance(item, dict) and item.get("kind") == "task"
            for item in proposed.get("facts", ())
        ):
            mixed_task_review = self._ask(
                PLANNER_MODEL,
                MIXED_TASK_CREATE_PROMPT,
                {"original_source": source, "suggested_facts": proposed.get("facts", [])},
                MIXED_TASK_CREATE_SCHEMA,
                "odyssey_mixed_task_create_v1",
            )
            if (
                mixed_task_review.get("only_new_task_creations") is not True
                or mixed_task_review.get("no_work_session_or_lifecycle_transition") is not True
                or mixed_task_review.get("source_quote") != source
            ):
                return self._abstain(delivery)
        review = self._ask(
            PLANNER_MODEL,
            PROMPT_SOURCE_REVIEW,
            {
                "source": source,
                "clock": clock,
                "proposed_facts": proposed.get("facts"),
                "proposed_entities": proposed.get("entities"),
                "core_verified_self_relationship": group_members or None,
            },
            REVIEW_SCHEMA,
            "odyssey_p2_source_coverage_v1",
        )
        try:
            validate_whole_message_coverage(
                source,
                proposed,
                review,
                capabilities,
                verified_relationship_members=tuple(name for _id, name in relationship.members)
                if relationship is not None
                else (),
            )
            names = tuple(
                sorted({name for fact in review["facts"] for name in fact["reference_names"]})
            )
            reject_unproven_person_collisions(self.repository, self.schema, names)
            speaker_payload = {
                "original_source": source,
                "facts": [
                    {"source_evidence": fact["source_evidence"]} for fact in proposed["facts"]
                ],
                "clock": clock,
            }
            speaker_a = self._ask(
                PLANNER_MODEL,
                PROMPT_SPEAKER_A,
                speaker_payload,
                SPEAKER_SCHEMA,
                "odyssey_speaker_full_A",
            )
            speaker_b = self._ask(
                ROUTER_MODEL,
                PROMPT_SPEAKER_B,
                speaker_payload,
                SPEAKER_SCHEMA,
                "odyssey_speaker_full_B",
            )
            attested = validate_dual_speaker_review(source, proposed["facts"], speaker_a, speaker_b)
            if any(f.assertion not in {"asserted", "planned"} for f in attested.facts):
                raise WholeMessageCoverageError("Non-affirmative input is not a completed event")
        except (WholeMessageCoverageError, UnprovenPersonIdentityError, WholeMessageSpeakerError):
            return self._abstain(delivery)
        # Compile ALL actions before ANY write. A missing owner, unsupported
        # Task lifecycle or invalid last fact cannot leave a partially
        # persisted multi-capability message behind.
        try:
            operations = compile_reviewed_operations(
                review, tuple(attested.requires_self_link(i) for i in range(len(attested.facts)))
            )
        except WholeSourceCompilationError:
            return self._abstain(delivery)
        if self.progress is not None:
            self.progress("planner.ready", {})
            self.progress("action.write.started", {})
        before = {
            path: self.repository.read_text(path) for path in self.repository.list_markdown_paths()
        }
        results: list[ApplicationResult] = []

        def execute_one(plan: Any, locator: str, task: bool = False) -> ApplicationResult:
            planner = SimpleNamespace(plan=lambda *_args, _plan=plan: _plan)
            # The P4 compiler is Core-owned. The Task App contributes only
            # its lifecycle preflight, never restructures a Core RequestPlan.
            return execute_request(
                source,
                planner=planner,
                repository=self.repository,
                schema=self.schema,
                context_index=self.context_index,
                semantic_index=self.semantic_index,
                embedder=self.embedder,
                contextual_reasoner=self.reasoner,
                authenticated_actor=actor,
                self_binding_repository=self.bindings,
                actor=actor.stable_user_id,
                now=now,
                context_limit=10,
                write_preflight_guard=TaskLifecycleGuard(TaskOperation.CREATE) if task else None,
                request_id_factory=lambda: locator,
            )

        # A SELF fact/member set might change while GPT is reasoning or between
        # source preflight and a delayed write. Never convert stale members to
        # fresh references, even when the prior reviewer was satisfied.
        if relationship is not None:
            try:
                recheck_self_relationship(
                    relationship,
                    repository=self.repository,
                    schema=self.schema,
                    actor=actor,
                    bindings=self.bindings,
                )
            except (WholeSourceRelationshipError, ValueError):
                return self._abstain(delivery)
        # The existing Core Writer and E3 guard remain the ONLY write path;
        # no app-specific plan rewrites or per-example validators execute.
        for operation in operations:
            if relationship is not None:
                try:
                    recheck_self_relationship(
                        relationship,
                        repository=self.repository,
                        schema=self.schema,
                        actor=actor,
                        bindings=self.bindings,
                    )
                except (WholeSourceRelationshipError, ValueError):
                    return self._partial(delivery, results) if results else self._abstain(delivery)
            result = execute_one(
                operation.plan,
                f"{delivery}-{operation.locator_suffix}",
                task=operation.task_create,
            )
            results.append(result)
            if result.status is not ApplicationStatus.COMPLETED:
                break
            if result.affected_stable_note_ids:
                self.refresh_affected_indexes(result.affected_stable_note_ids)
        candidate = self._partial(delivery, results)
        if candidate.status is not ApplicationStatus.COMPLETED:
            return candidate
        try:
            after = {
                path: self.repository.read_text(path)
                for path in self.repository.list_markdown_paths()
            }
            proof = assert_reviewed_markdown(
                repository=self.repository,
                schema=self.schema,
                context_index=self.context_index,
                before=before,
                after=after,
                request_id=delivery,
                review=review,
                self_roles=tuple(
                    attested.requires_self_link(i) for i in range(len(attested.facts))
                ),
                self_id=self.bindings.resolve(actor.stable_user_id).person_note_id,
            )
            if proof["physical_fact_count"] != len(review["facts"]):
                raise AssertionError("A source assertion lacks canonical readback")
        except (AssertionError, KeyError, ValueError):
            # Some earlier actions may already be durable. Preserve real
            # affected IDs and return PARTIAL, never falsely announce success.
            return replace(
                candidate,
                status=ApplicationStatus.PARTIAL,
                clarification_code="FULL_SOURCE_PHYSICAL_READBACK_UNVERIFIED",
            )
        return candidate

    @staticmethod
    def _abstain(delivery: str) -> ApplicationResult:
        return ApplicationResult(
            delivery,
            ApplicationStatus.NEEDS_ATTENTION,
            (),
            (),
            clarification_code="FULL_SOURCE_REVIEW_OR_IDENTITY_UNVERIFIED",
        )

    @staticmethod
    def _partial(delivery: str, results: list[ApplicationResult]) -> ApplicationResult:
        if not results:
            return WholeSourceLightExecutor._abstain(delivery)
        complete = all(r.status is ApplicationStatus.COMPLETED for r in results)
        return replace(
            results[-1],
            request_id=delivery,
            status=ApplicationStatus.COMPLETED if complete else ApplicationStatus.PARTIAL,
            action_results=tuple(action for r in results for action in r.action_results),
            affected_stable_note_ids=tuple(
                dict.fromkeys(n for r in results for n in r.affected_stable_note_ids)
            ),
        )
