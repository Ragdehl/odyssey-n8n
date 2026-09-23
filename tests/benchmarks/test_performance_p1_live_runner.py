"""Provider-free behavior tests for P1's isolated-DEV baseline executor."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from benchmarks.performance_p1 import run_live
from benchmarks.performance_p1.dev_fixture import (
    DEV_STATE,
    DEV_VAULT,
    DISPOSABLE_MARKER,
    FixtureError,
    _require_exact_dev_roots,
    fixture_notes,
)
from odyssey_core.notes import validate_note


def _cases() -> list[dict[str, Any]]:
    """Load the frozen registry used by the real executor."""
    path = Path(__file__).parents[2] / "benchmarks/performance_p1/cases.json"
    return json.loads(path.read_text(encoding="utf-8"))["cases"]


def _operational() -> dict[str, Any]:
    """Return one compact, fully supplied fake provider observation."""
    return {
        "total_duration_ms": 20.0,
        "product_execution_duration_ms": 22.0,
        "coverage": {
            "attributed_ms": 20.0,
            "unattributed_ms": 0.0,
            "coverage_pct": 100.0,
            "overlapping_ms": 0.0,
        },
        "stages": [
            {
                "name": "planner",
                "outcome": "completed",
                "duration_ms": 20.0,
                "start_offset_ms": 0.0,
                "provider_calls": [
                    {
                        "name": "planner.luna",
                        "ordinal": 1,
                        "model": "gpt-5.6-luna",
                        "outcome": "completed",
                        "duration_ms": 18.0,
                        "usage": {
                            "input_tokens": 100,
                            "cached_input_tokens": 0,
                            "output_tokens": 10,
                        },
                    }
                ],
            }
        ],
    }


def test_disposable_fixture_is_schema_valid_and_root_guard_rejects_non_dev_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The frozen fixture is schema-valid and requires the exact marked disposable DEV root."""
    schema = json.loads((Path(__file__).parents[2] / "config/note-schema.json").read_text())
    notes = fixture_notes({"Marta": ["Marta prefiere el té."]})
    assert set(notes) == {"Marta", "Elena", "Pablo", "self"}
    for note in notes.values():
        validate_note(note, schema)

    # CI does not own the fixed DEV filesystem. Simulate only the initialization and
    # marker checks so this unit test exercises the safety guard without host state.
    expected_dirs = {DEV_VAULT.parent, DEV_VAULT / ".git", DEV_STATE}
    monkeypatch.setattr(Path, "is_dir", lambda self: self in expected_dirs)
    monkeypatch.setattr(Path, "is_file", lambda self: self == DISPOSABLE_MARKER)
    _require_exact_dev_roots(DEV_VAULT, DEV_STATE)
    with pytest.raises(FixtureError):
        _require_exact_dev_roots(Path("/data/odyssey/vault"), DEV_STATE)


def test_live_request_payloads_use_the_configured_dev_webhook_prefix() -> None:
    """The runner uses DEV's ordinary n8n `api` webhook prefix, never a direct runtime path."""
    chat_url, _ = run_live._request_payload(_cases()[0], "p1-test")
    notes_url, _ = run_live._request_payload(_cases()[-1], "p1-test")
    assert chat_url.endswith("/api/request")
    assert notes_url.endswith("/api/notes")


