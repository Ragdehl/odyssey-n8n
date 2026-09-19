"""Deterministic tests for the production container DNS reconciliation guard."""

from __future__ import annotations

import json
import os
import shlex
import subprocess
from pathlib import Path

import pytest

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
        [
            "bash",
            "-c",
            f"""
source {shlex.quote(str(SCRIPT))}
# Fail closed if a harness accidentally falls through to a live command.
docker() {{ return 99; }}
curl() {{ return 99; }}
getent() {{ return 99; }}
bounded_command() {{ shift; "$@"; }}
host_resolvers() {{ printf '192.168.1.254\\n'; }}
RESOLVER_STABILIZATION_DELAY_SECONDS=0
{script}
""",
        ],
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


def resolver_stabilization_harness(container_resolvers: str) -> str:
    """Return real assessment fixtures around synthetic host resolver observations."""
    return f"""
validate_scope() {{ :; }}
getent() {{ return 0; }}
wait_for_startup_readiness() {{ :; }}
container_external_resolvers() {{ printf '%b\\n' {shlex.quote(container_resolvers)}; }}
cloudflared_started_at() {{ printf 'fixture-start\\n'; }}
cloudflared_logs() {{ printf 'Registered tunnel connection\\n'; }}
n8n_dns_ready() {{ return 0; }}
curl() {{ return 0; }}
n8n_mount_fingerprint() {{ printf 'fixture-mount\\n'; }}
compose_recreate() {{ printf 'recreate:%s\\n' "$1"; }}
wait_for_target() {{ return 0; }}
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
wait_for_target() {
  if [ "$1" = cloudflared ]; then
    sleep 1
  fi
  return 0
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
    assert "host resolver evidence did not stabilize with healthy DNS" in result.stderr


def test_already_stable_resolvers_follow_normal_healthy_path() -> None:
    result = run_bash(
        resolver_stabilization_harness("192.0.2.53")
        + """
host_resolvers() { printf '192.0.2.53\n'; }
run_guard
"""
    )
    assert result.returncode == 0, result.stderr
    assert "recreate:" not in result.stdout
    assert "host_resolvers_stable samples=3" in result.stderr
    assert result.stderr.count("[HEALTHY]") == 2


def test_real_stable_resolver_change_can_recover_stale_targets() -> None:
    result = run_bash(
        resolver_stabilization_harness("192.0.2.1")
        + """
host_resolvers() { printf '192.0.2.53\n'; }
run_guard
"""
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["recreate:cloudflared", "recreate:n8n"]
    assert result.stderr.count("[RECOVERED]") == 2


def test_resolver_change_after_assessment_blocks_every_recreation() -> None:
    result = run_bash(
        resolver_stabilization_harness("192.0.2.1")
        + """
phase=stable
host_resolvers() {
  if [ "$phase" = stable ]; then printf '192.0.2.53\n'; else printf '192.0.2.54\n'; fi
}
assess_target() { REASON='stale test state'; phase=changed; return 10; }
run_guard
"""
    )
    assert result.returncode == 1
    assert "recreate:" not in result.stdout
    assert result.stderr.count("stable host resolver evidence changed") == 2


def test_transient_a_b_c_waits_for_c_and_never_recovers_from_b() -> None:
    result = run_bash(
        resolver_stabilization_harness("192.0.2.3")
        + """
RESOLVER_STABILIZATION_DELAY_SECONDS=1
host_resolvers() {
  case "$SECONDS" in
    0) printf '192.0.2.1\n' ;;
    1) printf '192.0.2.2\n' ;;
    *) printf '192.0.2.3\n' ;;
  esac
}
sleep() { SECONDS=$((SECONDS + $1)); }
SECONDS=0
run_guard
"""
    )
    assert result.returncode == 0, result.stderr
    assert "recreate:" not in result.stdout
    assert "observed=192.0.2.2" in result.stderr
    assert "host_resolvers_stable samples=3 observed=192.0.2.3" in result.stderr


def test_oscillating_resolvers_fail_closed_without_recreation() -> None:
    result = run_bash(
        resolver_stabilization_harness("192.0.2.1")
        + """
