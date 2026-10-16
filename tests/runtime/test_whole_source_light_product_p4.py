"""P4 production module integration; frozen authentic review and real Core Writer.

The only mocks are the provider OUTPUTS and clock, never canonical Markdown,
identity lookup, Core plan execution, or E3 delivery replay. Actual GPT/n8n/UI
integration remains an independent approval gate.
"""

from __future__ import annotations

import copy
import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from odyssey_apps.schema_extensions import compose_application_schema
from odyssey_apps.tasks import TASK_SCHEMA_EXTENSION
from odyssey_core import create_entity
from odyssey_core.application import ApplicationResult, ApplicationStatus
from odyssey_core.context import ContextIndex
from odyssey_core.identity_boundary import AuthenticatedActorContext, SelfBindingRepository
from odyssey_core.local_conversations import ConversationRootResolver
from odyssey_core.notes import parse_note
from odyssey_core.semantic import SemanticEntityIndex
from odyssey_core.storage import VaultRepository
from odyssey_runtime.composition import RuntimeComposition
from odyssey_runtime.whole_source_light import WholeSourceLightExecutor
from tests.core.test_reference_preflight import UnresolvedReasoner
from tests.runtime.test_temporal_user_path_e2e import ConstantEmbedder

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = compose_application_schema(
    json.loads((ROOT / "config/note-schema.json").read_text()), (TASK_SCHEMA_EXTENSION,)
)
POC = ROOT / "benchmarks/application_router/light_router_poc_20261016"


def _actual_snapshot(name: str):
    original = next(
        x for x in json.loads((POC / "observations.json").read_text())["cases"] if x["case"] == name
    )
    reviewed = next(
        x
        for x in json.loads((POC / "p2_integration_receipts.json").read_text())["results"]
        if x["case"] == name
    )
    return (
        original["original_source"],
        original["router"],
        original["shared_plan"],
        reviewed["review"],
    )


class RecordedClient:
    def __init__(self, rows):
        self.rows = list(rows)
        self.responses = self
        self.calls = []

    def create(self, **kwargs):
        assert kwargs["store"] is False
        assert kwargs["text"]["format"]["strict"] is True
        self.calls.append(kwargs["text"]["format"]["name"])
        assert self.rows, "Unplanned model call"
        return SimpleNamespace(status="completed", output_text=json.dumps(self.rows.pop(0)))


def _fixture(tmp_path: Path, *, task_delegate=None, incremental_indexes=False):
    vault = tmp_path / "vault"
    state = tmp_path / "state"
    vault.mkdir()
    state.mkdir()
    repo = VaultRepository(vault)
    create_entity(
        repo,
        SCHEMA,
        path="self.md",
        entity_id="self-note",
        metadata={"name": "Persona autenticada", "type": "person"},
        content="",
        actor="fixture",
        now="2026-10-16T10:00:00+02:00",
    )
    actor = AuthenticatedActorContext(str(uuid4()))
    bindings = SelfBindingRepository(state, repo, SCHEMA)
    bindings.bind(actor.stable_user_id, "self-note")
    embedder = ConstantEmbedder()
    context = ContextIndex(tmp_path / "context.sqlite3")
    semantic = SemanticEntityIndex(tmp_path / "semantic.sqlite3")
    context.rebuild(repo, SCHEMA, embedder)
    semantic.rebuild(repo, SCHEMA, embedder)

    refresh_stats = {"incremental": 0, "rebuild": 0}

    def refresh(ids):
        assert ids
        if incremental_indexes:
            from odyssey_core.context import ContextIndexError
            from odyssey_core.semantic import SemanticIndexError
            from odyssey_core.temporal import materialized_day_link_index_ids

            expanded = tuple(
                dict.fromkeys((*ids, *materialized_day_link_index_ids(repo, SCHEMA, tuple(ids))))
            )
            try:
                context.refresh_notes(repo, SCHEMA, embedder, note_ids=expanded)
                semantic.refresh_notes(repo, SCHEMA, embedder, note_ids=expanded)
                refresh_stats["incremental"] += 1
                return
            except (ContextIndexError, SemanticIndexError, ValueError):
                # Exactly the same fallback used by production composition.
                pass
        refresh_stats["rebuild"] += 1
        context.rebuild(repo, SCHEMA, embedder)
        semantic.rebuild(repo, SCHEMA, embedder)

    service = WholeSourceLightExecutor(
        repo,
        SCHEMA,
        context,
        semantic,
        embedder,
        UnresolvedReasoner(),
        bindings,
        refresh,
        task_delegate or (lambda *_: (_ for _ in ()).throw(AssertionError("Tasks unexpected"))),
        RecordedClient([]),
        now=lambda: datetime.fromisoformat("2026-10-16T15:30:00+02:00"),
    )
    service.refresh_stats = refresh_stats
    runtime = RuntimeComposition(
        core_execute=lambda *_args: (_ for _ in ()).throw(AssertionError("Legacy Core unexpected")),
        refresh_indexes=lambda: None,
        hybrid_candidate_execute=service,
        full_source_mutation_guard=True,
        conversation_root_resolver=ConversationRootResolver(state),
    )
    return repo, actor, service, runtime


