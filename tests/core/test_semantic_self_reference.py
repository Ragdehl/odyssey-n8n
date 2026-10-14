"""Provider-free Core-bound SELF fact references for multilingual speaker semantics.

This tests identity binding and persistence, not an LLM's grammatical judgment.
The latter still requires independent source-evidence review and real DEV trials.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from odyssey_core import AuthenticatedActorContext, RequestPlan, execute_request
from odyssey_core.application import ApplicationStatus
from odyssey_core.notes import parse_note
from odyssey_core.semantic_write import (
    ApplyTo,
    IdentityBinding,
    IdentityIntent,
    IdentityPart,
    LiteralPart,
    SemanticFact,
    SemanticWriteCompileError,
    SemanticWriteIntent,
    SemanticWriteOperation,
    compile_semantic_write,
)
from tests.core.test_self_resolution import SCHEMA, USER_A, USER_B, binding_setup, person


@pytest.mark.parametrize(
    ("source", "speaker", "predicate"),
    [
        ("Ayer arreglé una silla.", "yo", " arregló una silla."),
        ("Hier j'ai réparé une chaise.", "je", " a réparé une chaise."),
        ("Yesterday I fixed a chair.", "I", " fixed a chair."),
    ],
)
def test_semantic_self_in_day_fact_resolves_only_existing_authenticated_person(
    tmp_path, source, speaker, predicate
):
    """A semantically justified speaker uses the same SELF binding, with no Person write."""
    vault, bindings = binding_setup(tmp_path)
    person(vault, "self-a", "people/a.md", "Alex")
    person(vault, "self-b", "people/b.md", "Alex")
    bindings.bind(USER_A, "self-a")
    bindings.bind(USER_B, "self-b")
    original_people = {path: vault.read_text(path) for path in ("people/a.md", "people/b.md")}
    day = IdentityIntent("2026-10-13", IdentityBinding.DESCRIBED, note_type="calendar_day")
    symbolic_self = IdentityIntent(speaker, IdentityBinding.SELF, note_type="person")
    intent = SemanticWriteIntent(
        (
            SemanticWriteOperation(
                day,
                ApplyTo.ONE,
                "record",
                (SemanticFact((IdentityPart(speaker, symbolic_self), LiteralPart(predicate))),),
            ),
        )
    )
    # Use the actual Core semantic compiler, then the actual canonical writer.
    action = compile_semantic_write(intent, SCHEMA, authorized_calendar_dates=("2026-10-13",))
    assert len(action.units) == 2
    assert action.units[0].target.type == "calendar_day"
    assert action.units[1].target.self_target == "self"
    assert action.units[1].reference_lookup_only is True
    plan = RequestPlan((action,), ())
    result = execute_request(
        source,
        planner=SimpleNamespace(plan=lambda _: plan),
        repository=vault,
        schema=SCHEMA,
        context_index=object(),
        semantic_index=object(),
        embedder=object(),
        contextual_reasoner=object(),
        actor={"human": USER_A, "app": "self-reference-test"},
        authenticated_actor=AuthenticatedActorContext(USER_A),
        self_binding_repository=bindings,
        now="2026-10-14T10:00:00+02:00",
        context_limit=5,
        request_id_factory=lambda: "self-day-write",
    )
    assert result.status is ApplicationStatus.COMPLETED
    day_content = vault.read_text("calendar/days/2026-10-13.md")
    assert "[[people/a|Alex]]" in day_content
    assert "[[people/b|Alex]]" not in day_content
    assert predicate.strip() in day_content
    for path, content in original_people.items():
        assert vault.read_text(path) == content
    assert parse_note(day_content).metadata["type"] == "calendar_day"


def test_unbound_self_fact_reference_fails_closed_without_person_creation(tmp_path):
    """No trusted self binding means no new self identity and no source day write."""
    vault, bindings = binding_setup(tmp_path)
    person(vault, "self-b", "people/b.md", "Alex")
    before = vault.read_text("people/b.md")
    day = IdentityIntent("2026-10-13", IdentityBinding.DESCRIBED, note_type="calendar_day")
    symbolic_self = IdentityIntent("yo", IdentityBinding.SELF, note_type="person")
    intent = SemanticWriteIntent(
        (
            SemanticWriteOperation(
                day,
                ApplyTo.ONE,
                "record",
                (
                    SemanticFact(
                        (IdentityPart("yo", symbolic_self), LiteralPart(" arregló una silla."))
                    ),
                ),
            ),
        )
    )
    action = compile_semantic_write(intent, SCHEMA, authorized_calendar_dates=("2026-10-13",))
    result = execute_request(
        "Ayer arreglé una silla.",
        planner=SimpleNamespace(plan=lambda _: RequestPlan((action,), ())),
        repository=vault,
        schema=SCHEMA,
        context_index=object(),
        semantic_index=object(),
        embedder=object(),
        contextual_reasoner=object(),
        actor={"human": USER_A, "app": "self-reference-test"},
        authenticated_actor=AuthenticatedActorContext(USER_A),
        self_binding_repository=bindings,
        now="2026-10-14T10:00:00+02:00",
        context_limit=5,
        request_id_factory=lambda: "unbound-self-day",
    )
    assert result.status is not ApplicationStatus.COMPLETED
    assert vault.read_text("people/b.md") == before
    assert not any(path.endswith("2026-10-13.md") for path in vault.list_markdown_paths())


@pytest.mark.parametrize(
    "spoofed_identity",
    [
        IdentityIntent("yo", IdentityBinding.SELF, "Alex", "person"),
        IdentityIntent("yo", IdentityBinding.SELF, note_type="project"),
    ],
)
def test_symbolic_self_reference_rejects_forged_selectors_or_non_person_type(
    spoofed_identity,
):
    """A model cannot select a named or non-Person actor by marking a fact part SELF."""
    # The ordinary valid SELF shape is covered by real Writer tests above.
    day = IdentityIntent("2026-10-13", IdentityBinding.DESCRIBED, note_type="calendar_day")
    intent = SemanticWriteIntent(
        (
            SemanticWriteOperation(
                day,
                ApplyTo.ONE,
                "record",
                (SemanticFact((IdentityPart("yo", spoofed_identity), LiteralPart(" llegó."))),),
            ),
        )
    )
    with pytest.raises(SemanticWriteCompileError):
        compile_semantic_write(intent, SCHEMA, authorized_calendar_dates=("2026-10-13",))
