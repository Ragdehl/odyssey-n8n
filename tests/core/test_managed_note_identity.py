"""E2: same read-only managed-Note Protocol across Core Day and Tasks sessions.

No adapter inherits ManagedNoteIdentityPort. Only explicit current Core/App
read methods decide identities; a protocol does not authorize generic writes.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from odyssey_apps.schema_extensions import compose_application_schema
from odyssey_apps.tasks import TASK_SCHEMA_EXTENSION
from odyssey_core.execution_context import ContextContractError
from odyssey_core.identity import resolve_exact_entity
from odyssey_core.managed_note_identity import (
    CalendarDayIdentityPort,
    ManagedNoteHandle,
    ManagedNoteIdentityPort,
    WorkSessionIdentityPort,
    locate_managed_note,
)
from odyssey_core.schema_types import referenceable_type_ids
from odyssey_core.temporal import CalendarDayRepository
from tests.apps.tasks.test_work_sessions import _build, _task_tokens

ROOT = Path(__file__).resolve().parents[2]
BASE = json.loads((ROOT / "config/note-schema.json").read_text())
SCHEMA = compose_application_schema(BASE, (TASK_SCHEMA_EXTENSION,))


def test_derived_schema_registers_task_as_referenceable_but_work_session_remains_managed():
    assert "task" in referenceable_type_ids(SCHEMA)
    assert "work_session" not in referenceable_type_ids(SCHEMA)
    assert "calendar_day" not in referenceable_type_ids(SCHEMA)
    assert "task" not in referenceable_type_ids(BASE)


def test_task_uses_existing_core_lookup_with_composed_runtime_schema(tmp_path):
    repository, service = _build(tmp_path)
    _ = service
    result = resolve_exact_entity(repository, SCHEMA, "Trabajar en Odyssey", type="task")
    assert result.candidate is not None
    assert result.candidate.id == "task-odyssey"
    assert result.candidate.type == "task"
    assert repository.read_text("odyssey.md")


def test_calendar_day_adapter_implements_protocol_without_inheritance(tmp_path):
    repository, service = _build(tmp_path)
    _ = service
    port = CalendarDayIdentityPort(CalendarDayRepository(repository, SCHEMA))
    assert ManagedNoteIdentityPort not in CalendarDayIdentityPort.__bases__
    assert isinstance(port, ManagedNoteIdentityPort)
    virtual = locate_managed_note(port, "2026-10-15", schema=SCHEMA)
    assert virtual == ManagedNoteHandle("date:2026-10-15", "calendar_day", "core", False)
    # A virtual calendar day is not secretly materialized by a read.
    assert not any(
        "calendar/days/2026-10-15.md" == path for path in repository.list_markdown_paths()
    )
    (repository.root / "calendar" / "days").mkdir(parents=True)
    materialized = port._days.materialize(
        "2026-10-15", actor="fixture", now="2026-10-15T08:00:00+02:00"
    )
    assert materialized.materialized
    assert locate_managed_note(port, "2026-10-15", schema=SCHEMA) == ManagedNoteHandle(
        "date:2026-10-15", "calendar_day", "core", True
    )


def test_work_session_adapter_reuses_existing_tasks_scope_without_write(tmp_path):
    repository, sessions = _build(tmp_path)
    revision, source_hash = _task_tokens(repository)
    session = sessions.start(
        task_id="task-odyssey",
        started_at="2026-10-05T18:00:00+02:00",
        expected_task_revision=revision,
        expected_task_source_hash=source_hash,
        request_id="start-e2-port",
        actor="test",
        now="2026-10-05T18:00:00+02:00",
    )
    port = WorkSessionIdentityPort(sessions, task_id="task-odyssey")
    assert ManagedNoteIdentityPort not in WorkSessionIdentityPort.__bases__
    assert isinstance(port, ManagedNoteIdentityPort)
    result = locate_managed_note(port, session.session.id, schema=SCHEMA)
    assert result == ManagedNoteHandle(session.session.id, "work_session", "tasks", True)
    assert session.session.id not in referenceable_type_ids(SCHEMA)
    # Another Task cannot hijack the session and claim a link target.
    other_owner = WorkSessionIdentityPort(sessions, task_id="task-taxes")
    with pytest.raises(ContextContractError, match="not uniquely"):
        locate_managed_note(other_owner, session.session.id, schema=SCHEMA)
    assert repository.read_text(session.path)


def test_owner_and_type_guard_fails_closed_even_for_shape_compatible_ports(tmp_path):
    repository, _service = _build(tmp_path)

    class FakeOwner:
        note_type = "work_session"

        def locate(self, key: str) -> ManagedNoteHandle:
            return ManagedNoteHandle(key, "work_session", "core", True)

    assert isinstance(FakeOwner(), ManagedNoteIdentityPort)
    with pytest.raises(ContextContractError, match="incorrect owner"):
        locate_managed_note(FakeOwner(), "stolen-session", schema=SCHEMA)

    class Malformed:
        note_type = "work_session"

        def locate(self, key: str) -> str:
            return key

    # A runtime-checkable Protocol only checks method presence, NOT signatures.
    assert isinstance(Malformed(), ManagedNoteIdentityPort)
    with pytest.raises(ContextContractError, match="incorrect owner"):
        locate_managed_note(Malformed(), "session-1", schema=SCHEMA)

    class NotAPort:
        pass

    assert not isinstance(NotAPort(), ManagedNoteIdentityPort)
    with pytest.raises(ContextContractError, match="missing required"):
        locate_managed_note(NotAPort(), "session-1", schema=SCHEMA)


def test_non_managed_schema_type_cannot_be_substituted_as_owner():
    class ClaimOwner:
        note_type = "person"

        def locate(self, key: str) -> ManagedNoteHandle:
            return ManagedNoteHandle(key, "person", "core", True)

    with pytest.raises(ContextContractError, match="no schema owner"):
        locate_managed_note(ClaimOwner(), "marta", schema=SCHEMA)


def test_calendar_and_work_session_share_real_execution_context_port(tmp_path):
    from odyssey_core.execution_context import (
        ContextPort,
        ExecutionContext,
        StageSpec,
        run_context_stage,
        stage_input,
    )
    from odyssey_core.managed_note_identity import ManagedNoteContextStage

    repository, sessions = _build(tmp_path)
    revision, source_hash = _task_tokens(repository)
    result = sessions.start(
        task_id="task-odyssey",
        started_at="2026-10-05T18:00:00+02:00",
        expected_task_revision=revision,
        expected_task_source_hash=source_hash,
        request_id="test-e2-handoff",
        actor="fixture",
        now="2026-10-05T18:00:00+02:00",
    )
    day = CalendarDayIdentityPort(CalendarDayRepository(repository, SCHEMA))
    work = WorkSessionIdentityPort(sessions, task_id="task-odyssey")
    ctx = ExecutionContext(
        "req-read-only",
        "Consultar sesión y calendario",
        "2026-10-15T09:00:00+02:00",
        "Europe/Paris",
    )
    stage = ManagedNoteContextStage(
        lookups=((day, "2026-10-15"), (work, result.session.id)),
        schema=SCHEMA,
    )
    enriched = run_context_stage(ctx, stage)
    assert enriched.managed_notes == (
        ManagedNoteHandle("date:2026-10-15", "calendar_day", "core", False),
        ManagedNoteHandle(result.session.id, "work_session", "tasks", True),
    )
    assert ctx.managed_notes == ()
    assert enriched.domains == () and enriched.note_mentions == ()
    assert not hasattr(enriched, "authorize_write")
    consumer = StageSpec(
        "calendar.read", frozenset({ContextPort.MANAGED_NOTES}), frozenset({ContextPort.PENDING})
    )
    projection = stage_input(enriched, consumer)
    assert projection.managed_notes == enriched.managed_notes
    assert projection.actor is None and projection.source is None


def test_managed_stage_cannot_replace_existing_handle_or_relabel_owner(tmp_path):
    from dataclasses import replace

    from odyssey_core.execution_context import (
        ContextContractError,
        ExecutionContext,
        run_context_stage,
    )
    from odyssey_core.managed_note_identity import ManagedNoteContextStage

    repository, _sessions = _build(tmp_path)
    day = CalendarDayIdentityPort(CalendarDayRepository(repository, SCHEMA))
    stage = ManagedNoteContextStage(lookups=((day, "2026-10-15"),), schema=SCHEMA)
    initial = ExecutionContext(
        "read-note", "Día 15 de octubre", "2026-10-15T09:00:00+02:00", "Europe/Paris"
    )
    enriched = run_context_stage(initial, stage)
    with pytest.raises(ContextContractError, match="duplicated"):
        run_context_stage(enriched, stage)
    with pytest.raises(ContextContractError, match="duplicated"):
        replace(enriched, managed_notes=enriched.managed_notes + enriched.managed_notes)


def test_work_session_text_uses_shared_generic_project_lookup_without_second_resolver(tmp_path):
    from odyssey_core.execution_context import (
        ExecutionContext,
        NoteReferenceCandidate,
        run_context_stage,
    )
    from odyssey_core.note_lookup_batch import NoteLookupRequest, ParallelExactNoteLookup
    from odyssey_core.persistence import create_entity

    repository, service = _build(tmp_path)
    create_entity(
        repository,
        SCHEMA,
        path="Atlas.md",
        entity_id="project-atlas",
        metadata={"name": "Proyecto Atlas", "type": "project"},
        content="",
        actor="fixture",
        now="2026-10-05T16:00:00+02:00",
    )
    revision, source_hash = _task_tokens(repository)
    session = service.start(
        task_id="task-odyssey",
        started_at="2026-10-05T18:00:00+02:00",
        expected_task_revision=revision,
        expected_task_source_hash=source_hash,
        request_id="ws-start",
        actor="fixture",
        now="2026-10-05T18:00:00+02:00",
    )
    text = "He revisado Proyecto Atlas con Marta."
    saved = service.add_activity(
        session_id=session.session.id,
        text=text,
        expected_revision=session.session.revision,
        expected_source_hash=session.session.source_hash,
        request_id="ws-activity",
        actor="fixture",
        now="2026-10-05T18:30:00+02:00",
    )
    assert saved.session.activity[0].text == text
    start = text.index("Proyecto Atlas")
    port = ParallelExactNoteLookup(
        requests=(
            NoteLookupRequest("Proyecto Atlas", start, start + len("Proyecto Atlas"), "project"),
        ),
        repository=repository,
        schema=SCHEMA,
    )
    context = ExecutionContext("e2-work-session", text, "2026-10-05T18:30:00+02:00", "Europe/Paris")
    prepared = run_context_stage(context, port)
    assert prepared.note_mentions[0].candidates == (
        NoteReferenceCandidate("project-atlas", "project", "Proyecto Atlas"),
    )
    assert prepared.pending == ()
    assert service.list_for_task("task-odyssey")[0].activity[0].text == text
    # E2 prepares read-only candidates; E3 will safely render + persist links.
    assert "[[" not in saved.session.activity[0].text


def test_independent_temporal_generic_lookup_and_managed_notes_use_one_context(tmp_path):
    """No central dispatcher branches when composing three independently typed ports."""
    from odyssey_core.domain_interpretation import DomainEvidence, DomainInterpretation
    from odyssey_core.execution_context import (
        ContextPort,
        ExecutionContext,
        QualitativeTime,
        StageInput,
        StageOutput,
        StageSpec,
        run_independent_stages,
    )
    from odyssey_core.managed_note_identity import ManagedNoteContextStage
    from odyssey_core.note_lookup_batch import NoteLookupRequest, ParallelExactNoteLookup
    from odyssey_core.persistence import create_entity

    repository, service = _build(tmp_path)
    create_entity(
        repository,
        SCHEMA,
        path="Atlas.md",
        entity_id="project-atlas",
        metadata={"name": "Proyecto Atlas", "type": "project"},
        content="",
        actor="test",
        now="2026-10-05T16:00:00+02:00",
    )
    revision, source_hash = _task_tokens(repository)
    session = service.start(
        task_id="task-odyssey",
        started_at="2026-10-05T18:00:00+02:00",
        expected_task_revision=revision,
        expected_task_source_hash=source_hash,
        request_id="ws-start-merged",
        actor="test",
        now="2026-10-05T18:00:00+02:00",
    )
    source = "Mañana por la tarde trabajaré en Proyecto Atlas."

    class Temporal:
        spec = StageSpec(
            "temporal",
            frozenset({ContextPort.SOURCE, ContextPort.CLOCK}),
            frozenset({ContextPort.DOMAIN, ContextPort.TEMPORAL}),
        )

        def execute(self, data: StageInput) -> StageOutput:
            phrase = "Mañana por la tarde"
            assert data.source == source and data.actor is None
            return StageOutput(
                domains=(
                    DomainInterpretation(
                        "temporal",
                        data.source,
                        "TEMPORAL_RESOLUTION",
                        (DomainEvidence("temporal_reference", phrase, "2026-10-16"),),
                    ),
                ),
                qualitative_times=(
                    QualitativeTime(phrase, "2026-10-16", "por la tarde", "Europe/Paris"),
                ),
            )

    project_at = source.index("Proyecto Atlas")
    batch = ParallelExactNoteLookup(
        requests=(
            NoteLookupRequest(
                "Proyecto Atlas", project_at, project_at + len("Proyecto Atlas"), "project"
            ),
        ),
        repository=repository,
        schema=SCHEMA,
    )
    managed = ManagedNoteContextStage(
        lookups=(
            (CalendarDayIdentityPort(CalendarDayRepository(repository, SCHEMA)), "2026-10-16"),
            (WorkSessionIdentityPort(service, task_id="task-odyssey"), session.session.id),
        ),
        schema=SCHEMA,
    )
    original = ExecutionContext(
        "request-e2-merged", source, "2026-10-15T09:00:00+02:00", "Europe/Paris"
    )
    merged = run_independent_stages(original, (Temporal(), batch, managed))
    assert merged.qualitative_times[0].date == "2026-10-16"
    assert merged.note_mentions[0].candidates[0].stable_note_id == "project-atlas"
    assert [(x.note_type, x.materialized) for x in merged.managed_notes] == [
        ("calendar_day", False),
        ("work_session", True),
    ]
    assert original.domains == original.note_mentions == original.managed_notes == ()
    assert merged.authenticated_actor is None
