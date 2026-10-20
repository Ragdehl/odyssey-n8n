"""Recorded model claims through source reviews, Core Writer, Tasks and E3 replay."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace

import pytest

from odyssey_apps.tasks import (
    TaskCorePlanner,
    TaskDependentTargetError,
    TaskInterpretation,
    TaskLifecycleGuard,
    TaskOperation,
    TaskPersonReference,
    TaskTemporalMention,
    TaskTemporalRole,
    compose_task_domain_interpretation,
)
from odyssey_core.application import (
    ApplicationResult,
    ApplicationStatus,
    DependentReferenceGuard,
    execute_request,
)
from odyssey_core.notes import parse_note
from odyssey_core.request_planning import (
    KnowledgeReference,
    KnowledgeUnit,
    PropertyChange,
    RequestPlan,
    SelectionCriteria,
    WriteAction,
)
from odyssey_core.source_bound_dependency import (
    SourceBoundDependencyError,
    prove_source_bound_dependency,
)
from odyssey_core.temporal_interpretation import parse_temporal_interpretation
from tests.runtime.test_whole_source_light_product_p4 import SCHEMA, RecordedClient, _fixture

CLOCK = "2026-10-16T15:30:00+02:00"


def _scenario(name: str, others: tuple[str, ...] = (), *, anaphoric: bool = False):
    before = f"Hoy conocí a {', '.join((name, *others))}."
    after = (
        f" Mañana debo llamar a {name}."
        if others and not anaphoric
        else " Mañana debo llamar a esa persona."
    )
    source = before + after
    mention = name if others and not anaphoric else "esa persona"
    route = {
        "capabilities": ["core", "tasks"],
        "self_relation_span": None,
        "interpretation": "joint",
        "reason": "shared_reference",
        "app_scopes": [
            {
                "capability": "core",
                "description": "person encounter",
                "depends_on_another_scope": False,
            },
            {
                "capability": "tasks",
                "description": "new obligation",
                "depends_on_another_scope": True,
            },
        ],
    }
    partition = {
        "full_source_quote": source,
        "antecedent_quote": before,
        "dependent_quote": after,
        "dependent_mention": mention,
    }
    review = {
        **partition,
        "one_target": True,
        "same_target": True,
        "target_type": "person",
        "operation": "CREATE",
        "operation_supported": True,
    }
    rows = [
        route,
        partition,
        {"only_task_semantics": True, "exactly_one_operation": True, "source_quote": after.strip()},
        review,
        deepcopy(review),
    ]
    return source, before, after, mention, rows


def _physical(
    tmp_path,
    name: str,
    *,
    core_writes=True,
    core_partial=False,
    others: tuple[str, ...] = (),
    wrong_link=False,
    anaphoric=False,
):
    repo, actor, executor, runtime = _fixture(tmp_path, incremental_indexes=True)
    source, before, after, mention, rows = _scenario(name, others, anaphoric=anaphoric)
    executor.dependent_person_create_enabled = True
    calls = []
    handoffs = []
    core_results = []

    def core(text, locator, identity, instant):
        assert text == before and identity == actor and instant.isoformat() == CLOCK
        calls.append("core")
        if not core_writes:
            from odyssey_core.application import ApplicationResult

            return ApplicationResult(locator, ApplicationStatus.NEEDS_ATTENTION, (), ())
        people = tuple(
            KnowledgeUnit(
                SelectionCriteria(person_name, person_name, "person", (), None),
                "record",
                (),
                (),
                (f"Conocí a {person_name}.",),
                (),
            )
            for person_name in (name, *others)
        )
        result = execute_request(
            text,
            planner=SimpleNamespace(plan=lambda *_: RequestPlan((WriteAction(people),), ())),
            repository=repo,
            schema=SCHEMA,
            context_index=executor.context_index,
            semantic_index=executor.semantic_index,
            embedder=executor.embedder,
            contextual_reasoner=executor.reasoner,
            authenticated_actor=identity,
            self_binding_repository=executor.bindings,
            actor=identity.stable_user_id,
            now=CLOCK,
            context_limit=10,
            request_id_factory=lambda: locator,
        )
        assert len(result.action_results[0].canonical_direct_target_evidence) == len(people)
        core_results.append(result)
        return replace(result, status=ApplicationStatus.PARTIAL) if core_partial else result

    def prepare(text, instant):
        assert text == after.strip() and instant.isoformat() == CLOCK
        calls.append("prepare")
        task = TaskInterpretation(
            text,
            TaskOperation.CREATE,
            temporal_mentions=(TaskTemporalMention("Mañana", TaskTemporalRole.TARGET_DATE),),
        )
        temporal = parse_temporal_interpretation(
            {
                "mentions": [
                    {
                        "temporal_text": "Mañana",
                        "temporal": {
                            "kind": "EXACT_DATE",
                            "exact_date": "2026-10-17",
                            "exact_datetime": None,
                            "range_start": None,
                            "range_end_exclusive": None,
                        },
                    }
                ]
            },
            text,
            timezone="Europe/Paris",
        )
        return task, temporal

    def task(text, locator, identity, interpretation, temporal, handoff, instant):
        assert isinstance(handoff, TaskPersonReference)
        assert identity == actor and instant.isoformat() == CLOCK
        assert temporal is not None and temporal.source_text == text
        proof = handoff.require_current(identity.stable_user_id, text, repo, SCHEMA)
        handoffs.append(handoff)
        calls.append("task")
        title = f"Llamar a {name}"
        primary = KnowledgeUnit(
            SelectionCriteria(title, title, "task", (), None),
            "record",
            (
                PropertyChange("status", "set", "pending"),
                PropertyChange("target_date", "set", "2026-10-17"),
            ),
            (),
            ("Debo llamar a {{ref:0}}.",),
            (KnowledgeReference(1, "person", mention),),
            force_create=True,
        )
        helper = KnowledgeUnit(
            SelectionCriteria(
                others[0] if wrong_link else name,
                others[0] if wrong_link else name,
                "person",
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
        planner = TaskCorePlanner(
            SimpleNamespace(plan=lambda *_: RequestPlan((WriteAction((primary, helper)),), ())),
            interpretation,
        )
        domain = compose_task_domain_interpretation(interpretation, temporal, now=CLOCK)
        assert domain.evidence
        return execute_request(
            text,
            planner=planner,
            repository=repo,
            schema=SCHEMA,
            context_index=executor.context_index,
            semantic_index=executor.semantic_index,
            embedder=executor.embedder,
            contextual_reasoner=executor.reasoner,
            authenticated_actor=identity,
            self_binding_repository=executor.bindings,
            actor=identity.stable_user_id,
            now=CLOCK,
            context_limit=10,
            request_id_factory=lambda: locator,
            write_preflight_guard=lambda action, preflight, repository, schema: (
                TaskLifecycleGuard(TaskOperation.CREATE)(action, preflight, repository, schema),
                DependentReferenceGuard(proof.mention, proof.evidence)(
                    action, preflight, repository, schema
                ),
            ),
        )

    executor.dependent_core_delegate = core
    executor.dependent_task_prepare = prepare
    executor.dependent_task_delegate = task
    executor.person_handoffs = handoffs
    executor.person_core_results = core_results
    executor.client = RecordedClient(rows)
    return repo, actor, executor, runtime, source, calls


def _notes(repo):
    return [parse_note(repo.read_text(path)) for path in repo.list_markdown_paths()]


def test_two_new_people_leave_ambiguous_task_pending_in_vertical_runtime(tmp_path):
    repo, actor, _executor, runtime, source, calls = _physical(
        tmp_path, "Nora", others=("Eva",), anaphoric=True
    )
    result = runtime.execute_product(source, "ambiguous-person-task", "main", actor)
    assert result["status"] != "completed"
    notes = _notes(repo)
    assert {n.metadata["name"] for n in notes if n.metadata["type"] == "person"} >= {"Nora", "Eva"}
    assert not any(n.metadata["type"] == "task" for n in notes)
    assert "task" not in calls


@pytest.mark.parametrize("name", ["Marta", "Élodie", "Rina"])
def test_fresh_person_task_wikilink_and_delivery_replay(tmp_path, name):
    repo, actor, executor, runtime, source, calls = _physical(tmp_path, name)
    result = runtime.execute_product(source, "fresh-person-task", "main", actor)
    assert result["status"] == "completed", result
    # Mixed Core+Tasks flow must display *real* physically affected write
    # receipts in both routes, not merely a successful model proposal.
    assert [route["capability"] for route in result["execution_flow"]["routes"]] == [
        "core",
        "tasks",
    ]
    assert [len(route["writes"]) for route in result["execution_flow"]["routes"]] == [1, 1]
    assert {
        write["target"]
        for route in result["execution_flow"]["routes"]
        for write in route["writes"]
        if write["status"] == "succeeded" and write["operation"] == "CREATED"
    } == set(result["affected_stable_note_ids"])
    notes = _notes(repo)
    people = [
        note
        for note in notes
        if note.metadata["type"] == "person" and note.metadata["name"] == name
    ]
    tasks = [note for note in notes if note.metadata["type"] == "task"]
    assert len(people) == len(tasks) == 1
    assert people[0].metadata["id"] in result["affected_stable_note_ids"]
    assert f"Conocí a {name}." in people[0].content
    assert tasks[0].metadata["target_date"] == "2026-10-17"
    assert tasks[0].metadata["status"] == "pending"
    person_path = next(
        path
        for path in repo.list_markdown_paths()
        if parse_note(repo.read_text(path)).metadata.get("id") == people[0].metadata["id"]
    )
    assert f"[[{person_path.removesuffix('.md')}|{name}]]" in tasks[0].content
    assert "15:00" not in tasks[0].content
    assert "Responsable" not in tasks[0].content
    snapshot = {path: repo.read_text(path) for path in repo.list_markdown_paths()}
    replay = runtime.execute_product(source, "fresh-person-task", "main", actor)
    assert replay["delivery_replayed"] is True
    assert {path: repo.read_text(path) for path in repo.list_markdown_paths()} == snapshot
    assert calls == ["prepare", "core", "task"]


@pytest.mark.parametrize(
    "others",
    [
        (),
        ("Leo", "Iris"),
        ("Leo", "Iris", "Noa", "Eva"),
        ("Leo", "Iris", "Noa", "Eva", "Tara", "Sofía"),
    ],
)
def test_named_person_selected_from_variable_core_receipts(tmp_path, others):
    repo, actor, _executor, runtime, source, _calls = _physical(tmp_path, "Marta", others=others)
    result = runtime.execute_product(source, "many-core-people", "main", actor)
    assert result["status"] == "completed", result
    tasks = [note for note in _notes(repo) if note.metadata["type"] == "task"]
    assert len(tasks) == 1
    assert "|Marta]]" in tasks[0].content
    assert all(f"|{other}]]" not in tasks[0].content for other in others)


@pytest.mark.parametrize(
    "changed",
    [
        {"one_target": False},
        {"same_target": False},
        {"target_type": "unknown"},
        {"operation": "UNKNOWN"},
        {"dependent_mention": "otra persona"},
    ],
)
def test_review_rejection_precedes_person_or_task_write(tmp_path, changed):
    repo, actor, executor, runtime, source, calls = _physical(tmp_path, "Nora")
    executor.client.rows[3] = {**executor.client.rows[3], **changed}
    before = {path: repo.read_text(path) for path in repo.list_markdown_paths()}
    result = runtime.execute_product(source, "invalid-review", "main", actor)
    assert result["status"] == "needs_attention"
    assert "core" not in calls and "task" not in calls
    assert {path: repo.read_text(path) for path in repo.list_markdown_paths()} == before


def test_failed_core_person_never_calls_tasks(tmp_path):
    repo, actor, _executor, runtime, source, calls = _physical(tmp_path, "Nora", core_writes=False)
    result = runtime.execute_product(source, "missing-person", "main", actor)
    assert result["status"] != "completed"
    assert "task" not in calls
    assert not any(note.metadata["type"] == "task" for note in _notes(repo))


def test_partial_core_receipt_never_authorizes_task(tmp_path):
    repo, actor, _executor, runtime, source, calls = _physical(tmp_path, "Nora", core_partial=True)
    result = runtime.execute_product(source, "partial-person", "main", actor)
    assert result["status"] != "completed"
    assert "core" in calls and "task" not in calls
    assert not any(note.metadata["type"] == "task" for note in _notes(repo))


def test_core_guard_rejects_link_to_different_created_person(tmp_path):
    repo, actor, _executor, runtime, source, calls = _physical(
        tmp_path, "Nora", others=("Eva",), wrong_link=True
    )
    result = runtime.execute_product(source, "wrong-person-link", "main", actor)
    assert result["status"] != "completed"
    assert "core" in calls and "task" in calls
    assert not any(note.metadata["type"] == "task" for note in _notes(repo))


def test_person_handoff_rejects_wrong_actor_and_stale_markdown(tmp_path):
    repo, actor, executor, runtime, source, _calls = _physical(tmp_path, "Nora")
    assert runtime.execute_product(source, "fresh-proof", "main", actor)["status"] == "completed"
    proof = executor.person_handoffs[0]
    with pytest.raises(TaskDependentTargetError):
        proof.require_current(
            "different-authenticated-actor",
            proof.source_dependency.dependent_quote.strip(),
            repo,
            SCHEMA,
        )
    person_path = next(
        path
        for path in repo.list_markdown_paths()
        if parse_note(repo.read_text(path)).metadata.get("name") == "Nora"
    )
    repo.replace_text(person_path, repo.read_text(person_path) + "\nChanged after receipt.\n")
    with pytest.raises(TaskDependentTargetError):
        proof.require_current(
            actor.stable_user_id, proof.source_dependency.dependent_quote.strip(), repo, SCHEMA
        )


def test_person_handoff_rejects_a_different_dependent_source(tmp_path):
    repo, actor, executor, runtime, source, _calls = _physical(tmp_path, "Nora")
    assert runtime.execute_product(source, "source-proof", "main", actor)["status"] == "completed"
    handoff = executor.person_handoffs[0]
    with pytest.raises(TaskDependentTargetError):
        handoff.require_current(
            actor.stable_user_id, "Mañana debo escribir a esa persona.", repo, SCHEMA
        )


def test_person_changed_after_core_write_vetoes_task_before_mutation(tmp_path):
    repo, actor, executor, runtime, source, calls = _physical(tmp_path, "Nora")

    def stale_task(text, locator, who, interpretation, temporal, handoff, instant):
        person_path = next(
            path
            for path in repo.list_markdown_paths()
            if parse_note(repo.read_text(path)).metadata.get("name") == "Nora"
        )
        repo.replace_text(person_path, repo.read_text(person_path) + "\nExternal change.\n")
        with pytest.raises(TaskDependentTargetError):
            handoff.require_current(
                who.stable_user_id, handoff.source_dependency.dependent_quote.strip(), repo, SCHEMA
            )
        return ApplicationResult(locator, ApplicationStatus.NEEDS_ATTENTION, (), ())

    executor.dependent_task_delegate = stale_task
    result = runtime.execute_product(source, "stale-person", "main", actor)
    assert result["status"] != "completed"
    assert calls == ["prepare", "core"]
    assert not any(note.metadata["type"] == "task" for note in _notes(repo))


def test_wrong_actor_person_proof_vetoes_task_before_mutation(tmp_path):
    repo, actor, executor, runtime, source, calls = _physical(tmp_path, "Nora")

    def wrong_actor_task(text, locator, who, interpretation, temporal, handoff, instant):
        with pytest.raises(TaskDependentTargetError):
            handoff.require_current(
                "another-authenticated-actor",
                handoff.source_dependency.dependent_quote.strip(),
                repo,
                SCHEMA,
            )
        return ApplicationResult(locator, ApplicationStatus.NEEDS_ATTENTION, (), ())

    executor.dependent_task_delegate = wrong_actor_task
    result = runtime.execute_product(source, "wrong-actor-person", "main", actor)
    assert result["status"] != "completed"
    assert calls == ["prepare", "core"]
    assert not any(note.metadata["type"] == "task" for note in _notes(repo))


def test_forged_core_direct_receipt_lacks_writer_authority(tmp_path):
    repo, actor, executor, runtime, source, _calls = _physical(tmp_path, "Nora")
    assert runtime.execute_product(source, "forged-proof", "main", actor)["status"] == "completed"
    result = executor.person_core_results[0]
    action = result.action_results[0]
    forged = replace(result, action_results=(replace(action, unit_results=()),))
    before, after = source.split(".", 1)
    with pytest.raises(SourceBoundDependencyError):
        prove_source_bound_dependency(
            complete_original_source=source,
            antecedent_quote=before + ".",
            dependent_quote=after,
            exact_dependent_mention="esa persona",
            predecessor=forged,
            repository=repo,
            schema=SCHEMA,
        )
