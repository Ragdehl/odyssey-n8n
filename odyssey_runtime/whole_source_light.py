"""Opt-in production-owned whole-source P4 coordinator.

Router and independent GPT reviews supply UNTRUSTED hints. Core alone
compiles source-bound facts and performs canonical preflight, identity resolution,
reference binding, Task lifecycle validation, Writer and Git. A guarded outer
request ID protects the full multi-write delivery against blind retries.

The opt-in path supports verified Core plus Task and Work Session operations,
including narrow N-group dependent DAG execution. Unsupported multi-target,
session-instance and cross-App dependencies fail closed without source loss.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from contextvars import ContextVar
from dataclasses import dataclass, replace
from datetime import datetime
from json import JSONDecodeError
from time import perf_counter
from types import SimpleNamespace
from typing import Any
from zoneinfo import ZoneInfo

from openai import OpenAIError

from odyssey_apps.tasks import (
    CanonicalSessionEvidence,
    PreparedDependentSubtask,
    SessionDependencyError,
    TaskBatchPreflightError,
    TaskDependentTarget,
    TaskDependentTargetError,
    TaskInterpretation,
    TaskLifecycleGuard,
    TaskOperation,
    TaskPersonReference,
    prove_dependent_person_reference,
    prove_dependent_task_target,
    validate_task_batch_prewrite,
    verify_dependent_task_semantics,
    verify_session_dependency,
)
from odyssey_core.application import ApplicationResult, ApplicationStatus, execute_request
from odyssey_core.context import ContextIndexError
from odyssey_core.dependent_group_evidence import (
    CanonicalGroupEvidenceError,
    prove_canonical_group_handoff,
)
from odyssey_core.dependent_group_graph import (
    DependentGroupGraphError,
    classify_dependent_group_review_rejection,
    verify_dependent_group_graph,
)
from odyssey_core.dependent_source_scopes import (
    DependentSourceScopesError,
    verify_dependent_source_scopes,
)
from odyssey_core.identity_boundary import AuthenticatedActorContext, SelfBindingRepository
from odyssey_core.independent_source_scopes import (
    IndependentSourceScopesError,
    verify_independent_source_scopes,
)
from odyssey_core.notes import scoped_note_decode_cache
from odyssey_core.observability import (
    OperationalEvidence,
    OperationalOutcome,
    OperationalStage,
    SpanRecorder,
)
from odyssey_core.source_bound_dependency import SourceBoundDependency
from odyssey_core.storage import VaultRepository
from odyssey_core.temporal_interpretation import TemporalInterpretation
from odyssey_core.verified_metadata_catalog import scoped_verified_metadata_catalog
from odyssey_core.whole_message_coverage import (
    WholeMessageCoverageError,
    anchor_planned_source_evidence,
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
from odyssey_runtime.routing import _aggregate as aggregate_verified_application_results
from odyssey_runtime.whole_source_model_contract import (
    DEPENDENT_GRAPH_PARTITION_PROMPT,
    DEPENDENT_GRAPH_PARTITION_SCHEMA,
    DEPENDENT_GRAPH_REVIEW_PROMPT,
    DEPENDENT_GRAPH_REVIEW_SCHEMA,
    DEPENDENT_SESSION_LINK_REVIEW_A,
    DEPENDENT_SESSION_LINK_REVIEW_B,
    DEPENDENT_SESSION_LINK_REVIEW_SCHEMA,
    DEPENDENT_TASK_PARTITION_PROMPT,
    DEPENDENT_TASK_PARTITION_SCHEMA,
    DEPENDENT_TASK_TARGET_REVIEW_A,
    DEPENDENT_TASK_TARGET_REVIEW_B,
    DEPENDENT_TASK_TARGET_REVIEW_SCHEMA,
    INDEPENDENT_SCOPE_PARTITION_PROMPT,
    INDEPENDENT_SCOPE_PARTITION_SCHEMA,
    INDEPENDENT_SCOPE_REVIEW_PROMPT,
    INDEPENDENT_SCOPE_REVIEW_SCHEMA,
    MIXED_TASK_CREATE_PROMPT,
    MIXED_TASK_CREATE_SCHEMA,
    PLAN_CORE_ANCHORED_SCHEMA,
    PLAN_SCHEMA,
    PLANNER_CORE_ANCHORED_INSTRUCTIONS,
    PLANNER_INSTRUCTIONS,
    PROMPT_SOURCE_REVIEW,
    PROMPT_SOURCE_REVIEW_CORE_ANCHORED,
    PROMPT_SPEAKER_A,
    PROMPT_SPEAKER_B,
    REVIEW_CORE_ANCHORED_SCHEMA,
    REVIEW_SCHEMA,
    ROUTE_SCHEMA,
    ROUTER_INSTRUCTIONS,
    SPEAKER_SCHEMA,
    TASK_ONLY_SCOPE_PROMPT,
    TASK_ONLY_SCOPE_SCHEMA,
)

ROUTER_MODEL = "gpt-6-luna"
PLANNER_MODEL = "gpt-5.6-luna"
# Request-local, content-free provider telemetry. No cross-actor or
# cross-request mutable state is stored on the long-lived P4 executor.
_P4_PROVIDER_SPANS: ContextVar[SpanRecorder | None] = ContextVar(
    "odyssey_p4_provider_spans", default=None
)


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
    # Prewrite-independent source-speaker reviewers can run concurrently on
    # the DEV provider. The frozen provider client stays sequential by default.
    # This does not remove either attestation or allow a write before both.
    parallel_speaker_reviews: bool = False
    # Coverage and independent speaker reviews use the SAME proposed facts.
    # They can overlap BEFORE any mutations; approvals remain compulsory.
    parallel_coverage_speaker_reviews: bool = False
    parallel_target_decisions: bool = False
    task_create_batch_enabled: bool = False
    # Experimental across ALL Core/Tasks source-reviewed routes, not a Task
    # cardinality special case; frozen provider contracts retain v1 by default.
    core_anchored_coverage_enabled: bool = False
    prewrite_diagnostic: Callable[[str, str, dict[str, int | bool]], None] | None = None
    # Reuse Core's existing persisted pending-work recorder. Losing an
    # uncertain Day write must not erase the pending review evidence.
    pending_recorder: Any | None = None
    refresh_between_independent_scopes: Callable[[tuple[str, ...]], None] | None = None
    operation_manifest_begin: (
        Callable[
            [str, str, AuthenticatedActorContext, tuple[tuple[str, str, tuple[int, ...]], ...]],
            None,
        ]
        | None
    ) = None
    operation_manifest_observe: (
        Callable[[str, str, AuthenticatedActorContext, int, str, ApplicationResult], None] | None
    ) = None
    # Distinct capability-owned adapters injected by production composition.
    # Optional for existing Core-only/independent tests. No new Writer.
    # Optional independent N-scope preflight and product Task execution.
    # Both must be installed together: a prechecked Task interpretation is
    # executed exactly once, never reinterpreted after an earlier Core WRITE.
    independent_task_prepare: (
        Callable[[str, datetime], tuple[TaskInterpretation, TemporalInterpretation | None]] | None
    ) = None
    independent_task_delegate: (
        Callable[
            [
                str,
                str,
                AuthenticatedActorContext,
                TaskInterpretation,
                TemporalInterpretation | None,
                datetime,
            ],
            ApplicationResult,
        ]
        | None
    ) = None
    dependent_core_delegate: (
        Callable[[str, str, AuthenticatedActorContext, datetime], ApplicationResult] | None
    ) = None
    # Enables ordinary Task CREATE with a current Core Person receipt.
    dependent_person_create_enabled: bool = False
    dependent_task_prepare: (
        Callable[[str, datetime], tuple[TaskInterpretation, TemporalInterpretation | None]] | None
    ) = None
    dependent_subtask_prepare: (
        Callable[[str, TaskInterpretation, datetime], PreparedDependentSubtask] | None
    ) = None
    dependent_session_delegate: (
        Callable[
            [
                str,
                str,
                AuthenticatedActorContext,
                TaskInterpretation,
                TemporalInterpretation | None,
                TaskDependentTarget,
                datetime,
                CanonicalSessionEvidence | None,
            ],
            tuple[ApplicationResult, CanonicalSessionEvidence | None],
        ]
        | None
    ) = None
    dependent_task_delegate: (
        Callable[
            [
                str,
                str,
                AuthenticatedActorContext,
                TaskInterpretation,
                TemporalInterpretation | None,
                TaskDependentTarget | TaskPersonReference,
                datetime,
            ],
            ApplicationResult,
        ]
        | None
    ) = None

    @staticmethod
    def _prewrite_reason_code(error: Exception) -> int:
        """Only own fixed contract errors may become bounded numeric codes."""
        fixed = {
            "Non-affirmative input is not a completed event": 10,
            "Atomic source evidence mismatch": 11,
            "Source reviewer invented a participant": 12,
            "Participant absent from original source": 13,
            "Symbolic Core references missing or repeated": 14,
            "Fact evidence order differs from source order": 15,
            "Independent reviewers disagree on speaker or assertion": 21,
            "Source-attested grammatical claim is invalid": 22,
            "Model ordinal sequence is incomplete": 23,
            "Independent source review count changed": 24,
            "An uncertain assertion cannot authorize a speaker link": 25,
        }
        message = str(error)
        if message.startswith("UNPROVEN_PARTIAL_CANONICAL_IDENTITY: "):
            return 31
        if message.startswith("AMBIGUOUS_CANONICAL_PERSON: "):
            return 32
        return fixed.get(message, 0)

    def _observe_prewrite(self, delivery: str, gate: str, **values: int | bool) -> None:
        """Prewrite telemetry never grants write authority."""
        if self.prewrite_diagnostic is not None:
            try:
                self.prewrite_diagnostic(delivery, gate, values)
            except Exception:
                pass

    def _ask(self, model: str, instructions: str, payload: dict, schema: dict, name: str) -> dict:
        # Same strict provider contract in production and frozen tests. Only
        # the timing wrapper differs; inputs never enter the request trace.
        arguments = {
            "model": model,
            "reasoning": {"effort": "low"},
            "store": False,
            "max_output_tokens": 1700,
            "input": [
                {"role": "system", "content": instructions},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": name,
                    "strict": True,
                    "schema": schema,
                }
            },
        }
        try:
            recorder = _P4_PROVIDER_SPANS.get()
            create = self.client.responses.create
            answer = (
                recorder.invoke(f"provider.{model}.{name}", create, **arguments)
                if recorder is not None
                else create(**arguments)
            )
        except (OpenAIError, TimeoutError, ConnectionError, OSError) as error:
            raise WholeSourceLightError("Bounded P4 provider is unavailable") from error
        if answer.status != "completed":
            raise WholeSourceLightError("Provider response was not complete")
        try:
            result = json.loads(answer.output_text)
        except (JSONDecodeError, TypeError, ValueError) as error:
            raise WholeSourceLightError("Bounded P4 provider response is invalid") from error
        if not isinstance(result, dict):
            raise WholeSourceLightError("Provider response shape is invalid")
        return result

    def _speaker_occurrence_instructions(self) -> str:
        if not self.core_anchored_coverage_enabled:
            return ""
        return (
            " EVIDENCE V2: For repeated words or assertions, each fact has "
            "optional ORIGINAL-source context anchoring its specific occurrence "
            "and extra literal supporting fragments. Use that typed context to "
            "interpret exactly that fact, not another occurrence of the same "
            "words. Return source_quote exactly equal to source_evidence, "
            "not the context, and never claim a canonical identity."
        )

    def _speaker_source_rows(self, proposed: dict) -> list[dict[str, object]]:
        """Supply every attestor the same Core-anchored original occurrence.

        This is generic to any factual domain; the model still cannot bind a
        canonical SELF id and must quote the original primary unchanged.
        """
        rows = []
        for fact in proposed["facts"]:
            row = {"source_evidence": fact["source_evidence"]}
            if self.core_anchored_coverage_enabled:
                row.update(
                    {
                        "source_evidence_context": fact["source_evidence_context"],
                        "source_evidence_fragments": fact["source_evidence_fragments"],
                        "source_evidence_fragment_contexts": fact[
                            "source_evidence_fragment_contexts"
                        ],
                    }
                )
            rows.append(row)
        return rows

    def _independent_speaker_reviews(self, payload: dict) -> tuple[dict, dict]:
        """Run independently required attestations concurrently, never skip one.

        Only the true provider path opts in. Each thread owns its own
        SpanRecorder and the caller joins the two bounded duration records;
        the request's parent SpanRecorder is never modified concurrently.
        """
        if not self.parallel_speaker_reviews:
            return (
                self._ask(
                    PLANNER_MODEL,
                    (PROMPT_SPEAKER_A + self._speaker_occurrence_instructions()),
                    payload,
                    SPEAKER_SCHEMA,
                    "odyssey_speaker_full_A",
                ),
                self._ask(
                    ROUTER_MODEL,
                    (PROMPT_SPEAKER_B + self._speaker_occurrence_instructions()),
                    payload,
                    SPEAKER_SCHEMA,
                    "odyssey_speaker_full_B",
                ),
            )

        parent_recorder = _P4_PROVIDER_SPANS.get()
        origin = parent_recorder.origin if parent_recorder is not None else perf_counter()

        def review(model: str, instructions: str, name: str) -> tuple[dict, tuple]:
            thread_recorder = SpanRecorder(origin, perf_counter)
            token = _P4_PROVIDER_SPANS.set(thread_recorder)
            try:
                value = self._ask(model, instructions, payload, SPEAKER_SCHEMA, name)
            finally:
                _P4_PROVIDER_SPANS.reset(token)
            return value, thread_recorder.spans

        with ThreadPoolExecutor(max_workers=2, thread_name_prefix="odyssey-p4-review") as pool:
            future_a = pool.submit(
                review,
                PLANNER_MODEL,
                PROMPT_SPEAKER_A + self._speaker_occurrence_instructions(),
                "odyssey_speaker_full_A",
            )
            future_b = pool.submit(
                review,
                ROUTER_MODEL,
                PROMPT_SPEAKER_B + self._speaker_occurrence_instructions(),
                "odyssey_speaker_full_B",
            )
            first, first_spans = future_a.result()
            second, second_spans = future_b.result()
        if parent_recorder is not None:
            parent_recorder.spans += tuple(
                sorted((*first_spans, *second_spans), key=lambda span: span.start_offset_ms)
            )
        return first, second

    def _complete_bounded_speaker_counts(
        self,
        delivery: str,
        payload: dict,
        first: dict,
        second: dict,
    ) -> tuple[dict, dict]:
        """One independent PREWRITE redo for omitted rows, never disagreements.

        A missing reviewer row is a mechanical incomplete provider output,
        not a second opinion. A retry never sees the other reviewer's answer
        and cannot override dual-source attestation or a semantic veto.
        """
        expected = len(payload["facts"])

        def incomplete(candidate: dict) -> bool:
            rows = candidate.get("facts")
            return not isinstance(rows, list) or len(rows) != expected

        redo_a, redo_b = incomplete(first), incomplete(second)
        if redo_a or redo_b:
            self._observe_prewrite(
                delivery,
                "speaker_count_retry",
                reviewer_a=redo_a,
                reviewer_b=redo_b,
                expected_facts=expected,
            )
        if redo_a:
            first = self._ask(
                PLANNER_MODEL,
                PROMPT_SPEAKER_A + self._speaker_occurrence_instructions(),
                payload,
                SPEAKER_SCHEMA,
                "odyssey_speaker_full_A",
            )
        if redo_b:
            second = self._ask(
                ROUTER_MODEL,
                PROMPT_SPEAKER_B + self._speaker_occurrence_instructions(),
                payload,
                SPEAKER_SCHEMA,
                "odyssey_speaker_full_B",
            )
        return first, second

    def _review_and_attest_concurrently(
        self,
        source: str,
        clock: dict[str, str],
        proposed: dict,
        group_members: list[dict],
    ) -> tuple[dict, tuple[dict, dict]]:
        """Overlap independent prewrite attestations, preserving every veto.

        Coverage reviews proposal/source, speakers review the SAME proposal.
        None can authorize a write alone; the existing validators run AFTER
        all three provider calls finish. DEV-only; false by default.
        """
        parent_recorder = _P4_PROVIDER_SPANS.get()
        origin = parent_recorder.origin if parent_recorder is not None else perf_counter()
        speaker_payload = {
            "original_source": source,
            "facts": self._speaker_source_rows(proposed),
            "clock": clock,
        }

        def run_speakers() -> tuple[tuple[dict, dict], tuple]:
            local_recorder = SpanRecorder(origin, perf_counter)
            token = _P4_PROVIDER_SPANS.set(local_recorder)
            try:
                result = self._independent_speaker_reviews(speaker_payload)
            finally:
                _P4_PROVIDER_SPANS.reset(token)
            return result, local_recorder.spans

        with ThreadPoolExecutor(max_workers=2, thread_name_prefix="odyssey-p4-prewrite") as pool:
            speaker_future = pool.submit(run_speakers)
            coverage = self._ask(
                PLANNER_MODEL,
                (
                    PROMPT_SOURCE_REVIEW_CORE_ANCHORED
                    if self.core_anchored_coverage_enabled
                    else PROMPT_SOURCE_REVIEW
                ),
                {
                    "source": source,
                    "clock": clock,
                    "proposed_facts": proposed.get("facts"),
                    "proposed_entities": proposed.get("entities"),
                    "core_verified_self_relationship": group_members or None,
                },
                (
                    REVIEW_CORE_ANCHORED_SCHEMA
                    if self.core_anchored_coverage_enabled
                    else REVIEW_SCHEMA
                ),
                (
                    "odyssey_p4_source_coverage_v2"
                    if self.core_anchored_coverage_enabled
                    else "odyssey_p2_source_coverage_v1"
                ),
            )
            speakers, speaker_spans = speaker_future.result()
        if parent_recorder is not None:
            parent_recorder.spans += tuple(
                sorted(speaker_spans, key=lambda span: span.start_offset_ms)
            )
        return coverage, speakers

    @staticmethod
    def _measure_local(name: str, operation: Callable, *args: Any, **kwargs: Any) -> Any:
        """Trace one deterministic Core boundary without exposing user data."""
        recorder = _P4_PROVIDER_SPANS.get()
        return (
            recorder.invoke(f"local.{name}", operation, *args, **kwargs)
            if recorder is not None
            else operation(*args, **kwargs)
        )

    def _note_hints(self, source: str) -> list[dict]:
        # The existing derived context index is only a bounded hint source.
        # Core subsequently resolves ALL identities against live Markdown.
        words = frozenset(re.findall(r"[\wÀ-ÿ]+", source.casefold()))
        try:
            return list(
                self.context_index.source_name_hint_candidates(
                    self.repository, source_words=words, limit=24
                )
            )
        except ContextIndexError as error:
            raise WholeSourceLightError("Canonical hints are unavailable or stale") from error

    def __call__(
        self, source: str, delivery: str, actor: AuthenticatedActorContext, conversation_id: str
    ) -> ApplicationResult:
        # Instrument only the authenticated request's MODEL boundaries. Source
        # text, token contents, Note identities and prompts never enter spans.
        # The existing typed Core/Tasks stage evidence remains authoritative.
        started = perf_counter()
        recorder = SpanRecorder(started, perf_counter)
        token = _P4_PROVIDER_SPANS.set(recorder)
        try:
            with (
                scoped_note_decode_cache(),
                self.repository.scoped_unchanged_reads(),
                scoped_verified_metadata_catalog(index_path=str(self.context_index.path)),
            ):
                try:
                    result = self._execute_source(source, delivery, actor, conversation_id)
                except WholeSourceLightError:
                    # The P4-specific error class is raised only by model and
                    # source-hint PREWRITE steps. Core/Tasks mutations use their
                    # own typed failures, which must still propagate and retain
                    # the E3 claim if a physical write may have happened.
                    result = self._abstain(delivery, "FULL_SOURCE_PROVIDER_OR_CONTEXT_UNAVAILABLE")
        finally:
            _P4_PROVIDER_SPANS.reset(token)
        elapsed_ms = max(0.0, (perf_counter() - started) * 1000)
        stages = result.operational.stages
        # One true source wall-clock stage with bounded model-only substeps.
        # The Core Writers/Task services continue to own their own stages;
        # overlaps here describe nested work, not additional operations.
        source_stage = OperationalStage(
            "application.source_processing",
            OperationalOutcome.COMPLETED,
            elapsed_ms,
            substeps=recorder.spans[:64],
        )
        flow = result.execution_flow
        if (
            flow is None
            and result.status is ApplicationStatus.COMPLETED
            and 0 < len(stages) <= 16
            and isinstance(source, str)
            and 0 < len(source) <= 4096
        ):
            # The Core-owned whole-source writer may produce several real
            # actions from ONE reviewed source. Describe exactly one Core
            # scope containing ALL observed steps; never fabricate a split
            # into source spans or dependency edges the Router didn't prove.
            first_router_ms = recorder.spans[0].duration_ms if recorder.spans else 0.0
            router_stage = OperationalStage(
                "application.router", OperationalOutcome.COMPLETED, first_router_ms
            )
            # Project actual SUCCEEDED Core unit receipts, never Planner
            # intentions. Each item is physically postwrite; no identity
            # inferred from text. The browser supports up to eight entries.
            verified_writes = [
                {
                    "status": unit.status.value,
                    "operation": unit.operation[:48],
                    "target": unit.stable_note_id[:160],
                }
                for action in result.action_results
                for unit in action.unit_results
                if unit.status.value == "succeeded"
                and unit.materially_affected
                and unit.stable_note_id in result.affected_stable_note_ids
                and isinstance(unit.operation, str)
                and unit.operation
                and isinstance(unit.stable_note_id, str)
                and unit.stable_note_id
            ]
            # Prior per-operation route_index values are action ordinals,
            # not Router-proven source subroutes. One complete Core source
            # route owns all those actions, so retain the action ordering and
            # normalize only its presentation route ownership to index zero.
            # Physical unit receipts remain independently visible above.
            stages = tuple(
                replace(stage, route_index=0) if stage.route_index is not None else stage
                for stage in stages
            )
            flow = {
                "version": 1,
                "input": source,
                "parallel_preparation": False,
                "routes": [
                    {
                        "capability": "core",
                        "text": source,
                        "stage_count": len(stages),
                        "status": result.status.value,
                        "temporal": [],
                        **({"writes": verified_writes} if 0 < len(verified_writes) <= 8 else {}),
                    }
                ],
            }
            stages = (router_stage, *stages)
        if flow is not None and result.execution_flow is not None:
            # Existing N-scope flows already have a real application.router
            # followed by exact per-route stages. Keep its position/owner
            # unchanged for the E2 ledger and JS flow contract; attach only
            # child provider timings without inserting a synthetic stage.
            if stages and stages[0].name == "application.router":
                stages = (replace(stages[0], substeps=recorder.spans[:64]), *stages[1:])
            operational_stages = stages
        else:
            operational_stages = (source_stage, *stages)
        return replace(
            result,
            operational=OperationalEvidence(elapsed_ms, operational_stages),
            execution_flow=flow,
        )

    def _execute_source(
        self,
        source: str,
        delivery: str,
        actor: AuthenticatedActorContext,
        conversation_id: str,
        *,
        independent_scope: str | None = None,
        delivery_instant: datetime | None = None,
        prechecked_task_scope: dict[str, object] | None = None,
    ) -> ApplicationResult:
        if not isinstance(actor, AuthenticatedActorContext) or conversation_id != "main":
            raise WholeSourceLightError("Authenticated main conversation required")
        if not isinstance(source, str) or not source.strip() or len(source) > 4096:
            raise WholeSourceLightError("Invalid original source")
        instant = (
            delivery_instant
            if delivery_instant is not None
            else self.now()
            if self.now is not None
            else datetime.now(ZoneInfo(self.timezone))
        )
        clock = {
            "date": instant.date().isoformat(),
            "time": instant.time().isoformat(timespec="seconds"),
            "timezone": self.timezone,
        }
        # Atomic facts require an exact offset-aware second timestamp. The
        # incoming runtime clock usually carries microseconds; passing its
        # raw isoformat silently fails BOTH Day CREATE and UPDATE preflight.
        now = instant.isoformat(timespec="seconds")
        # Require current trusted SELF before any provider plan. No synthetic
        # string identity or inferred speaker-to-note mapping is permitted.
        self.bindings.resolve(actor.stable_user_id)
        if self.progress is not None:
            self.progress("routing.started", {})
        router_started = perf_counter()
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
        if independent_scope is not None and (
            independent_scope not in {"core", "tasks"}
            or independent_scope not in capabilities
            or not set(capabilities) <= {independent_scope, "temporal"}
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
        # Only a fully source-partitioned and independently attested set of
        # standalone app scopes can use the existing per-App semantic pathway.
        # No dependency, common antecedent or date may be inherited across it.
        # Mixed dependent Task CREATE continues through whole-source Core.
        scopes = route.get("app_scopes")
        independent_route = (
            not independent_scope
            and "core" in capabilities
            and "tasks" in capabilities
            and route.get("interpretation") == "separable"
            and isinstance(scopes, list)
            and len(scopes) >= 2
            and all(
                isinstance(item, dict)
                and isinstance(item.get("capability"), str)
                and item["capability"] in {"core", "tasks"}
                and item.get("depends_on_another_scope") is False
                for item in scopes
            )
            and {item["capability"] for item in scopes} == {"core", "tasks"}
        )
        # A truly dependent source cannot be partitioned as independent. A
        # separately reviewed literal Core→Tasks chain can use the normal
        # Core planner and Tasks interpreter, but never a Router-supplied ID.
        dependent_route = (
            self.dependent_core_delegate is not None
            and self.dependent_task_prepare is not None
            and self.dependent_task_delegate is not None
            and independent_scope is None
            and "core" in capabilities
            and "tasks" in capabilities
            and route.get("interpretation") == "joint"
            and isinstance(scopes, list)
            and len(scopes) >= 2
            and any(
                isinstance(item, dict) and item.get("depends_on_another_scope") is True
                for item in scopes
            )
        )
        if (
            independent_scope is None
            and "core" in capabilities
            and "tasks" in capabilities
            and route.get("interpretation") == "joint"
            and isinstance(scopes, list)
            and len(scopes) > 2
            and not dependent_route
        ):
            # Missing Tasks adapters can NEVER demote a claimed multi-App
            # joint dependency into a person-only Core write. The complete
            # N-scope semantics remain unexecutable until the domain is wired.
            return self._abstain(delivery, "DEPENDENT_N_GRAPH_ADAPTER_UNAVAILABLE")
        if dependent_route:
            # This opt-in adapter owns precisely ONE Core antecedent and ONE
            # downstream Tasks operation. A Router description with extra
            # groups or an opposite/unproved edge is NOT permission to silently
            # discard N:M semantics. Preserve the complete source and abstain.
            if len(scopes) > 2 and (
                not isinstance(scopes[0], dict)
                or scopes[0].get("capability") != "core"
                or any(
                    isinstance(item, dict)
                    and item.get("capability") == "core"
                    and item.get("depends_on_another_scope") is not False
                    for item in scopes
                )
            ):
                return self._abstain(delivery, "DEPENDENT_SOURCE_GROUP_UNSUPPORTED")
            if len(scopes) > 2:
                return self._execute_dependent_graph(
                    source,
                    delivery,
                    actor,
                    delivery_instant=instant,
                    router_started=router_started,
                    route_scopes=scopes,
                )
            if (
                len(scopes) != 2
                or not all(isinstance(part, dict) for part in scopes)
                or scopes[0].get("capability") != "core"
                or scopes[0].get("depends_on_another_scope") is not False
                or scopes[1].get("capability") != "tasks"
                or scopes[1].get("depends_on_another_scope") is not True
            ):
                return self._abstain(delivery, "DEPENDENT_SOURCE_GROUP_UNSUPPORTED")
            dependent_result = self._execute_dependent_core_task(
                source,
                delivery,
                actor,
                delivery_instant=instant,
                router_started=router_started,
            )
            if dependent_result is not None:
                return dependent_result
            # Only a non-lifecycle mixed Task CREATE can fall through to
            # the existing whole-source Core planner + Task CREATE auditor.
            # A Work Session candidate with unproven target never falls back
            # to a less constrained Task-only mutation route.
        if independent_route:
            return self._execute_independent_scopes(
                source,
                delivery,
                actor,
                conversation_id,
                delivery_instant=instant,
                router_started=router_started,
                route_scopes=scopes,
            )
        task_only_batch = False
        if "tasks" in capabilities and "core" not in capabilities:
            # The router is a fallible hypothesis, NOT source coverage proof.
            # An independent model must attest this is exactly one Tasks-only
            # operation; otherwise no semantic unit may be silently dropped.
            scope = prechecked_task_scope
            if scope is None:
                scope = self._ask(
                    PLANNER_MODEL,
                    TASK_ONLY_SCOPE_PROMPT,
                    {"original_source": source},
                    TASK_ONLY_SCOPE_SCHEMA,
                    "odyssey_task_only_scope_v1",
                )
            self._observe_prewrite(
                delivery,
                "task_scope_verdict",
                task_only=scope.get("only_task_semantics") is True,
                one_operation=scope.get("exactly_one_operation") is True,
                source_aligned=scope.get("source_quote") == source,
            )
            if scope.get("only_task_semantics") is not True or scope.get("source_quote") != source:
                self._observe_prewrite(delivery, "task_scope_rejected")
                return self._abstain(delivery)
            single_operation = scope.get("exactly_one_operation") is True
            if single_operation and self.task_create_batch_enabled:
                # A single-scope hypothesis cannot authorize dropping a
                # second obligation. Seek INDEPENDENT source-wide cardinality
                # evidence before calling the single-operation Task delegate.
                # Only the exact unchanged source passes to the second
                # auditor; neither reviewer receives the other's judgment.
                independent = self._ask(
                    ROUTER_MODEL,
                    TASK_ONLY_SCOPE_PROMPT,
                    {"original_source": source},
                    TASK_ONLY_SCOPE_SCHEMA,
                    "odyssey_task_only_scope_v1",
                )
                self._observe_prewrite(
                    delivery,
                    "task_second_scope_verdict",
                    task_only=independent.get("only_task_semantics") is True,
                    one_operation=independent.get("exactly_one_operation") is True,
                    source_aligned=independent.get("source_quote") == source,
                )
                if (
                    independent.get("only_task_semantics") is not True
                    or independent.get("source_quote") != source
                ):
                    self._observe_prewrite(delivery, "task_scope_rejected")
                    return self._abstain(delivery)
                if independent.get("exactly_one_operation") is not True:
                    self._observe_prewrite(delivery, "task_cardinality_disagreed")
                    single_operation = False
            if single_operation:
                # Exactly one independently corroborated operation retains
                # the standard Task interpreter including lifecycle/sessions.
                if self.progress is not None:
                    self.progress("action.delegate.started", {})
                return self.task_delegate(source, delivery, actor)
            if not self.task_create_batch_enabled:
                self._observe_prewrite(delivery, "task_scope_rejected")
                return self._abstain(delivery)
            # Multi-Task CREATE uses the same Core compiler and canonical
            # Writer as a mixed Core+Task source. Never delegate only the
            # first task or convert a lifecycle action to Task CREATE.
            task_only_batch = True
        if "core" not in capabilities and not task_only_batch:
            return self._abstain(delivery)
        if self.progress is not None:
            self.progress("planner.started", {})
        # One bounded, PREWRITE re-evaluation only if an independent source
        # reviewer explicitly finds an omission, the proposal had no known
        # ambiguities, and nothing has been mutated. Never retry a genuinely
        # unresolved identity, unsupported Task operation, speaker conflict or
        # any delivery after Core could already have persisted a note.
        reviewed_ok = False
        concurrent_speakers: tuple[dict, dict] | None = None
        known_notes = self._measure_local("source_name_hints", self._note_hints, source)
        for attempt in range(2):
            concurrent_speakers = None
            proposed = self._ask(
                PLANNER_MODEL,
                (
                    PLANNER_CORE_ANCHORED_INSTRUCTIONS
                    if self.core_anchored_coverage_enabled
                    else PLANNER_INSTRUCTIONS
                ),
                {
                    "original_source": source,
                    "clock": clock,
                    "routing_hint": route,
                    "known_notes": known_notes,
                    "verified_family": group_members,
                    "prior_independent_coverage_rejected": bool(attempt),
                },
                (PLAN_CORE_ANCHORED_SCHEMA if self.core_anchored_coverage_enabled else PLAN_SCHEMA),
                (
                    "odyssey_light_shared_semantic_plan_v2"
                    if self.core_anchored_coverage_enabled
                    else "odyssey_light_shared_semantic_plan_v1"
                ),
            )
            proposed["_allowed_capabilities"] = capabilities
            if self.core_anchored_coverage_enabled:
                try:
                    anchor_planned_source_evidence(source, proposed)
                except WholeMessageCoverageError as error:
                    self._observe_prewrite(
                        delivery,
                        "coverage_contract",
                        reason_code=self._prewrite_reason_code(error),
                    )
                    return self._abstain(delivery)
            if task_only_batch and (
                not isinstance(proposed.get("facts"), list)
                or len(proposed["facts"]) < 2
                or any(
                    not isinstance(fact, dict) or fact.get("kind") != "task"
                    for fact in proposed["facts"]
                )
            ):
                self._observe_prewrite(delivery, "task_batch_plan_rejected")
                return self._abstain(delivery)
            self._observe_prewrite(
                delivery,
                "proposal",
                attempt=attempt,
                facts=len(proposed.get("facts")) if isinstance(proposed.get("facts"), list) else 0,
                entities=len(proposed.get("entities"))
                if isinstance(proposed.get("entities"), list)
                else 0,
                unresolved=bool(proposed.get("unresolved")),
            )
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
            candidate_facts = proposed.get("facts")
            can_overlap = (
                self.parallel_coverage_speaker_reviews
                and not proposed.get("unresolved")
                and isinstance(candidate_facts, list)
                and bool(candidate_facts)
                and all(
                    isinstance(fact, dict)
                    and isinstance(fact.get("source_evidence"), str)
                    and fact["source_evidence"]
                    and fact.get("needs_clarification") is not True
                    for fact in candidate_facts
                )
            )
            if can_overlap:
                review, concurrent_speakers = self._review_and_attest_concurrently(
                    source, clock, proposed, group_members
                )
            else:
                review = self._ask(
                    PLANNER_MODEL,
                    (
                        PROMPT_SOURCE_REVIEW_CORE_ANCHORED
                        if self.core_anchored_coverage_enabled
                        else PROMPT_SOURCE_REVIEW
                    ),
                    {
                        "source": source,
                        "clock": clock,
                        "proposed_facts": proposed.get("facts"),
                        "proposed_entities": proposed.get("entities"),
                        "core_verified_self_relationship": group_members or None,
                    },
                    (
                        REVIEW_CORE_ANCHORED_SCHEMA
                        if self.core_anchored_coverage_enabled
                        else REVIEW_SCHEMA
                    ),
                    (
                        "odyssey_p4_source_coverage_v2"
                        if self.core_anchored_coverage_enabled
                        else "odyssey_p2_source_coverage_v1"
                    ),
                )
            self._observe_prewrite(
                delivery,
                "coverage_verdict",
                attempt=attempt,
                approved=review.get("approved") is True,
                complete=review.get("complete") is True,
                facts=len(candidate_facts) if isinstance(candidate_facts, list) else 0,
                reviewed_facts=len(review.get("facts"))
                if isinstance(review.get("facts"), list)
                else 0,
                overlapping=can_overlap,
            )
            if review.get("approved") is True and review.get("complete") is True:
                reviewed_ok = True
                break
            if (
                attempt != 0
                or proposed.get("unresolved")
                or any(
                    f.get("needs_clarification") is True
                    for f in proposed.get("facts", ())
                    if isinstance(f, dict)
                )
            ):
                self._observe_prewrite(delivery, "coverage_rejected", attempt=attempt)
                return self._abstain(delivery)
        if not reviewed_ok:
            self._observe_prewrite(delivery, "coverage_retry_exhausted")
            return self._abstain(delivery)
        try:
            validate_whole_message_coverage(
                source,
                proposed,
                review,
                capabilities,
                verified_relationship_members=tuple(name for _id, name in relationship.members)
                if relationship is not None
                else (),
                core_anchored_evidence=self.core_anchored_coverage_enabled,
            )
            names = tuple(
                sorted({name for fact in review["facts"] for name in fact["reference_names"]})
            )
            self._measure_local(
                "identity_collision_preflight",
                reject_unproven_person_collisions,
                self.repository,
                self.schema,
                names,
            )
            speaker_payload = {
                "original_source": source,
                "facts": self._speaker_source_rows(proposed),
                "clock": clock,
            }
            speaker_a, speaker_b = (
                concurrent_speakers
                if concurrent_speakers is not None
                else self._independent_speaker_reviews(speaker_payload)
            )
            speaker_a, speaker_b = self._complete_bounded_speaker_counts(
                delivery, speaker_payload, speaker_a, speaker_b
            )
            attested = validate_dual_speaker_review(source, proposed["facts"], speaker_a, speaker_b)
            if any(f.assertion not in {"asserted", "planned"} for f in attested.facts):
                raise WholeMessageCoverageError("Non-affirmative input is not a completed event")
        except (
            WholeMessageCoverageError,
            UnprovenPersonIdentityError,
            WholeMessageSpeakerError,
        ) as error:
            category = (
                "coverage_contract"
                if isinstance(error, WholeMessageCoverageError)
                else "identity_collision"
                if isinstance(error, UnprovenPersonIdentityError)
                else "speaker_contract"
            )
            self._observe_prewrite(
                delivery, category, reason_code=self._prewrite_reason_code(error)
            )
            return self._abstain(delivery)
        self._observe_prewrite(delivery, "prewrite_accepted", facts=len(proposed["facts"]))
        # Compile ALL actions before ANY write. A missing owner, unsupported
        # Task lifecycle or invalid last fact cannot leave a partially
        # persisted multi-capability message behind.
        try:
            operations = self._measure_local(
                "compile_reviewed_operations",
                compile_reviewed_operations,
                review,
                tuple(attested.requires_self_link(i) for i in range(len(attested.facts))),
            )
        except WholeSourceCompilationError:
            self._observe_prewrite(delivery, "compile_rejected")
            return self._abstain(delivery)
        if self.progress is not None:
            self.progress("planner.ready", {})
            self.progress("action.write.started", {})
        before = self._measure_local(
            "prewrite_source_snapshot",
            lambda: {
                path: self.repository.read_text(path)
                for path in self.repository.list_markdown_paths()
            },
        )
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
                pending_recorder=self.pending_recorder,
                request_id_factory=lambda: locator,
                parallel_write_target_decisions=self.parallel_target_decisions,
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
            result = self._measure_local(
                "core_writer_action",
                execute_one,
                operation.plan,
                f"{delivery}-{operation.locator_suffix}",
                task=operation.task_create,
            )
            results.append(result)
            if result.status is not ApplicationStatus.COMPLETED:
                break
            # The outer product execution schedules ONE coalesced derived-index
            # refresh for all physically affected IDs after the complete Core
            # result. Do not embed or rebuild indexes between already-compiled
            # actions: the canonical Writer and Markdown readback, not an index,
            # are the authority for this same-source transaction. Subsequent
            # product readers use the existing wait_until_clean barrier.
        candidate = self._partial(delivery, results)
        if candidate.status is not ApplicationStatus.COMPLETED:
            return candidate
        try:
            after = self._measure_local(
                "postwrite_source_snapshot",
                lambda: {
                    path: self.repository.read_text(path)
                    for path in self.repository.list_markdown_paths()
                },
            )
            proof = self._measure_local(
                "canonical_markdown_readback",
                assert_reviewed_markdown,
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
                canonical_reference_evidence=(),
            )
        return candidate

    def _execute_dependent_core_task(
        self,
        source: str,
        delivery: str,
        actor: AuthenticatedActorContext,
        *,
        delivery_instant: datetime,
        router_started: float,
    ) -> ApplicationResult | None:
        """One narrow source-exact Core→Task chain, with E2 prewrite reviews.

        The normal Core Writer must physically prove the antecedent's Task
        link or newly created Person identity. Typed Tasks interpretation and
        two source reviews select the later operation; Core still selects and
        validates the canonical Task CREATE reference.
        """
        if (
            self.dependent_core_delegate is None
            or self.dependent_task_prepare is None
            or self.dependent_task_delegate is None
        ):
            return self._abstain(delivery)
        candidate = self._ask(
            PLANNER_MODEL,
            DEPENDENT_TASK_PARTITION_PROMPT,
            {"original_source": source},
            DEPENDENT_TASK_PARTITION_SCHEMA,
            "odyssey_dependent_task_partition_v1",
        )
        try:
            scope = verify_dependent_source_scopes(source, candidate)
        except DependentSourceScopesError:
            return self._abstain(delivery)
        # No write occurs until the target operation and TWO independent
        # source auditors are available, with identical exact-source claims.
        try:
            interpretation, temporal = self.dependent_task_prepare(
                scope.dependent.strip(), delivery_instant
            )
            if (
                not isinstance(interpretation, TaskInterpretation)
                or interpretation.requires_temporal() != (temporal is not None)
                or temporal is not None
                and (
                    not isinstance(temporal, TemporalInterpretation)
                    or temporal.source_text != scope.dependent.strip()
                )
            ):
                return self._abstain(delivery, "DEPENDENT_TASK_PREWRITE_UNAVAILABLE")
        except (ValueError, OpenAIError, TimeoutError, ConnectionError, OSError):
            return self._abstain(delivery, "DEPENDENT_TASK_PREWRITE_UNAVAILABLE")
        prepared_subtask: PreparedDependentSubtask | None = None
        if interpretation.operation is TaskOperation.CREATE:
            if any(
                getattr(mention.role, "value", None) == "PARENT_TASK"
                for mention in interpretation.relationship_mentions
            ):
                if self.dependent_subtask_prepare is None:
                    return self._abstain(delivery, "DEPENDENT_SUBTASK_PREWRITE_UNAVAILABLE")
                try:
                    prepared_subtask = self.dependent_subtask_prepare(
                        scope.dependent.strip(), interpretation, delivery_instant
                    )
                    if not isinstance(prepared_subtask, PreparedDependentSubtask):
                        return self._abstain(delivery, "DEPENDENT_SUBTASK_PREWRITE_UNAVAILABLE")
                    prepared_subtask.require_matches(
                        scope.dependent.strip(), interpretation.operation
                    )
                except (ValueError, OpenAIError, TimeoutError, ConnectionError, OSError):
                    return self._abstain(delivery, "DEPENDENT_SUBTASK_PREWRITE_UNAVAILABLE")
            elif (
                not interpretation.relationship_mentions
                and not self.dependent_person_create_enabled
            ):
                return None
            elif interpretation.relationship_mentions:
                return self._abstain(delivery, "DEPENDENT_CREATE_ROLE_UNSUPPORTED")
        # Audit the dependent segment's complete single-operation semantics
        # independently from both its Router label and the Tasks interpreter.
        # Two Work Session operations in the same fragment must never be
        # silently reduced to one before the first Core write.
        tasks_only = self._ask(
            PLANNER_MODEL,
            TASK_ONLY_SCOPE_PROMPT,
            {"original_source": scope.dependent.strip()},
            TASK_ONLY_SCOPE_SCHEMA,
            "odyssey_task_only_scope_v1",
        )
        if (
            tasks_only.get("only_task_semantics") is not True
            or tasks_only.get("exactly_one_operation") is not True
            or tasks_only.get("source_quote") != scope.dependent.strip()
        ):
            return self._abstain(delivery)
        payload = {
            "original_source": scope.original,
            "antecedent_source": scope.antecedent,
            "dependent_source": scope.dependent,
            "dependent_mention": scope.mention,
            "task_operation": interpretation.operation.value,
        }
        first = self._ask(
            PLANNER_MODEL,
            DEPENDENT_TASK_TARGET_REVIEW_A,
            payload,
            DEPENDENT_TASK_TARGET_REVIEW_SCHEMA,
            "odyssey_dependent_task_review_a_v1",
        )
        second = self._ask(
            ROUTER_MODEL,
            DEPENDENT_TASK_TARGET_REVIEW_B,
            payload,
            DEPENDENT_TASK_TARGET_REVIEW_SCHEMA,
            "odyssey_dependent_task_review_b_v1",
        )
        try:
            verify_dependent_task_semantics(
                full_source=source,
                antecedent_source=scope.antecedent,
                dependent_source=scope.dependent,
                dependent_mention=scope.mention,
                interpretation=interpretation,
                attestations=(first, second),
            )
        except TaskDependentTargetError:
            return self._abstain(delivery)
        # Do not allow an unproven dependent CREATE to fall back into the
        # person-only P4 light compiler. Task lifecycle paths are domain-owned.
        core_locator = f"{delivery}-dependent-core"
        task_locator = f"{delivery}-dependent-task"
        if max(len(core_locator), len(task_locator)) > 110:
            return self._abstain(delivery)
        if self.operation_manifest_begin is not None:
            self.operation_manifest_begin(
                delivery,
                source,
                actor,
                (("core", scope.antecedent, ()), ("tasks", scope.dependent, (0,))),
            )
        # Stages have the same observable meaning as the established P4
        # route, never synthetic model success. This is the actual boundary
        # where all model prechecks passed and the first WRITE begins.
        if self.progress is not None:
            self.progress("planner.ready", {})
            self.progress("action.write.started", {})
        # Standard Core planner/Writer performs the first write and MUST prove
        # a physical Task backlink. Provider and identity failures stay safe.
        core = self.dependent_core_delegate(
            scope.antecedent.strip(), core_locator, actor, delivery_instant
        )
        if self.operation_manifest_observe is not None:
            self.operation_manifest_observe(delivery, source, actor, 0, "core", core)
        if core.status is not ApplicationStatus.COMPLETED:
            return replace(core, request_id=delivery)
        # The typed handoff reads current canonical Markdown directly; it
        # never needs an index refresh between the two writes. Product E3
        # schedules ONE incremental refresh of the combined affected IDs at
        # the outer boundary, avoiding needless Raspberry index/CPU churn.
        try:
            prove_target = (
                prove_dependent_person_reference
                if interpretation.operation is TaskOperation.CREATE and prepared_subtask is None
                else prove_dependent_task_target
            )
            target = prove_target(
                full_source=source,
                antecedent_source=scope.antecedent,
                dependent_source=scope.dependent,
                dependent_mention=scope.mention,
                core_predecessor=core,
                interpretation=interpretation,
                attestations=(first, second),
                repository=self.repository,
                schema=self.schema,
            )
            if isinstance(target, SourceBoundDependency):
                target = TaskPersonReference(target, actor.stable_user_id)
            if prepared_subtask is not None:
                target = target.with_prepared_subtask(prepared_subtask)
        except TaskDependentTargetError:
            # Core may have written a real fact but its Task link was missing,
            # conflicting or stale: report PARTIAL and NEVER run Tasks.
            return self._partial(delivery, [core, self._abstain(task_locator)])
        if self.progress is not None:
            self.progress("action.delegate.started", {})
        task = self.dependent_task_delegate(
            scope.dependent.strip(),
            task_locator,
            actor,
            interpretation,
            temporal,
            target,
            delivery_instant,
        )
        if self.operation_manifest_observe is not None:
            self.operation_manifest_observe(delivery, source, actor, 1, "tasks", task)
        # Task's own domain service may still reject state/time/conflicts;
        # preserve the earlier Core write and describe the result truthfully.
        result = self._partial(delivery, [core, task])
        stages = (
            OperationalStage(
                "application.router",
                OperationalOutcome.COMPLETED,
                max(0.0, (perf_counter() - router_started) * 1000),
            ),
            *(
                replace(stage, route_index=index)
                for index, part in enumerate((core, task))
                for stage in part.operational.stages
            ),
        )
        return replace(
            result,
            operational=OperationalEvidence(
                max(0.0, (perf_counter() - router_started) * 1000),
                tuple(stages),
            ),
            execution_flow={
                "version": 1,
                "input": source,
                "parallel_preparation": False,
                "routes": [
                    {
                        "capability": cap,
                        "text": text,
                        # The second capability uses a canonical Task reference
                        # persisted by the preceding Core fact, NOT an independent
                        # interpretation group. E2 ledger and UI can draw this
                        # actual dependency without guessing from source prose.
                        **({"depends_on": 0, "reason": None} if cap == "tasks" else {}),
                        "status": receipt.status.value,
                        "stage_count": len(receipt.operational.stages),
                        "temporal": [],
                        "steps": [
                            {"name": stage.name[:80], "input": text[:512], "output": ""}
                            for stage in receipt.operational.stages
                        ],
                    }
                    for cap, text, receipt in (
                        ("core", scope.antecedent, core),
                        ("tasks", scope.dependent, task),
                    )
                ],
            },
        )

    def _execute_dependent_graph(
        self,
        source: str,
        delivery: str,
        actor: AuthenticatedActorContext,
        *,
        delivery_instant: datetime,
        router_started: float,
        route_scopes: list[dict[str, object]],
    ) -> ApplicationResult:
        """Opt-in N-scope Core→Tasks DAG, single canonical target per Task.

        All N-group topology, *each* Tasks domain operation, its source-only
        audit, and TWO independent semantic target reviews must pass BEFORE
        the FIRST Core WRITE. At execution each edge is freshly proved by
        canonical Core Markdown and verified again by the Tasks service CAS.
        Multi-target Task operations and Core groups depending on earlier
        groups are not representable by current domain services: fail closed.
        """
        if (
            self.dependent_core_delegate is None
            or self.dependent_task_prepare is None
            or self.dependent_task_delegate is None
        ):
            return self._abstain(delivery, "DEPENDENT_N_GRAPH_ADAPTER_UNAVAILABLE")
        proposed = self._ask(
            PLANNER_MODEL,
            DEPENDENT_GRAPH_PARTITION_PROMPT,
            {"original_source": source},
            DEPENDENT_GRAPH_PARTITION_SCHEMA,
            "odyssey_dependent_graph_partition_v1",
        )
        reviewed = self._ask(
            ROUTER_MODEL,
            DEPENDENT_GRAPH_REVIEW_PROMPT,
            {"original_source": source, "proposed_groups": proposed},
            DEPENDENT_GRAPH_REVIEW_SCHEMA,
            "odyssey_dependent_graph_review_v1",
        )
        try:
            graph = verify_dependent_group_graph(source, proposed, reviewed)
        except DependentGroupGraphError:
            # A reviewer veto may convey ONE bounded failure category, never
            # reasoning text or identities. No rejected review can be promoted
            # to authorization through its diagnostic fields.
            try:
                reason, _index = classify_dependent_group_review_rejection(
                    source, proposed, reviewed
                )
            except DependentGroupGraphError:
                return self._abstain(delivery, "DEPENDENT_N_GRAPH_SOURCE_UNVERIFIED")
            return self._abstain(delivery, f"DEPENDENT_N_GRAPH_REVIEW_{reason}")

        def _split_task_edges(part):
            core = tuple(
                dep
                for dep in part.dependencies
                if graph.groups[dep.predecessor_index].capability == "core"
            )
            sessions = tuple(
                dep
                for dep in part.dependencies
                if graph.groups[dep.predecessor_index].capability == "tasks"
            )
            return core, sessions

        if (
            len(graph.groups) != len(route_scopes)
            or not any(group.dependencies for group in graph.groups)
            or not any(group.capability == "tasks" for group in graph.groups)
            or any(
                not isinstance(scoped, dict)
                or scoped.get("capability") != part.capability
                or scoped.get("depends_on_another_scope") is not bool(part.dependencies)
                for scoped, part in zip(route_scopes, graph.groups, strict=True)
            )
            or any(
                (part.capability == "core" and part.dependencies)
                or (
                    part.capability == "tasks"
                    and (
                        len(_split_task_edges(part)[0]) > 1
                        or len(_split_task_edges(part)[1]) > 1
                        or (not _split_task_edges(part)[0] and bool(part.dependencies))
                        or (
                            bool(_split_task_edges(part)[0])
                            and len(part.dependencies) not in (1, 2)
                        )
                    )
                )
                for part in graph.groups
            )
        ):
            return self._abstain(delivery, "DEPENDENT_N_GRAPH_UNREPRESENTABLE")
        if any(part.capability == "tasks" and not part.dependencies for part in graph.groups) and (
            self.independent_task_prepare is None or self.independent_task_delegate is None
        ):
            return self._abstain(delivery, "DEPENDENT_N_INDEPENDENT_TASK_ADAPTER_UNAVAILABLE")
        # A Task->Task edge can only mean one subsequent consumer of a
        # same-delivery Work Session START, on the very same Core Task.
        if any(_split_task_edges(part)[1] for part in graph.groups):
            if self.dependent_session_delegate is None:
                return self._abstain(delivery, "DEPENDENT_N_SESSION_ADAPTER_UNAVAILABLE")

        locators = [f"{delivery}-dependent-n-{part.ordinal}" for part in graph.groups]
        if any(len(locator) > 110 for locator in locators):
            return self._abstain(delivery)
        # Preflight every downstream app operation, including its two semantic
        # target attestations, before any earlier Core result is persisted.
        reviewed_session_links: dict[int, int] = {}
        prepared: dict[
            int,
            tuple[
                TaskInterpretation,
                TemporalInterpretation | None,
                PreparedDependentSubtask | None,
            ],
        ] = {}
        for part in graph.groups:
            if part.capability != "tasks":
                continue
            segment = part.source.strip()
            core_dependencies, session_dependencies = _split_task_edges(part)
            dependency = core_dependencies[0] if core_dependencies else None
            try:
                # Zero inbound edges are genuine independent app operations.
                # They still receive full Tasks domain prewrite and E3, but
                # must NEVER inherit a canonical Core target.
                prepare = (
                    self.dependent_task_prepare
                    if dependency is not None
                    else self.independent_task_prepare
                )
                assert prepare is not None
                interpretation, temporal = prepare(segment, delivery_instant)
                if (
                    not isinstance(interpretation, TaskInterpretation)
                    or interpretation.source_text != segment
                    or interpretation.requires_temporal() != (temporal is not None)
                    or temporal is not None
                    and (
                        not isinstance(temporal, TemporalInterpretation)
                        or temporal.source_text != segment
                    )
                ):
                    return self._abstain(delivery, "DEPENDENT_N_TASK_PREWRITE_UNAVAILABLE")
                prepared_subtask: PreparedDependentSubtask | None = None
                if interpretation.operation is TaskOperation.CREATE and dependency is not None:
                    if any(
                        getattr(mention.role, "value", None) == "PARENT_TASK"
                        for mention in interpretation.relationship_mentions
                    ):
                        if self.dependent_subtask_prepare is None:
                            return self._abstain(
                                delivery, "DEPENDENT_N_SUBTASK_PREWRITE_UNAVAILABLE"
                            )
                        prepared_subtask = self.dependent_subtask_prepare(
                            segment, interpretation, delivery_instant
                        )
                        if not isinstance(prepared_subtask, PreparedDependentSubtask):
                            return self._abstain(
                                delivery, "DEPENDENT_N_SUBTASK_PREWRITE_UNAVAILABLE"
                            )
                        prepared_subtask.require_matches(segment, interpretation.operation)
                    elif (
                        not interpretation.relationship_mentions
                        and not self.dependent_person_create_enabled
                    ):
                        return self._abstain(delivery, "DEPENDENT_N_PERSON_CREATE_UNAVAILABLE")
                    elif interpretation.relationship_mentions:
                        return self._abstain(delivery, "DEPENDENT_N_CREATE_ROLE_UNSUPPORTED")
            except (ValueError, OpenAIError, TimeoutError, ConnectionError, OSError):
                return self._abstain(delivery, "DEPENDENT_N_TASK_PREWRITE_UNAVAILABLE")
            task_only = self._ask(
                PLANNER_MODEL,
                TASK_ONLY_SCOPE_PROMPT,
                {"original_source": segment},
                TASK_ONLY_SCOPE_SCHEMA,
                "odyssey_task_only_scope_v1",
            )
            if (
                task_only.get("only_task_semantics") is not True
                or task_only.get("exactly_one_operation") is not True
                or task_only.get("source_quote") != segment
            ):
                return self._abstain(delivery, "DEPENDENT_N_TASK_SOURCE_UNVERIFIED")
            if dependency is None:
                # No dependent target reviews apply: there is no edge.
                # Task-only full-scope semantics were independently reviewed
                # above, and ordinary Tasks service will preflight its target.
                prepared[part.ordinal] = (interpretation, temporal, None)
                continue
            payload = {
                "original_source": source,
                "antecedent_source": graph.groups[dependency.predecessor_index].source,
                "dependent_source": part.source,
                "dependent_mention": dependency.mention,
                "task_operation": interpretation.operation.value,
            }
            first = self._ask(
                PLANNER_MODEL,
                DEPENDENT_TASK_TARGET_REVIEW_A,
                payload,
                DEPENDENT_TASK_TARGET_REVIEW_SCHEMA,
                "odyssey_dependent_task_review_a_v1",
            )
            second = self._ask(
                ROUTER_MODEL,
                DEPENDENT_TASK_TARGET_REVIEW_B,
                payload,
                DEPENDENT_TASK_TARGET_REVIEW_SCHEMA,
                "odyssey_dependent_task_review_b_v1",
            )
            try:
                verify_dependent_task_semantics(
                    full_source=source,
                    antecedent_source=graph.groups[dependency.predecessor_index].source,
                    dependent_source=part.source,
                    dependent_mention=dependency.mention,
                    interpretation=interpretation,
                    attestations=(first, second),
                )
            except TaskDependentTargetError:
                return self._abstain(delivery, "DEPENDENT_N_TASK_SEMANTICS_UNVERIFIED")
            prepared[part.ordinal] = (interpretation, temporal, prepared_subtask)
            if session_dependencies:
                session_edge = session_dependencies[0]
                producer_index = session_edge.predecessor_index
                prior = prepared.get(producer_index)
                prior_core, prior_session = _split_task_edges(graph.groups[producer_index])
                if (
                    prior is None
                    or prior[0].operation is not TaskOperation.START_WORK_SESSION
                    or interpretation.operation is not TaskOperation.STOP_WORK_SESSION
                    or len(prior_core) != 1
                    or prior_session
                    or prior_core[0].predecessor_index != dependency.predecessor_index
                    or prior_core[0].antecedent_mention != dependency.antecedent_mention
                ):
                    return self._abstain(delivery, "DEPENDENT_N_SESSION_SOURCE_UNSUPPORTED")
                session_payload = {
                    "full_source": source,
                    "producer_source": graph.groups[producer_index].source,
                    "consumer_source": part.source,
                    "source_mention": session_edge.antecedent_mention,
                    "dependent_mention": session_edge.mention,
                    "producer_operation": prior[0].operation.value,
                    "consumer_operation": interpretation.operation.value,
                }
                session_a = self._ask(
                    PLANNER_MODEL,
                    DEPENDENT_SESSION_LINK_REVIEW_A,
                    session_payload,
                    DEPENDENT_SESSION_LINK_REVIEW_SCHEMA,
                    "odyssey_dependent_session_review_a_v1",
                )
                session_b = self._ask(
                    ROUTER_MODEL,
                    DEPENDENT_SESSION_LINK_REVIEW_B,
                    session_payload,
                    DEPENDENT_SESSION_LINK_REVIEW_SCHEMA,
                    "odyssey_dependent_session_review_b_v1",
                )
                try:
                    verify_session_dependency(
                        full_source=source,
                        producer_source=graph.groups[producer_index].source,
                        consumer_source=part.source,
                        source_mention=session_edge.antecedent_mention,
                        dependent_mention=session_edge.mention,
                        producer_index=producer_index,
                        consumer_index=part.ordinal,
                        producer=prior[0],
                        consumer=interpretation,
                        reviews=(session_a, session_b),
                    )
                except SessionDependencyError:
                    return self._abstain(delivery, "DEPENDENT_N_SESSION_SEMANTICS_UNVERIFIED")
                reviewed_session_links[part.ordinal] = producer_index
        try:
            ordered_task_indices = tuple(sorted(prepared))
            validate_task_batch_prewrite(
                tuple(prepared[index][0] for index in ordered_task_indices),
                session_linked_stops=frozenset(
                    ordered_task_indices.index(index) for index in reviewed_session_links
                ),
            )
        except TaskBatchPreflightError:
            return self._abstain(delivery, "DEPENDENT_N_TASK_BATCH_INCOMPATIBLE")
        if self.operation_manifest_begin is not None:
            self.operation_manifest_begin(
                delivery,
                source,
                actor,
                tuple(
                    (
                        part.capability,
                        part.source,
                        tuple(dep.predecessor_index for dep in part.dependencies),
                    )
                    for part in graph.groups
                ),
            )
        if self.progress is not None:
            self.progress("planner.ready", {})
            self.progress("action.write.started", {})
        outcomes: list[ApplicationResult] = []
        predecessors: dict[int, ApplicationResult] = {}
        session_proofs: dict[int, CanonicalSessionEvidence] = {}
        session_producers = frozenset(reviewed_session_links.values())
        pending_index_ids: list[str] = []
        for part, locator in zip(graph.groups, locators, strict=True):
            if part.capability == "core" and pending_index_ids:
                # Subsequent Core planners need refreshed, source-verified
                # context; never full-rebuild after earlier writes.
                try:
                    refresh = (
                        self.refresh_between_independent_scopes or self.refresh_affected_indexes
                    )
                    refresh(tuple(dict.fromkeys(pending_index_ids)))
                except Exception:
                    failure = self._abstain(locator, "DEPENDENT_N_CONTEXT_REFRESH_UNAVAILABLE")
                    if self.operation_manifest_observe is not None:
                        self.operation_manifest_observe(
                            delivery, source, actor, part.ordinal, part.capability, failure
                        )
                    outcomes.append(failure)
                    break
                pending_index_ids.clear()
            if part.capability == "core":
                # Ordinary Core Planner/Writer, not a second custom writer.
                outcome = self.dependent_core_delegate(
                    part.source.strip(), locator, actor, delivery_instant
                )
            else:
                core_dependencies, session_dependencies = _split_task_edges(part)
                if not core_dependencies:
                    task, temporal, _ = prepared[part.ordinal]
                    assert self.independent_task_delegate is not None
                    if self.progress is not None:
                        self.progress("action.delegate.started", {})
                    outcome = self.independent_task_delegate(
                        part.source.strip(),
                        locator,
                        actor,
                        task,
                        temporal,
                        delivery_instant,
                    )
                else:
                    dependency = core_dependencies[0]
                    try:
                        # The Core verifier only handles Core-authored note links,
                        # never interpret a Tasks-produced session as a Core link.
                        core_only_group = replace(part, dependencies=core_dependencies)
                        core_only_graph = replace(
                            graph,
                            groups=tuple(
                                core_only_group if item.ordinal == part.ordinal else item
                                for item in graph.groups
                            ),
                        )
                        handoff = prove_canonical_group_handoff(
                            graph=core_only_graph,
                            consumer_index=part.ordinal,
                            predecessors=predecessors,
                            repository=self.repository,
                            schema=self.schema,
                        )
                        if len(handoff.edges) != 1:
                            raise CanonicalGroupEvidenceError("Task has no unique target")
                        edge = handoff.edges[0]
                        task, temporal, subtask = prepared[part.ordinal]
                        source_proof = SourceBoundDependency(
                            graph.groups[dependency.predecessor_index].source,
                            part.source,
                            dependency.mention,
                            edge.evidence,
                        )
                        if task.operation is TaskOperation.CREATE and subtask is None:
                            if edge.evidence.note_type != "person":
                                raise CanonicalGroupEvidenceError("Dependent Person is unverified")
                            target = TaskPersonReference(source_proof, actor.stable_user_id)
                        else:
                            if edge.evidence.note_type != "task":
                                raise CanonicalGroupEvidenceError("Dependent Task is unverified")
                            target = TaskDependentTarget(source_proof, task.operation)
                            if subtask is not None:
                                target = target.with_prepared_subtask(subtask)
                        # Recheck at the consumption boundary even if the Core
                        # backlink was valid when the prior group returned.
                        handoff.require_all_current(self.repository, self.schema)
                    except (CanonicalGroupEvidenceError, TaskDependentTargetError):
                        outcome = self._abstain(locator, "DEPENDENT_N_CANONICAL_EDGE_UNVERIFIED")
                    else:
                        if self.progress is not None:
                            self.progress("action.delegate.started", {})
                        if part.ordinal in reviewed_session_links:
                            prior_proof = session_proofs.get(reviewed_session_links[part.ordinal])
                            if prior_proof is None or prior_proof.task_id != target.require_current(
                                self.repository, self.schema
                            ):
                                outcome = self._abstain(
                                    locator, "DEPENDENT_N_SESSION_RECEIPT_UNAVAILABLE"
                                )
                            else:
                                assert self.dependent_session_delegate is not None
                                outcome, _ = self.dependent_session_delegate(
                                    part.source.strip(),
                                    locator,
                                    actor,
                                    task,
                                    temporal,
                                    target,
                                    delivery_instant,
                                    prior_proof,
                                )
                        elif part.ordinal in session_producers:
                            assert self.dependent_session_delegate is not None
                            outcome, new_proof = self.dependent_session_delegate(
                                part.source.strip(),
                                locator,
                                actor,
                                task,
                                temporal,
                                target,
                                delivery_instant,
                                None,
                            )
                            if outcome.status is ApplicationStatus.COMPLETED:
                                if not isinstance(new_proof, CanonicalSessionEvidence):
                                    raise WholeSourceLightError(
                                        "A completed START is missing physical session evidence"
                                    )
                                session_proofs[part.ordinal] = new_proof
                        else:
                            outcome = self.dependent_task_delegate(
                                part.source.strip(),
                                locator,
                                actor,
                                task,
                                temporal,
                                target,
                                delivery_instant,
                            )
            if self.operation_manifest_observe is not None:
                self.operation_manifest_observe(
                    delivery, source, actor, part.ordinal, part.capability, outcome
                )
            outcomes.append(outcome)
            if outcome.status is not ApplicationStatus.COMPLETED:
                break
            pending_index_ids.extend(outcome.affected_stable_note_ids)
            if part.capability == "core":
                predecessors[part.ordinal] = outcome
        aggregate = self._partial(delivery, outcomes)
        rows = []
        stages = [
            OperationalStage(
                "application.router",
                OperationalOutcome.COMPLETED,
                max(0.0, (perf_counter() - router_started) * 1000),
            )
        ]
        complete_flow = len(outcomes) <= 8
        for part, outcome in zip(graph.groups, outcomes, strict=False):
            if len(outcome.operational.stages) > 16:
                complete_flow = False
            stages.extend(
                replace(stage, route_index=part.ordinal) for stage in outcome.operational.stages
            )
            rows.append(
                {
                    "capability": part.capability,
                    "text": part.source,
                    **(
                        {
                            "depends_on": part.dependencies[-1].predecessor_index,
                            "reason": None,
                            **(
                                {
                                    "dependency_indices": [
                                        dep.predecessor_index for dep in part.dependencies
                                    ]
                                }
                                if len(part.dependencies) > 1
                                else {}
                            ),
                        }
                        if part.dependencies
                        else {}
                    ),
                    "status": outcome.status.value,
                    "stage_count": len(outcome.operational.stages),
                    "temporal": [],
                    "steps": [
                        {"name": stage.name[:80], "input": part.source[:512], "output": ""}
                        for stage in outcome.operational.stages
                    ],
                }
            )
        return replace(
            aggregate,
            operational=OperationalEvidence(
                max(0.0, (perf_counter() - router_started) * 1000),
                tuple(stages),
            ),
            execution_flow={
                "version": 1,
                "input": source,
                "parallel_preparation": False,
                "routes": rows,
            }
            if complete_flow and rows
            else None,
        )

    def _execute_independent_scopes(
        self,
        source: str,
        delivery: str,
        actor: AuthenticatedActorContext,
        conversation_id: str,
        *,
        delivery_instant: datetime,
        router_started: float,
        route_scopes: list[dict[str, object]],
    ) -> ApplicationResult:
        # Proposed scopes are non-authoritative byte ranges. No trimming,
        # deletion, or LLM-authored canonical identities in this boundary.
        proposal = self._ask(
            PLANNER_MODEL,
            INDEPENDENT_SCOPE_PARTITION_PROMPT,
            {"original_source": source},
            INDEPENDENT_SCOPE_PARTITION_SCHEMA,
            "odyssey_independent_source_scopes_v1",
        )
        review = self._ask(
            ROUTER_MODEL,
            INDEPENDENT_SCOPE_REVIEW_PROMPT,
            {"original_source": source, "proposed_scopes": proposal},
            INDEPENDENT_SCOPE_REVIEW_SCHEMA,
            "odyssey_independent_source_scopes_audit_v1",
        )
        try:
            verified = verify_independent_source_scopes(
                source,
                proposal,
                review,
                permitted_capabilities=frozenset({"core", "tasks"}),
            )
        except IndependentSourceScopesError:
            return self._abstain(delivery)
        if len(route_scopes) != len(verified) or any(
            route_scopes[part.index].get("capability") != part.capability
            or route_scopes[part.index].get("depends_on_another_scope") is not False
            for part in verified
        ):
            return self._abstain(delivery, "INDEPENDENT_ROUTE_PARTITION_MISMATCH")
        # Reject overlong derived locators BEFORE writing anything. This keeps
        # the outer E3 claim responsible for the full logical request.
        locators = [f"{delivery}-independent-{part.index}" for part in verified]
        if any(len(locator) > 110 for locator in locators):
            return self._abstain(delivery)
        # E2/E3 prewrite contract: audit EVERY Tasks-owned standalone span
        # before any earlier Core fact is persisted. Otherwise a false Tasks
        # classification for a narrated future plan can leave an avoidable
        # first-Core-write + later failure/uncertain E3 claim.
        task_scopes: dict[int, dict[str, object]] = {}
        prepared_tasks: dict[int, tuple[TaskInterpretation, TemporalInterpretation | None]] = {}
        if (self.independent_task_prepare is None) != (self.independent_task_delegate is None):
            return self._abstain(delivery, "INDEPENDENT_TASK_ADAPTER_INCOMPLETE")
        for part in verified:
            if part.capability != "tasks":
                continue
            scope = self._ask(
                PLANNER_MODEL,
                TASK_ONLY_SCOPE_PROMPT,
                {"original_source": part.source.strip()},
                TASK_ONLY_SCOPE_SCHEMA,
                "odyssey_task_only_scope_v1",
            )
            if (
                scope.get("only_task_semantics") is not True
                or scope.get("exactly_one_operation") is not True
                or scope.get("source_quote") != part.source.strip()
            ):
                return self._abstain(delivery)
            task_scopes[part.index] = scope
            if self.independent_task_prepare is not None:
                try:
                    task, temporal = self.independent_task_prepare(
                        part.source.strip(), delivery_instant
                    )
                    if (
                        not isinstance(task, TaskInterpretation)
                        or task.source_text != part.source.strip()
                        or task.requires_temporal() != (temporal is not None)
                        or temporal is not None
                        and (
                            not isinstance(temporal, TemporalInterpretation)
                            or temporal.source_text != part.source.strip()
                        )
                    ):
                        return self._abstain(delivery, "INDEPENDENT_TASK_PREWRITE_UNVERIFIED")
                    prepared_tasks[part.index] = (task, temporal)
                except (ValueError, OpenAIError, TimeoutError, ConnectionError, OSError):
                    return self._abstain(delivery, "INDEPENDENT_TASK_PREWRITE_UNAVAILABLE")
        if self.operation_manifest_begin is not None:
            self.operation_manifest_begin(
                delivery,
                source,
                actor,
                tuple((part.capability, part.source, ()) for part in verified),
            )
        router_duration_ms = max(0.0, (perf_counter() - router_started) * 1000)
        outcomes: list[ApplicationResult] = []
        pending_index_ids: list[str] = []
        for part, locator in zip(verified, locators, strict=True):
            # An earlier canonical Writer may have made derived hints stale.
            # Refresh only the changed Note IDs before another Core planner
            # reads derived context. Never rebuild the complete index, and
            # never let an index failure rewrite or erase prior successes.
            if part.capability == "core" and pending_index_ids:
                try:
                    refresh = (
                        self.refresh_between_independent_scopes or self.refresh_affected_indexes
                    )
                    refresh(tuple(dict.fromkeys(pending_index_ids)))
                except Exception:
                    failed = self._abstain(locator, "INDEPENDENT_CONTEXT_REFRESH_UNAVAILABLE")
                    if self.operation_manifest_observe is not None:
                        self.operation_manifest_observe(
                            delivery, source, actor, part.index, part.capability, failed
                        )
                    outcomes.append(failed)
                    break
                pending_index_ids.clear()
            # This re-enters the EXACT usual Core/Tasks app path and guards,
            # with only the independently source-verified span as its scope.
            # No alternate Work Session or Task writer is introduced.
            try:
                if part.capability == "tasks" and self.independent_task_delegate is not None:
                    task, temporal = prepared_tasks[part.index]
                    outcome = self.independent_task_delegate(
                        part.source.strip(),
                        locator,
                        actor,
                        task,
                        temporal,
                        delivery_instant,
                    )
                else:
                    outcome = self._execute_source(
                        part.source.strip(),
                        locator,
                        actor,
                        conversation_id,
                        independent_scope=part.capability,
                        delivery_instant=delivery_instant,
                        prechecked_task_scope=task_scopes.get(part.index),
                    )
            except WholeSourceLightError:
                # A per-scope provider failure is prewrite for THAT scope,
                # but earlier independent scopes may already be durable.
                outcome = self._abstain(locator, "FULL_SOURCE_PROVIDER_OR_CONTEXT_UNAVAILABLE")
            if self.operation_manifest_observe is not None:
                self.operation_manifest_observe(
                    delivery, source, actor, part.index, part.capability, outcome
                )
            if outcome.status is not ApplicationStatus.COMPLETED and not outcomes:
                return replace(outcome, request_id=delivery)
            outcomes.append(outcome)
            pending_index_ids.extend(outcome.affected_stable_note_ids)
            if outcome.status is not ApplicationStatus.COMPLETED:
                break
        # Preserve actual Core/Task stages for donut + execution ledger instead
        # of inheriting only the final App's telemetry. These are observed
        # stages, not synthetic claims of semantic/model success.
        outer_stage = OperationalStage(
            "application.router",
            OperationalOutcome.COMPLETED,
            router_duration_ms,
        )
        flattened_stages = [outer_stage]
        route_rows = []
        complete_flow = len(outcomes) <= 8
        for part, outcome in zip(verified, outcomes, strict=False):
            stages = outcome.operational.stages
            if len(stages) > 16:
                complete_flow = False
            flattened_stages.extend(replace(stage, route_index=part.index) for stage in stages)
            route_rows.append(
                {
                    "capability": part.capability,
                    "text": part.source,
                    "stage_count": len(stages),
                    "status": outcome.status.value,
                    "temporal": [],
                    "steps": [
                        {"name": stage.name[:80], "input": part.source[:512], "output": ""}
                        for stage in stages
                    ],
                }
            )
        # Reuse the established, Core-result-only multi-App aggregator: it
        # renumbers action IDs and retains pending work, history, statuses,
        # and affected notes instead of letting the last App overwrite them.
        aggregate = aggregate_verified_application_results(delivery, outcomes)
        return replace(
            aggregate,
            operational=OperationalEvidence(
                max(0.0, (perf_counter() - router_started) * 1000),
                tuple(flattened_stages),
            ),
            execution_flow={
                "version": 1,
                "input": source,
                "parallel_preparation": False,
                "routes": route_rows,
            }
            if complete_flow and route_rows
            else None,
        )

    @staticmethod
    def _abstain(
        delivery: str, code: str = "FULL_SOURCE_REVIEW_OR_IDENTITY_UNVERIFIED"
    ) -> ApplicationResult:
        return ApplicationResult(
            delivery,
            ApplicationStatus.NEEDS_ATTENTION,
            (),
            (),
            clarification_code=code,
        )

    @staticmethod
    def _partial(delivery: str, results: list[ApplicationResult]) -> ApplicationResult:
        if not results:
            return WholeSourceLightExecutor._abstain(delivery)
        aggregate = aggregate_verified_application_results(delivery, results)
        # Never inherit whichever identity happened to be returned by the
        # *last* operation. Only a single Core-authored carrier across EVERY
        # completed suboperation may be considered for a later handoff. Any
        # duplicate link (even to the same Note) is ambiguous about which
        # source occurrence established the dependent pronoun.
        proofs = tuple(proof for result in results for proof in result.canonical_reference_evidence)
        return replace(
            aggregate,
            canonical_reference_evidence=proofs
            if aggregate.status is ApplicationStatus.COMPLETED and len(proofs) == 1
            else (),
            # Each verified Core sub-request may have been executed separately;
            # preserve an exact source digest only when every result agrees.
            core_source_digest=(
                results[0].core_source_digest
                if results[0].core_source_digest is not None
                and all(
                    result.core_source_digest == results[0].core_source_digest for result in results
                )
                else None
            ),
        )
