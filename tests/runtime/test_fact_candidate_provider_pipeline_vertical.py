"""Original Router v3 -> Temporal -> Core 5.6 -> chat preview, offline SDK.

The provider wrappers are REAL unchanged production adapter classes. Their
SDK replies are frozen previously completed model responses, never network
calls. Only disposable user roots and Markdown Notes are used.
"""

from __future__ import annotations

import json

import pytest

from benchmarks.fact_candidate_core_live import run_dependent_live
from benchmarks.fact_candidate_v2_live import run_remaining
from odyssey_apps.fact_candidates import OpenAIFactCandidateRouter
from odyssey_core.candidate_dependency_admission import (
    DependentOperationJournal,
    execute_dependent_core_once,
)
from odyssey_core.experimental_luna_planning import OpenAILunaExperimentalPlanner
from odyssey_core.temporal_interpretation import OpenAITemporalInterpreter
from odyssey_runtime.dependent_candidate_pipeline import DependentCandidatePipeline
from odyssey_runtime.dependent_candidate_preview import DependentCandidateChatPreview
from tests.core.test_candidate_dependencies_observed import _observed
from tests.core.test_reference_preflight import EmptyIndex, UnresolvedReasoner
from tests.runtime.test_candidate_pending_state import NOW
from tests.runtime.test_fact_candidate_dependent_chat_preview_vertical import _harness
from tests.runtime.test_fact_candidate_planning_vertical import _exact_date, _sdk_fake
from tests.runtime.test_fact_candidate_semantic_luna_vertical import CLOCK, SCHEMA
from tests.runtime.test_temporal_user_path_e2e import ConstantEmbedder


def _model_pipeline(case: str):
    """Script REAL stored provider JSON through unchanged SDK-backed adapters."""
    source, _ = _observed(case)
    router_file = next(run_remaining.RESULTS.glob(f"*--{case}.json"))
    router_raw = json.loads(json.loads(router_file.read_text())["raw_model_response"])
    router_sdk, router_calls = _sdk_fake(router_raw)
    router = OpenAIFactCandidateRouter(router_sdk, prompt_revision="v3")
    temporal_payload = {
        "mentions": (
            [_exact_date("ayer", "2026-10-03"), _exact_date("hoy", "2026-10-04")]
            if case == "F26"
            else []
        )
    }
    temporal_sdk, temporal_calls = _sdk_fake(temporal_payload)
    temporal = OpenAITemporalInterpreter(temporal_sdk, CLOCK)
    used = []

    def make_core(domain):
        unit = f"candidate-{len(used) + 1}"
        reply_file = next(run_dependent_live.RECEIPTS.glob(f"*--{case}--{unit}.json"))
        raw = json.loads(json.loads(reply_file.read_text())["raw_model_response"])
        sdk, calls = _sdk_fake(raw)
        used.append(calls)
        model = OpenAILunaExperimentalPlanner(
            sdk,
            SCHEMA,
            CLOCK,
            domain_interpretation=domain,
            max_output_tokens=1280 if case == "F26" else 2048,
        )
        return model

    pipeline = DependentCandidatePipeline(router, temporal, make_core)
    return source, pipeline, router_calls, temporal_calls, used


@pytest.mark.parametrize("case", ("F23", "F26"))
def test_real_sdk_adapter_boundary_assembles_independent_core_plans(case):
    source, pipeline, router_calls, temporal_calls, core_calls = _model_pipeline(case)
    prepared = pipeline.prepare(source)
    assert prepared.source == source
    assert len(prepared.context.candidates) == len(prepared.plans) == 2
    assert len(router_calls) == 1
    assert router_calls[0]["model"] == "gpt-6-luna"
    assert router_calls[0]["reasoning"] == {"effort": "low"}
    assert len(temporal_calls) == (1 if case == "F26" else 0)
    assert len(core_calls) == 2
    for index, calls in enumerate(core_calls, 1):
        assert len(calls) == 1
        assert calls[0]["model"] == "gpt-5.6-luna"
        assert calls[0]["reasoning"] == {"effort": "low"}
        assert calls[0]["store"] is False
        assert (
            calls[0]["input"][1]["content"]
            == run_dependent_live._request(case, f"candidate-{index}")[1]
        )


