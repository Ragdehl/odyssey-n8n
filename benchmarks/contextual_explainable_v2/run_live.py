"""Run the frozen GPT-6 explainable contextual gate after explicit authorization."""

from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from odyssey_core.contextual import (  # noqa: E402
    ContextualCandidate,
    ContextualResolutionRequest,
    OpenAIContextualReasoner,
    build_openai_payload,
    validate_contextual_decision,
)
from odyssey_core.contextual_calibration import (  # noqa: E402
    load_contextual_calibration_examples,
)

MODEL = "gpt-6-luna"
REASONING_EFFORT = "medium"
MAX_OUTPUT_TOKENS = 256
MAX_PROVIDER_CALLS = 6
MAX_COST_USD = Decimal("0.00")
GATE_CONSUMED = False
CASES_PATH = Path(__file__).with_name("cases.json")
MANIFEST_PATH = Path(__file__).with_name("manifest.json")
OUTPUT_PATH = ROOT / "benchmarks/.live-results/contextual-explainable-v2-gpt6-luna-medium.jsonl"
PRICING_PATH = Path(__file__).with_name("pricing_snapshot.json")


def load_cases() -> tuple[dict[str, Any], ...]:
    """Load exactly six frozen cases in deterministic order."""
    rows = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    if not isinstance(rows, list) or len(rows) != MAX_PROVIDER_CALLS:
        raise ValueError("Explainable contextual v2 gate requires exactly six cases")
    if len({row.get("id") for row in rows}) != len(rows):
        raise ValueError("Explainable contextual v2 case IDs must be unique")
    return tuple(rows)


def request_from_case(case: dict[str, Any]) -> ContextualResolutionRequest:
    """Remove oracle fields before constructing one provider request."""
    value = case["request"]
    return ContextualResolutionRequest(
        value["reference"],
        value["context"],
        value["entity_type"],
        tuple(ContextualCandidate(item["id"], item["evidence"]) for item in value["candidates"]),
    )


def conservative_cost_ceiling(cases: tuple[dict[str, Any], ...]) -> tuple[Decimal, int]:
    """Price a no-cache one-token-per-UTF-8-byte input bound plus bounded output."""
    examples = load_contextual_calibration_examples()
    pricing = json.loads(PRICING_PATH.read_text(encoding="utf-8"))
    if pricing.get("model") != MODEL:
        raise ValueError("Explainable v2 pricing snapshot model mismatch")
    input_tokens = 0
    for case in cases:
        payload = build_openai_payload(
            request_from_case(case),
            MODEL,
            reasoning_effort=REASONING_EFFORT,
            examples=examples,
            max_output_tokens=MAX_OUTPUT_TOKENS,
        )
        input_tokens += len(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
    cost = (
        Decimal(input_tokens) * Decimal(str(pricing["input_per_million"]))
        + Decimal(MAX_PROVIDER_CALLS * MAX_OUTPUT_TOKENS)
        * Decimal(str(pricing["output_per_million"]))
    ) / Decimal(1_000_000)
    return cost.quantize(Decimal("0.00000001")), input_tokens


def _passed(case: dict[str, Any], actual: dict[str, Any]) -> bool:
    """Score the frozen exact oracle or the one intentionally outcome-agnostic option oracle."""
    expected = case["expected"]
    if "outcomes" in expected:
        return (
            actual["outcome"] in expected["outcomes"]
            and actual["id"] == expected["id"]
            and actual["ambiguous_ids"] == expected["ambiguous_ids"]
        )
    return actual == expected


def _append_row(path: Path, row: dict[str, Any]) -> None:
    """Append immutable compact evidence without overwriting an earlier artifact."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def run_cases(cases: tuple[dict[str, Any], ...]) -> None:
    """Make one no-retry GPT-6 Luna/medium call per frozen case."""
    reasoner = OpenAIContextualReasoner(
        MODEL,
        reasoning_effort=REASONING_EFFORT,
        examples=load_contextual_calibration_examples(),
        max_output_tokens=MAX_OUTPUT_TOKENS,
    )
    for case in cases:
        request = request_from_case(case)
        raw, usage = reasoner.resolve(request)
        decision = validate_contextual_decision(raw, {item.id for item in request.candidates})
        actual = {
            "outcome": decision.outcome,
            "id": decision.id,
            "ambiguous_ids": list(decision.ambiguous_ids),
        }
        _append_row(
            OUTPUT_PATH,
            {
                "case_id": case["id"],
                "actual": actual,
                "expected": case["expected"],
                "passed": _passed(case, actual),
                "usage": usage,
            },
        )


def main(argv: list[str] | None = None) -> int:
    """Refuse before provider construction unless the frozen ceiling is explicitly authorized."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-live-provider-calls", action="store_true")
    args = parser.parse_args(argv)
    if GATE_CONSUMED:
        raise SystemExit("Refusing live calls: contextual-explainable-v2 is permanently consumed")
    cases = load_cases()
    ceiling, _input_tokens = conservative_cost_ceiling(cases)
    if not args.confirm_live_provider_calls or MAX_COST_USD < ceiling:
        raise SystemExit(f"Refusing live calls: explicit authorization of ${ceiling} is required")
    if OUTPUT_PATH.exists():
        raise SystemExit(f"Refusing to overwrite live artifact: {OUTPUT_PATH}")
    run_cases(cases)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
