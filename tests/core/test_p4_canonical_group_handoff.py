"""E2 N:M links are selected from physical Core Writer receipts, not Router IDs."""

from dataclasses import replace
from datetime import datetime
from types import SimpleNamespace

import pytest

from odyssey_core import create_entity
from odyssey_core.application import ApplicationStatus, execute_request
from odyssey_core.dependent_group_evidence import (
    CanonicalGroupEvidenceError,
    prove_canonical_group_handoff,
)
from odyssey_core.dependent_group_graph import verify_dependent_group_graph
from odyssey_core.notes import parse_note, serialize_note
from odyssey_core.request_planning import (
    KnowledgeReference,
    KnowledgeUnit,
    RequestPlan,
    SelectionCriteria,
    WriteAction,
)
from tests.core import test_p4_source_bound_dependency as source_dependency_tests
from tests.runtime.test_p4_dependent_router_integrated import (
    BEFORE,
    CLOCK,
    SCHEMA,
    _setup,
)

SECOND = "Ayer revisé Revisar contratos."
SHARED = " Ahora compara ambas tareas."
ANOTHER = " Y apunta algo sobre la primera."
SOURCE = BEFORE + " " + SECOND + SHARED + ANOTHER


def _reviewed_graph():
    groups = [
        {"capability": "core", "source_quote": BEFORE + " ", "dependencies": []},
        {"capability": "core", "source_quote": SECOND, "dependencies": []},
        {
            "capability": "tasks",
            "source_quote": SHARED,
            "dependencies": [
                {
                    "predecessor_index": 0,
                    "mention": "ambas tareas",
                    "antecedent_mention": "Preparar informe Atlas",
                },
                {
                    "predecessor_index": 1,
                    "mention": "ambas tareas",
                    "antecedent_mention": "Revisar contratos",
                },
            ],
        },
        {
            "capability": "tasks",
            "source_quote": ANOTHER,
            "dependencies": [
                {
                    "predecessor_index": 0,
                    "mention": "la primera",
                    "antecedent_mention": "Preparar informe Atlas",
                },
            ],
        },
    ]
    return verify_dependent_group_graph(
        SOURCE,
        {"full_source_quote": SOURCE, "groups": groups},
        {
            "full_source_quote": SOURCE,
            "complete": True,
            "dependency_edges_verified": True,
            "review_reason": "APPROVED",
            "failing_group_index": None,
            "groups": [dict(group) for group in groups],
        },
    )


@pytest.fixture
def written_predecessors(tmp_path):
    repo, actor, executor, runtime, calls, sessions = _setup(tmp_path)
    create_entity(
        repo,
        SCHEMA,
        path="other-task.md",
        entity_id="other-task",
        metadata={"name": "Revisar contratos", "type": "task", "status": "pending"},
        content="- Otra tarea.\n",
        actor="fixture",
        now=CLOCK,
    )
    executor.context_index.rebuild(repo, SCHEMA, executor.embedder)
    executor.semantic_index.rebuild(repo, SCHEMA, executor.embedder)
    assert executor.dependent_core_delegate is not None
    first = executor.dependent_core_delegate(
        BEFORE, "nm-predecessor-first", actor, datetime.fromisoformat(CLOCK)
    )
    assert first.status is ApplicationStatus.COMPLETED
    assert len(first.canonical_reference_evidence) == 1
    executor.refresh_affected_indexes(first.affected_stable_note_ids)

    primary = KnowledgeUnit(
        SelectionCriteria(None, "2026-10-15", "calendar_day", (), None),
        "record",
        (),
        (),
        ("Ayer revisé {{ref:0}}.",),
        (KnowledgeReference(1, "task", "Revisar contratos"),),
    )
    helper = KnowledgeUnit(
        SelectionCriteria("Revisar contratos", "Revisar contratos", "task", (), None),
        "record",
        (),
        (),
        (),
        (),
        reference_lookup_only=True,
    )
    second = execute_request(
        SECOND,
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
        request_id_factory=lambda: "nm-predecessor-second",
    )
    assert second.status is ApplicationStatus.COMPLETED, second
    assert len(second.canonical_reference_evidence) == 1
    return repo, _reviewed_graph(), first, second


