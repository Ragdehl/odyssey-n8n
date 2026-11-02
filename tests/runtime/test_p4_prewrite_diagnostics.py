"""P4 DEV prewrite verdict diagnostics do not change Writer or disclose sources."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import stat

from odyssey_runtime.dev_p4_diagnostics import record_dev_p4_prewrite_gate
from tests.runtime.test_whole_source_light_product_p4 import (
    RecordedClient,
    _actual_snapshot,
    _fixture,
    _speaker,
)


def test_dev_log_contains_only_bounded_verdicts_and_not_original_source(tmp_path, monkeypatch):
    root = tmp_path / "runtime"
    root.mkdir()
    monkeypatch.setenv("ODYSSEY_DEPLOYMENT_ENV", "DEV")
    monkeypatch.setenv("ODYSSEY_LIGHT_SOURCE_V1", "1")
    monkeypatch.setenv("ODYSSEY_RUNTIME_ROOT", str(root))
    request_id = "private-request-text-no-log"
    record_dev_p4_prewrite_gate(
        request_id,
        "coverage_verdict",
        {"approved": False, "attempt": 1, "facts": 2, "source_text": "SECRET NAME"},
    )
    data = (root / "p4-prewrite-gates.jsonl").read_text()
    entry = json.loads(data)
    assert entry == {
        "request_digest": hashlib.sha256(request_id.encode()).hexdigest()[:16],
        "gate": "coverage_verdict",
        "approved": False,
        "attempt": 1,
        "facts": 2,
    }
    assert "SECRET" not in data and request_id not in data
    assert stat.S_IMODE(os.stat(root / "p4-prewrite-gates.jsonl").st_mode) == 0o600
    monkeypatch.setenv("ODYSSEY_DEPLOYMENT_ENV", "PROD")
    record_dev_p4_prewrite_gate("another-id", "prewrite_accepted", {"facts": 10})
    assert (root / "p4-prewrite-gates.jsonl").read_text() == data


def test_mocked_coverage_rejection_records_exact_prewrite_gate_without_writes(tmp_path):
    source, route, plan, review = _actual_snapshot("maya_simple")
    repo, actor, service, runtime = _fixture(tmp_path)
    plan = copy.deepcopy(plan)
    plan["unresolved"] = ["unknown"]
    review = {**review, "approved": False, "complete": False}
    service.client = RecordedClient([route, plan, review])
    records = []
    service.prewrite_diagnostic = lambda delivery, gate, fields: records.append(
        (delivery, gate, fields)
    )
    response = runtime.execute_product(source, "p4-diagnostic-coverage", "main", actor)
    assert response["status"] == "needs_attention"
    assert not any("odyssey:fact" in repo.read_text(p) for p in repo.list_markdown_paths())
    assert [r[1] for r in records] == ["proposal", "coverage_verdict", "coverage_rejected"]
    assert records[-2][2]["approved"] is False


def test_mocked_speaker_veto_is_visible_but_still_never_writes(tmp_path):
    source, route, plan, review = _actual_snapshot("maya_simple")
    repo, actor, service, runtime = _fixture(tmp_path)
    wrong = _speaker(source, plan)
    wrong["facts"][0]["source_quote"] = "not in source"
    service.client = RecordedClient([route, plan, review, wrong, _speaker(source, plan)])
    records = []
    service.prewrite_diagnostic = lambda delivery, gate, fields: records.append(gate)
    result = runtime.execute_product(source, "p4-diagnostic-speaker", "main", actor)
    assert result["status"] == "needs_attention"
    assert records[-1] == "speaker_contract"
    assert not any("odyssey:fact" in repo.read_text(p) for p in repo.list_markdown_paths())


def test_dev_log_is_bounded_and_ignores_invalid_gate_and_source_content(tmp_path, monkeypatch):
    root = tmp_path / "runtime"
    root.mkdir()
    monkeypatch.setenv("ODYSSEY_DEPLOYMENT_ENV", "DEV")
    monkeypatch.setenv("ODYSSEY_LIGHT_SOURCE_V1", "1")
    monkeypatch.setenv("ODYSSEY_RUNTIME_ROOT", str(root))
    record_dev_p4_prewrite_gate("id-1", "prompt-content", {"facts": 2})
    assert not (root / "p4-prewrite-gates.jsonl").exists()
    (root / "p4-prewrite-gates.jsonl").write_bytes(b"x" * 263_000)
    record_dev_p4_prewrite_gate("id-2", "proposal", {"facts": 1})
    assert (root / "p4-prewrite-gates.jsonl").stat().st_size < 1000


def test_reason_codes_are_static_and_never_include_person_name():
    from odyssey_core.whole_message_coverage import WholeMessageCoverageError
    from odyssey_core.whole_message_identity_guard import UnprovenPersonIdentityError
    from odyssey_core.whole_message_speaker_proof import WholeMessageSpeakerError
    from odyssey_runtime.whole_source_light import WholeSourceLightExecutor

    code = WholeSourceLightExecutor._prewrite_reason_code
    assert (
        code(WholeMessageSpeakerError("Independent reviewers disagree on speaker or assertion"))
        == 21
    )
    assert code(WholeMessageCoverageError("Non-affirmative input is not a completed event")) == 10
    assert (
        code(UnprovenPersonIdentityError("UNPROVEN_PARTIAL_CANONICAL_IDENTITY: name private")) == 31
    )
    assert code(UnprovenPersonIdentityError("AMBIGUOUS_CANONICAL_PERSON: name private")) == 32
    # The live generic guard emits ENTITY, not the old PERSON-only prefix.
    assert code(UnprovenPersonIdentityError("AMBIGUOUS_CANONICAL_ENTITY: Atlas")) == 32
    assert code(UnprovenPersonIdentityError("UNSUPPORTED_CANONICAL_TYPE_CHOICE: Atlas")) == 33
    assert code(UnprovenPersonIdentityError("USER INPUT CAN NEVER BE LOGGED")) == 0


def test_only_task_source_with_two_operations_has_visible_scope_veto_without_writes(tmp_path):
    repo, actor, service, runtime = _fixture(tmp_path)
    source = "Llamar al electricista y revisar factura"
    route = {
        "capabilities": ["tasks"],
        "interpretation": "joint",
        "reason": "single",
        "app_scopes": [],
        "self_relation_span": None,
    }
    task_only = {
        "only_task_semantics": True,
        "exactly_one_operation": False,
        "source_quote": source,
    }
    service.client = RecordedClient([route, task_only])
    gates = []
    service.prewrite_diagnostic = lambda delivery, gate, values: gates.append((gate, values))
    response = runtime.execute_product(source, "p4-diagnostic-two-tasks", "main", actor)
    assert response["status"] == "needs_attention"
    assert gates == [
        ("task_scope_verdict", {"task_only": True, "one_operation": False, "source_aligned": True}),
        ("task_scope_rejected", {}),
    ]
    assert not any("odyssey:fact" in repo.read_text(p) for p in repo.list_markdown_paths())
