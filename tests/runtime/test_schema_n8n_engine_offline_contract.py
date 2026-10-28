"""Security and authority contract for the opt-in offline n8n Code smoke."""

from pathlib import Path

import pytest

from scripts.odyssey_schema_n8n_engine_offline import (
    ROOT,
    SHELL,
    source_code,
    workflow,
)


def test_offline_projection_reuses_exact_validator_and_actor_contract():
    project = Path(__file__).resolve().parents[2]
    assert ROOT == project
    code = source_code()
    assert "schema_backfill" in code and "schema_scan" in code
    assert "authenticated_actor" in code
    assert "schema_confirm" in code
    assert "operation !== 'schema_backfill'" in code
    result = workflow()
    assert len(result["nodes"]) == 21
    assert all("credentials" not in node for node in result["nodes"])
    validator = next(n for n in result["nodes"] if n["name"] == "Validate valid")
    assert validator["parameters"]["jsCode"] == code
    for name in ("forged", "bad_action", "bool_version", "extra_approval", "forged_followup"):
        assert next(n for n in result["nodes"] if n["name"] == "Validate " + name)
    for name in ("followup_stage", "followup_status", "followup_advance"):
        assert next(n for n in result["nodes"] if n["name"] == "Validate " + name)
    assert "$input.first()" in code
    assert "n8n execute" in SHELL and "n8n import:workflow" in SHELL


def test_offline_driver_contains_no_deployment_or_provider_channels():
    module = ROOT / "scripts/odyssey_schema_n8n_engine_offline.py"
    raw = module.read_text()
    assert "docker" in raw
    for protection in (
        "--network",
        "none",
        "--read-only",
        "--cap-drop",
        "ALL",
        "no-new-privileges",
        "--pids-limit",
        "never",
        "/tmp",
        "target=/fixture/workflow.json,readonly",
    ):
        assert protection in raw
    for unsafe in (
        "ODYSSEY_OPENAI_API_KEY",
        "OPENAI_API_KEY",
        "ODYSSEY_CF_ACCESS_CLIENT_SECRET",
        "/data/odyssey",
    ):
        assert unsafe not in raw
    assert '"--run", action="store_true"' in raw


def test_missing_source_template_fails_closed(monkeypatch):
    original = Path.read_text

    def injected(self, *args, **kwargs):
        if self.name == "odyssey-online.ts":
            return "const notesValidate = node({});"
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", injected)
    with pytest.raises(ValueError):
        source_code()
