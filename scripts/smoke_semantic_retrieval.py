"""Smoke-test production semantic model load, indexing, and query execution."""

from __future__ import annotations

import json
import platform
import tempfile
import time
from pathlib import Path

from odyssey_core.notes import Note, serialize_note
from odyssey_core.semantic import FastEmbedTextEmbedder, SemanticEntityIndex
from odyssey_core.storage import VaultRepository

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _note(note_id: str, note_type: str, content: str) -> Note:
    """Create one schema-valid synthetic note for an isolated smoke run.

    Args:
        note_id: Stable fixture identity.
        note_type: Canonical fixture note type.
        content: Semantic Markdown body.

    Returns:
        Valid note value containing required canonical metadata.
    """
    return Note(
        metadata={
            "id": note_id,
            "type": note_type,
            "created_at": "2026-08-16T12:00:00Z",
            "updated_at": "2026-08-16T12:00:00Z",
            "created_by": "phase-10-smoke",
            "updated_by": "phase-10-smoke",
            "revision": 1,
            "schema_version": 1,
        },
        content=content,
    )


def main() -> None:
    """Run the production adapter and derived index against a temporary synthetic vault."""
    schema = json.loads((REPOSITORY_ROOT / "config/note-schema.json").read_text(encoding="utf-8"))
    started = time.perf_counter()
    embedder = FastEmbedTextEmbedder()
    model_load_seconds = time.perf_counter() - started
    with tempfile.TemporaryDirectory(prefix="odyssey-phase10-smoke-") as directory:
        root = Path(directory)
        vault = root / "vault"
        (vault / "people").mkdir(parents=True)
        (vault / "people" / "Beatriz.md").write_text(
            serialize_note(_note("beatriz", "person", "My wife and mother of my children.")),
            encoding="utf-8",
        )
        (vault / "people" / "Xavi.md").write_text(
            serialize_note(_note("xavi", "person", "Friend of the user.")),
            encoding="utf-8",
        )
        index = SemanticEntityIndex(root / "derived" / "semantic.sqlite3")
        started = time.perf_counter()
        indexed = index.rebuild(VaultRepository(vault), schema, embedder)
        candidates = index.find_candidates(embedder, "ma femme", type="person", limit=2)
        execution_seconds = time.perf_counter() - started
    result = {
        "architecture": platform.machine(),
        "python": platform.python_version(),
        "model": embedder.model_name,
        "model_version": embedder.model_version,
        "model_load_seconds": model_load_seconds,
        "index_and_query_seconds": execution_seconds,
        "indexed_notes": indexed,
        "candidate_ids": [candidate.id for candidate in candidates],
        "pass": bool(candidates) and candidates[0].id == "beatriz",
    }
    print(json.dumps(result, indent=2))
    if not result["pass"]:
        raise SystemExit("Semantic retrieval smoke validation failed")


if __name__ == "__main__":
    main()
