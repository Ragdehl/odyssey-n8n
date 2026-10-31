"""Provider-free refusal tests for the paid R0 case adapter."""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

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


def test_appended_generic_read_case_has_preexisting_canonical_self_relationship(tmp_path):
    """R32 read-only fixture is real Markdown, not model-suggested membership."""
    from unittest.mock import patch

    from odyssey_core.notes import parse_note
    from odyssey_core.whole_message_relationship_proof import verify_self_relationship
    from scripts.odyssey_r0_real_browser_case import (
        _prepare_additional_test_fixture,
        _r0_product,
    )

    with patch.dict("os.environ", {"OPENAI_API_KEY": "FAKE_NO_PROVIDER"}):
        with _r0_product(tmp_path) as (repo, actor, product):
            assert len(repo.list_markdown_paths()) == 13
            assert _prepare_additional_test_fixture("R32", repo, product) == 1
            note = parse_note(repo.read_text("Alex.md"))
            assert "Mi padre es [[Eric]]." in note.content
            proof = verify_self_relationship(
                "¿Quién es mi padre?",
                "mi padre",
                repository=repo,
                schema=product.canonical_schema,
                actor=actor,
                bindings=product.hybrid_candidate_execute.bindings,
            )
            assert proof.members == (("fixture-person-eric", "Eric"),)
            assert len(repo.list_markdown_paths()) == 13


@pytest.mark.parametrize("rebuild_after_fixture", [False, True])
def test_r32_actual_core_read_recovers_current_canonical_member_without_writing(
    tmp_path, rebuild_after_fixture
):
    """Full real Core retrieval, index and serialization with a fake relevance AI only.

    The planner is replaced by one typed, verified read plan; the semantic-set
    relevance provider is replaced by the existing test selector, NOT Core's
    real relational resolver, Markdown source projection, context index or E3.
    This is offline integration proof, never a fresh GPT/browser acceptance.
    """
    from unittest.mock import patch

    from odyssey_core.request_planning import (
        RelationalReference,
        RequestPlan,
        RetrieveAction,
        SelectionCriteria,
    )
    from odyssey_runtime import composition
    from odyssey_runtime.serialization import application_result_to_response
    from scripts.odyssey_r0_real_browser_case import (
        _prepare_additional_test_fixture,
        _r0_product,
    )
    from tests.core.test_relational_application import RelevantFactSelector

    original = "¿Quién es mi padre?"
    plan = RequestPlan(
        (
            RetrieveAction(
                SelectionCriteria(
                    None,
                    "mi padre",
                    "person",
                    (),
                    None,
                    relational_reference=RelationalReference("mi padre", "self", None, "one"),
                )
            ),
        ),
        (),
    )
    with (
        patch.dict("os.environ", {"OPENAI_API_KEY": "FAKE_NO_PROVIDER"}),
        patch.object(
            composition,
            "OpenAILunaSemanticSetSelector",
            side_effect=lambda: RelevantFactSelector("mi padre"),
        ),
    ):
        with _r0_product(tmp_path) as (repo, actor, product):
            assert _prepare_additional_test_fixture("R32", repo, product) == 1
            before = {p: repo.read_text(p) for p in repo.list_markdown_paths()}
            if rebuild_after_fixture:
                product.refresh_indexes()
            result = product.core_execute(original, "r32-read", actor, None, fixed_plan=plan)
            projected = application_result_to_response(result)
            assert projected["product_outcome"] == "ANSWER"
            assert projected["status"] == "completed"
            assert len(result.action_results) == 1
            retrieval = result.action_results[0].retrieval
            assert retrieval is not None
            assert [item.id for item in retrieval.items] == ["fixture-person-eric"]
            assert [item.primary_name for item in retrieval.items] == ["Eric"]
            assert projected["actions"][0]["retrieval"]["items"][0]["primary_name"] == "Eric"
            assert not result.affected_stable_note_ids
            assert {p: repo.read_text(p) for p in repo.list_markdown_paths()} == before


def test_generic_core_read_abstention_keeps_its_observed_stage_through_safe_fallback(tmp_path):
    """A Core planner clarification must not disappear when P4 also declines.

    This test deliberately has no provider call, no personal vault and no
    per-relationship router. The fake model merely abstains at the existing
    planner boundary; source fallback remains separately guarded.
    """
    from types import SimpleNamespace
    from unittest.mock import patch

    from odyssey_core.application import ApplicationResult, ApplicationStatus
    from odyssey_core.request_planning import PlannerClarification
    from odyssey_runtime import composition
    from scripts.odyssey_r0_real_browser_case import _r0_product

    with patch.dict("os.environ", {"OPENAI_API_KEY": "FAKE_NO_PROVIDER"}):
        with _r0_product(tmp_path) as (_repo, actor, product):
            captured = []
            product.hybrid_candidate_execute = lambda *args: (
                captured.append(args[0])
                or ApplicationResult(
                    args[1],
                    ApplicationStatus.NEEDS_ATTENTION,
                    (),
                    (),
                    clarification_code="INCOMPLETE_EVIDENCE",
                )
            )
            planner = SimpleNamespace(
                plan=lambda *_args: PlannerClarification("UNREPRESENTABLE_REQUEST")
            )
            with patch.object(
                composition.OpenAIRequestPlanner,
                "from_environment",
                return_value=planner,
            ):
                answer = product.execute("¿Quién es mi padre?", "read-abstained", "main", actor)
            assert captured == ["¿Quién es mi padre?"]
            assert answer.status is ApplicationStatus.NEEDS_ATTENTION
            assert not answer.affected_stable_note_ids
            read_stage = next(
                item for item in answer.operational.stages if item.name == "core.read_preflight"
            )
            assert read_stage.outcome.value == "unavailable"
            assert read_stage.error_category == "CoreReadPreflightUnavailable"


def test_r0_browser_must_open_a_note_really_changed_by_the_same_message():
    """Opening any existing note on Notes cannot prove a source write."""
    from scripts.odyssey_r0_real_browser_case import _browser_opened_affected_note

    before = {
        "old.md": '---\nid: "old-id"\nname: "Old"\ntype: person\n---\n\nOld fact',
        "updated.md": '---\nid: "new-id"\nname: "New"\ntype: project\n---\n\nBefore',
    }
    after = {**before, "updated.md": before["updated.md"] + "\nNew fact"}
    assert not _browser_opened_affected_note(before, after, "old-id")
    assert not _browser_opened_affected_note(before, after, None)
    assert _browser_opened_affected_note(before, after, "new-id")
    assert _browser_opened_affected_note(before, before, None)
