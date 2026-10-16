"""Independent P4 acceptance: prove every reviewed assertion exists in Markdown.

A completed HTTP status and Writer action count are not evidence of complete
physical mutation. Inspect actual marked facts, identities and source backlinks
on the disposable vault, without treating the model review as a note authority.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from typing import Any

from odyssey_core.atomic_facts import parse_atomic_facts
from odyssey_core.note_queries import NotesQueryService
from odyssey_core.notes import parse_note


def assert_reviewed_markdown(
    *,
    repository: Any,
    schema: Mapping[str, Any],
    context_index: Any,
    before: Mapping[str, str],
    after: Mapping[str, str],
    request_id: str,
    review: Mapping[str, Any],
    self_roles: tuple[bool, ...],
    self_id: str,
) -> dict[str, Any]:
    """Validate per-fact owner, reference ID, SELF presence, and backlinks.

    Raises AssertionError if an approved claim did not materialize exactly once
    or linked another identity. Never repairs or mutates canonical Markdown.
    """
    reviewed = review["facts"]
    assert len(reviewed) == len(self_roles) and reviewed
    changed = {p: content for p, content in after.items() if before.get(p) != content}
    assert changed, "Completed source had no physical canonical changes"
    parsed = {path: parse_note(text) for path, text in after.items()}
    assert len({note.metadata["id"] for note in parsed.values()}) == len(parsed)
    by_id = {note.metadata["id"]: (path, note) for path, note in parsed.items()}
    people = [note for note in parsed.values() if note.metadata.get("type") == "person"]
    references_by_name: dict[str, str] = {}
    for item in reviewed:
        for name in item["reference_names"]:
            matches = [
                note
                for note in people
                if note.metadata.get("name", "").casefold() == name.casefold()
            ]
            assert len(matches) == 1, "A referenced name is not a unique canonical person"
            references_by_name[name] = str(matches[0].metadata["id"])

    expected_per_delivery = Counter()
    readback = []
    notes_query = NotesQueryService(repository, schema, context_index)
    for position, item in enumerate(reviewed):
        kind, date = item["kind"], item["date"]
        if kind == "record" and date is not None:
            owner_id = "date:" + date
            subrequest = f"{request_id}-day-{date}"
        elif kind == "record":
            owner_id = self_id
            assert self_roles[position], "Undated owner has no authenticated SELF proof"
            subrequest = f"{request_id}-self"
        elif kind == "task":
            subrequest = f"{request_id}-task"
            matches = []
            for note in parsed.values():
                if note.metadata.get("type") == "task" and any(
                    fact.request_id == subrequest for fact in parse_atomic_facts(note.content)
                ):
                    matches.append(note)
            assert len(matches) == 1, "Task request is not a unique canonical Task"
            owner_id = str(matches[0].metadata["id"])
            assert matches[0].metadata["status"] == "pending"
            assert matches[0].metadata["target_date"] == date
        else:
            raise AssertionError("Unknown reviewed operation")

        assert owner_id in by_id, "Reviewed fact owner is physically absent"
        path, note = by_id[owner_id]
        assert path in changed, "Reviewed fact was not newly written"
        expected_per_delivery[(owner_id, subrequest)] += 1
        atoms = [fact for fact in parse_atomic_facts(note.content) if fact.request_id == subrequest]
        ordinal = expected_per_delivery[(owner_id, subrequest)] - 1
        assert len(atoms) >= ordinal + 1, "Missing ordered physical atomic fact"
        fact = atoms[ordinal]
        assert fact.ordinal == ordinal, "Physical fact ordinal differs from review"
        # Markdown links use paths, not stable IDs: resolve them through Core's
        # real Notes projection, rather than pretending the raw path is the ID.
        detail = notes_query.detail(owner_id)
        blocks = [block for block in detail.body_blocks if block.fact_locator == fact.locator]
        assert len(blocks) == 1, "Physical fact is absent from Notes presentation"
        resolved_ids = {
            segment.target_id for segment in blocks[0].segments if segment.target_id is not None
        }
        for name in item["reference_names"]:
            person_id = references_by_name[name]
            assert person_id in resolved_ids, "Reviewed named participant lost its canonical link"
            backlinks = notes_query.backlinks(person_id)
            assert any(entry.source.id == owner_id for entry in backlinks.items), (
                "Physical reference is missing its graph backlink"
            )
        if kind == "record" and date is not None:
            assert (self_id in resolved_ids) == self_roles[position], (
                "SELF participation is missing or invented in physical Day fact"
            )
            if self_roles[position]:
                backlinks = notes_query.backlinks(self_id)
                assert any(entry.source.id == owner_id for entry in backlinks.items)
        readback.append(
            {
                "owner_id": owner_id,
                "source_kind": kind,
                "source_date": date,
                "fact_ordinal": fact.ordinal,
                "named_reference_count": len(item["reference_names"]),
                "verified_self": self_roles[position],
            }
        )

    for (owner_id, subrequest), expected_count in expected_per_delivery.items():
        atoms = [
            fact
            for fact in parse_atomic_facts(by_id[owner_id][1].content)
            if fact.request_id == subrequest
        ]
        assert len(atoms) == expected_count, "Canonical fact count disagrees with source review"
    return {
        "physical_fact_count": len(readback),
        "physical_facts": readback,
        "changed_canonical_note_count": len(changed),
    }
