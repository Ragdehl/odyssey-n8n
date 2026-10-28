"""Compare index-only batching against per-note ContextIndex refresh on disposable Git vaults.

The same Core/E3 writer preserves one local Git commit per Note. The worker
coalesces only derived ContextIndex refresh IDs, then the reader barrier forces
a complete refresh before a filtered query. No real provider or personal vault.

    python benchmarks/indexing/probe_schema_backfill_batches.py --scales 250:12,1000:12
"""

from __future__ import annotations

import argparse
import json
import resource
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests" / "runtime"))

from test_schema_backfill_jobs import ACTOR, NOW, setup  # noqa: E402

from benchmarks.indexing.probe_schema_backfill_scale import (  # noqa: E402
    DeterministicEmbedder,
    host_memory_mib,
    parse_scales,
)
from odyssey_apps.events import EVENT_SCHEMA_EXTENSION  # noqa: E402
from odyssey_apps.schema_extensions import compose_application_schema  # noqa: E402
from odyssey_apps.tasks import TASK_SCHEMA_EXTENSION  # noqa: E402
from odyssey_core.context import ContextFilter, ContextIndex  # noqa: E402
from odyssey_core.git_history import GitHistoryRecorder  # noqa: E402
from odyssey_core.note_queries import NotesQueryService  # noqa: E402
from odyssey_core.notes import Note, parse_note, serialize_note, validate_note  # noqa: E402
from odyssey_core.schema_auto_backfill import AutomaticPropertyBackfill  # noqa: E402
from odyssey_core.schema_types import planning_schema_for_capability  # noqa: E402
from odyssey_core.semantic import FastEmbedTextEmbedder, SemanticEntityIndex  # noqa: E402
from odyssey_core.verified_source_inventory import verified_context_source_inventory  # noqa: E402
from odyssey_runtime.composition import DerivedIndexRefreshCoordinator  # noqa: E402
from odyssey_runtime.schema_backfill_jobs import LocalBackfillJob  # noqa: E402