RESOLVER_STABILIZATION_DELAY_SECONDS=1
RESOLVER_STABILIZATION_ATTEMPTS=6
host_resolvers() {
  if [ $((SECONDS % 2)) -eq 0 ]; then printf '192.0.2.1\n'; else printf '192.0.2.2\n'; fi
}
sleep() { SECONDS=$((SECONDS + $1)); }
SECONDS=0
run_guard
"""
    )
    assert result.returncode == 1
    assert "recreate:" not in result.stdout
    assert "did not stabilize" in result.stderr


def test_ipv4_then_ipv6_waits_for_complete_stable_set() -> None:
    complete = "192.0.2.53\\n2001:db8::53"
    result = run_bash(
        resolver_stabilization_harness(complete)
        + """
RESOLVER_STABILIZATION_DELAY_SECONDS=1
host_resolvers() {
  if [ "$SECONDS" -eq 0 ]; then
    printf '192.0.2.53\n'
  else
    printf '192.0.2.53\n2001:db8::53\n'
  fi
}
sleep() { SECONDS=$((SECONDS + $1)); }
SECONDS=0
run_guard
"""
    )
    assert result.returncode == 0, result.stderr
    assert "recreate:" not in result.stdout
    assert "host_resolvers_stable samples=3" in result.stderr
    assert "2001:db8::53" in result.stderr


@pytest.mark.parametrize(
    "resolver_fixture",
    ["host_resolvers() { return 1; }", "host_resolvers() { printf ''; }"],
)
def test_malformed_or_empty_host_resolvers_fail_closed(
    resolver_fixture: str,
) -> None:
    result = run_bash(
        resolver_stabilization_harness("192.0.2.53")
        + resolver_fixture
        + """
RESOLVER_STABILIZATION_ATTEMPTS=3
run_guard
"""
    )
    assert result.returncode == 1
    assert "recreate:" not in result.stdout
    assert "observed=unavailable" in result.stderr


def test_stabilization_timeout_fails_closed_with_deterministic_diagnostic() -> None:
    result = run_bash(
        resolver_stabilization_harness("192.0.2.1")
        + """
RESOLVER_STABILIZATION_DELAY_SECONDS=1
RESOLVER_STABILIZATION_ATTEMPTS=4
host_resolvers() { printf '192.0.2.%s\n' "$((SECONDS + 1))"; }
sleep() { SECONDS=$((SECONDS + $1)); }
SECONDS=0
run_guard
"""
    )
    assert result.returncode == 1
    assert "recreate:" not in result.stdout
    assert "attempt=4/4" in result.stderr
    assert "host resolver evidence did not stabilize with healthy DNS" in result.stderr


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
bounded_command() { printf '%s\\n' "$*"; }
compose_recreate cloudflared
"""
    )
    assert result.returncode == 0
    assert result.stdout == (
        "45 docker compose --file /home/ragdehl/docker/n8n/compose.yaml "
        "up -d --no-deps --force-recreate --pull never cloudflared\n"
    )


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


@pytest.mark.parametrize("separator", [" ", ", ", ",", "  "])
def test_real_docker_external_resolver_formats(separator: str) -> None:
    upstream = separator.join(
        ["host(192.168.1.254)", "host(2001:861:4010:1960:6e15:dbff:fef0:125c)"]
    )
    result = run_bash(f"""
docker_cmd() {{ printf '%s\\n' '# ExtServers: [{upstream}]'; }}
tar() {{ cat; }}
container_external_resolvers n8n
""")
    assert result.returncode == 0
    assert result.stdout.splitlines() == [
        "192.168.1.254",
        "2001:861:4010:1960:6e15:dbff:fef0:125c",
    ]


@pytest.mark.parametrize("upstream", ["", "garbage", "host(192.168.1.254) garbage"])
def test_unparseable_resolvers_are_unknown_not_stale(upstream: str) -> None:
    result = run_bash(f"""
docker_cmd() {{ printf '%s\\n' '# ExtServers: [{upstream}]'; }}
tar() {{ cat; }}
assess_target n8n
""")
    assert result.returncode == 20


def readiness_fixture() -> str:
    """Provide real predicate evaluation with synthetic time and no live commands."""
    return """
validate_scope() { :; }
host_dns_healthy() { :; }
wait_for_startup_readiness() { :; }
assess_target() { REASON=stale; return 10; }
compose_recreate() { printf 'recreate:%s\\n' "$1"; }
container_external_resolvers() { host_resolvers; }
cloudflared_started_at() { printf 'fixture-start\\n'; }
cloudflared_logs() { printf 'Registered tunnel connection\\n'; }
n8n_mount_fingerprint() { printf 'fixture-mount\\n'; }
n8n_dns_ready() { return 0; }
curl() { printf 200; }
sleep() { SECONDS=$((SECONDS + $1)); }
"""


