"""R0: show the existing generic Core owner vs the P4 owner-loss boundary.

Synthetic vault and recorded model outputs ONLY. This is a diagnosis of an
unresolved product gap, not a declaration that P4 can write arbitrary owners.
"""

from __future__ import annotations

import pytest

from odyssey_core import create_entity
from odyssey_core.notes import parse_note
from odyssey_core.semantic_write import (
    ApplyTo,
    IdentityBinding,
    IdentityIntent,
    LiteralPart,
    SemanticFact,
    SemanticWriteIntent,
    SemanticWriteOperation,
    compile_semantic_write,
)
from tests.runtime.test_whole_source_light_product_p4 import RecordedClient, _fixture, _speaker


@pytest.mark.parametrize(
    ("note_type", "source", "fact_text"),
    [
        ("project", "El proyecto Atlas tiene prioridad alta.", "Tiene prioridad alta."),
        ("document", "Atlas requiere una revisión.", "Requiere una revisión."),
        ("concept", "Atlas requiere una revisión.", "Requiere una revisión."),
    ],
)
def test_existing_core_can_target_a_note_but_p4_must_not_claim_unowned_fact_saved(
    tmp_path, note_type, source, fact_text
):
    repo, actor, service, runtime = _fixture(tmp_path)
    create_entity(
        repo,
        service.schema,
        path="Atlas.md",
        entity_id="atlas-id",
        metadata={"name": "Atlas", "type": note_type},
        content="",
        actor="fixture",
        now="2026-10-16T11:00:00+02:00",
    )
    # Existing Core semantic writer correctly represents the owner without
    # creating an identity, app-specific note handler or second writer.
    semantic = SemanticWriteIntent(
        (
            SemanticWriteOperation(
                IdentityIntent("Atlas", IdentityBinding.DESCRIBED, "Atlas", note_type),
                ApplyTo.ONE,
                "record",
                (SemanticFact((LiteralPart(fact_text),)),),
                (),
                (),
                None,
            ),
        )
    )
    compiled = compile_semantic_write(semantic, service.schema)
    assert len(compiled.units) == 1
    assert compiled.units[0].target.type == note_type
    assert compiled.units[0].target.entity == "Atlas"
    assert compiled.units[0].facts == (fact_text,)

    # In the P4 whole-source path, the current reviewer *does* preserve the
    # source and identity proposal, but the old compiler has only Day/SELF
    # owners. It must not silently rewrite a third-party fact into SELF.
    route = {
        "capabilities": ["core"],
        "interpretation": "joint",
        "reason": "single",
        "self_relation_span": None,
        "app_scopes": [],
    }
    proposal = {
        "entities": [
            {
                "mention": "Atlas",
                "canonical_name": None,
                "note_type": note_type,
                "confidence": "explicit",
            }
        ],
        "facts": [
            {
                "meaning": source,
                "kind": "record",
                "subject": "Atlas",
                "date": None,
                "daypart": None,
                "participants": [],
                "source_evidence": source,
                "dependent_on_fact_index": None,
                "needs_clarification": False,
            }
        ],
        "unresolved": [],
    }
    reviewed = {
        "approved": True,
        "complete": True,
        "reason": None,
        "facts": [
            {
                "ordinal": 0,
                "source_quote": source,
                "kind": "record",
                "reviewed_text": fact_text,
                "date": None,
                "reference_names": [],
                "supported": True,
            }
        ],
    }
    service.client = RecordedClient(
        [
            route,
            proposal,
            reviewed,
            _speaker(source, proposal, role="other", base=1),
            _speaker(source, proposal, role="other"),
        ]
    )
    before = {path: repo.read_text(path) for path in repo.list_markdown_paths()}
    outcome = runtime.execute_product(source, f"owner-gap-{note_type}", "main", actor)
    assert outcome["status"] == "needs_attention", outcome
    assert {path: repo.read_text(path) for path in repo.list_markdown_paths()} == before
    assert not parse_note(repo.read_text("Atlas.md")).content
    replay = runtime.execute_product(source, f"owner-gap-{note_type}", "main", actor)
    assert replay["delivery_replayed"] is True


