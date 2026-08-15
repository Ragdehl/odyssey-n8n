"""Parse and serialize Odyssey's constrained Markdown frontmatter format."""

from __future__ import annotations

import json
import math
import re
from typing import Any

from .model import MetadataScalar, Note


_KEY_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")
_NUMBER_PATTERN = re.compile(
    r"^[+-]?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?$"
)
_PROPERTY_PATTERN = re.compile(r"^([A-Za-z_][A-Za-z0-9_-]*):(?:[ \t]*(.*))$")


class NoteFormatError(ValueError):
    """Indicate malformed or unsupported Odyssey Markdown serialization."""


def _serialize_scalar(value: Any) -> str:
    """Serialize one supported frontmatter scalar deterministically.

    Args:
        value: Candidate scalar metadata value.

    Returns:
        Canonical scalar text.

    Raises:
        NoteFormatError: If the value is not a supported finite scalar.
    """
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float) and math.isfinite(value):
        return repr(value)
    raise NoteFormatError("Metadata values must be supported finite scalars")


def serialize_note(note: Note) -> str:
    """Serialize a generic note to canonical Odyssey Markdown.

    Args:
        note: Generic note whose metadata and body should be serialized.

    Returns:
        Canonical frontmatter followed by the unchanged Markdown body.

    Raises:
        NoteFormatError: If the note or its metadata cannot be represented by the format.
    """
    if not isinstance(note, Note):
        raise NoteFormatError("Expected an Odyssey Note")
    if not isinstance(note.metadata, dict):
        raise NoteFormatError("Note metadata must be a mapping")
    if not isinstance(note.content, str):
        raise NoteFormatError("Note content must be text")

    if any(not isinstance(key, str) or not _KEY_PATTERN.fullmatch(key) for key in note.metadata):
        raise NoteFormatError("Metadata key is invalid")

    lines: list[str] = []
    for key in sorted(note.metadata):
        if not _KEY_PATTERN.fullmatch(key):
            raise NoteFormatError("Metadata key is invalid")
        value = note.metadata[key]
        if isinstance(value, list):
            serialized = ", ".join(_serialize_scalar(item) for item in value)
            lines.append(f"{key}: [{serialized}]")
        else:
            lines.append(f"{key}: {_serialize_scalar(value)}")
    return "---\n" + "\n".join(lines) + "\n---\n\n" + note.content


def _split_inline_array(source: str) -> list[str]:
    """Split a flat inline array into scalar tokens without interpreting YAML.

    Args:
        source: Text inside the array brackets.

    Returns:
        Individual serialized scalar tokens.

    Raises:
        NoteFormatError: If quoting, nesting, or item separation is malformed.
    """
    if not source.strip():
        return []
    tokens: list[str] = []
    token: list[str] = []
    quote: str | None = None
    escaped = False
    index = 0
    while index < len(source):
        char = source[index]
        if quote == '"':
            token.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
        elif quote == "'":
            token.append(char)
            if char == "'":
                if index + 1 < len(source) and source[index + 1] == "'":
                    token.append("'")
                    index += 1
                else:
                    quote = None
        elif char in {'"', "'"}:
            quote = char
            token.append(char)
        elif char == ",":
            item = "".join(token).strip()
            if not item:
                raise NoteFormatError("Inline array contains an empty item")
            tokens.append(item)
            token = []
        else:
            if char in "[]{}":
                raise NoteFormatError("Nested metadata structures are unsupported")
            token.append(char)
        index += 1
    if quote is not None:
        raise NoteFormatError("Metadata string has an unclosed quote")
    item = "".join(token).strip()
    if not item:
        raise NoteFormatError("Inline array contains an empty item")
    tokens.append(item)
    return tokens


