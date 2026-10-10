"""The manual Playground export is inert and mirrors captured Router requests."""

from __future__ import annotations

import json

from benchmarks.fact_candidate_v2_preflight.export_playground_requests import (
    OUTPUT,
    export,
)


def test_manual_export_is_only_frozen_synthetic_router_data() -> None:
    """Export never calls a provider or includes Core planner/private data."""
    output = export()
    assert output["mode"] == "MANUAL_PLAYGROUND_EXPORT_ONLY"
    assert output["executes_provider"] is False
    assert output["validated_model_equivalence"] is False
    assert [row["id"] for row in output["calls"]] == ["F09", "F10", "F14", "F27"]
    for row in output["calls"]:
        req = row["request"]
        assert req["model"] == "gpt-6-luna"
        assert req["reasoning"] == {"effort": "low"}
        assert req["store"] is False
        assert req["text"]["format"]["strict"] is True
    rendered = json.dumps(output, ensure_ascii=False)
    assert "OPENAI_API_KEY" not in rendered
    assert "sk-proj-" not in rendered


def test_checked_in_export_equals_current_requests() -> None:
    """Review bundle changes when the production-shaped inputs change."""
    assert json.loads(OUTPUT.read_text(encoding="utf-8")) == export()