@pytest.mark.parametrize("note_type", ["project", "document", "concept"])
def test_existing_core_owner_plan_writes_to_its_real_note_and_reuses_e3(tmp_path, note_type):
    """Positive R31 control: existing Core, not a second P4 writer, owns delivery."""
    from types import SimpleNamespace

    from odyssey_core.application import ApplicationStatus, execute_request
    from odyssey_core.request_planning import RequestPlan

    repo, actor, service, _runtime = _fixture(tmp_path)
    create_entity(
        repo,
        service.schema,
        path="Atlas.md",
        entity_id="atlas-id",
        metadata={"name": "Atlas", "type": note_type},
        content="",
        actor="fixture",
        now="2026-10-16T11:00:00+02:00",
    )
    service.refresh_affected_indexes(("atlas-id",))
    semantic = SemanticWriteIntent(
        (
            SemanticWriteOperation(
                IdentityIntent("Atlas", IdentityBinding.DESCRIBED, "Atlas", note_type),
                ApplyTo.ONE,
                "record",
                (SemanticFact((LiteralPart("Tiene prioridad alta."),)),),
                (),
                (),
                None,
            ),
        )
    )
    action = compile_semantic_write(semantic, service.schema)
    before_self = repo.read_text("self.md")
    result = execute_request(
        "El proyecto Atlas tiene prioridad alta.",
        planner=SimpleNamespace(plan=lambda *_args: RequestPlan((action,), ())),
        repository=repo,
        schema=service.schema,
        context_index=service.context_index,
        semantic_index=service.semantic_index,
        embedder=service.embedder,
        contextual_reasoner=service.reasoner,
        actor=actor.stable_user_id,
        now="2026-10-16T15:30:00+02:00",
        context_limit=10,
        authenticated_actor=actor,
        self_binding_repository=service.bindings,
        request_id_factory=lambda: f"core-owner-{note_type}",
    )
    assert result.status is ApplicationStatus.COMPLETED, result
    assert result.affected_stable_note_ids == ("atlas-id",)
    assert "Tiene prioridad alta." in parse_note(repo.read_text("Atlas.md")).content
    assert repo.read_text("self.md") == before_self
    assert repo.list_markdown_paths() == ["Atlas.md", "calendar/days/2026-10-16.md", "self.md"]
    # The extra Day is Core's canonical capture backlink, not a second
    # owner for the statement or an invented identity.
    assert "Tiene prioridad alta." not in repo.read_text("self.md")


@pytest.mark.parametrize("note_type", ["person", "project", "document", "concept"])
@pytest.mark.parametrize("reversed_order", [False, True])
def test_opt_in_existing_core_owner_routes_any_note_type_with_self_fact_and_replay(
    tmp_path, note_type, reversed_order
):
    """A reviewed source owner and SELF fact retain both destinations in either order.

    This is frozen/synthetic model output, NOT a real-model approval of the
    new reviewer prompt. Default P4 behavior stays unchanged.
    """
    repo, actor, service, runtime = _fixture(tmp_path)
    name = f"Entidad-{note_type}"
    create_entity(
        repo,
        service.schema,
        path=f"{name}.md",
        entity_id="existing-owner",
        metadata={"name": name, "type": note_type},
        content="",
        actor="fixture",
        now="2026-10-16T11:00:00+02:00",
    )
    service.refresh_affected_indexes(("existing-owner",))
    service.owner_review_enabled = True
    entries = [
        (f"{name} tiene prioridad alta.", "Tiene prioridad alta.", name, "other"),
        ("Me gusta leer por la noche.", "Me gusta leer por la noche.", None, "self_participant"),
    ]
    if reversed_order:
        entries.reverse()
    source = " ".join(item[0] for item in entries)
    route = {
        "capabilities": ["core"],
        "interpretation": "joint",
        "reason": "single",
        "self_relation_span": None,
        "app_scopes": [],
    }
    proposal = {
        "entities": [
            {
                "mention": name,
                "canonical_name": None,
                "note_type": note_type,
                "confidence": "explicit",
            }
        ],
        "facts": [
            {
                "meaning": quoted,
                "kind": "record",
                "subject": owner or "yo",
                "date": None,
                "daypart": None,
                "participants": [],
                "source_evidence": quoted,
                "dependent_on_fact_index": None,
                "needs_clarification": False,
            }
            for quoted, _text, owner, _role in entries
        ],
        "unresolved": [],
    }
    reviewed = {
        "approved": True,
        "complete": True,
        "reason": None,
        "facts": [
            {
                "ordinal": i,
                "source_quote": quoted,
                "kind": "record",
                "reviewed_text": text,
                "date": None,
                "reference_names": [],
                "owner_name": owner,
                "supported": True,
            }
            for i, (quoted, text, owner, _role) in enumerate(entries)
        ],
    }

    def speakers(base):
        return {
            "facts": [
                {"ordinal": i + base, "source_quote": quoted, "role": role, "assertion": "asserted"}
                for i, (quoted, _text, _owner, role) in enumerate(entries)
            ]
        }

    service.client = RecordedClient([route, proposal, reviewed, speakers(1), speakers(0)])
    outcome = runtime.execute_product(
        source, f"owner-positive-{note_type}-{reversed_order}", "main", actor
    )
    assert outcome["status"] == "completed", (outcome, service.client.calls)
    assert "owner_review" in str(service.client.calls)
    assert "Tiene prioridad alta." in parse_note(repo.read_text(f"{name}.md")).content
    assert "Me gusta leer por la noche." in parse_note(repo.read_text("self.md")).content
    assert "Tiene prioridad alta." not in parse_note(repo.read_text("self.md")).content
    assert "Me gusta leer por la noche." not in parse_note(repo.read_text(f"{name}.md")).content
    before = {path: repo.read_text(path) for path in repo.list_markdown_paths()}
    replay = runtime.execute_product(
        source, f"owner-positive-{note_type}-{reversed_order}", "main", actor
    )
    assert replay["delivery_replayed"] is True
    assert {path: repo.read_text(path) for path in repo.list_markdown_paths()} == before


