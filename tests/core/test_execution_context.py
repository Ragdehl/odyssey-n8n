"""E2 contract: Lego-like stage compatibility without promoted semantic authority."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, replace

import pytest

from odyssey_core.domain_interpretation import DomainEvidence, DomainInterpretation
from odyssey_core.execution_context import (
    ContextContractError,
    ContextPort,
    ExecutionContext,
    NoteMention,
    NoteReferenceCandidate,
    PendingContext,
    QualitativeTime,
    StageInput,
    StageOutput,
    StageSpec,
    apply_stage_output,
    run_context_stage,
    stage_input,
)
from odyssey_core.identity_boundary import AuthenticatedActorContext
from odyssey_core.temporal_interpretation import TemporalInterpretation, TemporalMention
from odyssey_core.temporal_resolution import TemporalResolution, TemporalResolutionKind

SOURCE = "Mañana por la tarde hablaré de Proyecto Atlas y Marta."
WHEN = "Mañana por la tarde"
DATE = "2026-10-15"


def initial_context():
    return ExecutionContext(
        request_id="req-e2-1",
        source=SOURCE,
        captured_at="2026-10-14T23:57:00+02:00",
        timezone="Europe/Paris",
        authenticated_actor=AuthenticatedActorContext("6fba8596-fd24-4caa-9a7d-93a41a8f5730"),
        conversation_id="main",
    )


class TemporalStage:
    spec = StageSpec(
        "temporal",
        frozenset({ContextPort.SOURCE, ContextPort.CLOCK}),
        frozenset({ContextPort.DOMAIN, ContextPort.TEMPORAL}),
    )

    def execute(self, data: StageInput) -> StageOutput:
        assert data.source == SOURCE
        assert data.captured_at == "2026-10-14T23:57:00+02:00"
        assert data.timezone == "Europe/Paris"
        assert data.actor is None  # explicit least-privilege projection
        assert data.note_mentions == ()
        interpretation = TemporalInterpretation(
            data.source,
            (
                TemporalMention(
                    WHEN, TemporalResolution(TemporalResolutionKind.EXACT_DATE, exact_date=DATE)
                ),
            ),
        )
        return StageOutput(
            domains=(interpretation.core_domain_interpretation(),),
            qualitative_times=(QualitativeTime(WHEN, DATE, "por la tarde", data.timezone),),
        )


class GenericNoteResolver:
    """Hypotheses across Note types; only Core later grants canonical identity."""

    spec = StageSpec(
        "notes.candidates",
        frozenset({ContextPort.SOURCE}),
        frozenset({ContextPort.NOTE_MENTIONS}),
    )

    def execute(self, data: StageInput) -> StageOutput:
        assert data.actor is None
        assert data.captured_at is None
        assert data.source == SOURCE
        return StageOutput(
            note_mentions=(
                NoteMention(
                    "Proyecto Atlas",
                    (NoteReferenceCandidate("atlas1", "project", "Proyecto Atlas"),),
                ),
                NoteMention(
                    "Marta",
                    (
                        NoteReferenceCandidate("marta1", "person", "Marta"),
                        NoteReferenceCandidate("marta2", "person", "Marta"),
                    ),
                ),
            )
        )


class FutureApp:
    """The central execution coordinator never needs an `if app == x` branch."""

    spec = StageSpec(
        "future.app",
        frozenset({ContextPort.SOURCE, ContextPort.DOMAIN, ContextPort.NOTE_MENTIONS}),
        frozenset({ContextPort.DOMAIN, ContextPort.PENDING}),
    )

    def execute(self, data: StageInput) -> StageOutput:
        assert data.actor is None
        assert {x.capability_id for x in data.domains} == {"temporal"}
        assert len(data.note_mentions) == 2
        assert len(data.note_mentions[1].candidates) == 2  # ambiguity not silently resolved
        return StageOutput(
            domains=(
                DomainInterpretation(
                    "future",
                    data.source,
                    "CAPTURE",
                    (DomainEvidence("domain.activity", "hablaré", "call"),),
                ),
            ),
            pending=(PendingContext("future", "AMBIGUOUS_NOTE_REFERENCE"),),
        )


def test_shared_immutable_context_accepts_temporal_and_note_proposals_in_either_order():
    origin = initial_context()
    by_date_first = run_context_stage(
        run_context_stage(origin, TemporalStage()), GenericNoteResolver()
    )
    by_notes_first = run_context_stage(
        run_context_stage(origin, GenericNoteResolver()), TemporalStage()
    )
    assert by_date_first == by_notes_first
    assert by_date_first.source == SOURCE
    assert by_date_first.authenticated_actor == origin.authenticated_actor
    assert by_date_first.qualitative_times == (
        QualitativeTime(WHEN, DATE, "por la tarde", "Europe/Paris"),
    )
    assert by_date_first.domains[0].temporal_references()[0].value == DATE
    assert origin.domains == () and origin.note_mentions == ()
    with pytest.raises(FrozenInstanceError):
        origin.source = "altered"


def test_new_app_consumes_independent_domains_without_dispatcher_special_case():
    context = run_context_stage(
        run_context_stage(initial_context(), TemporalStage()), GenericNoteResolver()
    )
    enriched = run_context_stage(context, FutureApp())
    assert {domain.capability_id for domain in enriched.domains} == {"temporal", "future"}
    assert enriched.pending == (PendingContext("future", "AMBIGUOUS_NOTE_REFERENCE"),)
    assert enriched.note_mentions == context.note_mentions
    assert enriched.authenticated_actor == context.authenticated_actor
    assert enriched.qualitative_times == context.qualitative_times


@pytest.mark.parametrize(
    "note_type",
    [
        "person",
        "project",
        "task",
        "work_session",
        "calendar_day",
        "next_custom_note_type",
    ],
)
def test_note_references_are_generic_and_not_person_only(note_type):
    ref = NoteReferenceCandidate("stable123", note_type, "Una nota")
    assert ref.note_type == note_type
    assert ref.stable_note_id == "stable123"


def test_stage_sees_only_declared_ports_even_if_actor_exists():
    context = initial_context()
    only_source = StageSpec(
        "router", frozenset({ContextPort.SOURCE}), frozenset({ContextPort.NOTE_MENTIONS})
    )
    projected = stage_input(context, only_source)
    assert projected.source == SOURCE
    assert projected.actor is None
    assert projected.timezone is None
    assert projected.domains == ()
    assert (
        stage_input(
            context,
            StageSpec(
                "core.owner", frozenset({ContextPort.ACTOR}), frozenset({ContextPort.PENDING})
            ),
        ).actor
        == context.authenticated_actor
    )


def test_missing_dependencies_detected_before_side_effects():
    called = []

    class RequiresTemporal:
        spec = StageSpec(
            "event", frozenset({ContextPort.TEMPORAL}), frozenset({ContextPort.DOMAIN})
        )

        def execute(self, data):
            called.append(data)
            return StageOutput()

    with pytest.raises(ContextContractError, match="Missing required context ports"):
        run_context_stage(initial_context(), RequiresTemporal())
    assert called == []


@pytest.mark.parametrize(
    "output",
    [
        StageOutput(
            note_mentions=(
                NoteMention("Marta", (NoteReferenceCandidate("id123", "person", "Marta"),)),
            )
        ),
        StageOutput(pending=(PendingContext("core", "NEEDS_ATTENTION"),)),
    ],
)
def test_stage_cannot_send_undeclared_outputs(output):
    spec = StageSpec("temporal", frozenset({ContextPort.SOURCE}), frozenset({ContextPort.DOMAIN}))
    with pytest.raises(ContextContractError, match="undeclared"):
        apply_stage_output(initial_context(), spec, output)


def test_source_freshness_and_temporal_provenance_fail_closed():
    context = initial_context()
    evidence = DomainInterpretation(
        "temporal",
        SOURCE,
        "TEMPORAL_RESOLUTION",
        (DomainEvidence("temporal_reference", WHEN, DATE),),
    )
    spec = StageSpec(
        "temporal",
        frozenset({ContextPort.SOURCE}),
        frozenset({ContextPort.DOMAIN, ContextPort.TEMPORAL}),
    )
    with pytest.raises(ContextContractError, match="source/owner"):
        apply_stage_output(
            context,
            spec,
            StageOutput(domains=(replace(evidence, source_text="Other text Mañana por la tarde"),)),
        )
    with pytest.raises(ContextContractError, match="verified temporal date anchor"):
        apply_stage_output(
            context,
            spec,
            StageOutput(
                qualitative_times=(QualitativeTime(WHEN, DATE, "por la tarde", "Europe/Paris"),)
            ),
        )
    with pytest.raises(ContextContractError, match="verified temporal date anchor"):
        apply_stage_output(
            context,
            spec,
            StageOutput(
                domains=(evidence,),
                qualitative_times=(
                    QualitativeTime(WHEN, "2026-10-16", "por la tarde", "Europe/Paris"),
                ),
            ),
        )
    with pytest.raises(ContextContractError, match="verified temporal date anchor"):
        apply_stage_output(
            context,
            spec,
            StageOutput(
                domains=(evidence,),
                qualitative_times=(QualitativeTime("hablaré", DATE, "hablaré", "Europe/Paris"),),
            ),
        )


def test_duplicate_domain_and_ambiguous_untrusted_note_candidates_cannot_be_promoted():
    context = run_context_stage(initial_context(), GenericNoteResolver())
    with pytest.raises(ContextContractError):
        replace(context, note_mentions=(NoteMention("INVENTED", ()),))
    with pytest.raises(ContextContractError, match="Domain evidence source/owner"):
        temporal = TemporalStage().execute(stage_input(context, TemporalStage.spec))
        apply_stage_output(
            run_context_stage(context, TemporalStage()), TemporalStage.spec, temporal
        )
    assert len(context.note_mentions[1].candidates) == 2
    assert not hasattr(context, "authorize_write")
    assert not hasattr(StageOutput(), "authenticated_actor")


def test_wrong_actor_unversioned_context_and_bad_note_types_refused():
    ctx = initial_context()
    with pytest.raises(ContextContractError):
        replace(ctx, authenticated_actor={"stable_user_id": "spoofed"})
    with pytest.raises(ContextContractError):
        replace(ctx, version=2)
    with pytest.raises(ContextContractError):
        NoteReferenceCandidate("id123", "Person With Space", "Marta")
    with pytest.raises(ContextContractError):
        NoteMention(
            "Marta",
            (
                NoteReferenceCandidate("a", "person", "Marta"),
                NoteReferenceCandidate("a", "person", "Marta"),
            ),
        )


def test_parallel_temporal_and_note_resolution_share_exact_initial_source():
    from threading import Barrier

    from odyssey_core.execution_context import run_independent_stages

    barrier = Barrier(2)

    class ConcurrentTemporal(TemporalStage):
        def execute(self, data):
            barrier.wait(timeout=6)
            return super().execute(data)

    class ConcurrentNotes(GenericNoteResolver):
        def execute(self, data):
            barrier.wait(timeout=6)
            return super().execute(data)

    context = run_independent_stages(initial_context(), (ConcurrentTemporal(), ConcurrentNotes()))
    assert context.qualitative_times[0].qualifier == "por la tarde"
    assert len(context.note_mentions) == 2
    assert len(context.domains) == 1


def test_dependency_missing_or_conflicting_parallel_capabilities_prevent_invocation():
    from odyssey_core.execution_context import run_independent_stages

    invoked = []

    class DependentApp(FutureApp):
        def execute(self, data):
            invoked.append("app")
            return super().execute(data)

    class OtherTemporal(TemporalStage):
        def execute(self, data):
            invoked.append("temporal")
            return super().execute(data)

    with pytest.raises(ContextContractError, match="Dependent stages"):
        run_independent_stages(initial_context(), (OtherTemporal(), DependentApp()))
    assert invoked == []
    with pytest.raises(ContextContractError, match="Concurrent stage specification"):
        run_independent_stages(initial_context(), (OtherTemporal(), OtherTemporal()))
    assert invoked == []


def test_temporal_port_accepts_exact_date_even_without_daypart():
    """Adding qualitative precision must never break ordinary today/tomorrow dates."""
    context = initial_context()
    date = DomainInterpretation(
        "temporal",
        SOURCE,
        "TEMPORAL_RESOLUTION",
        (DomainEvidence("temporal_reference", WHEN, DATE),),
    )
    no_daypart = replace(context, domains=(date,))
    port = StageSpec(
        "future.calendar", frozenset({ContextPort.TEMPORAL}), frozenset({ContextPort.PENDING})
    )
    info = stage_input(no_daypart, port)
    assert len(info.temporal_references) == 1
    assert info.temporal_references[0].value == DATE
    assert info.qualitative_times == ()
    assert info.actor is None
    assert info.domains == ()


def test_protocol_stage_compatibility_is_structural_not_inheritance():
    """Runtime checks *presence*, then explicit boundary checks types/results."""
    from odyssey_core.execution_context import ContextStage

    stage = TemporalStage()
    assert ContextStage not in TemporalStage.__bases__
    assert isinstance(stage, ContextStage)
    assert run_context_stage(initial_context(), stage).qualitative_times

    class MissingExecute:
        spec = stage.spec

    assert not isinstance(MissingExecute(), ContextStage)
    with pytest.raises(ContextContractError, match="does not implement"):
        run_context_stage(initial_context(), MissingExecute())

    class WrongOutput:
        spec = stage.spec

        def execute(self, data) -> str:
            return "not StageOutput"

    # Protocol at runtime cannot inspect return annotations or actual values.
    assert isinstance(WrongOutput(), ContextStage)
    with pytest.raises(ContextContractError, match="typed StageOutput"):
        run_context_stage(initial_context(), WrongOutput())

    class WrongSpec:
        spec = {"requires": "source"}

        def execute(self, data):
            return StageOutput()

    assert isinstance(WrongSpec(), ContextStage)
    with pytest.raises(ContextContractError, match="does not implement"):
        run_context_stage(initial_context(), WrongSpec())
