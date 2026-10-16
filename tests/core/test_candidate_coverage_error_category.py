"""Bounded coverage diagnostic categories retain the real error family."""

import pytest

from odyssey_core.application import (
    CandidateCoverageErrorCategory,
    _candidate_coverage_error_category,
)
from odyssey_core.candidate_attribution import CandidateAttributionError
from odyssey_core.candidate_property_evidence import CandidatePropertyEvidenceError


@pytest.mark.parametrize(
    "exception,expected",
    [
        (ValueError("ordinary"), CandidateCoverageErrorCategory.VALUE_ERROR),
        (
            CandidateAttributionError("internal semantic details"),
            CandidateCoverageErrorCategory.VALUE_ERROR,
        ),
        (
            CandidatePropertyEvidenceError("internal source"),
            CandidateCoverageErrorCategory.VALUE_ERROR,
        ),
        (TypeError("wrong shape"), CandidateCoverageErrorCategory.TYPE_ERROR),
        (RuntimeError("unavailable"), CandidateCoverageErrorCategory.RUNTIME_ERROR),
        (KeyError("unknown"), CandidateCoverageErrorCategory.UNEXPECTED_ERROR),
    ],
)
def test_specialized_coverage_rejections_keep_safe_bounded_category(exception, expected):
    assert _candidate_coverage_error_category(exception) == expected
    assert "internal" not in _candidate_coverage_error_category(exception).value
