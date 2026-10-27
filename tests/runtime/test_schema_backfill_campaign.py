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
    with pytest.raises(LocalBackfillJobError, match="identities changed|eligibility changed"):
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


def test_campaign_rejects_newly_eligible_note_behind_frontier(tmp_path):
    """An originally occupied property cannot become a skipped candidate."""
    state, repo, writer = setup(tmp_path, ["Profesión: ocupada"] * 4)
    before = parse_note(repo.read_text("0.md"))
    repo.replace_text(
        "0.md",
        serialize_note(Note({**before.metadata, "profesion": "preexistente"}, before.content)),
    )
    subprocess.run(["git", "add", "-A"], cwd=repo.root, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@localhost",
            "commit",
            "-qm",
            "preexisting-property",
        ],
        cwd=repo.root,
        check=True,
    )
    item = campaign(state, repo, writer)
    item.stage(campaign_id="all-people", type_id="person", property_id="profesion")
    assert step(item)["updated"] == 1
    assert step(item)["updated"] == 2
    changed = parse_note(repo.read_text("0.md"))
    repo.replace_text(
        "0.md",
        serialize_note(
            Note(
                {key: value for key, value in changed.metadata.items() if key != "profesion"},
                changed.content,
            )
        ),
    )
    with pytest.raises(LocalBackfillJobError, match="eligibility changed"):
        step(item)
    assert item.status("all-people")["updated"] == 2


def test_campaign_rejects_eligibility_change_ahead_of_frontier(tmp_path):
    """A future initial candidate cannot silently disappear mid-campaign."""
    state, repo, writer = setup(tmp_path, ["Profesión: médica"] * 4)
    item = campaign(state, repo, writer)
    item.stage(campaign_id="all-people", type_id="person", property_id="profesion")
    assert step(item)["updated"] == 1
    assert step(item)["updated"] == 2
    source = parse_note(repo.read_text("3.md"))
    repo.replace_text(
        "3.md",
        serialize_note(Note({**source.metadata, "profesion": "ocupada"}, source.content)),
    )
    with pytest.raises(LocalBackfillJobError, match="eligibility changed"):
        step(item)
    assert item.status("all-people")["updated"] == 2


def test_campaign_still_progresses_when_completed_child_contains_deferred(tmp_path):
    """An awaiting_ai child cannot stop the subsequent bounded segments."""
    state, repo, writer = setup(
        tmp_path, ["Sin datos", "Profesión: médica", "Profesión: médica", "Profesión: médica"]
    )
    item = campaign(state, repo, writer)
    item.stage(campaign_id="all-people", type_id="person", property_id="profesion")
    assert step(item)["deferred"] == 1
    boundary = step(item)
    assert boundary["finished"] is False
    assert boundary["status"] == "in_progress"
    assert boundary["updated"] == 1
    final = run_to_end(item)[-1]
    assert final["finished"] is True
    assert final["status"] == "awaiting_ai"
    assert final["updated"] == 3
    assert final["deferred"] == 1


def test_mixed_type_and_nonnumeric_paths_detect_new_candidate_behind_frontier(tmp_path):
    """A previously excluded document cannot become a skipped Person after cursor."""
    state, repo, writer = setup(tmp_path, ["Profesión: médica"] * 4)
    mapping = {
        "0.md": "a-antes.md",
        "1.md": "b-persona.md",
        "2.md": "m-persona.md",
        "3.md": "z-persona.md",
    }
    for old, new in mapping.items():
        (repo.root / old).rename(repo.root / new)
    old = parse_note(repo.read_text("a-antes.md"))
    repo.replace_text(
        "a-antes.md", serialize_note(Note({**old.metadata, "type": "document"}, old.content))
    )
    subprocess.run(["git", "add", "-A"], cwd=repo.root, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@localhost",
            "commit",
            "-qm",
            "nonnumeric-mixed-type-baseline",
        ],
        cwd=repo.root,
        check=True,
    )
    item = campaign(state, repo, writer)
    initial = item.stage(campaign_id="all-people", type_id="person", property_id="profesion")
    assert initial["total"] == 2
    assert step(item)["updated"] == 1
    assert step(item)["updated"] == 2
    changed = parse_note(repo.read_text("a-antes.md"))
    repo.replace_text(
        "a-antes.md", serialize_note(Note({**changed.metadata, "type": "person"}, changed.content))
    )
    with pytest.raises(LocalBackfillJobError, match="eligibility changed"):
        step(item)
    assert item.status("all-people")["updated"] == 2
    assert "profesion" not in parse_note(repo.read_text("z-persona.md")).metadata


