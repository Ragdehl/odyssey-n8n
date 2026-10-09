"""Core owns candidate evidence validation, Luna opt-in, and fail-closed source checks."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from odyssey_apps.fact_candidate_core import to_core_candidate_context
from odyssey_apps.fact_candidates import validate_fact_candidate_proposal
from odyssey_apps.fact_temporal import bind_temporal_to_fact_candidates
from odyssey_apps.router import RouterError
from odyssey_core.candidate_context import (
    MAX_CORE_CANDIDATE_CONTEXT_BYTES,
    CoreCandidateContext,
    CoreCandidateRole,
    CoreSourceSpan,
)
from odyssey_core.experimental_luna_planning import (
    OpenAILunaExperimentalPlanner,
    PlannerEscalation,
    render_luna_experimental_prompt,
)
from odyssey_core.request_planning import LUNA_DYNAMIC_CONTEXT_MARKER, RequestPlanningError
from odyssey_core.temporal_interpretation import TemporalInterpretation, TemporalMention
from odyssey_core.temporal_resolution import TemporalResolution, TemporalResolutionKind
from tests.apps.test_fact_candidates import CASES, _from_design

ROOT = Path(__file__).resolve().parents[2]
CLOCK = {"date": "2026-10-09", "time": "12:30", "timezone": "Europe/Paris"}


def _context(case_id: str) -> CoreCandidateContext:
    case = next(row for row in CASES if row["id"] == case_id)
    return to_core_candidate_context(
        validate_fact_candidate_proposal(case["source"], _from_design(case))
    )


def _schema() -> dict[str, Any]:
    return json.loads((ROOT / "config/note-schema.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", CASES, ids=lambda x: x["id"])
def test_all_26_design_cases_revalidate_at_independent_core_boundary(case: dict[str, Any]) -> None:
    """Core accepts 56 units as source hints, without trusting app-side validation."""
    packet = to_core_candidate_context(
        validate_fact_candidate_proposal(case["source"], _from_design(case))
    )
    assert packet.source == case["source"]
    assert len(packet.candidates) == len(case["expected_units"])
    packet.validate(case["source"])
    assert len(packet.prompt_payload_bytes()) <= MAX_CORE_CANDIDATE_CONTEXT_BYTES
    assert "canonical_id" not in packet.prompt_payload_bytes().decode("utf-8")
    assert "note_type" not in packet.prompt_payload_bytes().decode("utf-8")
    assert "write_intent" not in packet.prompt_payload_bytes().decode("utf-8")


def test_core_rejects_forged_offset_even_after_router_validation() -> None:
    """The independent Core boundary must not trust a mutated app dataclass."""
    original = _context("F26")
    candidate = original.candidates[0]
    forged_span = CoreSourceSpan(
        candidate.anchors[0].text, candidate.anchors[0].start + 1, candidate.anchors[0].end + 1
    )
    invalid = replace(
        original,
        candidates=(replace(candidate, anchors=(forged_span,)), *original.candidates[1:]),
    )
    with pytest.raises(ValueError, match="ungrounded"):
        invalid.validate(original.source)


def test_core_rejects_forged_inherited_scope_roles_and_stale_user_requests() -> None:
    """A source hint has no authority to become NoteSchema metadata or a different user message."""
    original = _context("F01")
    prior = original.candidates[0]
    bad = replace(
        original,
        candidates=(
            replace(prior, roles=(*prior.roles, CoreCandidateRole("note_type", prior.anchors[0]))),
            *original.candidates[1:],
        ),
    )
    with pytest.raises(ValueError, match="not permitted"):
        bad.validate(original.source)
    with pytest.raises(ValueError, match="full current source"):
        original.validate("A new different message")
    with pytest.raises(RouterError, match="Core preflight"):
        invalid_app = validate_fact_candidate_proposal(
            original.source,
            _from_design(next(x for x in CASES if x["id"] == "F01")),
        )
        first = invalid_app.candidates[0]

        forged = replace(first.anchors[0], start=9999)
        to_core_candidate_context(
            replace(
                invalid_app,
                candidates=(replace(first, anchors=(forged,)), *invalid_app.candidates[1:]),
            )
        )


def test_ordinary_luna_prompt_is_byte_identical_when_opt_in_absent() -> None:
    """Current production prompt/schema/cache contract remains wholly unchanged."""
    canonical = _schema()
    old = render_luna_experimental_prompt(canonical, CLOCK)
    actual = render_luna_experimental_prompt(canonical, CLOCK, candidate_context=None)
    assert actual == old
    assert hashlib.sha256(actual.encode()).hexdigest() == hashlib.sha256(old.encode()).hexdigest()
    assert old.count(LUNA_DYNAMIC_CONTEXT_MARKER) == 1
    assert "Unverified source-scoped candidate hints" not in old


def test_candidate_hints_are_only_in_dynamic_prompt_not_shared_cache_prefix() -> None:
    """No personalized source evidence may enter a cache prefix shared across requests."""
    source_hint = _context("F01")
    old = render_luna_experimental_prompt(_schema(), CLOCK)
    new = render_luna_experimental_prompt(_schema(), CLOCK, candidate_context=source_hint)
    assert old != new
    old_static, old_dynamic = old.split(LUNA_DYNAMIC_CONTEXT_MARKER, 1)
    new_static, new_dynamic = new.split(LUNA_DYNAMIC_CONTEXT_MARKER, 1)
    assert old_static == new_static
    assert new_dynamic.startswith(old_dynamic)
    assert "candidate-1" in new_dynamic and "candidate-3" in new_dynamic
    assert "mi mujer y mis hijos" in new_dynamic
    assert "Independently apply Core" in new_dynamic
    assert "canonical_id" not in new_dynamic


def test_luna_opt_in_consumes_three_candidates_but_cannot_execute_any_of_them() -> None:
    """Vertical provider-fake seam: Router evidence -> real Core Luna -> escalation."""
    packet = _context("F01")
    captured: list[dict[str, Any]] = []
    reply = SimpleNamespace(
        status="completed",
        id="synthetic",
        output_text=json.dumps(
            {
                "result": {
                    "outcome": "ESCALATE",
                    "actions": None,
                    "limitations": None,
                    "clarification_code": None,
                }
            }
        ),
        usage=None,
    )
    client = SimpleNamespace(
        responses=SimpleNamespace(create=lambda **payload: captured.append(payload) or reply)
    )
    planner = OpenAILunaExperimentalPlanner(client, _schema(), CLOCK, candidate_context=packet)
    result = planner.plan(packet.source)
    assert isinstance(result, PlannerEscalation)
    assert len(captured) == 1
    assert captured[0]["store"] is False
    assert captured[0]["input"][1]["content"] == packet.source
    assert "candidate-3" in str(captured[0]["input"][0]["content"])
    assert planner.last_cache_diagnostics is not None
    assert not hasattr(planner, "execute")


def test_luna_rejects_stale_proposal_before_provider_io() -> None:
    """An inherited context may not be used with a different current request."""
    packet = _context("F13")
    called: list[str] = []
    fake = SimpleNamespace(responses=SimpleNamespace(create=lambda **_k: called.append("called")))
    planner = OpenAILunaExperimentalPlanner(fake, _schema(), CLOCK, candidate_context=packet)
    with pytest.raises(RequestPlanningError, match="grounded in request"):
        planner.plan("Yesterday Eric was somewhere else")
    assert not called


def test_temporal_normalization_remains_separate_from_router_candidate_hints() -> None:
    """Existing Temporal can resolve dates, but candidate packet cannot authorize them."""
    case = next(x for x in CASES if x["id"] == "F01")
    source_proposal = validate_fact_candidate_proposal(case["source"], _from_design(case))
    temporal = TemporalInterpretation(
        case["source"],
        (
            TemporalMention(
                "Ayer",
                TemporalResolution(TemporalResolutionKind.EXACT_DATE, exact_date="2026-10-08"),
            ),
            TemporalMention(
                "a las tres por la tarde", TemporalResolution(TemporalResolutionKind.UNSPECIFIED)
            ),
            TemporalMention(
                "hoy",
                TemporalResolution(TemporalResolutionKind.EXACT_DATE, exact_date="2026-10-09"),
            ),
        ),
    )
    resolved = bind_temporal_to_fact_candidates(source_proposal, temporal)
    assert any(item.origin == "inherited" and item.role == "date" for item in resolved)
    packet = to_core_candidate_context(source_proposal)
    assert "2026-10-08" not in packet.prompt_payload_bytes().decode("utf-8")
    assert "2026-10-09" not in packet.prompt_payload_bytes().decode("utf-8")
    # Temporal's existing DomainInterpretation remains the exclusive exact-date
    # authorization route. The opt-in candidate packet merely explains scope.
    from odyssey_core.temporal_interpretation import TemporalInterpreterError

    # Full Temporal cannot grant a mixed exact+UNSPECIFIED cohort a durable
    # Core anchor. The candidate packet must not lower that established bar.
    with pytest.raises(TemporalInterpreterError, match="not an exact Core anchor"):
        temporal.core_domain_interpretation()


def test_full_router_temporal_core_luna_handoff_remains_read_only() -> None:
    """Vertical non-writing regression: source Router -> Temporal -> Core planner."""
    case = next(x for x in CASES if x["id"] == "F13")
    router = validate_fact_candidate_proposal(case["source"], _from_design(case))
    assert len(router.candidates) == 3
    temporal = TemporalInterpretation(
        case["source"],
        (
            TemporalMention(
                "Ayer",
                TemporalResolution(TemporalResolutionKind.EXACT_DATE, exact_date="2026-10-08"),
            ),
            TemporalMention(
                "Mañana",
                TemporalResolution(TemporalResolutionKind.EXACT_DATE, exact_date="2026-10-10"),
            ),
            TemporalMention(
                "Hoy",
                TemporalResolution(TemporalResolutionKind.EXACT_DATE, exact_date="2026-10-09"),
            ),
        ),
    )
    by_unit = bind_temporal_to_fact_candidates(router, temporal)
    assert [x.candidate_id for x in by_unit if x.role == "date"] == [
        "candidate-1",
        "candidate-2",
        "candidate-3",
    ]
    domain = temporal.core_domain_interpretation()
    assert len(domain.temporal_references()) == 3
    core_packet = to_core_candidate_context(router)
    assert core_packet.candidates[1].roles[0].role == "date"
    assert core_packet.candidates[1].roles[1].role == "reference"
    assert "2026-10-10" not in core_packet.prompt_payload_bytes().decode("utf-8")
    captured: list[dict[str, Any]] = []
    reply = SimpleNamespace(
        status="completed",
        id="synthetic",
        usage=None,
        output_text=json.dumps(
            {
                "result": {
                    "outcome": "ESCALATE",
                    "actions": None,
                    "limitations": None,
                    "clarification_code": None,
                }
            }
        ),
    )
    fake = SimpleNamespace(
        responses=SimpleNamespace(create=lambda **payload: captured.append(payload) or reply)
    )
    planner = OpenAILunaExperimentalPlanner(
        fake,
        _schema(),
        CLOCK,
        domain_interpretation=domain,
        candidate_context=core_packet,
    )
    result = planner.plan(core_packet.source)
    assert isinstance(result, PlannerEscalation)
    assert len(captured) == 1
    submitted = str(captured[0]["input"][0]["content"])
    assert "candidate-3" in submitted and "2026-10-10" in submitted
    assert captured[0]["input"][1]["content"] == case["source"]
    assert captured[0]["store"] is False
    assert not hasattr(planner, "execute")


def test_invalid_candidate_kind_type_fails_as_validation_not_unhandled_type_error() -> None:
    """Untrusted dataclasses cannot smuggle malformed types through a hash membership check."""
    packet = _context("F26")
    invalid = replace(
        packet,
        candidates=(replace(packet.candidates[0], kind=[]), *packet.candidates[1:]),
    )
    with pytest.raises(ValueError, match="kind or ambiguity"):
        invalid.validate(packet.source)


def test_candidate_context_input_size_is_explicitly_accounted_for() -> None:
    """New per-request evidence bytes must be visible in input-size diagnostics."""
    packet = _context("F01")
    sizing: dict[str, int] = {}
    rendered = render_luna_experimental_prompt(
        _schema(), CLOCK, candidate_context=packet, size_components=sizing
    )
    assert "candidate_context_bytes" in sizing
    assert sizing["candidate_context_bytes"] > len(packet.prompt_payload_bytes())
    assert sizing["candidate_context_bytes"] < len(rendered.encode("utf-8"))
    normal: dict[str, int] = {}
    render_luna_experimental_prompt(_schema(), CLOCK, size_components=normal)
    assert "candidate_context_bytes" not in normal
