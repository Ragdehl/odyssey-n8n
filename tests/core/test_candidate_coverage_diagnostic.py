"""Safe diagnostics retain coverage rejection without exposing review details."""

from __future__ import annotations

from tests.runtime.test_fact_candidate_coverage_gate import _run
from tests.runtime.test_fact_candidate_provenance_readback import _two_items
from tests.runtime.test_fact_candidate_writes_e2e import _case


def test_coverage_rejection_exposes_only_allowlisted_exception_class_and_never_writes(tmp_path):
    case, context = _case("F11")

    def broken_review(*_args):
        raise RuntimeError("private model rationale and source must not escape")

    result, repository = _run(tmp_path, case["source"], context, _two_items(), broken_review)

    coverage = next(
        stage for stage in result.operational.stages if stage.name == "candidate_coverage"
    )
    assert coverage.outcome.value == "failed"
    assert coverage.error_category == "RuntimeError"
    assert "private model rationale" not in repr(result)
    assert result.action_results == ()
    assert result.affected_stable_note_ids == ()
    assert repository.list_markdown_paths() == []
