"""Deterministic evaluator for the frozen prompt-parity atomicity benchmark."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from odyssey_core.request_planning import RequestPlan

ROOT = Path(__file__).resolve().parents[2]


def load_registry() -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """Load the frozen atomicity cases and structural oracle."""
    cases = json.loads((ROOT / "benchmarks/luna_first_planner/atomicity_cases.json").read_text())
    oracle = json.loads((ROOT / "benchmarks/luna_first_planner/atomicity_oracle.json").read_text())
    return cases, {item["id"]: item for item in oracle["oracles"]}


def evaluate_atomicity(
    case_id: str, result: RequestPlan, oracle: dict[str, Any]
) -> tuple[bool, tuple[str, ...]]:
    """Check unit/fact boundaries and required semantic tokens without lexical exact matching."""
    units = [unit for action in result.actions if action.kind == "write" for unit in action.units]
    facts = [fact for unit in units for fact in unit.facts]
    findings: list[str] = []
    if len(units) != oracle["units"]:
        findings.append("unit_boundary")
    if len(facts) != oracle["facts"]:
        findings.append("coherence_boundary")
    text = " ".join(facts).casefold()
    for token in oracle["required"]:
        if token.casefold() not in text:
            findings.append(f"missing_meaning:{token}")
    return not findings, tuple(findings)
