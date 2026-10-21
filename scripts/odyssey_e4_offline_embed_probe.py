"""Offline local-only FastEmbed cold/warm probe; never fetch or access a private vault."""

import json
import resource
import time
from pathlib import Path

from odyssey_core.semantic import FastEmbedTextEmbedder

cache = Path.home() / ".cache" / "fastembed"
start = time.perf_counter()
try:
    model = FastEmbedTextEmbedder(cache_dir=cache, local_files_only=True)
    cold = time.perf_counter() - start
    a = time.perf_counter()
    first = model.embed_queries(["Hoy conocí a Ana y Luis"])
    warm = time.perf_counter() - a
    assert len(first) == 1
    a = time.perf_counter()
    second = model.embed_queries(["Mañana llamar a los dos"])
    warm2 = time.perf_counter() - a
    print(
        "E4_FASTEMBED_OFFLINE="
        + json.dumps(
            {
                "status": "measured",
                "cache_kind": "home isolated fastembed",
                "cold_load_s": round(cold, 3),
                "first_query_s": round(warm, 3),
                "warm_query_s": round(warm2, 3),
                "rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            }
        ),
        flush=True,
    )
except Exception as ex:
    print(
        "E4_FASTEMBED_OFFLINE="
        + json.dumps(
            {
                "status": "blocked_cache_absent_or_unusable",
                "reason": type(ex).__name__,
                "cache_kind": "home isolated fastembed",
                "cold_attempt_s": round(time.perf_counter() - start, 3),
                "download_attempted": False,
            }
        ),
        flush=True,
    )