def run_sample(
    root: Path,
    size: int,
    sample: int,
    *,
    with_semantic: bool = False,
    with_app_indexes: bool = False,
    offline_model_cache: Path | None = None,
) -> dict[str, object]:
    """Measure isolated index coalescing without changing Core/Git/journal semantics."""
    fixture = root / f"notes-{size}"
    fixture.mkdir()
    if with_app_indexes:
        with_semantic = True
    # The schema scan has an intentionally bounded 10k identity manifest.
    # Count App fixtures INSIDE total vault capacity rather than silently
    # slipping two extra Markdown IDs past the model's safety budget.
    people_count = size - 2 if with_app_indexes else size
    if people_count < sample or people_count <= 0:
        raise ValueError("Scale has fewer eligible People than requested writes")
    state, repo, writer = setup(fixture, ["Profesión: médica"] * people_count)
    if with_app_indexes:
        schema = compose_application_schema(
            writer.schema, (TASK_SCHEMA_EXTENSION, EVENT_SCHEMA_EXTENSION)
        )
        sample_note = parse_note(repo.read_text("0.md"))
        for note_id, note_type, field, value in (
            ("fixture-task", "task", "status", "pending"),
            ("fixture-event", "event", "event_status", "scheduled"),
        ):
            metadata = {
                **sample_note.metadata,
                "id": note_id,
                "name": f"Synthetic {note_type}",
                "type": note_type,
                field: value,
            }
            if note_type == "event":
                metadata["start_date"] = "2026-10-27"
            content = serialize_note(Note(metadata, f"Isolated {note_type} fixture."))
            validate_note(parse_note(content), schema)
            repo.create_text(f"fixture-{note_type}.md", content)
        subprocess.run(
            ["git", "add", "fixture-task.md", "fixture-event.md"],
            cwd=repo.root,
            capture_output=True,
            text=True,
            check=True,
        )
        subprocess.run(
            [
                "git",
                "-c",
                "user.name=Test",
                "-c",
                "user.email=test@localhost",
                "commit",
                "-qm",
                "synthetic-app-notes",
            ],
            cwd=repo.root,
            capture_output=True,
            text=True,
            check=True,
        )
        writer = AutomaticPropertyBackfill(
            repository=repo, schema=schema, history=GitHistoryRecorder(repo.root)
        )
    index = ContextIndex(fixture / "derived" / "context.sqlite3")
    embedder = (
        FastEmbedTextEmbedder(
            cache_dir=offline_model_cache,
            local_files_only=True,
        )
        if offline_model_cache is not None
        else DeterministicEmbedder()
    )
    assert index.rebuild(repo, writer.schema, embedder) == size
    semantic = SemanticEntityIndex(fixture / "derived" / "semantic.sqlite3")
    if with_semantic:
        semantic.rebuild(repo, writer.schema, embedder)
    app_indexes = {}
    if with_app_indexes:
        for capability in ("tasks", "events"):
            app = SemanticEntityIndex(fixture / "derived" / f"semantic-{capability}.sqlite3")
            app_schema = planning_schema_for_capability(writer.schema, capability)
            app.rebuild(repo, app_schema, embedder)
            app_indexes[capability] = (app, app_schema)
    refresh_batches: list[tuple[str, ...]] = []
    refresh_times: list[float] = []

    def refresh(ids: tuple[str, ...]) -> None:
        started = time.perf_counter()
        index.refresh_notes(repo, writer.schema, embedder, note_ids=ids)
        if with_semantic:
            verified = verified_context_source_inventory(repo, writer.schema, index.path)
            semantic.refresh_notes(
                repo, writer.schema, embedder, note_ids=ids, verified_inventory=verified
            )
            for app_index, app_schema in app_indexes.values():
                app_index.refresh_notes(
                    repo, app_schema, embedder, note_ids=ids, verified_inventory=verified
                )
        refresh_times.append(time.perf_counter() - started)
        refresh_batches.append(tuple(ids))

    coordinator = DerivedIndexRefreshCoordinator(refresh)
    job = LocalBackfillJob(
        state_root=state,
        repository=repo,
        writer=writer,
        actor_id="synthetic",
        on_updated=lambda note_id: coordinator.schedule_backfill((note_id,)),
    )
    summary = job.stage(job_id="perf", type_id="person", property_id="profesion")
    assert summary["pending"] == people_count

    started = time.perf_counter()
    cpu_before = time.process_time()
    writes = []
    for _ in range(sample):
        before = time.perf_counter()
        summary = job.advance(
            job_id="perf",
            type_id="person",
            property_id="profesion",
            actor=ACTOR,
            now=NOW,
        )
        writes.append(time.perf_counter() - before)
    writer_elapsed = time.perf_counter() - started
    assert summary["updated"] == sample
    barrier_started = time.perf_counter()
    coordinator.wait_until_clean()
    wait_elapsed = time.perf_counter() - barrier_started
    elapsed = time.perf_counter() - started
    cpu_used = time.process_time() - cpu_before

    page = NotesQueryService(repo, writer.schema, index).query(
        filters=[ContextFilter("profesion", "eq", "médica")], page_size=30
    )
    assert page.total == sample
    assert sum(len(batch) for batch in refresh_batches) >= sample
    if with_semantic:
        import hashlib
        import sqlite3

        with sqlite3.connect(semantic.path) as connection:
            hashes = dict(connection.execute("SELECT id,source_hash FROM notes"))
        assert all(
            hashes[f"persona-{i}"] == hashlib.sha256(repo.read_text(f"{i}.md").encode()).hexdigest()
            for i in range(sample)
        )
        if with_app_indexes:
            # Tasks and Events deliberately advertise referenceable=True.
            # Their canonical IDs therefore belong to the generic reference
            # lookup as well as both application-scoped semantic projections.
            expected = {
                **{
                    f"persona-{i}": hashlib.sha256(repo.read_text(f"{i}.md").encode()).hexdigest()
                    for i in range(people_count)
                },
                **{
                    fixture_id: hashlib.sha256(
                        repo.read_text(f"{fixture_id}.md").encode()
                    ).hexdigest()
                    for fixture_id in ("fixture-task", "fixture-event")
                },
            }
            assert hashes == expected
            for app_index, _schema in app_indexes.values():
                with sqlite3.connect(app_index.path) as connection:
                    indexed = dict(connection.execute("SELECT id,source_hash FROM notes"))
                assert indexed == expected
    commits = subprocess.run(
        ["git", "rev-list", "--count", "HEAD"],
        cwd=repo.root,
        text=True,
        capture_output=True,
        check=True,
    )
    assert int(commits.stdout) == sample + 1 + int(with_app_indexes)
    return {
        "vault_notes": size,
        "eligible_people": people_count,
        "writes": sample,
        "semantic_enabled": with_semantic,
        "embedding": "local_neural_offline" if offline_model_cache is not None else "synthetic",
        "app_indexes_enabled": list(app_indexes),
        "refresh_calls": len(refresh_batches),
        "batch_sizes": [len(batch) for batch in refresh_batches],
        "write_loop_s": round(writer_elapsed, 2),
        "reader_barrier_wait_s": round(wait_elapsed, 2),
        "complete_elapsed_s": round(elapsed, 2),
        "cpu_s": round(cpu_used, 2),
        "write_median_ms": round(1000 * statistics.median(writes), 1),
        "refresh_total_s": round(sum(refresh_times), 2),
        "rss_peak_mib_cumulative": round(
            resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1
        ),
        "available_mib": host_memory_mib(),
        "filtered_query_count": page.total,
        "git_commits": int(commits.stdout),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scales", default="250:12", help="SIZE:SAMPLE comma-separated")
    parser.add_argument(
        "--offline-model-cache",
        type=Path,
        default=None,
        help="Use cached FastEmbed ONNX locally and with local_files_only=True (no downloads)",
    )
    parser.add_argument(
        "--with-app-indexes",
        action="store_true",
        help="Also build Task and Event fixtures and refresh both App semantic indexes",
    )
    parser.add_argument(
        "--with-semantic",
        action="store_true",
        help="Also reconcile the canonical SemanticEntityIndex with verified context proof",
    )
    args = parser.parse_args()
    scales = parse_scales(args.scales)
    if args.offline_model_cache is not None:
        resolved = args.offline_model_cache.resolve(strict=True)
        if not resolved.is_dir() or resolved.is_relative_to(Path("/data/odyssey")):
            raise ValueError("Offline model cache must be a safe existing directory")
    if host_memory_mib().get("MemAvailable", 0) < 900:
        raise RuntimeError("Insufficient memory for safe synthetic benchmark")
    print("SCHEMA_BATCH_START", json.dumps(host_memory_mib()), flush=True)
    with tempfile.TemporaryDirectory(prefix="odyssey-index-batch-", dir="/tmp") as root:
        for size, sample in scales:
            if host_memory_mib().get("MemAvailable", 0) < 900:
                raise RuntimeError("Insufficient memory for next synthetic scale")
            print(
                "SCHEMA_BATCH_RESULT",
                json.dumps(
                    run_sample(
                        Path(root),
                        size,
                        sample,
                        with_semantic=args.with_semantic,
                        with_app_indexes=args.with_app_indexes,
                        offline_model_cache=args.offline_model_cache,
                    )
                ),
                flush=True,
            )
    print("SCHEMA_BATCH_END", json.dumps(host_memory_mib()), flush=True)


if __name__ == "__main__":
    main()
