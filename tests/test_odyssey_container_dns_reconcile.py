"""Deterministic tests for the production container DNS reconciliation guard."""

from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "scripts" / "odyssey-container-dns-reconcile"
SERVICE = Path(__file__).parents[1] / "deploy" / "odyssey-container-dns-reconcile.service"
DISPATCHER = (
    Path(__file__).parents[1]
    / "deploy"
    / "NetworkManager"
    / "dispatcher.d"
    / "90-odyssey-container-dns-reconcile"
)


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
    assert "[RECOVERED] service=cloudflared" in result.stderr
    assert "[RECOVERED] service=n8n" in result.stderr


def test_delayed_cloudflared_recovery_does_not_skip_n8n() -> None:
    result = run_bash(
        """
validate_scope() { :; }
host_dns_healthy() { return 0; }
wait_for_startup_readiness() { :; }
n8n_mount_fingerprint() { printf 'volume|n8n_data|/home/node/.n8n|true\\n'; }
assess_target() { REASON='stale test state'; return 10; }
compose_recreate() { printf 'recreate:%s\\n' "$1"; }
cloudflared_ready=0
wait_for_target() {
  if [ "$1" = cloudflared ]; then
    sleep 1
    cloudflared_ready=1
  else
    [ "$cloudflared_ready" -eq 1 ]
  fi
}
sleep() { [ "$1" -eq 1 ]; }
run_guard
"""
    )
    assert result.returncode == 0
    assert result.stdout.splitlines() == ["recreate:cloudflared", "recreate:n8n"]
    assert result.stderr.index("service=cloudflared") < result.stderr.index("service=n8n")
    assert "[RECOVERED] service=cloudflared" in result.stderr
    assert "[RECOVERED] service=n8n" in result.stderr


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
n8n_service_ready() { return 0; }
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


def test_n8n_health_appears_during_startup_grace_without_recreation() -> None:
    result = run_bash(
        """
validate_scope() { :; }
host_dns_healthy() { return 0; }
container_running() { return 0; }
resolvers_match_host() { return 0; }
cloudflared_started_at() { printf 'started\n'; }
cloudflared_registered() { return 0; }
n8n_service_ready() {
  n8n_checks=$((n8n_checks + 1))
  [ "$n8n_checks" -ge 2 ]
}
n8n_checks=0
sleep() { :; }
assess_target() { REASON='healthy test state'; return 0; }
compose_recreate() { printf 'recreate:%s\n' "$1"; }
run_guard
"""
    )
    assert result.returncode == 0
    assert result.stdout == ""
    assert "service=n8n awaiting resolver, DNS, and health readiness" in result.stderr
    assert "[HEALTHY] service=n8n" in result.stderr


