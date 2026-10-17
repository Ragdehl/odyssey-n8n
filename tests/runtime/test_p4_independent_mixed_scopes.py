"""E2/E3 independent mixed Core + Tasks route through the SAME normal services.

All provider outputs are frozen; Core Writer, canonical Markdown, actual
Tasks Work Session service, authenticated SELF and E3 replay are real.
"""

from __future__ import annotations

from copy import deepcopy

import pytest

from odyssey_apps.tasks import TaskWorkSessionService
from odyssey_core import create_entity
from odyssey_core.application import ApplicationResult, ApplicationStatus
from odyssey_core.independent_source_scopes import (
    IndependentSourceScopesError,
    verify_independent_source_scopes,
)
from odyssey_core.note_queries import NotesQueryService
from odyssey_core.notes import parse_note
from tests.runtime.test_whole_source_light_product_p4 import (
    SCHEMA,
    RecordedClient,
    _fixture,
)

CORE = "Me gusta correr por la tarde."
TASK = "Empieza una sesión de trabajo en la tarea Preparar informe Atlas."
SOURCE = CORE + " " + TASK
CLOCK = "2026-10-16T18:00:00+02:00"


def _outer_route():
    return {
        "capabilities": ["core", "tasks"],
        "interpretation": "separable",
        "reason": "independent",
        "self_relation_span": None,
        "app_scopes": [
            {
                "capability": "core",
                "description": "personal preference",
                "depends_on_another_scope": False,
            },
            {
                "capability": "tasks",
                "description": "start work session",
                "depends_on_another_scope": False,
            },
        ],
    }


def _partitions():
    return {
        "full_source_quote": SOURCE,
        "parts": [
            {"capability": "core", "source_quote": CORE + " "},
            {"capability": "tasks", "source_quote": TASK},
        ],
    }


def _audit(**changes):
    return {
        "full_source_quote": SOURCE,
        "complete": True,
        "independent": True,
        "no_cross_scope_referents": True,
        **changes,
    }


def _provider_rows():
    return [
        _outer_route(),
        _partitions(),
        _audit(),
        {"only_task_semantics": True, "exactly_one_operation": True, "source_quote": TASK},
        {
            "capabilities": ["core"],
            "interpretation": "joint",
            "reason": "single",
            "self_relation_span": None,
            "app_scopes": [],
        },
        {
            "entities": [],
            "facts": [
                {
                    "meaning": "Me gusta correr por la tarde.",
                    "kind": "record",
                    "subject": "speaker",
                    "date": None,
                    "daypart": None,
                    "participants": [],
                    "source_evidence": CORE,
                    "dependent_on_fact_index": None,
                    "needs_clarification": False,
                }
            ],
            "unresolved": [],
        },
        {
            "approved": True,
            "complete": True,
            "reason": None,
            "facts": [
                {
                    "ordinal": 0,
                    "source_quote": CORE,
                    "kind": "record",
                    "reviewed_text": "Me gusta correr por la tarde.",
                    "date": None,
                    "reference_names": [],
                    "supported": True,
                }
            ],
        },
        {
            "facts": [
                {
                    "ordinal": 1,
                    "role": "self_participant",
                    "assertion": "asserted",
                    "source_quote": CORE,
                }
            ]
        },
        {
            "facts": [
                {
                    "ordinal": 0,
                    "role": "self_participant",
                    "assertion": "asserted",
                    "source_quote": CORE,
                }
            ]
        },
        {
            "capabilities": ["tasks"],
            "interpretation": "joint",
            "reason": "single",
            "self_relation_span": None,
            "app_scopes": [],
        },
    ]