@pytest.mark.parametrize("case,existing_report", [("F23", False), ("F26", True), ("F26", False)])
def test_full_existing_sdk_routers_and_core_writers_through_private_chat(
    case, existing_report, tmp_path
):
    source, pipeline, router_calls, temporal_calls, core_calls = _model_pipeline(case)
    source2, repo, root, work, _executor, runtime = _harness(
        case, tmp_path, existing_report=existing_report
    )
    assert source2 == source
    executor_calls = []
    _, _, context_index = _prepare_private_context(repo, tmp_path)

    def execute_with_models(message, outer_id, actor_root):
        executor_calls.append(message)
        prepared = pipeline.prepare(message)
        return execute_dependent_core_once(
            logical_operation_key=outer_id,
            state_root=actor_root,
            source=message,
            context=prepared.context,
            independent_plans=prepared.plans,
            repository=repo,
            schema=SCHEMA,
            context_index=context_index,
            semantic_index=EmptyIndex(),
            embedder=ConstantEmbedder(),
            contextual_reasoner=UnresolvedReasoner(),
            actor="synthetic-provider-pipeline",
            now=NOW,
            context_limit=5,
            request_id_factory=lambda: "core-" + outer_id,
        )

    request_id = f"web-{case}-whole-provider-pipeline"
    first = DependentCandidateChatPreview(runtime(), execute_with_models).execute(
        source, request_id, "main"
    )
    assert first["status"] == "completed"
    assert first["request_id"] == request_id
    assert len(first["actions"]) == 2
    assert len(router_calls) == 1
    assert len(temporal_calls) == (1 if case == "F26" else 0)
    assert len(core_calls) == 2
    assert DependentOperationJournal(root, repo).inspect(request_id).state == "completed"
    before = {path: repo.read_text(path) for path in repo.list_markdown_paths()}
    # A new runtime instance after restart delivers original completion
    # without an additional call to Router, Temporal, Core or Markdown.
    second = DependentCandidateChatPreview(runtime(), execute_with_models).execute(
        source, request_id, "main"
    )
    assert second["delivery_replayed"] is True
    assert second["status"] == "completed"
    assert len(executor_calls) == 1
    assert len(router_calls) == 1
    assert len(temporal_calls) == (1 if case == "F26" else 0)
    assert len(core_calls) == 2
    assert {path: repo.read_text(path) for path in repo.list_markdown_paths()} == before


def test_partial_operation_retry_never_recalls_an_sdk_model(tmp_path, monkeypatch):
    import odyssey_core.application as application
    from odyssey_core.application import ActionResult, ActionStatus
    from odyssey_runtime.dependent_candidate_preview import DependentCandidateChatPreview

    source, pipeline, router_calls, temporal_calls, core_calls = _model_pipeline("F23")
    _, repo, root, _, _, runtime = _harness("F23", tmp_path)
    _, _, context_index = _prepare_private_context(repo, tmp_path)
    original = application._execute_write

    def fail_second(action_index, *args, **kwargs):
        if action_index == 1:
            return ActionResult(action_index, "write", ActionStatus.FAILED)
        return original(action_index, *args, **kwargs)

    monkeypatch.setattr(application, "_execute_write", fail_second)

    def executor(message, outer_id, actor_root):
        prepared = pipeline.prepare(message)
        return execute_dependent_core_once(
            logical_operation_key=outer_id,
            state_root=actor_root,
            source=message,
            context=prepared.context,
            independent_plans=prepared.plans,
            repository=repo,
            schema=SCHEMA,
            context_index=context_index,
            semantic_index=EmptyIndex(),
            embedder=ConstantEmbedder(),
            contextual_reasoner=UnresolvedReasoner(),
            actor="isolated",
            now=NOW,
            context_limit=5,
            request_id_factory=lambda: "core-" + outer_id,
        )

    rid = "web-F23-model-safety"
    first = DependentCandidateChatPreview(runtime(), executor).execute(source, rid, "main")
    assert first["status"] == "partial"
    assert len(router_calls) == 1
    assert len(core_calls) == 2
    saved = {path: repo.read_text(path) for path in repo.list_markdown_paths()}
    monkeypatch.setattr(application, "_execute_write", original)
    second = DependentCandidateChatPreview(runtime(), executor).execute(source, rid, "main")
    assert second["status"] == "needs_attention"
    assert len(router_calls) == 1
    assert len(core_calls) == 2
    assert {path: repo.read_text(path) for path in repo.list_markdown_paths()} == saved


def _prepare_private_context(repo, tmp_path):
    from odyssey_core.context import ContextIndex

    # Built in disposable test fixture only.
    context = ContextIndex(tmp_path / "private-context.sqlite3")
    context.rebuild(repo, SCHEMA, ConstantEmbedder())
    return repo, None, context


