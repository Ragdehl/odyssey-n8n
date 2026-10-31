"""Core read-only safeguard for partial/alias canonical identity mentions.

This is a bounded collision preflight, NOT an identity resolver. It must never
promote a prefix, substring, alias, pronoun or model name to a stable Note ID.
Resolution remains in canonical Core preflight/Writer.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .notes import parse_note, validate_note
from .storage import VaultRepository
from .whole_message_relationship_proof import VerifiedSelfRelationship


class UnprovenIdentityError(ValueError):
    """A source mention cannot safely be promoted to a canonical Note identity."""


def reject_unproven_identity_collisions(
    repository: VaultRepository,
    schema: dict,
    mentions: tuple[str, ...],
    *,
    reference_types: Mapping[str, str | None] | None = None,
    verified_reference_names: frozenset[str] = frozenset(),
    max_notes: int = 5000,
) -> None:
    """Allow only an exact unique canonical match or a genuinely unoccupied name.

    A source alias is not a stable ID. Alias/prefix collision requires proof
    that current Core preflight cannot yet provide in this experimental seam.
    """
    if not isinstance(repository, VaultRepository) or not isinstance(schema, dict):
        raise UnprovenIdentityError("Invalid repository and schema")
    if (
        not isinstance(mentions, tuple)
        or len(mentions) > 32
        or any(not isinstance(m, str) or not m.strip() or len(m) > 128 for m in mentions)
    ):
        raise UnprovenIdentityError("Invalid source entity mention")
    if not mentions:
        return
    paths = repository.list_markdown_paths()
    if len(paths) > max_notes:
        raise UnprovenIdentityError("Canonical entity scan exceeds budget")
    candidates: list[tuple[str, str, set[str]]] = []
    type_hints = reference_types or {}
    for path in paths:
        note = parse_note(repository.read_text(path))
        validate_note(note, schema)
        if note.metadata.get("deleted") is True:
            continue
        aliases = note.metadata.get("aliases", [])
        if not isinstance(aliases, list) or not all(isinstance(a, str) for a in aliases):
            raise UnprovenIdentityError("Invalid canonical aliases")
        candidates.append(
            (
                str(note.metadata["name"]),
                str(note.metadata["type"]),
                {a.casefold() for a in aliases},
            )
        )
    for raw in mentions:
        mention = raw.strip().casefold()
        exact_any_type = [
            (canonical, note_type)
            for canonical, note_type, _aliases in candidates
            if canonical.casefold() == mention
        ]
        # Only a current Core-proven identity may narrow a genuinely
        # ambiguous existing name by Note type. An LLM type proposal is a
        # search hint, not proof of which homonym the user intended.
        if raw not in verified_reference_names:
            if len(exact_any_type) > 1:
                raise UnprovenIdentityError("AMBIGUOUS_CANONICAL_ENTITY: " + raw)
            if (
                exact_any_type
                and type_hints.get(raw) is not None
                and exact_any_type[0][1] != type_hints[raw]
            ):
                raise UnprovenIdentityError("UNSUPPORTED_CANONICAL_TYPE_CHOICE: " + raw)
        matches = []
        exacts = []
        for canonical, note_type, aliases in candidates:
            if type_hints.get(raw) is not None and note_type != type_hints[raw]:
                continue
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
            raise UnprovenIdentityError("UNPROVEN_PARTIAL_CANONICAL_IDENTITY: " + raw)
        if len(exacts) > 1 or (len(exacts) == 1 and len(matches) != 1):
            raise UnprovenIdentityError("AMBIGUOUS_CANONICAL_ENTITY: " + raw)


def collect_schema_reference_types(
    proposal: Mapping[str, Any],
    verified_relationships: Sequence[VerifiedSelfRelationship],
    schema: Mapping[str, Any],
    *,
    used_reference_names: frozenset[str] | None = None,
) -> dict[str, str]:
    """Bound source/relationship type hints without claiming canonical IDs.

    Note types come only from the active schema. Model proposals are untrusted
    selection hints; verified canonical membership takes precedence when a
    model's guess differs. None of these hints may authorize a write.
    """
    types = schema.get("types")
    if not isinstance(types, list):
        raise UnprovenIdentityError("Invalid canonical Note schema")
    allowed = {item.get("id") for item in types if isinstance(item, Mapping)}
    if not allowed or any(not isinstance(t, str) or not t for t in allowed):
        raise UnprovenIdentityError("Invalid canonical Note type registry")
    proposed = proposal.get("entities", [])
    if not isinstance(proposed, list):
        raise UnprovenIdentityError("Invalid model identity candidates")
    choices: dict[str, str] = {}
    for entity in proposed:
        # A model may propose an unused candidate while the complete-source
        # review safely keeps the text literal. It has no identity authority
        # and must not turn an otherwise valid diary write into refusal.
        if used_reference_names is not None and (
            not isinstance(entity, Mapping) or entity.get("mention") not in used_reference_names
        ):
            continue
        if not isinstance(entity, Mapping):
            raise UnprovenIdentityError("Invalid model identity candidate")
        mention, note_type = entity.get("mention"), entity.get("note_type")
        if (
            not isinstance(mention, str)
            or not mention.strip()
            or not isinstance(note_type, str)
            or note_type not in allowed
        ):
            raise UnprovenIdentityError("Unknown or incomplete candidate Note type")
        if mention in choices and choices[mention] != note_type:
            raise UnprovenIdentityError("Conflicting candidate Note types")
        choices[mention] = note_type
    verified: dict[str, str] = {}
    for proof in verified_relationships:
        by_id = dict(proof.member_types)
        for note_id, name in proof.members:
            note_type = by_id.get(note_id)
            if note_type not in allowed:
                raise UnprovenIdentityError("Unrecognized verified Note type")
            if name in verified and verified[name] != note_type:
                raise UnprovenIdentityError("Ambiguous verified Note type")
            verified[name] = note_type
    choices.update(verified)
    return choices


# Compatibility names for older P4 imports/tests. One implementation only;
# the authority and candidate universe now include every canonical Note type.
UnprovenPersonIdentityError = UnprovenIdentityError
reject_unproven_person_collisions = reject_unproven_identity_collisions
