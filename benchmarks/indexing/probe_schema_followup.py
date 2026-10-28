#!/usr/bin/env python3
"""Reproducible, disposable signed follow-up probe on the current host.

Every write is inside a TemporaryDirectory in /tmp; all model replies are
local fake responses. This is NOT a real-provider, DEV, 10k-note or mobile
performance guarantee.
"""

from __future__ import annotations

import json
import resource
import subprocess
import tempfile
import time
from pathlib import Path

from odyssey_core.notes import parse_note
from tests.runtime.test_schema_backfill_campaign import campaign, run_to_end, setup
from tests.runtime.test_schema_backfill_followup import (
    advance_campaign,
    budgeted,
    semantic_followup_id,
)
from tests.runtime.test_schema_semantic_budget import ProfessionGateway


def _host_health() -> dict[str, float]:
    stats = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        label, _, raw = line.partition(":")
        if label in ("MemAvailable", "SwapFree"):
            stats[label + "_mib"] = round(int(raw.split()[0]) / 1024, 2)
    thermal = Path("/sys/class/thermal/thermal_zone0/temp")
    if thermal.is_file():
        stats["temperature_c"] = round(int(thermal.read_text()) / 1000, 1)
    return stats


def _percentile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    index = (len(ordered) - 1) * quantile
    below = int(index)
    above = min(below + 1, len(ordered) - 1)
    return round(ordered[below] + (ordered[above] - ordered[below]) * (index - below), 3)


def run() -> dict[str, object]:
    """Measure local HMAC/read amplification plus 12 E3/Git writes."""
    before = _host_health()
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="odyssey-followup-probe-", dir="/tmp") as root:
        state, repo, writer = setup(Path(root), ["Ana trabaja como profesora."] * 12)
        original = campaign(state, repo, writer, segment_size=2)
        original.stage(campaign_id="all-people", type_id="person", property_id="profesion")
        sealed = run_to_end(original)[-1]
        assert sealed["finished"] and sealed["deferred"] == 12
        cid = semantic_followup_id("all-people")
        t0 = time.perf_counter()
        staged = original.stage_followup(
            campaign_id=cid,
            original_id="all-people",
            origin_kind="campaign",
            type_id="person",
            property_id="profesion",
        )
        stage_ms = (time.perf_counter() - t0) * 1000
        assert staged["pending"] == 2
        gateway = ProfessionGateway()
        interpreter = budgeted(original, gateway, cid=cid, cap=24)
        status_timings = []
        advance_timings = []
        for _ in range(35):
            t0 = time.perf_counter()
            original.status(cid)
            status_timings.append((time.perf_counter() - t0) * 1000)
            t0 = time.perf_counter()
            result = advance_campaign(original, cid, interpreter)
            advance_timings.append((time.perf_counter() - t0) * 1000)
            if result["finished"]:
                break
        assert result["finished"] and result["updated"] == 12 and result["total"] == 12
        assert result["deferred"] == 0 and gateway.calls == 24
        assert all(
            parse_note(repo.read_text(f"{idx}.md")).metadata["profesion"] == "profesora"
            for idx in range(12)
        )
        assert original.status("all-people") == sealed
        assert advance_campaign(campaign(state, repo, writer), cid, interpreter) == result
        assert gateway.calls == 24
    elapsed = round((time.perf_counter() - started) * 1000, 3)
    return {
        "kind": "odyssey_signed_semantic_followup_bounded_pi_probe",
        "sha": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "scope": {
            "notes": 12,
            "segment_size": 2,
            "original_deferred": 12,
            "followup_updated": 12,
            "fake_two_pass_calls": 24,
        },
        "stage_ms": round(stage_ms, 3),
        "status_ms": {
            "p50": _percentile(status_timings, 0.5),
            "p95": _percentile(status_timings, 0.95),
        },
        "advance_ms": {
            "p50": _percentile(advance_timings, 0.5),
            "p95": _percentile(advance_timings, 0.95),
        },
        "advances": len(advance_timings),
        "elapsed_ms": elapsed,
        "rss_peak_mib": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 2),
        "host_before": before,
        "host_after": _host_health(),
        "pass": True,
        "limits": "temporary Git+Markdown, fake provider, no DEV/PROD or real GPT; "
        "not 10k-note or sustained-load/mobile SLA",
    }


if __name__ == "__main__":
    print("ODYSSEY_FOLLOWUP_PI_PROBE=" + json.dumps(run(), ensure_ascii=False))
