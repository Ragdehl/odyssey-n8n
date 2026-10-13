"""Fresh GPT-6 Router + GPT-5.6 Core/Reviewer receipts; no provider calls in CI.

F26's genuine finalized independent reviewer is from hybrid_core_review_v2.
No model reply is synthesized or presumed to approve a different fact string.
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

RECEIPTS = {
    "F01": "hybrid_core_review_v3",
    "F02": "hybrid_core_review_v4",
    "F25": "hybrid_router_v5_end_to_end_v1",
    "F18": "hybrid_router_v5_end_to_end_v2",
    "F26": "hybrid_core_review_v2",
}
STRICT = {
    "F01": {
        "calendar/days/2026-10-03.md": (
            "- 15:00 — Fuimos con mi mujer y mis hijos al parque.",
            "- Después fuimos con mi mujer y mis hijos al cine.",
        ),
        "calendar/days/2026-10-04.md": ("- Vamos a ir a un concierto.",),
    },
    "F02": {
        "calendar/days/2026-10-04.md": (
            "- mis hijos, mi mujer y yo iremos a merendar sobre las 16h.",
        ),
        "calendar/days/2026-10-05.md": ("- mis hijos, mi mujer y yo iremos al parque.",),
        "calendar/days/2026-10-11.md": (
            "- 11:00 — mis hijos, mi mujer y yo iremos a un vide-grenier.",
        ),
    },
    "F25": {
        "La casa de Toulouse.md": (
            "- Tiene humedad en el sótano.",
            "- Necesita reparar el tejado.",
        ),
    },
    "F18": {
        "calendar/days/2026-10-03.md": ("- Ayer no vi a Ana, pero sí hablé con Luis.",),
    },
    "F26": {
        "El informe.md": (
            "- Llegó [[calendar/days/2026-10-03|03-10-2026]].",
            "- Lo envié a [[Ana|Ana]] [[calendar/days/2026-10-04|04-10-2026]].",
        ),
    },
}


@pytest.mark.parametrize("case", ("F01", "F02", "F25", "F18", "F26"))
def test_genuine_all_model_replies_physical_markdown_and_entity_roles(case: str, tmp_path: Path):
    source = next(row["source"] for row in CASES if row["id"] == case)
    receipt = json.loads(
        (ROOT / f"benchmarks/application_router/{RECEIPTS[case]}/{case}.json").read_text()
    )
    sdk = FrozenProvider(receipt["real_model_outputs"])
    repo, ctx, sem, emb = fresh_corpus_vault(tmp_path)
    result = execute_candidate_routed_message(
        source,
        router=OpenAIFactCandidateRouter(sdk, prompt_revision="v5"),
        temporal=OpenAITemporalInterpreter(
            sdk, CLOCK, max_output_tokens=1536, scoped_date_time_context=True
        ),
        core_planner_factory=lambda c, domain: OpenAILunaExperimentalPlanner(
            sdk, SCHEMA, CLOCK, candidate_context=c, domain_interpretation=domain
        ),
        core_candidate_attributor=OpenAICoreCandidateAttributor(sdk),
        repository=repo,
        schema=SCHEMA,
        context_index=ctx,
        semantic_index=sem,
        embedder=emb,
        contextual_reasoner=object(),
        actor="synthetic-vault-authentic-v5-replay",
        now=NOW,
        context_limit=5,
        request_id_factory=lambda: "v5-genuine-real-model-replay-" + case,
        bundle_compiler=compile_hybrid_candidate_bundle,
    )
    assert result.status is ApplicationStatus.COMPLETED, result.execution_flow
    assert len(sdk.calls) == len(receipt["real_model_outputs"])
    for path, expected_lines in STRICT[case].items():
        markdown = repo.read_text(path)
        for line in expected_lines:
            assert line in markdown, (case, path, markdown)
        assert markdown.count("odyssey:fact request=") >= len(expected_lines)
    if case == "F02":
        for path, expected_lines in STRICT[case].items():
            content = repo.read_text(path)
            assert "16:00 —" not in content
            assert "sobre las 16h" in content if path.endswith("2026-10-04.md") else True
            assert len(expected_lines) == 1
    if case == "F25":
        assert not any("task" in p.casefold() for p in repo.list_markdown_paths())
        assert repo.read_text("La casa de Toulouse.md").count("Necesita reparar el tejado.") == 1
    elif case == "F18":
        day = repo.read_text("calendar/days/2026-10-03.md")
        assert "No vi" not in "\n".join(line for line in day.splitlines() if line.startswith("- "))
        assert "no vi" in day
        assert "pero sí hablé con Luis" in day
    elif case == "F26":
        day = repo.read_text("El informe.md")
        assert "y [[calendar" not in day
        assert "- y " not in day
        assert "- Lo envié" in day
        assert repo.read_text("Ana.md").count("Lo envié a") == 0
        final_reviewer = sdk.calls[-1]
        payload = json.loads(final_reviewer["input"][1]["content"])
        assert (
            payload["trusted_core_predecessor_reference"]["source_proof_kind"]
            == "verified_written_direct_target"
        )
        assert payload["trusted_core_predecessor_reference"]["canonical_name"] == "El informe"


def test_preserved_original_v4_contract_still_replays(tmp_path: Path):
    source = next(row["source"] for row in CASES if row["id"] == "F15")
    receipt = json.loads(
        (ROOT / "benchmarks/application_router/hybrid_semantic_live_v5/F15.json").read_text()
    )
    sdk = FrozenProvider(receipt["real_model_outputs"])
    repo, ctx, sem, emb = fresh_corpus_vault(tmp_path)
    result = execute_candidate_routed_message(
        source,
        router=OpenAIFactCandidateRouter(sdk, prompt_revision="v4"),
        temporal=OpenAITemporalInterpreter(
            sdk, CLOCK, max_output_tokens=1536, scoped_date_time_context=True
        ),
        core_planner_factory=lambda c, domain: OpenAILunaExperimentalPlanner(
            sdk, SCHEMA, CLOCK, candidate_context=c, domain_interpretation=domain
        ),
        core_candidate_attributor=OpenAICoreCandidateAttributor(sdk),
        repository=repo,
        schema=SCHEMA,
        context_index=ctx,
        semantic_index=sem,
        embedder=emb,
        contextual_reasoner=object(),
        actor="isolated-f15-regression-v4",
        now=NOW,
        context_limit=5,
        request_id_factory=lambda: "f15-unaltered-v4-check",
        bundle_compiler=compile_hybrid_candidate_bundle,
    )
    assert result.status is ApplicationStatus.COMPLETED, result.execution_flow
    day = repo.read_text("calendar/days/2026-10-03.md")
    bea = repo.read_text("Bea.md")
    assert "- Mis hijos fueron al parque." in day
    assert "- Después yo preparé la cena." in day
    assert "- Se quedó en casa [[calendar/days/2026-10-03|03-10-2026]]." in bea