@pytest.mark.parametrize("case", ["F19", "F20"])
def test_corrections_and_conditionals_are_not_sent_to_core_planner(case):
    source, _ = _observed(case)
    router_file = next(run_remaining.RESULTS.glob(f"*--{case}.json"))
    raw = json.loads(json.loads(router_file.read_text())["raw_model_response"])
    router_sdk, router_calls = _sdk_fake(raw)
    temporal_sdk, temporal_calls = _sdk_fake({"mentions": []})
    core_used = []

    def core_factory(domain):
        core_used.append(domain)
        pytest.fail("Unsafe Router condition/correction reached Core model")

    pipeline = DependentCandidatePipeline(
        OpenAIFactCandidateRouter(router_sdk, prompt_revision="v3"),
        OpenAITemporalInterpreter(temporal_sdk, CLOCK),
        core_factory,
    )
    with pytest.raises(ValueError):
        pipeline.prepare(source)
    assert len(router_calls) == 1
    assert not temporal_calls
    assert not core_used


def test_private_preview_refuses_authenticated_actor_without_a_matching_vault(tmp_path):
    from odyssey_core.identity_boundary import AuthenticatedActorContext

    source, repo, root, calls, executor, runtime = _harness("F23", tmp_path)
    preview = DependentCandidateChatPreview(runtime(), executor)
    with pytest.raises(ValueError, match="actor-bound vault selection"):
        preview.execute(
            source,
            "web-other-user",
            "main",
            authenticated_actor=AuthenticatedActorContext("550e8400-e29b-41d4-a716-446655440000"),
        )
    assert calls == []
    assert not (root / "dependent-operations").exists()


def test_same_outer_message_id_is_root_isolated_between_two_local_instances(tmp_path):
    """One actor-local state root cannot replay another instance's Note mutation."""
    a = tmp_path / "instance-alpha"
    b = tmp_path / "instance-beta"
    a.mkdir()
    b.mkdir()
    source_a, vault_a, root_a, calls_a, executor_a, runtime_a = _harness("F23", a)
    source_b, vault_b, root_b, calls_b, executor_b, runtime_b = _harness("F23", b)
    assert source_a == source_b
    request_id = "web-same-on-two-isolated-local-instances"
    first = DependentCandidateChatPreview(runtime_a(), executor_a).execute(
        source_a, request_id, "main"
    )
    second = DependentCandidateChatPreview(runtime_b(), executor_b).execute(
        source_b, request_id, "main"
    )
    assert first["status"] == second["status"] == "completed"
    assert len(calls_a) == len(calls_b) == 1
    assert root_a != root_b and vault_a.root != vault_b.root
    assert DependentOperationJournal(root_a, vault_a).inspect(request_id).state == "completed"
    assert DependentOperationJournal(root_b, vault_b).inspect(request_id).state == "completed"
    assert (
        vault_a.read_text("Odyssey.md").count("<!-- odyssey:fact request=inner-" + request_id) == 2
    )
    assert (
        vault_b.read_text("Odyssey.md").count("<!-- odyssey:fact request=inner-" + request_id) == 2
    )


def test_temporal_missing_original_role_stops_before_any_core_planning():
    source, pipeline, router_calls, temporal_calls, core_calls = _model_pipeline("F26")
    missing, calls = _sdk_fake({"mentions": [_exact_date("ayer", "2026-10-03")]})
    pipeline._temporal = OpenAITemporalInterpreter(missing, CLOCK)
    with pytest.raises(ValueError, match="Unresolved or approximate"):
        pipeline.prepare(source)
    assert len(router_calls) == 1
    assert len(calls) == 1
    assert core_calls == []


def test_private_preview_blocks_model_rerun_after_first_write_partial(tmp_path):
    """The retry is rejected before any new Router/Temporal provider expense."""
    source, repo, root, calls, executor, runtime = _harness("F23", tmp_path)
    # Real original dependent Core plans; the first write is deliberately
    # interrupted before the second by the already tested recovery flow.
    import odyssey_core.application as application
    from odyssey_core.application import ActionResult, ActionStatus

    # F23 is not a temporal case, so the Core write failure is enough to
    # establish the durable replay refusal before provider invocation.
    original = application._execute_write

    def stop_second(action_index, *args, **kwargs):
        if action_index == 1:
            return ActionResult(action_index, "write", ActionStatus.FAILED)
        return original(action_index, *args, **kwargs)

    # Avoid writing to Notes outside the disposable vault.
    from unittest.mock import patch

    with patch.object(application, "_execute_write", stop_second):
        first = DependentCandidateChatPreview(runtime(), executor).execute(
            source, "web-partial-no-new-model", "main"
        )
    assert first["status"] == "partial"
    assert len(calls) == 1
    before = {path: repo.read_text(path) for path in repo.list_markdown_paths()}
    retry = DependentCandidateChatPreview(runtime(), executor).execute(
        source, "web-partial-no-new-model", "main"
    )
    assert retry["status"] == "needs_attention"
    assert len(calls) == 1
    assert {path: repo.read_text(path) for path in repo.list_markdown_paths()} == before
