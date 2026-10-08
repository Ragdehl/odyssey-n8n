"""Provider-free regression coverage for Core-private persisted-reference evidence."""

from __future__ import annotations

import json
from pathlib import Path

import odyssey_core.application as application
from odyssey_core.application import execute_request
from odyssey_core.notes import Note, serialize_note
from odyssey_core.reference_preflight import UnitTargetPreflight
from odyssey_core.request_planning import (
    KnowledgeReference,
    KnowledgeUnit,
    RequestPlan,
    SelectionCriteria,
    WriteAction,
)
from odyssey_core.storage import VaultRepository
from odyssey_core.write_target import WriteTargetOutcome
from odyssey_runtime.serialization import application_result_to_response

ROOT = Path(__file__).resolve().parents[2]


class FrozenPlanner:
    """Return one validated-shaped deterministic plan without a provider."""

    def __init__(self, plan: RequestPlan) -> None:
        self._plan = plan

    def plan(self, request: str, conversation_context=()) -> RequestPlan:
        """Return the fixed plan while accepting the production planner signature."""
        return self._plan


class EmptyIndex:
    """Keep the disposable fixture on exact resolution and CREATE paths."""

    def find_candidates(self, *args: object, **kwargs: object) -> tuple[object, ...]:
        """Return no semantic candidates."""
        return ()


class NoReasoner:
    """Fail if the exact fixture unexpectedly needs model-backed resolution."""

    def resolve(self, request: object) -> object:
        """Reject an unplanned contextual-resolution call."""
        raise AssertionError("fixture should not invoke contextual resolution")


def _unit(
    name: str,
    facts: tuple[str, ...] = (),
    references: tuple[KnowledgeReference, ...] = (),
    *,
    reference_lookup_only: bool = False,
) -> KnowledgeUnit:
    """Build one small record unit with an explicit person identity."""
    return KnowledgeUnit(
        SelectionCriteria(name, name, "person", (), None),
        "record",
        (),
        (),
        facts,
        references,
        reference_lookup_only=reference_lookup_only,
    )


def _write_existing(vault: Path, *, aliases: tuple[str, ...] = ()) -> None:
    """Create one isolated, valid canonical Eric fixture."""
    vault.mkdir(parents=True)
    value = Note(
        {
            "id": "eric-id",
            "name": "Eric",
            "type": "person",
            "aliases": list(aliases),
            "created_at": "2026-10-08T10:00:00Z",
            "updated_at": "2026-10-08T10:00:00Z",
            "created_by": {"human": None, "app": "test"},
            "updated_by": {"human": None, "app": "test"},
            "revision": 1,
            "schema_version": 3,
        },
        "",
    )
    (vault / "Eric.md").write_text(serialize_note(value), encoding="utf-8")


def _run(tmp_path: Path, source: KnowledgeUnit, target: KnowledgeUnit):
    """Execute an actual Core write against a disposable repository."""
    vault = tmp_path / "vault"
    _write_existing(vault, aliases=("Éric",))
    schema = json.loads((ROOT / "config/note-schema.json").read_text(encoding="utf-8"))
    return execute_request(
        "Hablé con Eric.",
        planner=FrozenPlanner(
            RequestPlan((WriteAction((source, target)),), ()),
        ),
        repository=VaultRepository(vault),
        schema=schema,
        context_index=object(),
        semantic_index=EmptyIndex(),
        embedder=object(),
        contextual_reasoner=NoReasoner(),
        actor="test",
        now="2026-10-08T12:00:00Z",
        context_limit=5,
        request_id_factory=lambda: "reference-evidence-request",
        preflight_id_allocator=lambda: "laura-id",
    )


