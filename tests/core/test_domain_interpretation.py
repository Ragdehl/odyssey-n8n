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
    source = "Marta Test empieza mañana a trabajar en Airbus Test."
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
        "note_type": None,
        "filters": [],
        "candidate_scope": None,
    }


def semantic_result(*, date: str = "2026-10-03", include_temporal: bool = True) -> dict[str, Any]:
    parts: list[dict[str, Any]] = [{"kind": "literal", "text": "Empieza "}]
    if include_temporal:
        parts.append({"kind": "temporal_reference", "text": "mañana", "date": date})
    parts.extend(
        [
            {"kind": "literal", "text": " a trabajar en "},
            {"kind": "identity", "text": "Airbus Test", "identity": identity("Airbus Test")},
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


def test_domain_handoff_does_not_change_pre_redesign_ordinary_luna_prompt() -> None:
    """Pin the ordinary Core prompt to the exact e78781b pre-redesign checkpoint."""
    baseline = {"date": "2026-09-28", "time": "20:30", "timezone": "Europe/Paris"}
    prompt = render_luna_experimental_prompt(schema(), baseline).encode("utf-8")
    assert hashlib.sha256(prompt).hexdigest() == (
        "d60c7605f0f3751cf7c5394e90daa8b92df9c10e6e9d949b447ab50907bdcd4b"
    )


def test_domain_handoff_does_not_change_ordinary_luna_provider_schema() -> None:
    """Pin the ordinary Core provider schema while specialized evidence remains opt-in."""
    payload = luna_experimental_result_json_schema(schema())
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    assert hashlib.sha256(encoded).hexdigest() == (
        "65877ae84df406d36648c37a7ad4826033990a1d1b2cc8a1d1a193a5e7ecedce"
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
    assert referenced.target.entity == "Airbus Test"
    assert referenced.reference_lookup_only is True
    assert target.references[0].target_index == 1
    assert "[[calendar/days/2026-10-03|mañana]]" in target.facts[0]


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
