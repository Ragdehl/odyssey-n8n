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
    CreateNoteAction,
    OpenAIRequestPlanner,
    RequestPlanningError,
    RetrieveAction,
    render_request_planner_prompt,
    validate_request_plan,
)

ROOT = Path(__file__).resolve().parents[2]
CONTEXT = {"date": "2026-08-22", "time": "09:30", "timezone": "Europe/Paris"}


@pytest.fixture
def schema() -> dict:
    """Load the canonical schema used by production planning."""
    return json.loads((ROOT / "config/note-schema.json").read_text(encoding="utf-8"))


def retrieve(
    query: str, *, note_type: str | None = None, filters: list[dict] | None = None
) -> dict:
    """Build one raw retrieval action fixture."""
    return {
        "kind": "retrieve",
        "plan": {"query": query, "type": note_type, "filters": filters or []},
    }


def output(*actions: dict, limitations: list[str] | None = None) -> dict:
    """Build one complete raw RequestPlan fixture."""
    return {"actions": list(actions), "limitations": limitations or []}


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


def test_mixed_and_compound_create_actions_preserve_content_only_intent(schema: dict) -> None:
    """Preserve ordered mixed requests and avoid decomposing compound memory content."""
    plan = validate_request_plan(
        output(
            {"kind": "create_note", "content": "Quiero usar Sol y revisar costes en septiembre."},
            retrieve("qué había pensado antes sobre esto"),
        ),
        schema,
    )
    assert isinstance(plan.actions[0], CreateNoteAction)
    assert plan.actions[0].content == "Quiero usar Sol y revisar costes en septiembre."
    assert isinstance(plan.actions[1], RetrieveAction)


def test_invalid_model_output_fails_closed(schema: dict) -> None:
    """Reject empty queries, unknown types, bad filters, bad shapes, and empty create content."""
    invalid = [
        output(retrieve("")),
        output(retrieve("Odyssey", note_type="invented")),
        output(retrieve("Odyssey", filters=[{"field": "tags", "op": "contains", "value": "idea"}])),
        output({"kind": "retrieve", "plan": {"query": "Odyssey"}}),
        output({"kind": "create_note", "content": " "}),
    ]
    for payload in invalid:
        with pytest.raises(RequestPlanningError):
            validate_request_plan(payload, schema)


def test_relationship_capability_uses_core_supported_string_operators(schema: dict) -> None:
    """Advertise only the equality operators Core accepts for relationship values."""
    prompt = render_request_planner_prompt(schema, CONTEXT)
    capabilities = json.loads(prompt.rsplit("\n\n", 1)[1])
    assert capabilities["filters"]["relationship_to_user"]["operators"] == ["eq", "in"]


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
    capabilities = json.loads(render_request_planner_prompt(changed, CONTEXT).rsplit("\n\n", 1)[1])
    assert capabilities["filters"]["source_year"]["operators"] == [
        "eq",
        "in",
        "gt",
        "gte",
        "lt",
        "lte",
    ]
    assert "tags" not in capabilities["filters"]


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


def test_production_planner_does_not_depend_on_frozen_benchmark_assets() -> None:
    """Keep production planning independent from historical benchmark files."""
    source = (ROOT / "odyssey_core" / "request_planning.py").read_text(encoding="utf-8")
    assert "benchmarks.phase14" not in source and "planner_capabilities.json" not in source