@pytest.mark.parametrize(
    "rejection",
    [
        "wrong_owner",
        "missing_owner",
        "unknown_canonical",
        "ambiguous_canonical",
        "self_conflict",
    ],
)
def test_opt_in_owner_review_rejects_unproven_or_ambiguous_destination_without_writes(
    tmp_path, rejection
):
    repo, actor, service, runtime = _fixture(tmp_path)
    existing_name = "Pieza A"
    create_entity(
        repo,
        service.schema,
        path="Pieza A.md",
        entity_id="piece-1",
        metadata={"name": existing_name, "type": "project"},
        content="",
        actor="fixture",
        now="2026-10-16T11:00:00+02:00",
    )
    if rejection == "ambiguous_canonical":
        create_entity(
            repo,
            service.schema,
            path="Pieza A copia.md",
            entity_id="piece-2",
            metadata={"name": existing_name, "type": "document"},
            content="",
            actor="fixture",
            now="2026-10-16T11:00:00+02:00",
        )
    service.refresh_affected_indexes(("piece-1",))
    service.owner_review_enabled = True
    source = f"{existing_name} necesita revisión."
    owner = (
        "Persona inventada"
        if rejection == "unknown_canonical"
        else "Otra persona"
        if rejection == "wrong_owner"
        else None
        if rejection == "missing_owner"
        else existing_name
    )
    planner = {
        "entities": [
            {
                "mention": existing_name,
                "canonical_name": None,
                "note_type": "project",
                "confidence": "explicit",
            }
        ],
        "facts": [
            {
                "meaning": source,
                "kind": "record",
                "subject": existing_name,
                "date": None,
                "daypart": None,
                "participants": [],
                "source_evidence": source,
                "dependent_on_fact_index": None,
                "needs_clarification": False,
            }
        ],
        "unresolved": [],
    }
    review = {
        "approved": True,
        "complete": True,
        "reason": None,
        "facts": [
            {
                "ordinal": 0,
                "source_quote": source,
                "kind": "record",
                "reviewed_text": "Necesita revisión.",
                "date": None,
                "reference_names": [],
                "supported": True,
                "owner_name": owner,
            }
        ],
    }
    role = "self_participant" if rejection == "self_conflict" else "other"
    speaker = _speaker(source, planner, role=role)
    service.client = RecordedClient(
        [
            {
                "capabilities": ["core"],
                "interpretation": "joint",
                "reason": "single",
                "self_relation_span": None,
                "app_scopes": [],
            },
            planner,
            review,
            _speaker(source, planner, role=role, base=1),
            speaker,
        ]
    )
    before = {path: repo.read_text(path) for path in repo.list_markdown_paths()}
    result = runtime.execute_product(source, f"owner-negative-{rejection}", "main", actor)
    assert result["status"] == "needs_attention", (result, service.client.calls)
    assert {path: repo.read_text(path) for path in repo.list_markdown_paths()} == before


