#!/usr/bin/env python3
"""Disposable real Chromium -> synthetic localhost proxy -> real HTTP/Core/Git.

NOT a deployed DEV / n8n / provider test. No real user data.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Thread

from odyssey_core.notes import parse_note
from odyssey_core.schema_retrospection_jobs import LocalSchemaScanJobs
from odyssey_runtime.server import _handler_for
from tests.runtime.test_schema_backfill_notes_vertical import fixture

ROOT = Path(__file__).resolve().parents[1]
BROWSER = ROOT / "scripts/odyssey_schema_backfill_chromium_local.cjs"
PI_LIBS = Path(
    "/home/ragdehl/projects/.odyssey-agent-runs/"
    "e6-chromium-runtime-deps/root/usr/lib/aarch64-linux-gnu"
)


def run() -> dict:
    results: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="odyssey-schema-chromium-", dir="/tmp") as folder:
        parent = Path(folder)
        for viewport in ("desktop", "mobile"):
            container = parent / viewport
            container.mkdir()
            app, repo, state = fixture(container)
            app.schema_scan_factory = lambda actor, state=state, repo=repo: LocalSchemaScanJobs(
                state_root=state, repository=repo, actor_id=actor
            )
            before = {
                path: hashlib.sha256(repo.read_text(path).encode()).hexdigest()
                for path in repo.list_markdown_paths()
            }
            server = ThreadingHTTPServer(("127.0.0.1", 0), _handler_for(app))
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                env = os.environ.copy()
                env["ODYSSEY_SYNTH_LOCAL_HTTP"] = f"http://127.0.0.1:{server.server_address[1]}/"
                if PI_LIBS.is_dir():
                    env["LD_LIBRARY_PATH"] = str(PI_LIBS) + ":" + env.get("LD_LIBRARY_PATH", "")
                task = subprocess.run(
                    ["node", str(BROWSER), viewport],
                    cwd=ROOT,
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=65,
                    check=False,
                )
                browser = next(
                    (
                        json.loads(line.split("ODYSSEY_BACKFILL_BROWSER=", 1)[1])
                        for line in task.stdout.splitlines()
                        if line.startswith("ODYSSEY_BACKFILL_BROWSER=")
                    ),
                    None,
                )
                if task.returncode or not browser or not browser.get("pass"):
                    raise RuntimeError(
                        f"Isolated browser FAIL {viewport}: {browser} " + task.stderr[-500:]
                    )
                after = {
                    path: hashlib.sha256(repo.read_text(path).encode()).hexdigest()
                    for path in repo.list_markdown_paths()
                }
                notes = {
                    path: parse_note(repo.read_text(path)).metadata
                    for path in repo.list_markdown_paths()
                }
                commits = int(
                    subprocess.check_output(
                        ["git", "rev-list", "--count", "HEAD"], cwd=repo.root, text=True
                    ).strip()
                )
                assert notes["0.md"]["profesion"] == "médica"
                assert notes["0.md"]["revision"] == 2
                assert "profesion" not in notes["1.md"]
                assert after["0.md"] != before["0.md"]
                assert after["1.md"] == before["1.md"]
                assert commits == 2
                journal = next((state / "schema-backfill-jobs").glob("*.json"))
                assert "médica" not in journal.read_text()
                assert "profesora" not in journal.read_text()
                results.append(
                    {
                        "viewport": viewport,
                        "pass": True,
                        "browserClicks": True,
                        "coreHttpReal": True,
                        "n8n": False,
                        "updated": 1,
                        "deferred": 1,
                        "gitCommitCount": commits,
                        "reload": browser.get("reloadPersisted"),
                        "requests": browser.get("requests"),
                    }
                )
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=6)
    return {
        "pass": len(results) == 2,
        "model": "NONE",
        "DEV": "NOT_TESTED",
        "n8n": "NOT_TESTED",
        "results": results,
    }


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    result = run()
    print("ODYSSEY_BACKFILL_LOCAL_E2E=" + json.dumps(result, ensure_ascii=False))
    raise SystemExit(0 if result["pass"] else 1)
