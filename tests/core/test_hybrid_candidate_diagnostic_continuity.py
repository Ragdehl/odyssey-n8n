"""Real DEV class of 2026-10-14 transcript error: a legitimate candidate_context_bytes
measurement is not an unsafe or unrecognized diagnostic field.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from odyssey_core.conversations import ConversationError
from odyssey_core.local_conversations import LocalConversationStore


def _candidate_detail(request_id: str, *, context_bytes: int = 440) -> dict:
    return {
        "request_id": request_id,
        "operational": {
            "total_duration_ms": 30_000,
            "stages": [
                {
                    "name": "planner",
                    "outcome": "completed",
                    "duration_ms": 3600,
                    "model": "gpt-5.6-luna",
                    "provider_calls": [
                        {
                            "name": "planner",
                            "outcome": "completed",
                            "duration_ms": 3500,
                            "model": "gpt-5.6-luna",
                            "reasoning_effort": "low",
                            "provider_calls": [],
                            "input_sizes": {
                                "fixed_instructions_bytes": 22370,
                                "candidate_context_bytes": context_bytes,
                                "user_request_bytes": 60,
                            },
                        }
                    ],
                }
            ],
        },
    }


def test_hybrid_detail_with_candidate_context_is_persisted_replayed_and_isolated(tmp_path: Path):
    store = LocalConversationStore(tmp_path / "only-actor-a")
    now = "2026-10-14T12:35:44+02:00"
    rid = "web-synthetic-backpack"
    store.append_turn(request_id=rid, role="user", text="Encontré una mochila", created_at=now)
    data = _candidate_detail(rid)
    store.append_turn(
        request_id=rid,
        role="assistant",
        text="Necesito comprobar el hecho",
        created_at=now,
        status="needs_attention",
        request_detail=data,
    )
    latest = store.load_main_page()["turns"]
    assert [t["role"] for t in latest] == ["user", "assistant"]
    assert (
        latest[1]["request_detail"]["operational"]["stages"][0]["provider_calls"][0]["input_sizes"][
            "candidate_context_bytes"
        ]
        == 440
    )
    store.append_turn(
        request_id=rid,
        role="assistant",
        text="Necesito comprobar el hecho",
        created_at=now,
        status="needs_attention",
        request_detail=data,
    )
    assert len(store.load_main_page()["turns"]) == 2
    assert (
        LocalConversationStore(tmp_path / "only-actor-b").load_or_create_main(now=now)["turns"]
        == []
    )


@pytest.mark.parametrize("invalid", [True, -1, "440", {"raw_source": "private"}])
def test_reject_invalid_candidate_context_measurement_without_losing_other_invariants(
    tmp_path: Path,
    invalid,
):
    store = LocalConversationStore(tmp_path / "actor")
    with pytest.raises(ConversationError, match="request detail"):
        store.append_turn(
            request_id="synthetic",
            role="assistant",
            text="No escrito",
            created_at="2026-10-14T12:35:44+02:00",
            request_detail=_candidate_detail("synthetic", context_bytes=invalid),
        )


def test_new_source_proposal_and_reviewer_do_not_break_verified_route_trace(tmp_path: Path):
    store = LocalConversationStore(tmp_path / "single-actor")
    source = "Ayer visité el museo"
    rid = "web-synthetic-v6-trace"
    stages = [
        {
            "name": "candidate.source_proposal",
            "outcome": "completed",
            "duration_ms": 1840,
            "model": "gpt-6-luna",
            "provider_calls": [],
        },
        {
            "name": "candidate.source_boundary_review",
            "outcome": "completed",
            "duration_ms": 1750,
            "model": "gpt-5.6-luna",
            "provider_calls": [],
        },
        {
            "name": "candidate.temporal_interpretation",
            "outcome": "completed",
            "duration_ms": 1960,
            "model": "gpt-6-luna",
            "provider_calls": [],
        },
        {
            "name": "planner",
            "outcome": "completed",
            "duration_ms": 3500,
            "model": "gpt-5.6-luna",
            "provider_calls": [],
        },
    ]
    detail = {
        "request_id": rid,
        "operational": {"total_duration_ms": 11000, "stages": stages},
        "flow": {
            "version": 1,
            "input": source,
            "parallel_preparation": False,
            "routes": [
                {
                    "capability": "temporal",
                    "text": source,
                    "stage_count": 2,
                    "status": "completed",
                    "temporal": [],
                    "steps": [
                        {
                            "name": "candidate.temporal_interpretation",
                            "input": source,
                            "output": "Fecha",
                        },
                        {"name": "planner", "input": source, "output": "Plan"},
                    ],
                }
            ],
        },
    }
    store.append_turn(
        request_id=rid,
        role="assistant",
        text="Guardado",
        created_at="2026-10-14T14:00:00+02:00",
        status="completed",
        request_detail=detail,
    )
    assert (
        store.load_main_page()["turns"][0]["request_detail"]["flow"]["routes"][0]["steps"][0][
            "name"
        ]
        == "candidate.temporal_interpretation"
    )
    detail["operational"]["stages"][2]["name"] = "planner"
    with pytest.raises(ConversationError, match="execution flow"):
        store.append_turn(
            request_id="web-synthetic-invalid-v6",
            role="assistant",
            text="Erróneo",
            created_at="2026-10-14T14:01:00+02:00",
            request_detail={**detail, "request_id": "web-synthetic-invalid-v6"},
        )
