"""Shared app-to-Core domain interpretation contract and planning guards."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from odyssey_core.domain_interpretation import (
    TEMPORAL_REFERENCE_EVIDENCE,
    DomainEvidence,
    DomainInterpretation,
)
from odyssey_core.experimental_luna_planning import (
    luna_experimental_result_json_schema,
    render_luna_experimental_prompt,
    validate_luna_experimental_result,
)
from odyssey_core.request_planning import (
    RequestPlan,
    RequestPlanningError,
    WriteAction,
    render_request_planner_prompt,
    render_semantic_write_planner_prompt,
)

ROOT = Path(__file__).resolve().parents[2]
CURRENT = {"date": "2026-10-02", "time": "17:00", "timezone": "Europe/Paris"}


def schema() -> dict[str, Any]:
    return json.loads((ROOT / "config/note-schema.json").read_text(encoding="utf-8"))


def interpretation() -> DomainInterpretation:
    source = "Marta Test empieza mañana a vivir con Daniel Test."
    return DomainInterpretation(
        "calendar",
        source,
        "TEMPORAL_ANNOTATION",
        (DomainEvidence(TEMPORAL_REFERENCE_EVIDENCE, "mañana", "2026-10-03"),),
    )


def identity(name: str) -> dict[str, Any]:
    return {
        "description": name,
        "binding": "described",
        "direct_name": name,
        "note_type": "person",
        "filters": [],
        "candidate_scope": None,
    }


def semantic_result(*, date: str = "2026-10-03", include_temporal: bool = True) -> dict[str, Any]:
    parts: list[dict[str, Any]] = [{"kind": "literal", "text": "Empieza "}]
    if include_temporal:
        parts.append({"kind": "temporal_reference", "text": "mañana", "value": date})
    parts.extend(
        [
            {"kind": "literal", "text": " a vivir con "},
            {"kind": "identity", "text": "Daniel Test", "identity": identity("Daniel Test")},
            {"kind": "literal", "text": "."},
        ]
    )
    return {
        "outcome": "PLAN",
        "actions": [
            {
                "kind": "write",
                "operations": [
                    {
                        "target": identity("Marta Test"),
                        "apply_to": "one",
                        "intent": "record",
                        "facts": [{"parts": parts}],
                        "properties": [],
                        "tag_changes": [],
                        "destination_type": None,
                    }
                ],
            }
        ],
        "limitations": [],
        "clarification_code": None,
        "presentation_intent": "answer",
    }


def test_domain_interpretation_is_bounded_grounded_and_mutation_free() -> None:
    value = interpretation()
    assert value.to_prompt_payload() == {
        "capability_id": "calendar",
        "intent": "TEMPORAL_ANNOTATION",
        "evidence": [
            {"kind": "temporal_reference", "source_text": "mañana", "value": "2026-10-03"}
        ],
    }
    serialized = json.dumps(value.to_prompt_payload())
    for forbidden in ("target", "facts", "candidate_scope", "write", "note_type", "properties"):
        assert forbidden not in serialized


@pytest.mark.parametrize(
    "factory",
    [
        lambda: DomainEvidence(TEMPORAL_REFERENCE_EVIDENCE, "mañana", "03/10/2026"),
        lambda: DomainInterpretation(
            "calendar",
            "Marta empieza mañana.",
            "TEMPORAL_ANNOTATION",
            (DomainEvidence(TEMPORAL_REFERENCE_EVIDENCE, "viernes", "2026-10-03"),),
        ),
        lambda: DomainInterpretation("Calendar App", "x", "INTENT", ()),
    ],
)
def test_domain_interpretation_rejects_invalid_or_ungrounded_evidence(factory) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(ValueError):
        factory()


def test_domain_handoff_retires_old_journal_prompt_and_pins_current_luna_candidate() -> None:
    """Keep the current provider-free Luna candidate explicit without changing accepted live evidence."""
    baseline = {"date": "2026-09-28", "time": "20:30", "timezone": "Europe/Paris"}
    prompt = render_luna_experimental_prompt(schema(), baseline).encode("utf-8")
    payload = luna_experimental_result_json_schema(schema())
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    assert hashlib.sha256(prompt).hexdigest() != (
        "3825f67eb4a209d709193cb1d928b94d7cd1a8b1035bba78f2f54f2b7275f143"
    )
    assert hashlib.sha256(encoded).hexdigest() == (
        "72698d25b7d8c491c41b2821473f955dd29a085ca9f41155a9af3f5688b032f7"
    )


def test_core_prompt_is_identical_when_no_domain_interpretation_is_supplied() -> None:
    active_schema = schema()
    normal = render_request_planner_prompt(active_schema, CURRENT)
    explicit_none = render_request_planner_prompt(
        active_schema, CURRENT, domain_interpretation=None
    )
    semantic_normal = render_semantic_write_planner_prompt(active_schema, CURRENT)
    semantic_none = render_semantic_write_planner_prompt(
        active_schema, CURRENT, domain_interpretation=None
    )
    assert normal == explicit_none
    assert semantic_normal == semantic_none
    assert "Specialized domain interpretation" not in normal
    assert "Specialized domain interpretation" not in semantic_normal


def test_specialized_evidence_is_additive_and_never_grants_core_semantics() -> None:
    prompt = render_semantic_write_planner_prompt(
        schema(), CURRENT, domain_interpretation=interpretation()
    )
    assert '"capability_id":"calendar"' in prompt
    assert '"kind":"temporal_reference"' in prompt
    assert '"source_text":"mañana"' in prompt
    assert '"value":"2026-10-03"' in prompt
    assert "Core still owns action choice, semantic ownership, targets, identities" in prompt
    assert "never as mutation authority" in prompt
    assert "Every supplied temporal_reference evidence item is mandatory" in prompt
    assert "ESCALATE instead of returning a partial PLAN" in prompt


def test_luna_core_schema_gains_only_shared_temporal_part_when_evidence_requires_it() -> None:
    active_schema = schema()
    ordinary = luna_experimental_result_json_schema(active_schema)
    specialized = luna_experimental_result_json_schema(active_schema, interpretation())
    assert "semantic_temporal_reference_part" not in ordinary["$defs"]
    assert specialized["$defs"]["semantic_temporal_reference_part"]["properties"]["kind"][
        "enum"
    ] == ["temporal_reference"]
    assert specialized["$defs"]["semantic_identity"] == ordinary["$defs"]["semantic_identity"]


def test_core_semantic_planning_with_domain_evidence_still_owns_identity_and_fact_shape() -> None:
    plan = validate_luna_experimental_result(
        semantic_result(), schema(), domain_interpretation=interpretation()
    )
    assert isinstance(plan, RequestPlan)
    action = plan.actions[0]
    assert isinstance(action, WriteAction)
    target, referenced = action.units
    assert target.target.entity == "Marta Test"
    assert referenced.target.entity == "Daniel Test"
    assert referenced.reference_lookup_only is True
    assert target.references[0].target_index == 1
    assert "[[calendar/days/2026-10-03|03-10-2026]]" in target.facts[0]


@pytest.mark.parametrize(
    "payload",
    [
        semantic_result(date="2026-10-04"),
        semantic_result(include_temporal=False),
    ],
)
def test_core_rejects_invented_or_dropped_specialized_temporal_evidence(
    payload: dict[str, Any],
) -> None:
    with pytest.raises(RequestPlanningError):
        validate_luna_experimental_result(payload, schema(), domain_interpretation=interpretation())


def test_core_requires_every_exact_date_from_multi_temporal_handoff() -> None:
    source = "Marta Test trabajó ayer y hoy."
    temporal = DomainInterpretation(
        "temporal",
        source,
        "TEMPORAL_RESOLUTION",
        (
            DomainEvidence(TEMPORAL_REFERENCE_EVIDENCE, "ayer", "2026-10-01"),
            DomainEvidence(TEMPORAL_REFERENCE_EVIDENCE, "hoy", "2026-10-02"),
        ),
    )

    def result(*, include_today: bool) -> dict[str, Any]:
        facts = [
            {
                "parts": [
                    {"kind": "literal", "text": "Trabajó "},
                    {"kind": "temporal_reference", "text": "ayer", "value": "2026-10-01"},
                    {"kind": "literal", "text": "."},
                ]
            }
        ]
        if include_today:
            facts.append(
                {
                    "parts": [
                        {"kind": "literal", "text": "Trabajó "},
                        {"kind": "temporal_reference", "text": "hoy", "value": "2026-10-02"},
                        {"kind": "literal", "text": "."},
                    ]
                }
            )
        return {
            "outcome": "PLAN",
            "actions": [
                {
                    "kind": "write",
                    "operations": [
                        {
                            "target": identity("Marta Test"),
                            "apply_to": "one",
                            "intent": "record",
                            "facts": facts,
                            "properties": [],
                            "tag_changes": [],
                            "destination_type": None,
                        }
                    ],
                }
            ],
            "limitations": [],
            "clarification_code": None,
            "presentation_intent": "answer",
        }

    accepted = validate_luna_experimental_result(
        result(include_today=True), schema(), domain_interpretation=temporal
    )
    assert isinstance(accepted, RequestPlan)
    with pytest.raises(RequestPlanningError, match="omitted required"):
        validate_luna_experimental_result(
            result(include_today=False), schema(), domain_interpretation=temporal
        )


def test_core_rejects_right_date_bound_to_wrong_temporal_wording() -> None:
    payload = semantic_result()
    temporal_part = payload["actions"][0]["operations"][0]["facts"][0]["parts"][1]
    temporal_part["text"] = "hoy"

    with pytest.raises(RequestPlanningError, match="wording/temporal evidence"):
        validate_luna_experimental_result(payload, schema(), domain_interpretation=interpretation())


def test_core_preserves_repeated_same_day_evidence_count_for_entity_write() -> None:
    temporal = DomainInterpretation(
        "temporal",
        "Marta Test trabajó hoy y descansó hoy.",
        "TEMPORAL_RESOLUTION",
        (
            DomainEvidence(TEMPORAL_REFERENCE_EVIDENCE, "hoy", "2026-10-02"),
            DomainEvidence(TEMPORAL_REFERENCE_EVIDENCE, "hoy", "2026-10-02"),
        ),
    )

    def result(repetitions: int) -> dict[str, Any]:
        facts = []
        labels = ("Trabajó ", "Descansó ", "Volvió ")
        for index in range(repetitions):
            facts.append(
                {
                    "parts": [
                        {"kind": "literal", "text": labels[index]},
                        {"kind": "temporal_reference", "text": "hoy", "value": "2026-10-02"},
                        {"kind": "literal", "text": "."},
                    ]
                }
            )
        return {
            "outcome": "PLAN",
            "actions": [
                {
                    "kind": "write",
                    "operations": [
                        {
                            "target": identity("Marta Test"),
                            "apply_to": "one",
                            "intent": "record",
                            "facts": facts,
                            "properties": [],
                            "tag_changes": [],
                            "destination_type": None,
                        }
                    ],
                }
            ],
            "limitations": [],
            "clarification_code": None,
            "presentation_intent": "answer",
        }

    assert isinstance(
        validate_luna_experimental_result(result(2), schema(), domain_interpretation=temporal),
        RequestPlan,
    )
    with pytest.raises(RequestPlanningError, match="omitted required"):
        validate_luna_experimental_result(result(1), schema(), domain_interpretation=temporal)
    with pytest.raises(RequestPlanningError, match="not supplied"):
        validate_luna_experimental_result(result(3), schema(), domain_interpretation=temporal)


def test_exact_datetime_becomes_day_link_plus_clock_and_internal_anchor() -> None:
    """Core renders the clock and retains the validated exact date-time as fact metadata."""
    temporal = DomainInterpretation(
        "temporal",
        "Marta Test ve mañana a las 15:35 a Daniel Test.",
        "TEMPORAL_RESOLUTION",
        (
            DomainEvidence(
                TEMPORAL_REFERENCE_EVIDENCE,
                "mañana a las 15:35",
                "2026-10-03T15:35:00+02:00",
            ),
        ),
    )
    payload = semantic_result()
    temporal_part = payload["actions"][0]["operations"][0]["facts"][0]["parts"][1]
    temporal_part["text"] = "mañana a las 15:35"
    temporal_part["value"] = "2026-10-03T15:35:00+02:00"

    plan = validate_luna_experimental_result(payload, schema(), domain_interpretation=temporal)
    action = plan.actions[0]
    assert isinstance(action, WriteAction)
    target = action.units[0]
    assert "[[calendar/days/2026-10-03|03-10-2026]] 15:35" in target.facts[0]
    assert [[anchor.value for anchor in row] for row in target.fact_temporal_anchors] == [
        ["2026-10-03T15:35:00+02:00"]
    ]


def test_calendar_day_target_consumes_date_but_keeps_exact_clock_anchor() -> None:
    """A Day-owned fact avoids a self-link while preserving its exact clock coordinate."""
    temporal = DomainInterpretation(
        "temporal",
        "Mañana a las 15:35 voy al dentista.",
        "TEMPORAL_RESOLUTION",
        (
            DomainEvidence(
                TEMPORAL_REFERENCE_EVIDENCE,
                "Mañana a las 15:35",
                "2026-10-03T15:35:00+02:00",
            ),
        ),
    )
    day = {
        "description": "2026-10-03",
        "binding": "described",
        "direct_name": None,
        "note_type": "calendar_day",
        "filters": [],
        "candidate_scope": None,
    }
    payload = {
        "outcome": "PLAN",
        "actions": [
            {
                "kind": "write",
                "operations": [
                    {
                        "target": day,
                        "apply_to": "one",
                        "intent": "record",
                        "facts": [
                            {
                                "parts": [
                                    {
                                        "kind": "temporal_reference",
                                        "text": "Mañana a las 15:35",
                                        "value": "2026-10-03T15:35:00+02:00",
                                    },
                                    {"kind": "literal", "text": " — Voy al dentista."},
                                ]
                            }
                        ],
                        "properties": [],
                        "tag_changes": [],
                        "destination_type": None,
                    }
                ],
            }
        ],
        "limitations": [],
        "clarification_code": None,
        "presentation_intent": "answer",
    }

    plan = validate_luna_experimental_result(
        payload,
        schema(),
        domain_interpretation=temporal,
        authorized_calendar_dates=("2026-10-03",),
    )
    action = plan.actions[0]
    assert isinstance(action, WriteAction)
    unit = action.units[0]
    assert unit.target.type == "calendar_day"
    assert unit.facts == ("15:35 — Voy al dentista.",)
    assert [[anchor.value for anchor in row] for row in unit.fact_temporal_anchors] == [
        ["2026-10-03T15:35:00+02:00"]
    ]


def test_semantic_write_prompt_preserves_elided_coordinated_relationship_scopes() -> None:
    prompt = render_semantic_write_planner_prompt(schema(), CURRENT)
    assert "mi mujer e hijos" in prompt
    assert 'member_query="mis hijos"' in prompt
    assert "Shared possessives distribute" in prompt
