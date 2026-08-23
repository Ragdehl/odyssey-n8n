"""Deterministic tests for the Phase 15.3 oracle and resume-safe evidence runner."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from benchmarks.phase15_3_capability_delegation import run_benchmark
from benchmarks.phase15_3_capability_delegation.benchmark import (
    BenchmarkContractError,
    load_cases,
    production_request,
)
from benchmarks.phase15_3_capability_delegation.evaluate import evaluate
from benchmarks.phase15_3_capability_delegation.targeted import evaluate_targeted

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads((ROOT / "config/note-schema.json").read_text(encoding="utf-8"))


def _selection(*, related: bool = False) -> dict:
    """Build a complete direct or related-note selection fixture."""
    return {
        "entity": None if related else "Marta",
        "query": "notas relacionadas con Marta" if related else "Marta",
        "type": None if related else "person",
        "filters": [],
        "link_scope": (
            {
                "anchor": {"entity": "Marta", "query": "Marta", "type": "person", "filters": []},
                "direction": "both",
                "max_depth": 1,
            }
            if related
            else None
        ),
    }


def _plan(action: dict) -> dict:
    """Wrap one raw action as a complete RequestPlan fixture."""
    return {"actions": [action], "limitations": []}


def test_related_oracles_reject_lost_or_weakened_link_selection() -> None:
    """Protect A07/A08 against free-text-only graph intent after delegation."""
    direct = _plan({"kind": "retrieve", "plan": _selection(related=True)})
    delegated = _plan(
        {
            "kind": "delegate",
            "request": "Cuenta las notas relacionadas con Marta.",
            "selection": _selection(related=True),
        }
    )
    assert evaluate("related_retrieve", direct, SCHEMA) == ("PASS", [])
    assert evaluate("related_count", delegated, SCHEMA) == ("PASS", [])
    lost = copy.deepcopy(delegated)
    lost["actions"][0]["selection"]["link_scope"] = None
    assert evaluate("related_count", lost, SCHEMA)[0] == "FAIL"
    wrong_depth = copy.deepcopy(direct)
    wrong_depth["actions"][0]["plan"]["link_scope"]["max_depth"] = 2
    assert evaluate("related_retrieve", wrong_depth, SCHEMA)[0] == "FAIL"
    missing_anchor_type = copy.deepcopy(delegated)
    missing_anchor_type["actions"][0]["selection"]["link_scope"]["anchor"]["type"] = None
    assert evaluate("related_count", missing_anchor_type, SCHEMA)[0] == "FAIL"


def test_oracle_fails_closed_for_action_inversions_and_unknown_expectations() -> None:
    """Reject capability inversions rather than treating valid JSON as a pass."""
    retrieve = _plan({"kind": "retrieve", "plan": _selection()})
    delegate = _plan(
        {"kind": "delegate", "request": "Cuenta las compras de Carrefour.", "selection": None}
    )
    assert evaluate("purchase_count", retrieve, SCHEMA)[0] == "FAIL"
    assert evaluate("purchase_retrieve", delegate, SCHEMA)[0] == "FAIL"
    assert evaluate("unknown", retrieve, SCHEMA) == ("FAIL", ["unknown_expectation"])


class _FakeClient:
    """Supply deterministic structured responses while recording scheduled provider calls."""

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.responses = self

    def create(self, **request: object) -> SimpleNamespace:
        """Record one synthetic provider call and return valid JSON evidence."""
        self.calls.append(request)
        return SimpleNamespace(
            output_text=json.dumps(
                _plan({"kind": "delegate", "request": "specialized work", "selection": None})
            ),
            usage=None,
        )


def _metadata() -> dict:
    """Return matching runner metadata for test-client evidence."""
    return {
        "created_at": "2026-08-24T00:00:00+00:00",
        "benchmark_version": "1.0.0",
        "model": "gpt-5.6-sol",
        "reasoning_effort": "low",
        "store": False,
        "planned_calls": 18,
        "automatic_retries": False,
        "production_prompt": "render_request_planner_prompt",
        "production_structured_outputs": "request_plan_json_schema",
        "openai_sdk_version": "test-client",
    }


def _resume_row(case: dict[str, str]) -> dict:
    """Build the immutable case identity needed to validate a resumed evidence row."""
    _, _, digests = production_request(case)
    return {
        "test_id": case["id"],
        "expectation": case["expect"],
        "request": case["request"],
        "identity_digests": digests,
    }


def test_runner_resumes_only_missing_cases_and_never_recalls_complete_rows(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Schedule only missing unique IDs and make a complete run a zero-call no-op."""
    monkeypatch.setattr(run_benchmark, "RESULTS_DIR", tmp_path)
    directory = tmp_path / "partial"
    directory.mkdir()
    (directory / "metadata.json").write_text(json.dumps(_metadata()), encoding="utf-8")
    cases = load_cases()
    completed = [_resume_row(case) for case in cases[:-1]]
    (directory / "raw_results.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in completed), encoding="utf-8"
    )
    client = _FakeClient()
    run_benchmark.run("partial", client)
    assert len(client.calls) == 1
    run_benchmark.run("partial", client)
    assert len(client.calls) == 1


