"""Authorization-gated runner for the five never-attempted Luna cases."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from benchmarks.luna_first_planner.evaluate_v2 import load_frozen_registry_v2  # noqa: E402
from benchmarks.luna_first_planner.run_live import select_cases  # noqa: E402
from benchmarks.luna_first_planner.run_live_v2 import (  # noqa: E402
    SCHEMA_PATH,
    OpenAILunaExperimentalPlanner,
    run_cases_v2,
)

CONTINUATION_CASE_IDS = ("SM02", "SC02", "SE02", "SA01", "SA02")
OUTPUT_PATH = ROOT / "benchmarks" / ".live-results" / "luna-first-planner-v2-continuation.jsonl"


def main(argv: list[str] | None = None) -> int:
    """Run exactly the closed continuation set after reserving its evidence path."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-live-provider-calls", action="store_true")
    args = parser.parse_args(argv)
    if not args.confirm_live_provider_calls:
        raise SystemExit("Refusing live calls without --confirm-live-provider-calls")
    cases_payload, oracles = load_frozen_registry_v2()
    cases = select_cases(cases_payload["cases"], list(CONTINUATION_CASE_IDS))
    if {case["id"] for case in cases} != set(CONTINUATION_CASE_IDS):
        raise SystemExit("Continuation case registry does not match the closed set")
    with reserve_evidence_path_at(OUTPUT_PATH) as evidence:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        planner = OpenAILunaExperimentalPlanner.from_environment(
            schema, cases_payload["fixed_context"]
        )
        run_cases_v2(planner, cases, oracles, evidence)
    return 0


def reserve_evidence_path_at(path: Path):
    """Reserve a continuation path while reusing the hardened streaming runner."""
    path.parent.mkdir(parents=True, exist_ok=True)
    return _ReservedPath(path.open("x", encoding="utf-8"))


class _ReservedPath:
    """Context manager for one exclusively reserved evidence stream."""

    def __init__(self, stream):
        self.stream = stream

    def __enter__(self):
        return self.stream

    def __exit__(self, exc_type, exc, traceback):
        self.stream.close()
        return False


if __name__ == "__main__":
    raise SystemExit(main())
