"""Real Markdown readback -> persisted selection -> read-only Core continuation."""

from __future__ import annotations

import json
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

from odyssey_core.candidate_continuation_context import (
    CandidateContinuationContextError,
    prepare_selected_candidate_continuation,
)
from odyssey_core.candidate_pending_state import CandidatePendingRepository
from odyssey_core.clarification import ClarificationOption
from tests.runtime.test_candidate_pending_state import NOW, _ready, _reply
from tests.runtime.test_temporal_user_path_e2e import SCHEMA


def _context(repo, vault, request_id, *, conversation_id="chat-1"):
    return prepare_selected_candidate_continuation(
        repo,
        conversation_id=conversation_id,
        request_id=request_id,
        vault=vault,
        schema=SCHEMA,
    )


def test_original_source_with_two_existing_real_facts_survives_restart(tmp_path: Path) -> None:
    preview, repo, vault, state = _ready(tmp_path)
    original = {path: vault.read_text(path) for path in vault.list_markdown_paths()}
    with pytest.raises(CandidateContinuationContextError):
        _context(repo, vault, preview.request_id)
    _reply(repo, vault, "Con Luis")
    rebooted = CandidatePendingRepository(state)
    context = _context(rebooted, vault, preview.request_id)
    pending = preview.pending[0]
    assert context.original_request_id == preview.request_id
    assert context.original_source == preview.original_request
    assert context.pending_source == pending.source_text
    assert context.reference_text == pending.reference_text
    assert context.source_start == pending.source_start
    assert context.source_end == pending.source_end
    assert context.selected_name == "Luis"
    assert context.selected_note_id == "luis-id"
    assert context.selected_identity_guard
    assert context.captured_at == NOW
    assert context.pending_record_digest and len(context.pending_record_digest) == 64
    assert len(context.completed_facts) == 2
    assert [f.ordinal for f in context.completed_facts] == [0, 1]
    assert context.may_execute is False
    with pytest.raises(FrozenInstanceError):
        context.original_source = "changed"
    reviewer_input = context.review_payload()
    assert reviewer_input["pending_source"] == pending.source_text
    assert reviewer_input["selected_identity_name"] == "Luis"
    assert reviewer_input["captured_at"] == NOW
    assert reviewer_input["already_written_fact_ordinals"] == [0, 1]
    # No canonical IDs/guards or additional tasks or previously written facts
    # are converted into write actions by this projection.
    assert "selected_note_id" not in reviewer_input
    assert "selected_identity_guard" not in reviewer_input
    assert not any("actions" in key for key in reviewer_input)
    assert {path: vault.read_text(path) for path in vault.list_markdown_paths()} == original


def test_wrong_conversation_and_cancelled_selected_work_never_prepare(tmp_path: Path) -> None:
    preview, repo, vault, _state = _ready(tmp_path)
    _reply(repo, vault, "Eric")
    with pytest.raises(CandidateContinuationContextError):
        _context(repo, vault, preview.request_id, conversation_id="other-chat")
    with pytest.raises(CandidateContinuationContextError):
        _context(repo, vault, "not-an-existing-id")
    (tmp_path / "other").mkdir()
    preview2, repo2, vault2, _state2 = _ready(tmp_path / "other")
    _reply(repo2, vault2, "cancelar")
    with pytest.raises(CandidateContinuationContextError):
        _context(repo2, vault2, preview2.request_id)


def test_identity_and_prior_fact_drift_reject_read_only_continuation(tmp_path: Path) -> None:
    preview, repo, vault, _state = _ready(tmp_path)
    _reply(repo, vault, "Luis")
    context = _context(repo, vault, preview.request_id)
    note = vault.root / "Luis.md"
    original = note.read_text(encoding="utf-8")
    note.write_text(original + "\n", encoding="utf-8")
    with pytest.raises(CandidateContinuationContextError):
        _context(repo, vault, preview.request_id)
    note.write_text(original, encoding="utf-8")
    assert _context(repo, vault, preview.request_id) == context
    # Existing independent facts must not be overwritten or silently retried
    day_path = vault.root / "calendar" / "days" / "2026-10-03.md"
    day_path.write_text(
        day_path.read_text(encoding="utf-8").replace("Hablé con Eric.", "Inventado."),
        encoding="utf-8",
    )
    with pytest.raises(CandidateContinuationContextError):
        _context(repo, vault, preview.request_id)


def test_tampered_source_fails_closed_and_keeps_no_write_authority(tmp_path: Path) -> None:
    preview, repo, vault, state = _ready(tmp_path)
    _reply(repo, vault, "Luis")
    path = state / "candidates" / (preview.request_id + ".json")
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["pending"][0]["text"] = "Voy a escribir un hecho inventado"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(CandidateContinuationContextError):
        _context(repo, vault, preview.request_id)