def _runtime(tmp_path):
    repo, actor, executor, runtime = _fixture(tmp_path, incremental_indexes=True)
    create_entity(
        repo,
        SCHEMA,
        path="task.md",
        entity_id="atlas-task",
        metadata={"name": "Preparar informe Atlas", "type": "task", "status": "pending"},
        content="- Preparar informe Atlas.\n",
        actor="fixture",
        now=CLOCK,
    )
    executor.context_index.rebuild(repo, SCHEMA, executor.embedder)
    executor.semantic_index.rebuild(repo, SCHEMA, executor.embedder)
    session_service = TaskWorkSessionService(
        repo, SCHEMA, None, id_allocator=lambda: "mixed-session-one"
    )
    calls = []

    def delegate(source, delivery, who):
        assert source == TASK
        assert who.stable_user_id == actor.stable_user_id
        calls.append(delivery)
        receipt = session_service.start(
            task_id="atlas-task",
            started_at=CLOCK,
            request_id=delivery,
            actor=who.stable_user_id,
            now=CLOCK,
        )
        return ApplicationResult(delivery, ApplicationStatus.COMPLETED, (), (receipt.session.id,))

    executor.task_delegate = delegate
    runtime.notes_service = NotesQueryService(repo, SCHEMA, executor.context_index)
    runtime.work_session_service = session_service
    runtime.vault_repository = repo
    runtime.canonical_schema = SCHEMA
    runtime.notes_mutation_actor = lambda *_: actor.stable_user_id
    return repo, actor, executor, runtime, calls


def _snapshot(repo):
    return {p: repo.read_text(p) for p in repo.list_markdown_paths()}


def test_mixed_independent_core_and_work_session_share_authored_notes_ui_and_e3(tmp_path):
    repo, actor, executor, runtime, calls = _runtime(tmp_path)
    executor.client = RecordedClient(_provider_rows())
    first = runtime.execute_product(SOURCE, "mixed-independent-chat-1", "main", actor)
    assert first["status"] == "completed", first
    assert executor.client.rows == []
    assert len(calls) == 1 and calls[0].endswith("-independent-1")
    flow = first["execution_flow"]
    stages = first["operational"]["stages"]
    assert flow["version"] == 1 and flow["input"] == SOURCE
    assert flow["parallel_preparation"] is False
    assert [route["capability"] for route in flow["routes"]] == ["core", "tasks"]
    assert stages[0]["name"] == "application.router"
    assert 0 <= stages[0]["duration_ms"] < first["operational"]["total_duration_ms"]
    offset = 1
    for route in flow["routes"]:
        expected = stages[offset : offset + route["stage_count"]]
        assert [step["name"] for step in route["steps"]] == [s["name"] for s in expected]
        assert all(stage["stage_view"] for stage in expected)
        offset += route["stage_count"]
    assert [stage["name"] for stage in stages[offset:]] == ["index_refresh"]
    assert "Me gusta correr por la tarde." in repo.read_text("self.md")
    task = runtime.notes("detail", {"note_id": "atlas-task"}, actor)
    assert len(task["work_sessions"]) == 1
    session = task["work_sessions"][0]
    add = {
        "operation": "work_session_activity_add",
        "session_id": session["id"],
        "text": "Probé el mensaje mixto.",
        "request_id": "mixed-ui-activity",
        "expected_revision": session["mutation"]["revision"],
        "expected_source_hash": session["mutation"]["source_hash"],
    }
    added = runtime.notes(
        "work_session_activity_add", {k: v for k, v in add.items() if k != "operation"}, actor
    )
    assert len(added["work_sessions"][0]["activity"]) == 1
    saved = _snapshot(repo)
    replay = runtime.execute_product(SOURCE, "mixed-independent-chat-1", "main", actor)
    assert replay["delivery_replayed"] is True
    assert _snapshot(repo) == saved and len(calls) == 1
    assert (
        len(
            [
                p
                for p in repo.list_markdown_paths()
                if parse_note(repo.read_text(p)).metadata["type"] == "work_session"
            ]
        )
        == 1
    )


@pytest.mark.parametrize(
    "change",
    [
        {"full_source_quote": CORE + TASK},
        {
            "parts": [
                {"capability": "core", "source_quote": CORE},
                {"capability": "tasks", "source_quote": TASK},
            ]
        },
        {
            "parts": [
                {"capability": "tasks", "source_quote": TASK},
                {"capability": "core", "source_quote": CORE + " "},
            ]
        },
        {"parts": [{"capability": "core", "source_quote": SOURCE}]},
    ],
)
def test_source_partition_rejects_omissions_duplicates_reorder_and_scope_loss(change):
    proposed = _partitions() | change
    with pytest.raises(IndependentSourceScopesError):
        verify_independent_source_scopes(
            SOURCE, proposed, _audit(), permitted_capabilities=frozenset({"core", "tasks"})
        )


