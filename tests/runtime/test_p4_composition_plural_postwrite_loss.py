"""Production composition must reject a Task whose postwrite Person link vanished."""

from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from odyssey_apps.tasks import TaskInterpretation, TaskOperation, TaskPersonReferenceSet
from odyssey_core import create_entity
from odyssey_core.application import ApplicationStatus, execute_request
from odyssey_core.notes import parse_note
from odyssey_core.request_planning import (
    KnowledgeUnit,
    PropertyChange,
    RequestPlan,
    SelectionCriteria,
    WriteAction,
)
from odyssey_core.source_bound_dependency import SourceBoundDependency
from odyssey_runtime import composition
from scripts.odyssey_e4_live_browser_n8n import CLOCK, live_product


@pytest.mark.parametrize("corruption", ["missing", "duplicate", "extra_person"])
def test_factory_physical_postwrite_loss_returns_partial_via_real_composition(
    tmp_path, monkeypatch, corruption
):
    """Do not call the guard in this test: production execute_tasks must do so."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-fixture-never-used")
    before = "Hoy he conocido a Ana y a Luis."
    after = "Debo llamar a los dos."
    with live_product(Path(tmp_path) / "synthetic") as (repo, actor, product):
        executor = product.hybrid_candidate_execute
        schema = product.canonical_schema
        assert executor is not None
        people = tuple(
            KnowledgeUnit(
                SelectionCriteria(name, name, "person", (), None),
                "record",
                (),
                (),
                (f"He conocido a {name}.",),
                (),
            )
            for name in ("Ana", "Luis")
        )
        predecessor = execute_request(
            before,
            planner=SimpleNamespace(plan=lambda *_args: RequestPlan((WriteAction(people),), ())),
            repository=repo,
            schema=schema,
            context_index=executor.context_index,
            semantic_index=executor.semantic_index,
            embedder=executor.embedder,
            contextual_reasoner=executor.reasoner,
            authenticated_actor=actor,
            self_binding_repository=executor.bindings,
            actor=actor.stable_user_id,
            now=CLOCK,
            context_limit=10,
            request_id_factory=lambda: "e4-production-people-previous",
        )
        assert predecessor.status is ApplicationStatus.COMPLETED
        receipts = tuple(
            receipt
            for action in predecessor.action_results
            for receipt in action.canonical_direct_target_evidence
            if receipt.note_type == "person"
        )
        assert len(receipts) == 2
        target = TaskPersonReferenceSet(
            tuple(SourceBoundDependency(before, after, "los dos", p) for p in receipts),
            actor.stable_user_id,
        )
        source_task = KnowledgeUnit(
            SelectionCriteria("Llamar a los dos", "Llamar a los dos", "task", (), None),
            "record",
            (PropertyChange("status", "set", "pending"),),
            (),
            ("Llamar a los dos.",),
            (),
            force_create=True,
        )
        monkeypatch.setattr(
            composition.OpenAIRequestPlanner,
            "from_environment",
            classmethod(
                lambda _cls, *_args, **_kwargs: SimpleNamespace(
                    plan=lambda *_args: RequestPlan((WriteAction((source_task,)),), ())
                )
            ),
        )

        from odyssey_core import plural_task_readback

        original_verify = plural_task_readback.verify_plural_task_markdown
        modifications = []

        if corruption == "extra_person":
            create_entity(
                repo,
                schema,
                path="marta-foreign.md",
                entity_id="e4-foreign-person",
                metadata={"name": "Marta", "type": "person"},
                content="",
                actor="fixture",
                now=CLOCK,
            )

        def corrupt_then_verify(repository, schema_, result, dependencies):
            # Called from the production guard, AFTER the Writer persisted.
            matches = [
                path
                for path in repository.list_markdown_paths()
                if parse_note(repository.read_text(path)).metadata.get("type") == "task"
            ]
            assert len(matches) == 1
            original = repository.read_text(matches[0])
            marker = "|Ana]]"
            assert marker in original
            cut = original.index(marker)
            start = original.rfind("[[", 0, cut)
            link = original[start : cut + len(marker)]
            if corruption == "missing":
                updated = original[:start] + original[cut + len(marker) :]
            elif corruption == "duplicate":
                updated = original.replace(link, link + " " + link, 1)
            else:
                updated = original.replace(link, link + " [[marta-foreign|Marta]]", 1)
            repository.replace_text(matches[0], updated)
            modifications.append(matches[0])
            return original_verify(repository, schema_, result, dependencies)

        monkeypatch.setattr(
            plural_task_readback, "verify_plural_task_markdown", corrupt_then_verify
        )
        actual = executor.dependent_task_delegate(
            after,
            "e4-production-link-lost-after-write",
            actor,
            TaskInterpretation(after, TaskOperation.CREATE),
            None,
            target,
            datetime.fromisoformat(CLOCK),
        )
        assert modifications, "real composition postwrite readback was not invoked"
        assert actual.status is ApplicationStatus.PARTIAL
        assert actual.clarification_code == "DEPENDENT_PERSON_SET_PHYSICAL_READBACK_UNVERIFIED"
        assert any(
            parse_note(repo.read_text(path)).metadata.get("type") == "task"
            for path in modifications
        )