def test_canonical_nm_many_to_one_and_one_to_many_read_real_markdown(written_predecessors):
    repo, graph, first, second = written_predecessors
    shared = prove_canonical_group_handoff(
        graph=graph,
        consumer_index=2,
        predecessors={0: first, 1: second},
        repository=repo,
        schema=SCHEMA,
    )
    ids = shared.require_all_current(repo, SCHEMA)
    assert ids == ("atlas-p4-dependent-task", "other-task")
    assert shared.edges[0].core_write_guard().mention == "ambas tareas"
    assert shared.edges[1].core_write_guard().mention == "ambas tareas"
    assert all(not hasattr(edge, "write") for edge in shared.edges)
    other = prove_canonical_group_handoff(
        graph=graph,
        consumer_index=3,
        predecessors={0: first, 1: second},
        repository=repo,
        schema=SCHEMA,
    )
    assert other.require_all_current(repo, SCHEMA) == ("atlas-p4-dependent-task",)
    assert shared.edges[0].evidence == other.edges[0].evidence
    assert first.canonical_reference_evidence[0].source_note_id in first.affected_stable_note_ids
    assert second.canonical_reference_evidence[0].source_note_id in second.affected_stable_note_ids


@pytest.mark.parametrize(
    "failure",
    [
        "missing_result",
        "wrong_result",
        "partial_result",
        "missing_actions",
        "fake_top_level",
        "stale_target",
        "stale_source",
        "deleted_target",
        "wrong_antecedent",
        "missing_source_link",
    ],
)
def test_nm_edge_missing_conflicting_or_stale_never_authorizes_consumer(
    written_predecessors, failure
):
    repo, graph, first, second = written_predecessors
    results = {0: first, 1: second}
    if failure == "missing_result":
        results.pop(1)
    elif failure == "wrong_result":
        results[1] = first
    elif failure == "partial_result":
        results[1] = replace(second, status=ApplicationStatus.PARTIAL)
    elif failure == "missing_actions":
        results[1] = replace(second, action_results=())
    elif failure == "fake_top_level":
        fake = replace(second.canonical_reference_evidence[0], stable_note_id="invented")
        results[1] = replace(second, canonical_reference_evidence=(fake,))
    elif failure == "wrong_antecedent":
        from dataclasses import replace as change

        from odyssey_core.dependent_group_graph import GroupDependency

        modified = list(graph.groups)
        modified[2] = change(
            modified[2],
            dependencies=(
                modified[2].dependencies[0],
                GroupDependency(1, "ambas tareas", "Preparar informe Atlas"),
            ),
        )
        graph = change(graph, groups=tuple(modified))
    elif failure == "missing_source_link":
        for path in repo.list_markdown_paths():
            note = parse_note(repo.read_text(path))
            if note.metadata.get("id") == second.canonical_reference_evidence[0].source_note_id:
                repo.replace_text(
                    path,
                    serialize_note(
                        replace(
                            note, content=note.content.replace("Revisar contratos", "Otro proyecto")
                        )
                    ),
                )
                break
    else:
        target_id = (
            first.canonical_reference_evidence[0].stable_note_id
            if failure == "stale_target"
            else second.canonical_reference_evidence[0].source_note_id
            if failure == "stale_source"
            else second.canonical_reference_evidence[0].stable_note_id
        )
        for path in repo.list_markdown_paths():
            note = parse_note(repo.read_text(path))
            if note.metadata.get("id") == target_id:
                update = (
                    replace(note, metadata={**note.metadata, "deleted": True})
                    if failure == "deleted_target"
                    else replace(note, content=note.content + "\n- external write\n")
                )
                repo.replace_text(path, serialize_note(update))
                break
    with pytest.raises(CanonicalGroupEvidenceError):
        prove_canonical_group_handoff(
            graph=graph,
            consumer_index=2,
            predecessors=results,
            repository=repo,
            schema=SCHEMA,
        )


def test_nm_handoff_rechecks_all_sources_immediately_before_consumer(written_predecessors):
    repo, graph, first, second = written_predecessors
    handoff = prove_canonical_group_handoff(
        graph=graph,
        consumer_index=2,
        predecessors={0: first, 1: second},
        repository=repo,
        schema=SCHEMA,
    )
    for path in repo.list_markdown_paths():
        note = parse_note(repo.read_text(path))
        if note.metadata.get("id") == first.canonical_reference_evidence[0].source_note_id:
            repo.replace_text(
                path, serialize_note(replace(note, content=note.content + "\n- different fact\n"))
            )
            break
    with pytest.raises(CanonicalGroupEvidenceError, match="stale"):
        handoff.require_all_current(repo, SCHEMA)