@pytest.mark.parametrize(
    "audit",
    [
        {"complete": False},
        {"independent": False},
        {"no_cross_scope_referents": False},
        {"full_source_quote": "different source"},
    ],
)
def test_independent_semantic_review_veto_never_modifies_vault(tmp_path, audit):
    repo, actor, executor, runtime, calls = _runtime(tmp_path)
    executor.client = RecordedClient([_outer_route(), _partitions(), _audit(**audit)])
    prior = _snapshot(repo)
    response = runtime.execute_product(SOURCE, "independent-veto-" + str(len(audit)), "main", actor)
    assert response["status"] == "needs_attention"
    assert calls == [] and _snapshot(repo) == prior


def test_partitioned_tasks_only_scope_veto_blocks_all_writes_in_preflight(tmp_path):
    repo, actor, executor, runtime, calls = _runtime(tmp_path)
    rows = _provider_rows()
    rows[3] = {**rows[3], "only_task_semantics": False}
    executor.client = RecordedClient(rows)
    response = runtime.execute_product(SOURCE, "independent-partial-1", "main", actor)
    assert response["status"] == "needs_attention"
    assert "Me gusta correr por la tarde." not in repo.read_text("self.md")
    assert calls == []
    before = _snapshot(repo)
    assert runtime.execute_product(SOURCE, "independent-partial-1", "main", actor)[
        "delivery_replayed"
    ]
    assert before == _snapshot(repo)


def test_joint_or_dependent_route_does_not_activate_independent_execution(tmp_path):
    repo, actor, executor, runtime, calls = _runtime(tmp_path)
    route = deepcopy(_outer_route())
    route["app_scopes"][1]["depends_on_another_scope"] = True
    executor.client = RecordedClient([route])
    # Normal whole-source pipeline may request additional model outputs; we
    # check ONLY the first request did not enter the partition generator.
    with pytest.raises(AssertionError, match="Unplanned model call"):
        runtime.execute_product(SOURCE, "dependent-not-partitioned", "main", actor)
    assert "odyssey_independent_source_scopes_v1" not in executor.client.calls
    assert calls == []


def test_independent_second_scope_provider_outage_returns_durable_partial(tmp_path):
    from openai import OpenAIError

    repo, actor, executor, runtime, calls = _runtime(tmp_path)

    class FailSecondScopedRouter(RecordedClient):
        def create(self, **kwargs):
            schema = kwargs["text"]["format"]["name"]
            if schema == "odyssey_light_capability_route_v1" and len(self.calls) == 9:
                raise OpenAIError("synthetic provider outage after first canonical fact")
            return super().create(**kwargs)

    executor.client = FailSecondScopedRouter(_provider_rows()[:-1])
    response = runtime.execute_product(SOURCE, "mixed-p4-second-provider-down", "main", actor)
    assert response["status"] == "partial"
    assert "Me gusta correr por la tarde." in repo.read_text("self.md")
    assert calls == []
    prior = _snapshot(repo)
    assert runtime.execute_product(SOURCE, "mixed-p4-second-provider-down", "main", actor)[
        "delivery_replayed"
    ]
    assert prior == _snapshot(repo)


def test_second_scoped_router_cannot_smuggle_core_into_tasks_source(tmp_path):
    repo, actor, executor, runtime, calls = _runtime(tmp_path)
    rows = _provider_rows()
    rows[-1] = {**rows[-1], "capabilities": ["tasks", "core"]}
    executor.client = RecordedClient(rows)
    response = runtime.execute_product(SOURCE, "mixed-p4-router-scope-mismatch", "main", actor)
    assert response["status"] == "partial"
    assert calls == [] and "Me gusta correr por la tarde." in repo.read_text("self.md")


