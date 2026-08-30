"""Deterministic preparation and safety tests for the bounded Phase 11B.2 parity runner."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from odyssey_core.contextual import ContextualResolutionError, build_openai_payload

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.skip(reason="Historical parity fixture predates Phase 17E schema")
RUNNER_PATH = ROOT / "benchmarks/run_phase11b2_sol_parity.py"


@pytest.fixture
def runner():
    """Load the parity runner without executing its network entry point."""
    spec = importlib.util.spec_from_file_location("phase11b2_parity", RUNNER_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_selected_case_ids_are_frozen_evaluation_cases(runner) -> None:
    """Require the exact twelve ordered IDs and reject calibration or extra cases."""
    data = json.loads((ROOT / "benchmarks/phase11a_contextual_resolution_cases.json").read_text())
    cases = [case for case in data["cases"] if case["split"] == "evaluation"]
    selected = runner.select_cases(
        [
            {
                "id": case["id"],
                "split": case["split"],
            }
            for case in cases
        ]
    )
    assert [case["id"] for case in selected] == list(runner.SELECTED_CASE_IDS)
    assert len(selected) == 12
    artifact = json.loads(runner.CANDIDATE_ARTIFACT.read_text())
    note_ids = {note["id"] for note in data["notes"]}
    assert set(artifact["evaluation"]) == set(runner.SELECTED_CASE_IDS)
    assert len(artifact["calibration"]) == 10
    assert all(
        candidate_id in note_ids
        for candidate_ids in (*artifact["evaluation"].values(), *artifact["calibration"].values())
        for candidate_id in candidate_ids
    )
    assert all(
        case["expected_id"] in artifact["evaluation"][case["id"]]
        for case in data["cases"]
        if case["id"] in artifact["evaluation"] and case["expected"] == "RESOLVED"
    )
    with pytest.raises(ValueError, match="exactly twelve"):
        runner.SELECTED_CASE_IDS = runner.SELECTED_CASE_IDS + ("extra",)
        runner.select_cases(cases)


def test_production_reconstruction_has_no_paths_or_benchmark_labels(runner) -> None:
    """Exercise canonical reconstruction and ensure request evidence is provider-minimized."""
    source = json.loads((ROOT / "benchmarks/phase11a_contextual_resolution_cases.json").read_text())
    schema = json.loads((ROOT / "config/note-schema.json").read_text())
    notes = {note["id"]: note for note in source["notes"]}
    case = {
        **next(case for case in source["cases"] if case["id"] == "en-wife-school"),
        "candidates": [
            {"id": "beatriz-alonso", "text": notes["beatriz-alonso"]["text"], "score": 1.0}
        ],
    }
    request = runner._production_request(case, notes, schema)
    serialized = json.dumps(
        {
            "reference": request.reference,
            "context": request.context,
            "entity_type": request.entity_type,
            "candidates": [
                {"id": candidate.id, "evidence": candidate.evidence}
                for candidate in request.candidates
            ],
        },
        ensure_ascii=False,
    )
    assert "people/" not in serialized
    assert "expected" not in serialized.casefold()
    assert "en-wife-school" not in serialized
    assert "score" not in serialized.casefold()
    assert request.candidates[0].id == "beatriz-alonso"
    assert "Name: Beatriz Alonso" in request.candidates[0].evidence
    assert "The user's wife" in request.candidates[0].evidence


def test_production_payload_keeps_privacy_controls_and_disables_cache(runner) -> None:
    """Verify current payload controls without making a provider call."""
    from odyssey_core.contextual import ContextualCandidate, ContextualResolutionRequest

    request = ContextualResolutionRequest(
        "my spouse",
        "She is the mother of my children.",
        "person",
        (ContextualCandidate("beatriz-alonso", "Name: Beatriz Alonso\nType: person"),),
    )
    payload = build_openai_payload(request, "gpt-5.6-sol")
    assert payload["store"] is False
    assert payload["text"]["format"]["strict"] is True
    assert "prompt_cache_key" not in payload
    assert "prompt_cache_options" not in payload


def test_result_shape_excludes_request_content(runner, tmp_path: Path) -> None:
    """Prove safe result serialization contains no body, prompt, context, or credentials."""
    output = tmp_path / "result.json"
    payload = {
        "case_ids": list(runner.SELECTED_CASE_IDS),
        "cases": [
            {"case_id": "en-wife-school", "outcome": "RESOLVED", "selected_id": "beatriz-alonso"}
        ],
        "token_usage": {"input_tokens": 1},
    }
    runner.write_json_atomic(output, payload)
    serialized = output.read_text()
    assert '"prompt"' not in serialized
    assert '"evidence"' not in serialized
    assert '"context"' not in serialized
    assert "OPENAI_API_KEY" not in serialized


def test_malformed_provider_output_persists_safe_failure_and_stops(
    runner, monkeypatch, tmp_path: Path
) -> None:
    """Stop after one invalid response and persist only safe partial benchmark state."""

    class InvalidReasoner:
        """Return malformed output once without making a network request."""

        calls = 0

        def __init__(self, *args: object, **kwargs: object) -> None:
            """Accept the production reasoner constructor contract."""

        def resolve(self, request: object) -> tuple[dict[str, object], dict[str, int]]:
            """Return an invalid outcome that Core must reject."""
            self.calls += 1
            return {"outcome": "MAYBE", "id": None}, {}

    fake = InvalidReasoner()
    monkeypatch.setattr(runner, "OpenAIContextualReasoner", lambda *args, **kwargs: fake)
    output = tmp_path / "failure.json"
    with pytest.raises(ContextualResolutionError):
        runner.run_benchmark(output)
    persisted = json.loads(output.read_text())
    assert fake.calls == 1
    assert persisted["requests_attempted"] == 1
    assert persisted["requests_completed"] == 0
    assert persisted["failure"] == {"type": "ContextualResolutionError"}
    serialized = output.read_text()
    assert '"evidence"' not in serialized
    assert '"context"' not in serialized
