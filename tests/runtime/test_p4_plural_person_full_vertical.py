"""No network/model: recorded source reviews through real dual-Person Core Writer,
Tasks Core planner, physical Markdown, and E3 exact-delivery replay.
"""

from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace

import pytest

from odyssey_apps.tasks import (
    TaskCorePlanner,
    TaskInterpretation,
    TaskLifecycleGuard,
    TaskOperation,
    TaskPersonReferenceSet,
    TaskTemporalMention,
    TaskTemporalRole,
)
from odyssey_core.application import ApplicationResult, ApplicationStatus, execute_request
from odyssey_core.notes import parse_note
from odyssey_core.request_planning import (
    KnowledgeUnit,
    PropertyChange,
    RequestPlan,
    RequestPlanningError,
    SelectionCriteria,
    WriteAction,
)
from odyssey_core.temporal_interpretation import parse_temporal_interpretation
from tests.runtime.test_p4_fresh_person_task import CLOCK
from tests.runtime.test_whole_source_light_product_p4 import SCHEMA, RecordedClient, _fixture

BEFORE = "Hoy he conocido a Ana y a Luis."
AFTER = " Mañana tengo que llamar a los dos."
SOURCE = BEFORE + AFTER
PEOPLE = ("Ana", "Luis")


def runtime_with_plural_recording(tmp_path, *, reject_task=False, forged_assignee=False):
    repo, actor, executor, product = _fixture(tmp_path, incremental_indexes=True)
    records = []

    def core(text, locator, identity, instant):
        assert text == BEFORE and instant.isoformat() == CLOCK and identity == actor
        records.append("core")
        units = tuple(
            KnowledgeUnit(
                SelectionCriteria(name, name, "person", (), None),
                "record",
                (),
                (),
                (f"He conocido a {name}.",),
                (),
            )
            for name in PEOPLE
        )
        return execute_request(
            text,
            planner=SimpleNamespace(plan=lambda *_: RequestPlan((WriteAction(units),), ())),
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

    def prepare(text, instant):
        assert text == AFTER.strip() and instant.isoformat() == CLOCK
        records.append("prepare")
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
        assert isinstance(handoff, TaskPersonReferenceSet)
        assert identity == actor and instant.isoformat() == CLOCK
        proofs = handoff.require_current(identity.stable_user_id, text, repo, SCHEMA)
        assert len(proofs) == 2
        records.append("task")
        if reject_task:
            return ApplicationResult(locator, ApplicationStatus.NEEDS_ATTENTION, (), ())
        title = "Llamar a los dos"
        primary = KnowledgeUnit(
            SelectionCriteria(title, title, "task", (), None),
            "record",
            (
                PropertyChange("status", "set", "pending"),
                PropertyChange("target_date", "set", "2026-10-17"),
            ),
            (),
            ("Llamar a los dos.",),
            (),
            force_create=True,
        )
        units = (primary,)
        if forged_assignee:
            from odyssey_core.request_planning import KnowledgeReference

            primary = replace(primary, references=(KnowledgeReference(1, "assignee", "Ana"),))
            helper = KnowledgeUnit(
                SelectionCriteria("Ana", "Ana", "person", (), None),
                "record",
                (),
                (),
                (),
                (),
                reference_lookup_only=True,
            )
            units = (primary, helper)
        planner = TaskCorePlanner(
            SimpleNamespace(plan=lambda *_: RequestPlan((WriteAction(units),), ())),
            interpretation,
            verified_person_set=tuple((d.mention, d.evidence.canonical_name) for d in proofs),
        )
        try:
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
                write_preflight_guard=TaskLifecycleGuard(TaskOperation.CREATE),
            )
        except RequestPlanningError:
            if not forged_assignee:
                raise
            return ApplicationResult(locator, ApplicationStatus.NEEDS_ATTENTION, (), ())

    route = {
        "capabilities": ["core", "tasks"],
        "self_relation_span": None,
        "interpretation": "joint",
        "reason": "shared_reference",
        "app_scopes": [
            {
                "capability": "core",
                "description": "people encountered",
                "depends_on_another_scope": False,
            },
            {
                "capability": "tasks",
                "description": "call both people",
                "depends_on_another_scope": True,
            },
        ],
    }
    partition = {
        "full_source_quote": SOURCE,
        "antecedent_quote": BEFORE,
        "dependent_quote": AFTER,
        "dependent_mention": "los dos",
    }
    review = {
        **partition,
        "antecedent_mentions": list(PEOPLE),
        "all_referents": True,
        "single_personal_task": True,
        "operation_supported": True,
    }
    executor.dependent_person_create_enabled = True
    executor.dependent_core_delegate = core
    executor.dependent_task_prepare = prepare
    executor.dependent_task_delegate = task
    executor.client = RecordedClient(
        [
            route,
            partition,
            deepcopy(review),
            deepcopy(review),
            {
                "only_task_semantics": True,
                "exactly_one_operation": True,
                "source_quote": AFTER.strip(),
            },
        ]
    )
    return repo, actor, executor, product, records


def snapshot(repo):
    return {name: repo.read_text(name) for name in repo.list_markdown_paths()}


def test_recorded_two_person_e4_vertical_physical_task_links_and_replay(tmp_path):
    repo, actor, executor, product, records = runtime_with_plural_recording(tmp_path)
    result = product.execute_product(SOURCE, "plural-e4-vertical", "main", actor)
    assert result["status"] == "completed", result
    parsed = {path: parse_note(text) for path, text in snapshot(repo).items()}
    persons = [
        (path, note)
        for path, note in parsed.items()
        if note.metadata.get("type") == "person" and note.metadata.get("name") in PEOPLE
    ]
    tasks = [note for note in parsed.values() if note.metadata.get("type") == "task"]
    assert len(persons) == 2 and len(tasks) == 1
    assert tasks[0].metadata["target_date"] == "2026-10-17"
    assert "Responsable:" not in tasks[0].content
    assert all(
        f"[[{path.removesuffix('.md')}|{note.metadata['name']}]]" in tasks[0].content
        for path, note in persons
    )
    assert records == ["prepare", "core", "task"]
    assert len(result["execution_flow"]["routes"]) == 2
    before = snapshot(repo)
    replay = product.execute_product(SOURCE, "plural-e4-vertical", "main", actor)
    assert replay["delivery_replayed"] is True
    assert snapshot(repo) == before
    assert records == ["prepare", "core", "task"]


@pytest.mark.parametrize("reject_task,forged_assignee", [(True, False), (False, True)])
def test_recorded_plural_e4_refuses_false_completion_after_person_writes(
    tmp_path, reject_task, forged_assignee
):
    repo, actor, _executor, product, records = runtime_with_plural_recording(
        tmp_path,
        reject_task=reject_task,
        forged_assignee=forged_assignee,
    )
    result = product.execute_product(SOURCE, "plural-e4-negative", "main", actor)
    assert result["status"] != "completed"
    parsed = [parse_note(text) for text in snapshot(repo).values()]
    assert len([n for n in parsed if n.metadata.get("type") == "task"]) == 0
    assert (
        len(
            [
                n
                for n in parsed
                if n.metadata.get("type") == "person" and n.metadata.get("name") in PEOPLE
            ]
        )
        == 2
    )
    assert records == ["prepare", "core", "task"]
