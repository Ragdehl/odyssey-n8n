"""Provider-free Slice 3 runtime routing and routed-continuation coverage."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from threading import Barrier, Lock, current_thread
from types import SimpleNamespace

import pytest

from odyssey_apps import (
    ApplicationCatalog,
    ApplicationDescriptor,
    ApplicationRegistry,
    Route,
    RouteOutcome,
    RoutePlan,
)
from odyssey_core.application import (
    ActionResult,
    ActionStatus,
    ApplicationResult,
    ApplicationStatus,
    PendingWorkStatus,
    UnitResult,
    UnitStatus,
)
from odyssey_core.clarification import LocalClarificationStore
from odyssey_core.git_history import GitHistoryResult, HistoryStatus
from odyssey_core.identity_boundary import AuthenticatedActorContext
from odyssey_core.local_conversations import ConversationRootResolver, LocalConversationStore
from odyssey_core.notes import Note, serialize_note
from odyssey_core.pending_work import PendingWorkRepository
from odyssey_core.request_planning import KnowledgeUnit, RequestPlan, SelectionCriteria, WriteAction
from odyssey_core.storage import VaultRepository
from odyssey_runtime.composition import RuntimeComposition
from odyssey_runtime.routing import (
    execute_routed_request,
    is_route_execution_id,
    route_execution_id,
)
from odyssey_runtime.serialization import application_result_to_response

ROOT = Path(__file__).resolve().parents[2]
ACTOR = AuthenticatedActorContext("11111111-1111-4111-8111-111111111111")


class FixedRouter:
    """Return one deterministic plan while retaining every bounded routing input."""

    def __init__(self, plan: RoutePlan) -> None:
        """Keep the exact closed plan used by a provider-free test."""
        self.plan = plan
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def route(self, request: str, conversation_context=()) -> RoutePlan:
        """Record only the exact original request and bounded prior evidence."""
        self.calls.append((request, tuple(conversation_context)))
        return self.plan


def _catalog() -> ApplicationCatalog:
    """Return one enabled synthetic application destination."""
    return ApplicationRegistry.from_descriptors(
        (ApplicationDescriptor("calendar", "calendar-owned intent"),)
    ).catalog(enabled_ids=("calendar",))


def _result(
    request_id: str,
    *,
    status: ApplicationStatus = ApplicationStatus.COMPLETED,
    actions: int = 0,
    affected: tuple[str, ...] = (),
    history: GitHistoryResult | None = None,
    pending: PendingWorkStatus | None = None,
) -> ApplicationResult:
    """Build compact route evidence with a configurable action count."""
    return ApplicationResult(
        request_id,
        status,
        tuple(ActionResult(index, "write", ActionStatus.COMPLETED) for index in range(actions)),
        affected,
        pending_work=PendingWorkStatus() if pending is None else pending,
        history=GitHistoryResult.disabled() if history is None else history,
    )


def test_route_locator_is_safe_for_128_character_and_unsafe_outer_ids() -> None:
    """Keep subordinate locators ASCII-safe and independent of delivery-ID length or spelling."""
    outer = "!" * 128
    locator = route_execution_id(outer, 0)

    assert locator == f"route-1-{hashlib.sha256(outer.encode()).hexdigest()}"
    assert len(locator) <= 128
    assert is_route_execution_id(outer, locator)
    assert not is_route_execution_id("other", locator)
    with pytest.raises(ValueError, match="ordinal"):
        route_execution_id(outer, True)
    with pytest.raises(ValueError, match="large"):
        route_execution_id(outer, 1_000_000_000)

    router = FixedRouter(RoutePlan(RouteOutcome.ROUTE, (Route("core", "Unsafe."),)))
    runtime = RuntimeComposition(
        core_execute=lambda source, locator, actor, **kwargs: _result(locator),
        refresh_indexes=lambda: None,
        application_router=router,
    )
    assert runtime.execute("Unsafe.", outer).request_id == outer


def test_full_plan_validation_precedes_all_executor_calls() -> None:
    """Reject a locally invalid exact-source plan before any Core or application side effect."""
    router = FixedRouter(RoutePlan(RouteOutcome.ROUTE, (Route("core", "only part"),)))
    calls: list[str] = []

    result = execute_routed_request(
        user_request="only part remains",
        outer_request_id="outer",
        router=router,
        catalog=_catalog(),
        core_execute=lambda *args, **kwargs: calls.append("core"),
        application_executors={},
    )

    assert result.planning_error == "ROUTER_INVALID"
    assert calls == []


def test_ordered_routes_share_only_prior_context_and_reindex_actions() -> None:
    """Run Core, app, Core in order with one unchanged prior context and contiguous actions."""
    text = "Remember tea. Tomorrow dentist. Remember milk."
    router = FixedRouter(
        RoutePlan(
            RouteOutcome.ROUTE,
            (
                Route("core", "Remember tea."),
                Route("calendar", "Tomorrow dentist."),
                Route("core", "Remember milk."),
            ),
        )
    )
    prior = ({"role": "user", "text": "Earlier fact"},)
    calls: list[tuple[str, str, tuple[object, ...]]] = []

    def core(source, locator, actor, *, conversation_context_override):
        calls.append((source, locator, tuple(conversation_context_override)))
        return _result(locator, actions=2)

    def calendar(source, locator, actor, conversation_context):
        calls.append((source, locator, tuple(conversation_context)))
        return _result(locator, actions=1)

    result = execute_routed_request(
        user_request=text,
        outer_request_id="outer",
        router=router,
        catalog=_catalog(),
        core_execute=core,
        application_executors={"calendar": calendar},
        authenticated_actor=ACTOR,
        conversation_context=prior,
    )

    assert [call[0] for call in calls] == [
        "Remember tea.",
        "Tomorrow dentist.",
        "Remember milk.",
    ]
    assert all(call[2] == prior for call in calls)
    assert router.calls == [(text, prior)]
    assert result.request_id == "outer"
    assert [action.action_index for action in result.action_results] == [0, 1, 2, 3, 4]


def test_parallel_interpretations_overlap_while_core_commits_in_route_order() -> None:
    """Two validated spans may interpret simultaneously, never mutate concurrently."""
    original = "Hoy tengo que ir al cine y mañana iré al teatro"
    spans = ("Hoy tengo que ir al cine", "y mañana iré al teatro")
    router = FixedRouter(RoutePlan(RouteOutcome.ROUTE, tuple(Route("calendar", t) for t in spans)))
    barrier = Barrier(2, timeout=3)
    lock = Lock()
    prepared_threads: list[str] = []
    commits: list[str] = []
    prior = ({"role": "assistant", "text": "Previous turn."},)

    def prepare(source, context):
        assert tuple(context) == prior
        with lock:
            prepared_threads.append(current_thread().name)
        barrier.wait()

        def commit(route_source, locator, actor, previous):
            assert current_thread().name == "MainThread"
            assert route_source == source
            assert tuple(previous) == prior
            assert actor is ACTOR
            commits.append(source)
            return _result(locator, actions=1, affected=(f"note-{len(commits)}",))

        return commit

    result = execute_routed_request(
        user_request=original,
        outer_request_id="parallel-route",
        router=router,
        catalog=_catalog(),
        core_execute=lambda *a, **kw: pytest.fail("no Core reroute"),
        application_executors={},
        route_preparers={"calendar": prepare},
        authenticated_actor=ACTOR,
        conversation_context=prior,
    )
    assert len(set(prepared_threads)) == 2
    assert commits == list(spans)
    assert result.request_id == "parallel-route"
    assert result.status is ApplicationStatus.COMPLETED
    assert result.affected_stable_note_ids == ("note-1", "note-2")
    assert [action.action_index for action in result.action_results] == [0, 1]
    flow = application_result_to_response(result)["execution_flow"]
    assert flow == {
        "version": 1,
        "input": original,
        "parallel_preparation": True,
        "routes": [
            {
                "capability": "calendar",
                "text": spans[0],
                "stage_count": 0,
                "status": "completed",
                "temporal": [],
                "plan": [],
                "entities": [],
                "writes": [],
                "steps": [],
            },
            {
                "capability": "calendar",
                "text": spans[1],
                "stage_count": 0,
                "status": "completed",
                "temporal": [],
                "plan": [],
                "entities": [],
                "writes": [],
                "steps": [],
            },
        ],
    }


def test_parallel_preparation_failure_is_bounded_and_serial_route_continues() -> None:
    """No retry of a failed interpreter and no lost independent Core route."""
    original = "First. Second. Third."
    router = FixedRouter(
        RoutePlan(
            RouteOutcome.ROUTE,
            (
                Route("calendar", "First."),
                Route("core", "Second."),
                Route("calendar", "Third."),
            ),
        )
    )
    commits: list[str] = []

    def prepare(source, context):
        if source == "First.":
            raise RuntimeError("do not replay this provider call")

        def commit(text, locator, actor, prior):
            commits.append(text)
            return _result(locator, actions=1)

        return commit

    def core(text, locator, actor, *, conversation_context_override):
        commits.append(text)
        return _result(locator, actions=1, affected=("second",))

    result = execute_routed_request(
        user_request=original,
        outer_request_id="parallel-partial",
        router=router,
        catalog=_catalog(),
        core_execute=core,
        application_executors={},
        route_preparers={"calendar": prepare},
    )
    assert result.status is ApplicationStatus.PARTIAL
    assert result.action_results[0].reason == "APPLICATION_PREPARATION_FAILED"
    assert commits == ["Second.", "Third."]
    assert result.affected_stable_note_ids == ("second",)


def test_dependency_blocks_without_sibling_text_and_independent_preparation_continues() -> None:
    """Prepare independent spans concurrently but never execute an ungrounded dependent span."""
    source = "Erik arrived. He left. Independent."
    router = FixedRouter(
        RoutePlan(
            RouteOutcome.ROUTE,
            (
                Route("calendar", "Erik arrived."),
                Route("calendar", "He left.", depends_on=0, dependent_mention="He"),
                Route("calendar", "Independent."),
            ),
        )
    )
    prepared = Barrier(2, timeout=3)
    prepared_sources: list[str] = []
    committed: list[str] = []

    def prepare(text, prior):
        assert prior == ()
        prepared_sources.append(text)
        prepared.wait()

        def execute(route_source, locator, actor, context):
            assert route_source == text
            assert context == ()
            committed.append(route_source)
            return _result(locator, actions=1)

        return execute

    result = execute_routed_request(
        user_request=source,
        outer_request_id="dependency-gate",
        router=router,
        catalog=_catalog(),
        core_execute=lambda *args, **kwargs: pytest.fail("no Core reroute"),
        application_executors={},
        route_preparers={"calendar": prepare},
    )

    assert sorted(prepared_sources) == ["Erik arrived.", "Independent."]
    assert committed == ["Erik arrived.", "Independent."]
    assert result.status is ApplicationStatus.PARTIAL
    dependent = result.execution_flow["routes"][1]
    assert dependent["status"] == "needs_attention"
    assert dependent["depends_on"] == 0
    assert dependent["reason"] == "ROUTE_DEPENDENCY_CANONICAL_EVIDENCE_UNAVAILABLE"


def test_dependency_does_not_retry_or_run_after_failed_predecessor() -> None:
    """Keep a failed predecessor isolated and expose its dependent's blocked reason."""
    source = "First. Dependent. Independent."
    router = FixedRouter(
        RoutePlan(
            RouteOutcome.ROUTE,
            (
                Route("core", "First."),
                Route("core", "Dependent.", depends_on=0, dependent_mention="Dependent"),
                Route("core", "Independent."),
            ),
        )
    )
    calls: list[str] = []

    def core(text, locator, actor, *, conversation_context_override):
        del locator, actor, conversation_context_override
        calls.append(text)
        if text == "First.":
            raise RuntimeError("failed once")
        return _result(route_execution_id("dependency-failure", 2), actions=1)

    result = execute_routed_request(
        user_request=source,
        outer_request_id="dependency-failure",
        router=router,
        catalog=_catalog(),
        core_execute=core,
        application_executors={},
    )

    assert calls == ["First.", "Independent."]
    assert result.status is ApplicationStatus.PARTIAL
    assert result.execution_flow["routes"][1]["reason"] == (
        "ROUTE_DEPENDENCY_PREDECESSOR_NOT_COMPLETED"
    )


