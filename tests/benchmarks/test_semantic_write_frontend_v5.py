"""Guards for the consumed semantic-write-frontend-v5 gate."""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from pathlib import Path

import pytest

from benchmarks.semantic_write_frontend_v5 import run_live as runner

ROOT = Path(__file__).resolve().parents[2]


def test_gate_is_consumed_with_evidence():
    assert runner.MAX_COST_USD == Decimal("0.00") and runner.GATE_CONSUMED is True
    m = json.loads(runner.MANIFEST_PATH.read_text())
    assert m["provider_calls_made"] == 8
    assert m["result"] == "failed_swr08"
    assert (
        m["artifact_sha256"] == "a94c33198b96bfbb152e3402ba04e7acba6fbeafff8e4b315fb9343c07d9987c"
    )
    if runner.OUTPUT_PATH.exists():
        assert hashlib.sha256(runner.OUTPUT_PATH.read_bytes()).hexdigest() == m["artifact_sha256"]


def test_consumed_gate_refuses_before_provider(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setattr(runner, "MAX_COST_USD", Decimal("1"))
    monkeypatch.setattr(runner, "OUTPUT_PATH", tmp_path / "x.jsonl")
    monkeypatch.setattr(
        runner.OpenAILunaExperimentalPlanner,
        "from_environment",
        lambda *_a, **_k: pytest.fail("provider constructed"),
    )
    with pytest.raises(SystemExit, match="permanently consumed"):
        runner.main(["--confirm-live-provider-calls"])
