"""Exercise REAL >10k Notes API routing (no threshold monkeypatch) on a temporary Git vault.

The small internal segment size of 2 forces a boundary after two explicit
user-approved API advances. This does NOT execute 10k writes or Access/GPT.
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

from benchmarks.indexing.probe_schema_backfill_scale import host_memory_mib  # noqa: E402
from odyssey_core.notes import Note, parse_note, serialize_note  # noqa: E402
from odyssey_runtime import schema_backfill_campaign  # noqa: E402
from tests.runtime.test_schema_backfill_notes_vertical import (  # noqa: E402
    ALICE,
    BOB,
    fixture,
    request,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--notes", type=int, default=10001)
    args = parser.parse_args()
    if not 10000 < args.notes <= 15000:
        raise ValueError("Benchmark only supports an actual 10001-15000-note boundary")
    if host_memory_mib().get("MemAvailable", 0) < 900:
        raise RuntimeError("Insufficient free memory for isolated test")

    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="odyssey-api-boundary-", dir="/tmp") as root:
        app, repo, state = fixture(Path(root))
        original = parse_note(repo.read_text("0.md"))
        for i in range(2, args.notes):
            note = Note(
                {**original.metadata, "id": f"persona-{i}", "name": f"Persona {i}"},
                f"# Added 26-10-2026\n- Profesión: médica\n"
                f"<!-- odyssey:fact request=req{i} ordinal=0 -->\n",
            )
            (repo.root / f"{i}.md").write_text(serialize_note(note), encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=repo.root, check=True)
        subprocess.run(
            [
                "git",
                "-c",
                "user.name=Test",
                "-c",
                "user.email=test@localhost",
                "commit",
                "-qm",
                "isolated-large-vault",
            ],
            cwd=repo.root,
            check=True,
        )
        prepared_s = time.perf_counter() - started
        # Internal test sizing, not a browser-input override or production flag.
        schema_backfill_campaign._DEFAULT_SEGMENT_SIZE = 2
        assert len(repo.note_version_snapshot()) == args.notes
        assert app.notes("schema_backfill", request("status"), ALICE)["status"] == "not_started"
        stage_at = time.perf_counter()
        staged = app.notes("schema_backfill", request("stage"), ALICE)
        stage_s = time.perf_counter() - stage_at
        assert staged["total"] == staged["pending"] == 2
        assert staged["segment"] == 0 and staged["finished"] is False
        unauthorized = False
        try:
            app.notes("schema_backfill", request("advance"), BOB)
        except ValueError:
            unauthorized = True
        assert unauthorized
        advances_at = time.perf_counter()
        first = app.notes("schema_backfill", request("advance"), ALICE)
        assert first["updated"] == 1
        second = app.notes("schema_backfill", request("advance"), ALICE)
        assert second["updated"] == 1 and second["deferred"] == 1
        assert second["status"] == "in_progress" and not second["finished"]
        third = app.notes("schema_backfill", request("advance"), ALICE)
        advance_s = time.perf_counter() - advances_at
        assert third["segment"] == 1
        assert third["updated"] == 2 and third["deferred"] == 1
        assert third["total"] == 4 and third["pending"] == 1
        assert not third["finished"]
        # Rebuild the worker to prove a fresh instance can read the parent
        # and child receipts, instead of trusting the original instance.
        original_factory = app.schema_backfill_factory
        app.schema_backfill_factory = lambda actor: original_factory(actor)
        assert app.notes("schema_backfill", request("status"), ALICE) == third
        assert parse_note(repo.read_text("0.md")).metadata["profesion"] == "médica"
        assert "profesion" not in parse_note(repo.read_text("1.md")).metadata
        updated = [
            path
            for path in repo.list_markdown_paths()
            if "profesion" in parse_note(repo.read_text(path)).metadata
        ]
        assert len(updated) == 2
        git_paths = subprocess.check_output(
            ["git", "diff", "HEAD~2", "HEAD", "--name-only"],
            cwd=repo.root,
            text=True,
        ).splitlines()
        assert set(updated) == set(git_paths)
        commit_count = int(
            subprocess.check_output(
                ["git", "rev-list", "--count", "HEAD"],
                cwd=repo.root,
                text=True,
            ).strip()
        )
        assert commit_count == 4  # 2 baseline + 2 updated
        assert len(list((state / "schema-backfill-jobs").glob("*.campaign.json"))) == 1
        print(
            "LARGE_NOTES_API_RESULT",
            json.dumps(
                {
                    "vault_notes": args.notes,
                    "route": "RuntimeComposition.notes(schema_backfill)",
                    "actual_10000_threshold": True,
                    "override_only_private_segment_size": 2,
                    "initial_stage_s": round(stage_s, 2),
                    "three_explicit_advances_s": round(advance_s, 2),
                    "updated": third["updated"],
                    "deferred": third["deferred"],
                    "pending": third["pending"],
                    "segment": third["segment"],
                    "parent_finished": third["finished"],
                    "authenticated_wrong_actor_rejected": unauthorized,
                    "new_worker_readback": True,
                    "git_commits": commit_count,
                    "rss_peak_mib": round(
                        resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1
                    ),
                    "fixture_s": round(prepared_s, 2),
                }
            ),
            flush=True,
        )


if __name__ == "__main__":
    main()
