"""Bounded offline FastEmbed isolated cache evaluation, 3 processes, synthetic text."""

import json
import resource
import statistics
import subprocess
import sys
import time
from pathlib import Path

from odyssey_core.semantic import FastEmbedTextEmbedder

ROOT = Path("/home/ragdehl/projects/.odyssey-agent-runs/e4-fastembed-synthetic-cache-20261021")


def mem():
    data = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        if line.startswith(("MemAvailable:", "SwapFree:")):
            key, val, *_ = line.split()
            data[key[:-1]] = int(val)
    try:
        data["cpu_thermal_millideg"] = int(
            Path("/sys/class/thermal/thermal_zone0/temp").read_text().strip()
        )
    except (OSError, ValueError):
        data["cpu_thermal_millideg"] = None
    return data


def one():
    start = time.perf_counter()
    model = FastEmbedTextEmbedder(cache_dir=ROOT, local_files_only=True)
    load = time.perf_counter() - start
    texts = [
        "Ana y Luis fueron al parque",
        "¿Cuándo debo llamarlos?",
        "Dos personas conocidas recientemente",
    ]
    observations = []
    for text in texts:
        now = time.perf_counter()
        result = model.embed_queries([text])
        observations.append(round(1000 * (time.perf_counter() - now), 3))
        assert len(result) == 1 and len(result[0]) == 384
    print(
        "E4_FASTEMBED_OFFLINE_PROCESS="
        + json.dumps(
            {
                "load_s": round(load, 3),
                "query_ms": observations,
                "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                "host_after": mem(),
                "source": "synthetic",
                "private_vault_access": False,
                "download_attempted": False,
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    if "--single" in sys.argv:
        one()
    else:
        runs = []
        for i in range(3):
            begun = time.monotonic()
            completed = subprocess.run(
                [sys.executable, __file__, "--single"],
                capture_output=True,
                text=True,
                timeout=50,
                check=True,
            )
            rows = [
                json.loads(line.partition("=")[2])
                for line in completed.stdout.splitlines()
                if line.startswith("E4_FASTEMBED_OFFLINE_PROCESS=")
            ]
            assert len(rows) == 1, completed.stdout[-500:]
            runs.extend(rows)
            print("E4_FASTEMBED_SAMPLE=" + json.dumps({"trial": i + 1, **rows[0]}), flush=True)
        values = sorted(row["load_s"] for row in runs)
        print(
            "E4_FASTEMBED_OFFLINE_SUMMARY="
            + json.dumps(
                {
                    "trials": len(values),
                    "load_median_s": statistics.median(values),
                    "load_min_s": min(values),
                    "load_max_s": max(values),
                    "model_isolated_offline": True,
                    "not_a_product_p95": True,
                }
            ),
            flush=True,
        )
