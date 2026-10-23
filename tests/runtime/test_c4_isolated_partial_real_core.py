"""C4 partial integration: physical isolated Core write -> E3 -> C4 -> n8n UI.

A controlled readback failure happens only AFTER actual Core Markdown mutation.
Provider outputs are recorded genuine responses, not new model calls.
No user DEV/PROD records, external services or hosted browser used.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from uuid import uuid4

import pytest

from odyssey_apps.fact_candidates import OpenAIFactCandidateRouter
from odyssey_core.candidate_attribution import OpenAICoreCandidateAttributor
from odyssey_core.experimental_luna_planning import OpenAILunaExperimentalPlanner
from odyssey_core.identity_boundary import AuthenticatedActorContext
from odyssey_core.local_conversations import ConversationRootResolver
from odyssey_core.temporal_interpretation import OpenAITemporalInterpreter
from odyssey_runtime.candidate_route_dispatch import execute_candidate_routed_message
from odyssey_runtime.composition import RuntimeComposition
from odyssey_runtime.hybrid_group_compiler import compile_hybrid_candidate_bundle
from tests.apps.test_fact_candidates import CASES
from tests.runtime.test_candidate_pending_state import NOW
from tests.runtime.test_fact_candidate_semantic_luna_vertical import CLOCK, SCHEMA
from tests.runtime.test_full_message_corpus_regression import (
    ROOT,
    fresh_corpus_vault,
)
from tests.runtime.test_scoped_route_recorded_real_replay import FrozenProvider


def test_isolated_physical_postwrite_partial_c4_n8n_and_replay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test the actual safety boundary, not a hand-written partial receipt."""
    case = next(item for item in CASES if item["id"] == "F14")
    source = case["source"]
    record = json.loads(
        (ROOT / "benchmarks/application_router/hybrid_remaining_diag_20261013/F14.json").read_text(
            encoding="utf-8"
        )
    )
    sdk = FrozenProvider(record["real_model_outputs"])
    vault, context_index, semantic_index, embedder = fresh_corpus_vault(tmp_path / "fixture")
    actor = AuthenticatedActorContext(str(uuid4()))
    request_id = "c4-isolated-" + uuid4().hex
    executed_core = []

    def broken_readback(*_args: object, **_kwargs: object):
        raise RuntimeError("controlled isolated postwrite readback failure")

    # The deterministic failure remains scoped to THIS pytest process and
    # vault. It does not change Odyssey source or deployed DEV behavior.
    monkeypatch.setattr("odyssey_core.candidate_fact_readback.readback_core_facts", broken_readback)

    def hybrid(user_request: str, rid: str, *_args: object):
        assert user_request == source
        executed_core.append(rid)
        return execute_candidate_routed_message(
            user_request,
            router=OpenAIFactCandidateRouter(sdk, prompt_revision="v5"),
            temporal=OpenAITemporalInterpreter(
                sdk, CLOCK, max_output_tokens=1536, scoped_date_time_context=True
            ),
            core_planner_factory=lambda context, domain: OpenAILunaExperimentalPlanner(
                sdk, SCHEMA, CLOCK, candidate_context=context, domain_interpretation=domain
            ),
            core_candidate_attributor=OpenAICoreCandidateAttributor(sdk),
            repository=vault,
            schema=SCHEMA,
            context_index=context_index,
            semantic_index=semantic_index,
            embedder=embedder,
            contextual_reasoner=object(),
            actor=actor.stable_user_id,
            now=NOW,
            context_limit=5,
            request_id_factory=lambda: rid,
            bundle_compiler=compile_hybrid_candidate_bundle,
        )

    runtime = RuntimeComposition(
        core_execute=lambda *_a, **_kw: (_ for _ in ()).throw(AssertionError("wrong route")),
        hybrid_candidate_execute=hybrid,
        full_source_mutation_guard=True,
        conversation_error_guidance_enabled=True,
        refresh_indexes=lambda: None,
        conversation_root_resolver=ConversationRootResolver(tmp_path / "isolated-conversation"),
        vault_repository=vault,
    )
    before = {p: vault.read_text(p) for p in vault.list_markdown_paths()}
    response = runtime.execute_product(source, request_id, "main", actor)
    assert response["status"] == "partial"
    assert response["product_outcome"] == "CANNOT_ANSWER"
    assert response["error_guidance"]["status"] == "partial"
    assert response["error_guidance"]["write_evidence"] == "SOME"
    assert response["affected_stable_note_ids"]
    assert "date:2026-10-03" in response["affected_stable_note_ids"]
    assert response["note_result_snapshot"]["kind"] == "affected_notes"
    saved = vault.read_text("calendar/days/2026-10-03.md")
    assert saved != before.get("calendar/days/2026-10-03.md")
    assert "Ayer hablé con [[Eric|Eric]] y [[Luis|Luis]]." in saved
    assert "cine" not in saved
    assert any(
        item.get("name") == "candidate.postwrite_verification"
        and item.get("error_category") == "RuntimeError"
        for item in response["operational"]["stages"]
    )

    rendered = subprocess.run(
        ["node", str(ROOT / "scripts/odyssey_c4_isolated_route_renderer.mjs")],
        input=json.dumps(response),
        text=True,
        capture_output=True,
        check=False,
        timeout=20,
        cwd=ROOT,
    )
    assert rendered.returncode == 0, rendered.stderr[:2000]
    public = json.loads(rendered.stdout)
    assert public["pass"] is True
    assert public["status"] == "partial"
    assert public["kind"] == "acknowledgement"
    assert "guardado parte" in public["message"].lower()
    assert "No he podido verificar la causa exacta" in public["message"]
    assert "No he guardado nada" not in public["message"]
    assert public["note_snapshot"]["note_ids"] == response["note_result_snapshot"]["note_ids"]

    repeat = runtime.execute_product(source, request_id, "main", actor)
    assert repeat.pop("delivery_replayed") is True
    assert repeat == response
    assert executed_core == [request_id]
    assert vault.read_text("calendar/days/2026-10-03.md") == saved
    assert len(sdk.calls) == len(record["real_model_outputs"])
