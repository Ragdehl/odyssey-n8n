"""Run the authorized six-case Luna-only Slice 1 semantic-set planner gate once."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from time import perf_counter
from typing import Any, Protocol, TextIO

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from benchmarks.semantic_set_planner.gate import (  # noqa: E402
    MAX_PROVIDER_CALLS,
    conservative_preflight,
    evaluate_result,
    load_registry,
)
from odyssey_core.experimental_luna_planning import (  # noqa: E402
    ExperimentalPlannerResult,
    OpenAILunaExperimentalPlanner,
)

OUTPUT_PATH = ROOT / "benchmarks/.live-results/semantic-set-slice1-luna-gate-20260925.jsonl"
SCHEMA_PATH = ROOT / "config/note-schema.json"


class Planner(Protocol):
    """Describe only the validated Luna planner telemetry retained by the gate."""

    last_error_category: str | None
    last_error_chain: tuple[str, ...] | None
    last_input_sizes: dict[str, int] | None
    last_parse_status: str | None
    last_provider_status: str | None
    last_response_id: str | None
    last_usage: dict[str, int] | None
    last_validation_code: str | None
    last_validation_stage: str | None

    def plan(self, request: str) -> ExperimentalPlannerResult:
        """Return one locally validated non-executing planner result."""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Require an explicit live-provider confirmation flag."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-live-provider-calls", action="store_true")
    return parser.parse_args(argv)


def reserve_evidence_path(path: Path = OUTPUT_PATH) -> TextIO:
    """Reserve a new ignored JSONL evidence artifact before provider construction."""
    path.parent.mkdir(parents=True, exist_ok=True)
    return path.open("x", encoding="utf-8")


def run_cases(
    planner: Planner,
    cases: list[dict[str, str]],
    oracles: dict[str, dict[str, Any]],
    evidence: TextIO,
    *,
    evaluator=evaluate_result,
    case_evaluator: Callable[[str, ExperimentalPlannerResult, dict[str, Any]], Any] | None = None,
    continue_on_safe_fail: bool = False,
) -> list[dict[str, Any]]:
    """Make one Luna call per case, optionally continuing after oracle-only failures."""
    rows: list[dict[str, Any]] = []
    for case in cases:
        started = perf_counter()
        try:
            result = planner.plan(case["request"])
        except Exception as error:
            row = _row(
                case["id"],
                "FAIL_CLOSED",
                [f"provider_or_local_error:{type(error).__name__[:120]}"],
                planner,
                duration_ms=(perf_counter() - started) * 1000,
            )
            rows.append(row)
            _write_row(evidence, row)
            break
        evaluation = (
            case_evaluator(case["id"], result, oracles[case["id"]])
            if case_evaluator is not None
            else evaluator(result, oracles[case["id"]])
        )
        row = _row(
            case["id"],
            evaluation.classification,
            list(evaluation.findings),
            planner,
            result=asdict(result),
            duration_ms=(perf_counter() - started) * 1000,
        )
        rows.append(row)
        _write_row(evidence, row)
        if evaluation.classification != "PASS" and not (
            continue_on_safe_fail and evaluation.classification == "FAIL"
        ):
            break
    return rows


def _row(
    case_id: str,
    classification: str,
    findings: list[str],
    planner: Planner,
    *,
    result: dict[str, Any] | None = None,
    duration_ms: float,
) -> dict[str, Any]:
    """Build one bounded evidence row without provider prompt or hidden reasoning."""
    return {
        "case_id": case_id,
        "classification": classification,
        "findings": findings,
        "validated_result": result,
        "model": "gpt-5.6-luna",
        "reasoning_effort": "low",
        "max_retries": 0,
        "usage": planner.last_usage,
        "duration_ms": round(duration_ms, 3),
        "response_id": planner.last_response_id,
        "provider_status": planner.last_provider_status,
        "validation_stage": planner.last_validation_stage,
        "validation_code": planner.last_validation_code,
        "parse_status": planner.last_parse_status,
        "error_category": planner.last_error_category,
        "error_chain": getattr(planner, "last_error_chain", None),
        "input_sizes": planner.last_input_sizes,
    }


def _write_row(evidence: TextIO, row: dict[str, Any]) -> None:
    """Flush each outcome so a first failure leaves durable bounded evidence."""
    evidence.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    evidence.flush()


def main(argv: list[str] | None = None) -> int:
    """Preflight and run one authorized Luna-only planner gate with no execution capability."""
    args = parse_args(argv)
    cases_payload, oracles = load_registry()
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    details = conservative_preflight(schema, cases_payload)
    print(json.dumps(details, ensure_ascii=False, sort_keys=True))
    if (
        not args.confirm_live_provider_calls
        or not os.environ.get("OPENAI_API_KEY")
        or OUTPUT_PATH.exists()
        or len(cases_payload["cases"]) != MAX_PROVIDER_CALLS
    ):
        raise SystemExit("Live semantic-set gate preflight refused")
    evidence = reserve_evidence_path()
    try:
        planner = OpenAILunaExperimentalPlanner.from_environment(
            schema, cases_payload["fixed_context"]
        )
        rows = run_cases(planner, cases_payload["cases"], oracles, evidence)
    finally:
        evidence.close()
    return (
        0
        if len(rows) == MAX_PROVIDER_CALLS and all(row["classification"] == "PASS" for row in rows)
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
