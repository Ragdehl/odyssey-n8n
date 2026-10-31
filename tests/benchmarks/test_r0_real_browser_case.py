"""Provider-free refusal tests for the paid R0 case adapter."""

from __future__ import annotations

import json
import subprocess
import sys

from scripts.odyssey_r0_browser_campaign import frozen_cases


def test_adapter_refuses_before_importing_or_calling_provider_without_transient_approval(tmp_path):
    case = frozen_cases()[0]
    receipt = tmp_path / "F01.json"
    receipt.write_text(
        json.dumps(
            {
                "case": case.id,
                "source_sha256": case.source_sha256,
                "outcome": "armed",
                "reserved_usd": 0.25,
            }
        ),
        encoding="utf-8",
    )
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/odyssey_r0_real_browser_case.py",
            "--case",
            case.id,
            "--source-sha256",
            case.source_sha256,
            "--receipt",
            str(receipt),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0
    trace = json.loads(completed.stdout.splitlines()[-1])
    assert trace["outcome"] == "failed"
    assert trace["provider_usage"] == []
    assert trace["forensics"]["error"] == "Refused"


def test_live_budget_allows_several_model_stages_without_an_unpriced_call(tmp_path):
    """Real production messages require Router, Temporal, Planner and review."""
    from types import SimpleNamespace
    from unittest.mock import patch

    from openai.resources.responses.responses import Responses

    from scripts.odyssey_r0_browser_campaign import arm_case
    from scripts.odyssey_r0_real_browser_case import MAX_CALLS, _usage_wrapper

    case = frozen_cases()[0]
    receipt = arm_case(tmp_path, case, 0.25)
    calls = []

    def fake_provider(self, **kwargs):
        calls.append(kwargs["text"]["format"]["name"])
        return SimpleNamespace(usage=SimpleNamespace(input_tokens=1200, output_tokens=400))

    assert MAX_CALLS >= 5
    with patch.object(Responses, "create", fake_provider):
        observed = []
        with _usage_wrapper(observed, receipt):
            for name in ("router", "temporal", "planner", "coverage", "speaker"):
                Responses.create(
                    None,
                    model="gpt-5.6-luna",
                    input="synthetic, no real provider",
                    max_output_tokens=1400,
                    text={"format": {"name": name}},
                )
    assert calls == ["router", "temporal", "planner", "coverage", "speaker"]
    assert len(observed) == 5
    assert all(row["usage_complete"] for row in observed)
    assert sum(row["charged_usd"] for row in observed) < 0.25


def test_live_budget_blocks_one_extremely_large_call_before_provider(tmp_path):
    from unittest.mock import patch

    import pytest
    from openai.resources.responses.responses import Responses

    from scripts.odyssey_r0_browser_campaign import arm_case
    from scripts.odyssey_r0_real_browser_case import Refused, _usage_wrapper

    case = frozen_cases()[0]
    receipt = arm_case(tmp_path, case, 0.25)
    with patch.object(Responses, "create", side_effect=AssertionError("network called")):
        with _usage_wrapper([], receipt):
            with pytest.raises(Refused, match="preflight veto"):
                Responses.create(
                    None,
                    model="gpt-5.6-sol",
                    input="synthetic" * 20000,
                    max_output_tokens=1400,
                    text={"format": {"name": "no-network"}},
                )


def test_r0_prewrite_probe_observes_active_real_p4_route_without_changing_outcome(tmp_path):
    """Frozen GPT responses, real P4 source coverage and real E3 no-write refusal."""
    from scripts.odyssey_r0_real_browser_case import _attach_prewrite_diagnostics
    from tests.runtime.test_whole_source_light_product_p4 import (
        RecordedClient,
        _actual_snapshot,
        _fixture,
    )

    source, route, plan, review = _actual_snapshot("maya_simple")
    repo, actor, executor, runtime = _fixture(tmp_path)
    rejected = {**review, "approved": False, "complete": False, "reason": "missing source fact"}
    executor.client = RecordedClient([route, plan, rejected, plan, rejected])
    evidence = {}
    _attach_prewrite_diagnostics(runtime, evidence)
    before = {p: repo.read_text(p) for p in repo.list_markdown_paths()}
    result = runtime.execute_product(source, "r0-test-prewrite-negative", "main", actor)
    assert result["status"] == "needs_attention"
    assert {p: repo.read_text(p) for p in repo.list_markdown_paths()} == before
    rows = evidence["core_prewrite_gates"]
    verdicts = [row for row in rows if row["gate"] == "coverage_verdict"]
    assert len(verdicts) == 2
    assert rows[-1]["gate"] == "coverage_rejected"
    assert any(row["gate"] == "proposal" for row in rows)
    assert verdicts[0]["values"]["approved"] is False
    assert verdicts[1]["values"]["attempt"] == 1
    assert all(len(row["delivery_sha256"]) == 64 for row in rows)
    assert all("source" not in row and "name" not in row for row in rows)


def test_r0_prewrite_probe_preserves_previous_callback(tmp_path):
    from scripts.odyssey_r0_real_browser_case import _attach_prewrite_diagnostics
    from tests.runtime.test_whole_source_light_product_p4 import _fixture

    _repo, _actor, executor, runtime = _fixture(tmp_path)
    existing = []
    executor.prewrite_diagnostic = lambda delivery, gate, values: existing.append(
        (delivery, gate, values)
    )
    evidence = {}
    _attach_prewrite_diagnostics(runtime, evidence)
    executor._observe_prewrite("request-one", "prewrite_accepted", facts=2)
    assert existing == [("request-one", "prewrite_accepted", {"facts": 2})]
    assert evidence["core_prewrite_gates"][0]["gate"] == "prewrite_accepted"
    reason = ValueError("New general validator reason (test fixture only)")
    assert executor._prewrite_reason_code(reason) == 0
    assert evidence["core_rejection_details"] == [
        {
            "error_class": "ValueError",
            "reason": str(reason),
            "unchanged_reason_code": 0,
        }
    ]