def test_independent_first_scope_provider_outage_does_not_claim_physical_partial(tmp_path):
    from openai import OpenAIError

    repo, actor, executor, runtime, calls = _runtime(tmp_path)

    class FailFirstScopedPlanner(RecordedClient):
        def create(self, **kwargs):
            if kwargs["text"]["format"]["name"] == "odyssey_light_shared_semantic_plan_v1":
                raise OpenAIError("synthetic no-write planner outage")
            return super().create(**kwargs)

    executor.client = FailFirstScopedPlanner(_provider_rows()[:5])
    before = _snapshot(repo)
    result = runtime.execute_product(SOURCE, "mixed-p4-first-provider-down", "main", actor)
    assert result["status"] == "needs_attention"
    assert calls == [] and _snapshot(repo) == before


def test_partition_three_independent_scopes_preserves_all_original_bytes():
    pieces = ["Hoy ordené libros. ", "Inicia sesión para estudiar. ", "También he preparado café."]
    source = "".join(pieces)
    proof = verify_independent_source_scopes(
        source,
        {
            "full_source_quote": source,
            "parts": [
                {"capability": "core", "source_quote": pieces[0]},
                {"capability": "tasks", "source_quote": pieces[1]},
                {"capability": "core", "source_quote": pieces[2]},
            ],
        },
        {
            "full_source_quote": source,
            "complete": True,
            "independent": True,
            "no_cross_scope_referents": True,
        },
        permitted_capabilities=frozenset({"core", "tasks"}),
    )
    assert [part.index for part in proof] == [0, 1, 2]
    assert "".join(part.source for part in proof) == source


def test_all_independent_scopes_share_one_frozen_delivery_clock_across_midnight(tmp_path):
    from datetime import datetime

    repo, actor, executor, runtime, calls = _runtime(tmp_path)
    executor.client = RecordedClient(_provider_rows())
    clock_calls = []

    def jumping_clock():
        clock_calls.append(True)
        if len(clock_calls) > 1:
            return datetime.fromisoformat("2026-10-17T00:01:00+02:00")
        return datetime.fromisoformat("2026-10-16T23:59:59+02:00")

    executor.now = jumping_clock
    outcome = runtime.execute_product(SOURCE, "mixed-clock-one-instant", "main", actor)
    assert outcome["status"] == "completed"
    assert len(clock_calls) == 1
    assert "recorded_at=2026-10-16T23:59:59+02:00" in repo.read_text("self.md")
    assert len(calls) == 1


def test_mixed_full_source_then_ui_mutation_over_actual_localhost_http(tmp_path):
    import json
    from http.client import HTTPConnection
    from http.server import ThreadingHTTPServer
    from threading import Thread

    from odyssey_runtime.server import _handler_for

    repo, actor, executor, runtime, calls = _runtime(tmp_path)
    executor.client = RecordedClient(_provider_rows())
    server = ThreadingHTTPServer(("127.0.0.1", 0), _handler_for(runtime))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def post(endpoint, payload):
        connection = HTTPConnection("127.0.0.1", server.server_port, timeout=15)
        connection.request(
            "POST",
            endpoint,
            json.dumps(
                {**payload, "authenticated_actor": {"stable_user_id": actor.stable_user_id}}
            ),
            {"Content-Type": "application/json"},
        )
        response = connection.getresponse()
        status = response.status
        body = json.loads(response.read())
        connection.close()
        return status, body

    try:
        payload = {
            "request": SOURCE,
            "request_id": "mixed-http-shared-1",
            "conversation_id": "main",
        }
        status, first = post("/execute", payload)
        assert status == 200 and first["status"] == "completed"
        assert len(first["execution_flow"]["routes"]) == 2
        assert first["operational"]["stages"][0]["name"] == "application.router"
        assert len(calls) == 1
        status, seen = post("/notes", {"operation": "detail", "note_id": "atlas-task"})
        assert status == 200 and len(seen["work_sessions"]) == 1
        session = seen["work_sessions"][0]
        activity = {
            "operation": "work_session_activity_add",
            "session_id": session["id"],
            "text": "Verificado por HTTP real.",
            "request_id": "mixed-http-ui-1",
            "expected_revision": session["mutation"]["revision"],
            "expected_source_hash": session["mutation"]["source_hash"],
        }
        status, changed = post("/notes", activity)
        assert status == 200 and len(changed["work_sessions"][0]["activity"]) == 1
        before_replay = _snapshot(repo)
        assert post("/execute", payload)[1]["delivery_replayed"] is True
        assert _snapshot(repo) == before_replay and len(calls) == 1
        assert "Me gusta correr por la tarde." in repo.read_text("self.md")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_independent_scope_execution_ledger_uses_only_actual_stages_and_route_indices(tmp_path):
    from odyssey_runtime.execution_ledger import project_execution_ledger

    repo, actor, executor, _, calls = _runtime(tmp_path)
    executor.client = RecordedClient(_provider_rows())
    result = executor(SOURCE, "p4-mixed-e2-ledger", actor, "main")
    assert result.status is ApplicationStatus.COMPLETED
    report = project_execution_ledger(result)
    assert [route["capability"] for route in report["routes"]] == ["core", "tasks"]
    assert report["stages"][0]["name"] == "application.router"
    assert report["stages"][0]["route_index"] is None
    assert all(stage["route_index"] == 0 for stage in report["stages"][1:])
    assert len(calls) == 1
    assert "Me gusta correr por la tarde." in repo.read_text("self.md")


