"""R0: Task CREATE cannot drop any Core-evidenced named source Note.

These are synthetic typed source hints and plans. Core/E3 preflight is still
required to turn a suggested helper into a canonical Markdown link.
"""

from types import SimpleNamespace

import pytest

from odyssey_apps.tasks import TaskCorePlanner, TaskInterpretation, TaskOperation
from odyssey_core.canonical_source_context import CanonicalSourceNameHint
from odyssey_core.request_planning import (
    KnowledgeReference,
    KnowledgeUnit,
    PropertyChange,
    RequestPlan,
    RequestPlanningError,
    SelectionCriteria,
    WriteAction,
)


def _task_with_source_hints(
    types,
    *,
    reversed_order=False,
    missing=frozenset(),
    wrong_type=None,
    wrong_name=None,
    omit_helper=False,
):
    named = [(f"Elemento {index:02d}", kind) for index, kind in enumerate(types)]
    if reversed_order:
        named.reverse()
    source = "Tengo que revisar " + ", ".join(name for name, _kind in named) + "."
    refs = []
    helpers = []
    for name, kind in named:
        if name in missing:
            continue
        index = len(helpers) + 1
        refs.append(KnowledgeReference(index, "reference", name))
        helpers.append(
            KnowledgeUnit(
                SelectionCriteria(
                    wrong_name or name, wrong_name or name, wrong_type or kind, (), None
                ),
                "record",
                (),
                (),
                (),
                (),
                reference_lookup_only=not omit_helper,
            )
        )
    primary = KnowledgeUnit(
        SelectionCriteria("Revisar elementos", "Revisar elementos", "task", (), None),
        "record",
        (PropertyChange("status", "set", "pending"),),
        (),
        ("Revisar elementos.",),
        tuple(refs),
        fact_temporal_anchors=((),),
    )
    existing = RequestPlan((WriteAction((primary, *helpers)),), ())
    wrapper = TaskCorePlanner(
        SimpleNamespace(plan=lambda *_: existing),
        TaskInterpretation(source, TaskOperation.CREATE),
    )
    wrapper.bind_verified_source_note_names(
        tuple(CanonicalSourceNameHint(name, name, kind) for name, kind in named)
    )
    return wrapper, source, named


@pytest.mark.parametrize(
    "types",
    [
        ("person",),
        ("project", "document"),
        ("concept", "project", "document", "person", "equipment"),
        (
            "project",
            "document",
            "concept",
            "person",
            "equipment",
            "document",
            "project",
            "concept",
            "person",
        ),
    ],
)
@pytest.mark.parametrize("reversed_order", [False, True])
def test_all_existing_named_source_notes_survive_task_plan(types, reversed_order):
    wrapper, source, named = _task_with_source_hints(types, reversed_order=reversed_order)
    result = wrapper.plan(source)
    primary, *helpers = result.actions[0].units
    assert len(helpers) == len(types)
    assert [reference.mention for reference in primary.references] == [
        name for name, _type in named
    ]
    assert [helper.target.type for helper in helpers] == [kind for _name, kind in named]


