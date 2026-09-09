"""Deterministic evaluator for the frozen prompt-parity atomicity benchmark."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from odyssey_core.request_planning import RequestPlan

ROOT = Path(__file__).resolve().parents[2]


def load_registry() -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """Load the frozen atomicity cases and structural oracle."""
    cases = json.loads((ROOT / "benchmarks/luna_first_planner/atomicity_cases.json").read_text())
    oracle = json.loads((ROOT / "benchmarks/luna_first_planner/atomicity_oracle.json").read_text())
    return cases, {item["id"]: item for item in oracle["oracles"]}


@dataclass(frozen=True, slots=True)
class AtomicityEvaluation:
    """Separate deterministic structural findings from bounded semantic review evidence."""

    safe_structure: bool
    findings: tuple[str, ...]
    semantic_review: tuple[str, ...]


def evaluate_atomicity(result: RequestPlan, oracle: dict[str, Any]) -> AtomicityEvaluation:
    """Check only structural boundaries; wording meaning is explicit human-review evidence."""
    units = [unit for action in result.actions if action.kind == "write" for unit in action.units]
    facts = [fact for unit in units for fact in unit.facts]
    findings: list[str] = []
    if len(units) != oracle["units"]:
        findings.append("unit_boundary")
    if len(facts) != oracle["facts"]:
        findings.append("coherence_boundary")
    review = tuple(f"meaning_review:{term}" for term in oracle.get("semantic_terms", []))
    return AtomicityEvaluation(not findings, tuple(findings), review)