def test_preparation_is_disabled_for_single_route_or_invalid_route_plan() -> None:
    """Never pre-interpret before validation, and don't spawn workers for one route."""
    called: list[str] = []

    def prepare(source, context):
        called.append("prepare")
        raise AssertionError("single/invalid route must not pre-interpret")

    def regular(source, locator, actor, context):
        called.append("regular")
        return _result(locator, actions=1)

    single = execute_routed_request(
        user_request="Tomorrow.",
        outer_request_id="one",
        router=FixedRouter(RoutePlan(RouteOutcome.ROUTE, (Route("calendar", "Tomorrow."),))),
        catalog=_catalog(),
        core_execute=lambda *a, **k: None,
        application_executors={"calendar": regular},
        route_preparers={"calendar": prepare},
    )
    assert single.status is ApplicationStatus.COMPLETED
    assert application_result_to_response(single)["execution_flow"]["parallel_preparation"] is False
    invalid = execute_routed_request(
        user_request="First. Second.",
        outer_request_id="bad",
        router=FixedRouter(RoutePlan(RouteOutcome.ROUTE, (Route("calendar", "First."),))),
        catalog=_catalog(),
        core_execute=lambda *a, **k: None,
        application_executors={"calendar": regular},
        route_preparers={"calendar": prepare},
    )
    assert invalid.planning_error == "ROUTER_INVALID"
    assert called == ["regular"]