def test_both_delayed_targets_have_overlapping_full_readiness_windows() -> None:
    result = run_bash(
        readiness_fixture()
        + """
SECONDS=0
cloudflared_logs() {
  if [ "$SECONDS" -ge 100 ]; then printf 'Registered tunnel connection\\n'; fi
}
n8n_dns_ready() { [ "$SECONDS" -ge 110 ]; }
curl() { if [ "$SECONDS" -ge 130 ]; then printf 200; else printf 503; fi; }
run_guard
"""
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["recreate:cloudflared", "recreate:n8n"]
    assert "[RECOVERED] service=cloudflared" in result.stderr
    assert "[RECOVERED] service=n8n" in result.stderr
    assert "[FAILED]" not in result.stderr


@pytest.mark.parametrize(
    ("failure", "diagnostic"),
    [
        ("container_external_resolvers() { printf '10.235.35.170\\n'; }", "resolver_match=FAIL"),
        ("n8n_dns_ready() { return 1; }", "dns_api_openai=FAIL healthz=200"),
        ("curl() { printf 503; }", "dns_api_openai=PASS healthz=503"),
        (
            "cloudflared_logs() { printf 'Registered tunnel connection\\nlookup foo i/o timeout\\n'; }",
            "last_dns_error=2 last_registration=1 registration_ready=FAIL",
        ),
        ("cloudflared_logs() { return 1; }", "logs=unavailable registration_ready=FAIL"),
    ],
)
def test_timeout_identifies_independent_failing_predicate(failure: str, diagnostic: str) -> None:
    result = run_bash(readiness_fixture() + failure + "\nrun_guard")
    assert result.returncode == 1
    assert diagnostic in result.stderr
    assert "expected=192.168.1.254 observed=" in result.stderr
    assert "readiness=timeout" in result.stderr
    assert result.stdout.count("recreate:cloudflared") == 1
    assert result.stdout.count("recreate:n8n") == 1


MOUNTS = [
    {"Type": "bind", "Source": "/release/web", "Destination": "/odyssey-web", "RW": False},
    {
        "Type": "volume",
        "Name": "n8n_data",
        "Source": "/volumes/n8n_data/_data",
        "Destination": "/home/node/.n8n",
        "RW": True,
    },
]


def mount_fixture(before: list[dict], after: list[dict]) -> str:
    """Use actual JSON normalization on synthetic inspect records across recreation."""
    return f"""
mounts={shlex.quote(json.dumps(before))}
docker_cmd() {{ printf '%s\\n' "$mounts"; }}
compose_recreate() {{
  printf 'recreate:%s\\n' "$1"
  mounts={shlex.quote(json.dumps(after))}
}}
"""


def test_mount_order_and_missing_optional_fields_are_stable() -> None:
    before = [dict(mount) for mount in MOUNTS]
    before[0]["Mode"] = "ro,z"
    after = [dict(mount) for mount in reversed(before)]
    after[1].update(Mode="z,ro", Name="", Driver="", Propagation="")
    result = run_bash(
        mount_fixture(before, after)
        + """
before=$(n8n_mount_fingerprint)
compose_recreate n8n >/dev/null
after=$(n8n_mount_fingerprint)
[ "$before" = "$after" ]
printf '%s\\n' "$after"
"""
    )
    assert result.returncode == 0
    assert len(result.stdout.splitlines()) == 2


@pytest.mark.parametrize(
    "field,value",
    [
        ("Source", "/unexpected/web"),
        ("RW", True),
        ("Destination", "/unexpected"),
        ("Propagation", "rshared"),
    ],
)
def test_actual_mount_drift_fails_closed_and_reports_changed_field(
    field: str, value: object
) -> None:
    after = [dict(mount) for mount in MOUNTS]
    after[0][field] = value
    # Keep real fingerprint implementation, while stubbing every external boundary.
    fixture = readiness_fixture().replace(
        "n8n_mount_fingerprint() { printf 'fixture-mount\\n'; }", ""
    )
    result = run_bash(
        fixture
        + mount_fixture(MOUNTS, after)
        + """
assess_target() { REASON=stale; [ "$1" = n8n ] && return 10; return 0; }
run_guard
"""
    )
    assert result.returncode == 1
    assert result.stdout == "recreate:n8n\n"
    assert "mounts=FAIL" in result.stderr
    assert "mount_diff=" in result.stderr
    assert field in result.stderr
    assert "mount configuration changed" in result.stderr


def test_budget_caps_external_commands_and_leaves_terminal_margin() -> None:
    # Exercise the real wrapper with a fake timeout; never call an external service.
    result = subprocess.run(
        [
            "bash",
            "-c",
            f"""
source {shlex.quote(str(SCRIPT))}
SECONDS=0
GUARD_DEADLINE=2
timeout() {{ printf '%s\\n' "$*"; }}
bounded_command 45 fixture-command
SECONDS=3
if bounded_command 5 fixture-command; then exit 1; fi
[ "$GUARD_WINDOW_SECONDS" -eq 165 ]
[ "$RESOLVER_STABILIZATION_SAMPLES" -eq 3 ]
[ "$RESOLVER_STABILIZATION_ATTEMPTS" -eq 8 ]
[ "$RESOLVER_STABILIZATION_DELAY_SECONDS" -eq 2 ]
[ $(((RESOLVER_STABILIZATION_ATTEMPTS - 1) * RESOLVER_STABILIZATION_DELAY_SECONDS)) -eq 14 ]
""",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert result.stdout == "--signal=TERM --kill-after=1 2 fixture-command\n"
    assert "TimeoutStartSec=180" in SERVICE.read_text()


def test_healthy_dual_stack_docker_upstreams_do_not_authorize_recreation() -> None:
    result = run_bash("""
host_resolvers() { printf '192.168.1.254\\n2001:db8::1\\n'; }
docker_cmd() { printf '# ExtServers: [host(192.168.1.254) host(2001:0db8:0:0:0:0:0:1)]\\n'; }
tar() { cat; }
n8n_dns_ready() { return 0; }
curl() { return 0; }
cloudflared_started_at() { printf fixture; }
cloudflared_logs() { printf 'Registered tunnel connection\\n'; }
assess_target cloudflared
assess_target n8n
""")
    assert result.returncode == 0, result.stderr


def test_real_stale_upstream_remains_stale() -> None:
    result = run_bash("""
docker_cmd() { printf '# ExtServers: [host(10.235.35.170)]\\n'; }
tar() { cat; }
assess_target n8n
""")
    assert result.returncode == 10


def test_stable_reordered_mounts_recover_successfully() -> None:
    fixture = readiness_fixture().replace(
        "n8n_mount_fingerprint() { printf 'fixture-mount\\n'; }", ""
    )
    result = run_bash(fixture + mount_fixture(MOUNTS, list(reversed(MOUNTS))) + "run_guard")
    assert result.returncode == 0, result.stderr
    assert "[RECOVERED] service=n8n" in result.stderr
    assert "mount_diff" not in result.stderr


def test_missing_mount_evidence_prevents_n8n_recreation() -> None:
    result = run_bash(
        readiness_fixture()
        + """
n8n_mount_fingerprint() { return 1; }
run_guard
"""
    )
    assert result.returncode == 1
    assert "recreate:n8n" not in result.stdout
    assert "mounts=unavailable before recreation" in result.stderr


def test_cloudflared_error_order_is_consumed_without_pipefail_sigpipe() -> None:
    result = run_bash("""
cloudflared_logs() {
  printf 'lookup foo server misbehaving\\n'
  for i in {1..2000}; do printf 'padding line\\n'; done
  printf 'Registered tunnel connection\\n'
}
cloudflared_dns_error fixture
cloudflared_registered_after_last_dns_error fixture
""")
    assert result.returncode == 0


def test_failed_scope_inspection_cannot_authorize_recovery_from_partial_output() -> None:
    result = run_bash("""
compose_cmd() { printf 'cloudflared\\nn8n\\n'; return 124; }
container_identity_valid() { return 0; }
run_guard
""")
    assert result.returncode == 1
    assert "compose identity unavailable" in result.stderr
    assert "RECOVERING" not in result.stderr


def test_failed_host_resolver_read_is_not_healthy_despite_partial_output() -> None:
    result = run_bash("""
host_resolvers() { printf '192.168.1.254\\n'; return 1; }
getent() { return 0; }
host_dns_healthy
""")
    assert result.returncode == 1