def test_recovery_of_first_child_rejects_vault_changed_before_parent_proof(tmp_path, monkeypatch):
    """A crash cannot adopt a new 00.md behind an unsealed first frontier."""
    state, repo, writer = setup(tmp_path, ["Profesión: médica"] * 4)
    original = campaign(state, repo, writer)
    stage_child = original.worker._stage_segment

    def publish_then_interrupt(**kwargs):
        stage_child(**kwargs)
        raise RuntimeError("interrupt after first child publication")

    monkeypatch.setattr(original.worker, "_stage_segment", publish_then_interrupt)
    with pytest.raises(RuntimeError, match="first child"):
        original.stage(campaign_id="all-people", type_id="person", property_id="profesion")
    assert original.status("all-people")["total"] == 0
    old = parse_note(repo.read_text("3.md"))
    repo.create_text(
        "00.md",
        serialize_note(
            Note(
                {**old.metadata, "id": "persona-new", "name": "New between 0 and 1"},
                old.content,
            )
        ),
    )
    subprocess.run(["git", "add", "-A"], cwd=repo.root, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@localhost",
            "commit",
            "-qm",
            "external-mid-frontier-note",
        ],
        cwd=repo.root,
        check=True,
    )
    restarted = campaign(state, repo, writer)
    with pytest.raises(LocalBackfillJobError, match="staged child inventory changed"):
        restarted.stage(campaign_id="all-people", type_id="person", property_id="profesion")
    assert restarted.status("all-people")["updated"] == 0
    assert "profesion" not in parse_note(repo.read_text("00.md")).metadata


def test_campaign_rejects_external_removal_of_property_it_already_wrote(tmp_path):
    """A previous successful E3 update may not silently become incomplete."""
    state, repo, writer = setup(tmp_path, ["Profesión: médica"] * 4)
    item = campaign(state, repo, writer)
    item.stage(campaign_id="all-people", type_id="person", property_id="profesion")
    assert step(item)["updated"] == 1
    assert step(item)["updated"] == 2
    written = parse_note(repo.read_text("0.md"))
    assert written.metadata["profesion"] == "médica"
    repo.replace_text(
        "0.md",
        serialize_note(
            Note(
                {key: value for key, value in written.metadata.items() if key != "profesion"},
                written.content,
            )
        ),
    )
    with pytest.raises(LocalBackfillJobError, match="previously written property was removed"):
        step(item)
    assert item.status("all-people")["updated"] == 2
    assert "profesion" not in parse_note(repo.read_text("2.md")).metadata


def test_fifo_at_campaign_checkpoint_is_rejected_without_blocking(tmp_path):
    """Fail before an O_RDONLY FIFO open, including a bounded hang regression."""
    import os
    import signal

    state, repo, writer = setup(tmp_path, ["Profesión: médica"] * 4)
    item = campaign(state, repo, writer)
    path = item._path("all-people")
    os.mkfifo(path, mode=0o600)

    def unsafe_open_timeout(_signal, _frame):
        raise AssertionError("FIFO checkpoint caused a blocking read")

    previous = signal.signal(signal.SIGALRM, unsafe_open_timeout)
    signal.setitimer(signal.ITIMER_REAL, 2.0)
    try:
        with pytest.raises(LocalBackfillJobError, match="Unsafe campaign checkpoint"):
            item.status("all-people")
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)
