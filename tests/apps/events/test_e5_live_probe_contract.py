"""Offline guard: E5 live-model probe must never be mistaken for product E2E."""

from __future__ import annotations

import pytest

from scripts import e5_live_intent_probe as gate


def test_real_model_oracle_is_diverse_and_contains_negative_safety_cases():
    ids = [row[0] for row in gate.CASES]
    assert len(ids) == len(set(ids)) == 9
    assert {expected for _, _, expected in gate.CASES} == {
        "CREATE",
        "UPDATE",
        "CANCEL",
        "QUERY",
        "ABSTAIN",
    }
    assert sum(expected == "ABSTAIN" for _, _, expected in gate.CASES) == 3
    assert all(isinstance(source, str) and len(source) > 20 for _, source, _ in gate.CASES)
    assert gate.SCHEMA["additionalProperties"] is False
    assert gate.SCHEMA["required"] == ["operation", "temporal_mentions", "event_reference"]
    assert gate.SCHEMA["properties"]["temporal_mentions"]["maxItems"] == 16


def test_probe_cannot_contact_gpt_without_explicit_live_approval(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ODYSSEY_E5_LIVE_APPROVED", raising=False)
    with pytest.raises(SystemExit, match="Authorized ephemeral"):
        gate.main()
