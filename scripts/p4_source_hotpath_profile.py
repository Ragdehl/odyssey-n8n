"""Profile the actual P4 Core read/write path, not provider latency.

Runs only synthetic Markdown in a fresh TemporaryDirectory. Report cumulative
call counts and cProfile hot spots; no application or provider state touched.
"""

from __future__ import annotations

import cProfile
import io
import json
import os
import pstats
import tempfile
import time
from collections import Counter
from pathlib import Path

from odyssey_core import create_entity
from tests.runtime.test_whole_source_light_product_p4 import (
    SCHEMA,
    RecordedClient,
    _actual_snapshot,
    _fixture,
    _speaker,
)


def main() -> int:
    source, route, plan, review = _actual_snapshot("maya_simple")
    with tempfile.TemporaryDirectory(prefix="odyssey-p4-hotpath-") as tmp:
        repo, actor, service, runtime = _fixture(Path(tmp), incremental_indexes=True)
        (Path(tmp) / "vault" / "notes").mkdir()
        for index in range(250):
            create_entity(
                repo,
                SCHEMA,
                path=f"notes/filler-{index:04d}.md",
                entity_id=f"synthetic-{index:04d}",
                metadata={"name": f"TemaSintetico{index:04d}", "type": "concept"},
                content="- Nota sin relación.\n",
                actor="profile-fixture",
                now="2026-10-16T08:00:00+02:00",
            )
        service.context_index.rebuild(repo, SCHEMA, service.embedder)
        service.semantic_index.rebuild(repo, SCHEMA, service.embedder)
        service.client = RecordedClient(
            [route, plan, review, _speaker(source, plan, base=1), _speaker(source, plan)]
        )
        original_read, original_list = repo.read_text, repo.list_markdown_paths
        calls = Counter()
        seconds = Counter()

        def instrument(name, operation):
            def wrapped(*args, **kwargs):
                start = time.perf_counter()
                try:
                    return operation(*args, **kwargs)
                finally:
                    calls[name] += 1
                    seconds[name] += time.perf_counter() - start

            return wrapped

        read_cache: dict[str, tuple[tuple[int, ...], str]] = {}
        cache_active = os.environ.get("ODYSSEY_P4_PROFILE_READ_CACHE") == "1"

        def version(path: str) -> tuple[int, ...]:
            # Experimental cache checks live metadata on every reuse;
            # production safety requires more adversarial coverage.
            real = (repo.root / path).resolve(strict=True)
            if not real.is_relative_to(repo.root) or not real.is_file():
                raise ValueError("Unavailable Note")
            meta = real.stat()
            return (meta.st_dev, meta.st_ino, meta.st_size, meta.st_mtime_ns, meta.st_ctime_ns)

        def maybe_cached_read(path: str) -> str:
            if not cache_active:
                return original_read(path)
            before = version(path)
            previous = read_cache.get(path)
            if previous is not None and previous[0] == before:
                calls["cache_hits"] += 1
                return previous[1]
            value = original_read(path)
            after = version(path)
            if before == after:
                read_cache[path] = (after, value)
            else:
                read_cache.pop(path, None)
            return value

        repo.read_text = instrument("markdown_reads", maybe_cached_read)
        list_cache: list[str] | None = None
        dir_fingerprints: tuple[tuple[str, tuple[int, ...]], ...] = ()
        list_cache_enabled = os.environ.get("ODYSSEY_P4_PROFILE_PATH_CACHE") == "1"

        def directory_fingerprints() -> tuple[tuple[str, tuple[int, ...]], ...]:
            result = []
            for directory, _subdirs, _filenames in os.walk(repo.root, followlinks=False):
                meta = os.stat(directory, follow_symlinks=False)
                result.append(
                    (directory, (meta.st_dev, meta.st_ino, meta.st_mtime_ns, meta.st_ctime_ns))
                )
            return tuple(sorted(result))

        def maybe_cached_list() -> list[str]:
            nonlocal list_cache, dir_fingerprints
            if not list_cache_enabled:
                return original_list()
            before = directory_fingerprints()
            if list_cache is not None and before == dir_fingerprints:
                calls["path_cache_hits"] += 1
                return list(list_cache)
            fresh = original_list()
            after = directory_fingerprints()
            if before == after:
                list_cache, dir_fingerprints = list(fresh), after
            else:
                list_cache, dir_fingerprints = None, ()
            return fresh

        repo.list_markdown_paths = instrument("full_path_enumerations", maybe_cached_list)
        profile = cProfile.Profile()
        profile.enable()
        start = time.perf_counter()
        result = runtime.execute_product(source, "p4-profile-250", "main", actor)
        elapsed = time.perf_counter() - start
        profile.disable()
        report = io.StringIO()
        pstats.Stats(profile, stream=report).sort_stats("cumulative").print_stats(40)
        payload = {
            "status": result.get("status"),
            "synthetic_notes": 250,
            "elapsed_ms": round(elapsed * 1000, 2),
            "repository_calls": dict(calls),
            "read_cache_enabled": cache_active,
            "path_cache_enabled": list_cache_enabled,
            "repository_time_ms": {key: round(seconds[key] * 1000, 2) for key in calls},
            "cprofile_top": report.getvalue(),
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0 if result.get("status") == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
