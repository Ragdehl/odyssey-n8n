"""Provider-free guards for fixed-fact semantic enrichment v2."""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal

import pytest

from benchmarks.fixed_fact_enrichment_live_v2 import run_live
from odyssey_core.fixed_fact_capture import (
    FIXED_FACT_ENRICHMENT_CONTRACT_VERSION,
    FIXED_FACT_ENRICHMENT_FORMAT_NAME,
)


def test_fixed_fact_v2_reuses_the_three_v1_semantic_cases() -> None:
    cases = run_live.load_cases()
    assert len(cases) == run_live.MAX_CALLS == 3
    assert [case["id"] for case in cases] == [
        "FFE01-nickname-occurrence",
        "FFE02-complete-self-set",
        "FFE03-mixed-canonical-day-content",
    ]
    assert hashlib.sha256(run_live.CASES_PATH.read_bytes()).hexdigest() == run_live.CASES_SHA256


def test_fixed_fact_v2_pins_the_scoped_successor_contract() -> None:
    schema = json.loads(run_live.SCHEMA_PATH.read_text(encoding="utf-8"))
    assert FIXED_FACT_ENRICHMENT_CONTRACT_VERSION == "fixed-fact-semantic-enrichment-v2"
    assert FIXED_FACT_ENRICHMENT_FORMAT_NAME == "odyssey_fixed_fact_semantic_enrichment_v2"
    assert run_live.contract_hashes(schema) == (
        run_live.PROMPT_SHA256,
        run_live.PROVIDER_SCHEMA_SHA256,
    )


def test_fixed_fact_v2_budget_is_small_and_bounded() -> None:
    budget = run_live.budget_snapshot()
    assert budget["calls"] == 3
    assert budget["conservative_usd_upper"] <= run_live.AUTHORIZED_CEILING_USD == Decimal("0.012")


def test_fixed_fact_v2_has_zero_provider_authority_without_explicit_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(run_live.AUTH_ENV, raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "presence-only")
    with pytest.raises(SystemExit, match=run_live.AUTH_ENV):
        run_live._preflight()
