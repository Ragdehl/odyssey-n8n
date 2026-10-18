from __future__ import annotations

import json
import re
import resource
import time

from odyssey_core.source_provenance import SourceEvidenceError, anchor_literal_evidence

samples = [
    ("unique_4k", "b" * 3990 + "target_token", "target_token", None),
    ("overlap_4k", "a" * 4000, "aa", None),
    ("unique_context", "f" * 3900 + "XaaY", "aa", "XaaY"),
]


def legacy(text, token, context):
    if context is None:
        return len(list(re.finditer(re.escape(token), text))) == 1
    return (
        len(list(re.finditer(re.escape(context), text))) == 1
        and len(list(re.finditer(re.escape(token), context))) == 1
    )


def new(text, token, context):
    try:
        anchor_literal_evidence(text, token, primary_context=context)
        return True
    except SourceEvidenceError:
        return False


def bench(fn, text, token, context):
    for _ in range(100):
        fn(text, token, context)
    samples_ns = []
    start_cpu = time.process_time()
    for _ in range(1500):
        start = time.perf_counter_ns()
        fn(text, token, context)
        samples_ns.append(time.perf_counter_ns() - start)
    samples_ns.sort()
    return {
        "p50_ms": round(samples_ns[len(samples_ns) // 2] / 1e6, 5),
        "p95_ms": round(samples_ns[int(len(samples_ns) * 0.95)] / 1e6, 5),
        "max_ms": round(samples_ns[-1] / 1e6, 5),
        "cpu_ms_1500_calls": round((time.process_time() - start_cpu) * 1e3, 2),
    }


before_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
rows = []
for name, text, token, context in samples:
    old = bench(legacy, text, token, context)
    corrected = bench(new, text, token, context)
    rows.append(
        {
            "scenario": name,
            "legacy": old,
            "corrected": corrected,
            "legacy_accepts": legacy(text, token, context),
            "corrected_accepts": new(text, token, context),
        }
    )
after_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
print(
    json.dumps(
        {
            "host": "Raspberry Pi arm64",
            "trials_per_case": 1500,
            "rss_highwater_before_kib": before_rss,
            "rss_highwater_after_kib": after_rss,
            "samples": rows,
        },
        indent=2,
    ),
    flush=True,
)
