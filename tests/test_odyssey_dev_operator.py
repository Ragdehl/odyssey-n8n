"""Deterministic tests for the DEV deployment coherence guard."""

from __future__ import annotations

import json
import shlex
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "scripts" / "odyssey-dev"
ROUTE_INVENTORY = Path(__file__).parents[1] / "deploy" / "odyssey-dev-product-routes.tsv"
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


def asset_coherence_result(
    tmp_path: Path, function: str, host_fingerprint: str, mounted_fingerprint: str
) -> bool:
    """Evaluate one real web-asset coherence predicate with controlled fingerprints."""
    deployment = tmp_path / "n8n-deployment"
    deployment.write_text(
        f"web_assets_sha256=recorded\nweb_deployment_marker={CURRENT}\n", encoding="utf-8"
    )
    web_root = tmp_path / "web"
    web_root.mkdir(exist_ok=True)
    (web_root / "environment.js").write_text(
        f'globalThis.ODYSSEY_DEPLOYMENT = Object.freeze({{commit: "{CURRENT}"}});\n',
        encoding="utf-8",
    )
    command = f"""
source {shlex.quote(str(SCRIPT))}
N8N_DEPLOYMENT={shlex.quote(str(deployment))}
DEV_WEB={shlex.quote(str(web_root))}
web_asset_fingerprint() {{ printf '%s\n' {shlex.quote(host_fingerprint)}; }}
mounted_web_asset_fingerprint() {{ printf '%s\n' {shlex.quote(mounted_fingerprint)}; }}
{function} {CURRENT}
"""
    return subprocess.run(["bash", "-c", command], check=False).returncode == 0


def prestart_coherence_result(tmp_path: Path, host_fingerprint: str) -> bool:
    """Run the real source preflight while making a container mount unavailable."""
    source_root = tmp_path / "source"
    source_root.mkdir()
    (source_root / "README").write_text("fixture\n", encoding="utf-8")
    for command in (
        ["git", "-C", str(source_root), "init", "-q"],
        ["git", "-C", str(source_root), "config", "user.email", "test@example.invalid"],
        ["git", "-C", str(source_root), "config", "user.name", "Test"],
        ["git", "-C", str(source_root), "add", "README"],
        ["git", "-C", str(source_root), "commit", "-qm", "fixture"],
    ):
        subprocess.run(command, check=True)
    commit = subprocess.check_output(
        ["git", "-C", str(source_root), "rev-parse", "HEAD"], text=True
    ).strip()
    deployment = tmp_path / "n8n-deployment"
    deployment.write_text(
        "\n".join(
            (
                f"source_commit={commit}",
                "web_assets_sha256=recorded",
                f"web_deployment_marker={commit}",
                "",
            )
        ),
        encoding="utf-8",
    )
    deployed_commit = tmp_path / "deployed-commit"
    deployed_commit.write_text(f"{commit}\n", encoding="utf-8")
    web_root = tmp_path / "web"
    web_root.mkdir()
    (web_root / "environment.js").write_text(
        f'globalThis.ODYSSEY_DEPLOYMENT = Object.freeze({{commit: "{commit}"}});\n',
        encoding="utf-8",
    )
    command = f"""
source {shlex.quote(str(SCRIPT))}
DEV_SOURCE={shlex.quote(str(source_root))}
N8N_DEPLOYMENT={shlex.quote(str(deployment))}
DEPLOYED_COMMIT={shlex.quote(str(deployed_commit))}
DEV_WEB={shlex.quote(str(web_root))}
web_asset_fingerprint() {{ printf '%s\n' {shlex.quote(host_fingerprint)}; }}
mounted_web_asset_fingerprint() {{ return 1; }}
assert_deployed_source_coherent
"""
    return subprocess.run(["bash", "-c", command], check=False).returncode == 0


def lifecycle_result(
    tmp_path: Path, action: str, mounted_check_succeeds: bool
) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    """Run the DEV lifecycle with deterministic component boundaries and event evidence."""
    events = tmp_path / "events"
    deployment = tmp_path / "n8n-deployment"
    deployed_commit = tmp_path / "deployed-commit"
    deployment.touch()
    deployed_commit.touch()
    mounted_result = "return 0" if mounted_check_succeeds else "return 1"
    invocation = "stop; start" if action == "restart" else action
    command = f"""
source {shlex.quote(str(SCRIPT))}
EVENTS={shlex.quote(str(events))}
N8N_DEPLOYMENT={shlex.quote(str(deployment))}
DEPLOYED_COMMIT={shlex.quote(str(deployed_commit))}
guard() {{ :; }}
assert_deployed_source_coherent() {{ printf 'preflight\n' >> "$EVENTS"; }}
assert_deployed_mounted_web_assets_coherent() {{ printf 'mounted-assets\n' >> "$EVENTS"; {mounted_result}; }}
systemctl() {{ printf 'systemctl:%s\n' "$*" >> "$EVENTS"; }}
n8n_compose() {{ printf 'compose:%s\n' "$*" >> "$EVENTS"; }}
wait_health() {{ printf 'runtime-health\n' >> "$EVENTS"; }}
wait_n8n_health() {{ printf 'n8n-health\n' >> "$EVENTS"; }}
wait_workflow_readiness() {{ printf 'workflow-readiness\n' >> "$EVENTS"; }}
{invocation}
"""
    result = subprocess.run(["bash", "-c", command], check=False, capture_output=True, text=True)
    return result, events.read_text(encoding="utf-8").splitlines()