def _speaker(source, proposal, *, role="self_participant", assertion="asserted", base=0):
    return {
        "facts": [
            {
                "ordinal": i + base,
                "role": role,
                "assertion": assertion,
                "source_quote": f["source_evidence"],
            }
            for i, f in enumerate(proposal["facts"])
        ]
    }


def test_production_p4_real_writer_and_e3_replay_from_authentic_model_snapshot(tmp_path):
    source, router, plan, review = _actual_snapshot("maya_simple")
    repo, actor, service, runtime = _fixture(tmp_path)
    service.client = RecordedClient(
        [router, plan, review, _speaker(source, plan, base=1), _speaker(source, plan)]
    )
    payload = (source, "p4-prod-real-md", "main", actor)
    result = runtime.execute_product(*payload)
    assert result["status"] == "completed", result
    assert service.client.calls == [
        "odyssey_light_capability_route_v1",
        "odyssey_light_shared_semantic_plan_v1",
        "odyssey_p2_source_coverage_v1",
        "odyssey_speaker_full_A",
        "odyssey_speaker_full_B",
    ]
    all_notes = [parse_note(repo.read_text(p)) for p in repo.list_markdown_paths()]
    dated = [n for n in all_notes if n.metadata["type"] == "calendar_day"]
    asserted = [n for n in dated if n.metadata["id"] == "date:2026-10-15"]
    assert len(asserted) == 1
    assert "odyssey:fact request=p4-prod-real-md-day-2026-10-15" in asserted[0].content
    assert "(yo:" in asserted[0].content
    assert all(not n.content for n in dated if n.metadata["id"] != "date:2026-10-15")
    before = {p: repo.read_text(p) for p in repo.list_markdown_paths()}
    replay = runtime.execute_product(*payload)
    assert replay["delivery_replayed"] is True
    assert {p: repo.read_text(p) for p in repo.list_markdown_paths()} == before


def test_route_task_only_reuses_one_task_delegate_not_source_model_planner(tmp_path):
    calls = []

    def delegate(source, request, actor):
        calls.append((source, request, actor.stable_user_id))
        return ApplicationResult(request, ApplicationStatus.COMPLETED, (), ())

    repo, actor, service, runtime = _fixture(tmp_path, task_delegate=delegate)
    service.client = RecordedClient(
        [
            {
                "capabilities": ["tasks"],
                "interpretation": "joint",
                "reason": "single",
                "app_scopes": [],
            },
            {
                "only_task_semantics": True,
                "exactly_one_operation": True,
                "source_quote": "Inicia la sesión de trabajo de una tarea.",
            },
        ]
    )
    result = runtime.execute_product(
        "Inicia la sesión de trabajo de una tarea.", "task-only-1", "main", actor
    )
    assert result["status"] == "completed"
    assert len(calls) == 1 and calls[0][2] == actor.stable_user_id
    assert service.client.calls == [
        "odyssey_light_capability_route_v1",
        "odyssey_task_only_scope_v1",
    ]
    assert len(repo.list_markdown_paths()) == 1


