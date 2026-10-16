"""E3 readback must detect unreviewed EXTRA Task writes by exact subrequest ID."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import odyssey_core.whole_source_readback as readback
from odyssey_core.notes import Note, serialize_note


def note(note_id, name, note_type, content="", **extra):
    return serialize_note(Note({"id": note_id, "name": name, "type": note_type, **extra}, content))


class FakeQuery:
    def __init__(self, *args):
        pass

    def detail(self, note_id):
        assert note_id == "task-p4"
        return SimpleNamespace(
            body_blocks=[
                SimpleNamespace(fact_locator="req-task-0:0", segments=[]),
                SimpleNamespace(fact_locator="req-task-0:1", segments=[]),
            ]
        )

    def backlinks(self, *_):
        return SimpleNamespace(items=[])


@pytest.mark.parametrize("extra", [False, True])
def test_exact_task_subrequest_readback_rejects_extra_atomic_writes(monkeypatch, extra):
    monkeypatch.setattr(readback, "NotesQueryService", FakeQuery)
    original = note("self-id", "Yo", "person", "")
    before = {"self.md": original}
    body = "- Llamar al proveedor.\n  <!-- odyssey:fact request=req-task-0 ordinal=0 -->\n"
    if extra:
        body += (
            "- Otro hecho no solicitado.\n  <!-- odyssey:fact request=req-task-0 ordinal=1 -->\n"
        )
    after = {
        **before,
        "task.md": note(
            "task-p4",
            "Llamar al proveedor",
            "task",
            body,
            status="pending",
            target_date="2026-10-17",
        ),
    }
    review = {
        "facts": [
            {
                "kind": "task",
                "date": "2026-10-17",
                "reference_names": [],
                "reviewed_text": "Llamar al proveedor.",
            }
        ]
    }
    kwargs = dict(
        repository=object(),
        schema={},
        context_index=object(),
        before=before,
        after=after,
        request_id="req",
        review=review,
        self_roles=(False,),
        self_id="self-id",
    )
    if extra:
        with pytest.raises(AssertionError, match="Unreviewed or duplicate"):
            readback.assert_reviewed_markdown(**kwargs)
    else:
        result = readback.assert_reviewed_markdown(**kwargs)
        assert result["physical_fact_count"] == 1
        assert result["new_facts"] == 1
