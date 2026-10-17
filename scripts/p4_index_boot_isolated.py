"""Compare derived index build vs verified P4 restart on disposable Notes."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from time import perf_counter

from odyssey_core.context import ContextIndex
from odyssey_core.semantic import SemanticEntityIndex
from odyssey_core.storage import VaultRepository
from odyssey_runtime.index_startup import p4_indexes_reusable
from tests.core.test_context import KeywordEmbedder, note
from tests.core.test_context_deterministic_projection import write


def main():
    with tempfile.TemporaryDirectory(prefix="odyssey-index-boot-") as tmp:
        root = Path(tmp)
        (root / "vault").mkdir()
        repo = VaultRepository(root / "vault")
        schema = json.loads(
            (Path(__file__).resolve().parents[1] / "config/note-schema.json").read_text()
        )
        for idx in range(250):
            write(
                repo,
                f"person-{idx:04d}.md",
                note(f"person-{idx:04d}", "person", "Synthetic.", name=f"Person {idx:04d}"),
            )
        embedder = KeywordEmbedder()
        context = ContextIndex(root / "context.sqlite3")
        semantic = SemanticEntityIndex(root / "semantic.sqlite3")
        t = perf_counter()
        context.rebuild(repo, schema, embedder)
        semantic.rebuild(repo, schema, embedder)
        construction = (perf_counter() - t) * 1000
        t = perf_counter()
        reused = p4_indexes_reusable(repo, schema, embedder, context, semantic, {})
        reuse = (perf_counter() - t) * 1000
        assert reused
        write(repo, "person-0001.md", note("person-0001", "person", "Updated.", name="Person 0001"))
        t = perf_counter()
        stale = p4_indexes_reusable(repo, schema, embedder, context, semantic, {})
        stale_ms = (perf_counter() - t) * 1000
        assert not stale
        print(
            json.dumps(
                {
                    "synthetic_notes": 250,
                    "initial_build_ms": round(construction, 2),
                    "verified_restart_ms": round(reuse, 2),
                    "stale_check_ms": round(stale_ms, 2),
                    "unchanged_reuse": reused,
                    "modified_reuse": stale,
                },
                ensure_ascii=False,
            )
        )


if __name__ == "__main__":
    main()