def test_runner_rejects_duplicate_unknown_and_mismatched_resume_evidence(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Fail closed before a resume could append to invalid historical evidence."""
    monkeypatch.setattr(run_benchmark, "RESULTS_DIR", tmp_path)
    for name, rows, metadata in (
        ("duplicate", [{"test_id": "A17"}, {"test_id": "A17"}], _metadata()),
        ("unknown", [{"test_id": "AXX"}], _metadata()),
        ("mismatch", [], _metadata() | {"model": "other"}),
    ):
        directory = tmp_path / name
        directory.mkdir()
        (directory / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
        (directory / "raw_results.jsonl").write_text(
            "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
        )
        with pytest.raises(BenchmarkContractError):
            run_benchmark.run(name, _FakeClient())

    digest_directory = tmp_path / "digest"
    digest_directory.mkdir()
    (digest_directory / "metadata.json").write_text(json.dumps(_metadata()), encoding="utf-8")
    bad_digest = _resume_row(load_cases()[0])
    bad_digest["identity_digests"] = {"prompt_sha256": "changed"}
    (digest_directory / "raw_results.jsonl").write_text(
        json.dumps(bad_digest) + "\n", encoding="utf-8"
    )
    with pytest.raises(BenchmarkContractError):
        run_benchmark.run("digest", _FakeClient())


def test_targeted_oracle_proves_direct_related_and_delegated_boundaries() -> None:
    """Fail closed when graph structure is lost, invented, or attached to the wrong action."""
    direct = _plan({"kind": "retrieve", "plan": _selection()})
    related = _plan({"kind": "retrieve", "plan": _selection(related=True)})
    delegated_related = _plan(
        {
            "kind": "delegate",
            "request": "Contar notas relacionadas con Marta.",
            "selection": _selection(related=True),
        }
    )
    ordinary = _plan(
        {
            "kind": "delegate",
            "request": "Contar cuántas compras hice en Carrefour.",
            "selection": None,
        }
    )
    assert evaluate_targeted("direct_marta", direct, SCHEMA) == ("PASS", [])
    assert evaluate_targeted("related_retrieve", related, SCHEMA) == ("PASS", [])
    assert evaluate_targeted("related_delegate", delegated_related, SCHEMA) == ("PASS", [])
    assert evaluate_targeted("ordinary_delegate", ordinary, SCHEMA) == ("PASS", [])

    lost = copy.deepcopy(delegated_related)
    lost["actions"][0]["selection"]["link_scope"] = None
    assert evaluate_targeted("related_delegate", lost, SCHEMA)[0] == "FAIL"
    invented = copy.deepcopy(ordinary)
    invented["actions"][0]["selection"] = _selection(related=True)
    assert evaluate_targeted("ordinary_delegate", invented, SCHEMA)[0] == "FAIL"
    assert evaluate_targeted("unknown", direct, SCHEMA) == ("FAIL", ["unknown_expectation"])
