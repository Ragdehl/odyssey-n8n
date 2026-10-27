"""Prove >10k physical Markdown sources with a bounded, resumable E3 write plan.

This is an opt-in Raspberry benchmark: synthetic Git vault in /tmp, no
provider, DEV, PROD or personal Notes. It distinguishes scanning an entire
large physical vault from authorizing a bounded (<=10k) mutation journal.

    python3 benchmarks/indexing/probe_schema_large_stage.py --notes 12000 --eligible 1200
"""

from __future__ import annotations

import argparse
import json
import resource
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests/runtime"))

from test_schema_backfill_jobs import ACTOR, NOW, setup  # noqa: E402

from benchmarks.indexing.probe_schema_backfill_scale import host_memory_mib  # noqa: E402
from odyssey_core.notes import Note, parse_note, serialize_note  # noqa: E402
from odyssey_core.schema_retrospection_jobs import LocalSchemaScanJobs  # noqa: E402
from odyssey_runtime.schema_backfill_jobs import LocalBackfillJob  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--notes", type=int, default=12000)
    parser.add_argument("--eligible", type=int, default=1200)
    args = parser.parse_args()
    if not (
        10001 <= args.notes <= 50000 and 1 <= args.eligible <= 10000 and args.eligible < args.notes
    ):
        raise ValueError("Require 10001..50000 physical notes and 1..10000 candidates")
    if host_memory_mib().get("MemAvailable", 0) < 900:
        raise RuntimeError("Insufficient available memory for large synthetic scan")
    with tempfile.TemporaryDirectory(prefix="odyssey-staged-large-", dir="/tmp") as root:
        state, repo, writer = setup(Path(root), ["Profesión: médica"] * args.eligible)
        sample = parse_note(repo.read_text("0.md"))
        extras = repo.root / "with-existing-property"
        extras.mkdir()
        for index in range(args.notes - args.eligible):
            note = Note(
                {
                    **sample.metadata,
                    "id": f"excluded-{index}",
                    "name": f"Already occupied {index}",
                    "profesion": "docente",
                },
                "Existing user-owned property must never be overwritten.\n",
            )
            (extras / f"{index:05}.md").write_text(serialize_note(note), encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=repo.root, check=True, timeout=180)
        subprocess.run(
            [
                "git",
                "-c",
                "user.name=Test",
                "-c",
                "user.email=test@localhost",
                "commit",
                "-qm",
                "synthetic-ineligible-notes",
            ],
            cwd=repo.root,
            check=True,
            timeout=180,
        )
        read_only = LocalSchemaScanJobs(
            state_root=state, repository=repo, actor_id="large-synthetic"
        )
        scan_started = time.perf_counter()
        pages = 0
        while True:
            scan_result = read_only.advance(
                job_id="ui-large",
                schema=writer.schema,
                kind="backfill_property",
                target_type_id="person",
                property_id="profesion",
                limit=25,
            )
            pages += 1
            if scan_result.complete:
                break
            if pages % 61 == 0:
                # A fresh store object tests durable mid-scan resume.
                read_only = LocalSchemaScanJobs(
                    state_root=state, repository=repo, actor_id="large-synthetic"
                )
        scan_seconds = time.perf_counter() - scan_started
        assert scan_result.scanned_paths == args.notes
        assert scan_result.eligible_notes == args.eligible
        assert scan_result.skipped_existing_values == args.notes - args.eligible
        assert read_only.read("ui-large") == scan_result
        job = LocalBackfillJob(
            state_root=state, repository=repo, writer=writer, actor_id="large-synthetic"
        )
        started = time.perf_counter()
        summary = job.stage(job_id="large", type_id="person", property_id="profesion")
        stage_seconds = time.perf_counter() - started
        assert summary["pending"] == args.eligible
        assert job.status("large")["pending"] == args.eligible
        write_start = time.perf_counter()
        receipt = job.advance(
            job_id="large",
            type_id="person",
            property_id="profesion",
            actor=ACTOR,
            now=NOW,
        )
        write_seconds = time.perf_counter() - write_start
        assert receipt["updated"] == 1
        assert parse_note(repo.read_text("0.md")).metadata["profesion"] == "médica"
        assert (
            parse_note(repo.read_text("with-existing-property/00000.md")).metadata["profesion"]
            == "docente"
        )
        restarted = LocalBackfillJob(
            state_root=state, repository=repo, writer=writer, actor_id="large-synthetic"
        )
        assert restarted.status("large")["updated"] == 1
        assert (
            restarted.stage(job_id="large", type_id="person", property_id="profesion")["pending"]
            == args.eligible - 1
        )
        commits = int(
            subprocess.check_output(
                ["git", "rev-list", "--count", "HEAD"], cwd=repo.root, text=True
            )
        )
        assert commits == 3  # original, additional sources, one E3 commit
        print(
            "LARGE_SCAN_RESULT",
            json.dumps(
                {
                    "physical_notes": args.notes,
                    "eligible_candidates": args.eligible,
                    "ui_read_only_scan_s": round(scan_seconds, 2),
                    "ui_progress_pages": pages,
                    "ui_resume_verified": True,
                    "scanned_and_staged_s": round(stage_seconds, 2),
                    "one_protected_write_s": round(write_seconds, 2),
                    "reopened_journal": True,
                    "git_commits": commits,
                    "rss_peak_mib": round(
                        resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1
                    ),
                    "memory": host_memory_mib(),
                }
            ),
            flush=True,
        )


if __name__ == "__main__":
    main()
