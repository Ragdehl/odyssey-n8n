"""E4 source-router and dependent-partition prompts preserve finite Person cohorts."""

import pytest

from odyssey_runtime.whole_source_model_contract import (
    DEPENDENT_TASK_PARTITION_PROMPT,
    ROUTER_INSTRUCTIONS,
)


def test_dependent_partition_prompt_supports_one_task_referencing_all_members():
    text = DEPENDENT_TASK_PARTITION_PROMPT
    assert "complete finite set of Persons" in text
    assert "'los dos'" in text and "'los tres'" in text
    assert "FULL exact-size preceding group" in text
    assert "ONE Task referring to all its members" in text
    assert "not to an arbitrary subset" in text
    assert "Do not" in text and "source entity" in text
    assert "every original character" in text
    assert "No output authorizes mutations" in text


def test_router_remains_non_authoritative_and_keeps_cross_clause_reference():
    text = ROUTER_INSTRUCTIONS
    assert "task depends on a just-mentioned" in text
    assert "Mark joint when" in text
    assert "not facts, identities or writes" in text


def test_invalid_model_partition_abstains_with_diagnostic_without_writing(monkeypatch):
    from odyssey_core.application import ApplicationStatus
    from odyssey_runtime.whole_source_light import WholeSourceLightExecutor

    source = "Hoy he conocido a Ana y a Luis. Mañana tengo que llamar a los dos."
    events = []
    executor = object.__new__(WholeSourceLightExecutor)
    executor.dependent_core_delegate = lambda *_args: pytest.fail("Core must not write")
    executor.dependent_task_prepare = lambda *_args: pytest.fail("Tasks must not run")
    executor.dependent_task_delegate = lambda *_args: pytest.fail("Tasks must not write")
    executor.prewrite_diagnostic = lambda request, gate, values: events.append(
        (request, gate, values)
    )
    monkeypatch.setattr(
        WholeSourceLightExecutor,
        "_ask",
        lambda *_args: {
            "full_source_quote": source,
            "antecedent_quote": "Hoy he conocido a Ana y a Luis.",
            "dependent_quote": " Mañana tengo que llamar a Ana.",
            "dependent_mention": "Ana",
        },
    )
    result = executor._execute_dependent_core_task(
        source,
        "synthetic-e4",
        None,
        delivery_instant=None,
        router_started=0.0,
        route_scopes=[
            {"capability": "core", "depends_on_another_scope": False},
            {"capability": "tasks", "depends_on_another_scope": True},
        ],
    )
    assert result.status is ApplicationStatus.NEEDS_ATTENTION
    assert result.clarification_code == "DEPENDENT_SOURCE_PARTITION_UNVERIFIED"
    assert events == [
        (
            "synthetic-e4",
            "dependent_partition_rejected",
            {"exact_source": True, "exact_span_coverage": False, "finite_mention": False},
        ),
    ]
