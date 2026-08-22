"""Production RequestPlan contract and model-boundary tests without provider calls."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from odyssey_core.request_planning import (
    PLANNER_MODEL,
    PLANNER_REASONING_EFFORT,
    WRITE_INTENTS,
    KnowledgeUnit,
    OpenAIRequestPlanner,
    PropertyChange,
    RequestPlanningError,
    RetrieveAction,
    WriteAction,
    render_request_planner_prompt,
    request_plan_json_schema,
    validate_request_plan,
)

ROOT = Path(__file__).resolve().parents[2]
CONTEXT = {"date": "2026-08-22", "time": "09:30", "timezone": "Europe/Paris"}


@pytest.fixture
def schema() -> dict:
    """Load the canonical schema used by production planning."""
    return json.loads((ROOT / "config/note-schema.json").read_text(encoding="utf-8"))


def selection(
    query: str, *, note_type: str | None = None, filters: list[dict] | None = None
) -> dict:
    """Build one raw shared query/type/filter selection fixture."""
    return {"query": query, "type": note_type, "filters": filters or []}


def retrieve(
    query: str, *, note_type: str | None = None, filters: list[dict] | None = None
) -> dict:
    """Build one raw retrieval action fixture."""
    return {"kind": "retrieve", "plan": selection(query, note_type=note_type, filters=filters)}


def output(*actions: dict, limitations: list[str] | None = None) -> dict:
    """Build one complete raw RequestPlan fixture."""
    return {"actions": list(actions), "limitations": limitations or []}


def unit(
    query: str,
    *,
    note_type: str | None = None,
    filters: list[dict] | None = None,
    intent: str = "record",
    properties: list[dict] | None = None,
    facts: list[str] | None = None,
    references: list[dict] | None = None,
) -> dict:
    """Build one raw Phase 15.1 semantic knowledge-unit fixture."""
    return {
        "target": selection(query, note_type=note_type, filters=filters),
        "intent": intent,
        "properties": [] if properties is None else properties,
        "facts": ["Remember this fact."] if facts is None else facts,
        "references": [] if references is None else references,
    }


def write(*units: dict) -> dict:
    """Build one raw non-executing write-action fixture."""
    return {"kind": "write", "units": list(units)}


def prop(field: str, value: object, *, op: str = "set") -> dict:
    """Build one raw generic property-change fixture."""
    return {"field": field, "op": op, "value": value}


def test_simple_semantic_retrieval_and_semantic_idea_review_remain_unrestricted(
    schema: dict,
) -> None:
    """Keep ordinary semantic terms in the query without invented type or tag filters."""
    plan = validate_request_plan(
        output(retrieve("Qué tengo apuntado sobre Odyssey, ideas para revisar")), schema
    )
    action = plan.actions[0]
    assert isinstance(action, RetrieveAction)
    assert action.plan.type is None and action.plan.filters == ()


def test_lifecycle_and_alias_filters_use_dynamic_context_and_non_empty_query(schema: dict) -> None:
    """Accept safe lifecycle ranges and exact aliases only with meaningful retrieval text."""
    prompt = render_request_planner_prompt(schema, CONTEXT)
    assert '"date":"2026-08-22"' in prompt and '"timezone":"Europe/Paris"' in prompt
    plan = validate_request_plan(
        output(
            retrieve(
                'notas con exactamente el alias "Ody"',
                filters=[{"field": "aliases", "op": "contains", "value": "Ody"}],
            ),
            retrieve(
                "qué escribí ayer sobre Odyssey",
                filters=[
                    {"field": "created_at", "op": "gte", "value": "2026-08-21T00:00:00+02:00"},
                    {"field": "created_at", "op": "lt", "value": "2026-08-22T00:00:00+02:00"},
                ],
            ),
        ),
        schema,
    )
    assert len(plan.actions) == 2


def test_multi_type_retrieval_and_controlled_limitations(schema: dict) -> None:
    """Accept canonical multi-type filters and reject unsupported limitation vocabulary."""
    plan = validate_request_plan(
        output(
            retrieve(
                "personas y proyectos relacionados con Toulouse",
                filters=[{"field": "type", "op": "in", "value": ["person", "project"]}],
            ),
            limitations=["not_supported"],
        ),
        schema,
    )
    assert plan.limitations == ("not_supported",)
    with pytest.raises(RequestPlanningError, match="limitations"):
        validate_request_plan(output(retrieve("Odyssey"), limitations=["unsupported_not"]), schema)


def test_mixed_retrieval_and_write_actions_preserve_request_order(schema: dict) -> None:
    """Preserve ordered mixed requests without executing either action type."""
    plan = validate_request_plan(
        output(
            write(
                unit(
                    "Phase 15",
                    note_type="project",
                    facts=["Use Sol.", "Review costs in September."],
                )
            ),
            retrieve("qué había pensado antes sobre esto"),
        ),
        schema,
    )
    assert isinstance(plan.actions[0], WriteAction)
    assert plan.actions[0].units[0].facts == ("Use Sol.", "Review costs in September.")
    assert plan.actions[0].units[0].target.query == "Phase 15"
    assert isinstance(plan.actions[1], RetrieveAction)


def test_structured_property_only_record_amend_and_remove_are_valid(schema: dict) -> None:
    """Treat canonical properties as first-class semantic payload rather than requiring prose facts."""
    plan = validate_request_plan(
        output(
            write(
                unit(
                    "Marta",
                    note_type="person",
                    properties=[prop("birth_date", "1990-05-03")],
                    facts=[],
                ),
                unit(
                    "Marta",
                    note_type="person",
                    intent="amend",
                    properties=[prop("relationship_to_user", "hermana")],
                    facts=[],
                ),
                unit(
                    "Marta",
                    note_type="person",
                    intent="remove",
                    properties=[prop("birth_date", None, op="remove")],
                    facts=[],
                ),
            )
        ),
        schema,
    )
    action = plan.actions[0]
    assert isinstance(action, WriteAction)
    assert action.units[0].properties == (
        PropertyChange(field="birth_date", op="set", value="1990-05-03"),
    )
    assert action.units[1].properties[0].value == "hermana"
    assert action.units[2].properties[0].op == "remove"


def test_write_target_reuses_filters_without_turning_identity_evidence_into_mutation(
    schema: dict,
) -> None:
    """Keep target selection and requested mutation separate even when both use properties."""
    plan = validate_request_plan(
        output(
            write(
                unit(
                    "la persona",
                    note_type="person",
                    filters=[{"field": "birth_date", "op": "eq", "value": "1990-05-03"}],
                    intent="amend",
                    properties=[prop("relationship_to_user", "hermana")],
                    facts=[],
                )
            )
        ),
        schema,
    )
    item = plan.actions[0].units[0]  # type: ignore[union-attr]
    assert item.target.filters[0].field == "birth_date"
    assert [change.field for change in item.properties] == ["relationship_to_user"]


def test_same_property_can_identify_old_value_and_set_corrected_value(schema: dict) -> None:
    """Do not deduplicate a field across target selection and mutation payload."""
    plan = validate_request_plan(
        output(
            write(
                unit(
                    "la persona",
                    note_type="person",
                    filters=[{"field": "birth_date", "op": "eq", "value": "1990-05-03"}],
                    intent="amend",
                    properties=[prop("birth_date", "1990-05-04")],
                    facts=[],
                )
            )
        ),
        schema,
    )
    item = plan.actions[0].units[0]  # type: ignore[union-attr]
    assert item.target.filters[0].value == "1990-05-03"
    assert item.properties[0].value == "1990-05-04"


def test_write_intents_multiple_targets_and_references(schema: dict) -> None:
    """Accept all controlled intents, factless deletes, and reference-only targets."""
    plan = validate_request_plan(
        output(
            write(
                unit(
                    "Carrefour Balma",
                    note_type="store",
                    intent="amend",
                    facts=["Closes at 20:30.", "Has underground parking."],
                ),
                unit(
                    "Leche Pascual semidesnatada",
                    note_type="product",
                    facts=[],
                ),
                unit(
                    "Weekly shopping",
                    note_type="purchase",
                    facts=["Bought today."],
                    references=[
                        {"target_index": 0, "role": "store"},
                        {"target_index": 1, "role": "product"},
                    ],
                ),
                unit("Old shopping list", intent="delete", facts=[]),
                unit(
                    "Weekly shopping",
                    note_type="purchase",
                    intent="remove",
                    facts=["Remove the obsolete delivery fee."],
                    references=[{"target_index": 0, "role": "store"}],
                ),
            )
        ),
        schema,
    )
    action = plan.actions[0]
    assert isinstance(action, WriteAction)
    assert set(item.intent for item in action.units) == set(WRITE_INTENTS)
    assert isinstance(action.units[0], KnowledgeUnit)
    assert action.units[1].facts == () and action.units[3].facts == ()
    assert action.units[2].references[0].target_index == 0


def test_property_validation_is_type_scoped_schema_driven_and_fail_closed(schema: dict) -> None:
    """Reject cross-type fields, malformed values, duplicate fields, and intent/op mismatches."""
    invalid = [
        unit("Marta", properties=[prop("birth_date", "1990-05-03")], facts=[]),
        unit(
            "Odyssey",
            note_type="project",
            properties=[prop("birth_date", "1990-05-03")],
            facts=[],
        ),
        unit("Marta", note_type="person", properties=[prop("birth_date", "03/05/1990")], facts=[]),
        unit(
            "Marta",
            note_type="person",
            properties=[
                prop("birth_date", "1990-05-03"),
                prop("birth_date", "1991-01-01"),
            ],
            facts=[],
        ),
        unit(
            "Marta",
            note_type="person",
            intent="amend",
            properties=[prop("birth_date", None, op="remove")],
            facts=[],
        ),
        unit(
            "Marta",
            note_type="person",
            intent="remove",
            properties=[prop("birth_date", "1990-05-03")],
            facts=[],
        ),
    ]
    for raw in invalid:
        with pytest.raises(RequestPlanningError):
            validate_request_plan(output(write(raw)), schema)


def test_write_contract_rejects_physical_decisions_and_invalid_semantic_fields(
    schema: dict,
) -> None:
    """Fail closed on persistence fields, bad types/intents, empty payloads, and unsafe references."""
    invalid = [
        output(write(unit("Carrefour", note_type="unknown"))),
        output(write(unit("Carrefour", intent="create"))),
        output(write(unit("Carrefour", intent="amend", facts=[]))),
        output(write(unit("Carrefour", intent="remove", facts=[]))),
        output(write(unit("Carrefour", intent="record", facts=[]))),
        output(write(unit("Carrefour", intent="delete", facts=["Delete this object."]))),
        output(
            write(
                unit(
                    "Carrefour",
                    intent="delete",
                    properties=[prop("birth_date", None, op="remove")],
                    facts=[],
                )
            )
        ),
        output(write(unit("Carrefour", references=[{"target_index": 0, "role": "self"}]))),
        output(write(unit("Carrefour", references=[{"target_index": 1, "role": "store"}]))),
        output(write(unit("Carrefour") | {"operation": "UPDATE"})),
        output(write(unit("Carrefour", references=[{"target_index": 0, "role": " "}]))),
    ]
    for payload in invalid:
        with pytest.raises(RequestPlanningError):
            validate_request_plan(payload, schema)


def test_invalid_model_output_fails_closed(schema: dict) -> None:
    """Reject empty queries, unknown types, bad filters, old write shapes, and invalid actions."""
    invalid = [
        output(retrieve("")),
        output(retrieve("Odyssey", note_type="invented")),
        output(retrieve("Odyssey", filters=[{"field": "tags", "op": "contains", "value": "idea"}])),
        output({"kind": "retrieve", "plan": {"query": "Odyssey"}}),
        output({"kind": "write", "units": []}),
        output(
            {
                "kind": "write",
                "units": [
                    {
                        "subject": "Marta",
                        "type": "person",
                        "intent": "record",
                        "facts": ["Old shape"],
                        "references": [],
                    }
                ],
            }
        ),
    ]
    for payload in invalid:
        with pytest.raises(RequestPlanningError):
            validate_request_plan(payload, schema)


def test_relationship_capability_uses_core_supported_string_operators(schema: dict) -> None:
    """Advertise only the equality operators Core accepts for relationship values."""
    prompt = render_request_planner_prompt(schema, CONTEXT)
    retrieval_json = prompt.split(
        "Planner retrieval/selection capabilities (derived dynamically from the canonical schema):\n\n",
        1,
    )[1].split("\n\nPlanner writable", 1)[0]
    capabilities = json.loads(retrieval_json)
    assert capabilities["filters"]["relationship_to_user"]["operators"] == ["eq", "in"]


def test_prompt_includes_dynamic_write_capabilities(schema: dict) -> None:
    """Give Sol the canonical property registry in the same interpretation call."""
    prompt = render_request_planner_prompt(schema, CONTEXT)
    write_json = prompt.split(
        "Planner writable type/property capabilities (derived dynamically from the same canonical schema):\n\n",
        1,
    )[1]
    capabilities = json.loads(write_json)
    assert capabilities["types"]["person"]["properties"]["birth_date"]["value_type"] == "date"
    assert capabilities["types"]["journal_entry"]["properties"]["entry_date"]["required"] is True


def test_dynamic_capabilities_reflect_schema_changes_and_exclude_tags(schema: dict) -> None:
    """Render the caller's schema rather than a benchmark snapshot or static field list."""
    changed = deepcopy(schema)
    changed["types"][0]["properties"].append(
        {
            "id": "source_year",
            "value_type": "integer",
            "required": False,
            "description": "Year supplied by the source.",
            "filterable": True,
        }
    )
    prompt = render_request_planner_prompt(changed, CONTEXT)
    retrieval_json = prompt.split(
        "Planner retrieval/selection capabilities (derived dynamically from the canonical schema):\n\n",
        1,
    )[1].split("\n\nPlanner writable", 1)[0]
    capabilities = json.loads(retrieval_json)
    assert capabilities["filters"]["source_year"]["operators"] == [
        "eq",
        "in",
        "gt",
        "gte",
        "lt",
        "lte",
    ]
    assert "tags" not in capabilities["filters"]


