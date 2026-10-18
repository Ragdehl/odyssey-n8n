"""Measure derived-index work using synthetic Notes and zero neural inference.

No input is read from PROD/DEV. Each run builds disposable canonical Markdown
and indexes under /tmp, then times a one-note incremental UPDATE. Use a
deterministic test embedder to isolate filesystem+SQLite/index-projection cost.
"""

from __future__ import annotations

import json
import resource
import shutil
import tempfile
import time
from pathlib import Path

from odyssey_apps.schema_extensions import compose_application_schema
from odyssey_apps.tasks import TASK_SCHEMA_EXTENSION
from odyssey_core.context import ContextIndex
from odyssey_core.notes import serialize_note
from odyssey_core.schema_types import planning_schema_for_capability
from odyssey_core.semantic import SemanticEntityIndex
from odyssey_core.storage import VaultRepository
from odyssey_core.verified_source_inventory import verified_context_source_inventory
from tests.core.test_context import KeywordEmbedder, note

schema = compose_application_schema(
    json.loads((Path(__file__).resolve().parents[2] / "config/note-schema.json").read_text()),
    (TASK_SCHEMA_EXTENSION,),
)
task_schema = planning_schema_for_capability(schema, "tasks")


class CountingRepository(VaultRepository):
    def __init__(self, root):
        super().__init__(root)
        self.reads = 0
        self.stats = 0
        self.listings = 0

    def read_text(self, path):
        self.reads += 1
        return super().read_text(path)

    def file_version(self, path):
        self.stats += 1
        return super().file_version(path)

    def list_markdown_paths(self):
        self.listings += 1
        return super().list_markdown_paths()

    def reset(self):
        self.reads = self.stats = self.listings = 0


def measure(size):
    with tempfile.TemporaryDirectory(prefix=f"odyssey-scale-{size}-", dir="/tmp") as root:
        root = Path(root)
        (root / "vault" / "people").mkdir(parents=True)
        r = CountingRepository(root / "vault")
        # Synthetic fixture contains no DEV/private texts.
        for i in range(size):
            (root / "vault" / "people" / f"Person-{i:05}.md").write_text(
                serialize_note(
                    note(
                        f"synthetic-{i:05}",
                        "person",
                        f"Name for synthetic person {i}.",
                        name=f"Person {i}",
                    )
                ),
                encoding="utf-8",
            )
        e = KeywordEmbedder()
        c = ContextIndex(root / "context.sqlite3")
        s = SemanticEntityIndex(root / "semantic.sqlite3")
        a = SemanticEntityIndex(root / "semantic-tasks.sqlite3")
        setup = time.perf_counter()
        c.rebuild(r, schema, e)
        s.rebuild(r, schema, e)
        a.rebuild(r, task_schema, e)
        print(
            json.dumps(
                {
                    "size": size,
                    "phase": "initial_build",
                    "seconds": round(time.perf_counter() - setup, 3),
                }
            ),
            flush=True,
        )
        r.replace_text(
            "people/Person-00000.md",
            serialize_note(
                note("synthetic-00000", "person", "Updated synthetic note.", name="Person 0")
            ),
        )
        measurements = []
        r.reset()
        tick = time.perf_counter()
        count = c.refresh_notes(r, schema, e, note_ids=("synthetic-00000",))
        measurements.append(
            {
                "kind": "context",
                "seconds": round(time.perf_counter() - tick, 3),
                "embedded_note_count": count,
                "read_text": r.reads,
                "file_version": r.stats,
                "listings": r.listings,
            }
        )
        r.reset()
        tick = time.perf_counter()
        manifest = verified_context_source_inventory(r, schema, c.path)
        measurements.append(
            {
                "kind": "verified_inventory",
                "seconds": round(time.perf_counter() - tick, 3),
                "embedded_note_count": 0,
                "read_text": r.reads,
                "file_version": r.stats,
                "listings": r.listings,
            }
        )
        for kind, index, sc in [
            ("semantic", s, schema),
            ("semantic-tasks", a, task_schema),
        ]:
            fast = SemanticEntityIndex(root / f"{kind}-fast.sqlite3")
            shutil.copy2(index.path, fast.path)
            for mode, target, extra in (
                ("legacy", index, {}),
                ("shared", fast, {"verified_inventory": manifest}),
            ):
                r.reset()
                tick = time.perf_counter()
                count = target.refresh_notes(r, sc, e, note_ids=("synthetic-00000",), **extra)
                measurements.append(
                    {
                        "kind": kind,
                        "mode": mode,
                        "seconds": round(time.perf_counter() - tick, 3),
                        "embedded_note_count": count,
                        "read_text": r.reads,
                        "file_version": r.stats,
                        "listings": r.listings,
                    }
                )
                # Equivalent source identity and vectors; only SQL storage order may vary.
                import sqlite3

                with (
                    sqlite3.connect(index.path) as legacy_db,
                    sqlite3.connect(fast.path) as fast_db,
                ):
                    if mode == "shared":
                        assert (
                            legacy_db.execute("select * from notes order by id").fetchall()
                            == fast_db.execute("select * from notes order by id").fetchall()
                        )
        print(
            json.dumps(
                {
                    "size": size,
                    "phase": "incremental_one_note",
                    "measurements": measurements,
                    "peak_rss_mb": round(
                        resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1
                    ),
                }
            ),
            flush=True,
        )


for size in (100, 1000, 5000):
    measure(size)
