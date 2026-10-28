"""Autonomous cross-journal campaign, strictly synthetic/isolated Core/E3 Git."""

from __future__ import annotations

import hashlib
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


def test_semantic_provider_is_reviewed_across_two_signed_children(tmp_path):
    """A single approved campaign can mix explicit and reviewed semantic values."""
    from odyssey_runtime.schema_backfill_interpreter import SemanticPropertyInterpreter

    state, repo, writer = setup(tmp_path, ["Profesión: médica", "Ana trabaja como profesora."] * 2)
    run = campaign(state, repo, writer, segment_size=2)

    class ReviewedGateway:
        calls = 0

        def _complete(self, **kwargs):
            self.calls += 1
            original = kwargs["data"]["marked_atomic_facts"][0]
            if kwargs["name"] == "odyssey_schema_backfill_interpret_v1":
                return {
                    "decision": "SET",
                    "locator": original["locator"],
                    "quote": original["text"],
                    "value": "profesora",
                }
            return {
                "verdict": "APPROVE",
                "reason": "ENTAILED_CURRENT",
                "locator": original["locator"],
                "quote": original["text"],
                "value": "profesora",
            }

    provider = ReviewedGateway()
    interpreter = SemanticPropertyInterpreter(provider)
    run.stage(campaign_id="all-people", type_id="person", property_id="profesion")
    for _ in range(12):
        receipt = step(run, interpreter=interpreter)
        if receipt["finished"]:
            break
    else:
        raise AssertionError("Campaign did not finish")
    assert receipt["updated"] == receipt["total"] == 4
    assert provider.calls == 4  # Only two natural-language rows, two passes each.
    assert parse_note(repo.read_text("1.md")).metadata["profesion"] == "profesora"
    assert parse_note(repo.read_text("3.md")).metadata["profesion"] == "profesora"
    assert step(run, interpreter=interpreter) == receipt
    assert provider.calls == 4  # Signed replay cannot incur model costs.


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
    with pytest.raises(LocalBackfillJobError, match="journal is missing"):
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


