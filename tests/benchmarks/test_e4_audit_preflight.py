"""Regression: E4 auditor dispatch must fail fast on missing evidence."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
path = ROOT / "scripts/odyssey_e4_audit_preflight.py"
spec = importlib.util.spec_from_file_location("e4_preflight", path)
assert spec and spec.loader
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


def test_duplicate_runs_or_invalid_results_do_not_count():
    rows = [
        {"run_id": "a", "pass": True, "status": "completed", "seconds": 45},
        {"run_id": "a", "pass": True, "status": "completed", "seconds": 45},
        {"run_id": "b", "pass": True, "status": "needs_attention", "seconds": 4},
        {"run_id": "c", "pass": False, "status": "completed", "seconds": 3},
        {"run_id": "d", "pass": True, "status": "completed", "seconds": 50},
    ]
    assert gate._qualified_samples(rows, browser=False) == [45, 50]
    assert gate._qualified_samples(rows, browser=True) == []
    rows[0]["physical_browser_n8n_gpt"] = True
    assert gate._qualified_samples(rows, browser=True) == []
    rows[0]["metric"] = "send_to_first_response"
    assert gate._qualified_samples(rows, browser=True) == [45]


def test_preflight_holds_when_independent_run_counts_missing(monkeypatch, tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "e4-v10-fastembed-isolated-pi-receipt-20261021.json").write_text(
        json.dumps(
            {
                "synthetic_only": True,
                "index_250_synthetic_notes": {"synthetic_notes": 250},
                "offline_model_reloads": [{"load_s": 1.3}] * 3,
            }
        )
    )
    monkeypatch.setattr(gate, "DOCS", docs)
    monkeypatch.setattr(
        gate, "_git", lambda *args: "frozen" if args == ("rev-parse", "HEAD") else ""
    )
    monkeypatch.setattr(gate, "_browser_evidence_ok", lambda receipt: True)
    report = gate.evaluate()
    assert report["ready_to_spend_four_auditors"] is False
    assert any("0/20" in issue for issue in report["blocking_prerequisites"])


def test_complete_synthetic_reporting_has_no_hidden_special_case(monkeypatch, tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    base = [
        {"run_id": str(i), "pass": True, "status": "completed", "seconds": 65} for i in range(20)
    ]
    (docs / "e4-v10-performance-samples-20261021.json").write_text(
        json.dumps(
            {
                "direct_positive": [{**row, "seconds": 52} for row in base],
                "browser_positive": [
                    {
                        **row,
                        "seconds": 85,
                        "physical_browser_n8n_gpt": True,
                        "metric": "send_to_first_response",
                    }
                    for row in base
                ],
                "host_resources_under_full_load": {"mem_available_kib": 1700000},
            }
        )
    )
    (docs / "e4-v10-fastembed-isolated-pi-receipt-20261021.json").write_text(
        json.dumps(
            {
                "synthetic_only": True,
                "index_250_synthetic_notes": {"synthetic_notes": 250},
                "offline_model_reloads": [{"load_s": 1.4}] * 3,
            }
        )
    )
    monkeypatch.setattr(gate, "DOCS", docs)
    monkeypatch.setattr(
        gate, "_git", lambda *args: "frozen" if args == ("rev-parse", "HEAD") else ""
    )
    monkeypatch.setattr(gate, "_browser_evidence_ok", lambda receipt: True)
    report = gate.evaluate()
    assert report["ready_to_spend_four_auditors"] is True
    assert report["qualified_performance_samples"]["direct_positive"]["qualified"] == 20
    assert report["qualified_performance_samples"]["browser_positive"]["qualified"] == 20


def test_browser_evidence_cannot_escape_document_directory(monkeypatch, tmp_path):
    monkeypatch.setattr(gate, "ROOT", tmp_path)
    monkeypatch.setattr(gate, "DOCS", tmp_path / "docs" / "architecture")
    (tmp_path / "docs" / "architecture").mkdir(parents=True)
    bad = {"committed_full_log": "docs/architecture/../../outside.log"}
    assert gate._browser_evidence_ok(bad) is False
