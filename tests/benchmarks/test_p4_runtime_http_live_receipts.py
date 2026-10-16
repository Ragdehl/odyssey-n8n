"""P4 replayable receipts captured from real AI and the real HTTP runtime adapter.

This suite audits evidence from the *isolated* transport pilot. It does not
claim that n8n or a real browser has been used.
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPORT = (
    ROOT / "benchmarks/application_router/light_router_poc_20261016/p4_runtime_http_receipts.json"
)


def _rows():
    report = json.loads(REPORT.read_text())
    return report, {item["id"]: item for item in report["cases"]}


def test_three_actual_model_http_core_mutations_and_two_safe_rejections():
    report, rows = _rows()
    assert report["outcome"] == "PASS"
    assert report["isolated_dev_clone"] is True
    assert report["source_note_count"] == 97
    assert report["temporary_vault_deleted"] is True
    assert len(rows) == 5
    assert report["n8n_traversed"] is False and report["browser_traversed"] is False
    assert report["full_prod_embeddings"] is False
    assert report["replay_survived_new_runtime_composition"] is True
    for row in rows.values():
        assert row["http_status"] == 200
        assert row["replay_http_status"] == 200
        assert row["replay_marked"] is True
        assert row["replay_preserved_all_note_bytes"] is True
        assert row["real_model_runs"] == 1
        assert row["network_errors"] is None


def test_maya_identity_and_two_dates_are_canonically_shared():
    _report, rows = _rows()
    first = rows["http-maya-1"]
    second = rows["http-maya-2"]
    assert first["product_status"] == second["product_status"] == "completed"
    a = first["validated_canonical_readback"]
    b = second["validated_canonical_readback"]
    assert a["unique_person_id"] == b["unique_person_id"]
    assert a["fact_receipts"] == 1
    assert b["fact_receipts"] == 2
    assert first["notes_added"] == 1 and second["notes_added"] == 0
    assert b["backlink_source_ids"] == ["date:2026-10-15", "date:2026-10-16"]


def test_maite_is_a_single_person_shared_by_core_and_tasks():
    _report, rows = _rows()
    row = rows["http-maite-3"]
    assert row["product_status"] == "completed"
    assert row["action_count"] == 2
    receipt = row["validated_canonical_readback"]
    assert receipt["fact_receipts"] == 2
    assert receipt["task_id"] in receipt["backlink_source_ids"]
    assert "date:2026-10-16" in receipt["backlink_source_ids"]
    assert row["notes_added"] == 2


def test_ambiguous_names_do_not_modify_any_canonical_file():
    _report, rows = _rows()
    for name in ("http-ana-4", "http-ambig-5"):
        row = rows[name]
        assert row["product_status"] == "needs_attention"
        assert row["expected_safe_abstention"] is True
        assert row["safe_no_write"] is True
        assert row["notes"] == []
        assert row["action_count"] == 0
        assert row["notes_added"] == 0


def test_main_runtime_guards_are_opt_in_and_pending_receipts_are_durable():
    src = (
        ROOT / "benchmarks/application_router/light_router_poc_20261016/p4_runtime_http_sandbox.py"
    ).read_text()
    assert "full_source_mutation_guard=True" in src
    code = (ROOT / "odyssey_runtime/composition.py").read_text()
    assert "full_source_mutation_guard: bool = False" in code
    assert "store.claim_mutation(request_id, fingerprint)" in code
    assert "store.finish_mutation_claim(request_id)" in code
