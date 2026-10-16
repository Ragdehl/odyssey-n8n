"""Core read-only safeguard for partial/alias Person source mentions.

This is a bounded collision preflight, NOT an identity resolver. It must never
promote a prefix, substring, alias, pronoun or model name to a stable Note ID.
Resolution remains in canonical Core preflight/Writer.
"""

from __future__ import annotations

from .notes import parse_note, validate_note
from .storage import VaultRepository


class UnprovenPersonIdentityError(ValueError):
    """Person mention cannot be safely promoted to a new canonical identity."""


def reject_unproven_person_collisions(
    repository: VaultRepository,
    schema: dict,
    mentions: tuple[str, ...],
    *,
    max_notes: int = 5000,
) -> None:
    """Allow only an exact unique canonical match or a genuinely unoccupied name.

    A source alias is not a stable ID. Alias/prefix collision requires proof
    that current Core preflight cannot yet provide in this experimental seam.
    """
    if not isinstance(repository, VaultRepository) or not isinstance(schema, dict):
        raise UnprovenPersonIdentityError("Invalid repository and schema")
    if (
        not isinstance(mentions, tuple)
        or len(mentions) > 32
        or any(not isinstance(m, str) or not m.strip() or len(m) > 128 for m in mentions)
    ):
        raise UnprovenPersonIdentityError("Invalid source person mention")
    if not mentions:
        return
    paths = repository.list_markdown_paths()
    if len(paths) > max_notes:
        raise UnprovenPersonIdentityError("Canonical person scan exceeds budget")
    people: list[tuple[str, set[str]]] = []
    for path in paths:
        note = parse_note(repository.read_text(path))
        validate_note(note, schema)
        if note.metadata.get("type") != "person" or note.metadata.get("deleted") is True:
            continue
        aliases = note.metadata.get("aliases", [])
        if not isinstance(aliases, list) or not all(isinstance(a, str) for a in aliases):
            raise UnprovenPersonIdentityError("Invalid person aliases")
        people.append((str(note.metadata["name"]), {a.casefold() for a in aliases}))
    for raw in mentions:
        mention = raw.strip().casefold()
        matches = []
        exacts = []
        for canonical, aliases in people:
            name = canonical.casefold()
            if mention == name:
                exacts.append(canonical)
                matches.append(canonical)
            elif (
                mention in aliases
                or name.startswith(mention + " ")
                or mention.startswith(name + " ")
            ):
                matches.append(canonical)
        if len(exacts) != 1 and matches:
            raise UnprovenPersonIdentityError("UNPROVEN_PARTIAL_CANONICAL_IDENTITY: " + raw)
        if len(exacts) > 1 or (len(exacts) == 1 and len(matches) != 1):
            raise UnprovenPersonIdentityError("AMBIGUOUS_CANONICAL_PERSON: " + raw)
