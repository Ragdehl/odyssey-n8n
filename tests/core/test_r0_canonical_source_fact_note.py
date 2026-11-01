"""Only physical Core E3 facts may be source-note references to later Apps.

Recorded Core plans, disposable Markdown; no model/browsers involved.
"""

from dataclasses import replace
from types import SimpleNamespace

import pytest

from odyssey_core.application import ApplicationStatus, execute_request
from odyssey_core.dependent_group_evidence import (
    CanonicalGroupEvidenceError,
    prove_canonical_source_fact_note,
)
from odyssey_core.notes import parse_note, serialize_note
from odyssey_core.request_planning import KnowledgeUnit, RequestPlan, SelectionCriteria, WriteAction
from tests.runtime.test_whole_source_light_product_p4 import _fixture


def _persist_source(tmp_path, source="He conocido varias personas.", target_type="calendar_day"):
    repo, actor, executor, _runtime = _fixture(tmp_path)
    target = (
        SelectionCriteria(None, "2026-10-16", target_type, (), None)
        if target_type == "calendar_day"
        else SelectionCriteria("Atlas", "Atlas", target_type, (), None)
    )
    plan = RequestPlan(
        (
            WriteAction(
                (
                    KnowledgeUnit(
                        target,
                        "record",
                        (),
                        (),
                        (source,),
                        (),
                    ),
                )
            ),
        ),
        (),
    )
    result = execute_request(
        source,
        planner=SimpleNamespace(plan=lambda *_: plan),
        repository=repo,
        schema=executor.schema,
        context_index=executor.context_index,
        semantic_index=executor.semantic_index,
        embedder=executor.embedder,
        contextual_reasoner=executor.reasoner,
        authenticated_actor=actor,
        self_binding_repository=executor.bindings,
        actor=actor.stable_user_id,
        now="2026-10-16T15:30:00+02:00",
        context_limit=10,
        request_id_factory=lambda: "r0-canonical-source-fact",
    )
    assert result.status is ApplicationStatus.COMPLETED, result
    return repo, actor, executor, result


def test_fact_source_targets_the_note_containing_this_request_fact_not_members(tmp_path):
    repo, actor, executor, result = _persist_source(tmp_path)
    proof = prove_canonical_source_fact_note(
        predecessor=result,
        predecessor_quote="He conocido varias personas.",
        original_mention="varias personas",
        repository=repo,
        schema=executor.schema,
        actor_id=actor.stable_user_id,
    )
    assert proof.stable_note_id == "date:2026-10-16"
    assert proof.fact_ordinal == 0
    assert (
        proof.require_current(repo, executor.schema, actor.stable_user_id) == proof.stable_note_id
    )
    assert not [
        parse_note(repo.read_text(p))
        for p in repo.list_markdown_paths()
        if parse_note(repo.read_text(p)).metadata.get("name") == "varias personas"
    ]
    with pytest.raises(CanonicalGroupEvidenceError, match="actor mismatch"):
        proof.require_current(repo, executor.schema, "another-actor")


@pytest.mark.parametrize(
    ("source", "mention"),
    [
        ("He conocido a otras personas.", "personas"),
        ("He conocido varias personas.", "personas inexistentes"),
    ],
)
def test_fact_source_rejects_wrong_source_quote_and_ungrounded_mention(tmp_path, source, mention):
    repo, actor, executor, result = _persist_source(tmp_path)
    with pytest.raises(CanonicalGroupEvidenceError):
        prove_canonical_source_fact_note(
            predecessor=result,
            predecessor_quote=source,
            original_mention=mention,
            repository=repo,
            schema=executor.schema,
            actor_id=actor.stable_user_id,
        )


def test_fact_source_rejects_forged_core_source_digest(tmp_path):
    repo, actor, executor, result = _persist_source(tmp_path)
    with pytest.raises(CanonicalGroupEvidenceError):
        prove_canonical_source_fact_note(
            predecessor=replace(result, core_source_digest="forged"),
            predecessor_quote="He conocido varias personas.",
            original_mention="personas",
            repository=repo,
            schema=executor.schema,
            actor_id=actor.stable_user_id,
        )


def test_fact_source_fails_closed_when_note_changes_after_proof(tmp_path):
    repo, actor, executor, result = _persist_source(tmp_path)
    proof = prove_canonical_source_fact_note(
        predecessor=result,
        predecessor_quote="He conocido varias personas.",
        original_mention="varias personas",
        repository=repo,
        schema=executor.schema,
        actor_id=actor.stable_user_id,
    )
    path = next(
        p
        for p in repo.list_markdown_paths()
        if parse_note(repo.read_text(p)).metadata.get("id") == proof.stable_note_id
    )
    note = parse_note(repo.read_text(path))
    repo.replace_text(
        path, serialize_note(replace(note, content=note.content + "\n- Otro dato posterior.\n"))
    )
    with pytest.raises(CanonicalGroupEvidenceError, match="changed"):
        proof.require_current(repo, executor.schema, actor.stable_user_id)


