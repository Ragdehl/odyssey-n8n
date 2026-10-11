"""Opt-in runtime chat delivery with actual frozen GPT-5.6 dependent plans.

Uses existing external browser request IDs, existing actor-local delivery
cache, and ordinary Core physical writes only in disposable Markdown.
The normal /execute HTTP route remains unmodified and cannot invoke preview.
"""

from __future__ import annotations

import hashlib

import pytest

import odyssey_core.application as core_application
from odyssey_core.application import ActionResult, ActionStatus, ApplicationStatus
from odyssey_core.candidate_dependency_admission import (
    DependentOperationJournal,
    execute_dependent_core_once,
)
from odyssey_core.local_conversations import ConversationRootResolver
from odyssey_runtime.composition import RuntimeComposition
from odyssey_runtime.dependent_candidate_preview import DependentCandidateChatPreview
from tests.core.test_reference_preflight import EmptyIndex, UnresolvedReasoner
from tests.runtime.test_candidate_pending_state import NOW
from tests.runtime.test_fact_candidate_dependency_global_coverage_vertical import _setup
from tests.runtime.test_fact_candidate_dependent_actual_core_vertical import _vault
from tests.runtime.test_fact_candidate_semantic_luna_vertical import SCHEMA
from tests.runtime.test_temporal_user_path_e2e import ConstantEmbedder


def _harness(case, tmp_path, *, existing_report=True):
    source, context, plans, *_ = _setup(case)
    repo, index = _vault(tmp_path, existing_report=existing_report)
    state = tmp_path / "state"
    state.mkdir()
    actor_root = ConversationRootResolver(state).resolve("odyssey-runtime")
    actor_root.mkdir(mode=0o700, parents=True)
    calls = []

    def executor(text, request_id, root):
        calls.append((text, request_id, root))
        assert text == source
        assert root == actor_root
        return execute_dependent_core_once(
            logical_operation_key=request_id,
            state_root=root,
            source=text,
            context=context,
            independent_plans=plans,
            repository=repo,
            schema=SCHEMA,
            context_index=index,
            semantic_index=EmptyIndex(),
            embedder=ConstantEmbedder(),
            contextual_reasoner=UnresolvedReasoner(),
            actor="preview-isolated",
            now=NOW,
            context_limit=5,
            request_id_factory=lambda: f"inner-{request_id}",
        )

    def runtime():
        # This is the REAL runtime composition class, but the experimental
        # route is never bound to its normal product execution or HTTP server.
        return RuntimeComposition(
            core_execute=lambda *_: pytest.fail("Ordinary chat must not run"),
            refresh_indexes=lambda: None,
            conversation_root_resolver=ConversationRootResolver(state),
            vault_repository=repo,
            canonical_schema=SCHEMA,
        )

    return source, repo, actor_root, calls, executor, runtime


@pytest.mark.parametrize("case,existing_report", [("F23", False), ("F26", True), ("F26", False)])
def test_real_core_frozen_plans_create_cached_chat_delivery_and_restart_replay(
    case, existing_report, tmp_path
):
    source, repo, actor_root, calls, executor, runtime = _harness(
        case, tmp_path, existing_report=existing_report
    )
    request_id = f"web-{case}-1111"
    first = DependentCandidateChatPreview(runtime(), executor).execute(source, request_id, "main")
    assert first["status"] == "completed"
    assert first["request_id"] == request_id
    assert first["actions"] and len(first["actions"]) == 2
    assert len(calls) == 1
    assert DependentOperationJournal(actor_root, repo).inspect(request_id).state == "completed"
    before = {p: repo.read_text(p) for p in repo.list_markdown_paths()}

    # Simulated runtime reboot: a newly composed runtime reads durable
    # cache and does not even call the Core executor again.
    replay = DependentCandidateChatPreview(runtime(), executor).execute(source, request_id, "main")
    assert replay["status"] == "completed"
    assert replay["delivery_replayed"] is True
    assert len(calls) == 1
    assert {p: repo.read_text(p) for p in repo.list_markdown_paths()} == before
    assert len(list((actor_root / "dependent-preview-deliveries").glob("*.json"))) == 1


@pytest.mark.parametrize("case", ["F23", "F26"])
def test_runtime_preview_second_action_failure_survives_restart_without_replay(
    case, tmp_path, monkeypatch
):
    source, repo, actor_root, calls, executor, runtime = _harness(case, tmp_path)
    original = core_application._execute_write

    def interrupt_second(action_index, *args, **kwargs):
        if action_index == 1:
            return ActionResult(
                action_index,
                "write",
                ActionStatus.FAILED,
                reason="test-injected-second-action-outage",
            )
        return original(action_index, *args, **kwargs)

    monkeypatch.setattr(core_application, "_execute_write", interrupt_second)
    rid = f"web-{case}-partial"
    first = DependentCandidateChatPreview(runtime(), executor).execute(source, rid, "main")
    assert first["status"] == "partial"
    assert DependentOperationJournal(actor_root, repo).inspect(rid).state == "partial"
    before = {p: repo.read_text(p) for p in repo.list_markdown_paths()}

    monkeypatch.setattr(core_application, "_execute_write", original)
    replay = DependentCandidateChatPreview(runtime(), executor).execute(source, rid, "main")
    assert replay["status"] == "needs_attention"
    assert replay["clarification_code"] == "CANDIDATE_COVERAGE_REVIEW_REQUIRED"
    assert replay["affected_stable_note_ids"] == []
    assert replay["actions"] == []
    assert {p: repo.read_text(p) for p in repo.list_markdown_paths()} == before
    assert len(calls) == 2  # attempted but blocked by Core durable admission


