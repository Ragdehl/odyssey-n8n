"""Autonomous cross-journal campaign, strictly synthetic/isolated Core/E3 Git."""

from __future__ import annotations

import json
import subprocess

import pytest

from odyssey_core.notes import Note, parse_note, serialize_note
from odyssey_core.schema_retrospection import SchemaRetrospectionError
from odyssey_runtime.schema_backfill_campaign import LocalBackfillCampaign
from odyssey_runtime.schema_backfill_jobs import LocalBackfillJobError
from tests.runtime.test_schema_backfill_jobs import ACTOR, NOW, job, setup


def campaign(state, repo, writer, *, segment_size=2, actor="profile-a"):
    return LocalBackfillCampaign(
        worker=job(state, repo, writer, actor=actor), segment_size=segment_size
    )


def step(item, interpreter=None):
    return item.advance(
        campaign_id="all-people",
        type_id="person",
        property_id="profesion",
        actor=ACTOR,
        now=NOW,
        interpreter=interpreter,
    )


def run_to_end(item, max_steps=40):
    results = []
    for _ in range(max_steps):
        receipt = step(item)
        results.append(receipt)
        if receipt["finished"]:
            return results
    raise AssertionError("Campaign did not terminate")


def test_campaign_seals_multiple_independently_undoable_git_journals(tmp_path):
    state, repo, writer = setup(tmp_path, ["Profesión: médica"] * 6)
    worker = campaign(state, repo, writer)
    assert (
        worker.stage(campaign_id="all-people", type_id="person", property_id="profesion")["status"]
        == "in_progress"
    )
    assert worker.status("all-people")["total"] == 2
    assert step(worker)["updated"] == 1
    restarted = campaign(state, repo, writer)
    receipts = run_to_end(restarted)
    assert receipts[-1]["updated"] == 6
    assert receipts[-1]["total"] == 6
    assert receipts[-1]["status"] == "complete"
    assert receipts[-1]["finished"] is True
    assert (
        sum(
            parse_note(repo.read_text(f"{i}.md")).metadata["profesion"] == "médica"
            for i in range(6)
        )
        == 6
    )
    assert (
        subprocess.check_output(
            ["git", "rev-list", "--count", "HEAD"],
            cwd=repo.root,
            text=True,
        ).strip()
        == "7"
    )
    # Three bounded write journals, an empty completion-proof journal, and
    # the signed parent receipt (no empty journals authorize source edits).
    journals = list((state / "schema-backfill-jobs").glob("*.json"))
    assert len(journals) == 5
    for record in journals:
        assert "médica" not in record.read_text()
    assert step(restarted) == receipts[-1]


def test_campaign_never_retries_deferred_notes_in_a_later_segment(tmp_path):
    state, repo, writer = setup(
        tmp_path,
        [
            "Voy a viajar mañana",
            "Profesión: médica",
            "Trabajo remoto",
            "Profesión: médica",
            "Me gusta cocinar",
            "Profesión: médica",
        ],
    )
    worker = campaign(state, repo, writer)
    worker.stage(campaign_id="all-people", type_id="person", property_id="profesion")
    result = run_to_end(worker)
    assert result[-1]["status"] == "awaiting_ai"
    assert result[-1]["finished"] is True
    assert result[-1]["updated"] == 3
    assert result[-1]["deferred"] == 3
    assert result[-1]["total"] == 6
    assert (
        subprocess.check_output(
            ["git", "rev-list", "--count", "HEAD"],
            cwd=repo.root,
            text=True,
        ).strip()
        == "4"
    )
    for idx in (0, 2, 4):
        assert "profesion" not in parse_note(repo.read_text(f"{idx}.md")).metadata
    assert step(worker) == result[-1]


