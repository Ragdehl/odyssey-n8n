"""Run the focused Phase 16.5A Sol/low reference-occurrence contract benchmark once."""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from benchmarks.phase15_1_schema_write_planning.benchmark import (
    load_cases as load_phase15_cases,
)
from benchmarks.phase15_1_schema_write_planning.benchmark import (
    schema_for as phase15_schema_for,
)
from odyssey_core.request_planning import OpenAIRequestPlanner, RequestPlanningError

BENCHMARK_DIR = Path(__file__).resolve().parent
CASES_PATH = BENCHMARK_DIR / "cases.json"
RESULTS_DIR = BENCHMARK_DIR / "results"
PHASE15_ORACLE_PATH = (
    BENCHMARK_DIR.parents[1] / "benchmarks/phase15_1_schema_write_planning/oracle.json"
)


def load_cases() -> list[dict[str, Any]]:
    """Load the fixed ten-case synthetic occurrence benchmark."""
    data = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    cases = data.get("cases")
    if not isinstance(cases, list) or len(cases) != 10:
        raise ValueError("Phase 16.5A benchmark requires exactly ten cases")
    return cases


def _schema() -> dict[str, Any]:
    """Load the canonical schema used by the production planner."""
    root = BENCHMARK_DIR.parents[1]
    return json.loads((root / "config" / "note-schema.json").read_text(encoding="utf-8"))


def _usage(response: Any) -> dict[str, int]:
    """Extract compact provider usage counters without storing provider content."""
    usage = getattr(response, "usage", None)
    if usage is None:
        return {}
    input_details = getattr(usage, "input_tokens_details", None)
    output_details = getattr(usage, "output_tokens_details", None)
    return {
        "input_tokens": int(getattr(usage, "input_tokens", 0) or 0),
        "cached_input_tokens": int(getattr(input_details, "cached_tokens", 0) or 0),
        "output_tokens": int(getattr(usage, "output_tokens", 0) or 0),
        "reasoning_tokens": int(getattr(output_details, "reasoning_tokens", 0) or 0),
    }


def _cost(usage: dict[str, int]) -> float | None:
    """Estimate standard Sol/low USD cost when the API supplies token counters."""
    if not usage:
        return None
    uncached = usage["input_tokens"] - usage["cached_input_tokens"]
    return round(
        (uncached * 4.0 + usage["cached_input_tokens"] * 0.4 + usage["output_tokens"] * 20.0)
        / 1_000_000,
        8,
    )


class _RecordingResponses:
    """Capture only the last response usage object while delegating the live API call."""

    def __init__(self, responses: Any) -> None:
        """Wrap the OpenAI Responses resource without changing its request arguments."""
        self._responses = responses
        self.last_response: Any | None = None

    def create(self, **kwargs: Any) -> Any:
        """Make one delegated provider call and retain its compact usage source."""
        self.last_response = None
        self.last_response = self._responses.create(**kwargs)
        return self.last_response


def _contract_findings(plan: Any, expected: dict[str, Any]) -> list[str]:
    """Compare validated plan references with the case's conservative contract oracle."""
    units = [unit for action in plan.actions if hasattr(action, "units") for unit in action.units]
    references = [reference for unit in units for reference in unit.references]
    findings: list[str] = []
    expected_count = expected.get("reference_count")
    if expected_count is not None and len(references) != expected_count:
        findings.append("reference_count")
    expected_mentions = [item["mention"] for item in expected.get("references", [])]
    actual_mentions = [reference.mention for reference in references]
    if expected_mentions and not all(mention in actual_mentions for mention in expected_mentions):
        findings.append("mention")
    if expected.get("repeated") and not any(
        sum(fact.count("{{ref:") for fact in unit.facts) > 1 for unit in units
    ):
        findings.append("repeated_marker")
    if expected.get("no_false_positive") and any(
        mention in expected["no_false_positive"] for mention in actual_mentions
    ):
        findings.append("false_positive_reference")
    if expected.get("intent") and not any(unit.intent == expected["intent"] for unit in units):
        findings.append("intent")
    expected_references = expected.get("references", [])
    actual_pairs: list[tuple[str, str]] = []
    marker_pairs: list[tuple[str, str]] = []
    for unit in units:
        for reference in unit.references:
            if 0 <= reference.target_index < len(units):
                actual_pairs.append((reference.mention, units[reference.target_index].target.query))
        for fact in unit.facts:
            cursor = 0
            while (start := fact.find("{{ref:", cursor)) >= 0:
                end = fact.find("}}", start)
                if end < 0:
                    break
                index = int(fact[start + 6 : end])
                reference = unit.references[index]
                marker_pairs.append((reference.mention, units[reference.target_index].target.query))
                cursor = end + 2
    for expected_reference in expected_references:
        expected_pair = (expected_reference["mention"], expected_reference["target_query"])
        if expected_pair not in actual_pairs:
            findings.append("reference_target_mapping")
        if expected_pair not in marker_pairs:
            findings.append("marker_target_mapping")
    if expected_references and len(marker_pairs) < len(expected_references):
        findings.append("missing_marker_occurrence")
    return findings


def _planner(
    schema: dict[str, Any], context: dict[str, str], recorder: _RecordingResponses
) -> OpenAIRequestPlanner:
    """Build the production planner for one benchmark schema/context pair."""
    return OpenAIRequestPlanner(SimpleNamespace(responses=recorder), schema, context)