def test_synthetic_new_type_property_flows_through_schema_and_validation(schema: dict) -> None:
    """Prove a novel type/property needs no production branch when semantics are already supported."""
    changed = deepcopy(schema)
    changed["types"].append(
        {
            "id": "car",
            "name": "Car",
            "description": "Reusable vehicle identity.",
            "examples": ["Family car"],
            "subtypes": [],
            "properties": [
                {
                    "id": "registration_number",
                    "value_type": "string",
                    "required": False,
                    "description": "Vehicle registration number.",
                    "filterable": True,
                }
            ],
        }
    )
    plan = validate_request_plan(
        output(
            write(
                unit(
                    "our car",
                    note_type="car",
                    properties=[prop("registration_number", "1234-ABC")],
                    facts=[],
                )
            )
        ),
        changed,
    )
    item = plan.actions[0].units[0]  # type: ignore[union-attr]
    assert item.properties[0].field == "registration_number"
    request_schema = request_plan_json_schema(changed)
    serialized = json.dumps(request_schema)
    assert "registration_number" in serialized and '"car"' in serialized


def test_openai_boundary_uses_sol_low_structured_output_and_store_false(schema: dict) -> None:
    """Send the approved production configuration through an injected no-network fake client."""
    calls: list[dict] = []

    def create(**kwargs: object) -> SimpleNamespace:
        calls.append(kwargs)
        return SimpleNamespace(output_text=json.dumps(output(retrieve("Odyssey"))))

    planner = OpenAIRequestPlanner(
        SimpleNamespace(responses=SimpleNamespace(create=create)), schema, CONTEXT
    )
    assert planner.plan("¿Qué tengo apuntado sobre Odyssey?").actions
    assert calls[0]["model"] == PLANNER_MODEL
    assert calls[0]["reasoning"] == {"effort": PLANNER_REASONING_EFFORT}
    assert calls[0]["store"] is False
    assert calls[0]["text"]["format"]["strict"] is True  # type: ignore[index]
    write_schema = calls[0]["text"]["format"]["schema"]["properties"]["actions"]["items"][  # type: ignore[index]
        "anyOf"
    ][1]
    unit_schema = write_schema["properties"]["units"]["items"]
    assert write_schema["properties"]["kind"] == {"type": "string", "enum": ["write"]}
    assert set(unit_schema["required"]) == {
        "target",
        "intent",
        "properties",
        "facts",
        "references",
    }
    assert "subject" not in unit_schema["properties"]


