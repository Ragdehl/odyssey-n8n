"""Actual disposable Core writes -> durable source pending -> guarded direct reply."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from odyssey_core.candidate_pending_projection import project_unresolved_candidate_preview
from odyssey_core.candidate_pending_state import (
    CandidatePendingRepository,
    CandidatePendingStateError,
)
from odyssey_core.clarification import ClarificationOption
from odyssey_core.notes import Note, serialize_note
from odyssey_core.pending_work import PendingWorkRepository
from tests.runtime.test_candidate_pending_projection import _case_with_pending
from tests.runtime.test_temporal_user_path_e2e import SCHEMA

NOW = "2026-10-04T17:35:00+02:00"


def _existing_identity(root: Path, name: str, stable_id: str, kind: str = "person") -> None:
    """Provide ordinary synthetic canonical notes, not hard-coded app identities."""
    note = Note(
        {
            "id": stable_id,
            "name": name,
            "type": kind,
            "aliases": [],
            "created_at": "2026-10-03T10:00:00Z",
            "updated_at": "2026-10-03T10:00:00Z",
            "created_by": {"human": None, "app": "test"},
            "updated_by": {"human": None, "app": "test"},
            "revision": 1,
            "schema_version": 3,
        },
        "",
    )
    (root / f"{name}.md").write_text(serialize_note(note), encoding="utf-8")


def _ready(tmp_path: Path, *, options: bool = True, conversation: str = "chat-1"):
    """Create a real partially written Markdown request and v2 pending record."""
    case, context, plan, manifest, result, readback, vault = _case_with_pending(tmp_path)
    preview = project_unresolved_candidate_preview(
        case["source"], context, plan, manifest, result, readback
    )
    state = tmp_path / "state" / "pending"
    state.mkdir(parents=True)
    repository = CandidatePendingRepository(state)
    choices = ()
    if options:
        _existing_identity(vault.root, "Eric", "eric-id")
        _existing_identity(vault.root, "Luis", "luis-id")
        choices = (ClarificationOption("eric-id", "Eric"), ClarificationOption("luis-id", "Luis"))
    repository.record(
        preview,
        conversation_id=conversation,
        created_at=NOW,
        options=choices,
        vault=vault,
        schema=SCHEMA,
    )
    return preview, repository, vault, state


def _reply(repo, vault, text, answer_id="reply-1", **kwargs):
    return repo.reply(
        conversation_id="chat-1",
        reply=text,
        answer_id=answer_id,
        vault=vault,
        schema=SCHEMA,
        immediate_followup=True,
        **kwargs,
    )


def test_real_partial_markdown_survives_restart_and_direct_reply_records_one_choice(
    tmp_path: Path,
) -> None:
    """Two saved Core facts stay intact while 'con Luis' selects only pending source."""
    preview, repo, vault, state = _ready(tmp_path)
    before = {p: vault.read_text(p) for p in vault.list_markdown_paths()}
    reboot = CandidatePendingRepository(state)
    assert reboot.open_requests("chat-1") == (preview.request_id,)
    decision = _reply(reboot, vault, "Con Luis")
    assert decision.outcome == "choice_recorded"
    assert decision.request_id == preview.request_id
    assert decision.selected_note_id == "luis-id"
    assert decision.selected_guard and len(decision.selected_guard) == 64
    assert decision.pending_source_text == "Mañana iré al cine con él"
    assert decision.captured_at == NOW
    assert not decision.may_execute
    record = CandidatePendingRepository(state).read(preview.request_id)
    assert record["status"] == "selected"
    assert record["answer_id"] == "reply-1"
    assert reboot.open_requests("chat-1") == ()
    assert {p: vault.read_text(p) for p in before} == before
    assert all("cine" not in vault.read_text(path) for path in vault.list_markdown_paths())


def test_same_answer_request_id_is_idempotent_and_different_reply_cannot_switch_identity(
    tmp_path: Path,
) -> None:
    preview, repo, vault, _state = _ready(tmp_path)
    assert _reply(repo, vault, "Luis", answer_id="answer-88").outcome == "choice_recorded"
    assert (
        _reply(repo, vault, "Luis", answer_id="answer-88", request_id=preview.request_id).outcome
        == "already_selected"
    )
    assert (
        _reply(repo, vault, "Eric", answer_id="answer-89", request_id=preview.request_id).outcome
        == "already_closed"
    )
    assert repo.read(preview.request_id)["selected_note_id"] == "luis-id"


def test_cancellation_preserves_existing_facts_and_does_not_reopen_automatically(
    tmp_path: Path,
) -> None:
    preview, repo, vault, _state = _ready(tmp_path)
    before = {p: vault.read_text(p) for p in vault.list_markdown_paths()}
    result = _reply(repo, vault, "cancelar")
    assert result.outcome == "cancelled"
    assert repo.read(preview.request_id)["status"] == "cancelled"
    assert repo.open_requests("chat-1") == ()
    assert _reply(repo, vault, "Luis", request_id=preview.request_id).outcome == "already_closed"
    assert {p: vault.read_text(p) for p in before} == before


def test_unrelated_turn_explicit_request_and_other_conversation_are_not_silent_choices(
    tmp_path: Path,
) -> None:
    preview, repo, vault, _state = _ready(tmp_path)
    result = repo.reply(
        conversation_id="chat-1",
        reply="Con Luis",
        answer_id="after-topic",
        vault=vault,
        schema=SCHEMA,
        immediate_followup=False,
    )
    assert result.outcome == "explicit_request_required"
    assert _reply(repo, vault, "Hoy compré café").outcome == "unresolved"
    assert (
        repo.reply(
            conversation_id="other-chat",
            reply="Luis",
            answer_id="foreign",
            vault=vault,
            schema=SCHEMA,
            immediate_followup=True,
            request_id=preview.request_id,
        ).outcome
        == "unavailable"
    )
    assert repo.read(preview.request_id)["status"] == "open"
    assert _reply(repo, vault, "Luis", request_id=preview.request_id).outcome == "choice_recorded"


def test_multiple_open_pending_require_explicit_request_id(tmp_path: Path) -> None:
    preview, repo, vault, state = _ready(tmp_path)
    second = replace(
        preview,
        request_id="candidate-second-request",
        physically_verified_fact_count=0,
        completed_fact_markers=(),
    )
    choices = (ClarificationOption("eric-id", "Eric"), ClarificationOption("luis-id", "Luis"))
    repo.record(
        second,
        conversation_id="chat-1",
        created_at=NOW,
        options=choices,
        vault=vault,
        schema=SCHEMA,
    )
    assert len(repo.open_requests("chat-1")) == 2
    assert _reply(repo, vault, "Luis").outcome == "multiple_or_no_pending"
    assert _reply(repo, vault, "Luis", request_id=second.request_id).outcome == "choice_recorded"
    assert repo.read(preview.request_id)["status"] == "open"
    assert CandidatePendingRepository(state).open_requests("chat-1") == (preview.request_id,)


def test_modified_canonical_person_blocks_answer_selection_without_mutation(tmp_path: Path) -> None:
    preview, repo, vault, _state = _ready(tmp_path)
    path = vault.root / "Luis.md"
    path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    assert _reply(repo, vault, "Luis").outcome == "stale_choice"
    assert repo.read(preview.request_id)["status"] == "open"


def test_ph17b_v1_pending_action_files_coexist_unchanged_with_source_v2(tmp_path: Path) -> None:
    preview, repo, _vault, state = _ready(tmp_path)
    assert PendingWorkRepository(state).list_ids() == ()
    assert (state / "candidates" / f"{preview.request_id}.json").exists()
    assert not (state / f"{preview.request_id}.json").exists()
    assert repo.read(preview.request_id)["format_version"] == 2


def test_pending_without_core_grounded_options_is_durable_but_cannot_choose(tmp_path: Path) -> None:
    preview, repo, vault, _state = _ready(tmp_path, options=False)
    assert _reply(repo, vault, "Luis").outcome == "needs_core_options"
    assert repo.read(preview.request_id)["status"] == "open"


def test_tampered_source_quote_and_symlink_files_are_rejected(tmp_path: Path) -> None:
    preview, repo, _vault, state = _ready(tmp_path)
    path = state / "candidates" / f"{preview.request_id}.json"
    content = json.loads(path.read_text(encoding="utf-8"))
    content["pending"][0]["text"] = "Voy al cine con alguien que inventé"
    path.write_text(json.dumps(content), encoding="utf-8")
    with pytest.raises(CandidatePendingStateError, match="not grounded"):
        repo.read(preview.request_id)
    path.unlink()
    path.symlink_to(tmp_path / "untrusted-target.json")
    with pytest.raises(CandidatePendingStateError, match="symlink"):
        repo.read(preview.request_id)


def test_replay_with_identical_payload_has_no_duplicate_pending_record(tmp_path: Path) -> None:
    preview, repo, vault, state = _ready(tmp_path)
    matching = preview
    choices = (ClarificationOption("eric-id", "Eric"), ClarificationOption("luis-id", "Luis"))
    assert (
        repo.record(
            matching,
            conversation_id="chat-1",
            created_at="2026-10-05T08:00:00+02:00",
            options=choices,
            vault=vault,
            schema=SCHEMA,
        )
        == preview.request_id
    )
    assert len(list((state / "candidates").glob("*.json"))) == 1


def test_untrusted_label_cannot_misrepresent_a_verified_canonical_identity(tmp_path: Path) -> None:
    preview, repo, vault, _state = _ready(tmp_path, options=False)
    with pytest.raises(CandidatePendingStateError, match="Canonical option evidence"):
        repo.record(
            preview,
            conversation_id="another-chat",
            created_at=NOW,
            options=(
                ClarificationOption("eric-id", "Luis"),
                ClarificationOption("luis-id", "Eric"),
            ),
            vault=vault,
            schema=SCHEMA,
        )


def test_core_persists_verified_pending_state_through_opt_in_application_boundary(
    tmp_path: Path,
) -> None:
    """One real Core partial write creates durable v2 only after Markdown readback."""
    state = tmp_path / "state" / "pending"
    state.mkdir(parents=True)
    v2 = CandidatePendingRepository(state)
    stored = []

    def persist(preview):
        stored.append(preview)
        return v2.record(preview, conversation_id="chat-1", created_at=NOW)

    _case, _context, _plan, _manifest, result, _readback, vault = _case_with_pending(
        tmp_path, candidate_pending_recorder=persist
    )
    assert result.status.value == "partial"
    assert result.pending_work.required and result.pending_work.persisted
    assert result.pending_work.record_id == "candidate-pending-test"
    assert len(stored) == 1
    durable = CandidatePendingRepository(state).read(result.request_id)
    assert durable["status"] == "open"
    assert durable["physically_verified_fact_count"] == 2
    assert len(durable["completed_fact_markers"]) == 2
    assert durable["pending"][0]["text"] == "Mañana iré al cine con él"
    assert not any("cine" in vault.read_text(p) for p in vault.list_markdown_paths())


def test_changed_previously_written_fact_blocks_later_identity_choice(tmp_path: Path) -> None:
    """Do not automatically repair or repeat already written facts after a manual edit."""
    preview, repo, vault, _state = _ready(tmp_path)
    path = vault.root / "calendar" / "days" / "2026-10-03.md"
    original = path.read_text(encoding="utf-8")
    path.write_text(
        original.replace("Hablé con Luis.", "Hablé con otra persona."), encoding="utf-8"
    )
    assert _reply(repo, vault, "Con Luis").outcome == "stale_written_facts"
    assert repo.read(preview.request_id)["status"] == "open"


def test_cancel_without_resolved_options_does_not_write_or_guess(tmp_path: Path) -> None:
    preview, repo, vault, _state = _ready(tmp_path, options=False)
    before = tuple(vault.list_markdown_paths())
    assert _reply(repo, vault, "cancelar").outcome == "cancelled"
    assert repo.read(preview.request_id)["status"] == "cancelled"
    assert tuple(vault.list_markdown_paths()) == before


def test_unrelated_request_classification_reuses_existing_core_control_outcome(
    tmp_path: Path,
) -> None:
    """Injected classifier decides NEW_REQUEST but never mutates pending or knowledge."""
    preview, repo, vault, _state = _ready(tmp_path)

    class NewRequestClassifier:
        def classify(self, reply, original_request, options):
            return "NEW_REQUEST"

    result = repo.reply(
        conversation_id="chat-1",
        reply="Hoy compré café",
        answer_id="new-msg-1",
        vault=vault,
        schema=SCHEMA,
        immediate_followup=True,
        classifier=NewRequestClassifier(),
    )
    assert result.outcome == "new_request"
    assert repo.read(preview.request_id)["status"] == "open"


def test_selected_choice_survives_restart_and_guards_are_checked_again(tmp_path: Path) -> None:
    preview, repo, vault, state = _ready(tmp_path)
    assert _reply(repo, vault, "Con Luis").outcome == "choice_recorded"
    reboot = CandidatePendingRepository(state)
    ready = reboot.selected_for_core_review(
        conversation_id="chat-1", request_id=preview.request_id, vault=vault, schema=SCHEMA
    )
    assert ready.outcome == "choice_ready_for_core_review"
    assert ready.selected_note_id == "luis-id"
    assert ready.captured_at == NOW
    assert ready.pending_source_text == "Mañana iré al cine con él"
    assert not ready.may_execute
    target = vault.root / "Luis.md"
    target.write_text(target.read_text() + "\n", encoding="utf-8")
    assert (
        reboot.selected_for_core_review(
            conversation_id="chat-1", request_id=preview.request_id, vault=vault, schema=SCHEMA
        ).outcome
        == "stale_choice"
    )


def test_can_cancel_an_already_selected_but_not_executed_pending_choice(tmp_path: Path) -> None:
    preview, repo, vault, _state = _ready(tmp_path)
    assert _reply(repo, vault, "Luis").outcome == "choice_recorded"
    assert (
        _reply(
            repo, vault, "cancelar", answer_id="cancel-choice", request_id=preview.request_id
        ).outcome
        == "cancelled"
    )
    record = repo.read(preview.request_id)
    assert record["status"] == "cancelled"
    assert record["selected_note_id"] is None
    assert record["selected_guard"] is None


def test_project_note_types_are_eligible_choices_without_person_only_assumptions(
    tmp_path: Path,
) -> None:
    preview, repo, vault, _state = _ready(tmp_path, options=False)
    _existing_identity(vault.root, "Odyssey", "odyssey-id", "project")
    _existing_identity(vault.root, "Atlas", "atlas-id", "project")
    other = replace(
        preview,
        request_id="synthetic-project-ambiguity",
        physically_verified_fact_count=0,
        completed_fact_markers=(),
    )
    project_options = (
        ClarificationOption("odyssey-id", "Odyssey"),
        ClarificationOption("atlas-id", "Atlas"),
    )
    repo.record(
        other,
        conversation_id="projects-chat",
        created_at=NOW,
        options=project_options,
        vault=vault,
        schema=SCHEMA,
    )
    result = repo.reply(
        conversation_id="projects-chat",
        reply="Atlas",
        answer_id="project-choice",
        vault=vault,
        schema=SCHEMA,
        immediate_followup=True,
        request_id=other.request_id,
    )
    assert result.outcome == "choice_recorded"
    assert result.selected_note_id == "atlas-id"
    assert not result.may_execute


def test_capture_clock_must_include_timezone_offset(tmp_path: Path) -> None:
    preview, repo, _vault, _state = _ready(tmp_path, options=False)
    with pytest.raises(CandidatePendingStateError):
        repo.record(
            replace(preview, request_id="bad-clock"),
            conversation_id="chat-2",
            created_at="2026-10-04T17:35:00",
        )