def _parse_scalar(source: str, *, allow_array: bool = True) -> Any:
    """Parse one scalar or flat inline array from the supported subset.

    Args:
        source: Serialized frontmatter value.
        allow_array: Whether an inline array is valid at this location.

    Returns:
        Parsed scalar or flat array value.

    Raises:
        NoteFormatError: If syntax is malformed, ambiguous, nested, or unsupported.
    """
    value = source.strip()
    if not value:
        raise NoteFormatError("Metadata value is missing")
    if value.startswith("["):
        if not allow_array or not value.endswith("]"):
            raise NoteFormatError("Nested or malformed arrays are unsupported")
        return [
            _parse_scalar(token, allow_array=False)
            for token in _split_inline_array(value[1:-1])
        ]
    if any(character in value for character in "[]{}"):
        raise NoteFormatError("Nested metadata structures are unsupported")
    if value.startswith('"'):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            raise NoteFormatError("Metadata string is malformed") from None
        if not isinstance(parsed, str):
            raise NoteFormatError("Double-quoted metadata must be a string")
        return parsed
    if value.startswith("'"):
        if len(value) < 2 or not value.endswith("'"):
            raise NoteFormatError("Metadata string has an unclosed quote")
        inner = value[1:-1]
        remainder = inner.replace("''", "")
        if "'" in remainder:
            raise NoteFormatError("Single-quoted metadata is malformed")
        return inner.replace("''", "'")
    if value.endswith(('"', "'")):
        raise NoteFormatError("Metadata string is malformed")
    if value.startswith(("!", "&", "*", "|", ">", "`", "@")):
        raise NoteFormatError("Unsupported YAML construct")
    if " #" in value or value.startswith("#"):
        raise NoteFormatError("Frontmatter comments are unsupported")
    if ": " in value or value.endswith(":"):
        raise NoteFormatError("Ambiguous mapping syntax is unsupported")
    if value.lower() in {"true", "false"}:
        return value.lower() == "true"
    if value.lower() in {"null", "~"}:
        return None
    if _NUMBER_PATTERN.fullmatch(value):
        parsed_number = float(value) if any(char in value for char in ".eE") else int(value)
        if isinstance(parsed_number, float) and not math.isfinite(parsed_number):
            raise NoteFormatError("Metadata numbers must be finite")
        return parsed_number
    return value


def _parse_frontmatter(source: str) -> dict[str, Any]:
    """Parse flat frontmatter containing supported scalars and arrays.

    Args:
        source: Frontmatter text without delimiter lines.

    Returns:
        Parsed metadata keyed by frontmatter property ID.

    Raises:
        NoteFormatError: If a property is duplicated, nested, or malformed.
    """
    metadata: dict[str, Any] = {}
    lines = re.split(r"\r?\n", source)
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line:
            index += 1
            continue
        if line[:1].isspace() or line.lstrip().startswith("#"):
            raise NoteFormatError("Unexpected indentation or comment in frontmatter")
        match = _PROPERTY_PATTERN.fullmatch(line)
        if match is None:
            raise NoteFormatError("Frontmatter property is malformed")
        key, serialized = match.groups()
        if key in metadata:
            raise NoteFormatError(f"Duplicate metadata key: {key}")
        if serialized:
            metadata[key] = _parse_scalar(serialized)
            index += 1
            continue

        values: list[MetadataScalar] = []
        index += 1
        while index < len(lines) and lines[index].startswith("  - "):
            item = lines[index][4:]
            values.append(_parse_scalar(item, allow_array=False))
            index += 1
        if not values:
            raise NoteFormatError("Nested or empty mappings are unsupported")
        metadata[key] = values
    return metadata


def parse_note(markdown: str) -> Note:
    """Parse Odyssey Markdown into a generic note without semantic validation.

    Args:
        markdown: Complete Markdown serialization with constrained frontmatter.

    Returns:
        A generic note containing parsed metadata and unchanged body text.

    Raises:
        NoteFormatError: If delimiters or supported frontmatter syntax are malformed.
    """
    if not isinstance(markdown, str):
        raise NoteFormatError("Markdown note must be text")
    opening = re.match(r"\A---(\r\n|\n)", markdown)
    if opening is None:
        raise NoteFormatError("Markdown note is missing opening frontmatter")
    start = opening.end()
    closing = re.search(r"(?:\r\n|\n)---(?:(\r\n|\n)|\Z)", markdown[start:])
    if closing is None:
        raise NoteFormatError("Markdown note is missing closing frontmatter")
    absolute_closing = start + closing.start()
    metadata_source = markdown[start:absolute_closing]
    content = markdown[start + closing.end():]
    closing_newline = closing.group(1)
    if closing_newline and content.startswith(closing_newline):
        content = content[len(closing_newline):]
    return Note(metadata=_parse_frontmatter(metadata_source), content=content)
