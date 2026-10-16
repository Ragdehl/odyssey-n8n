"""Physical P4 acceptance: prove each reviewed meaning is newly saved OR already exact.

Completed status alone is never proof: all source assertions must have an exact
canonical marker in the correct owner with grounded resolved links. A previously
identical marked fact can justify a no-op; unmarked plain text or merely similar
meaning cannot. Only read disposable-vault Markdown; never repair it here.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Mapping
from typing import Any

from odyssey_core.atomic_facts import AtomicFact, parse_atomic_facts
from odyssey_core.note_queries import NotesQueryService
from odyssey_core.notes import parse_note

_INLINE_LINK = re.compile(r"\[\[(?:[^|\]\n]+\|)?([^\]\n]+)\]\]")


def _exact_text(fact: AtomicFact, reviewed: Mapping[str, Any], speaker: bool) -> bool:
    """Compare literal reviewed fact text against canonical visible link labels.

    The source-attested SELF annotation is an explicit Core rendering suffix
    on a dated Day fact; remove only this known suffix when verifying its
    separate authenticated source role. Never use fuzzy semantic matching.
    """
    expected = reviewed["reviewed_text"]
    if not isinstance(expected, str) or not expected.strip():
        return False
    for index, name in enumerate(reviewed["reference_names"]):
        expected = expected.replace("{{ref:" + str(index) + "}}", name)
    visible = _INLINE_LINK.sub(lambda match: match.group(1), fact.text)
    if speaker and reviewed["kind"] == "record" and reviewed["date"] is not None:
        visible = re.sub(r" \(yo: [^\n)]+\)(?=\.$)", "", visible)
    return visible.strip() == expected.strip()


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
    """Prove each assertion's exact owner/text/links and new-or-existing receipt.

    Existing matches must come from the BEFORE snapshot and must have a
    canonical atomic marker: a response cannot claim success by echoing its
    text or by finding an unrelated similar statement. Duplicate current
    markers, absent references and invented SELF links always fail.
    """
    reviewed = review["facts"]
    assert len(reviewed) == len(self_roles) and reviewed
    changed = {p: content for p, content in after.items() if before.get(p) != content}
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

    used: set[tuple[str, str, int]] = set()
    expected_new = Counter()
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
            matches = [
                note
                for note in parsed.values()
                if note.metadata.get("type") == "task"
                and any(fact.request_id == subrequest for fact in parse_atomic_facts(note.content))
            ]
            assert len(matches) == 1, "Task request is not one unique canonical Task"
            owner_id = str(matches[0].metadata["id"])
            assert matches[0].metadata["status"] == "pending"
            assert matches[0].metadata["target_date"] == date
        else:
            raise AssertionError("Unknown reviewed operation")
        assert owner_id in by_id, "Reviewed fact owner is physically absent"
        path, note = by_id[owner_id]
        now_atoms = parse_atomic_facts(note.content)
        previous = before.get(path)
        before_atoms = (
            parse_atomic_facts(parse_note(previous).content) if previous is not None else ()
        )
        if previous is not None:
            assert parse_note(previous).metadata["id"] == owner_id
        # Prefer this delivery's physical write; an exact pre-existing
        # canonical match is the ONLY supported no-op proof.
        eligible = [("new", fact) for fact in now_atoms if fact.request_id == subrequest] + [
            ("existing", fact) for fact in before_atoms
        ]
        chosen = None
        detail = notes_query.detail(owner_id)
        for origin, fact in eligible:
            key = (owner_id, fact.request_id, fact.ordinal)
            if key in used or not _exact_text(fact, item, self_roles[position]):
                continue
            blocks = [b for b in detail.body_blocks if b.fact_locator == fact.locator]
            if len(blocks) != 1:
                continue
            resolved_ids = {
                segment.target_id for segment in blocks[0].segments if segment.target_id is not None
            }
            expected_names = {references_by_name[n] for n in item["reference_names"]}
            if not expected_names.issubset(resolved_ids):
                continue
            if (
                kind == "record"
                and date is not None
                and ((self_id in resolved_ids) != self_roles[position])
            ):
                continue
            chosen = (origin, fact, resolved_ids)
            used.add(key)
            break
        assert chosen is not None, "No exact new or pre-existing canonical fact proves source"
        origin, fact, _resolved = chosen
        if origin == "new":
            assert path in changed, "New fact did not mutate its canonical owner"
            expected_new[(owner_id, subrequest)] += 1
        for name in item["reference_names"]:
            person_id = references_by_name[name]
            backlinks = notes_query.backlinks(person_id)
            assert any(entry.source.id == owner_id for entry in backlinks.items), (
                "Physical reference lacks a graph backlink"
            )
        if kind == "record" and date is not None and self_roles[position]:
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
                "evidence": origin,
            }
        )

    for owner_id, subrequest in {
        (row["owner_id"], f"{request_id}-day-{row['source_date']}")
        if row["source_kind"] == "record" and row["source_date"] is not None
        else (row["owner_id"], f"{request_id}-self")
        if row["source_kind"] == "record"
        else (row["owner_id"], f"{request_id}-task")
        for row in readback
    }:
        new_atoms = [
            fact
            for fact in parse_atomic_facts(by_id[owner_id][1].content)
            if fact.request_id == subrequest
        ]
        assert len(new_atoms) == expected_new[(owner_id, subrequest)], (
            "Unreviewed or duplicate new physical fact is present"
        )
        assert [f.ordinal for f in new_atoms] == list(range(len(new_atoms))), (
            "New physical fact ordinals are not canonical"
        )
    return {
        "physical_fact_count": len(readback),
        "new_facts": sum(row["evidence"] == "new" for row in readback),
        "reused_facts": sum(row["evidence"] == "existing" for row in readback),
        "physical_facts": readback,
        "changed_canonical_note_count": len(changed),
    }