def test_campaign_refuses_cross_segment_added_or_duplicated_identity(tmp_path):
    state, repo, writer = setup(tmp_path, ["Profesión: médica"] * 4)
    worker = campaign(state, repo, writer)
    worker.stage(campaign_id="all-people", type_id="person", property_id="profesion")
    assert step(worker)["updated"] == 1
    assert step(worker)["updated"] == 2
    # Invariant: the next journal cannot select an invented new path/identity
    # even though the previous two notes already have the property.
    sample = parse_note(repo.read_text("3.md"))
    repo.create_text(
        "new.md",
        serialize_note(Note({**sample.metadata, "id": "new-id"}, sample.content)),
    )
    with pytest.raises(LocalBackfillJobError, match="identities changed"):
        step(worker)
    assert worker.status("all-people")["updated"] == 2
    assert "profesion" not in parse_note(repo.read_text("2.md")).metadata


def test_campaign_does_not_migrate_to_different_actor_or_schema(tmp_path):
    state, repo, writer = setup(tmp_path, ["Profesión: médica"] * 4)
    worker = campaign(state, repo, writer)
    worker.stage(campaign_id="all-people", type_id="person", property_id="profesion")
    assert campaign(state, repo, writer, actor="profile-b").status("all-people") is None
    with pytest.raises(LocalBackfillJobError, match="target changed"):
        worker.stage(campaign_id="all-people", type_id="person", property_id="otro")
    with pytest.raises(LocalBackfillJobError, match="configuration"):
        campaign(state, repo, writer, segment_size=0)
    with pytest.raises(LocalBackfillJobError, match="Invalid campaign"):
        campaign(state, repo, writer, segment_size=3).status("all-people")


def test_campaign_signature_and_missing_child_block_resume(tmp_path):
    state, repo, writer = setup(tmp_path, ["Profesión: médica"] * 4)
    worker = campaign(state, repo, writer)
    worker.stage(campaign_id="all-people", type_id="person", property_id="profesion")
    step(worker)
    folder = state / "schema-backfill-jobs"
    receipt = next(folder.glob("*.campaign.json"))
    document = json.loads(receipt.read_text())
    document["segment_index"] += 1
    receipt.write_text(json.dumps(document))
    with pytest.raises(LocalBackfillJobError, match="HMAC"):
        worker.status("all-people")


def test_campaign_reconciles_crash_after_actual_git_commit_without_rewriting(tmp_path, monkeypatch):
    state, repo, writer = setup(tmp_path, ["Profesión: médica"] * 4)
    worker = campaign(state, repo, writer)
    worker.stage(campaign_id="all-people", type_id="person", property_id="profesion")
    original_apply = writer.apply

    def interrupted(**kwargs):
        original_apply(**kwargs)
        raise RuntimeError("simulated process crash after Git")

    monkeypatch.setattr(writer, "apply", interrupted)
    with pytest.raises(RuntimeError, match="simulated process crash"):
        step(worker)
    monkeypatch.setattr(writer, "apply", original_apply)
    restarted = campaign(state, repo, writer)
    # First replay only reconciles the existing intent; never repeats Git.
    assert step(restarted)["updated"] == 1
    final = run_to_end(restarted)[-1]
    assert final["updated"] == 4
    assert (
        subprocess.check_output(
            ["git", "rev-list", "--count", "HEAD"],
            cwd=repo.root,
            text=True,
        ).strip()
        == "5"
    )


def test_campaign_recovers_child_published_before_parent_frontier(tmp_path, monkeypatch):
    """The deterministic segment ID recovers a persisted child after a crash."""
    state, repo, writer = setup(tmp_path, ["Profesión: médica"] * 5)
    worker = campaign(state, repo, writer)
    worker.stage(campaign_id="all-people", type_id="person", property_id="profesion")
    step(worker)
    step(worker)
    original = worker.worker._stage_segment

    def interrupt_after_child(**kwargs):
        child = original(**kwargs)
        if kwargs["after_path"] is not None:
            raise RuntimeError("crash between child staging and parent HMAC")
        return child

    monkeypatch.setattr(worker.worker, "_stage_segment", interrupt_after_child)
    with pytest.raises(RuntimeError, match="crash between"):
        step(worker)
    resumed = campaign(state, repo, writer)
    assert resumed.status("all-people")["updated"] == 2
    final = run_to_end(resumed)[-1]
    assert final["updated"] == final["total"] == 5
    assert (
        subprocess.check_output(
            ["git", "rev-list", "--count", "HEAD"], cwd=repo.root, text=True
        ).strip()
        == "6"
    )