def test_r0_prewrite_probe_records_success_before_real_markdown_write(tmp_path):
    """The same product P4 path emits accepted verdict before actual Core/E3."""
    from scripts.odyssey_r0_real_browser_case import _attach_prewrite_diagnostics
    from tests.runtime.test_whole_source_light_product_p4 import (
        RecordedClient,
        _actual_snapshot,
        _fixture,
        _speaker,
    )

    source, route, plan, review = _actual_snapshot("maya_simple")
    repository, actor, executor, runtime = _fixture(tmp_path)
    executor.client = RecordedClient(
        [route, plan, review, _speaker(source, plan, base=1), _speaker(source, plan)]
    )
    recorded = {}
    _attach_prewrite_diagnostics(runtime, recorded)
    response = runtime.execute_product(source, "r0-probe-genuine-e3-write", "main", actor)
    assert response["status"] == "completed"
    rows = recorded["core_prewrite_gates"]
    assert any(r["gate"] == "coverage_verdict" and r["values"]["complete"] is True for r in rows)
    assert any(r["gate"] == "prewrite_accepted" for r in rows)
    assert any(
        "odyssey:fact request=r0-probe-genuine-e3-write" in repository.read_text(path)
        for path in repository.list_markdown_paths()
    )


def test_appended_family_case_has_separate_proven_wife_and_child_sets(tmp_path):
    """R29 has TWO disjoint canonical groups; no wife→children leakage."""
    from unittest.mock import patch

    from odyssey_core.whole_message_relationship_proof import verify_self_relationship
    from scripts.odyssey_r0_real_browser_case import (
        _prepare_additional_test_fixture,
        _r0_product,
    )

    with patch.dict("os.environ", {"OPENAI_API_KEY": "FAKE_NO_PROVIDER"}):
        with _r0_product(tmp_path) as (repo, actor, runtime):
            assert len(repo.list_markdown_paths()) == 13
            assert _prepare_additional_test_fixture("R29", repo, runtime) == 1
            assert len(repo.list_markdown_paths()) == 13
            bindings = runtime.hybrid_candidate_execute.bindings
            groups = {}
            for phrase in ("mis hijos", "mi mujer"):
                proof = verify_self_relationship(
                    "Hoy hemos estado con mis hijos y mi mujer.",
                    phrase,
                    repository=repo,
                    schema=runtime.canonical_schema,
                    actor=actor,
                    bindings=bindings,
                )
                groups[phrase] = {name for _id, name in proof.members}
            assert groups == {"mis hijos": {"Nina", "Pablo"}, "mi mujer": {"Bea"}}
            assert groups["mis hijos"].isdisjoint(groups["mi mujer"])


def test_appended_work_session_case_starts_with_actual_synthetic_task(tmp_path):
    from unittest.mock import patch

    from odyssey_core.notes import parse_note
    from scripts.odyssey_r0_real_browser_case import (
        _prepare_additional_test_fixture,
        _r0_product,
    )

    with patch.dict("os.environ", {"OPENAI_API_KEY": "FAKE_NO_PROVIDER"}):
        with _r0_product(tmp_path) as (repo, _actor, runtime):
            assert len(repo.list_markdown_paths()) == 13
            assert _prepare_additional_test_fixture("R30", repo, runtime) == 1
            assert len(repo.list_markdown_paths()) == 14
            task = parse_note(repo.read_text("Preparar informe Atlas.md"))
            assert task.metadata["id"] == "synthetic-task-atlas"
            assert task.metadata["type"] == "task"
            assert task.metadata["status"] == "pending"


def test_original_frozen_case_does_not_gain_extra_test_preconditions(tmp_path):
    from unittest.mock import patch

    from scripts.odyssey_r0_real_browser_case import (
        _prepare_additional_test_fixture,
        _r0_product,
    )

    with patch.dict("os.environ", {"OPENAI_API_KEY": "FAKE_NO_PROVIDER"}):
        with _r0_product(tmp_path) as (repo, _actor, runtime):
            before = {path: repo.read_text(path) for path in repo.list_markdown_paths()}
            assert _prepare_additional_test_fixture("F09", repo, runtime) == 0
            assert before == {path: repo.read_text(path) for path in repo.list_markdown_paths()}


def test_disposable_markdown_delta_keeps_content_and_detects_missing_or_invented_facts():
    from hashlib import sha256

    from scripts.odyssey_r0_real_browser_case import _synthetic_markdown_delta

    before = {"day.md": "--- day ---\nHoy vi a Manu.\n", "self.md": "--- self ---\n"}
    after = {
        "day.md": "--- day ---\nHoy vi a Manu. Fui al parque.\n",
        "self.md": before["self.md"],
        "Manu.md": "--- person ---\nNombre Manu\n",
    }
    changed = _synthetic_markdown_delta(before, after)
    assert [item["path"] for item in changed] == ["Manu.md", "day.md"]
    assert changed[0]["new_file"] is True
    assert changed[1]["after_sha256"] == sha256(after["day.md"].encode()).hexdigest()
    assert "Fui al parque" in changed[1]["after_markdown_excerpt"]
    assert all(item["path"] != "self.md" for item in changed)
    assert _synthetic_markdown_delta(after, after) == []
