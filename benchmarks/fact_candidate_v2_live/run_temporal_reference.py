"""One reviewed synthetic Temporal test for a source-relative clock reference.

Uses Odyssey's unchanged Temporal GPT-6 prompt and schema. No identity or
write effects; cannot run twice or exceed prior authorized cumulative limit.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from benchmarks.fact_candidate_v2_live import run_remaining
from odyssey_apps.fact_candidates import validate_fact_candidate_proposal
from odyssey_apps.fact_temporal import bind_temporal_to_fact_candidates
from odyssey_core.temporal_interpretation import OpenAITemporalInterpreter
from tests.apps.test_fact_candidates import CASES
from tests.runtime.test_fact_candidate_planning_vertical import _sdk_fake

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
PIN = HERE / "reviewed_f08_temporal_request.json"
RECEIPT = HERE / "observed_f08_temporal.json"
MODEL = "gpt-6-luna"
APPROVED_CUMULATIVE_USD = 0.07
PREVIOUS_OBSERVED_USD = 0.0337352
FLAG = "ODYSSEY_TEMPORAL_REFERENCE_LIVE_APPROVED"
CLOCK = {"date": "2026-10-09", "time": "13:15", "timezone": "Europe/Paris"}


def original():
    """Recover exact fixed original and REAL Router GPT-6 F08 source roles."""
    case = next(x for x in CASES if x["id"] == "F08")
    file = next(run_remaining.RESULTS.glob("*--F08.json"))
    original = json.loads(file.read_text())
    if original["provider_status"] != "completed":
        raise ValueError("Router F08 provider evidence did not complete")
    proposal = validate_fact_candidate_proposal(
        case["source"], json.loads(original["raw_model_response"])
    )
    return case["source"], proposal


def request():
    """Capture the actual Temporal provider request using a fake SDK response."""
    source, _ = original()
    fake, calls = _sdk_fake(
        {
            "mentions": [
                {
                    "temporal_text": "Mañana",
                    "temporal": {
                        "kind": "EXACT_DATE",
                        "exact_date": "2026-10-10",
                        "exact_datetime": None,
                        "range_start": None,
                        "range_end_exclusive": None,
                    },
                }
            ]
        }
    )
    OpenAITemporalInterpreter(fake, CLOCK).interpret(source)
    if len(calls) != 1:
        raise ValueError("Temporal request cardinality changed")
    return calls[0]


def preflight():
    """Require frozen provider input, no old result, and full cost reservation."""
    payload = request()
    frozen = json.loads(PIN.read_text(encoding="utf-8"))
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()
    if (
        frozen.get("sha256") != hashlib.sha256(encoded).hexdigest()
        or frozen.get("bytes") != len(encoded)
        or payload["model"] != MODEL
        or payload["reasoning"] != {"effort": "low"}
        or payload["store"] is not False
        or payload["max_output_tokens"] != 512
        or payload["text"]["format"]["strict"] is not True
        or payload["input"][1]["content"] != original()[0]
    ):
        raise ValueError("Changed Temporal request is not approved")
    if RECEIPT.exists():
        raise ValueError("A Temporal provider attempt already exists; no retry")
    rates = json.loads((ROOT / "config/runtime-pricing-snapshot.json").read_text())["models"][MODEL]
    n = len(json.dumps(payload, ensure_ascii=False, default=str).encode())
    worst = (
        (2 * n + 200) * max(rates["input_per_million"], rates.get("cache_write_per_million", 0))
        + payload["max_output_tokens"] * rates["output_per_million"]
    ) / 1_000_000
    if worst + PREVIOUS_OBSERVED_USD > APPROVED_CUMULATIVE_USD:
        raise ValueError("Cumulative approved test budget exceeded")
    return payload, round(worst, 8)


def run(*, live: bool = False, client: Any = None):
    """Make at most one provider call; capture genuine parsed Temporal evidence."""
    payload, reserved = preflight()
    data = {
        "case": "F08",
        "mode": "REAL_TEMPORAL_SINGLE_SHOT" if live else "DRY_RUN_NO_PROVIDER",
        "model": MODEL,
        "estimated_previous_usd": PREVIOUS_OBSERVED_USD,
        "reserved_max_usd": reserved,
        "approved_cumulative_usd": APPROVED_CUMULATIVE_USD,
        "may_write_notes": False,
    }
    if not live:
        return data
    if os.getenv(FLAG) != "1":
        raise ValueError("Temporal live flag required")
    if client is None:
        from openai import OpenAI

        client = OpenAI(max_retries=0, timeout=50)
    try:
        response = client.responses.create(**payload)
        u = getattr(response, "usage", None)
        data.update(
            {
                "provider_status": getattr(response, "status", "unknown"),
                "raw_output": getattr(response, "output_text", ""),
                "usage": {
                    "input_tokens": getattr(u, "input_tokens", None),
                    "output_tokens": getattr(u, "output_tokens", None),
                },
            }
        )
        if data["provider_status"] == "completed":
            # Reparse through Odyssey's *unchanged* Temporal input validator.
            fake, _ = _sdk_fake(json.loads(data["raw_output"]))
            source, proposal = original()
            interpretation = OpenAITemporalInterpreter(fake, CLOCK).interpret(source)
            edges = bind_temporal_to_fact_candidates(proposal, interpretation)
            data["validation"] = "grounded"
            data["bindings"] = [
                {
                    "candidate_id": e.candidate_id,
                    "role": e.role,
                    "source": e.source.text,
                    "status": e.status,
                    "resolution_kind": (
                        e.resolution.kind.value if e.resolution is not None else None
                    ),
                    "value": (
                        e.resolution.exact_datetime or e.resolution.exact_date
                        if e.resolution is not None
                        else None
                    ),
                    "exact_shape": e.has_exact_source_shape,
                }
                for e in edges
            ]
        else:
            data["validation"] = "incomplete"
    except Exception as error:
        data["validation"] = "failed"
        data["error_type"] = type(error).__name__
    with RECEIPT.open("x", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
    return data


if __name__ == "__main__":
    output = run(live=os.getenv(FLAG) == "1")
    print(json.dumps({k: v for k, v in output.items() if k != "raw_output"}, ensure_ascii=False))
    if output.get("validation") == "failed":
        raise SystemExit(1)