@pytest.mark.parametrize("invalid", ["unsupported", "missing_review", "wrong_speaker"])
def test_product_route_abstains_without_mutating_on_bad_model_evidence(tmp_path, invalid):
    source, router, plan, review = _actual_snapshot("maya_simple")
    router, plan, review = copy.deepcopy(router), copy.deepcopy(plan), copy.deepcopy(review)
    if invalid == "unsupported":
        plan["unresolved"] = ["ambiguous"]
    elif invalid == "missing_review":
        review["facts"].clear()
    else:
        role = "other"
    a = _speaker(source, plan)
    b = _speaker(source, plan)
    if invalid == "wrong_speaker":
        b = _speaker(source, plan, role=role)
    repo, actor, service, runtime = _fixture(tmp_path)
    service.client = RecordedClient([router, plan, review, a, b])
    before = {p: repo.read_text(p) for p in repo.list_markdown_paths()}
    result = runtime.execute_product(source, "unsafe-" + invalid, "main", actor)
    assert result["status"] == "needs_attention"
    assert {p: repo.read_text(p) for p in repo.list_markdown_paths()} == before


@pytest.mark.parametrize("scenario", ["maya_pronoun", "maite_cross_app", "two_dates"])
def test_product_p4_multi_fact_or_cross_task_authentic_snapshot_and_replay(tmp_path, scenario):
    source, router, plan, review = _actual_snapshot(scenario)
    repo, actor, service, runtime = _fixture(tmp_path)
    replies = [router, plan]
    if scenario == "maite_cross_app":
        replies.append(
            {
                "only_new_task_creations": True,
                "no_work_session_or_lifecycle_transition": True,
                "source_quote": source,
            }
        )
    replies.extend([review, _speaker(source, plan, base=1), _speaker(source, plan)])
    service.client = RecordedClient(replies)
    delivery = "p4-fresh-" + scenario
    result = runtime.execute_product(source, delivery, "main", actor)
    assert result["status"] == "completed", result
    all_notes = [parse_note(repo.read_text(p)) for p in repo.list_markdown_paths()]
    asserted = [note for note in all_notes if "odyssey:fact request=" + delivery in note.content]
    assert len(asserted) >= 2, (scenario, result)
    assert len(set(n.metadata["id"] for n in all_notes)) == len(all_notes)
    if scenario == "maite_cross_app":
        assert len([n for n in all_notes if n.metadata["type"] == "task"]) == 1
        assert any("(yo:" in note.content for note in asserted)
    before = {p: repo.read_text(p) for p in repo.list_markdown_paths()}
    again = runtime.execute_product(source, delivery, "main", actor)
    assert again["delivery_replayed"] is True
    assert {p: repo.read_text(p) for p in repo.list_markdown_paths()} == before


@pytest.mark.parametrize(
    "scope",
    [
        {
            "only_task_semantics": False,
            "exactly_one_operation": True,
            "source_quote": "Inicia la sesión. Y conocí a Sara.",
        },
        {
            "only_task_semantics": True,
            "exactly_one_operation": False,
            "source_quote": "Inicia la sesión. Y conocí a Sara.",
        },
        {
            "only_task_semantics": True,
            "exactly_one_operation": True,
            "source_quote": "Inicia la sesión.",
        },
    ],
)
def test_task_only_source_review_rejects_hidden_core_fact_or_multiple_operations(tmp_path, scope):
    called = []
    source = "Inicia la sesión. Y conocí a Sara."

    def delegate(*_):
        called.append(True)
        raise AssertionError("Unsafe Task delegation")

    repo, actor, service, runtime = _fixture(tmp_path, task_delegate=delegate)
    service.client = RecordedClient(
        [
            {
                "capabilities": ["tasks"],
                "interpretation": "joint",
                "reason": "single",
                "app_scopes": [],
            },
            scope,
        ]
    )
    before = {p: repo.read_text(p) for p in repo.list_markdown_paths()}
    result = runtime.execute_product(source, "hidden-core-1", "main", actor)
    assert result["status"] == "needs_attention" and called == []
    assert {p: repo.read_text(p) for p in repo.list_markdown_paths()} == before


