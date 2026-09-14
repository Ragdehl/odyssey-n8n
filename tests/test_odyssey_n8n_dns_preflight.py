"""Deterministic contract tests for the production n8n DNS preflight."""

import subprocess
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "scripts" / "odyssey-n8n-dns-preflight"


def test_preflight_script_is_valid_bash() -> None:
    result = subprocess.run(
        ["bash", "-n", str(SCRIPT)], check=False, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr


def test_preflight_uses_node_dns_lookup_without_provider_http_call() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert 'const dns = require("dns")' in source
    assert "dns.lookup(host" in source
    assert "api.openai.com" in source
    assert "curl " not in source
    assert "wget " not in source
    assert "https://api.openai.com" not in source


def test_preflight_is_read_only_and_has_no_container_lifecycle_action() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert "docker inspect" in source
    assert "docker exec" in source
    assert "docker logs" in source
    for forbidden in (
        "docker restart",
        "docker stop",
        "docker rm",
        "docker compose up",
        "--force-recreate",
        "docker pull",
    ):
        assert forbidden not in source


def test_preflight_classifies_container_only_failure_as_drift() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert '[ "$host_dns" = healthy ] && [ "$node_rc" -ne 0 ]' in source
    assert "dns_preflight=DRIFT" in source
    assert "dns_preflight=HOST_UNHEALTHY" in source
    assert "dns_preflight=MATCH" in source


def test_preflight_does_not_print_resolved_addresses_or_secrets() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert "address" not in source
    assert "OPENAI_API_KEY" not in source
    assert "credentials" not in source.lower()
