"""Provider-free source-safety checks for the inactive Router v1 candidate interface."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from odyssey_apps.fact_candidates import (
    CANDIDATE_KINDS,
    SOURCE_ROLES,
    FactCandidateProposal,
    OpenAIFactCandidateRouter,
    as_candidate_preview,
    fact_candidate_json_schema,
    validate_fact_candidate_proposal,
)
from odyssey_apps.router import RouterError

DESIGN = (
    Path(__file__).resolve().parents[2] / "benchmarks/application_router/fact_units_v2.design.json"
)


def _from_design(case: dict[str, Any]) -> dict[str, Any]:
    """Translate human-specified semantic oracles to the untrusted v1 JSON shape."""
    return {
        "version": 1,
        "units": [
            {
                "kind": unit["kind"],
                "anchors": [{"text": text, "occurrence": 0} for text in unit["source_anchors"]],
                "scoped_source": [
                    {"role": item["role"], "anchor": {"text": item["text"], "occurrence": 0}}
                    for item in unit["scoped_source"]
                ],
                "inheritance": unit["inheritance"],
                "state": unit["state"],
            }
            for unit in case["expected_units"]
        ],
    }


CASES = json.loads(DESIGN.read_text(encoding="utf-8"))["cases"]


@pytest.mark.parametrize("case", CASES, ids=lambda item: item["id"])
def test_all_twenty_seven_design_oracles_are_grounded_source_only(case: dict[str, Any]) -> None:
    """Ground all 56 accepted design candidates without app, Note, or write authority."""
    payload = _from_design(case)
    plan = validate_fact_candidate_proposal(case["source"], payload)
    assert isinstance(plan, FactCandidateProposal)
    assert len(plan.candidates) == len(case["expected_units"])
    assert plan.source == case["source"]
    assert [unit.candidate_id for unit in plan.candidates] == [
        f"candidate-{index}" for index in range(1, len(plan.candidates) + 1)
    ]
    for unit in plan.candidates:
        assert unit.kind in CANDIDATE_KINDS
        for anchor in unit.anchors:
            assert case["source"][anchor.start : anchor.end] == anchor.text
        for role in unit.scopes:
            assert role.role in SOURCE_ROLES
            assert case["source"][role.anchor.start : role.anchor.end] == role.anchor.text
        assert all(
            1 <= dep.from_unit < int(unit.candidate_id.split("-")[-1]) for dep in unit.inheritance
        )
        assert not hasattr(unit, "note_type")
        assert not hasattr(unit, "canonical_id")
        assert not hasattr(plan, "execute")


def test_source_scopes_can_appear_after_units_that_use_them() -> None:
    """A shared later time expression is anchored, never normalized or copied."""
    case = next(item for item in CASES if item["id"] == "F21")
    plan = validate_fact_candidate_proposal(case["source"], _from_design(case))
    first = plan.candidates[0]
    assert any(role.role == "time" and role.anchor.text == "a las 18h" for role in first.scopes)
    assert any(role.anchor.start > first.anchors[0].start for role in first.scopes)


def test_generic_subjects_and_role_transition_stay_type_free() -> None:
    """Houses, vehicles, projects and documents use no canonical Note type here."""
    for case_id in ("F23", "F24", "F25", "F26"):
        case = next(item for item in CASES if item["id"] == case_id)
        result = validate_fact_candidate_proposal(case["source"], _from_design(case))
        assert len(result.candidates) == 2
        assert any(scope.role == "subject" for scope in result.candidates[0].scopes)
    report = next(item for item in CASES if item["id"] == "F26")
    second = validate_fact_candidate_proposal(report["source"], _from_design(report)).candidates[1]
    assert [(dep.role, dep.from_unit) for dep in second.inheritance] == [("object", 1)]


def test_repeated_source_occurrences_and_unicode_are_locally_resolved() -> None:
    """Identical Unicode quotes require an exact occurrence, not guessed offsets."""
    source = "Ana vio a Ana. Hoy Ana volvió. café 🏠 café"
    payload = {
        "version": 1,
        "units": [
            {
                "kind": "occurrence",
                "anchors": [{"text": "Ana", "occurrence": 2}],
                "scoped_source": [{"role": "subject", "anchor": {"text": "café", "occurrence": 1}}],
                "inheritance": [],
                "state": "candidate",
            }
        ],
    }
    proposal = validate_fact_candidate_proposal(source, payload)
    assert proposal.candidates[0].anchors[0].start == source.rfind("Ana")
    assert proposal.candidates[0].scopes[0].anchor.start == source.rfind("café")


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda x: x.update({"core_note_type": "person"}), "fields"),
        (lambda x: x["units"][0].update({"canonical_id": "person:A"}), "fields"),
        (lambda x: x["units"][0]["anchors"][0].update({"text": "fabricated person"}), "occurrence"),
        (lambda x: x["units"][0]["anchors"][0].update({"occurrence": 10}), "occurrence"),
        (lambda x: x["units"][0]["anchors"][0].update({"occurrence": True}), "anchor"),
        (lambda x: x["units"][0]["scoped_source"][0].update({"role": "note_type"}), "role"),
        (
            lambda x: x["units"][0]["inheritance"].append({"role": "subject", "from_unit": 1}),
            "dependency",
        ),
        (
            lambda x: x["units"][0]["inheritance"].append({"role": "subject", "from_unit": 2}),
            "dependency",
        ),
        (lambda x: x["units"][0].update({"state": "verified"}), "kind or state"),
        (lambda x: x.update({"version": 2}), "version"),
    ],
)
def test_untrusted_candidate_evidence_fails_closed(mutation, message: str) -> None:  # type: ignore[no-untyped-def]
    """Reject hallucinated source, invented authority and unsafe inheritance."""
    data = {
        "version": 1,
        "units": [
            {
                "kind": "occurrence",
                "anchors": [{"text": "Ana", "occurrence": 0}],
                "scoped_source": [{"role": "subject", "anchor": {"text": "Ana", "occurrence": 0}}],
                "inheritance": [],
                "state": "candidate",
            },
        ],
    }
    mutation(data)
    with pytest.raises(RouterError, match=message):
        validate_fact_candidate_proposal("Ana vino ayer.", data)


def test_candidate_arrays_are_bounded_and_more_than_one_unit_may_share_source() -> None:
    """One predicate can legitimately support many candidates without duplicate writes."""
    case = next(item for item in CASES if item["id"] == "F09")
    result = validate_fact_candidate_proposal(case["source"], _from_design(case))
    assert len(result.candidates) == 2
    assert len({scope.anchor.text for item in result.candidates for scope in item.scopes}) <= 4
    oversized = _from_design(case)
    oversized["units"] = oversized["units"] * 14
    with pytest.raises(RouterError, match="count"):
        validate_fact_candidate_proposal(case["source"], oversized)


def test_schema_is_closed_and_keeps_execution_fields_out() -> None:
    """Contract admits original source references but never Core mutation fields."""
    schema = fact_candidate_json_schema()
    assert schema["additionalProperties"] is False
    unit = schema["properties"]["units"]["items"]
    assert unit["additionalProperties"] is False
    assert set(unit["properties"]) == {"kind", "anchors", "scoped_source", "inheritance", "state"}
    assert not any(
        field in json.dumps(schema)
        for field in ("canonical_id", "note_type", "write_intent", "request_plan")
    )


def test_new_router_adapter_one_call_does_not_change_current_router() -> None:
    """Test the actual model-facing v1 seam with a fake provider and no execution."""
    case = next(item for item in CASES if item["id"] == "F01")
    call_kwargs: list[dict[str, Any]] = []
    reply = SimpleNamespace(
        status="completed", usage=None, output_text=json.dumps(_from_design(case))
    )
    fake = SimpleNamespace(
        responses=SimpleNamespace(create=lambda **kw: call_kwargs.append(kw) or reply)
    )
    adapter = OpenAIFactCandidateRouter(fake)
    proposal = adapter.propose(case["source"])
    assert len(proposal.candidates) == 3
    assert len(call_kwargs) == 1
    assert call_kwargs[0]["model"] == "gpt-6-luna"
    assert call_kwargs[0]["store"] is False
    assert call_kwargs[0]["text"]["format"]["strict"] is True
    assert call_kwargs[0]["input"][1]["content"] == case["source"]
    assert "NoteSchema" in call_kwargs[0]["input"][0]["content"]
    assert not hasattr(adapter, "execute")


def test_router_adapter_cannot_execute_ungrounded_proposal() -> None:
    """Even structurally plausible provider completions fail closed on invented facts."""
    case = next(item for item in CASES if item["id"] == "F02")
    forged = copy.deepcopy(_from_design(case))
    forged["units"][1]["anchors"][0]["text"] = "mañana con el presidente"
    reply = SimpleNamespace(status="completed", usage=None, output_text=json.dumps(forged))
    client = SimpleNamespace(responses=SimpleNamespace(create=lambda **_kw: reply))
    with pytest.raises(RouterError, match="grounded"):
        OpenAIFactCandidateRouter(client).propose(case["source"])


def test_local_preview_is_read_only_and_unverified() -> None:
    """Optional existing browser preview may show source roles, never Core success."""
    case = next(item for item in CASES if item["id"] == "F01")
    preview = as_candidate_preview(
        validate_fact_candidate_proposal(case["source"], _from_design(case))
    )
    assert preview["version"] == 1
    assert len(preview["candidates"]) == 3
    assert all(role["authority"] is None for c in preview["candidates"] for role in c["roles"])
    assert all(
        role["provenance"] != "verified" for c in preview["candidates"] for role in c["roles"]
    )
    assert all(c["dependency_target"] is None for c in preview["candidates"])


def test_old_router_route_plan_still_preserves_original_request_as_one_span() -> None:
    """New source-sharing fact candidates do not break the live disjoint v0 contract."""
    from odyssey_apps import (
        ApplicationRegistry,
        Route,
        RouteOutcome,
        RoutePlan,
        validate_route_plan,
    )

    source = "Hoy compré pan y leche."
    case = next(item for item in CASES if item["id"] == "F11")
    assert case["source"] == source
    candidates = validate_fact_candidate_proposal(source, _from_design(case))
    assert len(candidates.candidates) == 2
    catalog = ApplicationRegistry.from_descriptors(()).catalog(enabled_ids=())
    v0 = RoutePlan(RouteOutcome.ROUTE, (Route("temporal", source),))
    assert validate_route_plan(v0, source, catalog) == v0
    # No adapter is permitted to reinterpret the two candidate records as two
    # independent canonical purchases or as already-executable v0 routes.
    assert not any(hasattr(unit, "source_text") for unit in candidates.candidates)


def test_unit_roles_can_distinguish_polarity_conditions_and_corrections() -> None:
    """Design-level source scopes remain explicit; writes are left entirely to Core."""
    for case_id, expected in (
        ("F17", ("polarity", "polarity")),
        ("F18", ("polarity", "polarity")),
        ("F19", ("replacement",)),
        ("F20", ("condition", "condition")),
    ):
        case = next(item for item in CASES if item["id"] == case_id)
        result = validate_fact_candidate_proposal(case["source"], _from_design(case))
        observed = tuple(
            scope.role
            for unit in result.candidates
            for scope in unit.scopes
            if scope.role in {"polarity", "replacement", "condition"}
        )
        assert observed == expected
        assert not hasattr(result, "write")


def test_preview_inherited_role_never_uses_wrong_prior_source_excerpt() -> None:
    """An inherited group must cite the original group, not the preceding event text."""
    case = next(item for item in CASES if item["id"] == "F01")
    preview = as_candidate_preview(
        validate_fact_candidate_proposal(case["source"], _from_design(case))
    )
    inherited = [
        role
        for role in preview["candidates"][1]["roles"]
        if role["provenance"] == "inherited" and role["role"] == "participants"
    ]
    assert len(inherited) == 1
    assert inherited[0]["source"] == "mi mujer y mis hijos"
    assert inherited[0]["authority"] is None
