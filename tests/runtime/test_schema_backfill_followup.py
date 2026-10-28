"""Completed deterministic backfills must never be reopened to enrich old deferrals."""

from __future__ import annotations

import hashlib

import pytest

from odyssey_core.notes import parse_note
from odyssey_runtime.schema_backfill_interpreter import SemanticPropertyInterpreter
from odyssey_runtime.schema_backfill_jobs import LocalBackfillJobError
from odyssey_runtime.schema_semantic_budget import BudgetedSemanticInterpreter, SemanticCallLedger
from tests.runtime.test_schema_backfill_campaign import campaign, run_to_end, setup
from tests.runtime.test_schema_backfill_jobs import ACTOR, NOW, advance, job
from tests.runtime.test_schema_semantic_budget import ProfessionGateway

TYPE = "person"
PROP = "profesion"


def semantic_followup_id(original: str) -> str:
    return hashlib.sha256(f"semantic-followup-v1:{original}".encode()).hexdigest()[:48]


def budgeted(run, gateway, *, cid: str, cap: int = 12):
    return BudgetedSemanticInterpreter(
        interpreter=SemanticPropertyInterpreter(gateway),
        ledger=SemanticCallLedger(worker=run.worker, campaign_id=cid, limit=cap),
    )


def advance_campaign(run, cid, interpreter):
    return run.advance(
        campaign_id=cid,
        type_id=TYPE,
        property_id=PROP,
        actor=ACTOR,
        now=NOW,
        interpreter=interpreter,
    )


def test_closed_multichild_followup_only_old_deferred_without_touching_original(tmp_path):
    state, repo, writer = setup(
        tmp_path,
        ["Profesión: médica", "Ana trabaja como profesora."] * 3,
    )
    run = campaign(state, repo, writer, segment_size=2)
    run.stage(campaign_id="all-people", type_id=TYPE, property_id=PROP)
    baseline = run_to_end(run)
    assert baseline[-1]["status"] == "awaiting_ai"
    assert baseline[-1]["updated"] == 3 and baseline[-1]["deferred"] == 3
    original_files = {
        p.name: p.read_bytes() for p in (state / "schema-backfill-jobs").glob("*.json")
    }
    original_git_count = repo.read_text("1.md")
    cid = semantic_followup_id("all-people")
    staged = run.stage_followup(
        campaign_id=cid,
        original_id="all-people",
        origin_kind="campaign",
        type_id=TYPE,
        property_id=PROP,
    )
    assert staged["total"] == 2 and staged["updated"] == 0
    assert repo.read_text("1.md") == original_git_count  # stage never writes
    gateway = ProfessionGateway()
    adapter = budgeted(run, gateway, cid=cid)
    for _ in range(15):
        result = advance_campaign(run, cid, adapter)
        if result["finished"]:
            break
    else:
        raise AssertionError("Follow-up never sealed its last child")
    assert result["status"] == "complete"
    assert result["updated"] == 3 and result["deferred"] == 0 and result["total"] == 3
    assert gateway.calls == 6 and adapter.ledger.status()["reserved_calls"] == 6
    for i in range(6):
        assert parse_note(repo.read_text(f"{i}.md")).metadata["profesion"] == (
            "médica" if i % 2 == 0 else "profesora"
        )
    original_after = {
        p.name: p.read_bytes()
        for p in (state / "schema-backfill-jobs").glob("*.json")
        if p.name in original_files
    }
    assert original_after == original_files
    assert run.status("all-people") == baseline[-1]
    assert advance_campaign(campaign(state, repo, writer), cid, adapter) == result
    assert gateway.calls == 6


def test_followup_on_closed_legacy_v1_with_own_approved_journals(tmp_path):
    state, repo, writer = setup(tmp_path, ["Ana trabaja como profesora."])
    original = job(state, repo, writer)
    original.stage(job_id="historial", type_id=TYPE, property_id=PROP)
    assert advance(original)["status"] == "awaiting_ai"
    original_path = original._path("historial")
    original_bytes = original_path.read_bytes()
    cid = semantic_followup_id("historial")
    followup = campaign(state, repo, writer)
    assert (
        followup.stage_followup(
            campaign_id=cid,
            original_id="historial",
            origin_kind="legacy",
            type_id=TYPE,
            property_id=PROP,
        )["pending"]
        == 1
    )
    gateway = ProfessionGateway()
    adapter = budgeted(followup, gateway, cid=cid)
    for _ in range(6):
        done = advance_campaign(followup, cid, adapter)
        if done["finished"]:
            break
    assert done["updated"] == 1 and done["status"] == "complete"
    assert gateway.calls == 2
    assert original_path.read_bytes() == original_bytes
    assert original.status("historial")["deferred"] == 1