def test_misrouted_future_indicative_task_is_rejected_before_any_core_write(tmp_path):
    """Even two mistaken model classifications cannot turn a future plan into a Task.

    The independent Task scope audit must run BEFORE the first Core write.
    The false classification itself is injected as untrusted provider output;
    this fixture intentionally does not assert that real GPT always agrees.
    """
    repo, actor, executor, runtime, calls = _runtime(tmp_path)
    source = "Hoy compré pan y mañana compraré leche."
    first = "Hoy compré pan y "
    second = "mañana compraré leche."
    assert first + second == source
    proposal = {
        "full_source_quote": source,
        "parts": [
            {"capability": "core", "source_quote": first},
            {"capability": "tasks", "source_quote": second},
        ],
    }
    audit = {
        "full_source_quote": source,
        "complete": True,
        "independent": True,
        "no_cross_scope_referents": True,
    }
    executor.client = RecordedClient(
        [
            _outer_route(),
            proposal,
            audit,
            {"only_task_semantics": False, "exactly_one_operation": False, "source_quote": second},
        ]
    )
    prior = _snapshot(repo)
    result = runtime.execute_product(source, "misrouted-future-preflight", "main", actor)
    assert result["status"] == "needs_attention"
    assert result["affected_stable_note_ids"] == []
    assert _snapshot(repo) == prior and calls == []
    assert executor.client.rows == []
    assert executor.client.calls == [
        "odyssey_light_capability_route_v1",
        "odyssey_independent_source_scopes_v1",
        "odyssey_independent_source_scopes_audit_v1",
        "odyssey_task_only_scope_v1",
    ]
    replay = runtime.execute_product(source, "misrouted-future-preflight", "main", actor)
    assert replay["delivery_replayed"] is True and _snapshot(repo) == prior


def test_task_scope_provider_outage_before_any_core_fact_keeps_e3_consistent(tmp_path):
    from openai import OpenAIError

    repo, actor, executor, runtime, calls = _runtime(tmp_path)

    class PreflightTaskAuditOutage(RecordedClient):
        def create(self, **kwargs):
            if kwargs["text"]["format"]["name"] == "odyssey_task_only_scope_v1":
                raise OpenAIError("synthetic prewrite Task scope outage")
            return super().create(**kwargs)

    executor.client = PreflightTaskAuditOutage(_provider_rows()[:3])
    prior = _snapshot(repo)
    result = runtime.execute_product(SOURCE, "p4-task-preflight-outage", "main", actor)
    assert result["status"] == "needs_attention"
    assert result["clarification_code"] == "FULL_SOURCE_PROVIDER_OR_CONTEXT_UNAVAILABLE"
    assert _snapshot(repo) == prior and calls == []
    assert runtime.execute_product(SOURCE, "p4-task-preflight-outage", "main", actor)[
        "delivery_replayed"
    ]


