"""Trusted host packet makes reviews possible without relying on agent shell."""

import subprocess

import pytest

from scripts import odyssey_agent_cycle as cycle


def fixture(tmp_path):
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    (repo / "tests/runtime").mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@invalid.example"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Local Fixture"], cwd=repo, check=True)
    (repo / "scripts/odyssey_agent_cycle.py").write_text(
        "def a_real_helper(value):\n    return value + 1\n"
    )
    test = repo / "tests/runtime/test_agent_cycle_supervisor.py"
    test.write_text("def test_base():\n    assert True\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "base"], cwd=repo, check=True)
    baseline = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()
    test.write_text(
        "from scripts import odyssey_agent_cycle as cycle\n"
        "def test_helper():\n"
        "    assert cycle.a_real_helper(4) == 5\n"
    )
    return repo, {
        "baseline_commit": baseline,
        "acceptance_profile": "tooling",
        "risk": "normal",
    }


def passing_gates():
    return {
        "cross_surface": {"pass": True, "exit_code": 0},
        "acceptance": {"pass": True, "exit_code": 0},
        "ruff": {"pass": True, "exit_code": 0},
    }


def test_review_packet_contains_real_pinned_diff_helper_and_host_gates(tmp_path):
    repo, state = fixture(tmp_path)
    before = cycle.review_snapshot(repo)
    packet = cycle.bounded_reviewer_evidence(repo, state, passing_gates())
    assert "Pinned Git diff" in packet
    assert "+    assert cycle.a_real_helper(4) == 5" in packet
    assert "def a_real_helper(value)" in packet
    assert '"cross_surface": {"exit_code": 0, "pass": true}' in packet
    assert state["baseline_commit"] in packet
    assert before.hex() in packet
    assert "read-only" in packet
    assert cycle.review_snapshot(repo) == before


def test_review_packet_contains_safe_untracked_text(tmp_path):
    repo, state = fixture(tmp_path)
    (repo / "tests/runtime/new_file.py").write_text("VALUE = 42\n")
    packet = cycle.bounded_reviewer_evidence(repo, state, passing_gates())
    assert "UNTRACKED SOURCE tests/runtime/new_file.py:" in packet
    assert "VALUE = 42" in packet


@pytest.mark.parametrize(
    "tamper",
    [
        "bad_gate",
        "missing_gate",
        "fake_sha",
        "oversized",
        "binary",
        "symlink",
        "helper_symlink",
        "unsafe_kind",
    ],
)
def test_review_packet_fails_closed_on_invalid_evidence(tmp_path, tamper):
    repo, state = fixture(tmp_path)
    gates = passing_gates()
    if tamper == "bad_gate":
        gates["cross_surface"]["pass"] = False
    elif tamper == "missing_gate":
        gates = {}
    elif tamper == "fake_sha":
        state["baseline_commit"] = "z" * 40
    elif tamper == "oversized":
        (repo / "tests/runtime/test_agent_cycle_supervisor.py").write_text("a = 1\n" * 50000)
    elif tamper == "binary":
        (repo / "tests/runtime/suspicious.py").write_bytes(b"abc\0")
    elif tamper == "symlink":
        (repo / "tests/runtime/suspicious.py").symlink_to("/etc/passwd")
    elif tamper == "helper_symlink":
        helper = repo / "scripts/odyssey_agent_cycle.py"
        helper.unlink()
        helper.symlink_to("/etc/passwd")
    else:
        (repo / "tests/runtime/forbidden.dat").write_text("do not ingest")
    with pytest.raises((cycle.CycleError, OSError)):
        cycle.bounded_reviewer_evidence(repo, state, gates)