def _phase15_findings(case_id: str, plan: Any) -> list[str]:
    """Apply the existing Phase 15.1 oracle to the current planner dataclasses."""
    oracle = json.loads(PHASE15_ORACLE_PATH.read_text(encoding="utf-8"))
    expected = next(row for row in oracle["cases"] if row["id"] == case_id)
    findings: list[str] = []
    actions = list(plan.actions)
    if [action.kind for action in actions] != expected["action_kinds"]:
        return ["unexpected_action_order_or_kind"]
    write_index = expected.get("write_action_index", 0)
    write_action = actions[write_index]
    if write_action.kind == "retrieve":
        retrieve_query = " ".join(
            action.plan.query for action in actions if action.kind == "retrieve"
        )
        if any(
            term not in retrieve_query.lower() for term in expected.get("retrieve_query_terms", [])
        ):
            findings.append("retrieve_query_lost_semantic_identity")
        write_action = actions[write_index]
    if not hasattr(write_action, "units"):
        return ["unexpected_knowledge_unit_count"]
    substantive_units = [
        unit
        for unit in write_action.units
        if unit.properties or unit.tag_changes or unit.facts or unit.references
    ]
    if len(substantive_units) != 1:
        return ["unexpected_knowledge_unit_count"]
    unit = substantive_units[0]
    if unit.intent != expected["intent"]:
        findings.append("incorrect_intent")
    if expected.get("type") and unit.target.type != expected["type"]:
        findings.append("incorrect_target_type")
    actual_filters = [(item.field, item.op, item.value) for item in unit.target.filters]
    if actual_filters != [tuple(item) for item in expected.get("filters", [])]:
        findings.append("incorrect_target_filters")
    actual_properties = [(item.field, item.op, item.value) for item in unit.properties]
    if actual_properties != [tuple(item) for item in expected["properties"]]:
        findings.append("incorrect_property_mutations")
    query = unit.target.query.lower()
    facts = " ".join(unit.facts).lower()
    semantic_facts = " ".join(
        [facts, *[reference.mention.lower() for reference in unit.references]]
    )
    if any(term not in query for term in expected.get("query_terms", [])):
        findings.append("target_query_lost_semantic_identity")
    if any(
        term not in semantic_facts and term not in query for term in expected.get("fact_terms", [])
    ):
        findings.append("unrepresented_knowledge_lost_from_facts")
    if any(term in facts for term in expected.get("forbidden_fact_terms", [])):
        findings.append("structured_property_duplicated_in_facts")
    if any(item.field in expected.get("forbidden_property_fields", []) for item in unit.properties):
        findings.append("invented_or_unrequested_property_mutation")
    if any(
        item.field in expected.get("forbidden_filter_fields", []) for item in unit.target.filters
    ):
        findings.append("forbidden_lifecycle_filter")
    return findings


def run(run_id: str) -> Path:
    """Run each synthetic request once through the production Sol/low planner.

    Args:
        run_id: New result-directory name; existing directories are never overwritten.

    Returns:
        Created result directory.

    Raises:
        RuntimeError: If provider access or the OpenAI SDK is unavailable.
        ValueError: If the run ID is unsafe or already exists.
    """
    if not run_id or Path(run_id).name != run_id:
        raise ValueError("Invalid benchmark run ID")
    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is required for the focused live benchmark")
    directory = RESULTS_DIR / run_id
    if directory.exists():
        raise ValueError("Refusing to overwrite an existing benchmark run")
    try:
        from openai import OpenAI

        recorder = _RecordingResponses(OpenAI().responses)
        schema = _schema()
    except (ImportError, RequestPlanningError) as error:
        raise RuntimeError(str(error)) from error
    directory.mkdir(parents=True)
    metadata = {
        "created_at": datetime.now(UTC).isoformat(),
        "benchmark_version": "16.5A.2",
        "model": "gpt-5.6-sol",
        "reasoning_effort": "low",
        "store": False,
        "planned_calls": len(load_cases()) + len(load_phase15_cases()),
        "regression_suite": "benchmarks/phase15_1_schema_write_planning/cases.json",
    }
    (directory / "metadata.json").write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
    )
    with (directory / "raw_results.jsonl").open("x", encoding="utf-8") as stream:
        cases = [
            ("occurrence", case, schema, metadata_context)
            for case in load_cases()
            for metadata_context in [
                {"date": "2026-08-26", "time": "10:30", "timezone": "Europe/Paris"}
            ]
        ]
        cases.extend(
            ("phase15_regression", case, phase15_schema_for(case), case["current_context"])
            for case in load_phase15_cases()
        )
        for suite, case, active_schema, context in cases:
            planner = _planner(active_schema, context, recorder)
            try:
                plan = planner.plan(case["request"])
            except RequestPlanningError as error:
                record = {
                    "id": case["id"],
                    "request": case["request"],
                    "suite": suite,
                    "status": "INVALID",
                    "error": str(error),
                    "usage": _usage(recorder.last_response),
                    "estimated_cost_usd": _cost(_usage(recorder.last_response)),
                    "raw_output": getattr(recorder.last_response, "output_text", None),
                }
            else:
                if suite == "occurrence":
                    findings = _contract_findings(plan, case["expected"])
                else:
                    findings = _phase15_findings(case["id"], plan)
                usage = _usage(recorder.last_response)
                record = {
                    "id": case["id"],
                    "request": case["request"],
                    "suite": suite,
                    "status": "PASS" if not findings else "CONTRACT_FAIL",
                    "findings": findings,
                    "units": len(
                        [
                            unit
                            for action in plan.actions
                            if hasattr(action, "units")
                            for unit in action.units
                        ]
                    ),
                    "usage": usage,
                    "estimated_cost_usd": _cost(usage),
                    "raw_output": getattr(recorder.last_response, "output_text", None),
                    "parsed_plan": asdict(plan),
                }
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")
            stream.flush()
    return directory


def main() -> None:
    """Parse the explicit one-run benchmark command."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    arguments = parser.parse_args()
    print(run(arguments.run_id))


if __name__ == "__main__":
    main()