def test_stale_original_deferred_source_blocks_followup_without_writing(tmp_path):
    state, repo, writer = setup(tmp_path, ["Ana trabaja como profesora."] * 3)
    original = campaign(state, repo, writer)
    original.stage(campaign_id="all-people", type_id=TYPE, property_id=PROP)
    assert run_to_end(original)[-1]["deferred"] == 3
    # Editing a deferred source after the original receipt invalidates its CAS.
    old = repo.read_text("1.md")
    (repo.root / "1.md").write_text(old + "\n")
    cid = semantic_followup_id("all-people")
    with pytest.raises(LocalBackfillJobError, match="deferred source changed"):
        original.stage_followup(
            campaign_id=cid,
            original_id="all-people",
            origin_kind="campaign",
            type_id=TYPE,
            property_id=PROP,
        )
    assert "profesion" not in parse_note(repo.read_text("0.md")).metadata


def test_changed_original_signature_blocks_followup_replay(tmp_path):
    state, repo, writer = setup(tmp_path, ["Ana trabaja como profesora."])
    original = campaign(state, repo, writer)
    original.stage(campaign_id="all-people", type_id=TYPE, property_id=PROP)
    assert run_to_end(original)[-1]["status"] == "awaiting_ai"
    cid = semantic_followup_id("all-people")
    original.stage_followup(
        campaign_id=cid,
        original_id="all-people",
        origin_kind="campaign",
        type_id=TYPE,
        property_id=PROP,
    )
    original_parent = original._path("all-people")
    original_parent.write_text(
        original_parent.read_text().replace('"finished":true', '"finished":false')
    )
    with pytest.raises(LocalBackfillJobError, match="HMAC|Invalid campaign"):
        original.status(cid)


def test_followup_from_other_actor_cannot_use_original_deferred_receipt(tmp_path):
    state, repo, writer = setup(tmp_path, ["Ana trabaja como profesora."])
    original = campaign(state, repo, writer)
    original.stage(campaign_id="all-people", type_id=TYPE, property_id=PROP)
    assert run_to_end(original)[-1]["finished"]
    other = campaign(state, repo, writer, actor="another-profile")
    with pytest.raises(LocalBackfillJobError, match="missing|closed source"):
        other.stage_followup(
            campaign_id=semantic_followup_id("all-people"),
            original_id="all-people",
            origin_kind="campaign",
            type_id=TYPE,
            property_id=PROP,
        )


def test_lost_original_terminal_proof_blocks_followup_even_after_staging(tmp_path):
    state, repo, writer = setup(tmp_path, ["Ana trabaja como profesora."] * 3)
    original = campaign(state, repo, writer, segment_size=2)
    original.stage(campaign_id="all-people", type_id=TYPE, property_id=PROP)
    assert run_to_end(original)[-1]["finished"]
    cid = semantic_followup_id("all-people")
    original.stage_followup(
        campaign_id=cid,
        original_id="all-people",
        origin_kind="campaign",
        type_id=TYPE,
        property_id=PROP,
    )
    sealed = original._read("all-people")
    terminal = original._child_id(
        original.worker.scope,
        "all-people",
        sealed["segment_index"],
        sealed["generation"],
    )
    original.worker._path(terminal).unlink()
    with pytest.raises(LocalBackfillJobError, match="terminal proof journal missing"):
        original.status(cid)
    assert "profesion" not in parse_note(repo.read_text("0.md")).metadata


def test_future_deferred_source_changed_between_segments_fails_closed(tmp_path):
    state, repo, writer = setup(tmp_path, ["Ana trabaja como profesora."] * 4)
    original = campaign(state, repo, writer, segment_size=2)
    original.stage(campaign_id="all-people", type_id=TYPE, property_id=PROP)
    assert run_to_end(original)[-1]["deferred"] == 4
    cid = semantic_followup_id("all-people")
    original.stage_followup(
        campaign_id=cid,
        original_id="all-people",
        origin_kind="campaign",
        type_id=TYPE,
        property_id=PROP,
    )
    gateway = ProfessionGateway()
    interpreter = budgeted(original, gateway, cid=cid, cap=8)
    assert advance_campaign(original, cid, interpreter)["updated"] == 1
    assert advance_campaign(original, cid, interpreter)["updated"] == 2
    assert gateway.calls == 4
    previous = repo.read_text("2.md")
    (repo.root / "2.md").write_text(previous + "\n")
    # The next child must verify the exact original version; no charge/write.
    with pytest.raises(LocalBackfillJobError, match="deferred source changed"):
        advance_campaign(original, cid, interpreter)
    assert gateway.calls == 4
    assert "profesion" not in parse_note(repo.read_text("2.md")).metadata