@pytest.mark.parametrize("refresh_fails", [False, True])
def test_three_independent_scopes_core_task_core_have_complete_real_readback(
    tmp_path, refresh_fails
):
    """N independent scopes share one E3 claim and no graph route disappears."""
    from odyssey_apps.tasks import TaskInterpretation, TaskOperation

    extra = "También he regado las plantas."
    whole = SOURCE + " " + extra
    repo, actor, executor, runtime, calls = _runtime(tmp_path)
    rows = _provider_rows()
    extra_core_rows = deepcopy(rows[4:9])

    def replace_literals(item):
        if isinstance(item, str):
            return item.replace(CORE, extra).replace("Me gusta correr por la tarde.", extra)
        if isinstance(item, dict):
            return {key: replace_literals(value) for key, value in item.items()}
        if isinstance(item, list):
            return [replace_literals(value) for value in item]
        return item

    extra_core_rows = replace_literals(extra_core_rows)
    route = deepcopy(rows[0])
    route["app_scopes"].append(
        {"capability": "core", "description": "independent fact", "depends_on_another_scope": False}
    )
    partition = {
        "full_source_quote": whole,
        "parts": [
            {"capability": "core", "source_quote": CORE + " "},
            {"capability": "tasks", "source_quote": TASK + " "},
            {"capability": "core", "source_quote": extra},
        ],
    }
    audit = {**_audit(), "full_source_quote": whole}
    rows = [route, partition, audit, *rows[3:9], *extra_core_rows]
    executor.client = RecordedClient(rows)
    seen = []

    def prepared(text, instant):
        assert text == TASK
        seen.append(("prepare", instant))
        return TaskInterpretation(
            text, TaskOperation.START_WORK_SESSION, task_reference="Preparar informe Atlas"
        ), None

    def delegated(text, locator, who, interpretation, temporal, instant):
        assert interpretation.operation is TaskOperation.START_WORK_SESSION and temporal is None
        assert seen == [("prepare", instant)]
        seen.append(("delegate", instant))
        return executor.task_delegate(text, locator, who)

    executor.independent_task_prepare = prepared
    executor.independent_task_delegate = delegated
    from odyssey_runtime.delivery_results import LocalDeliveryResultStore

    store = LocalDeliveryResultStore(
        runtime.conversation_root_resolver.resolve(actor.stable_user_id) / "delivery-results"
    )

    executor.operation_manifest_begin = lambda request, text, _actor, groups: (
        store.begin_operation_manifest(request, store.fingerprint(text, "main"), text, groups)
    )
    executor.operation_manifest_observe = lambda request, text, _actor, index, cap, receipt: (
        store.observe_operation_manifest(
            request,
            store.fingerprint(text, "main"),
            index,
            cap,
            receipt.status.value,
            receipt.affected_stable_note_ids,
        )
    )
    if refresh_fails:

        def fail_mid_scope_refresh(_ids):
            raise ValueError("synthetic unrelated index drift")

        executor.refresh_between_independent_scopes = fail_mid_scope_refresh
    result = runtime.execute_product(whole, "independent-three-verified", "main", actor)
    assert store.inspect_operation_manifest(
        "independent-three-verified", store.fingerprint(whole, "main")
    ) == {
        "manifest_present": True,
        "planned_operations": 3,
        "observed_operations": 3,
        "claim_state": "receipt_confirmed",
        "recovery_authorized": False,
    }
    if refresh_fails:
        assert result["status"] == "partial", result
        assert CORE in repo.read_text("self.md")
        assert extra not in repo.read_text("self.md")
        assert len(runtime.work_session_service.list_for_task("atlas-task")) == 1
        before = _snapshot(repo)
        assert (
            runtime.execute_product(whole, "independent-three-verified", "main", actor)[
                "delivery_replayed"
            ]
            is True
        )
        assert _snapshot(repo) == before
        return
    assert result["status"] == "completed", result
    assert [item["capability"] for item in result["execution_flow"]["routes"]] == [
        "core",
        "tasks",
        "core",
    ]
    assert executor.client.rows == []
    assert len(seen) == 2 and seen[0][1] == seen[1][1]
    assert len(calls) == 1
    source = repo.read_text("self.md")
    assert CORE in source and extra in source
    assert len(runtime.work_session_service.list_for_task("atlas-task")) == 1
    snapshot = _snapshot(repo)
    replay = runtime.execute_product(whole, "independent-three-verified", "main", actor)
    assert replay["delivery_replayed"] is True
    assert _snapshot(repo) == snapshot and len(seen) == 2 and len(calls) == 1