def test_stale_success_cache_is_not_replayed_without_core_operation_proof(tmp_path):
    source, repo, actor_root, calls, executor, runtime = _harness("F23", tmp_path)
    request = "web-f23-cached"
    preview = DependentCandidateChatPreview(runtime(), executor)
    first = preview.execute(source, request, "main")
    assert first["status"] == "completed"
    assert len(calls) == 1
    record = (
        actor_root
        / "dependent-operations"
        / (hashlib.sha256(request.encode()).hexdigest() + ".json")
    )
    record.unlink()
    with pytest.raises(Exception, match="canonical operation proof"):
        DependentCandidateChatPreview(runtime(), executor).execute(source, request, "main")
    assert len(calls) == 1


def test_wrong_source_with_same_outer_id_is_rejected_even_if_completed(tmp_path):
    source, repo, actor_root, calls, executor, runtime = _harness("F23", tmp_path)
    request = "web-collision"
    preview = DependentCandidateChatPreview(runtime(), executor)
    assert preview.execute(source, request, "main")["status"] == "completed"
    with pytest.raises(Exception, match="bound to another delivery"):
        DependentCandidateChatPreview(runtime(), executor).execute(
            source.replace("Temporal", "Calendario"), request, "main"
        )
    assert len(calls) == 1


def test_missing_stable_request_id_and_unconfigured_root_fail_closed(tmp_path):
    source, _repo, actor_root, calls, executor, runtime = _harness("F23", tmp_path)
    preview = DependentCandidateChatPreview(runtime(), executor)
    with pytest.raises(ValueError, match="stable validated"):
        preview.execute(source, "", "main")
    actor_root.rename(actor_root.parent / "removed-local-actor-state")
    with pytest.raises(ValueError, match="actor-root"):
        preview.execute(source, "web-uuid", "main")
    assert calls == []


def test_replayed_message_id_is_scoped_to_one_conversation(tmp_path):
    from odyssey_runtime.delivery_results import DeliveryResultError

    source, repo, actor_root, calls, executor, runtime = _harness("F23", tmp_path)
    request_id = "web-one-conversation"
    assert (
        DependentCandidateChatPreview(runtime(), executor).execute(source, request_id, "main")[
            "status"
        ]
        == "completed"
    )
    before = {p: repo.read_text(p) for p in repo.list_markdown_paths()}
    with pytest.raises(DeliveryResultError, match="another delivery"):
        DependentCandidateChatPreview(runtime(), executor).execute(
            source, request_id, "another-conversation"
        )
    assert len(calls) == 1
    assert {p: repo.read_text(p) for p in repo.list_markdown_paths()} == before


def test_subordinate_core_request_must_match_durable_admission_receipt(tmp_path):
    from odyssey_core.application import ApplicationResult
    from odyssey_core.candidate_dependency_admission import DependentOperationAdmissionError

    source, repo, actor_root, calls, executor, runtime = _harness("F23", tmp_path)

    def forged(text, request_id, root):
        real = executor(text, request_id, root)
        assert real.status is ApplicationStatus.COMPLETED
        return ApplicationResult(
            "wrong-unlinked-subroute",
            real.status,
            real.action_results,
            real.affected_stable_note_ids,
        )

    with pytest.raises(DependentOperationAdmissionError, match="subordinate request ID"):
        DependentCandidateChatPreview(runtime(), forged).execute(
            source, "web-f23-bad-subroute", "main"
        )
    assert len(calls) == 1
    # Canonical facts may have been written before detecting the forged
    # return envelope: they remain for manual review, NOT silently replayed.
    assert (
        DependentOperationJournal(actor_root, repo).inspect("web-f23-bad-subroute").state
        == "completed"
    )


def test_partial_result_is_never_cached_as_a_success(tmp_path, monkeypatch):
    source, repo, actor_root, calls, executor, runtime = _harness("F23", tmp_path)
    original = core_application._execute_write

    def fail_after_first(action_index, *args, **kwargs):
        if action_index == 1:
            return ActionResult(action_index, "write", ActionStatus.FAILED)
        return original(action_index, *args, **kwargs)

    monkeypatch.setattr(core_application, "_execute_write", fail_after_first)
    response = DependentCandidateChatPreview(runtime(), executor).execute(
        source, "web-f23-no-false-cache", "main"
    )
    assert response["status"] == "partial"
    assert not list((actor_root / "dependent-preview-deliveries").glob("*.json"))
    assert (
        DependentOperationJournal(actor_root, repo).inspect("web-f23-no-false-cache").state
        == "partial"
    )


def test_public_http_server_remains_unaware_of_private_dependency_preview():
    """Source inspection guards accidental registration before user approval."""
    from pathlib import Path

    server = Path(__file__).resolve().parents[2] / "odyssey_runtime" / "server.py"
    composer = Path(__file__).resolve().parents[2] / "odyssey_runtime" / "composition.py"
    assert "dependent_candidate_preview" not in server.read_text(encoding="utf-8")
    assert "dependent_candidate_preview" not in composer.read_text(encoding="utf-8")
