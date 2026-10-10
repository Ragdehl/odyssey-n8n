"""Export four production-shaped synthetic Router calls for manual Playground use.

Offline-only exporter: no API client, credentials, network, vault or writes.
It emits data from existing fake-client request capture, never executes a call.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .check import audit, captured_requests

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "benchmarks/fact_candidate_v2_preflight/playground_router_requests.json"
EXPECTED = ("F09", "F10", "F14", "F27")


def export() -> dict[str, Any]:
    """Return exact synthetic Router request envelopes and safety limitations."""
    preflight = audit()
    if not preflight["first_wave"]["fits_ceiling"]:
        raise ValueError("Frozen conservative Router/Temporal envelope exceeds authorization")
    cases = {
        case_id: payload for case_id, stage, payload in captured_requests() if stage == "router"
    }
    if set(cases) != set(EXPECTED):
        raise ValueError("Frozen four-case set changed")
    for request in cases.values():
        if (
            request.get("store") is not False
            or request.get("model") != "gpt-6-luna"
            or request.get("reasoning") != {"effort": "low"}
            or request.get("max_output_tokens") != 4096
            or request.get("text", {}).get("format", {}).get("strict") is not True
            or len(request.get("input", [])) != 2
        ):
            raise ValueError("Production-like Router request contract changed")
    return {
        "mode": "MANUAL_PLAYGROUND_EXPORT_ONLY",
        "executes_provider": False,
        "validated_model_equivalence": False,
        "note": (
            "For user-operated official Playground, not ChatGPT-hosted tool execution. "
            "Use ONLY if exact gpt-6-luna, low reasoning, and strict structured JSON "
            "configuration are supported by the Playground; otherwise model parity is "
            "UNVERIFIED. Manual outputs still require independent semantic review. "
            "Do not use personal vault data or paste API credentials."
        ),
        "authorized_all_six_router_temporal_upper_usd": preflight["first_wave"]["upper_usd"],
        "calls": [{"id": case_id, "request": cases[case_id]} for case_id in EXPECTED],
        "result_shape_for_offline_comparison": {
            case_id: "Paste only the JSON object returned by Router for this case"
            for case_id in EXPECTED
        },
    }


def main() -> int:
    """Materialize deterministic synthetic Playground input without provider usage."""
    bundle = export()
    OUTPUT.write_text(json.dumps(bundle, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"OFFLINE ONLY: exported {len(bundle['calls'])} synthetic Router inputs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
