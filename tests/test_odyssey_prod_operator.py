"""Deterministic contract tests for the reboot-safe production operator."""

from __future__ import annotations

import subprocess
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "scripts" / "odyssey-prod"
SERVICE = Path(__file__).parents[1] / "deploy" / "odyssey-prod-runtime.service"
CURRENT = "a" * 40
OTHER = "b" * 40


def bash(function: str, *arguments: str) -> subprocess.CompletedProcess[str]:
    """Invoke one non-mutating Bash helper from the production operator."""
    quoted = " ".join(subprocess.list2cmdline([argument]) for argument in arguments)
    return subprocess.run(
        ["bash", "-c", f"source {SCRIPT}; {function} {quoted}"],
        check=False,
        text=True,
        capture_output=True,
    )


def test_source_guard_accepts_only_clean_synchronized_main() -> None:
    assert bash("source_is_approved", "main", "", CURRENT, CURRENT, CURRENT).returncode == 0


def test_source_guard_refuses_non_main_deployment() -> None:
    assert (
        bash(
            "source_is_approved",
            "phase23-production-self-identity-adoption",
            "",
            CURRENT,
            CURRENT,
            CURRENT,
        ).returncode
        != 0
    )


def test_source_guard_refuses_dirty_checkout() -> None:
    assert (
        bash(
            "source_is_approved", "main", " M scripts/odyssey-prod", CURRENT, CURRENT, CURRENT
        ).returncode
        != 0
    )


def test_source_guard_refuses_upstream_drift() -> None:
    assert bash("source_is_approved", "main", "", CURRENT, CURRENT, OTHER).returncode != 0


def test_root_guard_refuses_production_dev_overlap() -> None:
    assert bash("paths_do_not_overlap", "/data/odyssey", "/data/odyssey-dev").returncode == 0
    assert (
        bash("paths_do_not_overlap", "/data/odyssey/runtime", "/data/odyssey/runtime").returncode
        != 0
    )


def test_missing_stable_environment_source_fails_closed(tmp_path: Path) -> None:
    assert (
        bash("environment_source_has_required_keys", str(tmp_path / "missing.env")).returncode != 0
    )


def test_environment_source_is_checked_without_printing_values(tmp_path: Path) -> None:
    source = tmp_path / "secrets.env"
    source.write_text("OPENAI_API_KEY=\n", encoding="utf-8")
    result = bash("environment_source_has_required_keys", str(source))
    assert result.returncode == 0
    assert result.stdout == result.stderr == ""


def test_provenance_reports_match_drift_and_unknown() -> None:
    assert (
        bash("provenance_state", CURRENT, CURRENT, "main", "", CURRENT, CURRENT).stdout.strip()
        == "MATCH"
    )
    assert (
        bash("provenance_state", OTHER, CURRENT, "main", "", OTHER, OTHER).stdout.strip() == "DRIFT"
    )
    assert (
        bash("provenance_state", "", CURRENT, "main", "", CURRENT, CURRENT).stdout.strip()
        == "UNKNOWN"
    )


def test_health_contract_is_private_production_endpoint() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert "PROD_HOST=172.18.0.1" in source
    assert "PROD_PORT=8765" in source
    assert '"http://$PROD_HOST:$PROD_PORT/healthz"' in source


def test_source_contract_uses_the_established_explicit_worktree() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert 'git --git-dir="$PROD_SOURCE/.git" --work-tree="$PROD_SOURCE"' in source
    assert "prod_git status --porcelain" in source


def test_deploy_targets_only_production_runtime_service() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    deploy = source[source.index("deploy() {") : source.index("restart() {")]
    assert 'systemctl --user enable "$UNIT"' in deploy
    assert 'systemctl --user restart "$UNIT"' in deploy
    assert "n8n" not in deploy.lower()
    assert "cloudflared" not in deploy.lower()


def test_reboot_persistent_service_contract_is_structurally_present() -> None:
    service = SERVICE.read_text(encoding="utf-8")
    assert "EnvironmentFile=/home/ragdehl/.config/odyssey/secrets.env" in service
    assert "Restart=on-failure" in service
    assert "WantedBy=default.target" in service
    assert "ODYSSEY_RUNTIME_HOST=172.18.0.1" in service
    assert "ODYSSEY_RUNTIME_PORT=8765" in service
    assert "ReadWritePaths=/data/odyssey" in service


def test_status_is_read_only_and_cloudflared_diagnostic_has_no_lifecycle_action() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    status = source[source.index("status() {") : source.index("deploy() {")]
    diagnostic = source[source.index("cloudflared_dns_diagnostic() {") : source.index("status() {")]
    assert "systemctl --user is-active" in status
    assert "systemctl --user restart" not in status
    assert "install_artifacts" not in status
    assert "docker inspect" in diagnostic
    assert "docker logs" in diagnostic
    assert "docker compose" not in diagnostic
    assert "docker restart" not in diagnostic
    assert "docker recreate" not in diagnostic