def test_campaign_fingerprint_binds_each_path_to_id_and_deleted_state(tmp_path):
    """Swap live/deleted docs without changing public live IDs or eligibility."""
    from odyssey_core.schema_retrospection import scan_schema_sources

    state, repo, writer = setup(tmp_path, ["Profesión: médica"] * 4)
    sample = parse_note(repo.read_text("3.md"))
    repo.create_text(
        "a-document.md",
        serialize_note(
            Note(
                {
                    **sample.metadata,
                    "id": "live-doc",
                    "name": "Live document",
                    "type": "document",
                    "deleted": False,
                },
                sample.content,
            )
        ),
    )
    repo.create_text(
        "b-document.md",
        serialize_note(
            Note(
                {
                    **sample.metadata,
                    "id": "inactive-doc",
                    "name": "Deleted document",
                    "type": "document",
                    "deleted": True,
                },
                sample.content,
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
            "baseline-live-deleted-documents",
        ],
        cwd=repo.root,
        check=True,
    )

    def scan():
        return scan_schema_sources(
            repository=repo,
            schema=writer.schema,
            kind="backfill_property",
            target_type_id="person",
            property_id="profesion",
            limit=25,
        )

    initial_page = scan()
    item = campaign(state, repo, writer)
    item.stage(campaign_id="all-people", type_id="person", property_id="profesion")
    assert step(item)["updated"] == 1
    assert step(item)["updated"] == 2
    first = parse_note(repo.read_text("a-document.md"))
    second = parse_note(repo.read_text("b-document.md"))
    repo.replace_text(
        "a-document.md",
        serialize_note(
            Note({**first.metadata, "id": "inactive-doc", "deleted": True}, first.content)
        ),
    )
    repo.replace_text(
        "b-document.md",
        serialize_note(
            Note({**second.metadata, "id": "live-doc", "deleted": False}, second.content)
        ),
    )
    after_page = scan()
    assert initial_page.source_note_ids == after_page.source_note_ids
    assert initial_page.scanned_paths == after_page.scanned_paths
    # Two person notes were correctly enriched by the first child; the
    # non-target document swap itself adds no eligible property candidates.
    assert tuple(x.note_id for x in after_page.eligible_notes) == tuple(
        x.note_id for x in initial_page.eligible_notes[2:]
    )
    # The conventional active-ID list remains identical even though the
    # path-to-ID/deleted relation changed, which the new fingerprint must reject.
    with pytest.raises(LocalBackfillJobError, match="physical source identities changed"):
        step(item)
    assert item.status("all-people")["updated"] == 2


@pytest.mark.parametrize("missing", ["completed_child", "terminal_empty_child"])
def test_finished_campaign_requires_all_hmac_children_for_status(tmp_path, missing):
    """A sealed parent must never certify completion after child evidence loss."""
    state, repo, writer = setup(tmp_path, ["Profesión: médica"] * 4)
    item = campaign(state, repo, writer)
    item.stage(campaign_id="all-people", type_id="person", property_id="profesion")
    assert run_to_end(item)[-1]["status"] == "complete"
    parent = item._read("all-people")
    index = 0 if missing == "completed_child" else parent["segment_index"]
    child_id = item._child_id(item.worker.scope, "all-people", index, parent["generation"])
    item.worker._path(child_id).unlink()
    with pytest.raises(LocalBackfillJobError, match="journal missing"):
        item.status("all-people")
    with pytest.raises(LocalBackfillJobError, match="journal missing"):
        step(item)


@pytest.mark.parametrize("replay", ["completed_child", "terminal_receipt"])
def test_campaign_rejects_valid_hmac_receipt_replayed_from_prior_campaign_run(tmp_path, replay):
    """An OLD but correctly signed receipt must not authenticate a NEW parent."""
    state, repo, writer = setup(tmp_path, ["Profesión: médica"] * 4)
    originals = {name: repo.read_text(name) for name in repo.list_markdown_paths()}
    first = campaign(state, repo, writer)
    first.stage(campaign_id="all-people", type_id="person", property_id="profesion")
    assert run_to_end(first)[-1]["status"] == "complete"
    parent = first._read("all-people")
    old_index = 0 if replay == "completed_child" else parent["segment_index"]
    old_job = first._child_id(first.worker.scope, "all-people", old_index, parent["generation"])
    old_path = first.worker._path(old_job)
    old_signed_bytes = old_path.read_bytes()

    # Reset only the DISPOSABLE campaign receipts, while retaining the local
    # HMAC key and physical vault identity. Start another valid incarnation
    # using the SAME deterministic job IDs but changed canonical identity.
    for path in (state / "schema-backfill-jobs").glob("*.json"):
        path.unlink()
    for name, body in originals.items():
        repo.replace_text(name, body)
    changed = parse_note(repo.read_text("0.md"))
    repo.replace_text(
        "0.md",
        serialize_note(Note({**changed.metadata, "id": "persona-changed"}, changed.content)),
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
            "synthetic-second-incarnation",
        ],
        cwd=repo.root,
        check=True,
    )
    second = campaign(state, repo, writer)
    second.stage(campaign_id="all-people", type_id="person", property_id="profesion")
    assert run_to_end(second)[-1]["status"] == "complete"
    assert second._read("all-people")["totals"]["updated"] == 4

    latest_parent = second._read("all-people")
    latest_job = second._child_id(
        second.worker.scope, "all-people", old_index, latest_parent["generation"]
    )
    assert latest_job != old_job
    latest_path = second.worker._path(latest_job)
    assert latest_path.read_bytes() != old_signed_bytes
    latest_path.write_bytes(old_signed_bytes)
    # The old receipt has a VALID signature for the old generation, but is
    # unauthorized at the current generation's immutable child identity.
    assert second.worker._read(latest_path, old_job) is not None
    with pytest.raises(LocalBackfillJobError, match="Journal does not match actor/schema"):
        second.status("all-people")
    with pytest.raises(LocalBackfillJobError, match="Journal does not match actor/schema"):
        step(second)


