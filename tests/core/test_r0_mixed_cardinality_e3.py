"""R0: arbitrary typed canonical reference sets use one existing Core/E3 writer.

All Notes and receipts are physically written to a disposable Markdown vault.
No production model, router, n8n, browser or personal data participates.
"""

from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

import pytest

from odyssey_core import create_entity
from odyssey_core.application import (
    ApplicationStatus,
    DependentReferenceGuard,
    DependentReferenceSetGuard,
    WritePreflightGuardError,
    execute_request,
)
from odyssey_core.context import ContextIndex
from odyssey_core.dependent_group_evidence import prove_canonical_group_handoff
from odyssey_core.dependent_group_graph import (
    DependentGroupGraphError,
    verify_dependent_group_graph,
)
from odyssey_core.notes import parse_note
from odyssey_core.request_planning import (
    KnowledgeReference,
    KnowledgeUnit,
    RequestPlan,
    SelectionCriteria,
    WriteAction,
)
from odyssey_core.semantic import SemanticEntityIndex
from tests.apps.tasks.test_core_interop import Embedder, Reasoner
from tests.runtime.test_whole_source_light_product_p4 import SCHEMA, _fixture


def _core(tmp_path, *, reverse=False, custom_type=False):
    repo, actor, service, _runtime = _fixture(tmp_path)
    schema = deepcopy(SCHEMA)
    if custom_type:
        new_type = deepcopy(next(t for t in schema["types"] if t["id"] == "concept"))
        new_type["id"] = "equipment"
        new_type["name"] = "Equipment"
        schema["types"].append(new_type)
    types = ("concept", "project", "document", "person")
    entries = [
        (
            f"Recurso {i:02d}",
            "equipment" if custom_type and i == 8 else types[i % len(types)],
            f"known-ref-{i}",
        )
        for i in range(9)
    ]
    if reverse:
        entries.reverse()
    for name, note_type, note_id in entries:
        create_entity(
            repo,
            schema,
            path=f"{note_id}.md",
            entity_id=note_id,
            metadata={"name": name, "type": note_type},
            content="",
            actor="fixture",
            now="2026-10-16T11:00:00+02:00",
        )
    for name, suffix in (("Origen del conjunto", "source"), ("Destino del conjunto", "target")):
        create_entity(
            repo,
            schema,
            path=f"{suffix}.md",
            entity_id=f"set-{suffix}",
            metadata={"name": name, "type": "concept"},
            content="",
            actor="fixture",
            now="2026-10-16T11:00:00+02:00",
        )
    embedder = Embedder()
    context = ContextIndex(tmp_path / "r0-mixed-context.sqlite3")
    semantic = SemanticEntityIndex(tmp_path / "r0-mixed-semantic.sqlite3")
    context.rebuild(repo, schema, embedder)
    semantic.rebuild(repo, schema, embedder)

    def write(action, delivery, source, guard=None):
        return execute_request(
            source,
            planner=SimpleNamespace(plan=lambda *_: RequestPlan((action,), ())),
            repository=repo,
            schema=schema,
            context_index=context,
            semantic_index=semantic,
            embedder=embedder,
            contextual_reasoner=Reasoner(),
            authenticated_actor=actor,
            self_binding_repository=service.bindings,
            actor=actor.stable_user_id,
            now="2026-10-16T13:00:00+02:00",
            context_limit=10,
            write_preflight_guard=guard,
            request_id_factory=lambda: delivery,
        )

    def action(owner, mention="explicit", omit_last=False):
        selected = entries[:-1] if omit_last else entries
        label = "Origen del conjunto" if owner == "source" else "Destino del conjunto"
        refs = tuple(
            KnowledgeReference(i + 1, typ, name if mention == "explicit" else mention)
            for i, (name, typ, _id) in enumerate(selected)
        )
        helpers = tuple(
            KnowledgeUnit(
                SelectionCriteria(name, name, typ, (), None),
                "record",
                (),
                (),
                (),
                (),
                reference_lookup_only=True,
            )
            for name, typ, _id in entries
        )
        fact = "Verificados: " + ", ".join(f"{{{{ref:{i}}}}}" for i in range(len(selected))) + "."
        unit = KnowledgeUnit(
            SelectionCriteria(label, label, "concept", (), None),
            "record",
            (),
            (),
            (fact,),
            refs,
        )
        return WriteAction((unit, *helpers))

    return repo, schema, entries, write, action


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("custom_type", [False, True])
def test_nine_mixed_note_types_uses_core_receipts_guard_and_physical_e3_replay(
    tmp_path, reverse, custom_type
):
    repo, schema, entries, execute, build = _core(
        tmp_path, reverse=reverse, custom_type=custom_type
    )
    source = "He revisado " + ", ".join(name for name, _typ, _id in entries) + "."
    followup = " Prepara un resumen de ellos."
    predecessor = execute(build("source"), "r0-source-9", source)
    assert predecessor.status is ApplicationStatus.COMPLETED, predecessor.planning_error
    proofs = predecessor.action_results[0].canonical_reference_evidence
    assert len(proofs) == 9
    assert {p.note_type for p in proofs} == (
        {"concept", "project", "document", "person", "equipment"}
        if custom_type
        else {"concept", "project", "document", "person"}
    )
    assert all(
        f"[[{note_id}|{name}]]" in parse_note(repo.read_text("source.md")).content
        for name, _note_type, note_id in entries
    )
    groups = [
        {"capability": "core", "source_quote": source + " ", "dependencies": []},
        {
            "capability": "tasks",
            "source_quote": followup.lstrip(),
            "dependencies": [
                {"predecessor_index": 0, "mention": "ellos", "antecedent_mention": name}
                for name, _type, _id in entries
            ],
        },
    ]
    original = source + " " + followup.lstrip()
    proposal = {"full_source_quote": original, "groups": groups}
    review = {
        "full_source_quote": original,
        "complete": True,
        "dependency_edges_verified": True,
        "review_reason": "APPROVED",
        "failing_group_index": None,
        "groups": deepcopy(groups),
    }
    graph = verify_dependent_group_graph(original, proposal, review)
    handoff = prove_canonical_group_handoff(
        graph=graph,
        consumer_index=1,
        predecessors={0: predecessor},
        repository=repo,
        schema=schema,
    )
    assert handoff.require_all_current(repo, schema) == tuple(note_id for _, _, note_id in entries)
    guards = DependentReferenceSetGuard(tuple(edge.core_write_guard() for edge in handoff.edges))
    mismatched = deepcopy(review)
    mismatched["groups"][1]["dependencies"].pop()
    with pytest.raises(DependentGroupGraphError):
        verify_dependent_group_graph(original, proposal, mismatched)
    destination = build("target", mention="ellos")
    result = execute(destination, "r0-target-9", "Compila el resumen de ellos.", guards)
    assert result.status is ApplicationStatus.COMPLETED, (result.status, result.planning_error)
    content = parse_note(repo.read_text("target.md")).content
    for name, _note_type, note_id in entries:
        assert f"[[{note_id}|{name}]]" in content
    before = {p: repo.read_text(p) for p in repo.list_markdown_paths()}
    retry = execute(destination, "r0-target-9", "Compila el resumen de ellos.", guards)
    assert retry.status is ApplicationStatus.COMPLETED
    assert {p: repo.read_text(p) for p in repo.list_markdown_paths()} == before
    # A missing or incorrectly rebound link must be blocked before E3 writes.
    with pytest.raises(WritePreflightGuardError, match="REFERENCE_MARKER"):
        guards(
            build("target", mention="ellos", omit_last=True),
            tuple(
                SimpleNamespace(
                    unit_index=i,
                    stable_id=("set-target" if i == 0 else entries[i - 1][2]),
                    canonical_name=("Destino del conjunto" if i == 0 else entries[i - 1][0]),
                )
                for i in range(10)
            ),
            repo,
            schema,
        )
    assert {p: repo.read_text(p) for p in repo.list_markdown_paths()} == before


