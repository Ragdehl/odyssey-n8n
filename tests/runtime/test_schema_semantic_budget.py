"""Budgeted semantic paths over real synthetic Git journals, no real provider."""

from __future__ import annotations

import json
import os

import pytest

from odyssey_core.notes import parse_note
from odyssey_runtime.schema_backfill_interpreter import SemanticPropertyInterpreter
from odyssey_runtime.schema_backfill_jobs import LocalBackfillJobError
from odyssey_runtime.schema_semantic_budget import (
    BudgetedSemanticInterpreter,
    SemanticCallLedger,
)
from tests.runtime.test_schema_backfill_campaign import campaign, setup, step


class ProfessionGateway:
    def __init__(self, fail_on=None):
        self.calls = 0
        self.fail_on = fail_on

    def _complete(self, **kwargs):
        self.calls += 1
        if self.calls == self.fail_on:
            raise RuntimeError("model timed out after request")
        fact = kwargs["data"]["marked_atomic_facts"][0]
        if kwargs["name"] == "odyssey_schema_backfill_interpret_v1":
            return {
                "decision": "SET",
                "locator": fact["locator"],
                "quote": fact["text"],
                "value": "profesora",
            }
        return {
            "verdict": "APPROVE",
            "reason": "ENTAILED_CURRENT",
            "locator": fact["locator"],
            "quote": fact["text"],
            "value": "profesora",
        }


def limited(item, gateway, *, cap=3):
    return BudgetedSemanticInterpreter(
        interpreter=SemanticPropertyInterpreter(gateway),
        ledger=SemanticCallLedger(worker=item.worker, campaign_id="all-people", limit=cap),
    )


def test_signed_budget_bounds_multi_journal_and_survives_restart(tmp_path):
    state, repo, writer = setup(tmp_path, ["Ana trabaja como profesora."] * 4)
    run = campaign(state, repo, writer, segment_size=2)
    gateway = ProfessionGateway()
    run.stage(campaign_id="all-people", type_id="person", property_id="profesion")
    for _ in range(12):
        result = step(run, interpreter=limited(run, gateway))
        if result["finished"]:
            break
    else:
        raise AssertionError("Campaign did not stop")
    assert result["total"] == 4
    assert result["updated"] == 1
    assert result["deferred"] == 3
    assert result["status"] == "awaiting_ai"
    assert gateway.calls == 3
    assert limited(run, gateway).ledger.status() == {
        "reserved_calls": 3,
        "call_limit": 3,
    }
    assert parse_note(repo.read_text("0.md")).metadata["profesion"] == "profesora"
    assert all("profesion" not in parse_note(repo.read_text(f"{i}.md")).metadata for i in (1, 2, 3))
    restarted = campaign(state, repo, writer, segment_size=2)
    for _ in range(3):
        assert step(restarted, interpreter=limited(restarted, gateway)) == result
    assert gateway.calls == 3
    # Budget checkpoint stores only IDs and accounting, not source or model values.
    receipt = list((state / "schema-backfill-jobs").glob("*.semantic-budget.json"))
    assert len(receipt) == 1
    assert os.stat(receipt[0]).st_mode & 0o777 == 0o600
    assert "profesora" not in receipt[0].read_text()


def test_one_failed_sdk_request_remains_charged_and_no_replay(tmp_path):
    state, repo, writer = setup(tmp_path, ["Ana trabaja como profesora."])
    run = campaign(state, repo, writer)
    run.stage(campaign_id="all-people", type_id="person", property_id="profesion")
    gateway = ProfessionGateway(fail_on=1)
    with pytest.raises(RuntimeError, match="timed out"):
        step(run, interpreter=limited(run, gateway))
    assert limited(run, gateway).ledger.status()["reserved_calls"] == 1
    assert run.status("all-people")["deferred"] == 1
    restarted = campaign(state, repo, writer)
    assert step(restarted, interpreter=limited(restarted, gateway))["finished"]
    assert gateway.calls == 1
    assert "profesion" not in parse_note(repo.read_text("0.md")).metadata


def test_budget_rejects_tamper_new_limit_or_cross_actor(tmp_path):
    state, repo, writer = setup(tmp_path, ["Ana trabaja como profesora."])
    run = campaign(state, repo, writer)
    gateway = ProfessionGateway()
    run.stage(campaign_id="all-people", type_id="person", property_id="profesion")
    step(run, interpreter=limited(run, gateway, cap=4))
    assert gateway.calls == 2
    with pytest.raises(LocalBackfillJobError, match="scope|counters"):
        limited(run, gateway, cap=5).ledger.status()
    other = campaign(state, repo, writer, actor="other-user")
    assert limited(other, gateway, cap=4).ledger.status()["reserved_calls"] == 0
    receipt = next((state / "schema-backfill-jobs").glob("*.semantic-budget.json"))
    raw = json.loads(receipt.read_text())
    raw["calls"] = 0
    receipt.write_text(json.dumps(raw))
    with pytest.raises(LocalBackfillJobError, match="HMAC"):
        limited(run, gateway, cap=4).ledger.status()
    assert gateway.calls == 2


def test_empty_semantic_budget_and_invalid_limits_are_no_call(tmp_path):
    state, repo, writer = setup(tmp_path, ["Ana trabaja como profesora."])
    run = campaign(state, repo, writer)
    for cap in (0, -1, 37, True, 1.5):
        with pytest.raises(LocalBackfillJobError, match="call cap"):
            limited(run, ProfessionGateway(), cap=cap)
    valid = limited(run, ProfessionGateway(), cap=2)
    assert valid.ledger.status()["reserved_calls"] == 0
    assert not list((state / "schema-backfill-jobs").glob("*.semantic-budget.json"))
