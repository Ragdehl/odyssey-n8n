"""A user-agreed architectural requirement must not vanish with test refactors."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scripts.odyssey_acceptance_contracts import (
    REQUIRED,
    ROOT,
    AcceptanceContractError,
    inspect_contracts,
)

LEDGER = json.loads((ROOT / "docs/architecture/odyssey-acceptance-contracts.json").read_text())


def _modified():
    return copy.deepcopy(LEDGER)


def test_all_user_contracts_are_source_anchored_and_not_marked_product_ready():
    check = inspect_contracts()
    assert check["contract_count"] >= len(REQUIRED)
    assert check["existing_offline_test_anchors"] >= 15
    assert check["dev_ready"] is False
    assert check["real_browser_n8n_verified"] is False
    assert "P4-REAL-BROWSER" in check["blocked_product_contracts"]


def test_removing_requirement_or_test_never_silently_shrinks_regression():
    missing = _modified()
    missing["contracts"] = [row for row in missing["contracts"] if row["id"] != "E3-CLAIM-CRASH"]
    with pytest.raises(AcceptanceContractError, match="missing or duplicate"):
        inspect_contracts(manifest=missing)
    missing = _modified()
    missing["contracts"][0]["offline_test_selectors"][0] += "_renamed"
    with pytest.raises(AcceptanceContractError, match="Missing or unselected executable"):
        inspect_contracts(manifest=missing)


def test_unselected_test_is_not_accepted_as_coverage():
    missing = _modified()
    with pytest.raises(AcceptanceContractError, match="Missing or unselected executable"):
        inspect_contracts(manifest=missing, groups={"fake": ()})


def test_offline_success_never_certifies_browser_n8n_or_weakens_live_gate():
    forged = _modified()
    forged["contracts"][0]["verified_real_browser_n8n"] = True
    with pytest.raises(AcceptanceContractError, match="self-attest"):
        inspect_contracts(manifest=forged)
    forged = _modified()
    forged["required_product_gate"] = "local_python_passed"
    with pytest.raises(AcceptanceContractError, match="weakened"):
        inspect_contracts(manifest=forged)
    forged = _modified()
    forged["contracts"][0]["blocks_p4_dev"] = False
    with pytest.raises(AcceptanceContractError, match="cannot waive"):
        inspect_contracts(manifest=forged)


def test_acceptance_ledger_never_mutates_worktree(tmp_path):
    assert not list(tmp_path.iterdir())
    inspect_contracts()
    assert not list(tmp_path.iterdir())
    assert Path("docs/architecture/odyssey-acceptance-contracts.json").is_file()


def test_archived_agent_history_remains_accessible_but_not_primary_status():
    agent = (ROOT / "AGENTS.md").read_text()
    history = (ROOT / "docs/architecture/agent-execution-history-202610.md").read_text()
    roadmap = (ROOT / "docs/architecture/functional-roadmap.md").read_text()
    assert len(agent.splitlines()) < 620  # Prevent silent return of timeline bloat
    assert "agent-execution-history-202610.md" in agent
    assert "odyssey-acceptance-contracts.json" in agent
    assert "### 2026-10-16 — P4 five-stage stabilized" in history
    assert "### 2026-10-13 — Hybrid validator generalization" in history
    assert "## ➡️ Seguimiento activo" in roadmap


def test_dev_pull_requests_receive_an_independent_offline_contract_gate():
    dev_workflow = (ROOT / ".github/workflows/odyssey-dev-contract-gate.yml").read_text()
    legacy_ci = (ROOT / ".github/workflows/python-ci.yml").read_text()
    assert "pull_request:" in dev_workflow and "branches: [dev]" in dev_workflow
    assert "python scripts/odyssey_acceptance_contracts.py" in dev_workflow
    assert "python scripts/odyssey_cross_surface_gate.py" in dev_workflow
    assert "workflow_dispatch:" in dev_workflow
    assert "without credentials" in dev_workflow
    assert "branches: [main]" in legacy_ci


def test_ci_cli_runs_with_no_pythonpath_or_provider_credential(monkeypatch):
    import os
    import subprocess
    import sys

    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    for secret in ("OPENAI_API_KEY", "OPENAI_ORGANIZATION", "OPENAI_PROJECT"):
        env.pop(secret, None)
    result = subprocess.run(
        [sys.executable, "scripts/odyssey_acceptance_contracts.py"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr
    assert "ACCEPTANCE_LEDGER_INTEGRITY_PASS" in result.stdout
    assert "P4 DEV UNAUTHORIZED" in result.stdout
