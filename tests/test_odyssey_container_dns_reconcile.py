"""Deterministic tests for the production container DNS reconciliation guard."""

from __future__ import annotations

import shlex
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "scripts" / "odyssey-container-dns-reconcile"
SERVICE = Path(__file__).parents[1] / "deploy" / "odyssey-container-dns-reconcile.service"


def run_bash(script: str) -> subprocess.CompletedProcess[str]:
    """Run one isolated guard harness without contacting Docker or production."""
    return subprocess.run(
        ["bash", "-c", f"source {shlex.quote(str(SCRIPT))}; {script}"],
        check=False,
        text=True,
        capture_output=True,
    )


def guard_harness(
    *,
    cloudflared_assessment: str = "0",
    n8n_assessment: str = "0",
    host_dns: bool = True,
    recovery: bool = True,
) -> str:
    """Return shell overrides for one deterministic two-target guard run."""
    host_result = "return 0" if host_dns else "return 1"
    recovery_result = "return 0" if recovery else "return 1"
    return f"""
validate_scope() {{ :; }}
host_dns_healthy() {{ {host_result}; }}
wait_for_startup_readiness() {{ :; }}
n8n_mount_fingerprint() {{ printf 'volume|n8n_data|/home/node/.n8n|true\\n'; }}
assess_target() {{
  case "$1" in
    cloudflared) REASON='cloudflared test state'; return {cloudflared_assessment} ;;
    n8n) REASON='n8n test state'; return {n8n_assessment} ;;
  esac
}}
compose_recreate() {{ printf 'recreate:%s\\n' "$1"; {recovery_result}; }}
wait_for_target() {{ {recovery_result}; }}
run_guard
"""


def test_both_healthy_do_not_recreate() -> None:
    result = run_bash(guard_harness())
    assert result.returncode == 0
    assert "recreate:" not in result.stdout
    assert "[HEALTHY] service=cloudflared" in result.stderr
    assert "[HEALTHY] service=n8n" in result.stderr


def test_stale_cloudflared_recreates_only_cloudflared() -> None:
    result = run_bash(guard_harness(cloudflared_assessment="10"))
    assert result.returncode == 0
    assert result.stdout == "recreate:cloudflared\n"
    assert "service=n8n" not in result.stdout


def test_stale_n8n_recreates_only_n8n() -> None:
    result = run_bash(guard_harness(n8n_assessment="10"))
    assert result.returncode == 0
    assert result.stdout == "recreate:n8n\n"
    assert "service=cloudflared" not in result.stdout


def test_both_stale_recreate_each_once_independently() -> None:
    result = run_bash(guard_harness(cloudflared_assessment="10", n8n_assessment="10"))
    assert result.returncode == 0
    assert result.stdout.splitlines() == ["recreate:cloudflared", "recreate:n8n"]


def test_unhealthy_host_dns_recreates_nothing() -> None:
    result = run_bash(
        guard_harness(host_dns=False, cloudflared_assessment="10", n8n_assessment="10")
    )
    assert result.returncode != 0
    assert result.stdout == ""
    assert "host DNS is unhealthy" in result.stderr


def test_container_not_running_during_startup_grace_waits_without_recreation() -> None:
    result = run_bash(
        """
validate_scope() { :; }
host_dns_healthy() { return 0; }
wait_for_startup_readiness() { printf 'startup-grace\n'; return 1; }
assess_target() { printf 'unexpected-assessment:%s\n' "$1"; return 10; }
compose_recreate() { printf 'recreate:%s\n' "$1"; }
run_guard
"""
    )
    assert result.returncode != 0
    assert result.stdout == "startup-grace\n"
    assert "unexpected-assessment" not in result.stdout
    assert "RECOVERING" not in result.stderr
    assert "bounded startup readiness" in result.stderr


def test_cloudflared_registration_appears_during_startup_grace() -> None:
    result = run_bash(
        """
validate_scope() { :; }
host_dns_healthy() { return 0; }
container_running() { return 0; }
resolvers_match_host() { return 0; }
cloudflared_started_at() { printf 'started\n'; }
registration_checks=0
cloudflared_registered() {
  registration_checks=$((registration_checks + 1))
  [ "$registration_checks" -ge 2 ]
}
sleep() { :; }
assess_target() { REASON='healthy test state'; return 0; }
compose_recreate() { printf 'recreate:%s\n' "$1"; }
run_guard
"""
    )
    assert result.returncode == 0
    assert result.stdout == ""
    assert "recreate:" not in result.stdout
    assert "HEALTHY" in result.stderr


def test_failed_recovery_has_no_second_attempt_or_escalation() -> None:
    result = run_bash(
        """
validate_scope() { :; }
host_dns_healthy() { return 0; }
wait_for_startup_readiness() { :; }
n8n_mount_fingerprint() { printf 'volume|n8n_data|/home/node/.n8n|true\\n'; }
assess_target() { REASON='stale test state'; [ "$1" = cloudflared ] && return 10 || return 0; }
compose_recreate() { printf 'recreate:%s\\n' "$1"; return 0; }
wait_for_target() { return 1; }
run_guard
"""
    )
    assert result.returncode != 0
    assert result.stdout == "recreate:cloudflared\n"
    assert result.stdout.count("recreate:cloudflared") == 1
    assert "no retry or escalation" in result.stderr


def test_boot_unit_orders_after_network_and_docker_without_restart_loop() -> None:
    source = SERVICE.read_text(encoding="utf-8")
    assert "Wants=network-online.target" in source
    assert "After=network-online.target docker.service" in source
    assert "Requires=docker.service" in source
    assert "User=ragdehl" in source
    assert "ExecStart=/home/ragdehl/.local/libexec/odyssey-container-dns-reconcile" in source
    assert "Restart=no" in source
    assert "TimeoutStartSec=180" in source
    assert "odyssey-container-dns-reconcile" in source


def test_recreate_command_is_narrow_and_never_pulls() -> None:
    result = run_bash(
        """
compose_cmd() { printf '%s\\n' "$*"; }
compose_recreate cloudflared
"""
    )
    assert result.returncode == 0
    assert result.stdout == "up -d --no-deps --force-recreate --pull never cloudflared\n"


def test_unexpected_service_fails_closed_without_compose_call() -> None:
    result = run_bash(
        """
compose_cmd() { printf 'unexpected-compose-call\\n'; }
compose_recreate odyssey-dev-n8n
"""
    )
    assert result.returncode != 0
    assert result.stdout == ""
    assert "unexpected service=odyssey-dev-n8n" in result.stderr


def test_unexpected_compose_identity_fails_closed_before_assessment() -> None:
    result = run_bash(
        """
compose_cmd() { printf 'cloudflared\\nn8n\\nother-service\\n'; }
container_identity_valid() { :; }
run_guard
"""
    )
    assert result.returncode != 0
    assert "compose identity mismatch" in result.stderr
    assert "recreate:" not in result.stdout
