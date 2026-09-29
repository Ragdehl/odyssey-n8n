"""Guards for the retired, unexecuted semantic-write-frontend-v7 lineage."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from benchmarks.semantic_write_frontend_v7 import run_live as runner


def test_v7_is_retired_without_evidence() -> None:
    manifest = json.loads(runner.MANIFEST_PATH.read_text())
    assert runner.GATE_RETIRED is True
    assert runner.MAX_COST_USD == Decimal("0.00")
    assert manifest["provider_calls_made"] == 0
    assert manifest["result"] == "retired_unexecuted"
    assert manifest["artifact_created"] is False
    assert not runner.OUTPUT_PATH.exists()


def test_retired_gate_refuses_before_provider(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(runner, "OUTPUT_PATH", tmp_path / "x.jsonl")
    monkeypatch.setattr(
        runner.OpenAILunaExperimentalPlanner,
        "from_environment",
        lambda *_a, **_k: pytest.fail("provider constructed for retired v7"),
    )
    with pytest.raises(SystemExit, match="retired unexecuted"):
        runner.main(["--confirm-live-provider-calls"])
    assert not runner.OUTPUT_PATH.exists()
