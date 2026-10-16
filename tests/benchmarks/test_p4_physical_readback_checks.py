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
    review = {"facts": [{"kind": "record", "date": None, "reference_names": ["Maya"]}]}

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
