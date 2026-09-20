"""Deterministic tests for the DEV deployment coherence guard."""

from __future__ import annotations

import json
import shlex
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "scripts" / "odyssey-dev"
CURRENT = "a" * 40
OTHER = "b" * 40


def coherence_result(current: str, recorded: str, deployed: str, dirty: str) -> bool:
    """Evaluate the operator's source-coherence predicate in Bash."""
    command = f"source {SCRIPT}; source_is_coherent {current} {recorded} {deployed} {dirty!r}"
    return subprocess.run(["bash", "-c", command], check=False).returncode == 0


def test_clean_checkout_at_deployed_commit_is_coherent() -> None:
    assert coherence_result(CURRENT, CURRENT, CURRENT, "") is True


def test_different_head_is_not_coherent() -> None:
    assert coherence_result(OTHER, CURRENT, CURRENT, "") is False


def test_dirty_checkout_is_not_coherent() -> None:
    assert coherence_result(CURRENT, CURRENT, CURRENT, " M scripts/odyssey-dev") is False


def test_publish_allows_only_the_approved_dev_answerer_credential() -> None:
    """Keep DEV deployment bounded to its single explicitly approved credential."""
    source = SCRIPT.read_text(encoding="utf-8")
    assert "SELECT name, type FROM credentials_entity ORDER BY name" in source
    assert "Odyssey DEV OpenAI Answerer" in source
    assert "httpBearerAuth" in source
    assert "DEV n8n credentials are not exactly the approved DEV answerer credential" in source


def test_render_binds_the_isolated_answerer_credential_id() -> None:
    """Keep the generated DEV workflow bound to the isolated credential record."""
    source = SCRIPT.read_text(encoding="utf-8")
    assert "ODYSSEY_DEV_ANSWERER_CREDENTIAL_ID" in source
    assert 'name: "Odyssey DEV OpenAI Answerer"' in source


def test_dev_runtime_service_loads_the_approved_provider_environment() -> None:
    """Keep the isolated DEV planner able to use the existing protected provider key."""
    service = (Path(__file__).parents[1] / "deploy" / "odyssey-dev-runtime.service").read_text(
        encoding="utf-8"
    )
    assert "EnvironmentFile=/home/ragdehl/.config/odyssey/secrets.env" in service


def test_dev_provenance_binds_host_and_mounted_web_assets_to_the_commit() -> None:
    """Prevent MATCH when the served DEV web mount belongs to another deployment."""
    source = SCRIPT.read_text(encoding="utf-8")
    assert "web_assets_sha256" in source
    assert "web_deployment_marker" in source
    assert "mounted_web_asset_fingerprint" in source
    assert 'web_assets_coherent "$current"' in source
    assert "mounted_paths=$(printf '/odyssey-web/%s '" in source


def publication_result(rows: list[dict[str, object]]) -> subprocess.CompletedProcess[str]:
    """Run the DEV operator's pure active-version publication validator."""
    command = (
        f"source {SCRIPT}; PYTHON={shlex.quote(sys.executable)}; workflow_publication_is_valid"
    )
    return subprocess.run(
        ["bash", "-c", command],
        check=False,
        input=json.dumps(rows),
        capture_output=True,
        text=True,
    )


def active_version_nodes(*webhooks: tuple[str, str]) -> str:
    """Build the smallest n8n active-version node payload for a publication test."""
    return json.dumps(
        [
            {
                "type": "n8n-nodes-base.webhook",
                "parameters": {"httpMethod": method, "path": path},
            }
            for method, path in webhooks
        ]
    )


def valid_publication_rows() -> list[dict[str, object]]:
    """Return the two expected DEV workflows with valid published active versions."""
    return [
        {
            "id": "odyssey-online",
            "name": "Odyssey — DEV Online product boundary",
            "active": 0,
            "activeVersionId": "online-version",
            "activeVersionNodes": active_version_nodes(
                ("POST", "request"), ("POST", "conversation"), ("POST", "notes")
            ),
        },
        {
            "id": "odyssey-online-static",
            "name": "Odyssey — DEV Online static assets",
            "active": 0,
            "activeVersionId": "static-version",
            "activeVersionNodes": active_version_nodes(
                ("GET", "odyssey"),
                ("GET", "styles.css"),
                ("GET", "environment.js"),
                ("GET", "app.js"),
                ("GET", "client.js"),
                ("GET", "notes.js"),
                ("GET", "notes-client.js"),
            ),
        },
    ]


def test_publication_uses_active_version_not_legacy_active_flag() -> None:
    """n8n 2.x publication remains valid even when legacy active is false."""
    assert publication_result(valid_publication_rows()).returncode == 0


def test_publication_rejects_missing_active_version() -> None:
    """Fail closed when a workflow lacks a n8n 2.x published-version identity."""
    rows = valid_publication_rows()
    rows[0]["activeVersionId"] = None
    assert publication_result(rows).returncode != 0


def test_publication_rejects_active_version_without_request_webhook() -> None:
    """Fail closed when the active online version is not the expected DEV boundary."""
    rows = valid_publication_rows()
    rows[0]["activeVersionNodes"] = active_version_nodes(("POST", "conversation"))
    assert publication_result(rows).returncode != 0


def test_readiness_waits_for_route_not_only_n8n_health() -> None:
    """Keep process health distinct from deterministic product-route readiness."""
    source = SCRIPT.read_text(encoding="utf-8")
    assert "wait_n8n_health" in source
    assert "wait_workflow_readiness" in source
    assert "route_readiness_once" in source
    assert "static_route_readiness_once" in source
    assert '"http://$N8N_HOST:$N8N_PORT/api/request"' in source


def test_readiness_probe_is_invalid_and_cannot_reach_runtime_or_provider() -> None:
    """Keep the route readiness probe on the validation branch before runtime execution."""
    source = SCRIPT.read_text(encoding="utf-8")
    assert '"request":""' in source
    assert '"request_id":"dev-readiness-invalid"' in source
    assert '"status": "failed"' in source
    assert '"kind": "error"' in source


def test_deployment_record_follows_workflow_readiness() -> None:
    """Do not record a DEV deployment until its webhook route is ready."""
    source = SCRIPT.read_text(encoding="utf-8")
    deploy_tail = source[source.index("deploy() {") :]
    assert deploy_tail.index("wait_workflow_readiness") < deploy_tail.index("record_deployment")


def test_dev_route_inventory_lists_every_browser_and_workflow_product_path() -> None:
    """Keep new UI routes from silently falling outside the explicit DEV route inventory."""
    source = SCRIPT.read_text(encoding="utf-8")
    expected = (
        "/api/odyssey",
        "/api/styles.css",
        "/api/app.js",
        "/api/client.js",
        "/api/notes.js",
        "/api/notes-client.js",
        "/api/environment.js",
        "/api/request",
        "/api/conversation",
    )
    for route in expected:
        assert route in source
    assert "assert_dev_product_route_inventory" in source
    assert source.index("assert_dev_product_route_inventory") < source.index("publish_workflows")


def test_publication_and_readiness_require_the_notes_and_complete_module_routes() -> None:
    """Do not declare DEV healthy while a Notes browser import or product route is absent."""

    source = SCRIPT.read_text(encoding="utf-8")
    assert '("POST", "notes")' in source
    for route in ("notes.js", "notes-client.js"):
        assert f'("GET", "{route}")' in source
        assert route in source
    assert '"http://$N8N_HOST:$N8N_PORT/api/notes"' in source
    assert "DEV_STATIC_PATHS=(/api/odyssey" in source
    assert 'for path in "${DEV_STATIC_PATHS[@]}"' in source
