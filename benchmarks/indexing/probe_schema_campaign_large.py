"""Validate >10k *eligible* notes across independent bounded HMAC/E3/Git journals.

Source-only Raspberry probe; all Markdown and Git live in a disposable /tmp
repository. Only a handful of writes are performed, NOT 10k individual writes.
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
from odyssey_core.notes import parse_note  # noqa: E402
from odyssey_runtime.schema_backfill_campaign import LocalBackfillCampaign  # noqa: E402
from odyssey_runtime.schema_backfill_jobs import LocalBackfillJob  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--notes", type=int, default=11000)
    parser.add_argument("--writes", type=int, default=3)
    parser.add_argument("--segment-size", type=int, default=2)
    args = parser.parse_args()
    if not (
        10000 < args.notes <= 50000
        and 1 <= args.segment_size <= 10000
        and args.segment_size < args.writes <= min(10, args.notes)
    ):
        raise ValueError("Require >10k physical and eligible notes, and crosses >=2 segments")
    if host_memory_mib().get("MemAvailable", 0) < 900:
        raise RuntimeError("Insufficient RAM for large isolated vault")

    with tempfile.TemporaryDirectory(prefix="odyssey-campaign-large-", dir="/tmp") as root:
        started = time.perf_counter()
        try:
            state, repo, writer = setup(Path(root), ["Profesión: médica"] * args.notes)
        except subprocess.CalledProcessError as error:
            # The shared tiny pytest fixture captures Git stderr. Preserve
            # its diagnostic when used as a >10k-file standalone benchmark.
            print(
                "SYNTHETIC_GIT_FIXTURE_ERROR",
                json.dumps(
                    {
                        "notes": args.notes,
                        "command": error.cmd,
                        "code": error.returncode,
                        "stderr": str(error.stderr)[-1800:],
                    }
                ),
                flush=True,
            )
            raise
        prepared = time.perf_counter() - started

        worker = LocalBackfillJob(
            state_root=state, repository=repo, writer=writer, actor_id="campaign-isolated"
        )
        campaign = LocalBackfillCampaign(worker=worker, segment_size=args.segment_size)
        stage_started = time.perf_counter()
        first = campaign.stage(
            campaign_id="approved-property", type_id="person", property_id="profesion"
        )
        stage_s = time.perf_counter() - stage_started
        assert first["total"] == args.segment_size
        writes_started = time.perf_counter()
        for _ in range(args.writes):
            summary = campaign.advance(
                campaign_id="approved-property",
                type_id="person",
                property_id="profesion",
                actor=ACTOR,
                now=NOW,
            )
        writes_s = time.perf_counter() - writes_started
        assert summary["updated"] == args.writes
        assert not summary["finished"]
        reopened = LocalBackfillCampaign(
            worker=LocalBackfillJob(
                state_root=state,
                repository=repo,
                writer=writer,
                actor_id="campaign-isolated",
            ),
            segment_size=args.segment_size,
        )
        assert reopened.status("approved-property") == summary
        updated_paths: set[str] = set()
        for index in range(args.notes):
            note = parse_note(repo.read_text(f"{index}.md"))
            if "profesion" in note.metadata:
                assert note.metadata["profesion"] == "médica"
                updated_paths.add(f"{index}.md")
        assert len(updated_paths) == args.writes
        # Staging deliberately traverses lexicographically sorted physical
        # paths, not numeric note indices. Independently prove exactly those
        # same paths changed relative to the Git baseline.
        git_changed = subprocess.check_output(
            ["git", "diff", f"HEAD~{args.writes}", "HEAD", "--name-only"],
            cwd=repo.root,
            text=True,
        ).splitlines()
        assert set(git_changed) == updated_paths
        commit_count = int(
            subprocess.check_output(
                ["git", "rev-list", "--count", "HEAD"], cwd=repo.root, text=True
            ).strip()
        )
        assert commit_count == args.writes + 1
        child_receipts = list((state / "schema-backfill-jobs").glob("*.json"))
        assert len(child_receipts) == 1 + (args.writes - 1) // args.segment_size + 1
        assert all("médica" not in path.read_text() for path in child_receipts)
        print(
            "LARGE_CAMPAIGN_RESULT",
            json.dumps(
                {
                    "eligible_notes": args.notes,
                    "writes_completed": args.writes,
                    "segment_size": args.segment_size,
                    "segment_index": summary["segment"],
                    "prep_fixture_s": round(prepared, 2),
                    "initial_stage_s": round(stage_s, 2),
                    "few_segmented_writes_s": round(writes_s, 2),
                    "reopened": True,
                    "git_commits": commit_count,
                    "receipt_count": len(child_receipts),
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
