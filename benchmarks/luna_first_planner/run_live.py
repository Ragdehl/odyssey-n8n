"""Authorization-gated Luna-only runner for frozen held-out planner cases."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any, Protocol

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from benchmarks.luna_first_planner.evaluate import (  # noqa: E402
    evaluate_result,
    load_frozen_registry,
)
from odyssey_core.experimental_luna_planning import (  # noqa: E402
    LUNA_EXPERIMENT_AUTOMATIC_RETRIES,
    LUNA_EXPERIMENT_MAX_OUTPUT_TOKENS,
    LUNA_EXPERIMENT_MODEL,
    LUNA_EXPERIMENT_REASONING_EFFORT,
    ExperimentalPlannerResult,
    OpenAILunaExperimentalPlanner,
)

OUTPUT_PATH = ROOT / "benchmarks" / ".live-results" / "luna-first-planner.jsonl"
SCHEMA_PATH = ROOT / "config" / "note-schema.json"


class Planner(Protocol):
    """Describe the non-executing Luna planner state retained by this runner."""

    last_usage: dict[str, int] | None
    last_response_id: str | None
    last_provider_status: str | None

    def plan(self, request: str) -> ExperimentalPlannerResult:
        """Return one validated planning result without executing any action."""


def run_cases(
    planner: Planner,
    cases: list[dict[str, str]],
    oracles: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Attempt each selected frozen case once and retain bounded diagnostic evidence."""
    rows: list[dict[str, Any]] = []
    for case in cases:
        try:
            result = planner.plan(case["request"])
            evaluation = evaluate_result(case["id"], result, oracles[case["id"]])
            rows.append(
                {
                    "case_id": case["id"],
                    "model": LUNA_EXPERIMENT_MODEL,
                    "reasoning_effort": LUNA_EXPERIMENT_REASONING_EFFORT,
                    "attempt_count": 1,
                    "max_retries": LUNA_EXPERIMENT_AUTOMATIC_RETRIES,
                    "max_output_tokens": LUNA_EXPERIMENT_MAX_OUTPUT_TOKENS,
                    "classification": evaluation.classification.value,
                    "findings": list(evaluation.findings),
                    "result": asdict(result),
                    "usage": planner.last_usage,
                    "response_id": planner.last_response_id,
                    "provider_status": planner.last_provider_status,
                }
            )
        except Exception as error:
            rows.append(
                {
                    "case_id": case["id"],
                    "model": LUNA_EXPERIMENT_MODEL,
                    "reasoning_effort": LUNA_EXPERIMENT_REASONING_EFFORT,
                    "attempt_count": 1,
                    "max_retries": LUNA_EXPERIMENT_AUTOMATIC_RETRIES,
                    "max_output_tokens": LUNA_EXPERIMENT_MAX_OUTPUT_TOKENS,
                    "classification": "INVALID_FAIL_CLOSED",
                    "error_category": type(error).__name__[:120],
                    "usage": planner.last_usage,
                    "response_id": planner.last_response_id,
                    "provider_status": planner.last_provider_status,
                }
            )
    return rows


def select_cases(cases: list[dict[str, str]], requested_ids: list[str]) -> list[dict[str, str]]:
    """Select only known frozen cases while preserving registry order."""
    if not requested_ids:
        return cases
    requested = set(requested_ids)
    known = {case["id"] for case in cases}
    unknown = requested - known
    if unknown:
        raise ValueError(f"Unknown frozen case IDs: {sorted(unknown)!r}")
    return [case for case in cases if case["id"] in requested]


def write_rows(rows: list[dict[str, Any]], output_path: Path = OUTPUT_PATH) -> None:
    """Write one immutable JSONL artifact and refuse to overwrite prior evidence."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("x", encoding="utf-8") as output:
        output.writelines(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse the explicit provider authorization and optional frozen subset."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-live-provider-calls", action="store_true")
    parser.add_argument("--case-id", action="append", default=[])
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Run a Luna-only diagnostic; never invoke Sol or execute returned actions."""
    args = parse_args(argv)
    if not args.confirm_live_provider_calls:
        raise SystemExit("Refusing live calls without --confirm-live-provider-calls")
    if OUTPUT_PATH.exists():
        raise SystemExit(f"Refusing to overwrite existing evidence: {OUTPUT_PATH}")
    cases_payload, oracles = load_frozen_registry()
    cases = select_cases(cases_payload["cases"], args.case_id)
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    planner = OpenAILunaExperimentalPlanner.from_environment(schema, cases_payload["fixed_context"])
    write_rows(run_cases(planner, cases, oracles))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