def test_runtime_captures_prior_context_once_and_appends_only_outer_turn(tmp_path: Path) -> None:
    """Keep the current outer wording out of every routed planner's continuity evidence."""
    resolver = ConversationRootResolver(tmp_path / "state")
    router = FixedRouter(
        RoutePlan(
            RouteOutcome.ROUTE,
            (Route("core", "Remember tea."), Route("calendar", "Tomorrow dentist.")),
        )
    )
    seen: list[tuple[str, tuple[object, ...]]] = []

    def core(source, locator, actor, *, conversation_context_override):
        seen.append((source, tuple(conversation_context_override)))
        return _result(locator)

    def calendar(source, locator, actor, conversation_context):
        seen.append((source, tuple(conversation_context)))
        return _result(locator)

    runtime = RuntimeComposition(
        core_execute=core,
        refresh_indexes=lambda: pytest.fail("no mutation should refresh"),
        application_catalog=_catalog(),
        application_router=router,
        application_executors={"calendar": calendar},
        conversation_root_resolver=resolver,
    )
    runtime.append_conversation_turn(
        "main", "prior", "user", "Earlier fact.", authenticated_actor=ACTOR
    )

    result = runtime.execute("Remember tea. Tomorrow dentist.", "outer", "main", ACTOR)
    turns = LocalConversationStore(resolver.resolve(ACTOR.stable_user_id)).load_main_page()["turns"]
    prior = ({"role": "user", "text": "Earlier fact."},)

    assert result.request_id == "outer"
    assert router.calls == [("Remember tea. Tomorrow dentist.", prior)]
    assert seen == [("Remember tea.", prior), ("Tomorrow dentist.", prior)]
    assert [turn["text"] for turn in turns] == ["Earlier fact.", "Remember tea. Tomorrow dentist."]


