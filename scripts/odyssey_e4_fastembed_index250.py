"""E4 synthetic Pi context + semantic rebuild using real offline FastEmbed; no private vault."""

import json
import resource
import tempfile
import time
from pathlib import Path

from odyssey_core import create_entity
from odyssey_core.context import ContextIndex
from odyssey_core.semantic import FastEmbedTextEmbedder, SemanticEntityIndex
from odyssey_core.storage import VaultRepository

BASE = Path("/home/ragdehl/projects/.odyssey-agent-runs")
CACHE = BASE / "e4-fastembed-synthetic-cache-20261021"
SCHEMA = json.loads((Path(__file__).resolve().parents[1] / "config/note-schema.json").read_text())


def snapshot():
    data = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        if line.startswith(("MemAvailable:", "SwapFree:")):
            key, val, *_ = line.split()
            data[key[:-1]] = int(val)
    try:
        data["temperature_millideg"] = int(
            Path("/sys/class/thermal/thermal_zone0/temp").read_text()
        )
    except (OSError, ValueError):
        data["temperature_millideg"] = None
    return data


with tempfile.TemporaryDirectory(prefix="e4-real-embed-index-", dir=BASE) as where:
    temp = Path(where)
    (temp / "vault").mkdir()
    repo = VaultRepository(temp / "vault")
    now = "2026-10-21T11:00:00+02:00"
    started = time.perf_counter()
    for i in range(250):
        create_entity(
            repo,
            SCHEMA,
            path=f"synthetic-person-{i:04}.md",
            entity_id=f"e4-benchmark-person-{i:04}",
            metadata={"name": f"Synthetic Person {i:04}", "type": "person"},
            content=f"- Met synthetic person {i} in the park.\n",
            actor="fixture",
            now=now,
        )
    created = time.perf_counter() - started
    start = time.perf_counter()
    embedder = FastEmbedTextEmbedder(cache_dir=CACHE, local_files_only=True)
    load = time.perf_counter() - start
    index = ContextIndex(temp / "context.sqlite3")
    semantic = SemanticEntityIndex(temp / "semantic.sqlite3")
    begin = snapshot()
    before_cpu = resource.getrusage(resource.RUSAGE_SELF)
    start = time.perf_counter()
    index.rebuild(repo, SCHEMA, embedder)
    context_s = time.perf_counter() - start
    start = time.perf_counter()
    semantic.rebuild(repo, SCHEMA, embedder)
    semantic_s = time.perf_counter() - start
    after_cpu = resource.getrusage(resource.RUSAGE_SELF)
    print(
        "E4_FASTEMBED_INDEX="
        + json.dumps(
            {
                "synthetic_notes": 250,
                "note_create_s": round(created, 3),
                "model_offline_load_s": round(load, 3),
                "context_rebuild_s": round(context_s, 3),
                "semantic_rebuild_s": round(semantic_s, 3),
                "cpu_user_delta_s": round(after_cpu.ru_utime - before_cpu.ru_utime, 3),
                "cpu_system_delta_s": round(after_cpu.ru_stime - before_cpu.ru_stime, 3),
                "peak_rss_kib": after_cpu.ru_maxrss,
                "host_before": begin,
                "host_after": snapshot(),
                "model": "FastEmbed real offline",
                "private_vault_access": False,
                "network_used": False,
            }
        ),
        flush=True,
    )
