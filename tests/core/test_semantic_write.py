"""Provider-free semantic WRITE compiler coverage."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from odyssey_core.context import ContextFilter
from odyssey_core.reference_binding import render_reference_facts
from odyssey_core.reference_preflight import UnitTargetPreflight
from odyssey_core.request_planning import PropertyChange, TagChange
from odyssey_core.semantic_write import (
    ApplyTo,
    CandidateScope,
    CandidateScopeExtent,
    ExistingSource,
    IdentityBinding,
    IdentityIntent,
    IdentityPart,
    LiteralPart,
    SemanticFact,
    SemanticWriteCompileError,
    SemanticWriteIntent,
    SemanticWriteOperation,
    compile_semantic_write,
    decode_semantic_write_action,
    semantic_write_action_json_schema,
    semantic_write_schema_definitions,
)
from odyssey_core.write_target import WriteTargetOutcome

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def schema() -> dict:
    """Load the active schema whose existing validator remains compiler authority."""
    return json.loads((ROOT / "config/note-schema.json").read_text(encoding="utf-8"))


def person(
    description: str,
    *,
    name: str | None = None,
    scope: CandidateScope | None = None,
    filters: tuple[ContextFilter, ...] = (),
) -> IdentityIntent:
    """Build one ordinary person identity for compact compiler tests."""
    return IdentityIntent(description, IdentityBinding.DESCRIBED, name, "person", filters, scope)


def scoped_self(
    member_query: str, extent: CandidateScopeExtent = CandidateScopeExtent.ONE_MEMBER
) -> CandidateScope:
    """Build one self-grounded candidate scope."""
    return CandidateScope(IdentityBinding.SELF, member_query, extent)


def scoped_existing(source: str, member_query: str) -> CandidateScope:
    """Build one non-recursive existing-source candidate scope."""
    return CandidateScope(ExistingSource(source), member_query, CandidateScopeExtent.ONE_MEMBER)


def fact(*parts: LiteralPart | IdentityPart) -> SemanticFact:
    """Build one ordered semantic fact."""
    return SemanticFact(parts)


def operation(
    target: IdentityIntent,
    *fact_values: SemanticFact,
    apply_to: ApplyTo = ApplyTo.ONE,
    intent: str = "record",
    properties: tuple[PropertyChange, ...] = (),
    tags: tuple[TagChange, ...] = (),
    destination_type: str | None = None,
) -> SemanticWriteOperation:
    """Build one semantic operation with concise defaults."""
    return SemanticWriteOperation(
        target, apply_to, intent, fact_values, properties, tags, destination_type
    )


def compile_one(schema: dict, *operations: SemanticWriteOperation):
    """Compile ordered operations through the public provider-free boundary."""
    return compile_semantic_write(SemanticWriteIntent(operations), schema)


def raw_identity(
    description: str = "Marta",
    *,
    binding: str = "described",
    direct_name: str | None = "Marta",
    note_type: str | None = "person",
    filters: list[dict] | None = None,
    candidate_scope: dict | None = None,
) -> dict:
    """Build one complete provider semantic identity object."""
    return {
        "description": description,
        "binding": binding,
        "direct_name": direct_name,
        "note_type": note_type,
        "filters": filters or [],
        "candidate_scope": candidate_scope,
    }


def raw_operation(
    *,
    target: dict | None = None,
    apply_to: str = "one",
    facts: list[dict] | None = None,
) -> dict:
    """Build one complete provider semantic operation object."""
    return {
        "target": target or raw_identity(),
        "apply_to": apply_to,
        "intent": "record",
        "facts": facts
        if facts is not None
        else [{"parts": [{"kind": "literal", "text": "Lives in Lyon."}]}],
        "properties": [],
        "tag_changes": [],
        "destination_type": None,
    }


def raw_action(*operations: dict) -> dict:
    """Build one complete provider semantic write action."""
    return {"kind": "write", "operations": list(operations) or [raw_operation()]}


def test_simple_named_and_multiple_facts_lower_without_reference_plumbing(schema: dict) -> None:
    """Keep explicit entity and ordered independent facts on one material unit."""
    action = compile_one(
        schema,
        operation(
            person("Marta", name="Marta"),
            fact(LiteralPart("Trabaja en Toulouse.")),
            fact(LiteralPart("Prefiere"), LiteralPart(" "), LiteralPart("el tren.")),
        ),
    )

    unit = action.units[0]
    assert unit.target.entity == "Marta"
    assert unit.target.query == "Marta"
    assert unit.facts == ("Trabaja en Toulouse.", "Prefiere el tren.")
    assert unit.references == ()


def test_independent_targets_remain_ordered_independent_units(schema: dict) -> None:
    """Avoid compiler ownership regrouping across semantic operations."""
    action = compile_one(
        schema,
        operation(person("Denis", name="Denis"), fact(LiteralPart("Es zurdo."))),
        operation(person("Axel", name="Axel"), fact(LiteralPart("Es zurdo."))),
    )

    assert [(unit.target.entity, unit.facts) for unit in action.units] == [
        ("Denis", ("Es zurdo.",)),
        ("Axel", ("Es zurdo.",)),
    ]


def test_swr01_self_owned_two_participants_lowers_to_core_lookup_units(schema: dict) -> None:
    """Represent two coworkers as references owned by the authenticated self fact."""
    action = compile_one(
        schema,
        operation(
            IdentityIntent("yo", IdentityBinding.SELF, note_type="person"),
            fact(
                IdentityPart("Axel", person("Axel", name="Axel")),
                LiteralPart(" y "),
                IdentityPart("Denis", person("Denis", name="Denis")),
                LiteralPart(" son mis compañeros de trabajo."),
            ),
        ),
    )

    source, axel, denis = action.units
    assert source.target.self_target == "self"
    assert source.facts == ("{{ref:0}} y {{ref:1}} son mis compañeros de trabajo.",)
    assert [reference.role for reference in source.references] == ["identity", "identity"]
    assert [reference.target_index for reference in source.references] == [1, 2]
    assert (axel.reference_lookup_only, denis.reference_lookup_only) == (True, True)


@pytest.mark.parametrize(
    ("target", "expected_reference", "expected_source", "expected_member"),
    [
        (
            person(
                "mi hija a la que le gusta ver detectives de animales",
                scope=scoped_self("mi hija"),
            ),
            "mi hija",
            None,
            "mi hija a la que le gusta ver detectives de animales",
        ),
        (
            person(
                "el amigo de Bruno que vive en Lyon",
                scope=scoped_existing("Bruno", "los amigos de Bruno"),
            ),
            "los amigos de Bruno",
            "Bruno",
            "el amigo de Bruno que vive en Lyon",
        ),
        (
            person(
                "la persona de la cena relacional de prueba que trabaja en Airbus Test",
                scope=scoped_existing(
                    "cena relacional de prueba",
                    "las personas que estuvieron en la cena relacional de prueba",
                ),
            ),
            "las personas que estuvieron en la cena relacional de prueba",
            "cena relacional de prueba",
            "la persona de la cena relacional de prueba que trabaja en Airbus Test",
        ),
    ],
    ids=["SWR02", "SWR06", "SWR07"],
)
def test_swr_scoped_targets_preserve_description_and_candidate_scope(
    schema: dict,
    target: IdentityIntent,
    expected_reference: str,
    expected_source: str | None,
    expected_member: str,
) -> None:
    """Map non-recursive candidate scopes without replacing full target wording."""
    action = compile_one(schema, operation(target, fact(LiteralPart("Se muda a Toulouse."))))

    relational = action.units[0].target.relational_reference
    assert action.units[0].target.query == expected_member
    assert relational is not None
    assert relational.reference == expected_reference
    assert relational.source_kind == ("self" if expected_source is None else "existing")
    assert relational.source_query == expected_source
    assert relational.members == "one"


def test_candidate_scope_is_note_type_agnostic_for_project_target(schema: dict) -> None:
    """Keep the same bounded candidate semantics for non-person note types."""
    target = IdentityIntent(
        "uno de mis proyectos",
        IdentityBinding.DESCRIBED,
        note_type="project",
        candidate_scope=scoped_self("mis proyectos"),
    )
    action = compile_one(
        schema,
        operation(target, fact(LiteralPart("Ha cambiado de prioridad."))),
    )

    unit = action.units[0]
    assert unit.target.type == "project"
    assert unit.target.query == "uno de mis proyectos"
    assert unit.target.relational_reference is not None
    assert unit.target.relational_reference.source_kind == "self"
    assert unit.target.relational_reference.reference == "mis proyectos"
    assert unit.target.relational_reference.members == "one"


def test_swr03_ordinary_described_target_stays_unscoped(schema: dict) -> None:
    """Keep an ordinary described target independent of relational representation."""
    action = compile_one(
        schema,
        operation(person("la amiga con la que cené ayer"), fact(LiteralPart("Se muda a París."))),
    )
    assert action.units[0].target.query == "la amiga con la que cené ayer"
    assert action.units[0].target.relational_reference is None


def test_swr04_scoped_child_target_and_described_friend_reference(schema: dict) -> None:
    """Keep the child as owner while Core creates the separate friend lookup reference."""
    target = person("mi hijo mayor", scope=scoped_self("mi hijo"))
    friend = person("la amiga que vive en Lyon")
    action = compile_one(
        schema,
        operation(
            target,
            fact(
                LiteralPart("Fue al cine con "),
                IdentityPart("la amiga que vive en Lyon", friend),
                LiteralPart("."),
            ),
        ),
    )

    source, lookup = action.units
    assert source.target.query == "mi hijo mayor"
    assert source.target.relational_reference is not None
    assert source.target.relational_reference.reference == "mi hijo"
    assert source.facts == ("Fue al cine con {{ref:0}}.",)
    assert lookup.reference_lookup_only is True
    assert lookup.target.query == "la amiga que vive en Lyon"
    assert lookup.target.relational_reference is None


def test_swr08_scoped_target_and_scoped_participant(schema: dict) -> None:
    """Lower target and participant scopes independently through Core lookup lowering."""
    target = person("mi hija mayor", scope=scoped_self("mi hija"))
    participant = person(
        "la persona de la cena relacional de prueba que trabaja en Airbus Test",
        scope=scoped_existing(
            "cena relacional de prueba", "las personas de la cena relacional de prueba"
        ),
    )
    action = compile_one(
        schema,
        operation(
            target,
            fact(
                LiteralPart("Va a cenar con "),
                IdentityPart(
                    "la persona de la cena relacional de prueba que trabaja en Airbus Test",
                    participant,
                ),
                LiteralPart("."),
            ),
        ),
    )

    source, lookup = action.units
    assert source.target.relational_reference is not None
    assert source.target.relational_reference.reference == "mi hija"
    assert source.facts == ("Va a cenar con {{ref:0}}.",)
    assert lookup.reference_lookup_only is True
    assert lookup.target.relational_reference is not None
    assert lookup.target.relational_reference.source_query == "cena relacional de prueba"


def test_swr09_independent_shared_predicate_is_not_merged(schema: dict) -> None:
    """Keep each semantically independent shared-predicate target as one operation."""
    action = compile_one(
        schema,
        operation(person("Denis", name="Denis"), fact(LiteralPart("Es zurdo."))),
        operation(person("Axel", name="Axel"), fact(LiteralPart("Es zurdo."))),
    )
    assert len(action.units) == 2
    assert [unit.facts for unit in action.units] == [("Es zurdo.",), ("Es zurdo.",)]


def test_swr10_target_and_two_bounded_references_preserve_literal_saturday(schema: dict) -> None:
    """Assign local markers in occurrence order while retaining literal context exactly."""
    target = person("mi hija mayor", scope=scoped_self("mi hija"))
    airbus = person(
        "la persona de la cena relacional de prueba que trabaja en Airbus Test",
        scope=scoped_existing(
            "cena relacional de prueba", "las personas de la cena relacional de prueba"
        ),
    )
    italian = person(
        "la persona de la cena relacional de prueba que habla italiano",
        scope=scoped_existing(
            "cena relacional de prueba", "las personas de la cena relacional de prueba"
        ),
    )
    action = compile_one(
        schema,
        operation(
            target,
            fact(
                LiteralPart("Va al parque el sábado con "),
                IdentityPart(
                    "la persona de la cena relacional de prueba que trabaja en Airbus Test", airbus
                ),
                LiteralPart(" y con "),
                IdentityPart(
                    "la persona de la cena relacional de prueba que habla italiano", italian
                ),
                LiteralPart("."),
            ),
        ),
    )

    assert action.units[0].facts == ("Va al parque el sábado con {{ref:0}} y con {{ref:1}}.",)
    assert [unit.target.relational_reference.source_query for unit in action.units[1:]] == [
        "cena relacional de prueba",
        "cena relacional de prueba",
    ]


def test_repeated_reference_and_cross_operation_reference_reuse_core_lookup(schema: dict) -> None:
    """Reuse only exact identities, locally and across operations, through existing Core lowering."""
    faro = IdentityIntent("el proyecto Faro", IdentityBinding.DESCRIBED, "Faro", "project")
    action = compile_one(
        schema,
        operation(
            IdentityIntent("el informe", IdentityBinding.DESCRIBED, note_type="document"),
            fact(
                LiteralPart("Menciona "),
                IdentityPart("Faro", faro),
                LiteralPart(" y vuelve a mencionar "),
                IdentityPart("Faro", faro),
                LiteralPart("."),
            ),
        ),
        operation(
            person("Marta", name="Marta"),
            fact(LiteralPart("Colabora con "), IdentityPart("Faro", faro), LiteralPart(".")),
        ),
    )

    first, second, lookup = action.units
    assert first.facts == ("Menciona {{ref:0}} y vuelve a mencionar {{ref:0}}.",)
    assert [reference.target_index for reference in first.references] == [2]
    assert second.references[0].target_index == 2
    assert lookup.reference_lookup_only is True
    assert lookup.target.type == "project"
    assert lookup.target.entity == "Faro"


def test_same_identity_with_distinct_mentions_preserves_each_occurrence(schema: dict) -> None:
    """Do not collapse distinct pending wording merely because identity evidence matches."""
    faro = IdentityIntent("el proyecto Faro", IdentityBinding.DESCRIBED, "Faro", "project")
    action = compile_one(
        schema,
        operation(
            IdentityIntent("el informe", IdentityBinding.DESCRIBED, note_type="document"),
            fact(
                LiteralPart("Menciona "),
                IdentityPart("Faro", faro),
                LiteralPart(" y después el "),
                IdentityPart("proyecto", faro),
                LiteralPart(" otra vez."),
            ),
        ),
    )

    source, lookup = action.units
    assert source.facts == ("Menciona {{ref:0}} y después el {{ref:1}} otra vez.",)
    assert [reference.mention for reference in source.references] == ["Faro", "proyecto"]
    assert [reference.target_index for reference in source.references] == [1, 1]
    assert lookup.reference_lookup_only is True

    preflight = (
        UnitTargetPreflight(
            0,
            WriteTargetOutcome.UPDATE,
            stable_id="source-id",
            canonical_name="Informe",
            path="documents/informe.md",
        ),
        UnitTargetPreflight(
            1,
            WriteTargetOutcome.NEEDS_CLARIFICATION,
            candidate_note_ids=("project-faro",),
            reason="ambiguous",
            reference_only=True,
        ),
    )
    rendered = render_reference_facts(action, preflight)
    assert rendered.rendered_facts[0] == ("Menciona Faro y después el proyecto otra vez.",)
    assert [pending.mention for pending in rendered.pending_references] == ["Faro", "proyecto"]


def test_literal_fact_text_preserves_urls_paths_and_external_identifiers(schema: dict) -> None:
    """Keep representation guards from censoring ordinary durable user fact content."""
    text = (
        "La documentación está en https://example.com/README.md y el UUID externo "
        "123e4567-e89b-12d3-a456-426614174000 sigue vigente."
    )
    action = compile_one(
        schema,
        operation(person("Marta", name="Marta"), fact(LiteralPart(text))),
    )
    assert action.units[0].facts == (text,)


def test_reference_reuses_one_unique_material_target_and_ambiguous_match_fails(
    schema: dict,
) -> None:
    """Leave same-request target reuse and its ambiguity guard with the existing Core lowering."""
    faro = IdentityIntent("Faro", IdentityBinding.DESCRIBED, "Faro", "project")
    action = compile_one(
        schema,
        operation(
            IdentityIntent("el informe", IdentityBinding.DESCRIBED, note_type="document"),
            fact(LiteralPart("Menciona "), IdentityPart("Faro", faro), LiteralPart(".")),
        ),
        operation(faro, fact(LiteralPart("Está activo."))),
    )
    assert len(action.units) == 2
    assert action.units[0].references[0].target_index == 1
    assert action.units[1].reference_lookup_only is False

    with pytest.raises(SemanticWriteCompileError):
        compile_one(
            schema,
            operation(
                IdentityIntent("el informe", IdentityBinding.DESCRIBED, note_type="document"),
                fact(LiteralPart("Menciona "), IdentityPart("Faro", faro), LiteralPart(".")),
            ),
            operation(faro, fact(LiteralPart("Está activo."))),
            operation(faro, fact(LiteralPart("Tiene presupuesto."))),
        )


def test_properties_tags_intents_migration_bulk_and_complete_set_use_core_validation(
    schema: dict,
) -> None:
    """Cover generic mutation forms using a synthetic writable property-bearing type."""
    writable_schema = deepcopy(schema)
    next(item for item in writable_schema["types"] if item["id"] == "journal_entry")[
        "planner_writable"
    ] = True
    metadata = PropertyChange("entry_date", "set", "2026-09-29")
    mutation = compile_one(
        writable_schema,
        operation(
            IdentityIntent("diario", IdentityBinding.DESCRIBED, note_type="journal_entry"),
            fact(LiteralPart("Fue un buen día.")),
            properties=(metadata,),
            tags=(TagChange("add", "review"),),
        ),
        operation(
            person("Marta", name="Marta"),
            fact(LiteralPart("Vive en Lyon.")),
            intent="amend",
        ),
        operation(
            person("Marta", name="Marta"),
            fact(LiteralPart("Vivía en París.")),
            intent="remove",
        ),
        operation(person("Obsoleto", name="Obsoleto"), intent="delete"),
    )
    assert mutation.units[0].properties == (metadata,)
    assert mutation.units[0].tag_changes == (TagChange("add", "review"),)
    assert [unit.intent for unit in mutation.units] == ["record", "amend", "remove", "delete"]

    migration = compile_one(
        writable_schema,
        operation(
            IdentityIntent("nota diaria", IdentityBinding.DESCRIBED, note_type="concept"),
            intent="amend",
            properties=(metadata,),
            destination_type="journal_entry",
        ),
    )
    assert migration.units[0].destination_type == "journal_entry"
    assert migration.units[0].facts == ()

    bulk = compile_one(
        schema,
        operation(
            IdentityIntent("personas favoritas", IdentityBinding.DESCRIBED, note_type="person"),
            fact(LiteralPart("Recibieron la invitación.")),
            apply_to=ApplyTo.ALL_MATCHING,
        ),
    )
    assert bulk.units[0].cardinality == "all_matching"

    complete = compile_one(
        schema,
        operation(
            person(
                "mis hijos",
                scope=CandidateScope(
                    IdentityBinding.SELF, "mis hijos", CandidateScopeExtent.COMPLETE_SET
                ),
            ),
            fact(LiteralPart("Fueron "), LiteralPart("al colegio.")),
        ),
    )
    assert complete.units[0].cardinality == "one"
    assert complete.units[0].target.relational_reference is not None
    assert complete.units[0].target.relational_reference.members == "complete_set"


@pytest.mark.parametrize(
    "bad_operation",
    [
        operation(person("Marta"), fact(LiteralPart("No.")), intent="delete"),
        operation(person("Marta"), intent="amend"),
        operation(person("Marta"), intent="remove"),
        operation(
            person("Marta"),
            fact(LiteralPart("Texto.")),
            intent="amend",
            destination_type="project",
        ),
        operation(
            person("todas las personas", scope=scoped_self("mis hijos")),
            fact(LiteralPart("Texto.")),
            apply_to=ApplyTo.ALL_MATCHING,
        ),
        operation(
            IdentityIntent("yo", IdentityBinding.SELF, note_type="person"),
            fact(LiteralPart("Texto.")),
            apply_to=ApplyTo.ALL_MATCHING,
        ),
        operation(
            person("todas las personas"),
            fact(
                LiteralPart("Con "),
                IdentityPart("Marta", person("Marta", name="Marta")),
                LiteralPart("."),
            ),
            apply_to=ApplyTo.ALL_MATCHING,
        ),
        operation(
            IdentityIntent("todas las personas", IdentityBinding.DESCRIBED),
            fact(LiteralPart("Texto.")),
            apply_to=ApplyTo.ALL_MATCHING,
        ),
        operation(
            person(
                "mis hijos",
                scope=CandidateScope(
                    IdentityBinding.SELF, "mis hijos", CandidateScopeExtent.COMPLETE_SET
                ),
            ),
            fact(LiteralPart("Texto.")),
            properties=(PropertyChange("entry_date", "set", "2026-09-29"),),
        ),
    ],
    ids=[
        "delete-payload",
        "amend-empty",
        "remove-empty",
        "migration-fact",
        "bulk-scope",
        "bulk-self",
        "bulk-reference",
        "bulk-unbounded",
        "complete-set-payload",
    ],
)
def test_unsupported_operation_shapes_fail_closed(
    schema: dict, bad_operation: SemanticWriteOperation
) -> None:
    """Reject shapes outside the approved first slice before any execution boundary."""
    with pytest.raises(SemanticWriteCompileError):
        compile_one(schema, bad_operation)


def test_same_target_duplicate_and_current_property_tag_invariants_fail_closed(
    schema: dict,
) -> None:
    """Keep reference, fact, property, and tag invariants owned by Core validation."""
    marta = person("Marta", name="Marta")
    with pytest.raises(SemanticWriteCompileError):
        compile_one(
            schema,
            operation(
                marta,
                fact(LiteralPart("Habla con "), IdentityPart("Marta", marta), LiteralPart(".")),
            ),
        )
    with pytest.raises(SemanticWriteCompileError):
        compile_one(
            schema,
            operation(
                marta,
                fact(LiteralPart("Es puntual.")),
                fact(LiteralPart("Es puntual.")),
            ),
        )
    with pytest.raises(SemanticWriteCompileError):
        compile_one(
            schema,
            operation(
                IdentityIntent("diario", IdentityBinding.DESCRIBED, note_type="journal_entry"),
                fact(LiteralPart("Texto.")),
                properties=(
                    PropertyChange("entry_date", "set", "2026-09-29"),
                    PropertyChange("entry_date", "set", "2026-09-30"),
                ),
            ),
        )
    with pytest.raises(SemanticWriteCompileError):
        compile_one(
            schema,
            operation(
                person("Marta"),
                fact(LiteralPart("Texto.")),
                tags=(TagChange("add", "review"), TagChange("remove", "review")),
            ),
        )


def test_identity_description_preserves_benign_pathlike_and_uuid_wording(schema: dict) -> None:
    """Do not treat ordinary query wording as repository authority merely by its syntax."""
    description = "la referencia notes/marta.md con UUID 123e4567-e89b-12d3-a456-426614174000"
    action = compile_one(
        schema,
        operation(
            IdentityIntent(description, IdentityBinding.DESCRIBED, note_type="person"),
            fact(LiteralPart("Tiene una descripción externa.")),
        ),
    )
    assert action.units[0].target.query == description


@pytest.mark.parametrize("unsafe", ["", "dos\nlíneas", "[[Marta]]", "{{ref:0}}"])
def test_unsafe_identity_wording_fails_closed(schema: dict, unsafe: str) -> None:
    """Reject unsafe identity/source wording before raw lowering."""
    with pytest.raises(SemanticWriteCompileError):
        compile_one(schema, operation(person(unsafe), fact(LiteralPart("Texto."))))


@pytest.mark.parametrize("unsafe", ["", "dos\nlíneas", "[[Marta]]", "{{ref:0}}"])
def test_unsafe_literal_representation_syntax_fails_closed(schema: dict, unsafe: str) -> None:
    """Reserve Core marker/wikilink syntax while allowing ordinary path-like fact text."""
    with pytest.raises(SemanticWriteCompileError):
        compile_one(schema, operation(person("Marta"), fact(LiteralPart(unsafe))))


def test_self_and_candidate_scope_selector_conflicts_fail_closed(schema: dict) -> None:
    """Keep direct-name and relational scope authority mutually exclusive as Core requires."""
    with pytest.raises(SemanticWriteCompileError):
        compile_one(
            schema,
            operation(
                IdentityIntent("yo", IdentityBinding.SELF, direct_name="Marta"),
                fact(LiteralPart("Texto.")),
            ),
        )
    with pytest.raises(SemanticWriteCompileError):
        compile_one(
            schema,
            operation(
                IdentityIntent("yo", IdentityBinding.SELF, candidate_scope=scoped_self("mi hija")),
                fact(LiteralPart("Texto.")),
            ),
        )
    with pytest.raises(SemanticWriteCompileError):
        compile_one(
            schema,
            operation(
                person("mi hija", name="Marta", scope=scoped_self("mi hija")),
                fact(LiteralPart("Texto.")),
            ),
        )
    with pytest.raises(SemanticWriteCompileError):
        compile_one(
            schema,
            operation(
                person(
                    "mi hija",
                    scope=scoped_self("mi hija"),
                    filters=(ContextFilter("tags", "contains", "family"),),
                ),
                fact(LiteralPart("Texto.")),
            ),
        )


def test_semantic_provider_objects_are_closed_and_fully_required(schema: dict) -> None:
    """Keep every Structured Outputs object closed with all declared properties required."""
    root = {
        "type": "object",
        "properties": semantic_write_action_json_schema()["properties"],
        "required": semantic_write_action_json_schema()["required"],
        "additionalProperties": False,
        "$defs": semantic_write_schema_definitions(schema),
    }

    def assert_closed(value: object) -> None:
        if isinstance(value, dict):
            if value.get("type") == "object":
                assert value.get("additionalProperties") is False
                assert set(value.get("required", [])) == set(value.get("properties", {}))
            for child in value.values():
                assert_closed(child)
        elif isinstance(value, list):
            for child in value:
                assert_closed(child)

    assert_closed(root)


@pytest.mark.parametrize(
    "mechanical_field",
    [
        "units",
        "cardinality",
        "references",
        "target_index",
        "reference_lookup_only",
        "role",
        "source_kind",
        "source_query",
        "members",
    ],
)
def test_raw_decoder_rejects_core_mechanical_fields(schema: dict, mechanical_field: str) -> None:
    """Keep every legacy unit/reference/relational plumbing field outside Luna WRITE."""
    raw = raw_action(raw_operation())
    if mechanical_field == "units":
        raw[mechanical_field] = []
    elif mechanical_field in {"cardinality", "references", "reference_lookup_only"}:
        raw["operations"][0][mechanical_field] = None
    elif mechanical_field in {"target_index", "role"}:
        raw["operations"][0]["facts"][0]["parts"][0][mechanical_field] = None
    else:
        raw["operations"][0]["target"]["candidate_scope"] = {
            "source": {"kind": "SELF"},
            "member_query": "my colleagues",
            "extent": "one_member",
            mechanical_field: None,
        }
    with pytest.raises(SemanticWriteCompileError):
        compile_semantic_write(decode_semantic_write_action(raw), schema)


@pytest.mark.parametrize(
    "source",
    [
        {"kind": "SELF", "description": "me"},
        {"kind": "SOURCE_DESCRIPTION"},
        {"kind": "SOURCE_DESCRIPTION", "description": "dinner", "identity": {}},
        {"kind": "EXISTING_DESCRIPTION", "description": "dinner"},
        {"kind": "OTHER"},
        {
            "kind": "SOURCE_DESCRIPTION",
            "description": "dinner",
            "source": {"kind": "SELF"},
        },
    ],
)
def test_candidate_source_union_rejects_correlated_or_recursive_states(source: dict) -> None:
    """Accept only SELF or one non-recursive described source for Core grounding."""
    target = raw_identity(
        direct_name=None,
        candidate_scope={
            "source": source,
            "member_query": "participants",
            "extent": "one_member",
        },
    )
    with pytest.raises(SemanticWriteCompileError):
        decode_semantic_write_action(raw_action(raw_operation(target=target)))


def test_semantic_schema_is_derived_from_synthetic_canonical_additions(schema: dict) -> None:
    """Prove types, filters, properties, value shapes, and destinations are not hardcoded."""
    synthetic = deepcopy(schema)
    synthetic["types"].append(
        {
            "id": "synthetic_type",
            "name": "Synthetic",
            "description": "Test-only dynamic type.",
            "examples": ["Synthetic note"],
            "properties": [
                {
                    "id": "priority_score",
                    "value_type": "integer",
                    "required": False,
                    "description": "Test-only score.",
                    "filterable": True,
                },
                {
                    "id": "reviewers",
                    "value_type": "array[string]",
                    "required": False,
                    "description": "Test-only reviewers.",
                    "filterable": False,
                },
            ],
        }
    )
    definitions = semantic_write_schema_definitions(synthetic)
    serialized = json.dumps(definitions, sort_keys=True)
    assert (
        "synthetic_type"
        in definitions["semantic_identity"]["properties"]["note_type"]["anyOf"][1]["enum"]
    )
    assert "priority_score" in serialized
    assert '"type": "integer"' in serialized
    assert "reviewers" in serialized
    assert '"type": "array"' in serialized
    destination = definitions["semantic_operation"]["properties"]["destination_type"]
    assert "synthetic_type" in destination["anyOf"][1]["enum"]


def test_action_wide_unsupported_execution_shapes_fail_locally(schema: dict) -> None:
    """Reject mixed/bulk/relational/complete-set combinations before application execution."""
    one = operation(person("Marta"), fact(LiteralPart("Texto.")))
    bulk = operation(
        person("todas las personas"),
        fact(LiteralPart("Texto.")),
        apply_to=ApplyTo.ALL_MATCHING,
    )
    relational_a = operation(
        person("mi hija", scope=scoped_self("mi hija")), fact(LiteralPart("Texto."))
    )
    relational_b = operation(
        person("mi hijo", scope=scoped_self("mi hijo")), fact(LiteralPart("Texto."))
    )
    complete = operation(
        person(
            "mis hijos",
            scope=scoped_self("mis hijos", CandidateScopeExtent.COMPLETE_SET),
        ),
        fact(LiteralPart("Texto.")),
    )
    for operations in (
        (one, bulk),
        (bulk, bulk),
        (relational_a, relational_b),
        (complete, one),
    ):
        with pytest.raises(SemanticWriteCompileError):
            compile_one(schema, *operations)


def test_semantic_identity_256_character_bound_fails_locally(schema: dict) -> None:
    """Keep overlong model wording on the normal fail-closed planner path."""
    intent = decode_semantic_write_action(
        raw_action(raw_operation(target=raw_identity("x" * 257, direct_name=None)))
    )
    with pytest.raises(SemanticWriteCompileError):
        compile_semantic_write(intent, schema)


def test_temporal_reference_is_opt_in_and_default_core_schema_stays_closed(schema: dict) -> None:
    """Expose exact-Day fact parts only to application compilers, never the ordinary Core planner."""
    ordinary = semantic_write_schema_definitions(schema)
    assert list(ordinary) == [
        "filter_array",
        "semantic_candidate_scope",
        "semantic_identity",
        "semantic_literal_part",
        "semantic_identity_part",
        "semantic_fact",
        "semantic_property_changes",
        "semantic_operation",
    ]
    assert "semantic_temporal_reference_part" not in ordinary

    calendar = semantic_write_schema_definitions(schema, include_temporal_reference=True)
    assert "semantic_temporal_reference_part" in calendar
    raw = raw_action(
        raw_operation(
            facts=[
                {
                    "parts": [
                        {"kind": "literal", "text": "Empieza "},
                        {"kind": "temporal_reference", "text": "mañana", "date": "2026-10-03"},
                    ]
                }
            ]
        )
    )
    with pytest.raises(SemanticWriteCompileError):
        decode_semantic_write_action(raw)
    intent = decode_semantic_write_action(raw, allow_temporal_reference=True)
    action = compile_semantic_write(intent, schema)
    assert action.units[0].facts == ("Empieza [[calendar/days/2026-10-03|03-10-2026]]",)


def test_calendar_temporal_source_text_never_controls_durable_link_label(schema: dict) -> None:
    """Treat app temporal wording as evidence, while Core owns durable Markdown presentation."""
    intent = decode_semantic_write_action(
        raw_action(
            raw_operation(
                facts=[
                    {
                        "parts": [
                            {
                                "kind": "temporal_reference",
                                "text": "mañana o cualquier alias",
                                "date": "2026-10-03",
                            }
                        ]
                    }
                ]
            )
        ),
        allow_temporal_reference=True,
    )
    action = compile_semantic_write(intent, schema)
    assert action.units[0].facts == ("[[calendar/days/2026-10-03|03-10-2026]]",)
