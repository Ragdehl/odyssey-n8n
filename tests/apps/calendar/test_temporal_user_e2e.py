"""Provider-free user-shaped Temporal -> Core -> Markdown -> Calendar regressions."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from types import SimpleNamespace

from odyssey_apps.calendar import CalendarQueryService
from odyssey_core import (
    AuthenticatedActorContext,
    SelfBindingRepository,
    create_entity,
)
from odyssey_core.application import ApplicationStatus, execute_request
from odyssey_core.atomic_facts import parse_atomic_facts
from odyssey_core.context import ContextIndex
from odyssey_core.domain_interpretation import (
    TEMPORAL_REFERENCE_EVIDENCE,
    DomainEvidence,
    DomainInterpretation,
)
from odyssey_core.experimental_luna_planning import validate_luna_experimental_result
from odyssey_core.note_queries import NotesQueryService
from odyssey_core.notes import parse_note
from odyssey_core.semantic import SemanticEntityIndex
from odyssey_core.storage import VaultRepository

ROOT = Path(__file__).resolve().parents[3]
SCHEMA = json.loads((ROOT / "config/note-schema.json").read_text(encoding="utf-8"))
USER_ID = "11111111-1111-4111-8111-111111111111"


class FirstFactReasoner:
    """Choose only the first canonical fact supplied by Core for an isolated fixture."""

    def resolve(self, request):  # type: ignore[no-untyped-def]
        candidate = request.candidates[0]
        return ({"outcome": "RESOLVED", "id": candidate.id, "ambiguous_ids": []}, {})


class ConstantEmbedder:
    """Keep isolated identity/index work deterministic and provider-free."""

    model_name = "tests/temporal-user-e2e"
    model_version = "1"

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [[1.0, 0.5] for _ in texts]

    def embed_queries(self, texts: Sequence[str]) -> list[list[float]]:
        return [[1.0, 0.5] for _ in texts]


def _environment(tmp_path: Path):  # type: ignore[no-untyped-def]
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "people").mkdir()
    repository = VaultRepository(vault)
    for note_id, name in (("bea", "Bea"), ("cloe", "Cloe"), ("bruno", "Bruno")):
        create_entity(
            repository,
            SCHEMA,
            path=f"people/{note_id}.md",
            entity_id=note_id,
            metadata={"name": name, "type": "person"},
            content="",
            actor="fixture",
            now="2026-10-04T12:00:00+02:00",
        )
    create_entity(
        repository,
        SCHEMA,
        path="people/self.md",
        entity_id="self-person",
        metadata={"name": "Edgar", "type": "person"},
        content="- Mis hijos son [[people/cloe|Cloe]] y [[people/bruno|Bruno]].",
        actor="fixture",
        now="2026-10-04T12:00:00+02:00",
    )
    state = tmp_path / "state"
    state.mkdir()
    bindings = SelfBindingRepository(state, repository, SCHEMA)
    bindings.bind(USER_ID, "self-person")
    embedder = ConstantEmbedder()
    context = ContextIndex(tmp_path / "runtime" / "context.sqlite3")
    semantic = SemanticEntityIndex(tmp_path / "runtime" / "semantic.sqlite3")
    assert context.rebuild(repository, SCHEMA, embedder) == 4
    assert semantic.rebuild(repository, SCHEMA, embedder) == 4
    return repository, bindings, embedder, context, semantic


def _plan(source: str, temporal_text: str, value: str, raw_result: dict):  # type: ignore[no-untyped-def]
    interpretation = DomainInterpretation(
        "temporal",
        source,
        "TEMPORAL_RESOLUTION",
        (DomainEvidence(TEMPORAL_REFERENCE_EVIDENCE, temporal_text, value),),
    )
    return validate_luna_experimental_result(
        raw_result,
        SCHEMA,
        interpretation,
        authorized_calendar_dates=(value[:10],),
    )


def _execute(tmp_path: Path, source: str, plan, *, request_id: str, now: str):  # type: ignore[no-untyped-def]
    repository, bindings, embedder, context, semantic = _environment(tmp_path)
    result = execute_request(
        source,
        planner=SimpleNamespace(plan=lambda _request: plan, is_local_replay=True),
        repository=repository,
        schema=SCHEMA,
        context_index=context,
        semantic_index=semantic,
        embedder=embedder,
        contextual_reasoner=FirstFactReasoner(),
        actor="e2e",
        authenticated_actor=AuthenticatedActorContext(USER_ID),
        self_binding_repository=bindings,
        now=now,
        context_limit=10,
        request_id_factory=lambda: request_id,
    )
    assert result.status is ApplicationStatus.COMPLETED
    context.rebuild(repository, SCHEMA, embedder)
    notes = NotesQueryService(repository, SCHEMA, context)
    return repository, CalendarQueryService(repository, SCHEMA, notes)


def test_day_fact_resolves_complete_children_set_end_to_end(tmp_path: Path) -> None:
    """Resolve every known child while preserving the user's natural set wording."""
    source = "Hoy hemos vaciado el garaje con Bea y mis hijos."
    raw = {
        "outcome": "PLAN",
        "actions": [
            {
                "kind": "write",
                "operations": [
                    {
                        "target": {
                            "description": "2026-10-04",
                            "binding": "described",
                            "direct_name": None,
                            "note_type": "calendar_day",
                            "filters": [],
                            "candidate_scope": None,
                        },
                        "apply_to": "one",
                        "intent": "record",
                        "facts": [
                            {
                                "parts": [
                                    {"kind": "literal", "text": "Hemos vaciado el garaje con "},
                                    {
                                        "kind": "identity",
                                        "text": "Bea",
                                        "identity": {
                                            "description": "Bea",
                                            "binding": "described",
                                            "direct_name": "Bea",
                                            "note_type": "person",
                                            "filters": [],
                                            "candidate_scope": None,
                                        },
                                    },
                                    {"kind": "literal", "text": " y "},
                                    {
                                        "kind": "identity",
                                        "text": "mis hijos",
                                        "identity": {
                                            "description": "mis hijos",
                                            "binding": "described",
                                            "direct_name": None,
                                            "note_type": "person",
                                            "filters": [],
                                            "candidate_scope": {
                                                "source": {"kind": "SELF"},
                                                "member_query": "mis hijos",
                                                "extent": "complete_set",
                                            },
                                        },
                                    },
                                    {"kind": "literal", "text": "."},
                                ]
                            }
                        ],
                        "properties": [],
                        "tag_changes": [],
                        "destination_type": None,
                    }
                ],
            }
        ],
        "limitations": [],
        "clarification_code": None,
        "presentation_intent": "answer",
    }
    plan = _plan(source, "Hoy", "2026-10-04", raw)
    repository, calendar = _execute(
        tmp_path, source, plan, request_id="e2e-bea-children", now="2026-10-04T16:00:00+02:00"
    )

    markdown = repository.read_text("calendar/days/2026-10-04.md")
    assert (
        "Hemos vaciado el garaje con [[people/bea|Bea]] y mis hijos "
        "([[people/cloe|Cloe]], [[people/bruno|Bruno]])." in markdown
    )
    assert repository.list_markdown_paths() == [
        "calendar/days/2026-10-04.md",
        "people/bea.md",
        "people/bruno.md",
        "people/cloe.md",
        "people/self.md",
    ]
    visible = [
        "".join(segment.text for segment in block.segments)
        for block in calendar.day("2026-10-04").content
    ]
    assert "Hemos vaciado el garaje con Bea y mis hijos (Cloe, Bruno)." in visible