def test_route_failures_are_bounded_and_later_independent_routes_continue() -> None:
    """Contain executor exceptions, missing apps, and correlation substitutions per route."""
    text = "First. Second. Third."
    router = FixedRouter(
        RoutePlan(
            RouteOutcome.ROUTE,
            (Route("core", "First."), Route("calendar", "Second."), Route("core", "Third.")),
        )
    )
    calls: list[str] = []

    def core(source, locator, actor, *, conversation_context_override):
        calls.append(source)
        if source == "First.":
            raise RuntimeError("contained")
        return _result(locator, affected=("third",))

    result = execute_routed_request(
        user_request=text,
        outer_request_id="outer",
        router=router,
        catalog=_catalog(),
        core_execute=core,
        application_executors={},
    )

    assert calls == ["First.", "Third."]
    assert result.status is ApplicationStatus.PARTIAL
    assert result.affected_stable_note_ids == ("third",)
    assert [action.reason for action in result.action_results] == [
        "APPLICATION_EXECUTION_FAILED",
        "APPLICATION_EXECUTOR_UNAVAILABLE",
    ]


def test_invalid_route_correlation_and_all_failures_stay_outer_bounded() -> None:
    """Do not accept an executor result correlated to an outer or sibling request identity."""
    router = FixedRouter(RoutePlan(RouteOutcome.ROUTE, (Route("calendar", "Calendar."),)))
    result = execute_routed_request(
        user_request="Calendar.",
        outer_request_id="outer",
        router=router,
        catalog=_catalog(),
        core_execute=lambda *args, **kwargs: pytest.fail("Core must not run"),
        application_executors={"calendar": lambda *_args: _result("outer")},
    )

    assert result.request_id == "outer"
    assert result.status is ApplicationStatus.FAILED
    assert result.action_results[0].reason == "APPLICATION_CORRELATION_INVALID"


