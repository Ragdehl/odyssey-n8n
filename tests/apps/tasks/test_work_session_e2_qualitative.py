"""E2 shared qualifier preparation delegates persistence to Tasks-owned service."""

from __future__ import annotations

from dataclasses import replace

import pytest

from odyssey_core.domain_interpretation import DomainEvidence, DomainInterpretation
from odyssey_core.execution_context import ContextContractError, ExecutionContext, QualitativeTime
from odyssey_core.qualitative_fact_preservation import preserve_qualitative_activity_text
from tests.apps.tasks.test_work_sessions import _build, _task_tokens

SOURCE = "Mañana por la tarde trabajaré en Odyssey."
PHRASE = "Mañana por la tarde"


def verified_context():
    return ExecutionContext(
        "session-temporal",
        SOURCE,
        "2026-10-15T10:00:00+02:00",
        "Europe/Paris",
        domains=(
            DomainInterpretation(
                "temporal",
                SOURCE,
                "TEMPORAL_RESOLUTION",
                (DomainEvidence("temporal_reference", PHRASE, "2026-10-16"),),
            ),
        ),
        qualitative_times=(QualitativeTime(PHRASE, "2026-10-16", "por la tarde", "Europe/Paris"),),
    )


def test_work_session_activity_uses_core_guard_and_existing_writer_without_clock(tmp_path):
    repo, service = _build(tmp_path)
    revision, source_hash = _task_tokens(repo)
    session = service.start(
        task_id="task-odyssey",
        started_at="2026-10-15T09:00:00+02:00",
        expected_task_revision=revision,
        expected_task_source_hash=source_hash,
        request_id="e2-session-open",
        actor="test",
        now="2026-10-15T09:00:00+02:00",
    )
    result = service.add_activity(
        session_id=session.session.id,
        text="Trabajé en Odyssey.",
        qualitative_context=verified_context(),
        expected_revision=session.session.revision,
        expected_source_hash=session.session.source_hash,
        request_id="e2-session-add",
        actor="test",
        now="2026-10-15T09:10:00+02:00",
    )
    assert result.session.activity[0].text == "Trabajé en Odyssey (por la tarde)."
    assert result.session.started_at == session.session.started_at
    assert result.session.activity[0].created_at == "2026-10-15T09:10:00+02:00"
    assert repo.read_text("odyssey.md").find("por la tarde") < 0
    assert "15:00" not in repo.read_text(result.path)
    repeated = service.edit_activity(
        session_id=result.session.id,
        activity_id=result.session.activity[0].id,
        text="Trabajé en Odyssey por la tarde.",
        qualitative_context=verified_context(),
        expected_revision=result.session.revision,
        expected_source_hash=result.session.source_hash,
        request_id="e2-session-edit",
        actor="test",
        now="2026-10-15T09:11:00+02:00",
    )
    assert repeated.session.activity[0].text.count("por la tarde") == 1


def test_ambiguous_qualitative_context_does_not_write_activity_or_advance_revision(tmp_path):
    repo, service = _build(tmp_path)
    revision, source_hash = _task_tokens(repo)
    started = service.start(
        task_id="task-odyssey",
        started_at="2026-10-15T09:00:00+02:00",
        expected_task_revision=revision,
        expected_task_source_hash=source_hash,
        request_id="e2-open-ambiguous",
        actor="test",
        now="2026-10-15T09:00:00+02:00",
    )
    before = repo.read_text(started.path)
    ctx = verified_context()
    invalid = replace(ctx, qualitative_times=ctx.qualitative_times * 2)
    with pytest.raises(ContextContractError, match="multiple unowned"):
        service.add_activity(
            session_id=started.session.id,
            text="Trabajé en Odyssey.",
            qualitative_context=invalid,
            expected_revision=started.session.revision,
            expected_source_hash=started.session.source_hash,
            request_id="e2-ambiguous",
            actor="test",
            now="2026-10-15T09:10:00+02:00",
        )
    assert repo.read_text(started.path) == before
    assert (
        preserve_qualitative_activity_text("Trabajé en Odyssey por la tarde.", context=ctx).count(
            "por la tarde"
        )
        == 1
    )


def test_task_selected_session_uses_same_verified_activity_context_and_date(tmp_path):
    from odyssey_apps.tasks.work_sessions import WorkSessionError

    repo, service = _build(tmp_path)
    revision, source_hash = _task_tokens(repo)
    started = service.start(
        task_id="task-odyssey",
        started_at="2026-10-16T09:00:00+02:00",
        expected_task_revision=revision,
        expected_task_source_hash=source_hash,
        request_id="start-scoped-activity",
        actor="test",
        now="2026-10-16T09:00:00+02:00",
    )
    written = service.add_activity_for_task(
        task_id="task-odyssey",
        text="Trabajé en Odyssey.",
        session_date="2026-10-16",
        qualitative_context=verified_context(),
        request_id="activity-scoped",
        actor="test",
        now="2026-10-16T18:00:00+02:00",
    )
    assert written.session.id == started.session.id
    assert written.session.activity[0].text == "Trabajé en Odyssey (por la tarde)."
    before = repo.read_text(written.path)
    with pytest.raises(
        WorkSessionError, match="WORK_SESSION_UNAVAILABLE|WORK_SESSION_TEMPORAL_INVALID"
    ):
        service.add_activity_for_task(
            task_id="task-odyssey",
            text="Trabajé en Odyssey.",
            session_date="2026-10-15",
            qualitative_context=verified_context(),
            request_id="activity-wrong-date",
            actor="test",
            now="2026-10-16T18:02:00+02:00",
        )
    assert repo.read_text(written.path) == before