@pytest.mark.parametrize("single_anaphor", [False, True])
def test_two_real_core_links_in_one_antecedent_are_selected_by_exact_occurrence(
    tmp_path, single_anaphor
):
    """Multiple genuine links in one Core result must never choose the last."""
    from copy import deepcopy

    from tests.runtime.test_whole_source_light_product_p4 import _fixture

    repo, actor, executor, _runtime = _fixture(tmp_path, incremental_indexes=True)
    for label, ident in (
        ("Preparar informe Atlas", "alpha-note"),
        ("Revisar contratos", "beta-note"),
    ):
        create_entity(
            repo,
            SCHEMA,
            path=f"{ident}.md",
            entity_id=ident,
            metadata={"name": label, "type": "task", "status": "pending"},
            content="- Tarea anterior.\n",
            actor="fixture",
            now=CLOCK,
        )
    executor.context_index.rebuild(repo, SCHEMA, executor.embedder)
    executor.semantic_index.rebuild(repo, SCHEMA, executor.embedder)
    before = "Hoy revisé Preparar informe Atlas y Revisar contratos. "
    after = "Después organizo esa tarea." if single_anaphor else "Después organizo ambas tareas."
    children = (
        KnowledgeUnit(
            SelectionCriteria(None, "2026-10-16", "calendar_day", (), None),
            "record",
            (),
            (),
            ("Hoy revisé {{ref:0}} y {{ref:1}}.",),
            (
                KnowledgeReference(1, "task", "Preparar informe Atlas"),
                KnowledgeReference(2, "task", "Revisar contratos"),
            ),
        ),
        *(
            KnowledgeUnit(
                SelectionCriteria(name, name, "task", (), None),
                "record",
                (),
                (),
                (),
                (),
                reference_lookup_only=True,
            )
            for name in ("Preparar informe Atlas", "Revisar contratos")
        ),
    )
    result = execute_request(
        before.strip(),
        planner=SimpleNamespace(plan=lambda *_: RequestPlan((WriteAction(children),), ())),
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
        request_id_factory=lambda: "nm-two-links-one-source",
    )
    assert result.status is ApplicationStatus.COMPLETED, result
    proofs = result.action_results[0].canonical_reference_evidence
    assert len(proofs) == 2
    assert {proof.stable_note_id for proof in proofs} == {"alpha-note", "beta-note"}
    # Core retains both links; the 1:1 handoff must still reject their cardinality.
    assert len(result.canonical_reference_evidence) == 2
    groups = [
        {"capability": "core", "source_quote": before, "dependencies": []},
        {
            "capability": "tasks",
            "source_quote": after,
            "dependencies": (
                [
                    {
                        "predecessor_index": 0,
                        "mention": "esa tarea",
                        "antecedent_mention": "Preparar informe Atlas",
                    }
                ]
                if single_anaphor
                else [
                    {
                        "predecessor_index": 0,
                        "mention": "ambas tareas",
                        "antecedent_mention": "Preparar informe Atlas",
                    },
                    {
                        "predecessor_index": 0,
                        "mention": "ambas tareas",
                        "antecedent_mention": "Revisar contratos",
                    },
                ]
            ),
        },
    ]
    source = before + after
    graph = verify_dependent_group_graph(
        source,
        {"full_source_quote": source, "groups": groups},
        {
            "full_source_quote": source,
            "complete": True,
            "dependency_edges_verified": True,
            "review_reason": "APPROVED",
            "failing_group_index": None,
            "groups": deepcopy(groups),
        },
    )
    if single_anaphor:
        with pytest.raises(CanonicalGroupEvidenceError, match="uniquely identify"):
            prove_canonical_group_handoff(
                graph=graph,
                consumer_index=1,
                predecessors={0: result},
                repository=repo,
                schema=SCHEMA,
            )
        assert not any(
            parse_note(repo.read_text(path)).metadata.get("name") == "Después organizo esa tarea"
            for path in repo.list_markdown_paths()
        )
        return
    proof = prove_canonical_group_handoff(
        graph=graph,
        consumer_index=1,
        predecessors={0: result},
        repository=repo,
        schema=SCHEMA,
    )
    assert proof.require_all_current(repo, SCHEMA) == ("alpha-note", "beta-note")
    assert [e.antecedent_mention for e in proof.edges] == [
        "Preparar informe Atlas",
        "Revisar contratos",
    ]
    # A forged extra occurrence for one name MUST NOT be selected arbitrarily.
    forged = replace(result.action_results[0], canonical_reference_evidence=(*proofs, proofs[0]))
    with pytest.raises(CanonicalGroupEvidenceError):
        prove_canonical_group_handoff(
            graph=graph,
            consumer_index=1,
            predecessors={0: replace(result, action_results=(forged,))},
            repository=repo,
            schema=SCHEMA,
        )


@pytest.fixture
def grounded_person_reference(tmp_path):
    return source_dependency_tests.grounded_proof.__wrapped__(tmp_path)