def test_needs_attention_route_status_remains_visible_without_a_completed_sibling() -> None:
    """Keep a deferred independent route distinct from a wholly operational route failure."""
    router = FixedRouter(
        RoutePlan(RouteOutcome.ROUTE, (Route("core", "Clarify."), Route("calendar", "Fail.")))
    )
    result = execute_routed_request(
        user_request="Clarify. Fail.",
        outer_request_id="outer",
        router=router,
        catalog=_catalog(),
        core_execute=lambda source, locator, actor, **kwargs: _result(
            locator, status=ApplicationStatus.NEEDS_ATTENTION
        ),
        application_executors={},
    )

    assert result.status is ApplicationStatus.NEEDS_ATTENTION
    assert result.action_results[0].reason == "APPLICATION_EXECUTOR_UNAVAILABLE"


@pytest.mark.parametrize(
    ("outcome", "expected_product", "field", "code"),
    [
        (RouteOutcome.CLARIFY, "CLARIFY", "clarification_code", "ROUTER_CLARIFY"),
        (
            RouteOutcome.NEEDS_CAPABILITY,
            "CANNOT_ANSWER",
            "planning_error",
            "ROUTER_NEEDS_CAPABILITY",
        ),
    ],
)
def test_nonexecuting_router_outcomes_have_distinct_product_semantics(
    outcome: RouteOutcome, expected_product: str, field: str, code: str
) -> None:
    """Keep routing ambiguity resumable-looking only for the explicit CLARIFY outcome."""
    router = FixedRouter(RoutePlan(outcome, ()))
    result = execute_routed_request(
        user_request="Need something",
        outer_request_id="outer",
        router=router,
        catalog=_catalog(),
        core_execute=lambda *args, **kwargs: pytest.fail("no executor"),
        application_executors={},
    )
    response = application_result_to_response(result)

    assert getattr(result, field) == code
    assert response["product_outcome"] == expected_product
    assert response["product_reason"] == code
    assert response["actions"] == []


