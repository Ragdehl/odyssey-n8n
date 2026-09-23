"""Frozen structural oracle for the focused production relational planner gate."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from odyssey_core.request_planning import PlannerClarification, PlannerResult, RequestPlan

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = Path(__file__).with_name("cases.json")
ORACLE = Path(__file__).with_name("oracle.json")
MANIFEST = Path(__file__).with_name("manifest.json")
VERSION = "1.0.0"
_UUID = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I)


@dataclass(frozen=True, slots=True)
class Evaluation:
    """Keep a bounded structural verdict separate from the validated planner result."""

    classification: str
    findings: tuple[str, ...]
    semantic_review: tuple[str, ...] = ()


def load_frozen_registry() -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """Verify exact frozen inputs and case alignment before any provider construction."""
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if (
        manifest.get("version") != VERSION
        or manifest.get("frozen_before_provider_calls") is not True
    ):
        raise ValueError("Relational gate manifest is invalid")
    for relative, expected in manifest.get("sha256", {}).items():
        if hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() != expected:
            raise ValueError(f"Relational gate input drifted: {relative}")
    cases = json.loads(REGISTRY.read_text(encoding="utf-8"))
    oracles = json.loads(ORACLE.read_text(encoding="utf-8"))
    case_ids = [item["id"] for item in cases["cases"]]
    oracle_ids = [item["id"] for item in oracles["oracles"]]
    if (
        cases.get("version") != VERSION
        or oracles.get("version") != VERSION
        or case_ids != oracle_ids
        or len(set(case_ids)) != len(case_ids)
        or not 1 <= len(case_ids) <= 12
    ):
        raise ValueError("Relational gate registries are invalid")
    return cases, {item["id"]: item for item in oracles["oracles"]}


def evaluate_result(result: PlannerResult, oracle: dict[str, Any]) -> Evaluation:
    """Check identity, cardinality, action, and fact structure without exact prose matching."""
    if isinstance(result, PlannerClarification):
        return Evaluation(
            "PASS" if oracle.get("allow_clarification") else "FAIL_CLOSED",
            () if oracle.get("allow_clarification") else ("unexpected_clarification",),
        )
    if not isinstance(result, RequestPlan):
        return Evaluation("FAIL", ("invalid_planner_result",))
    findings: list[str] = []
    semantic_review: list[str] = []
    if len(result.actions) != 1 or result.actions[0].kind != oracle["action"]:
        return Evaluation("FAIL", ("action_shape",))
    if _UUID.search(json.dumps(asdict(result), ensure_ascii=False)) or ".md" in json.dumps(
        asdict(result), ensure_ascii=False
    ):
        findings.append("planner_asserted_physical_identity")
    action = result.actions[0]
    if action.kind == "retrieve":
        selections = [action.plan]
        units: list[Any] = []
    else:
        units = list(action.units)
        selections = [unit.target for unit in units]
    if "relation" in oracle:
        if len(selections) != 1:
            findings.append("extra_relational_units")
        else:
            selection = selections[0]
            relation = selection.relational_reference
            if relation is None:
                findings.append("missing_relational_intent")
            else:
                if relation.members != oracle["relation"]:
                    findings.append("wrong_member_cardinality")
                if relation.source_kind != oracle["source_kind"]:
                    findings.append("wrong_source_kind")
                if not _has_terms(relation.reference, oracle.get("reference_terms", [])):
                    findings.append("lost_reference_wording")
                if not _has_terms(relation.source_query or "", oracle.get("source_terms", [])):
                    findings.append("lost_source_intent")
                if relation.source_kind == "existing" and not oracle.get("source_terms"):
                    semantic_review.append("source_selector_review")
            if selection.entity is not None or selection.self_target is not None:
                findings.append("relational_identity_asserted_as_direct")
        if units and (len(units) != 1 or units[0].cardinality != "one" or units[0].references):
            findings.append("relational_write_shape")
    else:
        if any(selection.relational_reference is not None for selection in selections):
            findings.append("ordinary_target_became_relational")
        if oracle.get("ordinary") and (
            len(units) != 1 or not _has_terms(units[0].target.query, oracle["target_terms"])
        ):
            findings.append("named_target_lost")
        if oracle.get("self") and (len(units) != 1 or units[0].target.self_target != "self"):
            findings.append("self_target_lost")
        if oracle.get("all_matching") and (
            len(units) != 1 or units[0].cardinality != "all_matching"
        ):
            findings.append("all_matching_lost")
        if oracle.get("named_reference"):
            marta_indices = [
                index
                for index, unit in enumerate(units)
                if _has_terms(unit.target.query, ["marta"])
            ]
            airbus_indices = [
                index
                for index, unit in enumerate(units)
                if _has_terms(unit.target.query, oracle["reference_terms"])
            ]
            if len(units) != 2 or len(marta_indices) != 1 or len(airbus_indices) != 1:
                findings.append("named_reference_units")
            elif not any(
                _has_terms(ref.mention, oracle["reference_terms"])
                and ref.target_index == airbus_indices[0]
                for ref in units[marta_indices[0]].references
            ):
                findings.append("named_reference_binding_lost")
        if oracle.get("atomicity") and (
            len([unit for unit in units if unit.facts]) != 1
            or len(next((unit.facts for unit in units if unit.facts), ())) != 2
        ):
            findings.append("atomic_facts_not_split")
    if units:
        facts = " ".join(fact for unit in units for fact in unit.facts)
        mentions = " ".join(ref.mention for unit in units for ref in unit.references)
        if not _has_terms(f"{facts} {mentions}", oracle.get("fact_terms", [])):
            findings.append("requested_fact_lost")
        if oracle.get("all_matching") and not _has_terms(
            " ".join(change.value for unit in units for change in unit.tag_changes),
            oracle.get("tag_terms", []),
        ):
            findings.append("requested_tag_lost")
    return Evaluation(
        "FAIL" if findings else "PASS", tuple(findings[:8]), tuple(semantic_review[:4])
    )


def _has_terms(text: str, terms: list[str]) -> bool:
    """Use only broad semantic anchors; harmless wording remains for human review."""
    folded = text.casefold()
    return all(term.casefold() in folded for term in terms)
