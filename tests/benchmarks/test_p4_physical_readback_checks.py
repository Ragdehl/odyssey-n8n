"""Provider-free adversarial checks for physical P4 acceptance assertions."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from benchmarks.application_router.light_router_poc_20261016 import p4_physical_readback
from odyssey_core.notes import Note, serialize_note


def _note(identifier, name, note_type, body="", **properties):
    """Make a synthetic parseable Markdown note, never a real vault copy."""
    return serialize_note(
        Note({"id": identifier, "name": name, "type": note_type, **properties}, body)
    )


def _fixture(*, with_link=True, duplicate=False):
    """Build an undated SELF assertion with one canonical synthetic contact."""
    first = "- He conocido a [[Maya|Maya]].\n  <!-- odyssey:fact request=ex-self ordinal=0 -->\n"
    if duplicate:
        first += first
    before = {
        "self.md": _note("self-id", "Self", "person", "# Self\n"),
        "Maya.md": _note("maya-id", "Maya", "person"),
    }
    after = {**before, "self.md": _note("self-id", "Self", "person", first)}
    review = {
        "facts": [
            {
                "kind": "record",
                "date": None,
                "reference_names": ["Maya"],
                "reviewed_text": "He conocido a {{ref:0}}.",
            }
        ]
    }

    class Query:
        def __init__(self, *_):
            pass

        def detail(self, owner):
            return SimpleNamespace(
                body_blocks=[
                    SimpleNamespace(
                        fact_locator="ex-self:0",
                        segments=[
                            SimpleNamespace(target_id="maya-id" if with_link else "wrong-id")
                        ],
                    )
                ]
            )

        def backlinks(self, target):
            return SimpleNamespace(items=[SimpleNamespace(source=SimpleNamespace(id="self-id"))])

    return before, after, review, Query


def test_one_undated_self_fact_has_physical_canonical_person_link(monkeypatch):
    before, after, review, query = _fixture()
    monkeypatch.setattr(p4_physical_readback, "NotesQueryService", query)
    outcome = p4_physical_readback.assert_reviewed_markdown(
        repository=object(),
        schema={},
        context_index=object(),
        before=before,
        after=after,
        request_id="ex",
        review=review,
        self_roles=(True,),
        self_id="self-id",
    )
    assert outcome["physical_fact_count"] == 1
    assert outcome["physical_facts"][0]["owner_id"] == "self-id"


@pytest.mark.parametrize("fault", ["missing_owner", "wrong_person", "duplicate", "unproven_self"])
def test_unverified_physical_fact_never_passes_acceptance(monkeypatch, fault):
    before, after, review, query = _fixture(
        with_link=fault != "wrong_person", duplicate=fault == "duplicate"
    )
    if fault == "missing_owner":
        after = before
    monkeypatch.setattr(p4_physical_readback, "NotesQueryService", query)
    with pytest.raises(AssertionError):
        p4_physical_readback.assert_reviewed_markdown(
            repository=object(),
            schema={},
            context_index=object(),
            before=before,
            after=after,
            request_id="ex",
            review=review,
            self_roles=((fault != "unproven_self"),),
            self_id="self-id",
        )


def test_exact_preexisting_marked_fact_allows_safe_noop_without_new_write(monkeypatch):
    before, _after, review, _query = _fixture()
    prior = "- He conocido a [[Maya|Maya]].\n  <!-- odyssey:fact request=prior-self ordinal=0 -->\n"
    before["self.md"] = _note("self-id", "Self", "person", prior)

    class PriorQuery:
        def __init__(self, *_):
            pass

        def detail(self, _owner):
            return SimpleNamespace(
                body_blocks=[
                    SimpleNamespace(
                        fact_locator="prior-self:0", segments=[SimpleNamespace(target_id="maya-id")]
                    )
                ]
            )

        def backlinks(self, _target):
            return SimpleNamespace(items=[SimpleNamespace(source=SimpleNamespace(id="self-id"))])

    monkeypatch.setattr(p4_physical_readback, "NotesQueryService", PriorQuery)
    receipt = p4_physical_readback.assert_reviewed_markdown(
        repository=object(),
        schema={},
        context_index=object(),
        before=before,
        after=before,
        request_id="new-delivery",
        review=review,
        self_roles=(True,),
        self_id="self-id",
    )
    assert receipt["physical_fact_count"] == 1
    assert receipt["new_facts"] == 0 and receipt["reused_facts"] == 1
    assert receipt["changed_canonical_note_count"] == 0


@pytest.mark.parametrize(
    "old_fact",
    [
        "- He conocido a [[Maya|Maya]].\n",  # unmarked prose cannot prove canonical already-known
        "- He escrito a [[Maya|Maya]].\n  <!-- odyssey:fact request=prior-self ordinal=0 -->\n",
    ],
)
def test_unmarked_or_merely_similar_old_fact_must_not_certify_noop(monkeypatch, old_fact):
    before, _after, review, _query = _fixture()
    before["self.md"] = _note("self-id", "Self", "person", old_fact)

    class PriorQuery:
        def __init__(self, *_):
            pass

        def detail(self, _owner):
            return SimpleNamespace(
                body_blocks=[
                    SimpleNamespace(
                        fact_locator="prior-self:0", segments=[SimpleNamespace(target_id="maya-id")]
                    )
                ]
            )

        def backlinks(self, _target):
            return SimpleNamespace(items=[SimpleNamespace(source=SimpleNamespace(id="self-id"))])

    monkeypatch.setattr(p4_physical_readback, "NotesQueryService", PriorQuery)
    with pytest.raises(AssertionError, match="No exact new or pre-existing"):
        p4_physical_readback.assert_reviewed_markdown(
            repository=object(),
            schema={},
            context_index=object(),
            before=before,
            after=before,
            request_id="new-delivery",
            review=review,
            self_roles=(True,),
            self_id="self-id",
        )


def test_exact_prior_dated_self_and_person_backlinks_allow_safe_dedup(monkeypatch):
    # A later Task message may repeat a known Day fact; the fact must NOT be
    # written twice, but identity, SELF and tense must all match exactly.
    old_day = (
        "- Hoy he visto a [[Maya|Maya]] (yo: [[self|Usuario de prueba]]).\n"
        "  <!-- odyssey:fact request=prior-day ordinal=0 -->\n"
    )
    notes = {
        "day.md": _note("date:2026-10-05", "2026-10-05", "calendar_day", old_day),
        "Maya.md": _note("maya-id", "Maya", "person"),
        "self.md": _note("self-id", "Usuario de prueba", "person"),
    }
    review = {
        "facts": [
            {
                "kind": "record",
                "date": "2026-10-05",
                "reference_names": ["Maya"],
                "reviewed_text": "Hoy he visto a {{ref:0}}.",
            }
        ]
    }

    class PriorQuery:
        def __init__(self, *_):
            pass

        def detail(self, _owner):
            return SimpleNamespace(
                body_blocks=[
                    SimpleNamespace(
                        fact_locator="prior-day:0",
                        segments=[
                            SimpleNamespace(target_id="maya-id"),
                            SimpleNamespace(target_id="self-id"),
                        ],
                    )
                ]
            )

        def backlinks(self, _target):
            return SimpleNamespace(
                items=[SimpleNamespace(source=SimpleNamespace(id="date:2026-10-05"))]
            )

    monkeypatch.setattr(p4_physical_readback, "NotesQueryService", PriorQuery)
    proof = p4_physical_readback.assert_reviewed_markdown(
        repository=object(),
        schema={},
        context_index=object(),
        before=notes,
        after=notes,
        request_id="second-request",
        review=review,
        self_roles=(True,),
        self_id="self-id",
    )
    assert (proof["new_facts"], proof["reused_facts"]) == (0, 1)

    # Same physical note cannot prove a third-person claim: SELF link would be fabricated.
    with pytest.raises(AssertionError):
        p4_physical_readback.assert_reviewed_markdown(
            repository=object(),
            schema={},
            context_index=object(),
            before=notes,
            after=notes,
            request_id="third-person-request",
            review=review,
            self_roles=(False,),
            self_id="self-id",
        )