def test_request_plan_schema_uses_supported_enum_discriminators(schema: dict) -> None:
    """Keep Structured Outputs action discriminators in the established compatible subset."""
    request_schema = request_plan_json_schema(schema)

    def contains_key(value: object, key: str) -> bool:
        """Find one unsupported schema keyword recursively without a schema library."""
        if isinstance(value, dict):
            return key in value or any(contains_key(item, key) for item in value.values())
        if isinstance(value, list):
            return any(contains_key(item, key) for item in value)
        return False

    action_variants = request_schema["properties"]["actions"]["items"]["anyOf"]
    assert request_schema["properties"]["actions"]["minItems"] == 1
    assert [variant["properties"]["kind"] for variant in action_variants] == [
        {"type": "string", "enum": ["retrieve"]},
        {"type": "string", "enum": ["write"]},
    ]
    assert not contains_key(request_schema, "const")


def test_prompt_prevents_today_from_inventing_a_journal_entry_type(schema: dict) -> None:
    """Keep transient dated reflections untyped unless the request names a diary entry."""
    prompt = render_request_planner_prompt(schema, CONTEXT)
    assert "Do not infer `journal_entry` merely because a reflection says today/hoy" in prompt


def test_production_planner_does_not_depend_on_frozen_benchmark_assets() -> None:
    """Keep production planning independent from historical benchmark files."""
    source = (ROOT / "odyssey_core" / "request_planning.py").read_text(encoding="utf-8")
    assert "benchmarks.phase14" not in source and "planner_capabilities.json" not in source
