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


def test_production_release_selection_requires_a_full_sha() -> None:
    assert bash("is_full_commit_sha", CURRENT).returncode == 0
    assert bash("is_full_commit_sha", "main").returncode != 0
    assert bash("is_full_commit_sha", CURRENT[:-1]).returncode != 0


def test_cli_dispatch_forwards_the_deployment_argument() -> None:
    result = subprocess.run(
        [
            "bash",
            "-c",
            f'source {SCRIPT}; deploy() {{ printf "count=%s arg=%s\\n" "$#" "$1"; }}; main deploy {CURRENT}',
        ],
        check=False,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0
    assert result.stdout == f"count=1 arg={CURRENT}\n"


def test_cli_deploy_rejects_invalid_argument_counts_without_live_preflight() -> None:
    for arguments in (("deploy",), ("deploy", CURRENT, OTHER)):
        result = subprocess.run(
            ["bash", str(SCRIPT), *arguments], check=False, text=True, capture_output=True
        )
        assert result.returncode != 0
        assert "exactly one full commit SHA" in result.stderr


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
    assert bash("provenance_state", CURRENT, CURRENT, "", "").stdout.strip() == "MATCH"
    assert bash("provenance_state", OTHER, CURRENT, "", "").stdout.strip() == "DRIFT"
    assert bash("provenance_state", "", CURRENT, "", "").stdout.strip() == "UNKNOWN"


def test_health_contract_is_private_production_endpoint() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert "PROD_HOST=172.18.0.1" in source
    assert "PROD_PORT=8765" in source
    assert '"http://$PROD_HOST:$PROD_PORT/healthz"' in source


def test_source_contract_uses_the_established_explicit_worktree() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert 'git --git-dir="$git_dir" worktree add --detach "$release" "$resolved"' in source
    assert 'git -C "$release" checkout --detach "$resolved"' in source
    assert "production release worktree is dirty" in source
    assert "PYTHON=/home/ragdehl/projects/odyssey-prod-venv/bin/python" in source
    assert "production deploy requires exactly one full commit SHA" in source
    assert 'main "$@"' in source


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
    assert "WorkingDirectory=/home/ragdehl/projects/odyssey-prod-release" in service
    assert (
        "ExecStart=/home/ragdehl/projects/odyssey-prod-release/scripts/odyssey-prod runtime"
        in service
    )


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


def test_failed_candidate_cannot_replace_stable_control_operator(tmp_path: Path) -> None:
    """A candidate is not the rollback control path until health succeeds."""
    source = tmp_path / "source-operator"
    stable = tmp_path / "libexec" / "odyssey-prod"
    target = tmp_path / "bin" / "odyssey-prod"
    source.write_text("known-good\n", encoding="utf-8")
    subprocess.run(
        ["bash", "-c", f"source {SCRIPT}; ensure_control_operator {source} {stable} {target}"],
        check=True,
    )
    candidate = tmp_path / "candidate-operator"
    candidate.write_text("failed-candidate\n", encoding="utf-8")
    result = subprocess.run(
        ["bash", "-c", f"source {SCRIPT}; ensure_control_operator {candidate} {stable} {target}"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert stable.read_text(encoding="utf-8") == "known-good\n"
    assert target.is_symlink()
    assert target.resolve() == stable


def test_dirty_human_checkout_is_untouched_while_release_moves_between_commits(
    tmp_path: Path,
) -> None:
    """Materialization must use the actual bare-store-plus-files topology."""
    human = tmp_path / "human"
    bare = human / ".git"
    release = tmp_path / "release"
    seed = tmp_path / "seed"
    subprocess.run(["git", "init", "--bare", str(bare)], check=True, capture_output=True, text=True)
    subprocess.run(["git", "init", str(seed)], check=True, capture_output=True, text=True)
    seed_git = ["git", "-C", str(seed)]
    subprocess.run([*seed_git, "config", "user.name", "Test"], check=True)
    subprocess.run([*seed_git, "config", "user.email", "test@example.invalid"], check=True)
    (seed / "release.txt").write_text("A\n", encoding="utf-8")
    subprocess.run([*seed_git, "add", "release.txt"], check=True)
    subprocess.run([*seed_git, "commit", "-m", "A"], check=True, capture_output=True, text=True)
    subprocess.run([*seed_git, "remote", "add", "origin", str(bare)], check=True)
    subprocess.run(
        [*seed_git, "push", "origin", "HEAD:refs/heads/main"],
        check=True,
        capture_output=True,
        text=True,
    )
    (seed / "release.txt").write_text("B\n", encoding="utf-8")
    subprocess.run([*seed_git, "commit", "-am", "B"], check=True, capture_output=True, text=True)
    subprocess.run(
        [*seed_git, "push", "origin", "HEAD:refs/heads/main"],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["git", "--git-dir", str(bare), "symbolic-ref", "HEAD", "refs/heads/main"], check=True
    )
    git = ["git", "-c", "core.bare=false", "--git-dir", str(bare), "--work-tree", str(human)]
    commit_b = subprocess.check_output([*git, "rev-parse", "HEAD"], text=True).strip()
    commit_a = subprocess.check_output([*git, "rev-parse", "HEAD~1"], text=True).strip()
    assert bash("resolve_commit", str(bare), commit_b).stdout.strip() == commit_b
    assert bash("resolve_commit", str(bare), "main").returncode != 0
    subprocess.run([*git, "read-tree", commit_b], check=True)
    subprocess.run([*git, "checkout-index", "--all"], check=True)
    (human / "release.txt").write_text("B\n", encoding="utf-8")
    (human / "release.txt").write_text("human unstaged\n", encoding="utf-8")
    (human / "human-staged.txt").write_text("staged\n", encoding="utf-8")
    subprocess.run([*git, "add", "human-staged.txt"], check=True)
    before_status = subprocess.check_output([*git, "status", "--porcelain"], text=True)
    before_head = subprocess.check_output(
        ["git", "--git-dir", str(bare), "symbolic-ref", "HEAD"], text=True
    )
    assert (
        subprocess.check_output(
            ["git", "-C", str(human), "rev-parse", "--is-bare-repository"], text=True
        ).strip()
        == "true"
    )

    result = bash(
        "materialize_release",
        str(bare),
        str(release),
        commit_b,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == commit_b
    assert (release / "release.txt").read_text(encoding="utf-8") == "B\n"
    assert (
        subprocess.check_output(["git", "-C", str(release), "rev-parse", "HEAD"], text=True).strip()
        == commit_b
    )
    assert subprocess.check_output([*git, "status", "--porcelain"], text=True) == before_status
    assert (
        subprocess.check_output(["git", "--git-dir", str(bare), "symbolic-ref", "HEAD"], text=True)
        == before_head
    )

    result = bash("materialize_release", str(bare), str(release), commit_a)
    assert result.returncode == 0, result.stderr
    assert (release / "release.txt").read_text(encoding="utf-8") == "A\n"
    assert subprocess.check_output([*git, "status", "--porcelain"], text=True) == before_status
    assert (
        subprocess.check_output(["git", "--git-dir", str(bare), "symbolic-ref", "HEAD"], text=True)
        == before_head
    )