def test_router_provider_usage_is_retained_as_operational_stage() -> None:
    """Carry Router model/tokens into public operational evidence for cost calculation."""

    class TelemetryRouter(FixedRouter):
        model = "gpt-6-luna"
        reasoning_effort = "medium"
        last_call = True
        last_provider_status = "completed"
        last_response_id = "resp-router"
        last_error_category = None
        last_usage = {
            "input_tokens": 100,
            "output_tokens": 25,
            "input_tokens_details": {"cached_tokens": 20},
            "output_tokens_details": {"reasoning_tokens": 7},
        }

    router = TelemetryRouter(RoutePlan(RouteOutcome.ROUTE, (Route("core", "Remember tea."),)))
    result = execute_routed_request(
        user_request="Remember tea.",
        outer_request_id="outer",
        router=router,
        catalog=_catalog(),
        core_execute=lambda source, locator, actor, **kwargs: _result(locator),
        application_executors={},
    )

    stage = result.operational.stages[0]
    assert stage.name == "application.router"
    assert stage.model == "gpt-6-luna"
    assert stage.reasoning_effort == "medium"
    assert stage.usage == {
        "input_tokens": 100,
        "cached_input_tokens": 20,
        "output_tokens": 25,
        "reasoning_tokens": 7,
    }
    assert stage.provider_calls[0].response_id == "resp-router"


def test_scalar_pending_and_history_fail_closed_when_multiple_routes_provide_them() -> None:
    """Preserve one scalar evidence item, but never falsely select between route-local ones."""
    router = FixedRouter(
        RoutePlan(RouteOutcome.ROUTE, (Route("core", "One."), Route("core", "Two.")))
    )

    def core(source, locator, actor, *, conversation_context_override):
        return _result(
            locator,
            pending=PendingWorkStatus(required=True, persisted=True, record_id=locator),
            history=GitHistoryResult(HistoryStatus.COMMITTED, commit_sha=source),
        )

    result = execute_routed_request(
        user_request="One. Two.",
        outer_request_id="outer",
        router=router,
        catalog=_catalog(),
        core_execute=core,
        application_executors={},
    )

    assert result.pending_work == PendingWorkStatus(
        required=True, error="MULTIPLE_ROUTE_PENDING_WORK"
    )
    assert result.history == GitHistoryResult(HistoryStatus.FAILED, reason="MULTIPLE_ROUTE_HISTORY")


def test_one_non_disabled_history_result_is_preserved() -> None:
    """Retain a sole route-local history result rather than manufacturing aggregate history."""
    router = FixedRouter(RoutePlan(RouteOutcome.ROUTE, (Route("core", "One."),)))
    history = GitHistoryResult(HistoryStatus.COMMITTED, commit_sha="a" * 40)
    result = execute_routed_request(
        user_request="One.",
        outer_request_id="outer",
        router=router,
        catalog=_catalog(),
        core_execute=lambda source, locator, actor, **kwargs: _result(locator, history=history),
        application_executors={},
    )

    assert result.history == history