def test_day_exact_time_has_canonical_clock_prefix_and_separate_capture_time_end_to_end(
    tmp_path: Path,
) -> None:
    """Show one exact semantic time as a stable Day prefix while preserving capture chronology."""
    source = "Mañana a las 15:35 voy al parque con Bea y mis hijos."
    raw = {
        "outcome": "PLAN",
        "actions": [
            {
                "kind": "write",
                "operations": [
                    {
                        "target": {
                            "description": "2026-10-05",
                            "binding": "described",
                            "direct_name": None,
                            "note_type": "calendar_day",
                            "filters": [],
                            "candidate_scope": None,
                        },
                        "apply_to": "one",
                        "intent": "record",
                        "facts": [
                            {
                                "parts": [
                                    {
                                        "kind": "temporal_reference",
                                        "text": "Mañana a las 15:35",
                                        "value": "2026-10-05T15:35:00+02:00",
                                    },
                                    {"kind": "literal", "text": " voy al parque con "},
                                    {
                                        "kind": "identity",
                                        "text": "Bea",
                                        "identity": {
                                            "description": "Bea",
                                            "binding": "described",
                                            "direct_name": "Bea",
                                            "note_type": "person",
                                            "filters": [],
                                            "candidate_scope": None,
                                        },
                                    },
                                    {"kind": "literal", "text": " y "},
                                    {
                                        "kind": "identity",
                                        "text": "mis hijos",
                                        "identity": {
                                            "description": "mis hijos",
                                            "binding": "described",
                                            "direct_name": None,
                                            "note_type": "person",
                                            "filters": [],
                                            "candidate_scope": {
                                                "source": {"kind": "SELF"},
                                                "member_query": "mis hijos",
                                                "extent": "complete_set",
                                            },
                                        },
                                    },
                                    {"kind": "literal", "text": "."},
                                ]
                            }
                        ],
                        "properties": [],
                        "tag_changes": [],
                        "destination_type": None,
                    }
                ],
            }
        ],
        "limitations": [],
        "clarification_code": None,
        "presentation_intent": "answer",
    }
    plan = _plan(source, "Mañana a las 15:35", "2026-10-05T15:35:00+02:00", raw)
    repository, calendar = _execute(
        tmp_path,
        source,
        plan,
        request_id="e2e-bea-children-time",
        now="2026-10-04T16:05:00+02:00",
    )

    note = parse_note(repository.read_text("calendar/days/2026-10-05.md"))
    fact = parse_atomic_facts(note.content)[0]
    assert fact.text == (
        "15:35 — voy al parque con [[people/bea|Bea]] y mis hijos "
        "([[people/cloe|Cloe]], [[people/bruno|Bruno]])."
    )
    assert fact.recorded_at == "2026-10-04T16:05:00+02:00"
    assert [anchor.value for anchor in fact.temporal_anchors] == ["2026-10-05T15:35:00+02:00"]
    visible = [
        "".join(segment.text for segment in block.segments)
        for block in calendar.day("2026-10-05").content
    ]
    assert "15:35 — voy al parque con Bea y mis hijos (Cloe, Bruno)." in visible
