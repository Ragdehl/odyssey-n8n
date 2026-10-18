#!/usr/bin/env python3
"""Odyssey bounded, local Codex agent team. Never deploys or merges.

Usage:
  python scripts/odyssey_agent_cycle.py doctor
  python scripts/odyssey_agent_cycle.py plan --spec <markdown> --job <slug>
  python scripts/odyssey_agent_cycle.py plan --spec <markdown> --job <slug> --implemented-by chatgpt --against <commit>
  python scripts/odyssey_agent_cycle.py run --job <slug> --live
  python scripts/odyssey_agent_cycle.py status --job <slug>
  python scripts/odyssey_agent_cycle.py stop --job <slug>

No unattended executions occur without explicit --live, and every run creates
an isolated git worktree. Default modes are read-only/dry-run.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROLES = ROOT / "ops/agent-team"
STATE = ROOT.parent / ".odyssey-agent-runs"
SCHEMA = ROLES / "review.schema.json"
MODEL_POLICY = ROLES / "model-policy.json"
CHECKOUT_EXCLUDE = ("odyssey-dev", "odyssey-prod-release", "odyssey-prod-venv")
REVIEW_ROLES = ("generality", "quality", "testing", "performance")
ACCEPTANCE_PROFILES = {
    "product": {"ready_phase": "reviewed_browser_gate_pending", "ready_for_user": False},
    "tooling": {"ready_phase": "reviewed_tooling_ready", "ready_for_user": True},
}
TOOLING_PATHS = (
    "scripts/odyssey_agent_cycle.py",
    "tests/runtime/test_agent_cycle_supervisor.py",
    "docs/architecture/agent-team-pilot-20261018.md",
)
TIMEOUT = 1200
MIN_MEMORY_MIB = 650


class CycleError(RuntimeError):
    pass


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def mem_available() -> int:
    for line in Path("/proc/meminfo").read_text().splitlines():
        if line.startswith("MemAvailable:"):
            return int(line.split()[1]) // 1024
    raise CycleError("Cannot verify remaining host memory")


def running(command: list[str], *, cwd: Path | None = None, timeout=30, text=None):
    return subprocess.run(
        command,
        cwd=cwd,
        text=True,
        input=text,
        capture_output=True,
        timeout=timeout,
        check=False,
    )


def check_repository() -> None:
    if not (ROOT / "AGENTS.md").is_file():
        raise CycleError("Not an Odyssey source worktree")
    if not (ROOT / "docs/architecture/functional-roadmap.md").is_file():
        raise CycleError("Canonical roadmap is unavailable")
    if not (ROOT / "docs/architecture/application-extensibility-plan.md").is_file():
        raise CycleError("Core and app contracts are unavailable")
    if not shutil.which("codex"):
        raise CycleError("Codex CLI is not installed")
    result = running(["git", "-C", str(ROOT), "rev-parse", "--is-inside-work-tree"])
    if result.returncode or result.stdout.strip() != "true":
        raise CycleError("Git worktree is required")


def slug(value: str) -> str:
    if not re.fullmatch(r"[a-z][a-z0-9-]{2,38}", value) or (
        value in CHECKOUT_EXCLUDE or value.startswith("prod-")
    ):
        raise CycleError("Job must be safe, bounded and never name production")
    return value


def job_path(job: str) -> Path:
    slug(job)
    return STATE / job


def atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def load(job: str) -> dict:
    path = job_path(job) / "status.json"
    if not path.is_file():
        raise CycleError("No job found; use plan first")
    return json.loads(path.read_text(encoding="utf-8"))


def update(job: str, state: dict, phase: str, **extras) -> None:
    state.update(phase=phase, updated_at=now(), **extras)
    atomic_json(job_path(job) / "status.json", state)


def require_budget(job: str) -> None:
    if (job_path(job) / "STOP").exists():
        raise CycleError("Job was stopped by operator")
    available = mem_available()
    if available < MIN_MEMORY_MIB:
        raise CycleError(f"Memory protection: only {available} MiB available")


def model_policy() -> dict:
    """Load a locally owned, validated model and budget policy."""
    policy = json.loads(MODEL_POLICY.read_text(encoding="utf-8"))
    if policy.get("version") != 1:
        raise CycleError("Unsupported agent model policy")
    allowed_models = {"gpt-6-luna", "gpt-6-sol"}
    levels = policy.get("models", {})
    if set(levels) != {"economy", "standard", "deep"}:
        raise CycleError("Incomplete approved model tiers")
    for tier in levels.values():
        if tier.get("id") not in allowed_models or tier.get("effort") not in {
            "low",
            "medium",
            "high",
        }:
            raise CycleError("Unapproved model or reasoning effort")
    limit = policy.get("default_reported_token_budget")
    if not isinstance(limit, int) or not 20000 <= limit <= 300000:
        raise CycleError("Unsafe or missing token budget")
    headroom = policy.get("minimum_session_headroom")
    if (
        isinstance(headroom, bool)
        or not isinstance(headroom, int)
        or not 10000 <= headroom <= 100000
    ):
        raise CycleError("Unsafe model session headroom budget")
    prefixes = policy.get("architectural_change_prefixes")
    if (
        not isinstance(prefixes, list)
        or not prefixes
        or any(not isinstance(item, str) or not item.endswith("/") for item in prefixes)
    ):
        raise CycleError("Invalid architectural risk classifier")
    if set(policy.get("high_risk_roles", [])) - {"builder", *REVIEW_ROLES}:
        raise CycleError("Unrecognized expensive model role")
    return policy


def touched_paths(dest: Path, base: str) -> tuple[str, ...]:
    """Scope model risk to real source changes; no model-needed classifier."""
    changed = running(["git", "-C", str(dest), "diff", "--name-only", base], timeout=10)
    new = running(
        ["git", "-C", str(dest), "ls-files", "--others", "--exclude-standard"], timeout=10
    )
    if changed.returncode or new.returncode:
        raise CycleError("Cannot inspect agent scope for model risk")
    return tuple(sorted({line for line in (changed.stdout + new.stdout).splitlines() if line}))


def select_agent_model(role: str, state: dict, dest: Path) -> dict:
    """Choose a tier from contract impact, declared risk and repair history."""
    if role not in ("builder", *REVIEW_ROLES):
        raise CycleError("Unexpected agent role")
    policy = model_policy()
    declared = state.get("risk", "normal")
    if declared not in {"normal", "high", "critical"}:
        raise CycleError("Unknown feature risk declaration")
    base = state.get("review_base") or state.get("baseline_commit")
    if not isinstance(base, str) or not re.fullmatch(r"[0-9a-f]{40}", base):
        raise CycleError("Missing immutable source baseline for routing")
    paths = touched_paths(dest, base)
    architectural = any(
        name.startswith(tuple(policy["architectural_change_prefixes"])) for name in paths
    )
    high_risk = declared in {"high", "critical"} or architectural
    repair = int(state.get("round") or 0) > 1
    tier = "economy"
    if (high_risk and role in policy["high_risk_roles"]) or (repair and role == "builder"):
        tier = "standard"
    if (
        declared == "critical"
        and role in policy["high_risk_roles"]
        or (repair and high_risk and role == "builder")
    ):
        tier = "deep"
    selected = policy["models"][tier]
    return {
        "model": selected["id"],
        "effort": selected["effort"],
        "tier": tier,
        "reason": "retry"
        if repair and role == "builder"
        else (
            "contract_change" if architectural else ("declared_risk" if high_risk else "routine")
        ),
        "changed_files_count": len(paths),
    }


def reported_token_count(logfile: Path) -> int | None:
    """Extract CLI accounting, including its internal context; not API billing."""
    if not logfile.exists():
        return None
    with logfile.open("rb") as stream:
        stream.seek(0, 2)
        stream.seek(max(0, stream.tell() - 8192))
        tail = stream.read().decode("utf-8", errors="replace")
    values = re.findall(r"(?m)^tokens used\s*\n([0-9][0-9,]*)\s*$", tail)
    return int(values[-1].replace(",", "")) if values else None


def record_agent_usage(job: str, state: dict, role: str, receipt: dict) -> None:
    """Persist actual per-role usage and stop BEFORE the next model call."""
    if "reported_tokens" not in receipt:
        return  # Mocked offline reviewer in deterministic supervisor tests.
    tokens = receipt["reported_tokens"]
    if not isinstance(tokens, int) or tokens < 0:
        raise CycleError("Codex usage telemetry unavailable; cannot enforce budget")
    ledger = state.setdefault("token_usage", {"reported_total": 0, "sessions": []})
    ledger["reported_total"] += tokens
    ledger["sessions"].append(
        {
            "role": role,
            "round": state.get("round"),
            "model": receipt.get("model"),
            "tier": receipt.get("tier"),
            "reason": receipt.get("routing_reason"),
            "reported_tokens": tokens,
        }
    )
    update(job, state, state["phase"])
    if ledger["reported_total"] > state.get(
        "reported_token_budget", model_policy()["default_reported_token_budget"]
    ):
        raise CycleError("Codex reported-token budget exhausted")


def doctor() -> dict:
    check_repository()
    assert SCHEMA.is_file()
    policy = model_policy()
    for role in ("builder", *REVIEW_ROLES):
        if not (ROLES / (role + ".md")).is_file():
            raise CycleError(f"Role missing: {role}")
    result = running(["codex", "--version"])
    login = running(["codex", "login", "status"])
    return {
        "repository": str(ROOT),
        "model_cli": result.stdout.strip() if result.returncode == 0 else "unavailable",
        "auth_ready": login.returncode == 0,
        "available_ram_mib": mem_available(),
        "serial_model_concurrency": 1,
        "default_live": False,
        "production_deploy_allowed": False,
        "active_roles": ["supervisor", "builder", *REVIEW_ROLES],
        "models": policy["models"],
        "reported_token_budget": policy["default_reported_token_budget"],
    }


def resolve_commit(revision: str) -> str:
    """Accept only existing unambiguous SHAs, never Git option or ref injection."""
    if not isinstance(revision, str) or not re.fullmatch(r"[0-9a-f]{7,40}", revision):
        raise CycleError("Comparison base must be a literal Git SHA")
    result = running(["git", "-C", str(ROOT), "rev-parse", "--verify", revision + "^{commit}"])
    if result.returncode or not re.fullmatch(r"[0-9a-f]{40}\n?", result.stdout):
        raise CycleError("Comparison base must resolve to a local commit")
    return result.stdout.strip()


def tooling_scope_is_safe(worktree: Path, baseline: str) -> bool:
    """Allow tooling readiness only when all changed paths belong to the supervisor.

    Tracked changes are compared with the immutable job baseline; untracked files
    are included because a builder can create files after planning. Unknown paths
    fail closed, including future application directories.
    """
    tracked = running(["git", "diff", "--name-only", "-z", baseline, "--"], cwd=worktree)
    untracked = running(["git", "ls-files", "--others", "--exclude-standard", "-z"], cwd=worktree)
    if tracked.returncode or untracked.returncode:
        return False
    paths = {
        value
        for output in (tracked.stdout, untracked.stdout)
        for value in output.split("\0")
        if value
    }

    def permitted(path: str) -> bool:
        return path in TOOLING_PATHS or path.startswith("ops/agent-team/")

    return bool(paths) and all(permitted(path) for path in paths)


def plan(
    spec: Path,
    job: str,
    *,
    implemented_by: str = "codex",
    against: str | None = None,
    risk: str = "normal",
    token_budget: int | None = None,
    acceptance: str = "product",
) -> dict:
    check_repository()
    slug(job)
    if not spec.is_file() or not spec.resolve().is_relative_to(ROOT):
        raise CycleError("Feature brief must be an existing file inside this source checkout")
    brief = spec.resolve().read_text(encoding="utf-8")
    if not 40 <= len(brief) <= 25000:
        raise CycleError("Feature brief must be 40 to 25000 characters")
    policy = model_policy()
    if risk not in {"normal", "high", "critical"}:
        raise CycleError("Invalid declared impact/risk")
    if token_budget is None:
        token_budget = policy["default_reported_token_budget"]
    if (
        isinstance(token_budget, bool)
        or not isinstance(token_budget, int)
        or not 20000 <= token_budget <= 300000
    ):
        raise CycleError("Token budget must be 20000 to 300000 reported tokens")
    if implemented_by not in {"codex", "chatgpt"}:
        raise CycleError("Only Codex or ChatGPT can be the development source")
    if acceptance not in ACCEPTANCE_PROFILES:
        raise CycleError("Acceptance must be product or tooling")
    if implemented_by == "codex" and against is not None:
        raise CycleError("A comparison base is only meaningful for existing ChatGPT code")
    if implemented_by == "chatgpt" and against is None:
        raise CycleError("ChatGPT handoff requires an explicit committed Git base")
    baseline = running(["git", "-C", str(ROOT), "rev-parse", "HEAD"])
    if baseline.returncode or not re.fullmatch(r"[0-9a-f]{40}\n?", baseline.stdout):
        raise CycleError("Cannot anchor the source commit")
    status = running(["git", "-C", str(ROOT), "status", "--porcelain", "--untracked-files=all"])
    if status.returncode or status.stdout.strip():
        raise CycleError("Handoff requires committed files and a clean Git source snapshot")
    review_base = None
    if against is not None:
        review_base = resolve_commit(against)
        verify = running(
            [
                "git",
                "-C",
                str(ROOT),
                "merge-base",
                "--is-ancestor",
                review_base,
                baseline.stdout.strip(),
            ]
        )
        changed = running(
            [
                "git",
                "-C",
                str(ROOT),
                "diff",
                "--name-only",
                review_base,
                baseline.stdout.strip(),
            ]
        )
        if verify.returncode or changed.returncode or not changed.stdout.strip():
            raise CycleError("Comparison must be an ancestor with committed feature changes")
    run_dir = job_path(job)
    if (run_dir / "status.json").exists():
        raise CycleError("Job already exists: never overwrite evidence or re-run an ID")
    run_dir.mkdir(parents=True, exist_ok=False, mode=0o700)
    (run_dir / "brief.md").write_text(brief, encoding="utf-8")
    state = {
        "job": job,
        "phase": "planned",
        "baseline_commit": baseline.stdout.strip(),
        "implemented_by": implemented_by,
        "review_base": review_base,
        "feature_commit": baseline.stdout.strip() if implemented_by == "chatgpt" else None,
        "created_at": now(),
        "updated_at": now(),
        "round": 0,
        "ready_for_user": False,
        "reviews": {},
        "gate": {},
        "risk": risk,
        "acceptance_profile": acceptance,
        "reported_token_budget": token_budget,
        "token_usage": {"reported_total": 0, "sessions": []},
        "deployment": "forbidden",
        "last_error": None,
    }
    atomic_json(run_dir / "status.json", state)
    return state


def workspace(job: str, base_commit: str) -> Path:
    dest = ROOT.parent / ("odyssey-agent-work-" + job)
    if dest.exists() or dest.is_symlink():
        raise CycleError("Refusing to reuse a worktree or existing directory")
    branch = "agent/" + job
    exists = running(
        ["git", "-C", str(ROOT), "show-ref", "--verify", "--quiet", "refs/heads/" + branch]
    )
    if exists.returncode == 0:
        raise CycleError("Pilot branch already exists")
    result = running(
        [
            "git",
            "-C",
            str(ROOT),
            "worktree",
            "add",
            "-b",
            branch,
            str(dest),
            base_commit,
        ],
        timeout=60,
    )
    if result.returncode:
        raise CycleError("Isolated git worktree creation failed: " + result.stderr[-800:])
    return dest


def safe_worktree(dest: Path, job: str) -> None:
    expected = (ROOT.parent / ("odyssey-agent-work-" + job)).resolve()
    if dest.resolve() != expected or not (dest / ".git").exists():
        raise CycleError("Isolated worktree guard rejected this path")
    if any(piece in dest.name for piece in CHECKOUT_EXCLUDE) or dest == ROOT:
        raise CycleError("Never use DEV/PROD or the working feature branch")
    verify = running(["git", "-C", str(dest), "branch", "--show-current"])
    if verify.returncode or verify.stdout.strip() != "agent/" + job:
        raise CycleError("Codex cannot run outside its dedicated agent branch")


def codex(role: str, prompt: str, dest: Path, evidence: Path, *, read_only: bool) -> dict:
    """One actual Codex CLI process, bounded and cancellable by the supervisor."""
    job = evidence.parent.name
    require_budget(job)
    state = load(job)
    used = state.get("token_usage", {}).get("reported_total", 0)
    cap = state.get("reported_token_budget", model_policy()["default_reported_token_budget"])
    if cap - used < model_policy()["minimum_session_headroom"]:
        raise CycleError("Insufficient reported-token headroom for another Codex session")
    choice = select_agent_model(role, state, dest)
    artifact = evidence / (role + ".json" if read_only else "builder.md")
    stdout_log = evidence / (role + ".log")
    cmd = [
        "codex",
        "exec",
        "--ignore-user-config",
        "--ephemeral",
        "--model",
        choice["model"],
        "--config",
        'model_reasoning_effort="' + choice["effort"] + '"',
        "--sandbox",
        "read-only" if read_only else "workspace-write",
        "--cd",
        str(dest),
        "--output-last-message",
        str(artifact),
    ]
    if read_only:
        cmd.extend(("--output-schema", str(SCHEMA)))
    cmd.append("-")
    # The host CLI has ChatGPT login; never pass existing local MCP
    # configurations, API secrets or n8n tokens to these delegated agents.
    excluded = ("SECRET", "TOKEN", "API_KEY", "PASSWORD", "CREDENTIAL", "PRIVATE_KEY")
    env = {
        key: value
        for key, value in os.environ.items()
        if not any(name in key.upper() for name in excluded)
    }
    started = time.monotonic()
    minimum_available = mem_available()
    with stdout_log.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            cmd,
            cwd=dest,
            stdin=subprocess.PIPE,
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
            start_new_session=True,
        )
        try:
            assert process.stdin is not None
            process.stdin.write(prompt)
            process.stdin.close()
            while process.poll() is None:
                if (job_path(job) / "STOP").exists():
                    raise CycleError("Operator requested STOP")
                minimum_available = min(minimum_available, mem_available())
                if minimum_available < MIN_MEMORY_MIB:
                    raise CycleError("Memory protection: Codex process halted")
                if time.monotonic() - started > TIMEOUT:
                    raise CycleError("Codex session exceeded its time budget")
                time.sleep(2)
        except BaseException:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait(timeout=5)
            raise
    record = {
        "role": role,
        "exit_code": process.returncode,
        "elapsed_s": round(time.monotonic() - started, 2),
        "available_ram_mib_after": mem_available(),
        "minimum_available_ram_mib_during": minimum_available,
        "artifact": str(artifact),
        "model": choice["model"],
        "effort": choice["effort"],
        "tier": choice["tier"],
        "routing_reason": choice["reason"],
        "reported_tokens": reported_token_count(stdout_log),
    }
    # The CLI must not silently downgrade/replace our security-reviewed
    # model mapping, even if a future provider changes its fallbacks.
    with stdout_log.open("rb") as trace:
        header = trace.read(2048).decode("utf-8", errors="replace")
    matched = re.search(r"(?m)^model:\s*(\S+)\s*$", header)
    if process.returncode or not artifact.is_file():
        raise CycleError(f"{role} failed; see {stdout_log}")
    if matched is None or matched.group(1) != choice["model"]:
        raise CycleError("Codex model routing is not verified; refusing review")
    if read_only:
        record["verdict"] = json.loads(artifact.read_text(encoding="utf-8"))
        if record["verdict"].get("verdict") not in {"pass", "fail", "blocked"}:
            raise CycleError(role + " returned unknown verdict")
    if record["reported_tokens"] is None:
        raise CycleError("Codex CLI did not report tokens; cannot enforce budget")
    return record


def instructions(role: str, spec: str, baseline: str, reviews: dict | None = None) -> str:
    content = (ROLES / (role + ".md")).read_text(encoding="utf-8")
    return (
        content + "\n\nMANDATORY SOURCE OF TRUTH: first read AGENTS.md, "
        "docs/architecture/functional-roadmap.md and "
        "docs/architecture/application-extensibility-plan.md, scoped to the active "
        "section and changed contracts; avoid re-reading long histories. "
        "Do not run entire pytest/cross-surface suite inside Codex sandbox: "
        "socket tests will fail due to isolation; the supervisor runs that "
        "gate ONCE in the verified host environment. Run only relevant "
        "focused tests; review the gate receipt rather than rerunning it. "
        "When reviewing, begin with git diff against source baseline and read "
        "only files needed to support concrete findings. "
        "Work ONLY in this temporary worktree/agent branch; no deploy, "
        "no production/private vault, no secrets, no changing Git remotes, "
        "no approval bypasses, no push or merge.\n"
        "Original feature request:\n"
        + spec
        + "\nBaseline commit: "
        + baseline
        + "\nPrior audit findings (only on repair iterations):\n"
        + json.dumps(reviews or {}, ensure_ascii=False)[-12000:]
    )


def deterministic_gates(dest: Path, evidence: Path) -> dict:
    require_budget(evidence.parent.name)
    python = ROOT.parent / "odyssey-dev/.venv/bin/python"
    ruff = ROOT.parent / "odyssey-dev/.venv/bin/ruff"
    if not python.is_file() or not ruff.is_file():
        raise CycleError("Verified Python venv and Ruff are required")
    gates = [
        ("cross_surface", [str(python), "scripts/odyssey_cross_surface_gate.py"]),
        ("acceptance", [str(python), "scripts/odyssey_acceptance_contracts.py"]),
        (
            "ruff",
            [
                str(ruff),
                "check",
                "odyssey_core",
                "odyssey_runtime",
                "odyssey_apps",
                "scripts",
                "tests",
            ],
        ),
    ]
    report = {}
    for name, cmd in gates:
        require_budget(evidence.parent.name)
        started = time.monotonic()
        try:
            result = running(cmd, cwd=dest, timeout=240)
        except subprocess.TimeoutExpired:
            report[name] = {"pass": False, "reason": "timeout"}
            continue
        (evidence / (name + ".log")).write_text(
            (result.stdout + "\n" + result.stderr)[-18000:], encoding="utf-8"
        )
        report[name] = {
            "pass": result.returncode == 0,
            "exit_code": result.returncode,
            "elapsed_s": round(time.monotonic() - started, 2),
            "ram_available_after_mib": mem_available(),
            "log": str(evidence / (name + ".log")),
        }
    return report


def run(job: str, max_rounds: int, live: bool) -> dict:
    if not live:
        raise CycleError("No live agents without --live; use plan/doctor safely")
    if not 1 <= max_rounds <= 3:
        raise CycleError("Rounds capped at 1-3")
    state = load(job)
    if state["phase"] != "planned":
        raise CycleError("Job is not planned; refusing duplicate or concurrent launch")
    acceptance = state.get("acceptance_profile", "product")
    if acceptance not in ACCEPTANCE_PROFILES:
        raise CycleError("Stored acceptance profile is invalid")
    if mem_available() < MIN_MEMORY_MIB:
        raise CycleError("Not enough memory to launch Codex safely")
    run_dir = job_path(job)
    dest = workspace(job, state["baseline_commit"])
    safe_worktree(dest, job)
    state["worktree"] = str(dest)
    brief = (run_dir / "brief.md").read_text(encoding="utf-8")
    findings = {}
    review_base = state.get("review_base")
    if state.get("implemented_by", "codex") == "chatgpt" and not review_base:
        raise CycleError("A ChatGPT-originated feature requires independent comparison base")
    compare = (
        "\nIndependent review scope: validate Git changes since "
        + review_base
        + ". Inspect `git diff "
        + review_base
        + "` and any current uncommitted"
        " changes. Do NOT equate historical unrelated product gaps with"
        " newly introduced regressions; report unresolved preexisting blockers"
        " as non-blocking findings unless the feature actually promises to fix them."
        if review_base
        else ""
    )
    update(job, state, "running")
    try:
        for attempt in range(1, max_rounds + 1):
            evidence = run_dir / f"round-{attempt}"
            evidence.mkdir(parents=True)
            # Publish the new evidence scope before any repair or handoff work.
            # Prior verdicts remain in their round files and in `findings` for repair.
            update(
                job,
                state,
                "starting_round",
                round=attempt,
                active_role=None,
                reviews={},
                review_artifacts={},
                gate={},
                ready_for_user=False,
            )
            if state.get("implemented_by", "codex") == "chatgpt" and attempt == 1:
                # A real human-facing ChatGPT session ALREADY authored and
                # committed this exact source snapshot. Never bill Codex to
                # implement the same feature a second time.
                update(job, state, "reviewing_chatgpt_change", round=attempt, active_role=None)
                (evidence / "handoff.json").write_text(
                    json.dumps(
                        {
                            "developer": "chatgpt",
                            "feature_commit": state["feature_commit"],
                            "review_base": review_base,
                        },
                        indent=2,
                    ),
                    encoding="utf-8",
                )
            else:
                update(job, state, "implementing", round=attempt, active_role="builder")
                builder_receipt = codex(
                    "builder",
                    instructions(
                        "builder", brief, review_base or state["baseline_commit"], findings
                    )
                    + compare,
                    dest,
                    evidence,
                    read_only=False,
                )
                record_agent_usage(job, state, "builder", builder_receipt)
            safe_worktree(dest, job)
            if acceptance == "tooling":
                scope_baseline = review_base or state["baseline_commit"]
                if not tooling_scope_is_safe(dest, scope_baseline):
                    update(
                        job,
                        state,
                        "blocked_acceptance_scope",
                        active_role=None,
                        ready_for_user=False,
                        last_error="Tooling acceptance includes a path outside the supervisor allowlist",
                    )
                    return state
            update(job, state, "testing", active_role="deterministic_gates")
            gates = deterministic_gates(dest, evidence)
            state["gate"] = gates
            if not all(check.get("pass") is True for check in gates.values()):
                # Fail FAST on deterministic defects. Independent GPT reviews
                # at 30-50k tokens/session cannot usefully approve broken tests.
                # Feed the gate logs directly to the next Builder, without
                # spending more on architecture/QA/performance first.
                findings = {"gates": gates, "reviews": {}}
                remaining = state.get(
                    "reported_token_budget", model_policy()["default_reported_token_budget"]
                ) - state.get("token_usage", {}).get("reported_total", 0)
                if attempt >= max_rounds:
                    update(
                        job,
                        state,
                        "blocked_repair_budget",
                        active_role=None,
                        ready_for_user=False,
                        last_error="Deterministic gates failed; no repair rounds remain",
                    )
                    return state
                if remaining < model_policy()["minimum_session_headroom"]:
                    update(
                        job,
                        state,
                        "blocked_insufficient_token_headroom",
                        active_role=None,
                        ready_for_user=False,
                        last_error=(
                            "Deterministic gates failed; insufficient token headroom "
                            "for a safe repair attempt"
                        ),
                    )
                    return state
                update(job, state, "repair_needed", active_role=None, ready_for_user=False)
                continue
            update(job, state, "reviewing", active_role=None)
            reviews = {}
            for role in REVIEW_ROLES:
                update(job, state, "reviewing", active_role=role)
                before = running(
                    ["git", "status", "--porcelain", "--untracked-files=all"], cwd=dest
                )
                if before.returncode:
                    raise CycleError("Cannot record review-only Git baseline")
                review = codex(
                    role,
                    instructions(role, brief, review_base or state["baseline_commit"], gates)
                    + compare,
                    dest,
                    evidence,
                    read_only=True,
                )
                after = running(["git", "status", "--porcelain", "--untracked-files=all"], cwd=dest)
                if after.returncode or after.stdout != before.stdout:
                    raise CycleError("Read-only agent unexpectedly changed repository files")
                reviews[role] = review["verdict"]
                artifact = evidence / (role + "-completed.json")
                atomic_json(artifact, review)
                state["review_artifacts"][role] = str(artifact)
                # Preserve a valid review before applying the shared usage cap.
                update(job, state, "reviewing", reviews=dict(reviews), active_role=None)
                record_agent_usage(job, state, role, review)
            findings = {"gates": gates, "reviews": reviews}
            succeeded = all(check["pass"] for check in gates.values()) and all(
                v["verdict"] == "pass" for v in reviews.values()
            )
            if succeeded:
                profile = ACCEPTANCE_PROFILES[acceptance]
                if acceptance == "tooling":
                    update(
                        job,
                        state,
                        profile["ready_phase"],
                        active_role=None,
                        ready_for_user=profile["ready_for_user"],
                        readiness_meaning=(
                            "Internal CLI feature ready for maintainer; no deploy, merge, or push authority"
                        ),
                        last_error=None,
                    )
                    return state
                # Product readiness still requires genuine browser->n8n->Writer evidence.
                update(
                    job,
                    state,
                    profile["ready_phase"],
                    active_role=None,
                    ready_for_user=profile["ready_for_user"],
                    last_error="Authenticated live browser and deployment must be verified separately",
                )
                return state
            # A reviewer can simultaneously find a fixable defect and lack
            # an external browser or benchmark. Repair code findings within
            # budget; do NOT interpret an external blocker as another coding
            # failure. Conversely do not silently skip a fixable blocker just
            # because an unrelated external gate was also unavailable.
            fixable = any(not gate.get("pass", False) for gate in gates.values()) or any(
                judgment.get("verdict") == "fail"
                or any(
                    row.get("severity") == "blocking" and row.get("actionability") == "repairable"
                    for row in judgment.get("findings", [])
                )
                for judgment in reviews.values()
            )
            external = any(
                judgment.get("verdict") == "blocked"
                or any(
                    row.get("severity") == "blocking" and row.get("actionability") == "external"
                    for row in judgment.get("findings", [])
                )
                for judgment in reviews.values()
            )
            if fixable and attempt < max_rounds:
                update(job, state, "repair_needed", active_role=None, ready_for_user=False)
                continue
            if fixable:
                update(
                    job,
                    state,
                    "blocked_repair_budget",
                    active_role=None,
                    ready_for_user=False,
                    last_error="Repairable errors remain after the bounded iteration budget",
                )
                return state
            if external:
                update(
                    job,
                    state,
                    "blocked_external_evidence",
                    active_role=None,
                    ready_for_user=False,
                    last_error="An independent auditor requires a non-automated external gate",
                )
                return state
            update(
                job,
                state,
                "blocked_review_uncertain",
                active_role=None,
                ready_for_user=False,
                last_error="Reviewers did not grant a clear proof of completion",
            )
            return state
    except (CycleError, OSError, ValueError) as err:
        update(job, state, "blocked", ready_for_user=False, last_error=str(err))
    return state


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    actions.add_parser("doctor")
    p = actions.add_parser("plan")
    p.add_argument("--spec", type=Path, required=True)
    p.add_argument("--job", required=True)
    p.add_argument("--implemented-by", choices=("codex", "chatgpt"), default="codex")
    p.add_argument("--acceptance", choices=("product", "tooling"), default="product")
    p.add_argument("--against", help="Existing parent Git SHA of ChatGPT-authored changes")
    p.add_argument("--risk", choices=("normal", "high", "critical"), default="normal")
    p.add_argument(
        "--token-budget",
        type=int,
        default=None,
        help="Maximum cumulative CLI-reported tokens (default from policy)",
    )
    r = actions.add_parser("run")
    r.add_argument("--job", required=True)
    r.add_argument("--max-rounds", type=int, default=2)
    r.add_argument("--live", action="store_true")
    st = actions.add_parser("status")
    st.add_argument("--job", required=True)
    route = actions.add_parser("route")
    route.add_argument("--job", required=True)
    stop = actions.add_parser("stop")
    stop.add_argument("--job", required=True)
    args = parser.parse_args()
    try:
        if args.action == "doctor":
            value = doctor()
        elif args.action == "plan":
            value = plan(
                args.spec,
                args.job,
                implemented_by=args.implemented_by,
                against=args.against,
                risk=args.risk,
                token_budget=args.token_budget,
                acceptance=args.acceptance,
            )
        elif args.action == "run":
            STATE.mkdir(mode=0o700, parents=True, exist_ok=True)
            # Process-level exclusivity ACROSS job IDs on this Raspberry.
            with (STATE / "SUPERVISOR.lock").open("w") as lock:
                try:
                    fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError as error:
                    raise CycleError("Another Codex agent cycle is already active") from error
                value = run(args.job, args.max_rounds, args.live)
        elif args.action == "status":
            value = load(args.job)
        elif args.action == "route":
            state = load(args.job)
            checkout = Path(state["worktree"]) if state.get("worktree") else ROOT
            if state.get("worktree"):
                safe_worktree(checkout, args.job)
            value = {
                "job": args.job,
                "risk": state.get("risk", "normal"),
                "round": state.get("round", 0),
                "reported_token_budget": state.get(
                    "reported_token_budget", model_policy()["default_reported_token_budget"]
                ),
                "used_reported_tokens": (
                    state["token_usage"]["reported_total"] if "token_usage" in state else None
                ),
                "choices": {
                    role: select_agent_model(role, state, checkout)
                    for role in ("builder", *REVIEW_ROLES)
                },
                "models_launched": False,
            }
        else:
            path = job_path(args.job)
            if not (path / "status.json").exists():
                raise CycleError("Unknown job")
            (path / "STOP").touch()
            value = {"job": args.job, "stop_requested": True}
        print(json.dumps(value, ensure_ascii=False, indent=2))
        # A successful shell invocation is not a completed feature. CI/n8n
        # must also check the JSON phase; return nonzero for blocked pilots.
        return 3 if args.action == "run" and value.get("phase", "").startswith("blocked") else 0
    except CycleError as err:
        print(f"Odyssey agent-team: {err}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
