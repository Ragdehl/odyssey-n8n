"""The manual Playground export is inert and mirrors captured Router requests."""

from __future__ import annotations

import hashlib
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


def test_archived_playground_export_remains_intact_but_cannot_approve_current_router() -> None:
    """The previously shared manual requests are historical, not a live pin."""
    assert hashlib.sha256(OUTPUT.read_bytes()).hexdigest() == (
        "51159a04781a4462503d34d6bab7980967f565e6795dce5527353172c548bf95"
    )
    old = json.loads(OUTPUT.read_text(encoding="utf-8"))
    active = export()
    assert old != active  # Current prompt changed; don't re-export over old evidence.
    assert old["executes_provider"] is active["executes_provider"] is False
    assert old["validated_model_equivalence"] is active["validated_model_equivalence"] is False
