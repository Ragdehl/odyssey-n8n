"""All P4 model responses must remain valid OpenAI strict JSON schemas.

Prevent a schema field quietly becoming optional when an additional App field
or source evidence is introduced, since provider responses use strict=True.
"""

from __future__ import annotations

import pytest

from odyssey_runtime import whole_source_model_contract as contract

SCHEMAS = (
    contract.ROUTE_SCHEMA,
    contract.PLAN_SCHEMA,
    contract.REVIEW_SCHEMA,
    contract.SPEAKER_SCHEMA,
    contract.TASK_ONLY_SCOPE_SCHEMA,
    contract.MIXED_TASK_CREATE_SCHEMA,
    contract.INDEPENDENT_SCOPE_PARTITION_SCHEMA,
    contract.INDEPENDENT_SCOPE_REVIEW_SCHEMA,
    contract.DEPENDENT_TASK_TARGET_REVIEW_SCHEMA,
)


def _check(schema, depth=0):
    assert depth <= 10
    typ = schema.get("type")
    if typ == "object":
        assert schema.get("additionalProperties") is False
        assert isinstance(schema.get("properties"), dict)
        assert set(schema["required"]) == set(schema["properties"])
        assert len(set(schema["required"])) == len(schema["required"])
        for child in schema["properties"].values():
            _check(child, depth + 1)
    elif typ == "array":
        assert "items" in schema
        _check(schema["items"], depth + 1)
    elif isinstance(typ, list):
        assert len(typ) > 1 and "null" in typ
        assert all(t in {"string", "integer", "number", "null", "boolean"} for t in typ)
    else:
        assert typ in {"string", "integer", "number", "boolean"}


@pytest.mark.parametrize(
    "schema",
    SCHEMAS,
    ids=(
        "router",
        "semantic-planner",
        "whole-source-review",
        "speaker-proof",
        "tasks-only-scope",
        "mixed-task-lifecycle-audit",
        "independent-scope-partition",
        "independent-scope-audit",
        "dependent-task-target-audit",
    ),
)
def test_product_model_schema_requires_every_declared_field_and_forbids_extra(schema):
    _check(schema)


def test_product_never_exports_dynamic_codes_or_raw_source_as_mutation_authority():
    assert "source_quote" in contract.MIXED_TASK_CREATE_SCHEMA["required"]
    assert "source_quote" in contract.TASK_ONLY_SCOPE_SCHEMA["required"]
    assert "self_relation_span" in contract.ROUTE_SCHEMA["required"]
    assert (
        "dependent_on_fact_index"
        in contract.PLAN_SCHEMA["properties"]["facts"]["items"]["required"]
    )
    assert "supported" in contract.REVIEW_SCHEMA["properties"]["facts"]["items"]["required"]


def test_core_review_prompt_keeps_first_person_voice_in_live_contract():
    """Prevent accidentally placing a new prompt instruction in dead syntax."""
    assert "For first-person input" in contract.PROMPT_SOURCE_REVIEW
    assert "canonical SELF" in contract.PROMPT_SOURCE_REVIEW


def test_future_indicative_is_not_a_task_across_actual_product_prompts():
    for prompt in (
        contract.ROUTER_INSTRUCTIONS,
        contract.TASK_ONLY_SCOPE_PROMPT,
        contract.INDEPENDENT_SCOPE_PARTITION_PROMPT,
        contract.INDEPENDENT_SCOPE_REVIEW_PROMPT,
        contract.PLANNER_INSTRUCTIONS,
    ):
        assert "future" in prompt.lower()
        assert "Task" in prompt or "task" in prompt


def test_task_dependency_review_requires_whole_source_and_never_exposes_identity_ids():
    schema = contract.DEPENDENT_TASK_TARGET_REVIEW_SCHEMA
    assert {
        "full_source_quote",
        "antecedent_quote",
        "dependent_quote",
        "dependent_mention",
        "target_type",
        "one_target",
        "same_target",
        "operation",
        "operation_supported",
    } == set(schema["required"])
    assert not any("id" in name for name in schema["properties"])
    for prompt in (
        contract.DEPENDENT_TASK_TARGET_REVIEW_A,
        contract.DEPENDENT_TASK_TARGET_REVIEW_B,
    ):
        assert "Task" in prompt and "ID" in prompt
        assert "write" in prompt or "mutation" in prompt


def test_one_bounded_task_target_review_supports_work_sessions_and_subtask_parent_only():
    schema = contract.DEPENDENT_TASK_TARGET_REVIEW_SCHEMA
    names = set(schema["properties"]["operation"]["enum"])
    assert names == {
        "START_WORK_SESSION",
        "STOP_WORK_SESSION",
        "EDIT_WORK_SESSION",
        "ADD_WORK_SESSION_ACTIVITY",
        "CREATE_SUBTASK",
        "UNKNOWN",
    }
    assert "CREATE_SUBTASK" in contract.DEPENDENT_TASK_TARGET_REVIEW_A
    assert "subtask" in contract.DEPENDENT_TASK_TARGET_REVIEW_B.lower()
