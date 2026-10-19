"""Pure regression for the synthetic browser bridge's real Core output projection.

No Chromium, model provider, or n8n is invoked by the official offline suite.
"""

from __future__ import annotations

import copy

import pytest

from odyssey_core.conversations import ConversationError
from scripts.odyssey_browser_synthetic_p4 import real_result_browser_detail
from tests.runtime.test_whole_source_light_product_p4 import (
    RecordedClient,
    _actual_snapshot,
    _fixture,
    _speaker,
)


def _real_fixture(tmp_path):
    original, router, proposal, review = _actual_snapshot("maya_simple")
    repo, actor, executor, runtime = _fixture(tmp_path)
    executor.client = RecordedClient(
        [
            router,
            proposal,
            review,
            _speaker(original, proposal, base=1),
            _speaker(original, proposal),
        ]
    )
    response = runtime.execute_product(original, "synthetic-browser-contract", "main", actor)
    assert response["status"] == "completed"
    return repo, actor, runtime, response


def test_real_core_result_is_preserved_without_fabricating_n8n_write_receipts(tmp_path):
    repo, actor, runtime, raw = _real_fixture(tmp_path)
    detail = real_result_browser_detail(raw, raw["request_id"])
    assert len(detail["flow"]["routes"]) == 1
    assert detail["flow"]["routes"][0]["capability"] == "core"
    assert len(detail["flow"]["routes"][0]["writes"]) == 2
    assert len(detail["changes"]["affected_stable_note_ids"]) == 2
    assert len(detail["operational"]["stages"]) == len(raw["operational"]["stages"])
    assert all("estimated_cost_usd" not in stage for stage in detail["operational"]["stages"])
    assert len(repo.list_markdown_paths()) == 4
    assert (
        runtime.execute_product("Ayer hablé con Maya.", raw["request_id"], "main", actor)[
            "delivery_replayed"
        ]
        is True
    )


def test_synthetic_n8n_like_finalizer_retains_graph_and_note_buttons_after_persistence(tmp_path):
    _, actor, runtime, raw = _real_fixture(tmp_path)
    detail = real_result_browser_detail(raw, raw["request_id"])
    normalized = {
        "request_id": raw["request_id"],
        "status": "completed",
        "kind": "acknowledgement",
        "message": "Guardado",
        "request_detail": detail,
        "note_result_snapshot": raw["note_result_snapshot"],
    }
    receipt = runtime.persist_product_assistant_response(normalized, actor)
    assert receipt["conversation_persisted"] is True
    assert receipt["conversation_diagnostics_preserved"] is True
    turns = runtime.main_conversation(actor)["turns"]
    assert len(turns) == 2
    assert turns[0]["role"] == "user"
    assert turns[1]["role"] == "assistant"
    assert turns[1]["text"] == "Guardado"
    assert turns[1]["note_result_snapshot"]["total"] == 2
    assert (
        turns[1]["request_detail"]["flow"]["routes"][0]["writes"]
        == detail["flow"]["routes"][0]["writes"]
    )


def test_invalid_execution_flow_fails_closed_in_synthetic_projection(tmp_path):
    _, _, _, raw = _real_fixture(tmp_path)
    tampered = copy.deepcopy(raw)
    tampered["execution_flow"]["routes"][0]["depends_on"] = 0
    with pytest.raises(ConversationError, match="execution flow"):
        real_result_browser_detail(tampered, tampered["request_id"])
