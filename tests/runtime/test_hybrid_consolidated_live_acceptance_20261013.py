"""Immutable genuinely model-reviewed fixes on isolated canonical Markdown.

Every successful example uses authentic Router, Temporal, ordinary Core Planner
and independent Core reviewer outputs. No paid provider call is made on replay.
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

# These captures were collected at different points with authentic outputs.
# Later source-review calls are never laundered into synthetic model evidence.
RECEIPTS = {
    "F05": "hybrid_core_review_v1",
    "F07": "hybrid_semantic_live_v4",
    "F08": "hybrid_core_review_v1",
    "F10": "hybrid_semantic_live_v6",
    "F12": "hybrid_semantic_live_v6",
    "F13": "hybrid_semantic_live_v2",
    "F15": "hybrid_semantic_live_v5",
}
STRICT = {
    "F05": {
        "calendar/days/2026-10-09.md": ("- Cenaremos con [[Ana|Ana]] en Toulouse.",),
        "calendar/days/2026-10-10.md": ("- 10:00 — Cenaremos con [[Luis|Luis]] en Albi.",),
    },
    "F07": {
        "calendar/days/2026-10-04.md": (
            "- 15:00 — Veo a [[Bea|Bea]].",
            "- 17:00 — Veo a [[Luis|Luis]].",
        )
    },
    "F08": {
        "calendar/days/2026-10-05.md": (
            "- 10:00 — [[Marta|Marta]] irá al médico.",
            "- 10:00 — [[Luis|Luis]] irá al dentista.",
        )
    },
    "F10": {"Marta.md": ("- Marta y [[Luis|Luis]] se conocieron en Lyon.",)},
    "F12": {
        "Bea.md": (
            "- Bea y mis hijos limpiaron el garaje.",
            "- Bea y mis hijos montaron los muebles después.",
        )
    },
    "F13": {
        "calendar/days/2026-10-03.md": ("- Ayer hablé con [[Eric|Eric]].",),
        "calendar/days/2026-10-04.md": ("- Compré pan.",),
        "calendar/days/2026-10-05.md": ("- Iré al cine con [[Eric|Eric]].",),
    },
    "F15": {
        "Bea.md": ("- Se quedó en casa [[calendar/days/2026-10-03|03-10-2026]].",),
        "calendar/days/2026-10-03.md": (
            "- Mis hijos fueron al parque.",
            "- Después yo preparé la cena.",
        ),
    },
}


@pytest.mark.parametrize("case", tuple(RECEIPTS))
def test_real_models_write_all_expected_facts_with_readback(case: str, tmp_path: Path):
    source = next(row["source"] for row in CASES if row["id"] == case)
    receipt = json.loads(
        (ROOT / f"benchmarks/application_router/{RECEIPTS[case]}/{case}.json").read_text()
    )
    assert receipt["status"] == "completed"
    sdk = FrozenProvider(receipt["real_model_outputs"])
    repo, context, semantic, embedder = fresh_corpus_vault(tmp_path)
    result = execute_candidate_routed_message(
        source,
        router=OpenAIFactCandidateRouter(sdk, prompt_revision="v4"),
        temporal=OpenAITemporalInterpreter(
            sdk, CLOCK, max_output_tokens=1536, scoped_date_time_context=True
        ),
        core_planner_factory=lambda hints, domain: OpenAILunaExperimentalPlanner(
            sdk, SCHEMA, CLOCK, candidate_context=hints, domain_interpretation=domain
        ),
        core_candidate_attributor=OpenAICoreCandidateAttributor(sdk),
        repository=repo,
        schema=SCHEMA,
        context_index=context,
        semantic_index=semantic,
        embedder=embedder,
        contextual_reasoner=object(),
        actor="verified-all-real-models-fixture-only",
        now=NOW,
        context_limit=5,
        request_id_factory=lambda: f"frozen-20261013-{case}",
        bundle_compiler=compile_hybrid_candidate_bundle,
    )
    assert result.status is ApplicationStatus.COMPLETED, result.execution_flow
    assert len(sdk.calls) == len(receipt["real_model_outputs"])
    for path, expected_facts in STRICT[case].items():
        note = repo.read_text(path)
        for expected in expected_facts:
            assert expected in note, (case, path, note)
        assert note.count("odyssey:fact request=") >= len(expected_facts)
        assert "  " not in "\n".join(line for line in note.splitlines() if line.startswith("- ")), (
            case,
            path,
        )
    # The source was never sent to the Planner as a sibling fragment when
    # distinct independent Core routes were involved.
    assert not any(
        note.endswith("a las")
        for path in STRICT[case]
        for note in repo.read_text(path).splitlines()
        if note.startswith("- ")
    )


def test_reviewer_receipts_are_new_real_calls_not_forged(tmp_path: Path):
    del tmp_path
    review = json.loads(
        (ROOT / "benchmarks/application_router/hybrid_core_review_v1/SUMMARY.json").read_text()
    )
    assert {x["case"] for x in review["results"]} == {"F05", "F08"}
    assert all(x["status"] == "completed" and x["reviewer_calls"] == 1 for x in review["results"])
    assert 0 < review["new_estimated_usd"] < 0.05
    assert review["estimated_cumulative_usd"] < 1.0
    for case in ("F05", "F08"):
        receipt = json.loads(
            (ROOT / f"benchmarks/application_router/hybrid_core_review_v1/{case}.json").read_text()
        )
        assert receipt["fresh_reviewer_calls"] == 1
        assert receipt["real_model_outputs"][-1]["input_tokens"] > 0
        assert receipt["real_model_outputs"][-1]["output_tokens"] > 0