def test_core_emits_private_evidence_only_for_a_persisted_canonical_reference(
    tmp_path: Path,
) -> None:
    """Carry canonical Eric only after the rendered source fact exists in the disposable vault."""
    source = _unit(
        "Laura",
        ("Hoy hablé con {{ref:0}}.",),
        (KnowledgeReference(1, "person", "Eric"),),
    )
    result = _run(tmp_path, source, _unit("Eric"))

    assert len(result.canonical_reference_evidence) == 1
    evidence = result.canonical_reference_evidence[0]
    assert (evidence.source_mention, evidence.stable_note_id) == ("Eric", "eric-id")
    assert (evidence.note_type, evidence.canonical_name) == ("person", "Eric")
    assert evidence.source_note_id == "laura-id"
    assert evidence.source_content_guard and evidence.canonical_content_guard

    response = application_result_to_response(result)
    encoded = json.dumps(response)
    assert "canonical_reference_evidence" not in response
    assert evidence.source_content_guard not in encoded
    assert evidence.canonical_content_guard not in encoded


def test_core_rejects_alias_and_repeated_target_reference_evidence(tmp_path: Path) -> None:
    """Do not make alias wording or repeated canonical IDs available as an antecedent."""
    alias_source = _unit(
        "Laura",
        ("Hoy hablé con {{ref:0}}.",),
        (KnowledgeReference(1, "person", "Éric"),),
    )
    alias_result = _run(tmp_path / "alias", alias_source, _unit("Éric"))
    assert alias_result.action_results[0].status.value == "completed"
    assert alias_result.canonical_reference_evidence == ()

    repeated_source = _unit(
        "Laura",
        ("Hoy hablé con {{ref:0}} y después vi a {{ref:1}}.",),
        (
            KnowledgeReference(1, "person", "Eric"),
            KnowledgeReference(1, "person", "Eric"),
        ),
    )
    assert (
        _run(tmp_path / "repeated", repeated_source, _unit("Eric")).canonical_reference_evidence
        == ()
    )
    helper_source = _unit(
        "Laura",
        ("Hoy hablé con {{ref:0}}.",),
        (KnowledgeReference(1, "person", "Eric"),),
    )
    helper_result = _run(
        tmp_path / "helper", helper_source, _unit("Eric", reference_lookup_only=True)
    )
    assert len(helper_result.canonical_reference_evidence) == 1
    assert helper_result.canonical_reference_evidence[0].stable_note_id == "eric-id"
    assert helper_result.affected_stable_note_ids == ("laura-id",)


def test_failed_source_reference_never_reaches_the_private_carrier() -> None:
    """Fail closed before any repository lookup when its fact-bearing unit did not persist."""
    source = _unit(
        "Laura",
        ("Hoy hablé con {{ref:0}}.",),
        (KnowledgeReference(1, "person", "Eric"),),
    )
    action = WriteAction((source, _unit("Eric")))
    evidence = application._collect_persisted_reference_evidence(
        0,
        action,
        (
            UnitTargetPreflight(0, WriteTargetOutcome.CREATE, "laura-id", "Laura", "Laura.md"),
            UnitTargetPreflight(1, WriteTargetOutcome.UPDATE, "eric-id", "Eric", "Eric.md"),
        ),
        (("Hoy hablé con [[Eric|Eric]].",), ()),
        [
            application.UnitResult(0, application.UnitStatus.FAILED, stable_note_id="laura-id"),
            application.UnitResult(1, application.UnitStatus.SUCCEEDED, stable_note_id="eric-id"),
        ],
        ((0,), ()),
        "request",
        object(),
        {},
    )
    assert evidence == ()


