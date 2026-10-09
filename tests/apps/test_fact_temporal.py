"""Source-only Router candidate scope handoff to existing Temporal, with no writes."""

from __future__ import annotations

import pytest

from odyssey_apps.fact_candidates import validate_fact_candidate_proposal
from odyssey_apps.fact_temporal import bind_temporal_to_fact_candidates
from odyssey_apps.router import RouterError
from odyssey_core.temporal_interpretation import TemporalInterpretation, TemporalMention
from odyssey_core.temporal_resolution import TemporalResolution, TemporalResolutionKind
from tests.apps.test_fact_candidates import CASES, _from_design


def _case(case_id: str):
    case = next(row for row in CASES if row["id"] == case_id)
    return validate_fact_candidate_proposal(case["source"], _from_design(case))


def _date(text: str, value: str) -> TemporalMention:
    return TemporalMention(
        text, TemporalResolution(TemporalResolutionKind.EXACT_DATE, exact_date=value)
    )


def _unknown(text: str) -> TemporalMention:
    return TemporalMention(text, TemporalResolution(TemporalResolutionKind.UNSPECIFIED))


def test_three_activities_inherit_participants_but_not_the_first_clock_time() -> None:
    """A later candidate inherits date source only; time stays on the park event."""
    proposal = _case("F01")
    temporal = TemporalInterpretation(
        proposal.source,
        (
            _date("Ayer", "2026-10-08"),
            _unknown("a las tres por la tarde"),
            _date("hoy", "2026-10-09"),
        ),
    )
    edges = bind_temporal_to_fact_candidates(proposal, temporal)
    as_role = {(e.candidate_id, e.role): e for e in edges}
    assert as_role[("candidate-1", "date")].resolution.exact_date == "2026-10-08"
    assert as_role[("candidate-2", "date")].resolution.exact_date == "2026-10-08"
    assert as_role[("candidate-2", "date")].origin == "inherited"
    assert ("candidate-2", "time") not in as_role
    assert as_role[("candidate-1", "time")].has_exact_source_shape is False
    assert as_role[("candidate-3", "date")].resolution.exact_date == "2026-10-09"
    assert ("candidate-3", "time") not in as_role


def test_shared_time_in_later_source_is_not_moved_or_fabricated() -> None:
    """Forward lexical time can scope two earlier class days without a dependency."""
    proposal = _case("F21")
    temporal = TemporalInterpretation(
        proposal.source, (_unknown("La semana que viene"), _unknown("a las 18h"))
    )
    scopes = bind_temporal_to_fact_candidates(proposal, temporal)
    assert len(scopes) == 4
    clocks = [scope for scope in scopes if scope.role == "time"]
    assert len(clocks) == 2
    assert clocks[0].source.start == clocks[1].source.start
    assert all(clock.status == "matched" for clock in clocks)
    assert all(clock.has_exact_source_shape is False for clock in clocks)


def test_report_changes_subject_to_object_without_subject_inheritance() -> None:
    """A pronoun does not license a canonical identity or leak the earlier date."""
    proposal = _case("F26")
    temporal = TemporalInterpretation(
        proposal.source, (_date("ayer", "2026-10-08"), _date("hoy", "2026-10-09"))
    )
    bindings = bind_temporal_to_fact_candidates(proposal, temporal)
    assert [(b.candidate_id, b.role, b.resolution.exact_date) for b in bindings] == [
        ("candidate-1", "date", "2026-10-08"),
        ("candidate-2", "date", "2026-10-09"),
    ]


def test_time_relation_is_not_invented_into_an_exact_clock() -> None:
    """An inherited earlier hour remains source evidence, not instant authority."""
    proposal = _case("F08")
    temporal = TemporalInterpretation(
        proposal.source,
        (_date("Mañana", "2026-10-10"), _unknown("a las 10")),
    )
    scopes = bind_temporal_to_fact_candidates(proposal, temporal)
    second = {s.role: s for s in scopes if s.candidate_id == "candidate-2"}
    assert second["date"].origin == "inherited"
    assert second["time"].origin == "inherited"
    assert second["time_relation"].status == "missing"
    assert second["time_relation"].has_exact_source_shape is False


def test_missing_temporal_interpretation_retains_unresolved_original_source() -> None:
    """A missing Temporal response never turns inferred wording into an exact date."""
    proposal = _case("F02")
    scopes = bind_temporal_to_fact_candidates(proposal, None)
    assert len(scopes) >= 5
    assert all(s.status == "missing" and s.resolution is None for s in scopes)
    assert all(not s.has_exact_source_shape for s in scopes)


def test_mismatched_temporal_source_fails_closed_before_any_mutation() -> None:
    proposal = _case("F01")
    wrong = TemporalInterpretation("Ayer fuimos al cine.", (_date("Ayer", "2026-10-08"),))
    with pytest.raises(RouterError, match="does not match original"):
        bind_temporal_to_fact_candidates(proposal, wrong)


def test_new_explicit_date_overrides_proposed_inherited_date() -> None:
    """Do not attach a previous day when the next activity explicitly says today."""
    from tests.apps.test_fact_candidates import _from_design

    case = next(row for row in CASES if row["id"] == "F01")
    payload = _from_design(case)
    payload["units"][2]["inheritance"].append({"role": "date", "from_unit": 1})
    proposal = validate_fact_candidate_proposal(case["source"], payload)
    temporal = TemporalInterpretation(
        proposal.source,
        (
            _date("Ayer", "2026-10-08"),
            _unknown("a las tres por la tarde"),
            _date("hoy", "2026-10-09"),
        ),
    )
    bindings = bind_temporal_to_fact_candidates(proposal, temporal)
    third_dates = [x for x in bindings if x.candidate_id == "candidate-3" and x.role == "date"]
    assert len(third_dates) == 1
    assert third_dates[0].origin == "explicit"
    assert third_dates[0].resolution.exact_date == "2026-10-09"


def test_clock_wording_cannot_be_accepted_as_exact_time_from_a_date_only_shape() -> None:
    """An incorrect Temporal date-only shape never becomes an exact clock instant."""
    proposal = _case("F08")
    temporal = TemporalInterpretation(
        proposal.source,
        (_date("Mañana", "2026-10-10"), _date("a las 10", "2026-10-10")),
    )
    clock = next(
        edge
        for edge in bind_temporal_to_fact_candidates(proposal, temporal)
        if edge.candidate_id == "candidate-1" and edge.role == "time"
    )
    assert clock.status == "matched"
    assert clock.has_exact_source_shape is False
