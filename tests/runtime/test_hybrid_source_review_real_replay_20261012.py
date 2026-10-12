"""Reproduce genuine source-review model behavior against disposable Markdown.

All provider outputs are immutable. No new provider call is made in tests.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from odyssey_apps.fact_candidates import OpenAIFactCandidateRouter
from odyssey_core.application import ApplicationStatus
from odyssey_core.candidate_attribution import OpenAICoreCandidateAttributor
from odyssey_core.experimental_luna_planning import OpenAILunaExperimentalPlanner
from odyssey_core.temporal_interpretation import OpenAITemporalInterpreter
from odyssey_runtime.candidate_route_dispatch import execute_candidate_routed_message
from odyssey_runtime.hybrid_group_compiler import compile_hybrid_candidate_bundle
from tests.apps.test_fact_candidates import CASES
from tests.runtime.test_candidate_pending_state import NOW
from tests.runtime.test_fact_candidate_semantic_luna_vertical import CLOCK, SCHEMA
from tests.runtime.test_full_message_corpus_regression import ROOT, fresh_corpus_vault
from tests.runtime.test_scoped_route_recorded_real_replay import FrozenProvider

CAPTURES = ROOT / "benchmarks/application_router/hybrid_source_review_v1"


@pytest.mark.parametrize(
    ("case_id", "expected", "days", "linked_people"),
    [
        ("F06", ApplicationStatus.COMPLETED, ("2026-10-04",), ("Ana",)),
        ("F13", ApplicationStatus.COMPLETED, ("2026-10-03", "2026-10-04", "2026-10-05"), ("Eric",)),
        ("F14", ApplicationStatus.PARTIAL, ("2026-10-03", "2026-10-04"), ("Eric", "Luis")),
    ],
)
def test_actual_source_review_and_core_have_source_grounded_canonical_readback(
    case_id: str,
    expected: ApplicationStatus,
    days: tuple[str, ...],
    linked_people: tuple[str, ...],
    tmp_path: Path,
) -> None:
    original = next(row["source"] for row in CASES if row["id"] == case_id)
    receipt = json.loads((CAPTURES / f"{case_id}.json").read_text())
    sdk = FrozenProvider(receipt["real_model_outputs"])
    repo, context, semantic, embedder = fresh_corpus_vault(tmp_path)
    originals = set(repo.list_markdown_paths())
    result = execute_candidate_routed_message(
        original,
        router=OpenAIFactCandidateRouter(sdk, prompt_revision="v4"),
        temporal=OpenAITemporalInterpreter(
            sdk, CLOCK, max_output_tokens=1536, scoped_date_time_context=True
        ),
        core_planner_factory=lambda candidate, domain: OpenAILunaExperimentalPlanner(
            sdk, SCHEMA, CLOCK, candidate_context=candidate, domain_interpretation=domain
        ),
        core_candidate_attributor=OpenAICoreCandidateAttributor(sdk),
        repository=repo,
        schema=SCHEMA,
        context_index=context,
        semantic_index=semantic,
        embedder=embedder,
        contextual_reasoner=object(),
        actor="frozen-genuine-source-review",
        now=NOW,
        context_limit=5,
        request_id_factory=lambda: "frozen-reviewed-" + case_id,
        bundle_compiler=compile_hybrid_candidate_bundle,
    )
    assert result.status is expected, result.execution_flow
    assert len(sdk.calls) == receipt["provider_calls"]
    created = set(repo.list_markdown_paths()) - originals
    assert created == {f"calendar/days/{day}.md" for day in days}
    rendered = "\n".join(repo.read_text(path) for path in sorted(created))
    for name in linked_people:
        assert f"[[{name}|{name}]]" in rendered
    if case_id == "F06":
        assert "compré pan" in rendered
        assert "Vi a [[Ana|Ana]]" in rendered
    elif case_id == "F13":
        assert rendered.count("[[Eric|Eric]]") == 2
        assert "Iré al cine con [[Eric|Eric]]" in rendered
        assert "compré pan" in rendered
    else:
        assert "[[Eric|Eric]] y [[Luis|Luis]]" in rendered
        assert "Iré al cine" not in rendered


def test_source_review_batch_preserves_all_real_model_receipts_and_pending_cases() -> None:
    summary = json.loads((CAPTURES / "SUMMARY.json").read_text())
    assert summary["finished_count"] == summary["requested_count"] == 6
    assert {x["case"] for x in summary["results"]} == {"F05", "F06", "F07", "F13", "F14", "F15"}
    for row in summary["results"]:
        receipt = json.loads((CAPTURES / f"{row['case']}.json").read_text())
        assert receipt["status"] == "finished"
        assert receipt["application_status"] == row["application_status"]
        assert receipt["provider_calls"] == len(receipt["real_model_outputs"])
        assert receipt["source_sha256"]
    assert (
        next(x for x in summary["results"] if x["case"] == "F07")["application_status"] == "failed"
    )
