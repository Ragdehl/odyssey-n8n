"""Frozen offline-only audit for the approved Router fact-candidate v2 models."""

from __future__ import annotations

from pathlib import Path

from benchmarks.fact_candidate_v2_preflight.check import MAX_CALLS, audit


def test_offline_envelopes_reuse_real_model_settings_but_not_live_provider() -> None:
    """Expose accidental model, storage, schema or budget drift before any spend."""
    report = audit()
    rows = report["calls"]
    assert report["mode"] == "OFFLINE_ONLY_NO_PROVIDER"
    assert MAX_CALLS == len(rows) == 9
    assert [r["case"] for r in rows[:4]] == ["F14", "F27", "F09", "F10"]
    assert [r["stage"] for r in rows] == [
        "router",
        "router",
        "router",
        "router",
        "temporal",
        "luna_core",
        "temporal",
        "luna_core",
        "attribution",
    ]
    assert [r["model"] for r in rows[:4]] == ["gpt-6-luna"] * 4
    assert [r["model"] for r in rows if r["stage"] == "luna_core"] == [
        "gpt-5.6-luna",
        "gpt-5.6-luna",
    ]
    assert report["ceiling_usd"] == 0.02
    assert not report["fits_ceiling"]
    assert report["total_upper_usd"] > report["ceiling_usd"]


def test_first_wave_fits_ceiling_only_when_luna_core_is_excluded() -> None:
    """Limit the next reviewable wave to Router and Temporal, never Core writes."""
    report = audit()
    first = report["first_wave"]
    assert first["cases"] == ["F14", "F27", "F09", "F10"]
    assert first["stages"] == ["router", "temporal"]
    assert first["calls"] == 6
    assert first["fits_ceiling"]
    assert 0 < first["upper_usd"] < report["ceiling_usd"]
    assert first["requires_separate_allowed_live_workflow"]


def test_offline_audit_source_has_no_credential_or_provider_entrypoint() -> None:
    """Preflight may construct payloads, but cannot own live invocation authority."""
    source = (
        Path(__file__).resolve().parents[2] / "benchmarks/fact_candidate_v2_preflight/check.py"
    ).read_text()
    for unsafe in (
        "import openai",
        "from openai import",
        "os.environ",
        "EnvironmentFile=",
        "OpenAI(",
        "OPENAI_API_KEY",
        "subprocess.run",
    ):
        assert unsafe not in source
