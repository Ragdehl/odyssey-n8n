"""An omitted earlier alias-linked Person cannot be ignored by an E4 finite cohort."""

from types import SimpleNamespace

import pytest

from odyssey_core import create_entity
from odyssey_core.application import ApplicationStatus, execute_request
from odyssey_core.dependent_group_evidence import (
    CanonicalGroupEvidenceError,
    prove_canonical_group_handoff,
)
from odyssey_core.dependent_group_graph import GroupDependency, ReviewedSourceGraph, SourceGroup
from odyssey_core.notes import parse_note
from odyssey_core.request_planning import (
    KnowledgeReference,
    KnowledgeUnit,
    RequestPlan,
    SelectionCriteria,
    WriteAction,
)
from tests.runtime.test_p4_fresh_person_task import CLOCK
from tests.runtime.test_p4_plural_person_full_vertical import (
    AFTER,
    BEFORE,
    runtime_with_plural_recording,
)
from tests.runtime.test_whole_source_light_product_p4 import SCHEMA


def test_alias_linked_extra_person_is_vetoed_with_real_core_receipt(tmp_path):
    repo, actor, executor, product, _records = runtime_with_plural_recording(tmp_path)
    create_entity(
        repo,
        SCHEMA,
        path="maria-garcia.md",
        entity_id="maria-garcia-extra",
        metadata={"name": "María García", "type": "person", "aliases": ["Mari"]},
        content="",
        actor="fixture",
        now=CLOCK,
    )
    executor.context_index.rebuild(repo, SCHEMA, executor.embedder)
    executor.semantic_index.rebuild(repo, SCHEMA, executor.embedder)
    earlier = "Ayer hablé con Mari. "
    primary = KnowledgeUnit(
        SelectionCriteria(None, "2026-10-15", "calendar_day", (), None),
        "record",
        (),
        (),
        ("Ayer hablé con {{ref:0}}.",),
        (KnowledgeReference(1, "person", "Mari"),),
    )
    helper = KnowledgeUnit(
        SelectionCriteria("María García", "María García", "person", (), None),
        "record",
        (),
        (),
        (),
        (),
        reference_lookup_only=True,
    )
    first = execute_request(
        earlier.strip(),
        planner=SimpleNamespace(plan=lambda *_: RequestPlan((WriteAction((primary, helper)),), ())),
        repository=repo,
        schema=SCHEMA,
        context_index=executor.context_index,
        semantic_index=executor.semantic_index,
        embedder=executor.embedder,
        contextual_reasoner=executor.reasoner,
        authenticated_actor=actor,
        self_binding_repository=executor.bindings,
        actor=actor.stable_user_id,
        now=CLOCK,
        context_limit=10,
        request_id_factory=lambda: "e4-aliased-prior-core-20261021",
    )
    assert first.status is ApplicationStatus.COMPLETED, first
    assert any(
        "[[maria-garcia|María García]]" in parse_note(repo.read_text(path)).content
        and first.request_id in parse_note(repo.read_text(path)).content
        for path in repo.list_markdown_paths()
    ), "Canonical Writer must have physically linked the aliased Person"
    # Alias links may lack an E2 carrier; the physical verifier must not
    # confuse missing evidence with proof of an absent Person.
    assert not first.canonical_reference_evidence
    # For the selected cohort, use real materialized Core receipts.
    capture = []
    actual = executor.dependent_core_delegate

    def saved(*args):
        value = actual(*args)
        capture.append(value)
        return value

    executor.dependent_core_delegate = saved
    r = product.execute_product(BEFORE + AFTER, "e4-alias-selected-cohort", "main", actor)
    assert r["status"] == "completed" and len(capture) == 1
    graph = ReviewedSourceGraph(
        earlier + BEFORE + AFTER,
        (
            SourceGroup(0, "core", earlier, ()),
            SourceGroup(1, "core", BEFORE, ()),
            SourceGroup(
                2,
                "tasks",
                AFTER,
                (GroupDependency(1, "los dos", "Ana"), GroupDependency(1, "los dos", "Luis")),
            ),
        ),
    )
    # The physical verifier examines each earlier Core receipt. It must veto
    # the alias proof independently of the canonical display name.
    with pytest.raises(CanonicalGroupEvidenceError, match="earlier Core Person"):
        prove_canonical_group_handoff(
            graph=graph,
            consumer_index=2,
            predecessors={0: first, 1: capture[0]},
            repository=repo,
            schema=SCHEMA,
        )