def test_start_checks_host_assets_before_start_and_mounted_assets_after_n8n_health(
    tmp_path: Path,
) -> None:
    """A stopped n8n can start because its mount is verified only after it is available."""
    result, events = lifecycle_result(tmp_path, "start", mounted_check_succeeds=True)
    assert result.returncode == 0, result.stderr
    assert events == [
        "preflight",
        "systemctl:--user start odyssey-dev-runtime.service",
        "runtime-health",
        "compose:up -d",
        "n8n-health",
        "mounted-assets",
        "workflow-readiness",
    ]


def test_restart_performs_stop_then_start_and_rechecks_the_mounted_assets(tmp_path: Path) -> None:
    """Restart keeps a genuine DEV stop/start lifecycle while preserving readiness evidence."""
    result, events = lifecycle_result(tmp_path, "restart", mounted_check_succeeds=True)
    assert result.returncode == 0, result.stderr
    assert events == [
        "compose:stop",
        "systemctl:--user stop odyssey-dev-runtime.service",
        "preflight",
        "systemctl:--user start odyssey-dev-runtime.service",
        "runtime-health",
        "compose:up -d",
        "n8n-health",
        "mounted-assets",
        "workflow-readiness",
    ]


def test_host_asset_drift_fails_the_prestart_coherence_check(tmp_path: Path) -> None:
    """Host assets must still match the recorded deployment before services are started."""
    assert prestart_coherence_result(tmp_path, "drifted") is False


def test_mounted_asset_drift_fails_after_n8n_starts_before_readiness(tmp_path: Path) -> None:
    """A changed container mount cannot be reported as a successful DEV start."""
    result, events = lifecycle_result(tmp_path, "start", mounted_check_succeeds=False)
    assert result.returncode != 0
    assert events == [
        "preflight",
        "systemctl:--user start odyssey-dev-runtime.service",
        "runtime-health",
        "compose:up -d",
        "n8n-health",
        "mounted-assets",
    ]


def test_host_preflight_does_not_require_a_stopped_n8n_container(tmp_path: Path) -> None:
    """The pre-start check remains valid without a mounted-container fingerprint."""
    assert prestart_coherence_result(tmp_path, "recorded") is True
    assert asset_coherence_result(tmp_path, "web_assets_coherent", "recorded", "drifted") is False


def publication_result(rows: list[dict[str, object]]) -> subprocess.CompletedProcess[str]:
    """Run the DEV operator's pure active-version publication validator."""
    command = (
        f"source {SCRIPT}; PYTHON={shlex.quote(sys.executable)}; "
        f"DEV_ROUTE_INVENTORY={shlex.quote(str(ROUTE_INVENTORY))}; "
        "workflow_publication_is_valid"
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


def test_publication_rejects_an_uninventoried_active_webhook() -> None:
    """Keep public readiness fail-closed when deployed n8n exposes an extra route."""
    rows = valid_publication_rows()
    rows[0]["activeVersionNodes"] = active_version_nodes(
        ("POST", "request"),
        ("POST", "conversation"),
        ("POST", "notes"),
        ("POST", "admin"),
    )
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
    inventory = (Path(__file__).parents[1] / "deploy" / "odyssey-dev-product-routes.tsv").read_text(
        encoding="utf-8"
    )
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
        "/api/notes",
    )
    for route in expected:
        assert route in inventory
    assert "DEV_ROUTE_INVENTORY" in source
    assert "assert_dev_product_route_inventory" in source
    assert source.index("assert_dev_product_route_inventory") < source.index("publish_workflows")


def test_publication_and_readiness_require_the_notes_and_complete_module_routes() -> None:
    """Do not declare DEV healthy while a Notes browser import or product route is absent."""

    source = SCRIPT.read_text(encoding="utf-8")
    inventory = (Path(__file__).parents[1] / "deploy" / "odyssey-dev-product-routes.tsv").read_text(
        encoding="utf-8"
    )
    for route in ("notes.js", "notes-client.js"):
        assert route in inventory
    assert '"http://$N8N_HOST:$N8N_PORT/api/notes"' in source
    assert "dev_static_paths" in source
    assert 'for path in "${static_paths[@]}"' in source


def test_status_distinguishes_public_route_provenance_from_access_reachability() -> None:
    """An Access redirect alone must never be reported as complete public-route readiness."""
    source = SCRIPT.read_text(encoding="utf-8")
    status = source[source.index("status() {") : source.index("deploy() {")]
    assert "public_route_provenance" in status
    assert "public_endpoint" in status
    assert "public-status" in source
    assert "odyssey_dev_public_routes.py" in source


def test_publish_uses_n8n_current_imported_version_not_a_stale_history_pointer() -> None:
    """n8n 2.33 creates the current history version during publish, not import."""

    source = SCRIPT.read_text(encoding="utf-8")
    publish = source[source.index("publish_workflows() {") : source.index("workflow_metadata() {")]
    assert "n8n import:workflow" in publish
    assert "n8n publish:workflow --id=$workflow_id >/dev/null" in publish
    assert "n8n publish:workflow --id=$workflow_id --versionId=" not in publish