def test_n8n_transient_dns_or_health_failure_then_ready_has_no_recreation() -> None:
    result = run_bash(
        """
validate_scope() { :; }
host_dns_healthy() { return 0; }
container_running() { return 0; }
resolvers_match_host() { return 0; }
cloudflared_started_at() { printf 'started\n'; }
cloudflared_registered() { return 0; }
dns_checks=0
n8n_dns_ready() {
  dns_checks=$((dns_checks + 1))
  [ "$dns_checks" -ge 2 ]
}
health_checks=0
curl() {
  health_checks=$((health_checks + 1))
  [ "$health_checks" -ge 2 ]
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
    assert "[HEALTHY] service=n8n" in result.stderr


def test_stale_cloudflared_does_not_suppress_n8n_startup_grace() -> None:
    result = run_bash(
        """
validate_scope() { :; }
host_dns_healthy() { return 0; }
container_running() { return 0; }
resolvers_match_host() {
  [ "$1" = cloudflared ] && return 1
  return 0
}
cloudflared_started_at() { printf 'started\n'; }
cloudflared_registered() { return 0; }
n8n_service_ready() {
  n8n_checks=$((n8n_checks + 1))
  [ "$n8n_checks" -ge 2 ]
}
n8n_checks=0
sleep() { :; }
assess_target() {
  if [ "$1" = cloudflared ]; then
    REASON='stale cloudflared test state'
    return 10
  fi
  REASON='healthy n8n test state'
  return 0
}
n8n_mount_fingerprint() { printf 'volume|n8n_data|/home/node/.n8n|true\n'; }
compose_recreate() { printf 'recreate:%s\n' "$1"; }
wait_for_target() { return 0; }
run_guard
"""
    )
    assert result.returncode == 0
    assert result.stdout == "recreate:cloudflared\n"
    assert "recreate:n8n" not in result.stdout
    assert "[HEALTHY] service=n8n" in result.stderr


def test_n8n_startup_grace_timeout_fails_without_stale_dns_recreation() -> None:
    result = run_bash(
        """
validate_scope() { :; }
host_dns_healthy() { return 0; }
container_running() { return 0; }
resolvers_match_host() { return 0; }
cloudflared_started_at() { printf 'started\n'; }
cloudflared_registered() { return 0; }
n8n_service_ready() { return 1; }
STARTUP_GRACE_ATTEMPTS=3
sleep() { :; }
assess_target() {
  if [ "$1" = n8n ]; then
    printf 'unexpected-assessment:%s\n' "$1"
    return 10
  fi
  return 0
}
compose_recreate() { printf 'recreate:%s\n' "$1"; }
run_guard
"""
    )
    assert result.returncode != 0
    assert result.stdout == ""
    assert "unexpected-assessment:n8n" not in result.stdout
    assert "service=n8n" in result.stderr
    assert "without stale DNS proof; no recreation" in result.stderr


def test_transient_cloudflared_dns_error_before_registration_is_healthy() -> None:
    result = run_bash(
        """
validate_scope() { :; }
host_dns_healthy() { return 0; }
wait_for_startup_readiness() { :; }
resolvers_match_host() { return 0; }
cloudflared_started_at() { printf 'started\n'; }
cloudflared_logs() {
  printf '%s\n' \
    'lookup api.cloudflare.com on 127.0.0.11:53: server misbehaving' \
    'Registered tunnel connection conn=abc'
}
eval "$(declare -f assess_target | sed 's/^assess_target /real_assess_target /')"
assess_target() {
  if [ "$1" = n8n ]; then REASON='healthy n8n test state'; return 0; fi
  real_assess_target "$1"
}
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


def run_dispatcher(interface: str, action: str, tmp_path: Path) -> list[str]:
    """Run the dispatcher with a fake systemctl and return submitted arguments."""
    fake_bin = tmp_path / f"bin-{interface}-{action}"
    fake_bin.mkdir(parents=True)
    calls = tmp_path / f"calls-{interface}-{action}"
    fake_systemctl = fake_bin / "systemctl"
    fake_systemctl.write_text(
        '#!/bin/sh\nprintf \'%s\\n\' "$*" >> "$DISPATCHER_CALLS"\n',
        encoding="utf-8",
    )
    fake_systemctl.chmod(0o755)
    environment = os.environ | {
        "PATH": str(fake_bin),
        "DISPATCHER_CALLS": str(calls),
    }
    result = subprocess.run(
        [str(DISPATCHER), interface, action],
        check=False,
        env=environment,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    return calls.read_text(encoding="utf-8").splitlines() if calls.exists() else []


def test_dispatcher_submits_only_existing_guard_asynchronously(tmp_path: Path) -> None:
    calls = run_dispatcher("wlan0", "dns-change", tmp_path)
    assert calls == ["start --no-block odyssey-container-dns-reconcile.service"]
    source = DISPATCHER.read_text(encoding="utf-8")
    assert "docker" not in source.lower()
    assert "nmcli" not in source.lower()
    assert "resolv" not in source.lower()
    assert "timeout" not in source.lower()


def test_dispatcher_repeated_relevant_events_are_guard_only(tmp_path: Path) -> None:
    first = run_dispatcher("wlan0", "up", tmp_path)
    second = run_dispatcher("wlan0", "dhcp4-change", tmp_path)
    assert first == ["start --no-block odyssey-container-dns-reconcile.service"]
    assert second == ["start --no-block odyssey-container-dns-reconcile.service"]


def test_dispatcher_ignores_irrelevant_events(tmp_path: Path) -> None:
    assert run_dispatcher("wlan0", "down", tmp_path) == []
    assert run_dispatcher("eth0", "pre-up", tmp_path) == []


def test_dispatcher_covers_future_wired_and_resolver_events(tmp_path: Path) -> None:
    for action in ("up", "dhcp6-change", "connectivity-change", "vpn-up"):
        assert run_dispatcher("eth0", action, tmp_path) == [
            "start --no-block odyssey-container-dns-reconcile.service"
        ]


def test_dispatcher_preserves_guard_execution_bound() -> None:
    service = SERVICE.read_text(encoding="utf-8")
    dispatcher = DISPATCHER.read_text(encoding="utf-8")
    assert "TimeoutStartSec=180" in service
    assert "--no-block" in dispatcher
    assert "timeout" not in dispatcher.lower()


def test_n8n_stale_resolver_still_reaches_existing_single_service_recovery() -> None:
    result = run_bash(
        """
validate_scope() { :; }
host_dns_healthy() { return 0; }
wait_for_startup_readiness() { N8N_STARTUP_STATE=stale; :; }
assess_target() { REASON='stale test state'; [ "$1" = n8n ] && return 10 || return 0; }
compose_recreate() { printf 'recreate:%s\n' "$1"; }
wait_for_target() { return 0; }
n8n_mount_fingerprint() { printf 'volume|n8n_data|/home/node/.n8n|true\n'; }
run_guard
"""
    )
    assert result.returncode == 0
    assert result.stdout == "recreate:n8n\n"
    assert result.stdout.count("recreate:") == 1


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