def _routed_pending_runtime(tmp_path: Path, *, pending_routes: int = 1):
    """Build a real durable-pending fixture with one success and one or two deferred Core routes."""
    schema = json.loads((ROOT / "config/note-schema.json").read_text())
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    for note_id, label in (("marta-1", "Marta Lyon"), ("marta-2", "Marta Madrid")):
        (vault_root / f"{note_id}.md").write_text(
            serialize_note(
                Note(
                    {
                        "id": note_id,
                        "name": label,
                        "type": "person",
                        "created_at": "2026-10-01T00:00:00Z",
                        "updated_at": "2026-10-01T00:00:00Z",
                        "created_by": {"human": None, "app": "test"},
                        "updated_by": {"human": None, "app": "test"},
                        "revision": 1,
                        "schema_version": 3,
                    },
                    "Known fact.",
                )
            ),
            encoding="utf-8",
        )
    pending_root = tmp_path / "pending"
    pending_root.mkdir()
    pending_repo = PendingWorkRepository(pending_root)
    resolver = ConversationRootResolver(tmp_path / "state")
    sources = ["Record success.", "Resolve Marta."]
    if pending_routes == 2:
        sources.append("Resolve Marta again.")
    router = FixedRouter(
        RoutePlan(RouteOutcome.ROUTE, tuple(Route("core", source) for source in sources))
    )
    calls: list[tuple[str, str, object]] = []

    def core(
        source, request_id, actor=None, _conversation_id=None, plan=None, choice=None, **kwargs
    ):
        calls.append((source, request_id, plan))
        if plan is not None:
            return _result(request_id)
        if source == "Record success.":
            return _result(request_id, affected=("success",))
        action = WriteAction(
            (
                KnowledgeUnit(
                    SelectionCriteria("Marta", source, "person", (), None),
                    "amend",
                    (),
                    (),
                    ("Marta update.",),
                    (),
                ),
            )
        )
        deferred = ApplicationResult(
            request_id,
            ApplicationStatus.NEEDS_ATTENTION,
            (
                ActionResult(
                    0,
                    "write",
                    ActionStatus.DEFERRED,
                    unit_results=(
                        UnitResult(
                            0,
                            UnitStatus.DEFERRED,
                            reason="ambiguous_existing_target",
                            candidates=("marta-1", "marta-2"),
                        ),
                    ),
                ),
            ),
            (),
        )
        pending_repo.record(
            user_request=source,
            plan=RequestPlan((action,), ()),
            result=deferred,
            created_at="2026-10-01T00:00:00Z",
        )
        return ApplicationResult(
            request_id,
            deferred.status,
            deferred.action_results,
            (),
            pending_work=PendingWorkStatus(required=True, persisted=True, record_id=request_id),
        )

    class Notes:
        """Read exactly the candidate labels needed for a bounded clarification view."""

        def detail(self, note_id):
            """Return the local label for an already validated opaque candidate ID."""
            return SimpleNamespace(
                note=SimpleNamespace(
                    id=note_id,
                    name={
                        "marta-1": "Marta Lyon",
                        "marta-2": "Marta Madrid",
                    }[note_id],
                )
            )

    refreshes: list[None] = []
    runtime = RuntimeComposition(
        core_execute=core,
        refresh_indexes=lambda: refreshes.append(None),
        application_catalog=ApplicationCatalog.empty(),
        application_router=router,
        conversation_root_resolver=resolver,
        pending_recorder=pending_repo,
        vault_repository=VaultRepository(vault_root),
        canonical_schema=schema,
        notes_service=Notes(),
    )
    return runtime, router, calls, refreshes, resolver


def test_routed_partial_clarification_resumes_only_saved_route_without_router_replay(
    tmp_path: Path,
) -> None:
    """Resume a persisted route-local plan while preserving an earlier sibling completion exactly once."""
    runtime, router, calls, refreshes, resolver = _routed_pending_runtime(tmp_path)
    outer = "outer-delivery"

    initial = runtime.execute_product("Record success. Resolve Marta.", outer, "main", ACTOR)
    state = LocalClarificationStore(resolver.resolve(ACTOR.stable_user_id), "main")
    pending = state.read()

    assert initial["request_id"] == outer
    assert initial["status"] == "partial"
    assert initial["product_outcome"] == "CLARIFY"
    assert pending is not None
    assert pending.original_request == "Resolve Marta."
    assert pending.original_request_id == pending.pending_record_id
    assert is_route_execution_id(outer, pending.pending_record_id)
    assert len(router.calls) == 1
    assert [call[0] for call in calls] == ["Record success.", "Resolve Marta."]
    assert len(refreshes) == 1

    resumed = runtime.execute_product("2", "reply-delivery", "main", ACTOR)

    assert resumed["product_outcome"] == "ANSWER"
    assert state.read() is None
    assert len(router.calls) == 1
    assert [call[0] for call in calls] == [
        "Record success.",
        "Resolve Marta.",
        "Resolve Marta.",
    ]
    assert calls[-1][2] is not None
    turns = LocalConversationStore(resolver.resolve(ACTOR.stable_user_id)).load_main_page()["turns"]
    assert [turn["text"] for turn in turns] == ["Record success. Resolve Marta.", "2"]