def test_mixed_task_scope_cannot_smuggle_work_session_as_task_creation(tmp_path):
    source, router, plan, _ = _actual_snapshot("maite_cross_app")
    repo, actor, service, runtime = _fixture(tmp_path)
    service.client = RecordedClient(
        [
            router,
            plan,
            {
                "only_new_task_creations": False,
                "no_work_session_or_lifecycle_transition": False,
                "source_quote": source,
            },
        ]
    )
    before = {p: repo.read_text(p) for p in repo.list_markdown_paths()}
    result = runtime.execute_product(source, "unsafe-mixed-work-session", "main", actor)
    assert result["status"] == "needs_attention"
    assert {p: repo.read_text(p) for p in repo.list_markdown_paths()} == before


def test_product_p4_flag_forbids_prod_storage_without_any_side_effect(monkeypatch, tmp_path):
    from odyssey_runtime.composition import build_runtime_from_environment

    monkeypatch.setenv("ODYSSEY_LIGHT_SOURCE_V1", "1")
    monkeypatch.setenv("ODYSSEY_VAULT_ROOT", "/data/odyssey/vault")
    monkeypatch.setenv("ODYSSEY_RUNTIME_ROOT", str(tmp_path / "scratch-runtime"))
    monkeypatch.setenv("ODYSSEY_STATE_ROOT", str(tmp_path / "scratch-state"))
    monkeypatch.setenv("ODYSSEY_PENDING_ROOT", str(tmp_path / "scratch-pending"))
    with pytest.raises(ValueError, match="PROD storage"):
        build_runtime_from_environment()
    assert not any(tmp_path.iterdir()), "Guard must run before creating state or index files"


def test_p4_reports_only_existing_bounded_browser_progress_stages(tmp_path):
    source, router, plan, review = _actual_snapshot("maya_simple")
    repo, actor, service, runtime = _fixture(tmp_path)
    stages = []
    service.progress = lambda stage, payload: stages.append((stage, payload))
    service.client = RecordedClient(
        [router, plan, review, _speaker(source, plan, base=1), _speaker(source, plan)]
    )
    response = runtime.execute_product(source, "p4-stage-evidence", "main", actor)
    assert response["status"] == "completed"
    assert [name for name, _ in stages] == [
        "routing.started",
        "routing.ready",
        "planner.started",
        "planner.ready",
        "action.write.started",
    ]
    assert stages[1][1] == {"route_count": 1}
    assert all(not data or set(data) == {"route_count"} for _, data in stages)
    runtime.execute_product(source, "p4-stage-evidence", "main", actor)
    assert len(stages) == 5, "Replay cannot invent new progress milestones"
    assert any(
        parse_note(repo.read_text(path)).metadata["type"] == "calendar_day"
        for path in repo.list_markdown_paths()
    )


def test_full_source_preflight_prevents_earlier_core_write_when_last_task_unsupported(tmp_path):
    """A late Task with no date must not leave the earlier dated event persisted."""
    source, route, plan, review = _actual_snapshot("maite_cross_app")
    plan, review = copy.deepcopy(plan), copy.deepcopy(review)
    assert plan["facts"][-1]["kind"] == "task"
    plan["facts"][-1]["date"] = None
    review["facts"][-1]["date"] = None
    repo, actor, service, runtime = _fixture(tmp_path)
    service.client = RecordedClient(
        [
            route,
            plan,
            {
                "only_new_task_creations": True,
                "no_work_session_or_lifecycle_transition": True,
                "source_quote": source,
            },
            review,
            _speaker(source, plan, base=1),
            _speaker(source, plan),
        ]
    )
    before = {p: repo.read_text(p) for p in repo.list_markdown_paths()}
    response = runtime.execute_product(source, "late-unsupported-task", "main", actor)
    assert response["status"] == "needs_attention", response
    assert {p: repo.read_text(p) for p in repo.list_markdown_paths()} == before
    replay = runtime.execute_product(source, "late-unsupported-task", "main", actor)
    assert replay["delivery_replayed"] is True