def test_multi_pending_source_is_not_reduced_to_one_choice(tmp_path: Path) -> None:
    preview, repo, vault, state = _ready(tmp_path)
    # Synthetic adversarial state with multiple candidates cannot gain a
    # scalar selected-person continuation from a single choice.
    _reply(repo, vault, "Luis")
    path = state / "candidates" / (preview.request_id + ".json")
    record = json.loads(path.read_text(encoding="utf-8"))
    record["pending"].append({**record["pending"][0], "id": "candidate-8"})
    path.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(CandidateContinuationContextError):
        _context(repo, vault, preview.request_id)


def test_prepared_evidence_revalidates_before_any_eventual_write(tmp_path: Path) -> None:
    from odyssey_core.candidate_continuation_context import (
        validate_selected_continuation_current,
    )

    preview, repo, vault, _state = _ready(tmp_path)
    _reply(repo, vault, "Luis")
    prepared = _context(repo, vault, preview.request_id)
    validate_selected_continuation_current(prepared, repo, vault=vault, schema=SCHEMA)
    with pytest.raises(CandidateContinuationContextError):
        validate_selected_continuation_current(
            replace(prepared, selected_note_id="eric-id"), repo, vault=vault, schema=SCHEMA
        )
    note = vault.root / "Luis.md"
    note.write_text(note.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(CandidateContinuationContextError):
        validate_selected_continuation_current(prepared, repo, vault=vault, schema=SCHEMA)


def test_continuation_input_is_language_and_phrase_independent(tmp_path: Path) -> None:
    from odyssey_core.candidate_pending_projection import CandidatePendingItem

    preview, repo, vault, _state = _ready(tmp_path)
    initial = preview.original_request
    original_pending = preview.pending[0]
    source_prefix = initial[: original_pending.source_start]
    # Different grammar and date/language references use the same generic
    # original-span contract, not the former cinema-example write guard.
    for number, (sentence, reference) in enumerate(
        (
            ("Tomorrow I will visit the gallery with him", "him"),
            ("Demain je rencontrerai la personne avec lui", "lui"),
            ("El sábado hablaré de este proyecto con ella", "ella"),
        ),
        start=1,
    ):
        full_source = source_prefix + sentence
        start = len(source_prefix)
        end = len(full_source)
        reference_start = full_source.rfind(reference)
        item = CandidatePendingItem(
            candidate_id=original_pending.candidate_id,
            source_text=sentence,
            source_start=start,
            source_end=end,
            reason="ambiguous_identity",
            reference_text=reference,
            reference_start=reference_start,
            reference_end=reference_start + len(reference),
        )
        changed = replace(
            preview,
            original_request=full_source,
            pending=(item,),
            request_id=f"candidate-generic-{number}",
            physically_verified_fact_count=0,
            completed_fact_markers=(),
        )
        repo.record(
            changed,
            conversation_id="chat-1",
            created_at=NOW,
            options=(
                ClarificationOption("eric-id", "Eric"),
                ClarificationOption("luis-id", "Luis"),
            ),
            vault=vault,
            schema=SCHEMA,
        )
        result = repo.reply(
            conversation_id="chat-1",
            reply="Con Luis",
            answer_id=f"reply-{number}",
            vault=vault,
            schema=SCHEMA,
            immediate_followup=False,
            request_id=changed.request_id,
        )
        assert result.outcome == "choice_recorded"
        prepared = _context(repo, vault, changed.request_id)
        assert prepared.pending_source == sentence
        assert prepared.reference_text == reference
        assert prepared.captured_at == NOW
        assert prepared.completed_facts == ()
        assert prepared.may_execute is False


def test_prewrite_recheck_rejects_a_consistently_replaced_original_source(tmp_path: Path):
    """Even internally coherent changed source invalidates an earlier review."""
    from odyssey_core.candidate_continuation_context import (
        validate_selected_continuation_current,
    )

    preview, repo, vault, state = _ready(tmp_path)
    _reply(repo, vault, "Luis")
    prepared = _context(repo, vault, preview.request_id)
    path = state / "candidates" / (preview.request_id + ".json")
    record = json.loads(path.read_text(encoding="utf-8"))
    old = record["pending"][0]["text"]
    changed = old.replace("cine", "casa")
    assert len(old) == len(changed)
    record["original_request"] = record["original_request"].replace(old, changed)
    record["pending"][0]["text"] = changed
    path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
    latest = _context(repo, vault, preview.request_id)
    assert latest.pending_source == changed
    assert latest.pending_record_digest != prepared.pending_record_digest
    with pytest.raises(CandidateContinuationContextError):
        validate_selected_continuation_current(prepared, repo, vault=vault, schema=SCHEMA)
