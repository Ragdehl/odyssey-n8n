"""Authorization and cost-gated production Luna-first relational planner run."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path
from typing import Any, TextIO

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from benchmarks.reference_relationship_v1.evaluate import (  # noqa: E402
    VERSION,
    evaluate_result,
    load_frozen_registry,
)
from odyssey_core.cost_aware_planning import LunaFirstRequestPlanner  # noqa: E402
from odyssey_core.experimental_luna_planning import (  # noqa: E402
    LUNA_EXPERIMENT_MAX_OUTPUT_TOKENS,
    LUNA_EXPERIMENT_MODEL,
    luna_experimental_result_json_schema,
    render_luna_experimental_prompt,
)
from odyssey_core.request_planning import (  # noqa: E402
    PLANNER_MAX_OUTPUT_TOKENS,
    PLANNER_MODEL,
    planner_result_json_schema,
    render_request_planner_prompt,
)

OUTPUT_PATH = ROOT / "benchmarks" / ".live-results" / "reference-relationship-v1.jsonl"
SCHEMA_PATH = ROOT / "config" / "note-schema.json"
PRICING_PATH = ROOT / "benchmarks" / "performance_p1" / "pricing_snapshot.json"
MAX_COST_USD = Decimal("0.46")
INPUT_OVERHEAD_BYTES = 1024


def conservative_cost_ceiling(
    cases: list[dict[str, Any]], context: dict[str, str], schema: dict[str, Any]
) -> tuple[Decimal, int, int]:
    """Price all possible Luna attempts and one possible Sol fallback with no cache.

    UTF-8 byte count plus fixed envelope allowance bounds ordinary text-token input without
    relying on caching or observed average usage. Both production Structured Outputs schemas and
    inherited prompts are counted at their higher case input bound. The runner stops immediately
    after flushing its first Sol fallback row, so one Sol attempt is the hard maximum.
    """
    pricing = json.loads(PRICING_PATH.read_text(encoding="utf-8"))["models"]
    max_luna_bytes = 0
    max_sol_bytes = 0
    luna_schema = json.dumps(luna_experimental_result_json_schema(schema), ensure_ascii=False)
    sol_schema = json.dumps(planner_result_json_schema(schema), ensure_ascii=False)
    for case in cases:
        conversation = tuple(case.get("conversation_context", ()))
        request = case["request"]
        luna_text = render_luna_experimental_prompt(
            schema, context, conversation_context=conversation
        )
        sol_text = render_request_planner_prompt(schema, context, conversation)
        max_luna_bytes = max(
            max_luna_bytes,
            len((luna_text + luna_schema + request).encode("utf-8")),
        )
        max_sol_bytes = max(
            max_sol_bytes,
            len((sol_text + sol_schema + request).encode("utf-8")),
        )
    luna_input = max_luna_bytes + INPUT_OVERHEAD_BYTES
    sol_input = max_sol_bytes + INPUT_OVERHEAD_BYTES
    luna = pricing[LUNA_EXPERIMENT_MODEL]
    sol = pricing[PLANNER_MODEL]
    luna_attempt_cost = Decimal(luna_input) * Decimal(str(luna["input_per_million"])) + Decimal(
        LUNA_EXPERIMENT_MAX_OUTPUT_TOKENS
    ) * Decimal(str(luna["output_per_million"]))
    sol_attempt_cost = Decimal(sol_input) * Decimal(str(sol["input_per_million"])) + Decimal(
        PLANNER_MAX_OUTPUT_TOKENS
    ) * Decimal(str(sol["output_per_million"]))
    cost = (Decimal(len(cases)) * luna_attempt_cost + sol_attempt_cost) / Decimal(1_000_000)
    return cost, luna_input, sol_input


def run_cases(
    planner: LunaFirstRequestPlanner,
    cases: list[dict[str, Any]],
    oracles: dict[str, dict[str, Any]],
    evidence: TextIO,
) -> list[dict[str, Any]]:
    """Attempt frozen cases once, stopping after unsafe output or the first Sol fallback."""
    rows: list[dict[str, Any]] = []
    for case in cases:
        try:
            result = planner.plan(case["request"], tuple(case.get("conversation_context", ())))
            evaluation = evaluate_result(result, oracles[case["id"]])
            row = {
                "case_id": case["id"],
                "evaluator_version": VERSION,
                "classification": evaluation.classification,
                "findings": list(evaluation.findings),
                "semantic_review": list(evaluation.semantic_review),
                "result": asdict(result),
                "attempts": _attempts(planner),
                "fallback": planner.last_attempt_count == 2,
                "final_provider": ("sol" if planner.last_attempt_count == 2 else "luna"),
            }
        except Exception as error:
            row = {
                "case_id": case["id"],
                "evaluator_version": VERSION,
                "classification": "FAIL_CLOSED",
                "findings": [type(error).__name__[:80]],
                "attempts": _attempts(planner),
                "fallback": planner.last_attempt_count == 2,
            }
        rows.append(row)
        evidence.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
        evidence.flush()
        if row["classification"] in {"FAIL", "FAIL_CLOSED"} or row["fallback"]:
            break
    return rows


def _attempts(planner: LunaFirstRequestPlanner) -> list[dict[str, Any]]:
    """Retain only bounded provider usage and local validation diagnostics."""
    return [
        {
            "name": call.name,
            "model": call.model,
            "outcome": call.outcome.value,
            "usage": call.usage,
            "duration_ms": call.duration_ms,
            "validation_stage": call.validation_stage,
            "validation_code": call.validation_code,
            "error_category": call.error_category,
        }
        for call in planner.last_provider_calls
    ]


def main(argv: list[str] | None = None) -> int:
    """Refuse unapproved or over-ceiling execution before constructing a provider client."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-live-provider-calls", action="store_true")
    args = parser.parse_args(argv)
    registry, oracles = load_frozen_registry()
    cases = registry["cases"]
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    cost, luna_input, sol_input = conservative_cost_ceiling(
        cases, registry["fixed_context"], schema
    )
    print(
        f"logical_cases={len(cases)} provider_call_ceiling={len(cases) + 1} "
        f"no_cache_max_usd={cost:.6f} luna_input_bound={luna_input} "
        f"sol_input_bound={sol_input}"
    )
    if not args.confirm_live_provider_calls:
        raise SystemExit("Refusing live calls without --confirm-live-provider-calls")
    if cost > MAX_COST_USD:
        raise SystemExit("Refusing live calls: conservative ceiling exceeds $0.15")
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        evidence = OUTPUT_PATH.open("x", encoding="utf-8")
    except FileExistsError as error:
        raise SystemExit(f"Refusing to overwrite existing evidence: {OUTPUT_PATH}") from error
    try:
        planner = LunaFirstRequestPlanner.from_environment(schema, registry["fixed_context"])
        run_cases(planner, cases, oracles, evidence)
    finally:
        evidence.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
