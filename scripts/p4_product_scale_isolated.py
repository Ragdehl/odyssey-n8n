"""Disposable P4 product source-readback scaling benchmark, provider-free.

Measures Core+index+full-source guard, with identical fake-model outputs at
varying note counts. It does not measure actual embedding-model compute, true
n8n latency, browser paint or model inference.
"""

from __future__ import annotations

import json
import resource
import tempfile
import time
from pathlib import Path

from odyssey_core import create_entity
from tests.runtime.test_whole_source_light_product_p4 import (
    SCHEMA,
    RecordedClient,
    _actual_snapshot,
    _fixture,
    _speaker,
)


def main():
    source, route, plan, review = _actual_snapshot("maya_simple")
    rows = []
    for note_count in (20, 250, 1000):
        with tempfile.TemporaryDirectory(prefix="odyssey-p4-scale-") as path:
            repo, actor, service, runtime = _fixture(Path(path), incremental_indexes=True)
            before_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            setup = time.monotonic()
            (Path(path) / "vault" / "notes").mkdir()
            for i in range(note_count):
                create_entity(
                    repo,
                    SCHEMA,
                    path=f"notes/filler-{i:04d}.md",
                    entity_id=f"synthetic-filler-{i:04d}",
                    metadata={"name": f"TemaSintetico{i:04d}", "type": "concept"},
                    content="- Contenido irrelevante.\n",
                    actor="scale-fixture",
                    now="2026-10-16T08:00:00+02:00",
                )
            service.context_index.rebuild(repo, SCHEMA, service.embedder)
            service.semantic_index.rebuild(repo, SCHEMA, service.embedder)
            setup_s = time.monotonic() - setup
            service.client = RecordedClient(
                [route, plan, review, _speaker(source, plan, base=1), _speaker(source, plan)]
            )
            start = time.monotonic()
            result = runtime.execute_product(source, f"perf-{note_count}", "main", actor)
            wall = round((time.monotonic() - start) * 1000, 1)
            row = {
                "initial_extra_notes": note_count,
                "setup_seconds": round(setup_s, 2),
                "execution_ms_no_llm": wall,
                "index_refresh_modes": dict(service.refresh_stats),
                "status": result.get("status"),
                "peak_rss_growth_kb_upper_bound": max(
                    0, resource.getrusage(resource.RUSAGE_SELF).ru_maxrss - before_rss
                ),
                "canonical_note_count": len(repo.list_markdown_paths()),
            }
            rows.append(row)
            print(json.dumps(row), flush=True)
    Path("/tmp/odyssey-p4-product-scale.json").write_text(json.dumps(rows, indent=2) + "\n")
    return 0 if all(r["status"] == "completed" for r in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