def test_campaign_can_finish_without_candidates_and_requires_terminal_receipt(tmp_path):
    """No E3 writes: terminal proof still belongs to signed parent."""
    state, repo, writer = setup(tmp_path, ["Profesión: médica"] * 2)
    for name in repo.list_markdown_paths():
        note = parse_note(repo.read_text(name))
        repo.replace_text(
            name,
            serialize_note(Note({**note.metadata, "profesion": "existente"}, note.content)),
        )
    item = campaign(state, repo, writer)
    terminal = item.stage(campaign_id="all-people", type_id="person", property_id="profesion")
    assert terminal["status"] == "complete" and terminal["finished"] is True
    assert terminal["total"] == terminal["updated"] == 0
    assert item.status("all-people") == terminal
    parent = item._read("all-people")
    child_id = item._child_id(
        item.worker.scope, "all-people", parent["segment_index"], parent["generation"]
    )
    item.worker._path(child_id).unlink()
    with pytest.raises(LocalBackfillJobError, match="terminal proof journal missing"):
        item.status("all-people")


def test_active_child_replay_from_previous_generation_fails_before_status_or_write(tmp_path):
    """A valid HMAC from a previous campaign must never certify new progress."""
    state, repo, writer = setup(tmp_path, ["Profesión: médica"] * 4)
    originals = {path: repo.read_text(path) for path in repo.list_markdown_paths()}
    first = campaign(state, repo, writer)
    first.stage(campaign_id="all-people", type_id="person", property_id="profesion")
    assert step(first)["updated"] == 1
    old_id = first._read("all-people")["active_segment"]
    old_signed_child = first.worker._path(old_id).read_bytes()

    # Create a second legitimate campaign on restored synthetic Markdown while
    # preserving the original HMAC key: the replay is cryptographically valid.
    for path in (state / "schema-backfill-jobs").glob("*.json"):
        path.unlink()
    for path, original in originals.items():
        repo.replace_text(path, original)
    subprocess.run(["git", "add", "-A"], cwd=repo.root, check=True, capture_output=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@localhost",
            "commit",
            "-qm",
            "restore-synthetic-notes-for-new-generation",
        ],
        cwd=repo.root,
        check=True,
        capture_output=True,
    )
    second = campaign(state, repo, writer)
    second.stage(campaign_id="all-people", type_id="person", property_id="profesion")
    parent = second._read("all-people")
    new_id = parent["active_segment"]
    assert old_id != new_id
    assert second.status("all-people")["updated"] == 0
    second.worker._path(new_id).write_bytes(old_signed_child)
    assert second.worker._read(second.worker._path(new_id), old_id) is not None
    with pytest.raises(LocalBackfillJobError, match="Journal does not match actor/schema"):
        second.status("all-people")
    with pytest.raises(LocalBackfillJobError, match="Journal does not match actor/schema"):
        step(second)
    assert {path: repo.read_text(path) for path in originals} == originals


def test_active_child_signed_manifest_change_is_rejected_without_writes(tmp_path):
    """Even a re-signed current child cannot choose different source evidence."""
    state, repo, writer = setup(tmp_path, ["Profesión: médica"] * 4)
    original = {path: repo.read_text(path) for path in repo.list_markdown_paths()}
    item = campaign(state, repo, writer)
    item.stage(campaign_id="all-people", type_id="person", property_id="profesion")
    active_id = item._read("all-people")["active_segment"]
    child_path = item.worker._path(active_id)
    child = item.worker._required(child_path, active_id)
    child["rows"][0]["hash"] = "0" * 64
    item.worker._write(child_path, child)
    assert item.worker._read(child_path, active_id) is not None
    with pytest.raises(LocalBackfillJobError, match="active signed source manifest mismatch"):
        item.status("all-people")
    with pytest.raises(LocalBackfillJobError, match="active signed source manifest mismatch"):
        step(item)
    assert {path: repo.read_text(path) for path in original} == original