@pytest.mark.parametrize(
    "problem",
    [
        "router_missing",
        "router_reordered",
        "precheck_missing",
        "precheck_raises",
        "precheck_wrong_source",
    ],
)
def test_independent_scope_preflight_vetoes_before_first_core_write(tmp_path, problem):
    from odyssey_apps.tasks import TaskInterpretation, TaskOperation

    repo, actor, executor, runtime, calls = _runtime(tmp_path)
    rows = _provider_rows()
    if problem == "router_missing":
        rows[0]["app_scopes"] = rows[0]["app_scopes"][:1]
        # This is not a valid independent outer route; it may be rejected
        # immediately, without asking for any downstream source plan.
        executor.client = RecordedClient(rows)
        before = _snapshot(repo)
        outcome = runtime.execute_product(SOURCE, "independent-precheck-" + problem, "main", actor)
        assert outcome["status"] != "completed"
        assert _snapshot(repo) == before and calls == []
        return
    if problem == "router_reordered":
        rows[0]["app_scopes"].reverse()
    executor.client = RecordedClient(rows)
    before = _snapshot(repo)
    if problem == "precheck_missing":
        executor.independent_task_prepare = lambda _text, _instant: (
            TaskInterpretation(
                TASK, TaskOperation.START_WORK_SESSION, task_reference="Preparar informe Atlas"
            ),
            None,
        )
    elif problem == "precheck_raises":
        executor.independent_task_prepare = lambda _text, _instant: (_ for _ in ()).throw(
            ValueError("synthetic prewrite interpretation failure")
        )
        executor.independent_task_delegate = lambda *_: pytest.fail("must never execute")
    elif problem == "precheck_wrong_source":
        executor.independent_task_prepare = lambda _text, _instant: (
            TaskInterpretation(
                "wrong source", TaskOperation.START_WORK_SESSION, task_reference="wrong"
            ),
            None,
        )
        executor.independent_task_delegate = lambda *_: pytest.fail("must never execute")
    result = runtime.execute_product(SOURCE, "independent-precheck-" + problem, "main", actor)
    assert result["status"] == "needs_attention", result
    assert calls == [] and _snapshot(repo) == before


def test_four_scopes_later_task_precheck_vetoes_all_prior_core_writes(tmp_path):
    """A bad fourth group is caught before either preceding Core WRITE."""
    repo, actor, executor, runtime, calls = _runtime(tmp_path)
    pieces = [CORE + " ", TASK + " ", "He preparado café. ", "Termina esa sesión."]
    source = "".join(pieces)
    route = _outer_route()
    route["app_scopes"].extend(
        [
            {"capability": "core", "description": "coffee", "depends_on_another_scope": False},
            {"capability": "tasks", "description": "stop", "depends_on_another_scope": False},
        ]
    )
    # Independent auditor statements are frozen evidence; the actual final
    # scope still needs its own task-only and typed Task interpretation checks.
    proposal = {
        "full_source_quote": source,
        "parts": [
            {"capability": cap, "source_quote": quote}
            for cap, quote in zip(("core", "tasks", "core", "tasks"), pieces, strict=True)
        ],
    }
    executor.client = RecordedClient(
        [
            route,
            proposal,
            {**_audit(), "full_source_quote": source},
            {"only_task_semantics": True, "exactly_one_operation": True, "source_quote": TASK},
            {
                "only_task_semantics": False,
                "exactly_one_operation": True,
                "source_quote": pieces[-1],
            },
        ]
    )
    before = _snapshot(repo)
    outcome = runtime.execute_product(source, "independent-four-prewrite-veto", "main", actor)
    assert outcome["status"] == "needs_attention", outcome
    assert _snapshot(repo) == before and calls == []
    assert executor.client.rows == []
