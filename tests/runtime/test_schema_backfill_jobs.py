"""Restartable autonomous enrichment against disposable local Git Markdown."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from odyssey_core.git_history import GitHistoryRecorder
from odyssey_core.notes import Note, parse_note, serialize_note
from odyssey_core.schema_auto_backfill import AutomaticPropertyBackfill
from odyssey_core.storage import VaultRepository
from odyssey_runtime.schema_backfill_interpreter import SemanticPropertyInterpreter
from odyssey_runtime.schema_backfill_jobs import (
    LocalBackfillJob,
    LocalBackfillJobError,
    SemanticProviderDeferred,
)

ROOT = Path(__file__).resolve().parents[2]
NOW = "2026-10-26T12:00:00+00:00"
ACTOR = {"human": None, "app": "odyssey-local-autofill"}


def setup(tmp_path: Path, messages: list[str]):
    vault = tmp_path / "vault"
    state = tmp_path / "private-state"
    vault.mkdir()
    state.mkdir()
    schema = json.loads((ROOT / "config/note-schema.json").read_text())
    person = next(t for t in schema["types"] if t["id"] == "person")
    person["properties"].append(
        {
            "id": "profesion",
            "value_type": "string",
            "required": False,
            "description": "Profesión actual",
            "filterable": True,
        }
    )
    for i, text in enumerate(messages):
        note = Note(
            {
                "id": f"persona-{i}",
                "name": f"Persona {i}",
                "type": "person",
                "created_at": NOW,
                "updated_at": NOW,
                "schema_version": 3,
                "created_by": ACTOR,
                "updated_by": ACTOR,
                "revision": 1,
                "aliases": [],
                "tags": [],
            },
            f"# Added 26-10-2026\n- {text}\n<!-- odyssey:fact request=src{i} ordinal=0 -->\n",
        )
        (vault / f"{i}.md").write_text(serialize_note(note))
    for args in (
        ("init", "-q"),
        ("add", "."),
        (
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@localhost",
            "commit",
            "--allow-empty",
            "-q",
            "-m",
            "initial",
        ),
    ):
        subprocess.run(
            ["git", *args], cwd=vault, capture_output=True, text=True, check=True, timeout=10
        )
    repo = VaultRepository(vault)
    writer = AutomaticPropertyBackfill(
        repository=repo, schema=schema, history=GitHistoryRecorder(vault)
    )
    return state, repo, writer


def job(state, repo, writer, actor="profile-a"):
    return LocalBackfillJob(state_root=state, repository=repo, writer=writer, actor_id=actor)


def advance(worker, *, model=None):
    return worker.advance(
        job_id="historial",
        type_id="person",
        property_id="profesion",
        actor=ACTOR,
        now=NOW,
        interpreter=model,
    )


def test_stage_is_read_only_and_resume_uses_frozen_source_ids(tmp_path):
    state, repo, writer = setup(
        tmp_path,
        [
            "Profesión: médica",
            "Profesión: ingeniero",
            "Ana fue arquitecta",
        ],
    )
    before = {path: repo.read_text(path) for path in repo.list_markdown_paths()}
    worker = job(state, repo, writer)
    initial = worker.stage(job_id="historial", type_id="person", property_id="profesion")
    assert initial["total"] == 3 and initial["pending"] == 3
    checkpoint = next((state / "schema-backfill-jobs").glob("*.json"))
    body = checkpoint.read_text()
    assert "médica" not in body and "Ana fue" not in body
    assert {path: repo.read_text(path) for path in repo.list_markdown_paths()} == before
    assert advance(worker)["updated"] == 1
    restarted = job(state, repo, writer)
    assert (
        restarted.stage(job_id="historial", type_id="person", property_id="profesion")["updated"]
        == 1
    )
    assert advance(restarted)["updated"] == 2
    assert advance(restarted)["status"] == "awaiting_ai"
    assert restarted.status("historial")["deferred"] == 1
    assert parse_note(repo.read_text("0.md")).metadata["profesion"] == "médica"
    assert parse_note(repo.read_text("1.md")).metadata["profesion"] == "ingeniero"
    assert parse_note(repo.read_text("2.md")).metadata.get("profesion") is None
    assert advance(restarted)["updated"] == 2
    assert (
        subprocess.check_output(
            ["git", "rev-list", "--count", "HEAD"], cwd=repo.root, text=True
        ).strip()
        == "3"
    )


def test_crash_after_real_canonical_write_reconciles_without_double_write(tmp_path, monkeypatch):
    state, repo, writer = setup(tmp_path, ["Profesión: médica"])
    worker = job(state, repo, writer)
    worker.stage(job_id="historial", type_id="person", property_id="profesion")
    real = writer.apply

    def simulate_crash(**kwargs):
        receipt = real(**kwargs)
        assert receipt.status == "updated"
        raise RuntimeError("process lost after physical write")

    monkeypatch.setattr(writer, "apply", simulate_crash)
    with pytest.raises(RuntimeError, match="process lost"):
        advance(worker)
    monkeypatch.setattr(writer, "apply", real)
    resumed = job(state, repo, writer)
    assert resumed.status("historial")["status"] == "attention"
    # A proven write is reconciled by the next ordinary worker step,
    # without asking the user or issuing a second physical mutation.
    result = advance(resumed)
    assert result["updated"] == 1 and result["status"] == "complete"
    assert advance(resumed)["updated"] == 1
    assert parse_note(repo.read_text("0.md")).metadata["revision"] == 2
    assert (
        subprocess.check_output(
            ["git", "rev-list", "--count", "HEAD"], cwd=repo.root, text=True
        ).strip()
        == "2"
    )


def test_crash_before_physical_write_can_safely_retry_after_reconciliation(tmp_path, monkeypatch):
    state, repo, writer = setup(tmp_path, ["Profesión: médica"])
    worker = job(state, repo, writer)
    worker.stage(job_id="historial", type_id="person", property_id="profesion")
    real = writer.apply

    def fail_before_write(**_kwargs):
        raise RuntimeError("no write happened")

    monkeypatch.setattr(writer, "apply", fail_before_write)
    with pytest.raises(RuntimeError, match="no write"):
        advance(worker)
    monkeypatch.setattr(writer, "apply", real)
    resumed = job(state, repo, writer)
    assert (
        resumed.reconcile(job_id="historial", type_id="person", property_id="profesion")["pending"]
        == 1
    )
    assert advance(resumed)["updated"] == 1


def test_stale_other_note_is_skipped_but_remaining_notes_continue(tmp_path):
    state, repo, writer = setup(tmp_path, ["Profesión: médica", "Profesión: profesora"])
    worker = job(state, repo, writer)
    worker.stage(job_id="historial", type_id="person", property_id="profesion")
    (repo.root / "0.md").write_text((repo.root / "0.md").read_text() + "changed\n")
    assert advance(worker)["stale"] == 1
    assert advance(worker)["updated"] == 1
    assert "profesion" not in parse_note(repo.read_text("0.md")).metadata


def test_actor_schema_and_target_cannot_open_each_others_journals(tmp_path):
    state, repo, writer = setup(tmp_path, ["Profesión: médica"])
    worker = job(state, repo, writer)
    worker.stage(job_id="historial", type_id="person", property_id="profesion")
    assert job(state, repo, writer, actor="profile-b").status("historial") is None
    with pytest.raises(LocalBackfillJobError, match="No staged"):
        advance(job(state, repo, writer, actor="profile-b"))
    with pytest.raises(LocalBackfillJobError, match="optional properties"):
        worker.stage(job_id="historial", type_id="person", property_id="unknown")
    incompatible = json.loads(json.dumps(writer.schema))
    next(t for t in incompatible["types"] if t["id"] == "person")["properties"][-1][
        "description"
    ] = "Different schema"
    other_writer = AutomaticPropertyBackfill(
        repository=repo, schema=incompatible, history=GitHistoryRecorder(repo.root)
    )
    with pytest.raises(LocalBackfillJobError, match="schema"):
        job(state, repo, other_writer).status("historial")


def test_symlink_poisoning_does_not_touch_vault(tmp_path):
    state, repo, writer = setup(tmp_path, ["Profesión: médica"])
    worker = job(state, repo, writer)
    worker.stage(job_id="historial", type_id="person", property_id="profesion")
    receipt = next((state / "schema-backfill-jobs").glob("*.json"))
    content = repo.read_text("0.md")
    receipt.unlink()
    receipt.symlink_to(repo.root / "0.md")
    with pytest.raises(LocalBackfillJobError, match="link"):
        advance(worker)
    assert repo.read_text("0.md") == content


def test_model_failure_before_write_defers_without_automatic_billable_retry(tmp_path):
    state, repo, writer = setup(tmp_path, ["Ana trabaja como médica."])
    worker = job(state, repo, writer)
    worker.stage(job_id="historial", type_id="person", property_id="profesion")

    class BadGateway:
        def _complete(self, **_kwargs):
            raise RuntimeError("model offline")

    with pytest.raises(SemanticProviderDeferred, match="safely deferred"):
        advance(worker, model=SemanticPropertyInterpreter(BadGateway()))
    restarted = job(state, repo, writer)
    assert restarted.status("historial")["pending"] == 0
    assert restarted.status("historial")["deferred"] == 1
    assert advance(restarted)["status"] == "awaiting_ai"
    assert parse_note(repo.read_text("0.md")).metadata.get("profesion") is None


def test_empty_vault_and_private_device_state(tmp_path):
    state, repo, writer = setup(tmp_path, [])
    worker = job(state, repo, writer)
    assert (
        worker.stage(job_id="historial", type_id="person", property_id="profesion")["status"]
        == "complete"
    )
    assert worker.status("historial")["total"] == 0
    with pytest.raises(LocalBackfillJobError, match="outside"):
        LocalBackfillJob(state_root=repo.root, repository=repo, writer=writer, actor_id="profile")


def test_deferred_local_prose_is_resumed_after_opt_in_model_becomes_available(tmp_path):
    state, repo, writer = setup(tmp_path, ["Ana trabaja como médica."])
    worker = job(state, repo, writer)
    worker.stage(job_id="historial", type_id="person", property_id="profesion")
    offline = advance(worker)
    assert offline["status"] == "awaiting_ai"
    assert offline["deferred"] == 1
    assert parse_note(repo.read_text("0.md")).metadata.get("profesion") is None

    class AcceptedGateway:
        def __init__(self):
            self.calls = 0

        def _complete(self, **_kwargs):
            self.calls += 1
            assert self.calls <= 2
            if self.calls == 1:
                return {
                    "decision": "SET",
                    "locator": "src0:0",
                    "quote": "trabaja como médica",
                    "value": "médica",
                }
            return {
                "verdict": "APPROVE",
                "reason": "ENTAILED_CURRENT",
                "locator": "src0:0",
                "quote": "trabaja como médica",
                "value": "médica",
            }

    gateway = AcceptedGateway()
    resumed = job(state, repo, writer)
    complete = advance(resumed, model=SemanticPropertyInterpreter(gateway))
    assert complete["status"] == "complete" and complete["updated"] == 1
    assert complete["deferred"] == 0
    assert gateway.calls == 2
    assert parse_note(repo.read_text("0.md")).metadata["profesion"] == "médica"
    assert advance(resumed, model=SemanticPropertyInterpreter(gateway))["updated"] == 1


def test_unattributed_physical_change_never_autoretries_after_crash(tmp_path, monkeypatch):
    state, repo, writer = setup(tmp_path, ["Profesión: médica"])
    worker = job(state, repo, writer)
    worker.stage(job_id="historial", type_id="person", property_id="profesion")
    original = repo.read_text("0.md")

    def corrupt_before_receipt(**_kwargs):
        # Simulates another local process having modified Markdown after
        # the durable pre-write intent, without a matching Git receipt.
        (repo.root / "0.md").write_text(original + "Unattributed edit\n")
        raise RuntimeError("ambiguous I/O")

    monkeypatch.setattr(writer, "apply", corrupt_before_receipt)
    with pytest.raises(RuntimeError, match="ambiguous I/O"):
        advance(worker)
    worker = job(state, repo, writer)
    with pytest.raises(LocalBackfillJobError, match="Ambiguous physical write"):
        advance(worker)
    assert worker.status("historial")["status"] == "attention"
    assert repo.read_text("0.md") == original + "Unattributed edit\n"


def test_multi_page_plan_collects_all_candidates_before_writing(tmp_path):
    state, repo, writer = setup(tmp_path, [f"Profesión: oficio-{i}" for i in range(28)])
    worker = job(state, repo, writer)
    staged = worker.stage(job_id="historial", type_id="person", property_id="profesion")
    assert staged["total"] == staged["pending"] == 28
    assert len([p for p in repo.list_markdown_paths()]) == 28
    assert advance(worker)["updated"] == 1
    assert worker.status("historial")["pending"] == 27
    assert all(
        "profesion" not in parse_note(repo.read_text(f"{i}.md")).metadata for i in range(1, 28)
    )


def test_incremental_index_refresh_is_scheduled_once_on_known_commit(tmp_path):
    state, repo, writer = setup(tmp_path, ["Profesión: médica"])
    changes: list[str] = []
    worker = LocalBackfillJob(
        state_root=state,
        repository=repo,
        writer=writer,
        actor_id="profile-a",
        on_updated=lambda note_id: changes.append(note_id),
    )
    worker.stage(job_id="historial", type_id="person", property_id="profesion")
    assert advance(worker)["updated"] == 1
    assert changes == ["persona-0"]
    assert advance(worker)["updated"] == 1
    assert changes == ["persona-0"]


def test_index_refresh_failure_after_commit_is_recovered_without_second_commit(tmp_path):
    state, repo, writer = setup(tmp_path, ["Profesión: médica"])
    calls = []

    def broken(note_id):
        calls.append(("failed", note_id))
        raise RuntimeError("index queue unavailable")

    worker = LocalBackfillJob(
        state_root=state,
        repository=repo,
        writer=writer,
        actor_id="profile-a",
        on_updated=broken,
    )
    worker.stage(job_id="historial", type_id="person", property_id="profesion")
    with pytest.raises(RuntimeError, match="index queue"):
        advance(worker)
    assert worker.status("historial")["status"] == "attention"
    recovered = LocalBackfillJob(
        state_root=state,
        repository=repo,
        writer=writer,
        actor_id="profile-a",
        on_updated=lambda note_id: calls.append(("ok", note_id)),
    )
    assert advance(recovered)["updated"] == 1
    assert calls == [("failed", "persona-0"), ("ok", "persona-0")]
    assert (
        subprocess.check_output(
            ["git", "rev-list", "--count", "HEAD"], cwd=repo.root, text=True
        ).strip()
        == "2"
    )


def test_tampered_completed_row_is_not_trusted_even_if_shape_is_valid(tmp_path):
    state, repo, writer = setup(tmp_path, ["Profesión: médica"])
    worker = job(state, repo, writer)
    worker.stage(job_id="historial", type_id="person", property_id="profesion")
    assert advance(worker)["updated"] == 1
    journal = next((state / "schema-backfill-jobs").glob("*.json"))
    saved = json.loads(journal.read_text())
    assert saved["rows"][0]["status"] == "updated"
    saved["rows"][0]["undo"] = "f" * 40
    journal.write_text(json.dumps(saved))
    with pytest.raises(LocalBackfillJobError, match="integrity"):
        job(state, repo, writer).status("historial")
    assert parse_note(repo.read_text("0.md")).metadata["revision"] == 2


def test_history_receipt_is_discoverable_past_100_path_commits(tmp_path, monkeypatch):
    state, repo, writer = setup(tmp_path, ["Profesión: médica"])
    worker = job(state, repo, writer)
    worker.stage(job_id="historial", type_id="person", property_id="profesion")
    real = writer.apply

    def fail_after_real_write(**kwargs):
        assert real(**kwargs).status == "updated"
        raise RuntimeError("crash after commit")

    monkeypatch.setattr(writer, "apply", fail_after_real_write)
    with pytest.raises(RuntimeError, match="crash after commit"):
        advance(worker)
    original_modified = repo.read_text("0.md")
    assert parse_note(original_modified).metadata["revision"] == 2
    # More than 100 later commits touch this path but eventually restore
    # exactly the accepted bytes. The journal must find its original request
    # without assuming the 100 newest history entries are sufficient.
    for index in range(104):
        (repo.root / "0.md").write_text(
            original_modified + f"Temporary external history event: {index}\n"
        )
        subprocess.run(
            ["git", "add", "0.md"], cwd=repo.root, check=True, capture_output=True, timeout=10
        )
        subprocess.run(
            [
                "git",
                "-c",
                "user.name=Test",
                "-c",
                "user.email=test@localhost",
                "commit",
                "-q",
                "-m",
                f"event-{index}",
            ],
            cwd=repo.root,
            check=True,
            capture_output=True,
            timeout=10,
        )
    (repo.root / "0.md").write_text(original_modified)
    subprocess.run(
        ["git", "add", "0.md"], cwd=repo.root, check=True, capture_output=True, timeout=10
    )
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@localhost",
            "commit",
            "-q",
            "-m",
            "restore-identical-content",
        ],
        cwd=repo.root,
        check=True,
        capture_output=True,
        timeout=10,
    )
    resumed = job(state, repo, writer)
    result = advance(resumed)
    assert result["updated"] == 1 and result["status"] == "complete"
    assert repo.read_text("0.md") == original_modified


def test_first_integrity_key_creation_survives_crash_before_publication(tmp_path, monkeypatch):
    """An interrupted initialize must not leave a published zero-byte key."""
    import os

    from odyssey_runtime import schema_backfill_jobs as module

    state, repo, writer = setup(tmp_path, ["profesion: médica"])
    original_link = os.link
    calls = []

    def interrupt_after_key_fsync(source, destination, **kwargs):
        if str(destination).endswith("/.integrity-key") and not calls:
            calls.append(destination)
            raise SystemExit("simulated crash before atomic key publication")
        return original_link(source, destination, **kwargs)

    monkeypatch.setattr(module.os, "link", interrupt_after_key_fsync)
    with pytest.raises(SystemExit, match="simulated crash"):
        job(state, repo, writer)
    journal = state / "schema-backfill-jobs"
    assert len(calls) == 1
    assert not (journal / ".integrity-key").exists()
    assert not list(journal.glob(".integrity-pending-*"))

    # Restart regenerates a FULL key, and the new signed journal resumes.
    monkeypatch.setattr(module.os, "link", original_link)
    resumed = job(state, repo, writer)
    assert len((journal / ".integrity-key").read_bytes()) == 32
    assert (journal / ".integrity-key").stat().st_mode & 0o777 == 0o600
    assert (
        resumed.stage(job_id="historial", type_id="person", property_id="profesion")["pending"] == 1
    )
    assert advance(resumed)["updated"] == 1
    assert job(state, repo, writer).status("historial")["updated"] == 1


def test_staged_inventory_uses_two_full_scans_not_two_scans_per_page(tmp_path, monkeypatch):
    """A large journal plan uses one initial and one final inventory proof."""
    state, repo, writer = setup(tmp_path, [f"profesion: oficio-{i}" for i in range(54)])
    original = repo.note_version_snapshot
    visits = []

    def counted_snapshot():
        visits.append(True)
        return original()

    monkeypatch.setattr(repo, "note_version_snapshot", counted_snapshot)
    staged = job(state, repo, writer).stage(
        job_id="historial", type_id="person", property_id="profesion"
    )
    assert staged["pending"] == 54
    assert len(visits) == 2


@pytest.mark.parametrize("change", ["first_page", "new_file"])
def test_staged_scan_does_not_publish_after_any_concurrent_vault_change(
    tmp_path, monkeypatch, change
):
    """The final inventory guard catches edits behind the page cursor."""
    from odyssey_runtime import schema_backfill_jobs

    state, repo, writer = setup(tmp_path, [f"profesion: oficio-{i}" for i in range(28)])
    original = schema_backfill_jobs._scan_schema_sources_page
    counter = 0

    def mutate_between_pages(**kwargs):
        nonlocal counter
        page = original(**kwargs)
        counter += 1
        if counter == 1:
            if change == "first_page":
                target = repo.root / "0.md"
                target.write_text(target.read_text() + "External edit\n")
            else:
                target = repo.root / "new.md"
                target.write_text((repo.root / "0.md").read_text())
        return page

    monkeypatch.setattr(schema_backfill_jobs, "_scan_schema_sources_page", mutate_between_pages)
    with pytest.raises(
        LocalBackfillJobError, match="Vault changed|canonical source changed mid-scan"
    ):
        job(state, repo, writer).stage(
            job_id="historial", type_id="person", property_id="profesion"
        )
    assert not list((state / "schema-backfill-jobs").glob("*.json"))


def test_git_history_reuses_one_canonical_identity_scan_per_backfill(tmp_path, monkeypatch):
    """History may reuse prewrite canonical evidence, never parse N notes twice."""
    state, repo, writer = setup(tmp_path, ["Profesión: médica"] * 85)
    worker = job(state, repo, writer)
    worker.stage(job_id="historial", type_id="person", property_id="profesion")
    reads = []
    original_read = repo.read_text

    def counted_read(path):
        reads.append(path)
        return original_read(path)

    monkeypatch.setattr(repo, "read_text", counted_read)
    result = advance(worker)
    assert result["updated"] == 1
    assert 85 <= len(reads) < 105, f"Unexpected full-vault reparsing: {len(reads)}"
    assert sum(path == "0.md" for path in reads) >= 3
    assert parse_note(original_read("0.md")).metadata["profesion"] == "médica"
    reads.clear()
    result = advance(worker)
    assert result["updated"] == 2
    assert len(reads) < 15, f"Canonical cache did not survive a confirmed write: {len(reads)}"
    assert (
        subprocess.run(
            ["git", "log", "-1", "--format=%B"],
            cwd=repo.root,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.count("Odyssey-Request:")
        == 1
    )


def test_duplicate_identity_added_after_staging_blocks_automatic_update(tmp_path):
    """A new duplicate on disk must defeat any earlier scan or ID hint."""
    state, repo, writer = setup(tmp_path, ["Profesión: médica", "Profesión: docente"])
    worker = job(state, repo, writer)
    worker.stage(job_id="historial", type_id="person", property_id="profesion")
    original = repo.read_text("0.md")
    repo.create_text("shadow.md", original)
    result = advance(worker)
    assert result["updated"] == 0 and result["stale"] == 1
    assert repo.read_text("0.md") == original


def test_history_fails_closed_if_duplicate_appears_after_target_write(tmp_path, monkeypatch):
    """A changed path set between Core prepare and Git attribution is unsafe."""
    state, repo, writer = setup(tmp_path, ["Profesión: médica", "Profesión: docente"])
    worker = job(state, repo, writer)
    worker.stage(job_id="historial", type_id="person", property_id="profesion")
    previous_head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo.root,
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()
    original_record = writer.history.record
    injected = False

    def inject_duplicate_after_write(**kwargs):
        nonlocal injected
        if not injected:
            injected = True
            repo.create_text("shadow.md", repo.read_text("0.md"))
        return original_record(**kwargs)

    monkeypatch.setattr(writer.history, "record", inject_duplicate_after_write)
    with pytest.raises(Exception, match="history"):
        advance(worker)
    assert injected
    assert parse_note(repo.read_text("0.md")).metadata["profesion"] == "médica"
    assert (
        subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=repo.root, text=True, capture_output=True, check=True
        ).stdout.strip()
        == previous_head
    )
    assert worker.status("historial")["status"] == "attention"


def test_cached_inventory_invalidates_when_another_note_changes(tmp_path, monkeypatch):
    """An unrelated physical change defeats the cache and forces canonical reads."""
    state, repo, writer = setup(tmp_path, ["Profesión: médica"] * 45)
    worker = job(state, repo, writer)
    worker.stage(job_id="historial", type_id="person", property_id="profesion")
    assert advance(worker)["updated"] == 1
    fresh_count = 0
    original = repo.read_text

    def counted(path):
        nonlocal fresh_count
        fresh_count += 1
        return original(path)

    monkeypatch.setattr(repo, "read_text", counted)
    # An unrelated note's body changed without an authorized revision bump.
    repo.replace_text("12.md", original("12.md") + "\nExternal edit.\n")
    assert advance(worker)["updated"] == 2
    assert fresh_count >= 45
    assert parse_note(original("12.md")).content.endswith("External edit.\n")


def test_cached_inventory_new_duplicate_stops_next_write(tmp_path):
    """Even after a confirmed first write, a new path can invalidate uniqueness."""
    state, repo, writer = setup(tmp_path, ["Profesión: médica"] * 4)
    worker = job(state, repo, writer)
    worker.stage(job_id="historial", type_id="person", property_id="profesion")
    assert advance(worker)["updated"] == 1
    old = repo.read_text("1.md")
    repo.create_text("shadow.md", old)
    result = advance(worker)
    assert result["updated"] == 1 and result["stale"] == 1
    assert repo.read_text("1.md") == old


def test_stage_separates_physical_inventory_capacity_from_write_candidates(tmp_path, monkeypatch):
    """Private staging scans all IDs, even past public receipt capacity."""
    from odyssey_core import schema_retrospection

    state, repo, writer = setup(tmp_path, ["Profesión: médica"] * 28 + ["Profesión: ingeniero"])
    # Simulate passing the much smaller 10k public limit without expensive
    # 10k fixtures in the routine gate; the full 10k+ proof is opt-in.
    monkeypatch.setattr(schema_retrospection, "_MAX_PROGRESS_IDS", 25)
    worker = job(state, repo, writer)
    summary = worker.stage(job_id="over-limit", type_id="person", property_id="profesion")
    assert summary["total"] == 29
    assert worker.status("over-limit")["pending"] == 29
    # The public/durable per-page accumulator remains bounded.
    from odyssey_core.schema_retrospection import (
        SchemaRetrospectionError,
        accumulate_schema_scan,
        scan_schema_sources,
    )

    first = scan_schema_sources(
        repository=repo,
        schema=writer.schema,
        kind="backfill_property",
        target_type_id="person",
        property_id="profesion",
        limit=25,
    )
    second = scan_schema_sources(
        repository=repo,
        schema=writer.schema,
        kind="backfill_property",
        target_type_id="person",
        property_id="profesion",
        cursor=first.next_cursor,
        limit=25,
    )
    with pytest.raises(SchemaRetrospectionError, match="Duplicate or inconsistent"):
        accumulate_schema_scan(second, accumulate_schema_scan(first))


def test_staged_large_scan_still_rejects_duplicate_identity_across_pages(tmp_path, monkeypatch):
    """The private extended limit does not weaken cross-page collision rejection."""
    from odyssey_core import schema_retrospection
    from odyssey_core.schema_retrospection import SchemaRetrospectionError

    state, repo, writer = setup(tmp_path, ["Profesión: médica"] * 26)
    original = parse_note(repo.read_text("25.md"))
    duplicate = type(original)(
        {**original.metadata, "id": "persona-0"},
        original.content,
    )
    repo.replace_text("25.md", serialize_note(duplicate))
    monkeypatch.setattr(schema_retrospection, "_MAX_PROGRESS_IDS", 10)
    worker = job(state, repo, writer)
    with pytest.raises(SchemaRetrospectionError, match="Duplicate"):
        worker.stage(job_id="duplicate", type_id="person", property_id="profesion")
    assert worker.status("duplicate") is None
    assert parse_note(repo.read_text("0.md")).metadata.get("profesion") is None


def test_stage_rejects_staged_inventory_changed_after_page_zero(tmp_path, monkeypatch):
    """A new note anywhere invalidates the snapshot before plan publication."""
    from odyssey_runtime import schema_backfill_jobs as jobs

    state, repo, writer = setup(tmp_path, ["Profesión: médica"] * 31)
    original = jobs._scan_schema_sources_page
    injected = False

    def external_insert(**kwargs):
        nonlocal injected
        page = original(**kwargs)
        if not injected:
            injected = True
            extra = parse_note(repo.read_text("0.md"))
            repo.create_text(
                "added.md",
                serialize_note(type(extra)({**extra.metadata, "id": "inserted"}, extra.content)),
            )
        return page

    monkeypatch.setattr(jobs, "_scan_schema_sources_page", external_insert)
    worker = job(state, repo, writer)
    with pytest.raises(LocalBackfillJobError, match="Vault changed"):
        worker.stage(job_id="external", type_id="person", property_id="profesion")
    assert injected and worker.status("external") is None


def test_staged_scan_never_silently_exceeds_bounded_mutation_plan(tmp_path, monkeypatch):
    """More candidate writes than the durable budget abort before any plan exists."""
    from odyssey_runtime import schema_backfill_jobs as jobs

    state, repo, writer = setup(tmp_path, ["Profesión: médica"] * 4)
    monkeypatch.setattr(jobs, "_LIMIT", 3)
    worker = job(state, repo, writer)
    with pytest.raises(LocalBackfillJobError, match="capacity"):
        worker.stage(job_id="too-many", type_id="person", property_id="profesion")
    assert worker.status("too-many") is None
    assert all(
        parse_note(repo.read_text(f"{i}.md")).metadata.get("profesion") is None for i in range(4)
    )


def test_large_staged_inventory_uses_only_two_physical_snapshots(tmp_path, monkeypatch):
    """Pages share one proof; final publication still checks every path again."""
    state, repo, writer = setup(tmp_path, ["Profesión: médica"] * 53)
    calls = []
    original = repo.note_version_snapshot

    def counted_snapshot():
        calls.append(True)
        return original()

    monkeypatch.setattr(repo, "note_version_snapshot", counted_snapshot)
    worker = job(state, repo, writer)
    assert (
        worker.stage(job_id="snapshots", type_id="person", property_id="profesion")["pending"] == 53
    )
    assert len(calls) == 2


def test_staged_id_bytes_cannot_exceed_bounded_memory_proof(tmp_path, monkeypatch):
    """Very long identities must not create unbounded transient scan receipts."""
    from odyssey_runtime import schema_backfill_jobs as jobs

    state, repo, writer = setup(tmp_path, ["Profesión: médica"] * 4)
    monkeypatch.setattr(jobs, "_MAX_STAGED_ID_BYTES", 12)
    worker = job(state, repo, writer)
    with pytest.raises(LocalBackfillJobError, match="memory budget"):
        worker.stage(job_id="oversized", type_id="person", property_id="profesion")
    assert worker.status("oversized") is None