def test_calendar_day_emits_grounded_reference_for_prior_route_handoff(tmp_path: Path) -> None:
    """A dated fact linking Eric must carry Core evidence of Eric, not merely the changed Day ID."""
    from odyssey_core.temporal import TemporalAnchor

    vault = tmp_path / "vault"
    _write_existing(vault)
    schema = json.loads((ROOT / "config/note-schema.json").read_text(encoding="utf-8"))
    day_unit = KnowledgeUnit(
        SelectionCriteria(None, "2026-10-07", "calendar_day", (), None),
        "record",
        (),
        (),
        ("Ayer hablé con {{ref:0}}.",),
        (KnowledgeReference(1, "person", "Eric"),),
        fact_temporal_anchors=((TemporalAnchor("2026-10-07"),),),
    )
    result = execute_request(
        "Ayer hablé con Eric.",
        planner=FrozenPlanner(
            RequestPlan((WriteAction((day_unit, _unit("Eric", reference_lookup_only=True))),), ())
        ),
        repository=VaultRepository(vault),
        schema=schema,
        context_index=object(),
        semantic_index=EmptyIndex(),
        embedder=object(),
        contextual_reasoner=NoReasoner(),
        actor="test",
        now="2026-10-08T12:00:00Z",
        context_limit=5,
        request_id_factory=lambda: "day-route-canonical-ref",
        preflight_id_allocator=lambda: "unused-id",
    )
    assert result.status is application.ApplicationStatus.COMPLETED
    assert result.affected_stable_note_ids == ("date:2026-10-07",)
    assert len(result.canonical_reference_evidence) == 1
    evidence = result.canonical_reference_evidence[0]
    assert evidence.source_note_id == "date:2026-10-07"
    assert (evidence.source_mention, evidence.stable_note_id) == ("Eric", "eric-id")
    assert evidence.note_type == "person"
    day = (vault / "calendar/days/2026-10-07.md").read_text()
    assert "[[" in day and "Eric" in day
    assert evidence.source_content_guard and evidence.canonical_content_guard


def test_dependent_guard_rejects_stale_or_marker_free_reference(tmp_path: Path) -> None:
    """Never authorize a stale predecessor, wrong ID, or a dependent unlinked fact."""
    import pytest

    from odyssey_core.application import DependentReferenceGuard, WritePreflightGuardError

    source = _unit(
        "Laura", ("Hoy hablé con {{ref:0}}.",), (KnowledgeReference(1, "person", "Eric"),)
    )
    result = _run(tmp_path, source, _unit("Eric", reference_lookup_only=True))
    assert len(result.canonical_reference_evidence) == 1
    evidence = result.canonical_reference_evidence[0]
    guard = DependentReferenceGuard("él", evidence)
    schema = json.loads((ROOT / "config/note-schema.json").read_text(encoding="utf-8"))
    repo = VaultRepository(tmp_path / "vault")
    action = WriteAction(
        (
            _unit(
                "Otra", ("Iré al cine con {{ref:0}}.",), (KnowledgeReference(1, "person", "él"),)
            ),
            _unit("Eric", reference_lookup_only=True),
        )
    )
    correct = (
        UnitTargetPreflight(0, WriteTargetOutcome.CREATE, "otra-id", "Otra", "Otra.md"),
        UnitTargetPreflight(
            1, WriteTargetOutcome.UPDATE, "eric-id", "Eric", "Eric.md", reference_only=True
        ),
    )
    guard(action, correct, repo, schema)
    with pytest.raises(WritePreflightGuardError, match="REFERENCE_MARKER_REQUIRED"):
        guard(
            WriteAction(
                (
                    _unit(
                        "Otra", ("Iré al cine con él.",), (KnowledgeReference(1, "person", "él"),)
                    ),
                    _unit("Eric", reference_lookup_only=True),
                )
            ),
            correct,
            repo,
            schema,
        )
    wrong = (
        correct[0],
        UnitTargetPreflight(1, WriteTargetOutcome.UPDATE, "other-id", "Eric", "Other.md"),
    )
    with pytest.raises(WritePreflightGuardError, match="REFERENCE_MARKER_REQUIRED"):
        guard(action, wrong, repo, schema)

    source_note = next((tmp_path / "vault").glob("Laura*.md"))
    original = source_note.read_text()
    source_note.write_text(original + "\n", encoding="utf-8")
    with pytest.raises(WritePreflightGuardError, match="CANONICAL_EVIDENCE_STALE"):
        guard(action, correct, repo, schema)
