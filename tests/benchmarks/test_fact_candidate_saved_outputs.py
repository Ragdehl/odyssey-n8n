"""The saved-output reviewer is offline and never certifies model quality."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from benchmarks.fact_candidate_v2_preflight.compare_saved_outputs import (
    compare_saved_proposals,
)
from tests.apps.test_fact_candidates import CASES, _from_design


def _case(case_id: str) -> dict:
    """Use synthetic reviewed oracle data, never personal vault content."""
    return _from_design(next(case for case in CASES if case["id"] == case_id))


def test_exact_fixture_matches_still_require_semantic_review() -> None:
    """Matching a fixture cannot be advertised as provider-model validation."""
    report = compare_saved_proposals(
        {case_id: _case(case_id) for case_id in ("F09", "F10", "F14", "F27")}
    )
    assert report["all_fixture_matches"] is True
    assert report["human_semantic_review_required"] is True
    assert report["live_model_quality_verified"] is False


def test_prior_f14_future_plan_classification_is_visible() -> None:
    """The known prior kind discrepancy must not be hidden by a unit-count pass."""
    f14 = _case("F14")
    f14["units"][1]["kind"] = "plan"
    report = compare_saved_proposals({"F14": f14})
    assert report["all_fixture_matches"] is False
    assert "candidate_2_kind" in report["cases"]["F14"]["differences"]


def test_f27_over_grouping_cannot_pass() -> None:
    """A single shared event is not a substitute for sequential conversations."""
    f27 = _case("F27")
    f27["units"].pop(1)
    report = compare_saved_proposals({"F27": f27})
    assert "candidate_count" in report["cases"]["F27"]["differences"]


def test_f09_subject_swap_and_f10_missing_participant_are_visible() -> None:
    """Count/kind alone do not establish independent facts or both participants."""
    f09 = _case("F09")
    f09["units"][1] = copy.deepcopy(f09["units"][0])
    f10 = _case("F10")
    f10["units"][0]["scoped_source"].pop(0)
    report = compare_saved_proposals({"F09": f09, "F10": f10})
    # The source validator now rejects identical cloned units before the
    # offline comparison can mistake them for separate source facts.
    assert report["cases"]["F09"]["differences"] == ["invalid_output"]
    assert report["cases"]["F09"]["error_type"] == "RouterError"
    assert "candidate_1_scopes" in report["cases"]["F10"]["differences"]


def test_f14_unresolved_pronoun_must_stay_unresolved() -> None:
    """A fabricated resolution must not be accepted as a pending identity."""
    f14 = _case("F14")
    f14["units"][1]["state"] = "candidate"
    report = compare_saved_proposals({"F14": f14})
    assert "candidate_2_state" in report["cases"]["F14"]["differences"]


def test_cli_accepts_saved_synthetic_result_without_model_access(tmp_path: Path) -> None:
    """Exercise the review command boundary using only a local synthetic JSON file."""
    payload = tmp_path / "saved-result.json"
    payload.write_text(json.dumps({"F14": _case("F14")}), encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "benchmarks.fact_candidate_v2_preflight.compare_saved_outputs",
            str(payload),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["cases"]["F14"]["fixture_match"] is True
    assert report["human_semantic_review_required"] is True
    assert report["live_model_quality_verified"] is False


def test_ungrounded_source_and_unknown_cases_fail_closed() -> None:
    """No invented quote and no unrelated personal case can enter the reviewer."""
    f10 = _case("F10")
    f10["units"][0]["anchors"][0]["text"] = "invented text"
    report = compare_saved_proposals({"F10": f10})
    assert report["cases"]["F10"]["differences"] == ["invalid_output"]
    with pytest.raises(ValueError):
        compare_saved_proposals({"USER_PRIVATE_CASE": f10})
