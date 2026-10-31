"""Provider-free controls for the R0 browser campaign controller."""

from __future__ import annotations

import json

import pytest

from scripts import odyssey_r0_browser_campaign as campaign


def _trace(case):
    return {
        "case": case.id,
        "source_sha256": case.source_sha256,
        "outcome": "deferred",
        "visible_ui_submitted": True,
        "real_n8n_single_throwaway_container": True,
        "isolated_actor_vault": True,
        "fresh_vault_per_case": True,
        "original_fixture_13_notes": True,
        "fixed_original_clock": True,
        "source_preserved": True,
        "markdown_source_readback": True,
        "ui_reload_readback": True,
        "replay_checked": True,
        "cloudflare_public_access_used": False,
        "provider_usage": [{"model": "synthetic-test-model", "input_tokens": 1}],
    }


def test_offline_inventory_uses_exact_27_original_sources_and_never_calls_provider(tmp_path):
    cases = campaign.frozen_cases()
    assert [case.id for case in cases] == [f"F{i:02d}" for i in range(1, 28)]
    assert campaign.accounted_spend(tmp_path / "missing", cases) == 0.25
    assert all(len(case.source_sha256) == 64 for case in cases)


def test_armed_receipt_is_durable_and_conservatively_charged_without_usage(tmp_path):
    case = campaign.frozen_cases()[0]
    receipt = campaign.arm_case(tmp_path, case, 0.25)
    data = json.loads(receipt.read_text())
    assert data["outcome"] == "armed"
    assert campaign.accounted_spend(tmp_path, campaign.frozen_cases()) == 0.5
    with pytest.raises(campaign.CampaignError, match="never silently retry"):
        campaign.arm_case(tmp_path, case, 0.25)


def test_trace_requires_isolated_actor_vault_exact_source_and_no_cloudflare():
    case = campaign.frozen_cases()[10]
    accepted = campaign.validate_adapter_trace(_trace(case), case)
    assert accepted["outcome"] == "deferred"
    bad_hash = _trace(case)
    bad_hash["source_sha256"] = "0" * 64
    with pytest.raises(campaign.CampaignError, match="original source"):
        campaign.validate_adapter_trace(bad_hash, case)
    bad_isolation = _trace(case)
    bad_isolation["fresh_vault_per_case"] = False
    with pytest.raises(campaign.CampaignError, match="lacks required"):
        campaign.validate_adapter_trace(bad_isolation, case)
    bad_cloudflare = _trace(case)
    bad_cloudflare["cloudflare_public_access_used"] = True
    with pytest.raises(campaign.CampaignError, match="Cloudflare"):
        campaign.validate_adapter_trace(bad_cloudflare, case)


def test_rejected_trace_without_provider_usage_cannot_be_recorded_as_live():
    case = campaign.frozen_cases()[0]
    trace = _trace(case)
    trace["provider_usage"] = []
    with pytest.raises(campaign.CampaignError, match="provider usage"):
        campaign.validate_adapter_trace(trace, case)


def test_failed_browser_run_retains_forensics_without_false_pass():
    case = campaign.frozen_cases()[5]
    failure = {
        "case": case.id,
        "source_sha256": case.source_sha256,
        "outcome": "failed",
        "provider_usage": [],
        "forensics": {"error": "RouterError", "detail": "bootstrap rejected"},
    }
    assert campaign.validate_adapter_trace(failure, case)["forensics"]["error"] == "RouterError"
    failure["outcome"] = "passed"
    with pytest.raises(campaign.CampaignError, match="Cloudflare"):
        campaign.validate_adapter_trace(failure, case)
