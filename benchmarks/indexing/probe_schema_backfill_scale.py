"""Measure schema-backfill Git + ContextIndex cost at different synthetic vault sizes.

Disposable /tmp fixtures only, real Core/E3 history and deterministic embeddings.
Not a full semantic-index or mobile benchmark. No real provider, DEV or PROD access.

Quick smoke:
    python benchmarks/indexing/probe_schema_backfill_scale.py
Scale sample:
    python benchmarks/indexing/probe_schema_backfill_scale.py --scales 1000:12,5000:8,10000:5
"""

from __future__ import annotations

import argparse
import json
import resource
import statistics
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests" / "runtime"))

from test_schema_backfill_jobs import ACTOR, NOW, setup  # noqa: E402

from odyssey_core.context import ContextFilter, ContextIndex  # noqa: E402
from odyssey_core.note_queries import NotesQueryService  # noqa: E402
from odyssey_runtime.schema_backfill_jobs import LocalBackfillJob  # noqa: E402


class DeterministicEmbedder:
    model_name = "tests/local-zero-provider"
    model_version = "1"

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0] for _ in texts]

    def embed_queries(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0] for _ in texts]


def host_memory_mib() -> dict[str, int]:
    result: dict[str, int] = {}
    for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
        if line.startswith(("MemAvailable:", "SwapFree:")):
            key, value = line.split(":", 1)
            result[key.removesuffix(":")] = round(int(value.split()[0]) / 1024)
    return result


def parse_scales(raw: str) -> list[tuple[int, int]]:
    scales = []
    for pair in raw.split(","):
        try:
            size, sample = (int(part) for part in pair.split(":"))
        except ValueError as error:
            raise ValueError("Scales must use SIZE:SAMPLE comma-separated pairs") from error
        if not (1 <= sample <= size <= 10000):
            raise ValueError("Each scale requires 1 <= sample <= size <= 10000")
        scales.append((size, sample))
    if not scales or len(scales) > 5:
        raise ValueError("Specify one to five scales")
    return scales


def run_sample(root: Path, size: int, sample: int) -> dict[str, object]:
    fixture = root / f"notes-{size}"
    fixture.mkdir()
    state, repository, writer = setup(fixture, ["profesion: médica"] * size)
    index = ContextIndex(fixture / "derived" / "context.sqlite3")
    embedder = DeterministicEmbedder()
    index_started = time.perf_counter()
    assert index.rebuild(repository, writer.schema, embedder) == size
    index_elapsed = time.perf_counter() - index_started
    refresh_times: list[float] = []

    def refresh(note_id: str) -> None:
        start = time.perf_counter()
        index.refresh_notes(repository, writer.schema, embedder, note_ids=(note_id,))
        refresh_times.append(time.perf_counter() - start)

    job = LocalBackfillJob(
        state_root=state,
        repository=repository,
        writer=writer,
        actor_id="synthetic",
        on_updated=refresh,
    )
    stage_started = time.perf_counter()
    summary = job.stage(job_id="perf", type_id="person", property_id="profesion")
    stage_elapsed = time.perf_counter() - stage_started
    assert summary["pending"] == size

    write_times: list[float] = []
    cpu_started = time.process_time()
    writes_started = time.perf_counter()
    for _ in range(sample):
        start = time.perf_counter()
        summary = job.advance(
            job_id="perf",
            type_id="person",
            property_id="profesion",
            actor=ACTOR,
            now=NOW,
        )
        write_times.append(time.perf_counter() - start)
    total_elapsed = time.perf_counter() - writes_started
    cpu_elapsed = time.process_time() - cpu_started
    assert summary["updated"] == sample

    query = NotesQueryService(repository, writer.schema, index)
    result = query.query(filters=[ContextFilter("profesion", "eq", "médica")], page_size=20)
    assert result.total == sample
    assert len(refresh_times) == sample

    def sample_p95_ms(values: list[float]) -> float:
        return round(sorted(values)[int(0.95 * (len(values) - 1))] * 1000, 1)

    return {
        "vault_notes": size,
        "sample_writes": sample,
        "initial_context_index_s": round(index_elapsed, 2),
        "stage_s": round(stage_elapsed, 2),
        "writes_and_context_s": round(total_elapsed, 2),
        "writes_cpu_s": round(cpu_elapsed, 2),
        "per_write_median_ms": round(statistics.median(write_times) * 1000, 1),
        "per_write_observed_p95_ms": sample_p95_ms(write_times),
        "context_refresh_total_s": round(sum(refresh_times), 2),
        "context_refresh_observed_p95_ms": sample_p95_ms(refresh_times),
        "rss_peak_mib_cumulative": round(
            resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1
        ),
        "query_count": result.total,
        "memory_mib": host_memory_mib(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scales",
        default="25:3",
        help="Comma-separated SIZE:SAMPLE pairs; default is a quick synthetic smoke",
    )
    args = parser.parse_args()
    scales = parse_scales(args.scales)
    if host_memory_mib().get("MemAvailable", 0) < 900:
        raise RuntimeError("Insufficient available RAM for safe benchmark")
    print("SCHEMA_BENCH_START", json.dumps(host_memory_mib()), flush=True)
    with tempfile.TemporaryDirectory(prefix="odyssey-backfill-scale-", dir="/tmp") as directory:
        for size, sample in scales:
            if host_memory_mib().get("MemAvailable", 0) < 900:
                raise RuntimeError("Insufficient available RAM for next sample")
            result = run_sample(Path(directory), size, sample)
            print("SCHEMA_BENCH_RESULT", json.dumps(result), flush=True)
    print("SCHEMA_BENCH_END", json.dumps(host_memory_mib()), flush=True)


if __name__ == "__main__":
    main()