@pytest.mark.parametrize("dependent", ["Ana", "ana", "lucía", "LUcía", "otra persona"])
def test_nm_single_core_person_never_links_unmatched_explicit_name(
    grounded_person_reference, dependent
):
    """Overconfident source-graph reviews cannot create wrong-person handoff."""
    repo, result, source = grounded_person_reference
    after = f" Después debo llamar a {dependent}."
    groups = [
        {"capability": "core", "source_quote": source, "dependencies": []},
        {
            "capability": "tasks",
            "source_quote": after,
            "dependencies": [
                {"predecessor_index": 0, "mention": dependent, "antecedent_mention": "Maya"}
            ],
        },
    ]
    full = source + after
    graph = verify_dependent_group_graph(
        full,
        {"full_source_quote": full, "groups": groups},
        {
            "full_source_quote": full,
            "complete": True,
            "dependency_edges_verified": True,
            "review_reason": "APPROVED",
            "failing_group_index": None,
            "groups": groups,
        },
    )
    with pytest.raises(CanonicalGroupEvidenceError, match="does not uniquely identify"):
        prove_canonical_group_handoff(
            graph=graph, consumer_index=1, predecessors={0: result}, repository=repo, schema=SCHEMA
        )
    assert not any(
        parse_note(repo.read_text(p)).metadata.get("type") == "task"
        for p in repo.list_markdown_paths()
    )


@pytest.mark.parametrize("dependent", ["ella", "Esa persona", "Maya"])
def test_nm_single_core_person_genuine_anaphor_or_name_still_passes(
    grounded_person_reference, dependent
):
    repo, result, source = grounded_person_reference
    after = f" Después debo llamar a {dependent}."
    groups = [
        {"capability": "core", "source_quote": source, "dependencies": []},
        {
            "capability": "tasks",
            "source_quote": after,
            "dependencies": [
                {"predecessor_index": 0, "mention": dependent, "antecedent_mention": "Maya"}
            ],
        },
    ]
    full = source + after
    graph = verify_dependent_group_graph(
        full,
        {"full_source_quote": full, "groups": groups},
        {
            "full_source_quote": full,
            "complete": True,
            "dependency_edges_verified": True,
            "review_reason": "APPROVED",
            "failing_group_index": None,
            "groups": groups,
        },
    )
    handoff = prove_canonical_group_handoff(
        graph=graph,
        consumer_index=1,
        predecessors={0: result},
        repository=repo,
        schema=SCHEMA,
    )
    assert handoff.require_all_current(repo, SCHEMA) == (
        result.canonical_reference_evidence[0].stable_note_id,
    )


def test_direct_finite_graph_cannot_omit_third_real_core_person_receipt(tmp_path):
    """A forged graph cannot bypass the prewrite veto after three physical Core writes."""
    from odyssey_core.dependent_group_graph import GroupDependency, ReviewedSourceGraph, SourceGroup
    from tests.runtime.test_whole_source_light_product_p4 import _fixture

    repo, actor, executor, _runtime = _fixture(tmp_path, incremental_indexes=True)
    names = ("Ana", "Luis", "Marta")
    predecessors = {}
    fragments = tuple(f"Hoy conocí a {name}. " for name in names)
    for i, (name, part) in enumerate(zip(names, fragments, strict=True)):
        unit = KnowledgeUnit(
            SelectionCriteria(name, name, "person", (), None),
            "record",
            (),
            (),
            (f"Conocí a {name}.",),
            (),
        )
        result = execute_request(
            part.strip(),
            planner=SimpleNamespace(plan=lambda *_, u=unit: RequestPlan((WriteAction((u,)),), ())),
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
            request_id_factory=lambda i=i: f"e4-three-person-predecessor-{i}",
        )
        assert result.status is ApplicationStatus.COMPLETED, result
        assert any(action.canonical_direct_target_evidence for action in result.action_results)
        predecessors[i] = result
        executor.refresh_affected_indexes(result.affected_stable_note_ids)
    after = "Mañana llamaré a los dos."
    graph = ReviewedSourceGraph(
        "".join(fragments) + after,
        (
            *(SourceGroup(i, "core", fragment, ()) for i, fragment in enumerate(fragments)),
            SourceGroup(
                3,
                "tasks",
                after,
                (
                    GroupDependency(0, "los dos", "Ana"),
                    GroupDependency(1, "los dos", "Luis"),
                ),
            ),
        ),
    )
    before = {path: repo.read_text(path) for path in repo.list_markdown_paths()}
    with pytest.raises(CanonicalGroupEvidenceError, match="omits an earlier Core"):
        prove_canonical_group_handoff(
            graph=graph,
            consumer_index=3,
            predecessors=predecessors,
            repository=repo,
            schema=SCHEMA,
        )
    assert {path: repo.read_text(path) for path in repo.list_markdown_paths()} == before
    assert sum(parse_note(text).metadata.get("type") == "person" for text in before.values()) >= 3
    assert not any(parse_note(text).metadata.get("type") == "task" for text in before.values())