@pytest.mark.parametrize("missing_index", [0, 4, 8])
def test_nine_refs_guard_fails_closed_on_substituted_canonical_identity(tmp_path, missing_index):
    repo, schema, entries, execute, build = _core(tmp_path)
    predecessor = execute(build("source"), "r0-source-stale", "Compruebo los nueve recursos.")
    assert predecessor.status is ApplicationStatus.COMPLETED
    proofs = predecessor.action_results[0].canonical_reference_evidence
    guards = DependentReferenceSetGuard(tuple(DependentReferenceGuard("ellos", p) for p in proofs))
    preflight = [
        SimpleNamespace(unit_index=0, stable_id="set-target", canonical_name="Destino del conjunto")
    ]
    preflight.extend(
        SimpleNamespace(unit_index=i + 1, stable_id=note_id, canonical_name=name)
        for i, (name, _typ, note_id) in enumerate(entries)
    )
    altered = list(preflight)
    idx = missing_index + 1
    altered[idx] = SimpleNamespace(
        unit_index=idx,
        stable_id=entries[(missing_index + 1) % 9][2],
        canonical_name=entries[(missing_index + 1) % 9][0],
    )
    before = {p: repo.read_text(p) for p in repo.list_markdown_paths()}
    with pytest.raises(WritePreflightGuardError, match="REFERENCE_MARKER"):
        guards(build("target", mention="ellos"), tuple(altered), repo, schema)
    assert {p: repo.read_text(p) for p in repo.list_markdown_paths()} == before


