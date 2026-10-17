"""Task Work Session E2 carrier: physical readback, CAS, and actor-local scope."""

from dataclasses import replace

import pytest

from odyssey_apps.tasks import (
    CanonicalSessionEvidenceError,
    prove_created_session,
)
from odyssey_core.notes import parse_note, serialize_note
from tests.apps.tasks.test_work_sessions import _build, _task_tokens

CLOCK = "2026-10-05T18:00:00+02:00"


def _started(tmp_path):
    repo, service = _build(tmp_path)
    rev, digest = _task_tokens(repo)
    created = service.start(
        task_id="task-odyssey",
        started_at=CLOCK,
        expected_task_revision=rev,
        expected_task_source_hash=digest,
        request_id="n3-start",
        actor="actor-a",
        now=CLOCK,
    )
    return repo, service, created


def test_session_receipt_proves_markdown_and_powers_existing_stop_cas(tmp_path):
    repo, service, created = _started(tmp_path)
    proof = prove_created_session(
        result=created,
        expected_task_id="task-odyssey",
        creator_delivery_step="n3-start",
        service=service,
    )
    assert proof.session_id == created.session.id
    assert proof.task_id == created.task_id
    assert proof.creator_delivery_step == "n3-start"
    assert proof.require_current(service) == (created.session.revision, created.session.source_hash)
    assert not hasattr(proof, "stop") and not hasattr(proof, "write")
    revision, hash_ = proof.require_current(service)
    stopped = service.stop(
        session_id=proof.session_id,
        ended_at="2026-10-05T18:30:00+02:00",
        expected_revision=revision,
        expected_source_hash=hash_,
        request_id="n3-stop",
        actor="actor-a",
        now="2026-10-05T18:30:00+02:00",
    )
    assert stopped.session.ended_at == "2026-10-05T18:30:00+02:00"
    with pytest.raises(CanonicalSessionEvidenceError):
        proof.require_current(service)


@pytest.mark.parametrize(
    "change",
    [
        "wrong_task",
        "wrong_step",
        "wrong_operation",
        "wrong_source_hash",
        "wrong_path",
        "wrong_session_id",
        "closed_receipt",
        "missing_receipt",
        "partial_previous_hash",
    ],
)
def test_session_creation_receipt_must_be_current_and_exact(tmp_path, change):
    _repo, service, created = _started(tmp_path)
    kwargs = {
        "result": created,
        "expected_task_id": "task-odyssey",
        "creator_delivery_step": "n3-start",
        "service": service,
    }
    if change == "wrong_task":
        kwargs["expected_task_id"] = "task-taxes"
    elif change == "wrong_step":
        kwargs["creator_delivery_step"] = ""
    elif change == "wrong_operation":
        kwargs["result"] = replace(created, operation="work_session_stopped")
    elif change == "wrong_source_hash":
        kwargs["result"] = replace(created, session=replace(created.session, source_hash="0" * 64))
    elif change == "wrong_path":
        kwargs["result"] = replace(created, path="fake.md")
    elif change == "wrong_session_id":
        kwargs["result"] = replace(created, session=replace(created.session, id="invented"))
    elif change == "closed_receipt":
        kwargs["result"] = replace(created, session=replace(created.session, ended_at=CLOCK))
    elif change == "missing_receipt":
        kwargs["result"] = None
    elif change == "partial_previous_hash":
        kwargs["result"] = replace(created, previous_source_hash="0" * 64)
    with pytest.raises(CanonicalSessionEvidenceError):
        prove_created_session(**kwargs)


@pytest.mark.parametrize(
    "change",
    [
        "external_session_edit",
        "external_task_edit",
        "session_deleted",
        "task_deleted",
        "session_reowned",
        "duplicate_session_id",
        "duplicate_task_id",
    ],
)
def test_session_recheck_rejects_external_mutations_and_duplicate_ids(tmp_path, change):
    repo, service, created = _started(tmp_path)
    proof = prove_created_session(
        result=created,
        expected_task_id="task-odyssey",
        creator_delivery_step="n3-start",
        service=service,
    )
    if change == "duplicate_session_id":
        repo.create_text("duplicate-session.md", repo.read_text(created.path))
    elif change == "duplicate_task_id":
        repo.create_text("duplicate-task.md", repo.read_text("odyssey.md"))
    else:
        path = "odyssey.md" if change in {"external_task_edit", "task_deleted"} else created.path
        note = parse_note(repo.read_text(path))
        if change == "external_task_edit":
            updated = replace(note, content=note.content + "\n- changed externally\n")
        elif change == "task_deleted" or change == "session_deleted":
            updated = replace(note, metadata={**note.metadata, "deleted": True})
        elif change == "session_reowned":
            updated = replace(note, metadata={**note.metadata, "task_id": "task-taxes"})
        else:
            updated = replace(note, content=note.content + "\n- tampered\n")
        repo.replace_text(path, serialize_note(updated))
    with pytest.raises(CanonicalSessionEvidenceError):
        proof.require_current(service)


def test_evidence_cannot_be_reused_in_other_vault_even_with_copied_markdown(tmp_path):
    (tmp_path / "owner-a").mkdir()
    (tmp_path / "owner-b").mkdir()
    repo, service, created = _started(tmp_path / "owner-a")
    proof = prove_created_session(
        result=created,
        expected_task_id="task-odyssey",
        creator_delivery_step="n3-start",
        service=service,
    )
    other, another_service = _build(tmp_path / "owner-b")
    other.create_text(created.path, repo.read_text(created.path))
    with pytest.raises(CanonicalSessionEvidenceError, match="actor-local vault"):
        proof.require_current(another_service)