@pytest.mark.parametrize("reversed_order", [False, True])
def test_opt_in_core_owner_groups_many_facts_under_user_defined_schema_type(
    tmp_path, reversed_order
):
    """Two different facts → one existing user-defined note, no NoteSchema branch."""
    from copy import deepcopy

    from odyssey_core.atomic_facts import parse_atomic_facts
    from odyssey_core.identity_boundary import SelfBindingRepository

    repo, actor, service, runtime = _fixture(tmp_path)
    dynamic_schema = deepcopy(service.schema)
    new_type = deepcopy(next(row for row in dynamic_schema["types"] if row["id"] == "concept"))
    new_type["id"] = "equipment"
    new_type["name"] = "Equipment"
    dynamic_schema["types"].append(new_type)
    service.schema = dynamic_schema
    service.bindings = SelfBindingRepository(tmp_path / "state", repo, dynamic_schema)
    name = "Equipo Delta"
    create_entity(
        repo,
        dynamic_schema,
        path="Equipo Delta.md",
        entity_id="equipment-id",
        metadata={"name": name, "type": "equipment"},
        content="",
        actor="fixture",
        now="2026-10-16T11:00:00+02:00",
    )
    service.context_index.rebuild(repo, dynamic_schema, service.embedder)
    service.semantic_index.rebuild(repo, dynamic_schema, service.embedder)
    service.owner_review_enabled = True
    entries = [
        (f"{name} pesa cinco kilos.", "Pesa cinco kilos."),
        (f"{name} necesita mantenimiento.", "Necesita mantenimiento."),
    ]
    if reversed_order:
        entries.reverse()
    source = " ".join(quote for quote, _text in entries)
    proposal = {
        "entities": [
            {
                "mention": name,
                "canonical_name": None,
                "note_type": "equipment",
                "confidence": "explicit",
            }
        ],
        "facts": [
            {
                "meaning": quote,
                "kind": "record",
                "subject": name,
                "date": None,
                "daypart": None,
                "participants": [],
                "source_evidence": quote,
                "dependent_on_fact_index": None,
                "needs_clarification": False,
            }
            for quote, _text in entries
        ],
        "unresolved": [],
    }
    reviewed = {
        "approved": True,
        "complete": True,
        "reason": None,
        "facts": [
            {
                "ordinal": i,
                "source_quote": quote,
                "kind": "record",
                "reviewed_text": text,
                "date": None,
                "reference_names": [],
                "owner_name": name,
                "supported": True,
            }
            for i, (quote, text) in enumerate(entries)
        ],
    }
    speaker_a = {
        "facts": [
            {"ordinal": i + 1, "source_quote": quote, "role": "other", "assertion": "asserted"}
            for i, (quote, _text) in enumerate(entries)
        ]
    }
    speaker_b = {"facts": [{**row, "ordinal": i} for i, row in enumerate(speaker_a["facts"])]}
    service.client = RecordedClient(
        [
            {
                "capabilities": ["core"],
                "interpretation": "joint",
                "reason": "single",
                "self_relation_span": None,
                "app_scopes": [],
            },
            proposal,
            reviewed,
            speaker_a,
            speaker_b,
        ]
    )
    delivery = f"dynamic-owner-{reversed_order}"
    response = runtime.execute_product(source, delivery, "main", actor)
    assert response["status"] == "completed", (response, service.client.calls)
    content = parse_note(repo.read_text("Equipo Delta.md")).content
    assert all(text in content for _quote, text in entries)
    assert len(parse_atomic_facts(content)) == 2
    assert all(fact.request_id == f"{delivery}-owner-0" for fact in parse_atomic_facts(content))
    assert "Pesa cinco kilos." not in parse_note(repo.read_text("self.md")).content
    snapshot = {path: repo.read_text(path) for path in repo.list_markdown_paths()}
    replay = runtime.execute_product(source, delivery, "main", actor)
    assert replay["delivery_replayed"] is True
    assert {path: repo.read_text(path) for path in repo.list_markdown_paths()} == snapshot
