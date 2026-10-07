"""One-shot current production Planner regression gate with no accepted failures."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from openai import OpenAI

from benchmarks.planner_prompt_regression_v1 import run_live as inherited
from benchmarks.semantic_write_resolution_current_v1.evaluate import (
    evaluate as evaluate_current_successor,
)
from benchmarks.semantic_write_resolution_current_v1.evaluate import (
    load_registry as load_current_successors,
)
from odyssey_apps.schema_extensions import compose_application_schema
from odyssey_apps.tasks import TASK_SCHEMA_EXTENSION
from odyssey_core.experimental_luna_planning import (
    LUNA_EXPERIMENT_MAX_OUTPUT_TOKENS,
    LUNA_EXPERIMENT_MODEL,
    LUNA_EXPERIMENT_REASONING_EFFORT,
    OpenAILunaExperimentalPlanner,
    luna_experimental_result_json_schema,
    render_luna_experimental_prompt,
)
from odyssey_core.request_planning import KnowledgeUnit, RequestPlan, WriteAction

ROOT = Path(__file__).resolve().parents[2]
BASE_SCHEMA_PATH = ROOT / "config/note-schema.json"
NEW_CASES_PATH = Path(__file__).with_name("new_cases.json")
MANIFEST_PATH = Path(__file__).with_name("manifest.json")
RESULTS_DIR = Path(__file__).with_name("results")
PRODUCTION_MODEL = "gpt-5.6-luna"
REASONING_EFFORT = "low"
MAX_CALLS = 23
MAX_ACTUAL_COST_USD = Decimal("0.150")
MAX_CONSERVATIVE_COST_USD = Decimal("0.350")
STANDARD_INPUT_USD_PER_M = Decimal("0.20")
STANDARD_OUTPUT_USD_PER_M = Decimal("1.20")
INPUT_OVERHEAD_BYTES = 1024

# These event-like journal fixtures were superseded by the already-accepted current
# Directorio Faro cases. Every other inherited case is still a current requirement.
OBSOLETE_INHERITED_IDS = frozenset(
    {
        "SWR07-qualified-event-member",
        "SWR08-relational-target-described-reference",
        "SWR10-relational-target-two-bounded-references",
    }
)


def production_schema() -> dict[str, Any]:
    """Return the exact composed schema used by the DEV Core planner."""
    base = json.loads(BASE_SCHEMA_PATH.read_text(encoding="utf-8"))
    return compose_application_schema(base, (TASK_SCHEMA_EXTENSION,))


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _model_contract_hashes(schema: dict[str, Any], context: dict[str, str]) -> dict[str, str]:
    prompt = render_luna_experimental_prompt(schema, context).encode("utf-8")
    provider = json.dumps(
        luna_experimental_result_json_schema(schema),
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return {
        "prompt_sha256": _sha256_bytes(prompt),
        "provider_schema_sha256": _sha256_bytes(provider),
        "teaching_examples_sha256": _sha256_bytes(inherited.TEACHING_PATH.read_bytes()),
    }


def load_gate_cases() -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Compose only current inherited, successor, and newly discovered regression cases."""
    old_cases, context = inherited.load_gate_cases()
    retained = [
        {**case, "lineage": case["lineage"]}
        for case in old_cases
        if case["id"] not in OBSOLETE_INHERITED_IDS
    ]

    current_registry = load_current_successors()
    if current_registry["fixed_context"] != context:
        raise RuntimeError("current successor context diverged")
    retained.extend({**case, "lineage": "current_successor"} for case in current_registry["cases"])

    new_payload = json.loads(NEW_CASES_PATH.read_text(encoding="utf-8"))
    if new_payload["fixed_context"] != context:
        raise RuntimeError("new regression context diverged")
    retained.extend(new_payload["cases"])

    ids = [case["id"] for case in retained]
    if len(retained) != MAX_CALLS or len(ids) != len(set(ids)):
        raise RuntimeError("v5 case registry has unexpected size or duplicate IDs")
    return retained, context


