"""Protect the accepted planner model-facing contract from un-gated drift."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import odyssey_core.experimental_luna_planning as luna

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "benchmarks/planner_model_contract/accepted_contract.json"
TEACHING = ROOT / "benchmarks/luna_first_planner/teaching_examples_v3.json"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def test_current_planner_contract_matches_last_live_accepted_evidence() -> None:
    """Require fresh reviewed live evidence before any model-facing planner drift can merge."""
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    schema = json.loads((ROOT / "config/note-schema.json").read_text(encoding="utf-8"))
    context = contract["baseline_context"]
    prompt = luna.render_luna_experimental_prompt(schema, context).encode("utf-8")
    provider_schema = json.dumps(
        luna.luna_experimental_result_json_schema(schema),
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")

    assert _sha(prompt) == contract["prompt_sha256"], (
        "planner prompt changed: fresh live gate required"
    )
    assert _sha(provider_schema) == contract["provider_schema_sha256"], (
        "planner provider schema changed: fresh live gate required"
    )
    assert _sha(TEACHING.read_bytes()) == contract["teaching_examples_sha256"], (
        "planner teaching examples changed: fresh live gate required"
    )
    assert luna.LUNA_EXPERIMENT_MODEL == contract["production_model"], (
        "planner model changed: fresh live gate required"
    )
    assert luna.LUNA_EXPERIMENT_REASONING_EFFORT == contract["production_reasoning_effort"], (
        "planner reasoning effort changed: fresh live gate required"
    )


def test_accepted_contract_points_to_immutable_recorded_evidence() -> None:
    """Bind the accepted hashes to the already recorded production and GPT-6 comparison manifests."""
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    production = json.loads(
        (ROOT / "benchmarks/semantic_write_frontend_v8/manifest.json").read_text(encoding="utf-8")
    )
    candidate = json.loads(
        (ROOT / "benchmarks/semantic_write_frontend_gpt6_luna_v1/manifest.json").read_text(
            encoding="utf-8"
        )
    )
    prod_evidence = contract["accepted_production_evidence"]
    candidate_evidence = contract["candidate_model_evidence"]
    assert production["result"] == prod_evidence["result"]
    assert production["artifact_sha256"] == prod_evidence["artifact_sha256"]
    assert candidate["result"] == candidate_evidence["result"]
    assert candidate["artifact_sha256"] == candidate_evidence["artifact_sha256"]
    assert contract["change_policy"] == {
        "fresh_versioned_live_gate_required": True,
        "explicit_bounded_cost_authorization_required": True,
        "collect_complete_matrix": True,
        "deterministic_vertical_e2e_required": True,
    }
