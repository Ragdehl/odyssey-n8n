"""One actual Core graph review enriches two same-day facts before the canonical Writer.

No real provider, no special-case time guessing, no alternate persistence.
"""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

from odyssey_core.application import ApplicationStatus, execute_request
from odyssey_core.candidate_attribution import (
    OpenAICoreCandidateAttributor,
    review_model_candidate_fact_coverage,
)
from odyssey_core.candidate_context import (
    CoreCandidate,
    CoreCandidateContext,
    CoreCandidateRole,
    CoreSourceSpan,
)
from odyssey_core.candidate_coverage import PreparedCoreCandidateCoverage
from tests.core.test_e2_fact_temporal_ownership import PHRASES, SRC, ctx, plan
from tests.runtime.test_fact_candidate_planning_vertical import _sdk_fake
from tests.runtime.test_fact_candidate_semantic_luna_vertical import SCHEMA
from tests.runtime.test_full_message_corpus_regression import fresh_corpus_vault


def _source_context():
    source = SRC
    candidates = []
    for index, clause in enumerate(
        ("Hoy por la tarde llamé a Bea.", "Hoy por la noche vi a Marta."), 1
    ):
        start = source.index(clause)
        qualifier = PHRASES[index - 1][1]
        qstart = source.index(qualifier, start)
        candidates.append(
            CoreCandidate(
                f"candidate-{index}",
                "occurrence",
                "candidate",
                (CoreSourceSpan(clause, start, start + len(clause)),),
                (
                    CoreCandidateRole(
                        "time_approx", CoreSourceSpan(qualifier, qstart, qstart + len(qualifier))
                    ),
                    CoreCandidateRole(
                        "predicate",
                        CoreSourceSpan(
                            ("llamé", "vi")[index - 1],
                            source.index(("llamé", "vi")[index - 1], start),
                            source.index(("llamé", "vi")[index - 1], start)
                            + len(("llamé", "vi")[index - 1]),
                        ),
                    ),
                    CoreCandidateRole(
                        "participants",
                        CoreSourceSpan(
                            ("Bea", "Marta")[index - 1],
                            source.index(("Bea", "Marta")[index - 1], start),
                            source.index(("Bea", "Marta")[index - 1], start)
                            + len(("Bea", "Marta")[index - 1]),
                        ),
                    ),
                ),
                (),
            )
        )
    return CoreCandidateContext(
        source,
        tuple(candidates),
        scoped_route_source=True,
        hybrid_interpretation_mode=True,
        verified_route_temporal=ctx().domains[0],
    )


def _run(tmp_path, *, changed=None):
    repository, index, semantic, embedder = fresh_corpus_vault(tmp_path)
    original = plan()
    source = _source_context()
    payload = {
        "candidates": [
            {
                "candidate_id": f"candidate-{index}",
                "source_quote": candidate.anchors[0].text,
                "fact_ordinals": [index - 1],
                "planned_fact_texts": [original.actions[0].units[0].facts[index - 1]],
                "pending_reason": None,
            }
            for index, candidate in enumerate(source.candidates, 1)
        ]
    }
    if changed is not None:
        changed(payload)
    sdk, calls = _sdk_fake(payload)
    attributor = OpenAICoreCandidateAttributor(sdk)
    inspected = []

    def review(text, core_context, current):
        evidence = review_model_candidate_fact_coverage(
            text,
            core_context,
            current,
            attributor,
            verified_temporal=ctx().domains[0],
            qualitative_context=replace(ctx(), candidates=core_context),
        )
        inspected.append(evidence)
        return evidence

    result = execute_request(
        SRC,
        planner=SimpleNamespace(plan=lambda *_: original),
        repository=repository,
        schema=SCHEMA,
        context_index=index,
        semantic_index=semantic,
        embedder=embedder,
        contextual_reasoner=object(),
        context_limit=5,
        actor="fixture",
        now="2026-10-15T10:00:00+02:00",
        candidate_context=source,
        candidate_coverage_factory=review,
        request_id_factory=lambda: "e2-reviewed-same-day",
    )
    return result, repository, original, inspected, calls


def test_one_real_core_review_enriches_both_facts_in_one_writer_transaction(tmp_path):
    result, repository, original, inspected, calls = _run(tmp_path)
    assert result.status is ApplicationStatus.COMPLETED, result.clarification_code
    assert len(calls) == 1
    assert isinstance(inspected[0], PreparedCoreCandidateCoverage)
    assert original.actions[0].units[0].facts == ("Llamé a Bea.", "Vi a Marta.")
    saved = repository.read_text("calendar/days/2026-10-15.md")
    assert "Llamé a Bea (por la tarde)." in saved
    assert "Vi a Marta (por la noche)." in saved
    assert "15:00" not in saved and "21:00" not in saved


def test_review_swapped_fact_ownership_blocks_all_writes(tmp_path):
    def tamper(payload):
        payload["candidates"][0]["fact_ordinals"] = [1]
        payload["candidates"][0]["planned_fact_texts"] = ["Vi a Marta."]
        payload["candidates"][1]["fact_ordinals"] = [0]
        payload["candidates"][1]["planned_fact_texts"] = ["Llamé a Bea."]

    result, repository, _, _, calls = _run(tmp_path, changed=tamper)
    assert result.status is ApplicationStatus.NEEDS_ATTENTION
    assert result.clarification_code == "CANDIDATE_COVERAGE_REVIEW_REQUIRED"
    assert len(calls) == 1
    assert "calendar/days/2026-10-15.md" not in repository.list_markdown_paths()


def test_review_failure_keeps_all_original_person_notes_untouched(tmp_path):
    result, repository, *_ = _run(tmp_path)
    assert result.status is ApplicationStatus.COMPLETED
    assert "por la tarde" not in repository.read_text("Bea.md")
    assert "por la noche" not in repository.read_text("Marta.md")


def test_prewrite_plan_contract_rejects_unrelated_sentence_even_with_matching_digest():
    import hashlib

    import pytest

    from odyssey_core.candidate_coverage import (
        validate_prewrite_fact_text_enrichment,
    )

    original = plan()
    unit = original.actions[0].units[0]
    fake = replace(
        original,
        actions=(
            replace(
                original.actions[0],
                units=(replace(unit, facts=("A totally new fact.", "Vi a Marta.")),),
            ),
        ),
    )
    _ = hashlib.sha256(repr(original).encode()).hexdigest()
    with pytest.raises(ValueError, match="non-source fact change"):
        validate_prewrite_fact_text_enrichment(original, fake, _source_context())
