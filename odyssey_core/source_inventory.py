"""Physical version/metadata projections of a COMPLETE canonical vault.

Used only as a derived lookup accelerator. A version match is not a proof of
byte equality against a malicious filesystem; positive matches re-ground in
Markdown and canonical mutation gates continue enforcing CAS.
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
from typing import Any

from odyssey_core.notes import Note
from odyssey_core.storage import VaultRepository


def exact_key(value: str) -> str:
    return " ".join(unicodedata.normalize("NFC", value).casefold().split())


def schema_digest(schema: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(schema, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def inventory_row(
    repo: VaultRepository,
    path: str,
    note: Note,
    raw: str,
    *,
    before: tuple[object, ...] | None = None,
) -> tuple[str, str, str, str, str, str, str]:
    version = repo.file_version(path)
    if before is not None and before != version:
        raise ValueError("Canonical source changed during indexing")
    return (
        path,
        note.metadata["id"],
        json.dumps(version, ensure_ascii=False),
        hashlib.sha256(raw.encode("utf-8")).hexdigest(),
        json.dumps(note.metadata, ensure_ascii=False, sort_keys=True),
        note.content.strip()[:320],
        exact_key(note.metadata["name"]),
    )
