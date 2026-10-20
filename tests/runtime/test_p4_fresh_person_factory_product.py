"""Production composition factory: recorded models, real Core/Tasks Writer and replay."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest

from odyssey_apps.schema_extensions import compose_application_schema
from odyssey_apps.tasks import (
    TASK_SCHEMA_EXTENSION,
    TaskInterpretation,
    TaskOperation,
    TaskPersonReference,
    TaskTemporalMention,
    TaskTemporalRole,
)
from odyssey_core import create_entity
from odyssey_core.context import ContextIndex
from odyssey_core.identity_boundary import AuthenticatedActorContext, SelfBindingRepository
from odyssey_core.notes import parse_note
from odyssey_core.request_planning import (
    KnowledgeReference,
    KnowledgeUnit,
    PropertyChange,
    RequestPlan,
    SelectionCriteria,
    WriteAction,
)
from odyssey_core.semantic import SemanticEntityIndex
from odyssey_core.storage import VaultRepository
from odyssey_core.temporal_interpretation import parse_temporal_interpretation
from odyssey_runtime import composition
from tests.core.test_reference_preflight import UnresolvedReasoner
from tests.runtime.test_p4_fresh_person_task import CLOCK, _scenario
from tests.runtime.test_temporal_user_path_e2e import ConstantEmbedder
from tests.runtime.test_whole_source_light_product_p4 import RecordedClient


@pytest.mark.parametrize("fault", [None, "stale", "wrong_actor", "forged_link"])
def test_factory_fresh_person_create_task_create_and_replay(tmp_path, monkeypatch, fault):
    vault, state, derived = (tmp_path / part for part in ("vault", "state", "derived"))
    for path in (vault, state / "pending", derived):
        path.mkdir(parents=True)
    repo = VaultRepository(vault)
    base = json.loads((Path(__file__).resolve().parents[2] / "config/note-schema.json").read_text())
    schema = compose_application_schema(base, (TASK_SCHEMA_EXTENSION,))
    create_entity(
        repo,
        schema,
        path="self.md",
        entity_id="self-p4-factory",
        metadata={"name": "Persona local", "type": "person"},
        content="",
        actor="fixture",
        now=CLOCK,
    )
    actor = AuthenticatedActorContext(str(uuid4()))
    SelfBindingRepository(state, repo, schema).bind(actor.stable_user_id, "self-p4-factory")
    embedder = ConstantEmbedder()
    for index in (
        ContextIndex(derived / "context.sqlite3"),
        SemanticEntityIndex(derived / "semantic.sqlite3"),
        SemanticEntityIndex(derived / "semantic-tasks.sqlite3"),
    ):
        index.rebuild(repo, schema, embedder)
    for key, value in {
        "OPENAI_API_KEY": "sk-synthetic-unused-do-not-send",
        "ODYSSEY_LIGHT_SOURCE_V1": "1",
        "ODYSSEY_ENABLED_APPLICATIONS": "tasks",
        "ODYSSEY_VAULT_ROOT": str(vault),
        "ODYSSEY_RUNTIME_ROOT": str(derived),
        "ODYSSEY_STATE_ROOT": str(state),
        "ODYSSEY_PENDING_ROOT": str(state / "pending"),
        "ODYSSEY_EMBEDDING_CACHE": str(tmp_path / "fake-cache"),
    }.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(composition, "FastEmbedTextEmbedder", lambda **_kw: embedder)
    monkeypatch.setattr(composition, "_build_contextual_reasoner", UnresolvedReasoner)
    monkeypatch.setattr(composition, "GitHistoryRecorder", lambda _root: None)
    monkeypatch.setattr(
        composition,
        "_current_time",
        lambda: {
            "date": "2026-10-16",
            "time": "15:30:00",
            "timezone": "Europe/Paris",
            "timestamp": CLOCK,
        },
    )
    source, before, after, mention, rows = _scenario("Marta")
    seen = []

    def planner_from_environment(_cls, _schema, _clock, **_kwargs):
        class Planner:
            def plan(self, text, *_args):
                seen.append(text)
                if text == before:
                    unit = KnowledgeUnit(
                        SelectionCriteria("Marta", "Marta", "person", (), None),
                        "record",
                        (),
                        (),
                        ("Conocí a Marta.",),
                        (),
                        force_create=True,
                    )
                    return RequestPlan((WriteAction((unit,)),), ())
                assert text == after.strip(), text
                unit = KnowledgeUnit(
                    SelectionCriteria("Llamar a Marta", "Llamar a Marta", "task", (), None),
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
                    SelectionCriteria("Marta", "Marta", "person", (), None),
                    "record",
                    (),
                    (),
                    (),
                    (),
                    reference_lookup_only=True,
                )
                return RequestPlan((WriteAction((unit, helper)),), ())

        return Planner()

    monkeypatch.setattr(
        composition.OpenAIRequestPlanner, "from_environment", classmethod(planner_from_environment)
    )

    class Interpreter:
        def interpret(self, text, context=()):
            assert text == after.strip()
            return TaskInterpretation(
                text,
                TaskOperation.CREATE,
                temporal_mentions=(TaskTemporalMention("Mañana", TaskTemporalRole.TARGET_DATE),),
            )

    monkeypatch.setattr(
        composition.OpenAITaskInterpreter,
        "from_environment",
        classmethod(lambda cls: Interpreter()),
    )

    class Temporal:
        def interpret(self, text, context=()):
            return parse_temporal_interpretation(
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

    monkeypatch.setattr(
        composition.OpenAITemporalInterpreter,
        "from_environment",
        classmethod(lambda cls, *_args: Temporal()),
    )
    product = composition.build_runtime_from_environment()
    executor = product.hybrid_candidate_execute
    assert executor.dependent_person_create_enabled is True
    executor.client = RecordedClient(rows)
    if fault is not None:
        actual_delegate = executor.dependent_task_delegate

        def with_invalid_handoff(
            text, locator, identity, interpretation, temporal, handoff, instant
        ):
            assert isinstance(handoff, TaskPersonReference)
            if fault == "stale":
                person = next(
                    path
                    for path in repo.list_markdown_paths()
                    if parse_note(repo.read_text(path)).metadata.get("name") == "Marta"
                )
                (vault / person).write_text(
                    repo.read_text(person) + "\nLocally changed after Core receipt.\n"
                )
            elif fault == "wrong_actor":
                handoff = replace(handoff, actor_id="different-actor")
            elif fault == "forged_link":
                evidence = replace(
                    handoff.source_dependency.evidence, stable_note_id="self-p4-factory"
                )
                handoff = replace(
                    handoff, source_dependency=replace(handoff.source_dependency, evidence=evidence)
                )
            return actual_delegate(
                text, locator, identity, interpretation, temporal, handoff, instant
            )

        executor.dependent_task_delegate = with_invalid_handoff
    result = product.execute_product(source, f"p4-factory-{fault or 'success'}", "main", actor)
    assert seen == ([source, before] if fault is not None else [source, before, after.strip()])
    if fault is not None:
        assert result["status"] != "completed", result
        assert not any(
            parse_note(repo.read_text(path)).metadata.get("type") == "task"
            for path in repo.list_markdown_paths()
        ), "Invalid Core reference must never create a Task"
        return
    assert result["status"] == "completed", result
    notes = [parse_note(repo.read_text(path)) for path in repo.list_markdown_paths()]
    people = [
        n for n in notes if n.metadata.get("type") == "person" and n.metadata.get("name") == "Marta"
    ]
    tasks = [n for n in notes if n.metadata.get("type") == "task"]
    assert len(people) == len(tasks) == 1
    assert tasks[0].metadata["target_date"] == "2026-10-17"
    assert "[[Marta" in tasks[0].content or "|Marta]]" in tasks[0].content
    snapshot = {path: repo.read_text(path) for path in repo.list_markdown_paths()}
    replay = product.execute_product(source, "p4-factory-success", "main", actor)
    assert replay["delivery_replayed"] is True
    assert snapshot == {path: repo.read_text(path) for path in repo.list_markdown_paths()}
    assert executor.client.rows == []
