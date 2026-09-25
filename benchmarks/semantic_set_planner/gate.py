"""Frozen, planner-only semantic-set gate with deterministic cost and safety checks."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from odyssey_core.experimental_luna_planning import (
    LUNA_EXPERIMENT_AUTOMATIC_RETRIES,
    LUNA_EXPERIMENT_MAX_OUTPUT_TOKENS,
    LUNA_EXPERIMENT_MODEL,
    LUNA_EXPERIMENT_REASONING_EFFORT,
    ExperimentalPlannerResult,
    PlannerEscalation,
    luna_experimental_result_json_schema,
    render_luna_experimental_prompt,
)
from odyssey_core.request_planning import PlannerClarification, RequestPlan, RetrieveAction

ROOT = Path(__file__).resolve().parents[2]
CASES_PATH = Path(__file__).with_name("cases.json")
ORACLE_PATH = Path(__file__).with_name("oracle.json")
PRICING_PATH = ROOT / "benchmarks" / "phase20_answerer" / "pricing_snapshot.json"

LOGICAL_CASE_COUNT = 6
MAX_PROVIDER_CALLS = 6
MAX_LUNA_INPUT_TOKENS = 70_000
MAX_COST_USD = Decimal("0.10")

_UNSAFE_PLANNER_AUTHORITY = re.compile(
    r"(?:\[\[|\.md\b|[\\/]|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class Evaluation:
    """Return the closed classification and bounded structural findings for one case."""

    classification: str
    findings: tuple[str, ...] = ()


def load_registry(
    cases_path: Path = CASES_PATH, oracle_path: Path = ORACLE_PATH
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """Load exactly six frozen case/oracle pairs before any provider client is created."""
    cases_payload = json.loads(cases_path.read_text(encoding="utf-8"))
    oracle_payload = json.loads(oracle_path.read_text(encoding="utf-8"))
    if (
        set(cases_payload) != {"version", "frozen_before_provider_calls", "fixed_context", "cases"}
        or set(oracle_payload) != {"version", "frozen_before_provider_calls", "oracles"}
        or cases_payload["version"] != oracle_payload["version"]
        or cases_payload["frozen_before_provider_calls"] is not True
        or oracle_payload["frozen_before_provider_calls"] is not True
        or not isinstance(cases_payload["cases"], list)
        or not isinstance(oracle_payload["oracles"], list)
    ):
        raise ValueError("Semantic-set gate registry is invalid")
    cases = cases_payload["cases"]
    oracles = oracle_payload["oracles"]
    case_ids = [item.get("id") for item in cases if isinstance(item, dict)]
    oracle_ids = [item.get("id") for item in oracles if isinstance(item, dict)]
    if (
        len(cases) != LOGICAL_CASE_COUNT
        or len(oracles) != LOGICAL_CASE_COUNT
        or case_ids != oracle_ids
        or len(set(case_ids)) != LOGICAL_CASE_COUNT
        or not all(
            set(case) == {"id", "request"}
            and all(isinstance(case[field], str) and case[field].strip() for field in case)
            for case in cases
        )
        or not all(isinstance(oracle, dict) and set(oracle) >= {"id", "kind"} for oracle in oracles)
    ):
        raise ValueError("Semantic-set gate must contain six aligned frozen cases")
    return cases_payload, {oracle["id"]: oracle for oracle in oracles}


def conservative_preflight(
    schema: Mapping[str, Any],
    cases_payload: Mapping[str, Any],
    *,
    teaching_examples: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Calculate a no-cache Luna-only ceiling from the checked-in pricing snapshot."""
    if (
        LUNA_EXPERIMENT_MODEL != "gpt-5.6-luna"
        or LUNA_EXPERIMENT_REASONING_EFFORT != "low"
        or LUNA_EXPERIMENT_AUTOMATIC_RETRIES != 0
        or MAX_PROVIDER_CALLS != LOGICAL_CASE_COUNT
    ):
        raise ValueError("Semantic-set gate provider configuration is unsafe")
    prompt = render_luna_experimental_prompt(
        schema, cases_payload["fixed_context"], teaching_examples=teaching_examples
    )
    output_schema = luna_experimental_result_json_schema(schema)
    serialized_request_bytes = max(
        len(prompt.encode("utf-8"))
        + len(json.dumps(output_schema, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
        + len(case["request"].encode("utf-8"))
        for case in cases_payload["cases"]
    )
    if serialized_request_bytes > MAX_LUNA_INPUT_TOKENS:
        raise ValueError("Serialized planner input exceeds the reviewed Luna token bound")
    pricing = json.loads(PRICING_PATH.read_text(encoding="utf-8"))
    rates = pricing.get("models", {}).get(LUNA_EXPERIMENT_MODEL)
    if not isinstance(rates, dict):
        raise ValueError("Checked-in pricing snapshot has no Luna rates")
    input_rate = Decimal(str(rates["input_per_million"]))
    output_rate = Decimal(str(rates["output_per_million"]))
    ceiling = (
        Decimal(MAX_PROVIDER_CALLS)
        * (
            Decimal(MAX_LUNA_INPUT_TOKENS) * input_rate
            + Decimal(LUNA_EXPERIMENT_MAX_OUTPUT_TOKENS) * output_rate
        )
        / Decimal(1_000_000)
    )
    if ceiling > MAX_COST_USD:
        raise ValueError("Conservative Luna no-cache ceiling exceeds authorization")
    return {
        "logical_cases": LOGICAL_CASE_COUNT,
        "maximum_provider_calls": MAX_PROVIDER_CALLS,
        "luna_model": LUNA_EXPERIMENT_MODEL,
        "reasoning_effort": LUNA_EXPERIMENT_REASONING_EFFORT,
        "retries": LUNA_EXPERIMENT_AUTOMATIC_RETRIES,
        "maximum_luna_input_bound": MAX_LUNA_INPUT_TOKENS,
        "maximum_output_tokens": LUNA_EXPERIMENT_MAX_OUTPUT_TOKENS,
        "serialized_request_bytes": serialized_request_bytes,
        "conservative_no_cache_maximum_usd": str(ceiling),
        "pricing_basis": pricing.get("as_of"),
    }


def evaluate_result(result: ExperimentalPlannerResult, oracle: Mapping[str, Any]) -> Evaluation:
    """Check a locally validated result without execution or a model-as-judge."""
    if isinstance(result, (PlannerEscalation, PlannerClarification)):
        return Evaluation("FAIL", ("unexpected_non_plan_outcome",))
    if not isinstance(result, RequestPlan):
        return Evaluation("FAIL_CLOSED", ("unknown_validated_result",))
    if len(result.actions) != 1 or not isinstance(result.actions[0], RetrieveAction):
        return Evaluation("FAIL", ("wrong_action_kind_or_count",))
    if _has_unsafe_authority(result):
        return Evaluation("FAIL", ("unsafe_planner_authority",))
    selection = result.actions[0].plan
    kind = oracle["kind"]
    if kind == "semantic_set":
        return _evaluate_semantic_set(selection, oracle)
    if kind == "singular_relational":
        if selection.semantic_set is not None:
            return Evaluation("FAIL", ("semantic_set_on_relational_regression",))
        relational = selection.relational_reference
        if (
            relational is None
            or relational.source_kind != "self"
            or relational.members != "one"
            or not _contains_any(relational.reference, oracle["reference_terms"])
        ):
            return Evaluation("FAIL", ("singular_relational_contract_missing",))
        return Evaluation("PASS")
    if kind == "ordinary_named":
        if selection.semantic_set is not None:
            return Evaluation("FAIL", ("semantic_set_on_named_regression",))
        if selection.relational_reference is not None:
            return Evaluation("FAIL", ("relational_reference_on_named_regression",))
        if not _contains_all_sets(selection.query, oracle["query_term_sets"]):
            return Evaluation("FAIL", ("ordinary_named_query_dropped",))
        return Evaluation("PASS")
    return Evaluation("FAIL_CLOSED", ("unknown_oracle_kind",))


def _evaluate_semantic_set(selection: Any, oracle: Mapping[str, Any]) -> Evaluation:
    """Check the approved planner-only semantic-set shape and material wording."""
    intent = selection.semantic_set
    if intent is None:
        return Evaluation("FAIL", ("semantic_set_missing",))
    if selection.relational_reference is not None:
        return Evaluation("FAIL", ("semantic_set_relational_conflict",))
    if intent.anchor_kind != oracle["anchor_kind"]:
        return Evaluation("FAIL", ("wrong_anchor_kind",))
    if intent.anchor_kind == "self" and intent.anchor_query is not None:
        return Evaluation("FAIL", ("self_anchor_query_present",))
    if intent.anchor_kind == "existing" and (
        intent.anchor_query is None
        or not _contains_all(intent.anchor_query, oracle["anchor_terms"])
    ):
        return Evaluation("FAIL", ("existing_anchor_query_missing",))
    if not intent.asks_exhaustive:
        return Evaluation("FAIL", ("exhaustive_intent_dropped",))
    if not _contains_all_sets(intent.group_query, oracle["group_term_sets"]):
        return Evaluation("FAIL", ("group_meaning_dropped",))
    qualifier_text = f"{intent.group_query} {intent.explicit_qualifiers}"
    if not _contains_all_sets(qualifier_text, oracle["qualifier_term_sets"]):
        return Evaluation("FAIL", ("material_qualifier_dropped",))
    return Evaluation("PASS")


def _has_unsafe_authority(plan: RequestPlan) -> bool:
    """Reject planner text that resembles a stable identity, path, or canonical link."""
    return bool(_UNSAFE_PLANNER_AUTHORITY.search(json.dumps(asdict(plan), ensure_ascii=False)))


def _contains_any(value: str, terms: Sequence[str]) -> bool:
    """Check one bounded semantic stem set after casefolding harmless wording variation."""
    normalized = value.casefold()
    return any(term.casefold() in normalized for term in terms)


def _contains_all(value: str, terms: Sequence[str]) -> bool:
    """Check every required bounded semantic stem in one planner field."""
    return all(term.casefold() in value.casefold() for term in terms)


def _contains_all_sets(value: str, term_sets: Sequence[Sequence[str]]) -> bool:
    """Require one matching harmless-wording alternative for every material concept."""
    return all(_contains_any(value, terms) for terms in term_sets)
