"""Guards for the consumed semantic-write-frontend-v6 gate."""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from pathlib import Path

import pytest

from benchmarks.semantic_write_frontend_v6 import run_live as runner

ROOT = Path(__file__).resolve().parents[2]


def test_gate_is_consumed_with_evidence() -> None:
    assert runner.MAX_COST_USD == Decimal("0.00") and runner.GATE_CONSUMED is True
    manifest = json.loads(runner.MANIFEST_PATH.read_text())
    assert manifest["provider_calls_made"] == 4
    assert manifest["result"] == "failed_swr04"
    assert (
        manifest["artifact_sha256"]
        == "0a4b2524bda2605bcbcc6e4f7662090c0089e4c2cc264089ab83c3ecb9b0ab2e"
    )
    assert (
        manifest["evaluator_sha256"]
        == "7360d91b179ba68c1243c6829738ec0507a04034c8b6c1cc5cee6ec009a3b9e3"
    )
    if runner.OUTPUT_PATH.exists():
        assert (
            hashlib.sha256(runner.OUTPUT_PATH.read_bytes()).hexdigest()
            == manifest["artifact_sha256"]
        )


def test_consumed_gate_refuses_before_provider(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(runner, "MAX_COST_USD", Decimal("1"))
    monkeypatch.setattr(runner, "OUTPUT_PATH", tmp_path / "x.jsonl")
    monkeypatch.setattr(
        runner.OpenAILunaExperimentalPlanner,
        "from_environment",
        lambda *_a, **_k: pytest.fail("provider constructed"),
    )
    with pytest.raises(SystemExit, match="permanently consumed"):
        runner.main(["--confirm-live-provider-calls"])