def test_previous_v1_finished_campaign_remains_readable_after_generation_upgrade(tmp_path):
    """Old completed campaign proofs are not silently discarded by V2 protection."""
    state, repo, writer = setup(tmp_path, ["Profesión: médica"] * 4)
    item = campaign(state, repo, writer)
    item.stage(campaign_id="all-people", type_id="person", property_id="profesion")
    completed = run_to_end(item)[-1]
    parent = item._read("all-people")
    nonce = parent["generation"]
    chain = "0" * 64
    terminal = None
    for index in range(parent["segment_index"] + 1):
        new_id = item._child_id(item.worker.scope, "all-people", index, nonce)
        old_id = item._child_id(item.worker.scope, "all-people", index)
        child = item.worker._required(item.worker._path(new_id), new_id)
        child["job_id"] = old_id
        for row_index, row in enumerate(child["rows"]):
            if row["request"] is not None:
                row["request"] = (
                    f"schema-{hashlib.sha256(f'{item.worker.scope}:{old_id}'.encode()).hexdigest()[:16]}-{row_index:05d}"
                )
        item.worker._write(item.worker._path(old_id), child)
        if index < parent["segment_index"]:
            chain = item._chain_next(chain, child)
        else:
            terminal = item.worker._integrity(child)
    parent["completed_chain"] = chain
    parent["terminal_receipt_hash"] = terminal
    del parent["generation"]
    del parent["active_manifest_hash"]
    parent["version"] = 1
    item._save("all-people", parent)
    assert item.status("all-people") == completed
    assert step(item) == completed


def test_previous_v1_active_campaign_requires_explicit_safe_replan(tmp_path):
    """Do not implicitly trust an old HMAC child with no generation binding."""
    state, repo, writer = setup(tmp_path, ["Profesión: médica"] * 4)
    original = {path: repo.read_text(path) for path in repo.list_markdown_paths()}
    item = campaign(state, repo, writer)
    item.stage(campaign_id="all-people", type_id="person", property_id="profesion")
    parent = item._read("all-people")
    del parent["generation"]
    del parent["active_manifest_hash"]
    parent["version"] = 1
    item._save("all-people", parent)
    with pytest.raises(LocalBackfillJobError, match="Invalid campaign state or owner"):
        item.status("all-people")
    with pytest.raises(LocalBackfillJobError, match="Invalid campaign state or owner"):
        step(item)
    assert {path: repo.read_text(path) for path in original} == original


@pytest.mark.parametrize("poison", ["missing", "re-signed"])
def test_later_active_child_rejects_missing_or_changed_previous_journal(tmp_path, poison):
    """Never report or write active progress when an older signed child is lost."""
    state, repo, writer = setup(tmp_path, ["Profesión: médica"] * 5)
    item = campaign(state, repo, writer)
    item.stage(campaign_id="all-people", type_id="person", property_id="profesion")
    assert step(item)["updated"] == 1
    assert step(item)["updated"] == 2
    assert step(item)["updated"] == 3
    parent = item._read("all-people")
    assert parent["segment_index"] == 1 and parent["active_segment"] is not None
    previous_id = item._child_id(item.worker.scope, "all-people", 0, parent["generation"])
    previous_path = item.worker._path(previous_id)
    if poison == "missing":
        previous_path.unlink()
        failure = "Campaign completed journal missing"
    else:
        receipt = item.worker._required(previous_path, previous_id)
        receipt["rows"][0]["hash"] = "0" * 64
        item.worker._write(previous_path, receipt)
        failure = "Campaign signed parent/child evidence mismatch"
    before = {path: repo.read_text(path) for path in repo.list_markdown_paths()}
    before_git = subprocess.check_output(
        ["git", "rev-list", "--count", "HEAD"], cwd=repo.root, text=True
    )
    with pytest.raises(LocalBackfillJobError, match=failure):
        item.status("all-people")
    with pytest.raises(LocalBackfillJobError, match=failure):
        step(item)
    assert {path: repo.read_text(path) for path in before} == before
    assert (
        subprocess.check_output(["git", "rev-list", "--count", "HEAD"], cwd=repo.root, text=True)
        == before_git
    )
