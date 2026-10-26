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
from odyssey_runtime.schema_backfill_jobs import LocalBackfillJob, LocalBackfillJobError

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


def test_model_failure_before_write_is_retryable_without_unsafe_receipt(tmp_path):
    state, repo, writer = setup(tmp_path, ["Ana trabaja como médica."])
    worker = job(state, repo, writer)
    worker.stage(job_id="historial", type_id="person", property_id="profesion")

    class BadGateway:
        def _complete(self, **_kwargs):
            raise RuntimeError("model offline")

    with pytest.raises(RuntimeError, match="model offline"):
        advance(worker, model=SemanticPropertyInterpreter(BadGateway()))
    restarted = job(state, repo, writer)
    assert restarted.status("historial")["pending"] == 1
    assert advance(restarted)["status"] == "awaiting_ai"
    assert restarted.status("historial")["deferred"] == 1
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