def test_e3_refuses_nine_link_write_if_one_actual_source_note_changed(tmp_path):
    """A real canonical edit after source proof invalidates the whole E3 set."""
    from odyssey_core.persistence import update_entity

    repo, schema, entries, execute, build = _core(tmp_path)
    predecessor = execute(build("source"), "r0-source-before-edited", "Compruebo los recursos.")
    assert predecessor.status is ApplicationStatus.COMPLETED
    proofs = predecessor.action_results[0].canonical_reference_evidence
    guards = DependentReferenceSetGuard(tuple(DependentReferenceGuard("ellos", p) for p in proofs))
    update_entity(
        repo,
        schema,
        path=f"{entries[4][2]}.md",
        expected_id=entries[4][2],
        set_metadata={},
        content="Se modificó después de comprobarla.",
        actor="fixture",
        now="2026-10-16T14:00:00+02:00",
    )
    before_target = repo.read_text("target.md")
    result = execute(
        build("target", mention="ellos"), "r0-target-after-edited", "Resume ellos.", guards
    )
    assert result.status is not ApplicationStatus.COMPLETED
    assert repo.read_text("target.md") == before_target


def test_core_guard_checks_each_distinct_mention_without_shared_word_or_note_type(tmp_path):
    """Each reference can have its own exact source mention and canonical type."""
    repo, schema, entries, execute, build = _core(tmp_path, custom_type=True)
    predecessor = execute(
        build("source"), "r0-source-independent-names", "Compruebo cada referencia."
    )
    assert predecessor.status is ApplicationStatus.COMPLETED
    proofs = predecessor.action_results[0].canonical_reference_evidence
    guards = DependentReferenceSetGuard(
        tuple(
            DependentReferenceGuard(name, proof)
            for (name, _typ, _id), proof in zip(entries, proofs, strict=True)
        )
    )
    result = execute(
        build("target", mention="explicit"),
        "r0-target-independent-names",
        "Relaciona todas las referencias.",
        guards,
    )
    assert result.status is ApplicationStatus.COMPLETED, result.planning_error
    content = parse_note(repo.read_text("target.md")).content
    assert all(f"[[{note_id}|{name}]]" in content for name, _typ, note_id in entries)
    with pytest.raises(WritePreflightGuardError, match="SET_INVALID"):
        DependentReferenceSetGuard((*guards.guards, guards.guards[0]))