@pytest.mark.parametrize("link_target", ["source", "other_note", "stale"])
def test_e3_source_fact_link_guard_authorizes_only_current_source_note(tmp_path, link_target):
    from odyssey_apps.tasks import TaskLifecycleGuard, TaskOperation
    from odyssey_core.dependent_group_evidence import CanonicalSourceFactLinkGuard
    from odyssey_core.request_planning import KnowledgeReference, PropertyChange
    from tests.apps.tasks.test_core_interop import Reasoner

    repo, actor, executor, predecessor = _persist_source(tmp_path)
    proof = prove_canonical_source_fact_note(
        predecessor=predecessor,
        predecessor_quote="He conocido varias personas.",
        original_mention="varias personas",
        repository=repo,
        schema=executor.schema,
        actor_id=actor.stable_user_id,
    )
    if link_target == "other_note":
        from odyssey_core import create_entity

        create_entity(
            repo,
            executor.schema,
            path="calendar/days/2026-10-17.md",
            entity_id="date:2026-10-17",
            metadata={"type": "calendar_day", "name": "17-10-2026", "date": "2026-10-17"},
            content="- Un dato distinto.\n",
            actor="synthetic",
            now="2026-10-16T15:31:00+02:00",
        )
    if link_target == "stale":
        path = next(
            p
            for p in repo.list_markdown_paths()
            if parse_note(repo.read_text(p)).metadata.get("id") == proof.stable_note_id
        )
        note = parse_note(repo.read_text(path))
        repo.replace_text(
            path, serialize_note(replace(note, content=note.content + "\n- Actualización.\n"))
        )
    executor.context_index.rebuild(repo, executor.schema, executor.embedder)
    executor.semantic_index.rebuild(repo, executor.schema, executor.embedder)
    primary = KnowledgeUnit(
        SelectionCriteria("Escribirles", "Escribirles", "task", (), None),
        "record",
        (
            PropertyChange("status", "set", "pending"),
            PropertyChange("target_date", "set", "2026-10-17"),
        ),
        (),
        ("Mañana tengo que escribirles. Contexto: {{ref:0}}.",),
        (KnowledgeReference(1, "reference", "nota de contexto"),),
        force_create=True,
    )
    helper = KnowledgeUnit(
        SelectionCriteria(
            None,
            "2026-10-17" if link_target == "other_note" else "2026-10-16",
            "calendar_day",
            (),
            None,
        ),
        "record",
        (),
        (),
        (),
        (),
        reference_lookup_only=True,
    )
    plan = RequestPlan((WriteAction((primary, helper)),), ())
    outcome = execute_request(
        "Mañana tengo que escribirles.",
        planner=SimpleNamespace(plan=lambda *_: plan),
        repository=repo,
        schema=executor.schema,
        context_index=executor.context_index,
        semantic_index=executor.semantic_index,
        embedder=executor.embedder,
        contextual_reasoner=Reasoner(),
        authenticated_actor=actor,
        self_binding_repository=executor.bindings,
        actor=actor.stable_user_id,
        now="2026-10-16T15:40:00+02:00",
        context_limit=10,
        request_id_factory=lambda: "r0-linked-task",
        write_preflight_guard=CanonicalSourceFactLinkGuard(
            proof, actor.stable_user_id, TaskLifecycleGuard(TaskOperation.CREATE)
        ),
    )
    if link_target != "source":
        assert outcome.status is not ApplicationStatus.COMPLETED
        assert not [
            parse_note(repo.read_text(p))
            for p in repo.list_markdown_paths()
            if parse_note(repo.read_text(p)).metadata.get("type") == "task"
        ]
        return
    assert outcome.status is ApplicationStatus.COMPLETED, outcome
    tasks = [
        parse_note(repo.read_text(p))
        for p in repo.list_markdown_paths()
        if parse_note(repo.read_text(p)).metadata.get("type") == "task"
    ]
    assert len(tasks) == 1
    assert tasks[0].metadata["target_date"] == "2026-10-17"
    assert "escribirles" in tasks[0].content
    assert "[[calendar/days/2026-10-16|" in tasks[0].content
    assert not [
        parse_note(repo.read_text(p))
        for p in repo.list_markdown_paths()
        if parse_note(repo.read_text(p)).metadata.get("name") == "varias personas"
    ]


@pytest.mark.parametrize("note_type", ["project", "document", "concept", "person"])
def test_source_fact_note_proof_is_generic_across_registered_note_types(tmp_path, note_type):
    source = "Atlas contiene un dato importante."
    repo, actor, executor, result = _persist_source(tmp_path, source=source, target_type=note_type)
    proof = prove_canonical_source_fact_note(
        predecessor=result,
        predecessor_quote=source,
        original_mention="dato importante",
        repository=repo,
        schema=executor.schema,
        actor_id=actor.stable_user_id,
    )
    path = next(
        p
        for p in repo.list_markdown_paths()
        if parse_note(repo.read_text(p)).metadata.get("id") == proof.stable_note_id
    )
    assert parse_note(repo.read_text(path)).metadata["type"] == note_type
    assert (
        proof.require_current(repo, executor.schema, actor.stable_user_id) == proof.stable_note_id
    )
