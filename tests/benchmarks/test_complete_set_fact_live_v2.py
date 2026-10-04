"""Provider-free freeze for the shared-semantic-frontend Sol successor gate."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from benchmarks.complete_set_fact_live_v2 import run_live

ROOT = Path(__file__).resolve().parents[2]
MATRIX = ROOT / "benchmarks/complete_set_fact_live_v2/matrix.json"
RUNNER = ROOT / "benchmarks/complete_set_fact_live_v2/run_live.py"


def test_v2_is_one_sol_call_on_shared_semantic_frontend() -> None:
    """Pin the successor to one model-only fallback difference and no mutation authority."""
    matrix = json.loads(MATRIX.read_text(encoding="utf-8"))
    assert hashlib.sha256(MATRIX.read_bytes()).hexdigest() == run_live.MATRIX_SHA256
    assert run_live.MAX_CALLS == 1
    assert run_live.PROPOSED_CEILING_USD == 0.23
    assert run_live._budget_upper() < run_live.PROPOSED_CEILING_USD
    assert matrix["case"]["expect_extent"] == "complete_set"
    source = RUNNER.read_text(encoding="utf-8")
    assert "OpenAILunaExperimentalPlanner(" in source
    assert "model=PLANNER_MODEL" in source
    assert "max_output_tokens=LUNA_EXPERIMENT_MAX_OUTPUT_TOKENS" in source
    for forbidden in ("OpenAIRequestPlanner(", "execute_request(", "create_entity(", "git push"):
        assert forbidden not in source


def test_v2_preflight_is_provider_free(monkeypatch) -> None:
    """Allow hash/budget validation without credentials or authorization."""
    monkeypatch.delenv(run_live.AUTH_ENV, raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert run_live.run(preflight_only=True) == 0
