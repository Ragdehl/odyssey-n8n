"""Regression sentinels for Odyssey agent instructions and safe context discovery."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _load_script(name: str):
    """Load a standalone script without executing its command-line entrypoint."""
    path = ROOT / "scripts" / name
    spec = importlib.util.spec_from_file_location(name.removesuffix(".py"), path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_skill_discovery_and_canonical_document_links_are_valid() -> None:
    """Prevent silent loss of mandatory agent workflows and relative references."""
    guard = _load_script("odyssey_docs_guard.py")
    assert guard.check() == []


def test_short_agent_contract_routes_to_llm_and_generality() -> None:
    """Keep critical always-on rules visible regardless of optional skills."""
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert len(agents.splitlines()) <= 150
    assert "odyssey-llm-stage" in agents
    assert "odyssey-generality" in agents
    assert "Core/E3" in agents
    assert "systemd" in agents
    assert "human" in agents.lower()


def test_universal_semantic_generality_rule_is_discoverable_and_auditable() -> None:
    """Prevent narrowing the no-special-case policy to names or family examples."""
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    skill = (ROOT / ".codex/skills/odyssey-generality/SKILL.md").read_text(encoding="utf-8")
    plan = (ROOT / "docs/architecture/r0-remediation-plan.md").read_text(encoding="utf-8")
    reviewer = (ROOT / "ops/agent-team/generality.md").read_text(encoding="utf-8")
    assert "No case-specific semantic code" in agents
    assert "temporal mention position/order" in agents
    assert "redundant path removed" in agents
    assert "semantically equivalent reorderings" in skill
    assert "user-defined note types" in skill
    assert "posición o secuencia de fechas" in plan
    assert "temporal position/order" in reviewer
    # A green offline suite never justifies a new producer used only by tests.
    assert "Unreachable-component veto" in reviewer
    assert "MUST be **FAIL" in reviewer
    skill = (ROOT / ".codex/skills/odyssey-implement-change/SKILL.md").read_text()
    assert "Pre-code veto for new semantic mechanisms" in skill
    assert "--require-production-use" in skill


def test_existing_generality_reviewer_returns_actionable_repair_handoff_not_only_verdict():
    """The existing audit schema and prompts must yield a usable repair proposal.

    Deterministic instruction contract only, NOT a live model compliance claim.
    """
    reviewer = (ROOT / "ops/agent-team/generality.md").read_text(encoding="utf-8")
    implement = (ROOT / ".codex/skills/odyssey-implement-change/SKILL.md").read_text(
        encoding="utf-8"
    )
    results = (ROOT / ".codex/skills/odyssey-results/SKILL.md").read_text(encoding="utf-8")
    schema = json.loads((ROOT / "ops/agent-team/review.schema.json").read_text())
    fields = set(schema["properties"]["findings"]["items"]["required"])
    assert {"path", "reason", "action", "severity", "actionability"} <= fields
    assert {"summary", "findings", "evidence", "verdict"} <= set(schema["required"])
    assert "Reusable repair handoff, not just a verdict" in reviewer
    for requirement in (
        "preferred minimal repair in the existing owner",
        "positive/negative final-effect tests",
        "ranked recommendation",
        "Do NOT invent another schema",
        "Reduce token waste",
    ):
        assert requirement in reviewer
    assert "Reuse negative audit results rather than restarting analysis" in implement
    assert "actual useful findings" in results
    ledger = json.loads((ROOT / "docs/architecture/r0-remediation-ledger.json").read_text())
    group = next(g for g in ledger["workstreams"] if g["id"] == "G04")
    handoff = group["reusable_repair_handoff_20261102"]
    assert handoff["status"] == "ACTIONABLE_PLAN_FROM_EXISTING_READ_ONLY_AUDIT_NOT_YET_IMPLEMENTED"
    assert len(handoff["preferred_repair_order_without_new_phase"]) == 3
    for finding in handoff["preferred_repair_order_without_new_phase"]:
        assert all(
            finding[k]
            for k in ("owner", "existing", "missing", "minimal_change_proposal", "acceptance_first")
        )
    assert "NOT" in handoff["decision_gate"] or "pending" in handoff["decision_gate"].lower()


def test_doctor_never_displays_protected_key_and_fails_closed_on_unknown(
    tmp_path: Path,
) -> None:
    """A readable secret file only yields booleans; no secret value is read."""
    doctor = _load_script("odyssey_context_doctor.py")
    src = tmp_path / "checkout"
    dev = tmp_path / "dev"
    src.mkdir()
    dev.mkdir()
    secret_file = tmp_path / "protected.env"
    dummy_secret = "odyssey-do-not-leak-this-fixture-value-123"
    secret_file.write_text("OPENAI_API_KEY=" + dummy_secret, encoding="utf-8")
    marker = tmp_path / "deployed-commit"
    marker.write_text("invalid-id", encoding="utf-8")
    result = doctor.inspect(
        repo=src,
        dev_root=dev,
        marker_path=marker,
        env_path=secret_file,
        check_health=False,
    )
    rendered = json.dumps(result)
    assert dummy_secret not in rendered
    assert "OPENAI_API_KEY=" not in rendered
    assert result["provider_environment"]["protected_file_readable"] is True
    assert result["provider_environment"]["key_value_examined"] is False
    assert result["dev_checkout_matches_marker"] is False
    assert result["source_sha"] == "unknown"
    assert any("marker/checkout unknown" in x for x in result["warnings"])


def test_doctor_marker_requires_exact_full_sha(tmp_path: Path) -> None:
    """Prevent mistaking a stale, truncated or malformed marker for a release."""
    doctor = _load_script("odyssey_context_doctor.py")
    marker = tmp_path / "deployed-commit"
    assert doctor._marker(marker) is None
    marker.write_text("abc123", encoding="utf-8")
    assert doctor._marker(marker) is None
    marker.write_text("a" * 40 + "\n", encoding="utf-8")
    assert doctor._marker(marker) == "a" * 40


def _r0_ledger_fixture(tmp_path: Path) -> tuple[object, Path, dict]:
    """Use a real immutable audit, but a disposable, locally writable ledger."""
    guard = _load_script("odyssey_docs_guard.py")
    relative = Path("docs/architecture")
    (tmp_path / relative).mkdir(parents=True)
    for name in (
        "r0-whole-repository-source-audit-evidence-20261031.json",
        "r0-remediation-plan.md",
        "r0-remediation-ledger.json",
    ):
        (tmp_path / relative / name).write_bytes((ROOT / relative / name).read_bytes())
    path = tmp_path / relative / "r0-remediation-ledger.json"
    return guard, path, json.loads(path.read_text())


def test_global_r0_findings_are_all_tracked_and_originals_immutable(tmp_path: Path) -> None:
    """A report or PR cleanup cannot silently remove one of the 24 findings."""
    guard, path, ledger = _r0_ledger_fixture(tmp_path)
    assert guard.check_r0_findings(tmp_path) == []
    assert len(ledger["findings"]) == 24
    assert len(ledger["workstreams"]) == 13
    assert sum(f["severity"] == "blocking" for f in ledger["findings"]) == 13

    ledger["findings"].pop()
    path.write_text(json.dumps(ledger))
    assert any("24 original" in x for x in guard.check_r0_findings(tmp_path))


def test_r0_guard_blocks_severity_or_owner_drift_and_fake_closure(tmp_path: Path) -> None:
    """Changing labels or marking solved without evidence cannot green CI."""
    guard, path, ledger = _r0_ledger_fixture(tmp_path)
    ledger["findings"][0]["severity"] = "warning"
    path.write_text(json.dumps(ledger))
    assert any("origin/severity/reference" in x for x in guard.check_r0_findings(tmp_path))
    ledger["findings"][0]["severity"] = "blocking"
    ledger["findings"][0]["workstream_id"] = "G13"
    path.write_text(json.dumps(ledger))
    assert any("assignment changed" in x for x in guard.check_r0_findings(tmp_path))
    ledger["findings"][0]["workstream_id"] = "G03"
    ledger["findings"][0]["state"] = "closed"
    path.write_text(json.dumps(ledger))
    assert any("closure evidence missing" in x for x in guard.check_r0_findings(tmp_path))


def test_r0_guard_requires_closure_proof_and_no_premature_group_done(tmp_path: Path) -> None:
    """Even a verified component test does not automatically finish R0."""
    guard, path, ledger = _r0_ledger_fixture(tmp_path)
    proof = {
        "commit_sha": "a" * 40,
        "before_after": "Observed failure and physically verified result on a synthetic vault",
        "tests": ["tests/runtime/test_r0_finding_fixture.py"],
    }
    path_to_test = tmp_path / proof["tests"][0]
    path_to_test.parent.mkdir(parents=True)
    path_to_test.write_text("def test_something(): pass\n")
    ledger["findings"][0].update(state="code_verified", closure=proof)
    path.write_text(json.dumps(ledger))
    assert guard.check_r0_findings(tmp_path) == []
    ledger["findings"][0]["state"] = "closed"
    path.write_text(json.dumps(ledger))
    assert any("incomplete closure" in x for x in guard.check_r0_findings(tmp_path))
    proof["independent_reviews"] = ["read-only generality review on the pinned code"]
    ledger["workstreams"][0]["status"] = "closed"
    path.write_text(json.dumps(ledger))
    assert any("group closed with unresolved" in x for x in guard.check_r0_findings(tmp_path))


def test_r0_append_only_followup_has_consistent_id_and_expected_effect(tmp_path: Path) -> None:
    guard, path, ledger = _r0_ledger_fixture(tmp_path)
    next_index = len(ledger["followups"]) + 1
    case = {
        "id": f"R0-N{next_index:03}",
        "source": "Caso sintético anónimo",
        "observed_failure": "Se perdió el hecho",
        "expected_effect": "Debería verse en la nota",
        "workstream_id": "G03",
        "state": "open",
        "closure": None,
    }
    ledger["followups"].append(case)
    path.write_text(json.dumps(ledger))
    assert guard.check_r0_findings(tmp_path) == []
    ledger["followups"][-1]["expected_effect"] = ""
    path.write_text(json.dumps(ledger))
    assert any("invalid appended" in x for x in guard.check_r0_findings(tmp_path))


def test_r0_original_audit_cannot_be_silently_rewritten(tmp_path: Path) -> None:
    guard, _, _ = _r0_ledger_fixture(tmp_path)
    audit = tmp_path / "docs/architecture/r0-whole-repository-source-audit-evidence-20261031.json"
    audit.write_bytes(audit.read_bytes() + b"\n")
    assert any(
        "original whole-repository audit changed" in x for x in guard.check_r0_findings(tmp_path)
    )