@pytest.mark.parametrize(
    "types",
    [
        ("project", "document"),
        ("person", "project", "document", "concept", "equipment"),
        (
            "project",
            "document",
            "concept",
            "person",
            "equipment",
            "document",
            "project",
            "concept",
            "person",
        ),
    ],
)
@pytest.mark.parametrize("reversed_order", [False, True])
def test_missing_one_source_note_fails_closed_instead_of_completing_partial_task(
    types, reversed_order
):
    entries = [(f"Elemento {index:02d}", kind) for index, kind in enumerate(types)]
    missing = {entries[len(entries) // 2][0]}
    wrapper, source, _named = _task_with_source_hints(
        types, reversed_order=reversed_order, missing=missing
    )
    with pytest.raises(RequestPlanningError, match="source.*identity|dropped"):
        wrapper.plan(source)


@pytest.mark.parametrize("kind", ["person", "project", "document", "concept", "equipment"])
def test_mismatched_note_type_never_satisfies_a_source_name_hint(kind):
    mismatch = "project" if kind != "project" else "document"
    wrapper, source, _named = _task_with_source_hints((kind,), wrong_type=mismatch)
    with pytest.raises(RequestPlanningError, match="source.*identity|dropped"):
        wrapper.plan(source)


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("drop_one", [False, True])
def test_actual_tasks_e3_write_preserves_verified_mixed_source_links_and_rejects_omission(
    tmp_path, reverse, drop_one
):
    """Actual Task CREATE → Core/E3 → Markdown/readback, with only model plan frozen."""
    from odyssey_apps.tasks import TaskLifecycleGuard
    from odyssey_core import create_entity
    from odyssey_core.application import ApplicationStatus, execute_request
    from odyssey_core.canonical_source_context import matching_canonical_names_in_source
    from odyssey_core.context import ContextIndex
    from odyssey_core.notes import parse_note
    from odyssey_core.semantic import SemanticEntityIndex
    from tests.apps.tasks.test_core_interop import Embedder, Reasoner
    from tests.runtime.test_whole_source_light_product_p4 import SCHEMA, _fixture

    repo, actor, service, _runtime = _fixture(tmp_path)
    types = (
        "person",
        "project",
        "document",
        "concept",
        "project",
        "document",
        "person",
        "concept",
        "project",
    )
    named = [(f"Recurso {idx:02d}", kind, f"asset-{idx}") for idx, kind in enumerate(types)]
    if reverse:
        named.reverse()
    for name, kind, stable_id in named:
        create_entity(
            repo,
            SCHEMA,
            path=f"{stable_id}.md",
            entity_id=stable_id,
            metadata={"name": name, "type": kind},
            content="",
            actor="fixture",
            now="2026-10-16T11:00:00+02:00",
        )
    source = "Tengo que revisar " + ", ".join(name for name, _, _ in named) + "."
    refs, helpers, markers = [], [], []
    for name, kind, _stable_id in named:
        if drop_one and name == "Recurso 04":
            continue
        idx = len(helpers)
        refs.append(KnowledgeReference(idx + 1, "reference", name))
        helpers.append(
            KnowledgeUnit(
                SelectionCriteria(name, name, kind, (), None),
                "record",
                (),
                (),
                (),
                (),
                reference_lookup_only=True,
            )
        )
        markers.append(f"{{{{ref:{idx}}}}}")
    primary = KnowledgeUnit(
        SelectionCriteria("Revisar elementos", "Revisar elementos", "task", (), None),
        "record",
        (PropertyChange("status", "set", "pending"),),
        (),
        ("Referencias: " + ", ".join(markers) + ".",),
        tuple(refs),
        fact_temporal_anchors=((),),
    )
    fake_plan = RequestPlan((WriteAction((primary, *helpers)),), ())
    hints = matching_canonical_names_in_source(source, repo, SCHEMA)
    assert len(hints) == len(named)
    # execute_request itself binds the current Core source hints exactly once.
    # A test that prebinds them here would bypass real production ownership.
    embedder = Embedder()
    context = ContextIndex(tmp_path / "task-mixed-context.sqlite")
    semantic = SemanticEntityIndex(tmp_path / "task-mixed-semantic.sqlite")
    context.rebuild(repo, SCHEMA, embedder)
    semantic.rebuild(repo, SCHEMA, embedder)

    def apply():
        # The production boundary binds verified source hints per fresh plan.
        wrapper = TaskCorePlanner(
            SimpleNamespace(plan=lambda *_: fake_plan),
            TaskInterpretation(source, TaskOperation.CREATE),
        )
        return execute_request(
            source,
            planner=wrapper,
            repository=repo,
            schema=SCHEMA,
            context_index=context,
            semantic_index=semantic,
            embedder=embedder,
            contextual_reasoner=Reasoner(),
            authenticated_actor=actor,
            self_binding_repository=service.bindings,
            actor=actor.stable_user_id,
            now="2026-10-16T13:00:00+02:00",
            context_limit=10,
            write_preflight_guard=TaskLifecycleGuard(TaskOperation.CREATE),
            request_id_factory=lambda: "mixed-source-task-create",
        )

    before = {p: repo.read_text(p) for p in repo.list_markdown_paths()}
    outcome = apply()
    if drop_one:
        assert outcome.status is not ApplicationStatus.COMPLETED
        assert {p: repo.read_text(p) for p in repo.list_markdown_paths()} == before
        return
    assert outcome.status is ApplicationStatus.COMPLETED, (outcome.status, outcome.planning_error)
    task_paths = [
        p
        for p in repo.list_markdown_paths()
        if parse_note(repo.read_text(p)).metadata.get("type") == "task"
    ]
    assert len(task_paths) == 1
    task = parse_note(repo.read_text(task_paths[0]))
    assert task.metadata["status"] == "pending"
    assert all(f"[[{stable_id}|{name}]]" in task.content for name, _kind, stable_id in named)
    # Bare Core CREATE does not own delivery-idempotence. Existing production
    # P4 LocalDeliveryResultStore tests prove the actual replay boundary.
    # Calling bare Core CREATE a second time would itself create another Task.


@pytest.mark.parametrize("bad_evidence", ["wrong_canonical", "not_lookup", "unlinked"])
@pytest.mark.parametrize("kind", ["project", "document", "person", "concept", "equipment"])
def test_core_source_note_completeness_rejects_wrong_helper_kind_identity_or_absent_link(
    bad_evidence, kind
):
    kwargs = (
        {"wrong_name": "Otras notas"}
        if bad_evidence == "wrong_canonical"
        else {"omit_helper": True}
        if bad_evidence == "not_lookup"
        else {"missing": frozenset({"Elemento 00"})}
    )
    wrapper, source, _names = _task_with_source_hints((kind,), **kwargs)
    with pytest.raises(RequestPlanningError, match="source.*identity|dropped|primary task target"):
        wrapper.plan(source)
