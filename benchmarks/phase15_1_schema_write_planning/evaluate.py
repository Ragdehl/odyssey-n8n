"""Small deterministic oracle for focused Phase 15.1 benchmark evidence."""

from __future__ import annotations

from typing import Any

from benchmarks.phase15_1_schema_write_planning.benchmark import BENCHMARK_DIR, load_json
from odyssey_core.request_planning import RequestPlanningError, validate_request_plan


def _expectation(case_id: str) -> dict[str, Any]:
    """Load one frozen oracle row by its unique benchmark identifier."""
    rows = load_json(BENCHMARK_DIR / "oracle.json").get("cases")
    matches = [row for row in rows if row.get("id") == case_id] if isinstance(rows, list) else []
    if len(matches) != 1:
        raise ValueError(f"Missing frozen oracle for {case_id}")
    return matches[0]


def evaluate(case_id: str, payload: Any, schema: dict[str, Any]) -> tuple[str, list[str]]:
    """Classify one production response as PASS, FAIL, or INVALID.

    Args:
        case_id: Stable frozen case identifier.
        payload: JSON-decoded model response.
        schema: Exact active schema used for the request.

    Returns:
        Classification and concise deterministic mismatch codes.
    """
    try:
        validate_request_plan(payload, schema)
    except RequestPlanningError as error:
        return "INVALID", [f"invalid_plan:{error}"]
    expected, actions = _expectation(case_id), payload["actions"]
    if [action["kind"] for action in actions] != expected["action_kinds"]:
        return "FAIL", ["unexpected_action_order_or_kind"]
    action = actions[expected.get("write_action_index", 0)]
    if len(action["units"]) != 1:
        return "FAIL", ["unexpected_knowledge_unit_count"]
    unit, findings = action["units"][0], []
    if unit["intent"] != expected["intent"]:
        findings.append("incorrect_intent")
    if "type" in expected and unit["target"]["type"] != expected["type"]:
        findings.append("incorrect_target_type")
    actual_filters = [
        [item["field"], item["op"], item["value"]] for item in unit["target"]["filters"]
    ]
    allowed = expected.get("allowed_filters", [expected.get("filters", [])])
    if actual_filters not in allowed:
        findings.append("incorrect_target_filters")
    actual_properties = [[item["field"], item["op"], item["value"]] for item in unit["properties"]]
    if actual_properties != expected["properties"]:
        findings.append("incorrect_property_mutations")
    query, facts = unit["target"]["query"].lower(), " ".join(unit["facts"]).lower()
    if any(term not in query for term in expected.get("query_terms", [])):
        findings.append("target_query_lost_semantic_identity")
    if any(term not in facts for term in expected.get("fact_terms", [])):
        findings.append("unrepresented_knowledge_lost_from_facts")
    if any(term in facts for term in expected.get("forbidden_fact_terms", [])):
        findings.append("structured_property_duplicated_in_facts")
    if any(
        item["field"] in expected.get("forbidden_filter_fields", [])
        for item in unit["target"]["filters"]
    ):
        findings.append("forbidden_lifecycle_filter")
    return ("FAIL" if findings else "PASS"), findings
