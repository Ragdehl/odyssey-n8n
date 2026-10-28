#!/usr/bin/env python3
"""Opt-in bounded 10,001–50,000 physical Markdown-note scanner probe.

No provider, no 50k-note Git commit, no personal vault, no DEV/PROD deploy.
Run only on a host with safe memory and space headroom:
  python benchmarks/indexing/probe_schema_scan_50k_readonly.py --run --notes 50000
Stdout carries the measured result; invoke via shell redirection if persistence
is required. A single run does NOT establish a p95 latency SLA.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[2]

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument(
    "--notes", type=int, default=50000, help="Physical synthetic notes, 10001–50000"
)
parser.add_argument(
    "--run", action="store_true", help="Explicitly consent to a bounded Pi resource probe"
)
args = parser.parse_args()
if not args.run:
    parser.error("Specify --run to create and scan a temporary synthetic vault")
if not 10001 <= args.notes <= 50000:
    parser.error("Expected 10001–50000 synthetic notes")
EXPECTED = subprocess.check_output(
    ["git", "-C", str(SOURCE), "rev-parse", "HEAD"], text=True
).strip()
if not Path("/tmp").is_dir():
    raise SystemExit("MISSING_TMPFS")
sys.path[:0] = [str(SOURCE), str(SOURCE / "tests/runtime")]
from test_schema_backfill_jobs import setup  # noqa: E402

from odyssey_core.notes import Note, parse_note, serialize_note  # noqa: E402
from odyssey_core.schema_retrospection_jobs import LocalSchemaScanJobs  # noqa: E402

NOTES = args.notes
LIMIT_SECONDS = 235
MIN_MEM_AVAILABLE_KIB = 950 * 1024
SAMPLES = []
STOP = threading.Event()


def meminfo():
    out = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        if line.startswith(("MemAvailable:", "SwapTotal:", "SwapFree:")):
            parts = line.split()
            out[parts[0][:-1]] = int(parts[1])
    return out


def sample():
    while not STOP.wait(0.35):
        m = meminfo()
        if m["MemAvailable"] < MIN_MEM_AVAILABLE_KIB:
            os.kill(os.getpid(), signal.SIGTERM)
        temp = Path("/sys/class/thermal/thermal_zone0/temp")
        try:
            t = float(temp.read_text().strip()) / 1000 if temp.exists() else None
        except (OSError, ValueError):
            t = None
        rss = 0
        try:
            for line in Path("/proc/self/status").read_text().splitlines():
                if line.startswith("VmRSS:"):
                    rss = int(line.split()[1])
                    break
        except OSError:
            pass
        SAMPLES.append((m["MemAvailable"], m["SwapTotal"] - m["SwapFree"], rss, t))


def _bounded_abort(_signal, _frame):
    raise TimeoutError("PI_SYNTHETIC_SCAN_RESOURCE_OR_TIME_GUARD")


signal.signal(signal.SIGTERM, _bounded_abort)
signal.signal(signal.SIGALRM, _bounded_abort)
before = meminfo()
if before["MemAvailable"] < MIN_MEM_AVAILABLE_KIB + 200000:
    raise SystemExit("NO_RESOURCE_HEADROOM")
size = os.statvfs("/tmp")
if size.f_bavail * size.f_frsize < 700 * 1024 * 1024:
    raise SystemExit("TMPFS_FREE_TOO_LOW")
thread = threading.Thread(target=sample, daemon=True)
thread.start()
signal.alarm(LIMIT_SECONDS)
all_start = time.perf_counter()
cpu_before = time.process_time()
temperature = []
with tempfile.TemporaryDirectory(prefix="odyssey-perf-50k-scan-", dir="/tmp") as temp_root:
    root = Path(temp_root)
    state, repo, writer = setup(root, ["Profesión: médica"])
    sample_note = parse_note(repo.read_text("0.md"))
    extras = repo.root / "synth-others"
    extras.mkdir()
    for i in range(NOTES - 1):
        d = extras / f"{i // 1000:03}"
        d.mkdir(exist_ok=True)
        note = Note(
            {
                **sample_note.metadata,
                "id": f"big-synthetic-{i:05d}",
                "name": f"Synthetic excluded note {i:05d}",
                "profesion": "docente",
            },
            "# Added 28-10-2026\n- Ya se registró el valor.\n",
        )
        (d / f"{i:05d}.md").write_text(serialize_note(note), encoding="utf-8")
        if i and i % 10000 == 0:
            print("FIXTURE_CREATED", i, "of", NOTES - 1, flush=True)
            if time.perf_counter() - all_start > LIMIT_SECONDS - 30:
                raise RuntimeError("FIXTURE_DURATION_GUARD")
    fixture_seconds = time.perf_counter() - all_start
    scanner = LocalSchemaScanJobs(state_root=state, repository=repo, actor_id="synthetic-audit-50k")
    start = time.perf_counter()
    pages = 0
    restart_count = 0
    while True:
        progress = scanner.advance(
            job_id="large50k",
            schema=writer.schema,
            kind="backfill_property",
            target_type_id="person",
            property_id="profesion",
            limit=25,
        )
        pages += 1
        if progress.complete:
            break
        if pages % 400 == 0:
            scanner = LocalSchemaScanJobs(
                state_root=state, repository=repo, actor_id="synthetic-audit-50k"
            )
            restart_count += 1
        if pages % 500 == 0:
            print("SCAN_PROGRESS", progress.scanned_paths, NOTES, flush=True)
    assert progress.scanned_paths == NOTES and progress.eligible_notes == 1
    assert progress.skipped_existing_values == NOTES - 1
    scan_seconds = time.perf_counter() - start
    reread_start = time.perf_counter()
    scanner = LocalSchemaScanJobs(state_root=state, repository=repo, actor_id="synthetic-audit-50k")
    recovered = scanner.read("large50k")
    assert recovered == progress
    resume_seconds = time.perf_counter() - reread_start
    all_elapsed = time.perf_counter() - all_start
    assert pages == (NOTES + 24) // 25 and restart_count >= (pages - 1) // 400
    cpu_used = time.process_time() - cpu_before
    STOP.set()
    thread.join(timeout=1)
    samples = SAMPLES or [
        (before["MemAvailable"], before["SwapTotal"] - before["SwapFree"], 0, None)
    ]
    result = {
        "source_sha": EXPECTED,
        "read_only": True,
        "synthetic_only": True,
        "notes": NOTES,
        "eligible": 1,
        "skipped_existing": NOTES - 1,
        "pages": pages,
        "resumptions": restart_count,
        "fixture_creation_s": round(fixture_seconds, 2),
        "scan_complete_s": round(scan_seconds, 2),
        "restart_read_s": round(resume_seconds, 4),
        "total_elapsed_s": round(all_elapsed, 2),
        "process_cpu_s": round(cpu_used, 2),
        "peak_rss_mib": round(max(x[2] for x in samples) / 1024, 2),
        "min_mem_available_mib": round(min(x[0] for x in samples) / 1024, 2),
        "max_swap_used_mib": round(max(x[1] for x in samples) / 1024, 2),
        "start_swap_used_mib": round((before["SwapTotal"] - before["SwapFree"]) / 1024, 2),
        "max_temperature_c": max((x[3] for x in samples if x[3] is not None), default=None),
        "sample_count": len(samples),
        "physical_markdown_verified_at_finish": True,
        "no_real_git_50k_commit": True,
        "not_a_50k_write_benchmark": True,
        "note": "Single Pi 4 ARM64 fixture scan; Git of 50k notes not committed, no latency p95 SLA.",
    }
    print("PI_SYNTHETIC_50000_SCHEMA_SCAN_RESULT", json.dumps(result, sort_keys=True), flush=True)

STOP.set()
print("PI_50000_SCAN_CLEANUP_DONE", flush=True)