def _normalize(value: str) -> str:
    return re.sub(
        r"[^a-z0-9 ]",
        "",
        value.casefold()
        .replace("á", "a")
        .replace("é", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ú", "u")
        .replace("ü", "u")
        .replace("ñ", "n"),
    )


def _single_write(result: Any) -> WriteAction | None:
    if not isinstance(result, RequestPlan) or len(result.actions) != 1:
        return None
    action = result.actions[0]
    return action if isinstance(action, WriteAction) else None


def _material_and_lookups(
    action: WriteAction,
) -> tuple[tuple[KnowledgeUnit, ...], tuple[KnowledgeUnit, ...]]:
    material = tuple(unit for unit in action.units if not unit.reference_lookup_only)
    lookups = tuple(unit for unit in action.units if unit.reference_lookup_only)
    return material, lookups


def _nested_identity_passed(result: Any, case: dict[str, Any]) -> tuple[bool, list[str]]:
    action = _single_write(result)
    if action is None:
        return False, ["expected_single_write"]
    material, lookups = _material_and_lookups(action)
    expected = case["expect"]
    findings: list[str] = []
    if len(material) != 1:
        findings.append("expected_one_material_unit")
        return False, findings

    matching = [
        unit
        for unit in lookups
        if unit.target.type == expected["note_type"]
        and (
            unit.target.entity == expected["entity"]
            or _normalize(expected["entity"]) in _normalize(unit.target.query)
        )
    ]
    if len(matching) != 1:
        findings.append("missing_nested_typed_identity")
    source = material[0]
    if not any(
        _normalize(expected["entity"]) in _normalize(reference.mention)
        for reference in source.references
    ):
        findings.append("nested_surface_occurrence_not_referenced")
    if not any("{{ref:" in fact for fact in source.facts):
        findings.append("material_fact_has_no_reference_marker")

    forbidden = tuple(_normalize(term) for term in expected.get("forbidden_identity_terms", ()))
    for lookup in lookups:
        identity_text = _normalize(
            " ".join(filter(None, (lookup.target.entity, lookup.target.query)))
        )
        if any(term and term in identity_text for term in forbidden):
            findings.append("unresolved_literal_context_promoted_to_identity")
            break
    return not findings, findings


def _coordinated_relations_passed(result: Any) -> tuple[bool, list[str]]:
    action = _single_write(result)
    if action is None:
        return False, ["expected_single_write"]
    material, lookups = _material_and_lookups(action)
    findings: list[str] = []
    if len(material) != 1:
        return False, ["expected_one_material_unit"]

    selections = [unit.target for unit in lookups]
    selections.extend(
        reference.selection
        for reference in material[0].references
        if reference.selection is not None
    )
    spouse = None
    children = None
    for selection in selections:
        relation = selection.relational_reference
        if relation is None:
            continue
        text = _normalize(" ".join(filter(None, (selection.query, relation.reference))))
        if "mujer" in text:
            spouse = selection
        if "hijo" in text:
            children = selection
    if spouse is None:
        findings.append("missing_spouse_scope")
    else:
        relation = spouse.relational_reference
        if relation is None or relation.source_kind != "self" or relation.members != "one":
            findings.append("wrong_spouse_scope")
    if children is None:
        findings.append("missing_children_scope")
    else:
        relation = children.relational_reference
        if relation is None or relation.source_kind != "self" or relation.members != "complete_set":
            findings.append("wrong_children_scope")
    if len(material[0].references) != 2:
        findings.append("expected_two_fact_references")
    return not findings, findings


def _complete_set_passed(result: Any) -> tuple[bool, list[str]]:
    action = _single_write(result)
    if action is None:
        return False, ["expected_single_write"]
    material, lookups = _material_and_lookups(action)
    findings: list[str] = []
    if len(material) != 1:
        return False, ["expected_one_material_unit"]
    selections = [unit.target for unit in lookups]
    selections.extend(
        reference.selection
        for reference in material[0].references
        if reference.selection is not None
    )
    complete_sets = [
        selection
        for selection in selections
        if selection.relational_reference is not None
        and selection.relational_reference.members == "complete_set"
    ]
    if len(complete_sets) != 1:
        return False, ["expected_one_complete_set_selection"]
    selection = complete_sets[0]
    relation = selection.relational_reference
    assert relation is not None
    text = _normalize(" ".join(filter(None, (selection.query, relation.reference))))
    if "primo" not in text or "canada" not in text:
        findings.append("complete_set_surface_lost")
    if relation.source_kind != "self":
        findings.append("expected_self_complete_set")
    if len(material[0].references) != 1:
        findings.append("expected_one_fact_reference")
    return not findings, findings


def evaluate_case(result: Any, case: dict[str, Any]) -> tuple[bool, list[str]]:
    lineage = case["lineage"]
    if lineage in {"frozen_swr", "frontend_sentinel", "clarification_entry"}:
        return inherited._case_passed(result, case)
    if lineage == "current_successor":
        verdict = evaluate_current_successor(result, case["expect"])
        return verdict.passed, list(verdict.findings)
    if lineage == "nested_identity":
        return _nested_identity_passed(result, case)
    if lineage == "coordinated_relations":
        return _coordinated_relations_passed(result)
    if lineage == "complete_set":
        return _complete_set_passed(result)
    return False, ["unknown_lineage"]


class RecordingResponses:
    """Count provider calls and retain bounded usage only."""

    def __init__(self, responses: Any) -> None:
        self._responses = responses
        self.attempts = 0
        self.records: list[dict[str, int]] = []
        self.failures: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> Any:
        self.attempts += 1
        try:
            response = self._responses.create(**kwargs)
        except Exception as error:
            self.failures.append(
                {
                    "attempt": self.attempts,
                    "error_type": type(error).__name__,
                    "status_code": getattr(error, "status_code", None),
                }
            )
            raise
        usage = getattr(response, "usage", None)
        details = getattr(usage, "input_tokens_details", None)
        output_details = getattr(usage, "output_tokens_details", None)
        self.records.append(
            {
                "input_tokens": int(getattr(usage, "input_tokens", 0) or 0),
                "cached_input_tokens": int(getattr(details, "cached_tokens", 0) or 0),
                "output_tokens": int(getattr(usage, "output_tokens", 0) or 0),
                "reasoning_tokens": int(getattr(output_details, "reasoning_tokens", 0) or 0),
            }
        )
        return response


def conservative_cost_ceiling(
    cases: list[dict[str, Any]], context: dict[str, str], schema: dict[str, Any]
) -> Decimal:
    """Use byte-as-token input and no cache credit as a deliberately loose upper bound."""
    provider_schema = json.dumps(
        luna_experimental_result_json_schema(schema),
        ensure_ascii=False,
        separators=(",", ":"),
    )
    maximum = 0
    for case in cases:
        prompt = render_luna_experimental_prompt(
            schema,
            context,
            conversation_context=case.get("conversation_context", ()),
        )
        maximum = max(
            maximum,
            len((prompt + provider_schema + case["request"]).encode("utf-8")),
        )
    input_bound = maximum + INPUT_OVERHEAD_BYTES
    per_call = (
        Decimal(input_bound) * STANDARD_INPUT_USD_PER_M
        + Decimal(LUNA_EXPERIMENT_MAX_OUTPUT_TOKENS) * STANDARD_OUTPUT_USD_PER_M
    ) / Decimal(1_000_000)
    return per_call * Decimal(len(cases))


def actual_standard_cost(records: list[dict[str, int]]) -> Decimal:
    """Charge cached input at the standard input rate for a conservative observed total."""
    return sum(
        (
            Decimal(record["input_tokens"]) * STANDARD_INPUT_USD_PER_M
            + Decimal(record["output_tokens"]) * STANDARD_OUTPUT_USD_PER_M
        )
        / Decimal(1_000_000)
        for record in records
    )


def verify_manifest(schema: dict[str, Any], context: dict[str, str]) -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    actual = {
        "new_cases_sha256": _sha256_bytes(NEW_CASES_PATH.read_bytes()),
        "current_successor_sha256": _sha256_bytes(
            (ROOT / "benchmarks/semantic_write_resolution_current_v1/cases.json").read_bytes()
        ),
        **_model_contract_hashes(schema, context),
    }
    if actual != manifest["sha256"]:
        raise SystemExit(f"Refusing live calls: v5 contract drifted: {actual}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-live-provider-calls", action="store_true")
    args = parser.parse_args(argv)
    if not args.confirm_live_provider_calls:
        raise SystemExit("Refusing live calls: explicit confirmation is required")
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("Refusing live calls: OPENAI_API_KEY is unavailable")
    if subprocess.check_output(
        ["git", "-C", str(ROOT), "status", "--porcelain"], text=True
    ).strip():
        raise SystemExit("Refusing live calls from a dirty worktree")
    if (LUNA_EXPERIMENT_MODEL, LUNA_EXPERIMENT_REASONING_EFFORT) != (
        PRODUCTION_MODEL,
        REASONING_EFFORT,
    ):
        raise SystemExit("Refusing live calls: production Planner model contract changed")

    cases, context = load_gate_cases()
    schema = production_schema()
    verify_manifest(schema, context)
    ceiling = conservative_cost_ceiling(cases, context, schema)
    if ceiling > MAX_CONSERVATIVE_COST_USD:
        raise SystemExit(f"Refusing live calls: conservative v5 ceiling changed: {ceiling}")
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    commit = subprocess.check_output(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True
    ).strip()
    out = RESULTS_DIR / f"{commit[:12]}.json"
    if out.exists():
        raise SystemExit("Refusing live calls: this v5 candidate already has retained evidence")

    recorder = RecordingResponses(OpenAI(max_retries=0, timeout=30.0).responses)
    planner = OpenAILunaExperimentalPlanner(SimpleNamespace(responses=recorder), schema, context)
    rows: list[dict[str, Any]] = []
    for case in cases:
        try:
            result = planner.plan(case["request"], case.get("conversation_context", ()))
            passed, findings = evaluate_case(result, case)
            row = {
                "case_id": case["id"],
                "lineage": case["lineage"],
                "passed": passed,
                "findings": findings,
                "result": asdict(result),
                "usage": planner.last_usage,
                "provider_status": planner.last_provider_status,
                "response_id": planner.last_response_id,
            }
        except Exception as error:
            row = {
                "case_id": case["id"],
                "lineage": case["lineage"],
                "passed": False,
                "findings": [planner.last_error_category or type(error).__name__[:120]],
                "error": type(error).__name__,
                "usage": planner.last_usage,
            }
        rows.append(row)
        print(
            case["id"],
            "PASS" if row["passed"] else "FAIL",
            row["findings"],
            flush=True,
        )

    cost = actual_standard_cost(recorder.records)
    if recorder.attempts > MAX_CALLS or cost > MAX_ACTUAL_COST_USD:
        raise SystemExit("v5 actual provider ceiling exceeded")
    acceptable = all(row["passed"] for row in rows)
    artifact = {
        "version": 5,
        "commit": subprocess.check_output(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True
        ).strip(),
        "provider_attempts": recorder.attempts,
        "completed_provider_responses": len(recorder.records),
        "automatic_retries": 0,
        "sol_calls": 0,
        "conservative_cost_ceiling_usd": str(ceiling),
        "estimated_standard_cost_usd": str(cost),
        "acceptable": acceptable,
        "failed_case_ids": [row["case_id"] for row in rows if not row["passed"]],
        "rows": rows,
        "provider_failures": recorder.failures,
    }
    out = RESULTS_DIR / f"{artifact['commit'][:12]}.json"
    out.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"provider_attempts={recorder.attempts}")
    print(f"estimated_standard_cost_usd={cost}")
    print(f"acceptable={acceptable}")
    print(f"failed_case_ids={artifact['failed_case_ids']}")
    print(f"artifact={out.relative_to(ROOT)}")
    return 0 if acceptable else 1


if __name__ == "__main__":
    raise SystemExit(main())