def test_multiple_routed_pending_results_never_create_misleading_clarification(
    tmp_path: Path,
) -> None:
    """Keep a scalar pending bridge inactive when two route-local pending records exist."""
    runtime, _router, _calls, refreshes, resolver = _routed_pending_runtime(
        tmp_path, pending_routes=2
    )

    response = runtime.execute_product(
        "Record success. Resolve Marta. Resolve Marta again.", "outer", "main", ACTOR
    )

    state = LocalClarificationStore(resolver.resolve(ACTOR.stable_user_id), "main")
    assert response["product_outcome"] == "CANNOT_ANSWER"
    assert response["pending_work"] == {
        "required": True,
        "persisted": False,
        "record_id": None,
        "error": "MULTIPLE_ROUTE_PENDING_WORK",
    }
    assert state.read() is None
    assert len(refreshes) == 1


def test_temporal_is_a_builtin_pre_core_route_not_an_application() -> None:
    """Route exact-date normalization through the built-in Temporal executor before Core ownership."""
    source = "Hoy hemos vaciado el garaje con Bea y mis hijos."
    router = FixedRouter(RoutePlan(RouteOutcome.ROUTE, (Route("temporal", source),)))
    calls: list[tuple[str, str]] = []

    def temporal(text, locator, actor, conversation_context):
        calls.append(("temporal", text))
        return _result(locator, actions=1)

    result = execute_routed_request(
        user_request=source,
        outer_request_id="outer",
        router=router,
        catalog=ApplicationCatalog.empty(),
        core_execute=lambda *args, **kwargs: pytest.fail("Router must not bypass Temporal"),
        application_executors={},
        temporal_execute=temporal,
    )

    assert calls == [("temporal", source)]
    assert result.status is ApplicationStatus.COMPLETED
    assert result.request_id == "outer"


def test_two_independent_temporal_routes_execute_separately_in_source_order() -> None:
    """Keep Router atomization intact when adjacent independent spans share Temporal."""
    source = "Ayer vi a Ana y hoy vi a Luis."
    router = FixedRouter(
        RoutePlan(
            RouteOutcome.ROUTE,
            (
                Route("temporal", "Ayer vi a Ana"),
                Route("temporal", "y hoy vi a Luis."),
            ),
        )
    )
    calls: list[tuple[str, str]] = []

    def temporal(text, locator, actor, conversation_context):
        calls.append((text, locator))
        return _result(locator, actions=1)

    result = execute_routed_request(
        user_request=source,
        outer_request_id="outer",
        router=router,
        catalog=ApplicationCatalog.empty(),
        core_execute=lambda *args, **kwargs: pytest.fail("Router must not bypass Temporal"),
        application_executors={},
        temporal_execute=temporal,
    )

    assert calls == [
        ("Ayer vi a Ana", route_execution_id("outer", 0)),
        ("y hoy vi a Luis.", route_execution_id("outer", 1)),
    ]
    assert calls[0][1] != calls[1][1]
    assert result.status is ApplicationStatus.COMPLETED
    assert result.request_id == "outer"
    assert [action.action_index for action in result.action_results] == [0, 1]


def test_temporal_route_fails_closed_when_runtime_executor_is_unavailable() -> None:
    """Never silently send a Temporal-owned span straight to Core if normalization is unavailable."""
    source = "Marta empieza mañana a trabajar en Airbus."
    router = FixedRouter(RoutePlan(RouteOutcome.ROUTE, (Route("temporal", source),)))

    result = execute_routed_request(
        user_request=source,
        outer_request_id="outer",
        router=router,
        catalog=ApplicationCatalog.empty(),
        core_execute=lambda *args, **kwargs: pytest.fail(
            "Core must not receive unresolved temporal text"
        ),
        application_executors={},
    )

    assert result.status is ApplicationStatus.FAILED
    assert result.action_results[0].reason == "TEMPORAL_EXECUTOR_UNAVAILABLE"
