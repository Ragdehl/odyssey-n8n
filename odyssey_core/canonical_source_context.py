"""Bounded, read-only canonical Note names actually mentioned in a source group.

These hints support ordinary Core planning. They NEVER attest that a source
claim is true, identify an unbound speaker or group member, select write
targets, or bypass Core's existing reference/identity preflight.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .candidate_context import CoreCandidateContext, CoreSourceSpan
from .notes import NoteFormatError, NoteValidationError, parse_note, validate_note
from .storage import VaultRepository

MAX_SCANNED_NOTES = 5000
MAX_HINTS = 16


@dataclass(frozen=True, slots=True)
class CanonicalSourceNameHint:
    mention: str
    name: str
    note_type: str
    content_excerpt: str = ""

    def to_prompt_payload(self) -> dict[str, str]:
        payload = {
            "exact_source_mention": self.mention,
            "existing_note_name": self.name,
            "existing_note_type": self.note_type,
        }
        if self.content_excerpt:
            payload["existing_note_content_excerpt"] = self.content_excerpt
        return payload


SOURCE_NOTE_MENTION_ROLES = frozenset({"subject", "participants", "object", "reference"})


def source_note_role_spans(context: CoreCandidateContext) -> tuple[CoreSourceSpan, ...]:
    """Share exact source-role extraction across Core hints and E2 batch.

    No person detection, English/Spanish endings, phrase splitting, name
    guessing or trusted identity claims: these are *Router-proposed mentions*.
    Only the ordinary Core exact resolver can test whether a named Note exists.
    """
    if not isinstance(context, CoreCandidateContext):
        raise ValueError("Core source candidate context is required")
    context.validate(context.source)
    unique: dict[tuple[int, int], CoreSourceSpan] = {}
    for candidate in context.candidates:
        for role in candidate.roles:
            if role.role not in SOURCE_NOTE_MENTION_ROLES:
                continue
            span = role.span
            text = span.text.strip()
            if not text or len(text) > 128:
                continue
            start = span.start + len(span.text) - len(span.text.lstrip())
            end = start + len(text)
            unique.setdefault((start, end), CoreSourceSpan(text, start, end))
    return tuple(span for _, span in sorted(unique.items()))


def matching_canonical_source_names(
    context: CoreCandidateContext,
    repository: VaultRepository,
    schema: dict,
) -> tuple[CanonicalSourceNameHint, ...]:
    """Return only exact named source-role matches with unambiguous Note metadata."""
    if not isinstance(context, CoreCandidateContext) or not isinstance(repository, VaultRepository):
        raise ValueError("Trusted Core context and root-bound vault required")
    context.validate(context.source)
    mention_by_key: dict[str, str] = {}
    for span in source_note_role_spans(context):
        mention_by_key.setdefault(span.text.casefold(), span.text)
    if not mention_by_key:
        return ()
    paths = repository.list_markdown_paths()
    if len(paths) > MAX_SCANNED_NOTES:
        return ()  # No unbounded vault enumeration in the critical path.
    matched: dict[str, list[tuple[str, str, str]]] = {}
    for path in paths:
        try:
            note = parse_note(repository.read_text(path))
            validate_note(note, schema)
        except (NoteFormatError, NoteValidationError, OSError, ValueError):
            continue
        name = note.metadata.get("name")
        kind = note.metadata.get("type")
        if not isinstance(name, str) or not isinstance(kind, str):
            continue
        key = name.casefold()
        if key in mention_by_key:
            matched.setdefault(key, []).append((name, kind, note.content.strip()[:320]))
    hints = []
    for key, mention in mention_by_key.items():
        values = matched.get(key, [])
        if len(values) == 1:
            name, kind, excerpt = values[0]
            hints.append(CanonicalSourceNameHint(mention, name, kind, excerpt))
        if len(hints) >= MAX_HINTS:
            break
    return tuple(hints)


def matching_canonical_names_in_source(
    source: str,
    repository: VaultRepository,
    schema: dict,
) -> tuple[CanonicalSourceNameHint, ...]:
    """Read-only exact-name hints for specialized consumers with no Router roles.

    A raw whole-word occurrence is evidence that a name appears in the source,
    NOT that it denotes the known Note. The planner must still decide source
    semantics, and Core must independently resolve every proposed link.
    """
    if (
        not isinstance(source, str)
        or not source.strip()
        or len(source) > 4096
        or not isinstance(repository, VaultRepository)
    ):
        raise ValueError("Untrusted source or repository for canonical hints")
    paths = repository.list_markdown_paths()
    if len(paths) > MAX_SCANNED_NOTES:
        raise ValueError("Canonical name hint lookup exceeds current scan budget")
    names: dict[str, list[tuple[str, str, str]]] = {}
    for path in paths:
        try:
            note = parse_note(repository.read_text(path))
            validate_note(note, schema)
        except (NoteFormatError, NoteValidationError, OSError, ValueError):
            continue
        name = note.metadata.get("name")
        kind = note.metadata.get("type")
        if not isinstance(name, str) or not isinstance(kind, str):
            continue
        if not name.strip() or len(name) > 128:
            continue
        if re.search(r"(?<!\w)" + re.escape(name) + r"(?!\w)", source, re.IGNORECASE):
            names.setdefault(name.casefold(), []).append((name, kind, note.content.strip()[:320]))
    result: list[CanonicalSourceNameHint] = []
    for entries in names.values():
        if len(entries) != 1:
            continue
        name, kind, content = entries[0]
        match = re.search(r"(?<!\w)" + re.escape(name) + r"(?!\w)", source, re.IGNORECASE)
        if match is not None:
            result.append(CanonicalSourceNameHint(match.group(), name, kind, content))
        if len(result) >= MAX_HINTS:
            break
    return tuple(result)