def test_campaign_cross_segment_duplicate_is_not_silently_requeued(tmp_path):
    state, repo, writer = setup(tmp_path, ["Profesión: médica"] * 5)
    worker = campaign(state, repo, writer)
    worker.stage(campaign_id="all-people", type_id="person", property_id="profesion")
    step(worker)
    step(worker)
    original = parse_note(repo.read_text("3.md"))
    repo.replace_text(
        "3.md", serialize_note(Note({**original.metadata, "id": "persona-0"}, original.content))
    )
    with pytest.raises(
        (SchemaRetrospectionError, LocalBackfillJobError), match="Duplicate|identit"
    ):
        step(worker)
    assert worker.status("all-people")["updated"] == 2
    assert (
        subprocess.check_output(
            ["git", "rev-list", "--count", "HEAD"], cwd=repo.root, text=True
        ).strip()
        == "3"
    )


def test_campaign_missing_active_journal_stops_without_fabricating_progress(tmp_path):
    state, repo, writer = setup(tmp_path, ["Profesión: médica"] * 4)
    worker = campaign(state, repo, writer)
    worker.stage(campaign_id="all-people", type_id="person", property_id="profesion")
    job_folder = state / "schema-backfill-jobs"
    child = next(p for p in job_folder.glob("*.json") if not p.name.endswith(".campaign.json"))
    child.unlink()
    with pytest.raises(LocalBackfillJobError, match="journal is missing"):
        worker.status("all-people")
    with pytest.raises(LocalBackfillJobError, match="journal missing"):
        step(worker)


def test_campaign_does_not_follow_changed_schema_hash(tmp_path):
    """A confirmed property cannot silently migrate into a new schema revision."""
    from odyssey_core.git_history import GitHistoryRecorder
    from odyssey_core.schema_auto_backfill import AutomaticPropertyBackfill

    state, repo, writer = setup(tmp_path, ["Profesión: médica"] * 4)
    original = campaign(state, repo, writer)
    original.stage(campaign_id="all-people", type_id="person", property_id="profesion")
    changed_schema = json.loads(json.dumps(writer.schema))
    person = next(t for t in changed_schema["types"] if t["id"] == "person")
    person["properties"].append(
        {
            "id": "nuevo",
            "value_type": "string",
            "description": "Nueva propiedad",
            "required": False,
        }
    )
    changed_writer = AutomaticPropertyBackfill(
        repository=repo, schema=changed_schema, history=GitHistoryRecorder(repo.root)
    )
    with pytest.raises(LocalBackfillJobError, match="owner"):
        campaign(state, repo, changed_writer).status("all-people")


def test_existing_v1_job_keeps_its_original_receipts_when_vault_expands(tmp_path, monkeypatch):
    """No automatic migration of a previously approved legacy journal."""
    from odyssey_core import schema_retrospection
    from tests.runtime.test_schema_backfill_notes_vertical import (
        ALICE,
        fixture,
        request,
    )

    app, repo, _ = fixture(tmp_path)
    assert app.notes("schema_backfill", request("stage"), ALICE)["total"] == 2
    monkeypatch.setattr(schema_retrospection, "_MAX_PROGRESS_IDS", 1)
    # Even though the vault now exceeds the routing threshold, the signed V1
    # plan that already exists is resumed verbatim, not silently replaced.
    reply = app.notes("schema_backfill", request("status"), ALICE)
    assert reply["total"] == 2
    assert "segment" not in reply
