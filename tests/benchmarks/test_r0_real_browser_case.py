"""Provider-free refusal tests for the paid R0 case adapter."""

from __future__ import annotations

import json
import subprocess
import sys

from scripts.odyssey_r0_browser_campaign import frozen_cases


def test_adapter_refuses_before_importing_or_calling_provider_without_transient_approval(tmp_path):
    case = frozen_cases()[0]
    receipt = tmp_path / "F01.json"
    receipt.write_text(
        json.dumps(
            {
                "case": case.id,
                "source_sha256": case.source_sha256,
                "outcome": "armed",
                "reserved_usd": 0.25,
            }
        ),
        encoding="utf-8",
    )
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/odyssey_r0_real_browser_case.py",
            "--case",
            case.id,
            "--source-sha256",
            case.source_sha256,
            "--receipt",
            str(receipt),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0
    trace = json.loads(completed.stdout.splitlines()[-1])
    assert trace["outcome"] == "failed"
    assert trace["provider_usage"] == []
    assert trace["forensics"]["error"] == "Refused"


def test_live_budget_allows_several_model_stages_without_an_unpriced_call(tmp_path):
    """Real production messages require Router, Temporal, Planner and review."""
    from types import SimpleNamespace
    from unittest.mock import patch

    from openai.resources.responses.responses import Responses

    from scripts.odyssey_r0_browser_campaign import arm_case
    from scripts.odyssey_r0_real_browser_case import MAX_CALLS, _usage_wrapper

    case = frozen_cases()[0]
    receipt = arm_case(tmp_path, case, 0.25)
    calls = []

    def fake_provider(self, **kwargs):
        calls.append(kwargs["text"]["format"]["name"])
        return SimpleNamespace(usage=SimpleNamespace(input_tokens=1200, output_tokens=400))

    assert MAX_CALLS >= 5
    with patch.object(Responses, "create", fake_provider):
        observed = []
        with _usage_wrapper(observed, receipt):
            for name in ("router", "temporal", "planner", "coverage", "speaker"):
                Responses.create(
                    None,
                    model="gpt-5.6-luna",
                    input="synthetic, no real provider",
                    max_output_tokens=1400,
                    text={"format": {"name": name}},
                )
    assert calls == ["router", "temporal", "planner", "coverage", "speaker"]
    assert len(observed) == 5
    assert all(row["usage_complete"] for row in observed)
    assert sum(row["charged_usd"] for row in observed) < 0.25


def test_live_budget_blocks_one_extremely_large_call_before_provider(tmp_path):
    from unittest.mock import patch

    import pytest
    from openai.resources.responses.responses import Responses

    from scripts.odyssey_r0_browser_campaign import arm_case
    from scripts.odyssey_r0_real_browser_case import Refused, _usage_wrapper

    case = frozen_cases()[0]
    receipt = arm_case(tmp_path, case, 0.25)
    with patch.object(Responses, "create", side_effect=AssertionError("network called")):
        with _usage_wrapper([], receipt):
            with pytest.raises(Refused, match="preflight veto"):
                Responses.create(
                    None,
                    model="gpt-5.6-sol",
                    input="synthetic" * 20000,
                    max_output_tokens=1400,
                    text={"format": {"name": "no-network"}},
                )
