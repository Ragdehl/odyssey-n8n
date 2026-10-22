"""Regression sentinels for Odyssey agent instructions and safe context discovery."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _load_script(name: str):
    """Load a standalone script without executing its command-line entrypoint."""
    path = ROOT / "scripts" / name
    spec = importlib.util.spec_from_file_location(name.removesuffix(".py"), path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_skill_discovery_and_canonical_document_links_are_valid() -> None:
    """Prevent silent loss of mandatory agent workflows and relative references."""
    guard = _load_script("odyssey_docs_guard.py")
    assert guard.check() == []


def test_short_agent_contract_routes_to_llm_and_generality() -> None:
    """Keep critical always-on rules visible regardless of optional skills."""
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert len(agents.splitlines()) <= 150
    assert "odyssey-llm-stage" in agents
    assert "odyssey-generality" in agents
    assert "Core/E3" in agents
    assert "systemd" in agents
    assert "human" in agents.lower()


def test_doctor_never_displays_protected_key_and_fails_closed_on_unknown(
    tmp_path: Path,
) -> None:
    """A readable secret file only yields booleans; no secret value is read."""
    doctor = _load_script("odyssey_context_doctor.py")
    src = tmp_path / "checkout"
    dev = tmp_path / "dev"
    src.mkdir()
    dev.mkdir()
    secret_file = tmp_path / "protected.env"
    dummy_secret = "odyssey-do-not-leak-this-fixture-value-123"
    secret_file.write_text("OPENAI_API_KEY=" + dummy_secret, encoding="utf-8")
    marker = tmp_path / "deployed-commit"
    marker.write_text("invalid-id", encoding="utf-8")
    result = doctor.inspect(
        repo=src,
        dev_root=dev,
        marker_path=marker,
        env_path=secret_file,
        check_health=False,
    )
    rendered = json.dumps(result)
    assert dummy_secret not in rendered
    assert "OPENAI_API_KEY=" not in rendered
    assert result["provider_environment"]["protected_file_readable"] is True
    assert result["provider_environment"]["key_value_examined"] is False
    assert result["dev_checkout_matches_marker"] is False
    assert result["source_sha"] == "unknown"
    assert any("marker/checkout unknown" in x for x in result["warnings"])


def test_doctor_marker_requires_exact_full_sha(tmp_path: Path) -> None:
    """Prevent mistaking a stale, truncated or malformed marker for a release."""
    doctor = _load_script("odyssey_context_doctor.py")
    marker = tmp_path / "deployed-commit"
    assert doctor._marker(marker) is None
    marker.write_text("abc123", encoding="utf-8")
    assert doctor._marker(marker) is None
    marker.write_text("a" * 40 + "\n", encoding="utf-8")
    assert doctor._marker(marker) == "a" * 40
