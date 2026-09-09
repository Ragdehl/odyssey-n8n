"""Authorization-gated Luna-only runner using the corrected v2 evaluator."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any, Protocol, TextIO

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from benchmarks.luna_first_planner.evaluate_v2 import (  # noqa: E402
    EVALUATOR_VERSION,
    evaluate_result_v2,
    load_frozen_registry_v2,
)
from benchmarks.luna_first_planner.run_live import select_cases  # noqa: E402
from odyssey_core.experimental_luna_planning import (  # noqa: E402
    LUNA_EXPERIMENT_AUTOMATIC_RETRIES,
    LUNA_EXPERIMENT_MAX_OUTPUT_TOKENS,
    LUNA_EXPERIMENT_MODEL,
    LUNA_EXPERIMENT_REASONING_EFFORT,
    ExperimentalPlannerResult,
    OpenAILunaExperimentalPlanner,
)

OUTPUT_PATH = ROOT / "benchmarks" / ".live-results" / "luna-first-planner-v2.jsonl"
SCHEMA_PATH = ROOT / "config" / "note-schema.json"


class Planner(Protocol):
    """Describe the non-executing Luna planner state retained by this runner."""

    last_usage: dict[str, int] | None
    last_response_id: str | None
    last_provider_status: str | None

    def plan(self, request: str) -> ExperimentalPlannerResult:
        """Return one validated result without executing any action."""


def run_cases_v2(
    planner: Planner,
    cases: list[dict[str, str]],
    oracles: dict[str, dict[str, Any]],
    evidence: TextIO | None = None,
) -> list[dict[str, Any]]:
    """Attempt each selected corrected-contract case once and retain bounded evidence."""
    rows: list[dict[str, Any]] = []
    for case in cases:
        try:
            result = planner.plan(case["request"])
            evaluation = evaluate_result_v2(case["id"], result, oracles[case["id"]])
            row = {
                "case_id": case["id"],
                "evaluator_version": EVALUATOR_VERSION,
                "model": LUNA_EXPERIMENT_MODEL,
                "reasoning_effort": LUNA_EXPERIMENT_REASONING_EFFORT,
                "attempt_count": 1,
                "max_retries": LUNA_EXPERIMENT_AUTOMATIC_RETRIES,
                "max_output_tokens": LUNA_EXPERIMENT_MAX_OUTPUT_TOKENS,
                "classification": evaluation.classification.value,
                "findings": list(evaluation.findings),
                "semantic_review": list(evaluation.semantic_review),
                "result": asdict(result),
                "usage": planner.last_usage,
                "response_id": planner.last_response_id,
                "provider_status": planner.last_provider_status,
            }
            rows.append(row)
            if evidence is not None:
                evidence.write(json.dumps(row, ensure_ascii=False) + "\n")
                evidence.flush()
            if evaluation.classification.value in {
                "UNSAFE_NON_ESCALATION",
                "INVALID_FAIL_CLOSED",
            }:
                break
        except Exception as error:
            row = {
                "case_id": case["id"],
                "evaluator_version": EVALUATOR_VERSION,
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
            rows.append(row)
            if evidence is not None:
                evidence.write(json.dumps(row, ensure_ascii=False) + "\n")
                evidence.flush()
            break
    return rows


def reserve_evidence_path() -> TextIO:
    """Exclusively reserve the fixed evidence path before provider construction."""
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    return OUTPUT_PATH.open("x", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    """Run exactly one corrected Luna-only diagnostic with no fallback or execution path."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-live-provider-calls", action="store_true")
    parser.add_argument("--case-id", action="append", default=[])
    args = parser.parse_args(argv)
    if not args.confirm_live_provider_calls:
        raise SystemExit("Refusing live calls without --confirm-live-provider-calls")
    try:
        evidence = reserve_evidence_path()
    except FileExistsError as error:
        raise SystemExit(f"Refusing to overwrite existing evidence: {OUTPUT_PATH}") from error
    cases_payload, oracles = load_frozen_registry_v2()
    cases = select_cases(cases_payload["cases"], args.case_id)
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    try:
        planner = OpenAILunaExperimentalPlanner.from_environment(
            schema, cases_payload["fixed_context"]
        )
        run_cases_v2(planner, cases, oracles, evidence)
    finally:
        evidence.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