def test_live_runner_flushes_every_case_and_keeps_semantic_failures_independent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A safe oracle failure is recorded once and does not cause a retry or lost later evidence."""
    state = {
        "Marta": "marta trabaja en thales. marta vive en lyon.",
        "Elena": "elena vive en girona.",
        "Pablo": "pablo vive en barcelona.",
    }
    requests: list[dict[str, object]] = []
    restarts: list[None] = []

    def reset(case: dict[str, Any]) -> dict[str, object]:
        state.update(
            {
                "Marta": "marta trabaja en thales. marta vive en lyon.",
                "Elena": "elena vive en girona.",
                "Pablo": "pablo vive en barcelona.",
            }
        )
        for person, facts in case.get("extra_fixture_facts", {}).items():
            state[person] += " " + " ".join(facts).casefold()
        return {"fixture_version": 1, "fixture_git_commit": f"fixture-{case['id']}"}

    def post(_url: str, payload: dict[str, object], _timeout: float) -> dict[str, Any]:
        requests.append(payload)
        if payload.get("operation") == "turn":
            return {"conversation_id": "main"}
        if payload.get("operation") == "intelligent":
            return {
                "kind": "page",
                "mode": "intelligent",
                "items": [{"id": "p1-marta"}],
                "operational": _operational(),
            }
        request = payload["request"]
        assert isinstance(request, str)
        if request == "???":
            return {
                "request_id": payload["request_id"],
                "status": "needs_attention",
                "kind": "clarification",
                "request_detail": {"operational": _operational(), "changes": {"units": []}},
            }
        if request.startswith("¿"):
            fact = "Marta trabaja en Thales." if "trabaja" in request else "Marta vive en Lyon."
            return {
                "request_id": payload["request_id"],
                "status": "completed",
                "kind": "answer",
                "message": fact,
                "request_detail": {"operational": _operational(), "changes": {"units": []}},
            }
        if request.startswith("Guarda"):
            state["Marta"] += " prefiere el té"
        elif request.startswith("Marta prefiere"):
            state["Marta"] += " prefiere el té"
            state["Elena"] += " prefiere el café"
        else:
            state["Marta"] += " prefiere el té"
            state["Elena"] += " le gusta el café"
            state["Pablo"] += " trabaja en thales"
        kind = "empty" if request.startswith("Guarda") else "acknowledgement"
        return {
            "request_id": payload["request_id"],
            "status": "completed",
            "kind": kind,
            "request_detail": {
                "operational": _operational(),
                "changes": {"units": [{"status": "completed"}]},
            },
        }

    monkeypatch.setattr(run_live, "_fixture_note_text", lambda person: state[person])
    rows = run_live.run_live_cases(
        _cases(),
        evidence_path=tmp_path / "baseline.jsonl",
        pricing=json.loads(
            (
                Path(__file__).parents[2] / "benchmarks/performance_p1/pricing_snapshot.json"
            ).read_text()
        ),
        provenance={"source_commit": "test", "deployed_commit": "test"},
        confirmed=True,
        post=post,
        reset=reset,
        restart=lambda: restarts.append(None),
        run_id="deterministic",
    )
    assert len(rows) == 7 and len(restarts) == 7
    assert [row["case_id"] for row in rows] == ["R1", "R2", "W1", "W2", "W3", "C1", "N1"]
    assert rows[2]["semantic_passed"] is False and rows[2]["semantic_oracle"] == "write_shape"
    assert rows[3]["semantic_passed"] is True and rows[4]["semantic_passed"] is True
    assert len([request for request in requests if "request" in request]) == 6
    assert len([request for request in requests if request.get("operation") == "turn"]) == 2
    persisted = [
        json.loads(line) for line in (tmp_path / "baseline.jsonl").read_text().splitlines()
    ]
    assert len(persisted) == 8 and persisted[0]["record_type"] == "run"
    assert all(row["record_type"] == "case" for row in persisted[1:])


def test_live_runner_stops_after_persisting_an_unsafe_transport_failure(tmp_path: Path) -> None:
    """A malformed product reply writes its stop record and performs no later request or retry."""
    calls = 0

    def post(_url: str, _payload: dict[str, object], _timeout: float) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        return {"request_id": "wrong"}

    with pytest.raises(run_live.LiveRunError, match="fresh execution"):
        run_live.run_live_cases(
            _cases(),
            evidence_path=tmp_path / "stopped.jsonl",
            pricing={"as_of": "test", "models": {}},
            provenance={"source_commit": "test", "deployed_commit": "test"},
            confirmed=True,
            post=post,
            reset=lambda _case: {},
            restart=lambda: None,
            run_id="unsafe",
        )
    rows = [json.loads(line) for line in (tmp_path / "stopped.jsonl").read_text().splitlines()]
    assert calls == 1 and rows[-1]["record_type"] == "unsafe_stop" and len(rows) == 2


def test_live_runner_refuses_existing_evidence_without_reset_or_request(tmp_path: Path) -> None:
    """An immutable evidence name is checked before fixture mutation or provider-boundary work."""
    evidence = tmp_path / "existing.jsonl"
    evidence.write_text("existing\n", encoding="utf-8")
    with pytest.raises(FileExistsError):
        run_live.run_live_cases(
            _cases(),
            evidence_path=evidence,
            pricing={},
            provenance={},
            confirmed=True,
            post=lambda *_args: pytest.fail("request must not run"),
            reset=lambda _case: pytest.fail("reset must not run"),
            restart=lambda: pytest.fail("restart must not run"),
        )
