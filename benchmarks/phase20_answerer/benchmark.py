"""Deterministic Phase 20.1 grounded-answerer benchmark contract and evaluation."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

OUTCOMES = ("ANSWER", "INSUFFICIENT_EVIDENCE")
LIMITATIONS = ("PARTIAL_RESULT",)
PROMPT_VERSION = "phase20.1-v1"
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
CASES_PATH = Path(__file__).with_name("cases.json")
PRICING_PATH = Path(__file__).with_name("pricing_snapshot.json")


@dataclass(frozen=True)
class AnswerCase:
    """One frozen answerer input plus its deterministic benchmark oracle."""

    id: str
    description: str
    input: dict[str, Any]
    oracle: dict[str, Any]


def answer_schema() -> dict[str, Any]:
    """Return the closed structured-output contract used only by this benchmark."""
    return {
        "type": "object",
        "properties": {
            "outcome": {"type": "string", "enum": list(OUTCOMES)},
            "answer": {"type": "string", "minLength": 1},
            "supporting_item_ids": {"type": "array", "items": {"type": "string"}},
            "limitations": {
                "type": "array",
                "items": {"type": "string", "enum": list(LIMITATIONS)},
            },
        },
        "required": ["outcome", "answer", "supporting_item_ids", "limitations"],
        "additionalProperties": False,
    }


def answer_system_prompt() -> str:
    """Return the frozen Phase 20.1 evidence-only answerer instruction."""
    return (
        "You are Odyssey's bounded answerer. Answer only from the supplied Odyssey evidence; "
        "never use outside knowledge or fill missing facts from memory. Reply in the user's language "
        "unless the request explicitly asks otherwise. Preserve names, numbers, dates, and domain "
        "terms exactly when they matter. For ANSWER, cite every supplied evidence item you rely on "
        "in supporting_item_ids and do not cite irrelevant items. If the supplied evidence cannot "
        "answer the request, return INSUFFICIENT_EVIDENCE, explain that briefly, and use no support "
        "IDs. If Odyssey status is partial, include PARTIAL_RESULT in limitations and do not imply "
        "that the overall Odyssey operation was fully complete."
    )


def provider_request(case: AnswerCase) -> dict[str, Any]:
    """Build the provider-neutral request payload that 20.1B will send unchanged per case."""
    return {
        "store": False,
        "input": [
            {"role": "system", "content": answer_system_prompt()},
            {"role": "user", "content": json.dumps(case.input, ensure_ascii=False)},
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "odyssey_grounded_answer",
                "strict": True,
                "schema": answer_schema(),
            }
        },
    }


def repository_path(path: Path) -> Path:
    """Resolve an internal test/input path while refusing access outside this repository."""
    candidate = path.resolve() if path.is_absolute() else (REPOSITORY_ROOT / path).resolve()
    if candidate != REPOSITORY_ROOT and REPOSITORY_ROOT not in candidate.parents:
        raise ValueError("benchmark paths must stay inside the repository")
    return candidate


def _string_list(value: object, field: str) -> list[str]:
    """Validate a JSON list containing strings and return it unchanged."""
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{field} must be a list of strings")
    return value


def _validate_case(raw: object) -> AnswerCase:
    """Validate one frozen case and its oracle before any provider call can occur."""
    if not isinstance(raw, dict) or set(raw) != {"id", "description", "input", "oracle"}:
        raise ValueError("answerer case has an invalid top-level shape")
    if not isinstance(raw["id"], str) or not raw["id"].strip():
        raise ValueError("answerer case id must be a non-empty string")
    if not isinstance(raw["description"], str) or not raw["description"].strip():
        raise ValueError(f"case {raw['id']} description must be non-empty")

    input_value = raw["input"]
    if not isinstance(input_value, dict) or set(input_value) != {
        "request",
        "status",
        "retrieval_query",
        "items",
    }:
        raise ValueError(f"case {raw['id']} input has an invalid shape")
    if not isinstance(input_value["request"], str) or not input_value["request"].strip():
        raise ValueError(f"case {raw['id']} request must be non-empty")
    if input_value["status"] not in {"completed", "partial"}:
        raise ValueError(f"case {raw['id']} status must be completed or partial")
    if not isinstance(input_value["retrieval_query"], str):
        raise ValueError(f"case {raw['id']} retrieval_query must be a string")
    if not isinstance(input_value["items"], list):
        raise ValueError(f"case {raw['id']} items must be a list")

    item_ids: list[str] = []
    paths: list[str] = []
    for item in input_value["items"]:
        if not isinstance(item, dict) or set(item) != {"id", "type", "path", "content"}:
            raise ValueError(f"case {raw['id']} contains an invalid evidence item")
        if any(not isinstance(item[field], str) or not item[field].strip() for field in item):
            raise ValueError(f"case {raw['id']} evidence fields must be non-empty strings")
        item_ids.append(item["id"])
        paths.append(item["path"])
    if len(item_ids) != len(set(item_ids)):
        raise ValueError(f"case {raw['id']} contains duplicate evidence item ids")
    if len(paths) != len(set(paths)):
        raise ValueError(f"case {raw['id']} contains duplicate canonical note paths")

    oracle = raw["oracle"]
    expected_oracle_keys = {
        "expected_outcome",
        "required_supporting_item_ids",
        "forbidden_supporting_item_ids",
        "required_answer_fragments",
        "forbidden_answer_fragments",
        "require_partial_limitation",
    }
    if not isinstance(oracle, dict) or set(oracle) != expected_oracle_keys:
        raise ValueError(f"case {raw['id']} oracle has an invalid shape")
    if oracle["expected_outcome"] not in OUTCOMES:
        raise ValueError(f"case {raw['id']} oracle outcome is invalid")

    required_ids = _string_list(
        oracle["required_supporting_item_ids"], "required_supporting_item_ids"
    )
    forbidden_ids = _string_list(
        oracle["forbidden_supporting_item_ids"], "forbidden_supporting_item_ids"
    )
    required_fragments = _string_list(
        oracle["required_answer_fragments"], "required_answer_fragments"
    )
    forbidden_fragments = _string_list(
        oracle["forbidden_answer_fragments"], "forbidden_answer_fragments"
    )
    if len(required_ids) != len(set(required_ids)) or len(forbidden_ids) != len(set(forbidden_ids)):
        raise ValueError(f"case {raw['id']} oracle contains duplicate support ids")
    if set(required_ids) & set(forbidden_ids):
        raise ValueError(f"case {raw['id']} oracle support sets overlap")
    if not set(required_ids + forbidden_ids).issubset(item_ids):
        raise ValueError(f"case {raw['id']} oracle references unknown evidence ids")
    if any(not fragment for fragment in required_fragments + forbidden_fragments):
        raise ValueError(f"case {raw['id']} answer fragments must be non-empty")
    if not isinstance(oracle["require_partial_limitation"], bool):
        raise ValueError(f"case {raw['id']} partial limitation flag must be boolean")
    if oracle["require_partial_limitation"] and input_value["status"] != "partial":
        raise ValueError(f"case {raw['id']} cannot require partial limitation when completed")
    if oracle["expected_outcome"] == "ANSWER" and not required_ids:
        raise ValueError(f"case {raw['id']} answer oracle must require grounded support")
    if oracle["expected_outcome"] == "INSUFFICIENT_EVIDENCE" and required_ids:
        raise ValueError(f"case {raw['id']} insufficient oracle cannot require support")

    return AnswerCase(raw["id"], raw["description"], input_value, oracle)


def load_cases(path: Path = CASES_PATH) -> tuple[AnswerCase, ...]:
    """Load and validate the frozen benchmark suite from an internal repository file."""
    payload = json.loads(repository_path(path).read_text(encoding="utf-8"))
    if (
        not isinstance(payload, dict)
        or set(payload) != {"cases"}
        or not isinstance(payload["cases"], list)
    ):
        raise ValueError("answerer cases file has an invalid shape")
    cases = tuple(_validate_case(raw) for raw in payload["cases"])
    if not cases:
        raise ValueError("answerer cases file must contain at least one case")
    ids = [case.id for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("answerer cases file contains duplicate case ids")
    return cases


def select_cases(
    cases: tuple[AnswerCase, ...], case_ids: tuple[str, ...] | None
) -> tuple[AnswerCase, ...]:
    """Return requested cases in frozen corpus order, rejecting unknown IDs."""
    if not case_ids:
        return cases
    requested = set(case_ids)
    unknown = requested - {case.id for case in cases}
    if unknown:
        raise ValueError(f"unknown benchmark case ids: {sorted(unknown)}")
    return tuple(case for case in cases if case.id in requested)


def validate_answer(value: object, supplied_ids: set[str]) -> dict[str, Any]:
    """Validate the closed answer contract and reject invented support IDs."""
    expected_keys = {"outcome", "answer", "supporting_item_ids", "limitations"}
    if not isinstance(value, dict) or set(value) != expected_keys:
        raise ValueError("answer schema is invalid")
    if value["outcome"] not in OUTCOMES:
        raise ValueError("answer outcome is invalid")
    if not isinstance(value["answer"], str) or not value["answer"].strip():
        raise ValueError("answer text must be non-empty")
    supporting_ids = _string_list(value["supporting_item_ids"], "supporting_item_ids")
    limitations = _string_list(value["limitations"], "limitations")
    if len(supporting_ids) != len(set(supporting_ids)):
        raise ValueError("answer contains duplicate supporting item ids")
    if len(limitations) != len(set(limitations)):
        raise ValueError("answer contains duplicate limitations")
    if any(item_id not in supplied_ids for item_id in supporting_ids):
        raise ValueError("answer contains an unknown supporting item id")
    if any(limitation not in LIMITATIONS for limitation in limitations):
        raise ValueError("answer contains an unknown limitation")
    if value["outcome"] == "ANSWER" and not supporting_ids:
        raise ValueError("ANSWER requires at least one supplied supporting item")
    if value["outcome"] == "INSUFFICIENT_EVIDENCE" and supporting_ids:
        raise ValueError("INSUFFICIENT_EVIDENCE cannot cite supporting items")
    return value


def evaluate_case(case: AnswerCase, response: dict[str, Any]) -> dict[str, Any]:
    """Apply the frozen deterministic oracle to one validated model response."""
    oracle = case.oracle
    answer_folded = response["answer"].casefold()
    supporting_ids = set(response["supporting_item_ids"])
    partial_present = "PARTIAL_RESULT" in response["limitations"]
    checks = {
        "outcome": response["outcome"] == oracle["expected_outcome"],
        "required_support": set(oracle["required_supporting_item_ids"]).issubset(supporting_ids),
        "forbidden_support": not supporting_ids.intersection(
            oracle["forbidden_supporting_item_ids"]
        ),
        "required_fragments": all(
            fragment.casefold() in answer_folded for fragment in oracle["required_answer_fragments"]
        ),
        "forbidden_fragments": all(
            fragment.casefold() not in answer_folded
            for fragment in oracle["forbidden_answer_fragments"]
        ),
        "partial_limitation": partial_present == oracle["require_partial_limitation"],
    }
    return {"passed": all(checks.values()), "checks": checks}


def contract_identity() -> str:
    """Hash the exact prompt and schema for live-evidence compatibility in 20.1B."""
    payload = json.dumps(
        {
            "prompt_version": PROMPT_VERSION,
            "prompt": answer_system_prompt(),
            "schema": answer_schema(),
        },
        ensure_ascii=False,
        sort_keys=True,
    ).encode()
    return hashlib.sha256(payload).hexdigest()


def run_identity(
    model: str,
    reasoning: str,
    case_ids: tuple[str, ...] = (),
    cases_path: Path = CASES_PATH,
) -> dict[str, str]:
    """Return stable identities for an exact future live configuration without performing I/O."""
    cases_file = repository_path(cases_path)
    return {
        "model": model,
        "reasoning": reasoning,
        "cases": ",".join(case_ids),
        "cases_sha256": hashlib.sha256(cases_file.read_bytes()).hexdigest(),
        "contract_sha256": contract_identity(),
    }


def normalize_usage(usage: object) -> dict[str, int | None] | None:
    """Extract only bounded token counters supplied by a later provider call."""
    if usage is None:
        return None
    input_tokens = getattr(usage, "input_tokens", None)
    output_tokens = getattr(usage, "output_tokens", None)
    input_details = getattr(usage, "input_tokens_details", None)
    output_details = getattr(usage, "output_tokens_details", None)
    cached_input_tokens = getattr(input_details, "cached_tokens", None)
    reasoning_tokens = getattr(output_details, "reasoning_tokens", None)
    values = (input_tokens, output_tokens, cached_input_tokens, reasoning_tokens)
    if any(value is not None and (not isinstance(value, int) or value < 0) for value in values):
        raise ValueError("provider usage contains an invalid token count")
    return {
        "input_tokens": input_tokens,
        "cached_input_tokens": cached_input_tokens,
        "output_tokens": output_tokens,
        "reasoning_tokens": reasoning_tokens,
    }


def load_pricing_snapshot(path: Path | None = None) -> dict[str, Any] | None:
    """Load an optional dated pricing snapshot for later deterministic cost evaluation."""
    pricing_file = PRICING_PATH if path is None else repository_path(path)
    if not pricing_file.exists():
        return None
    payload = json.loads(pricing_file.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or set(payload) != {"as_of", "source", "models"}:
        raise ValueError("pricing snapshot has an invalid shape")
    if not isinstance(payload["as_of"], str) or not payload["as_of"].strip():
        raise ValueError("pricing snapshot as_of must be non-empty")
    if not isinstance(payload["source"], str) or not payload["source"].strip():
        raise ValueError("pricing snapshot source must be non-empty")
    if not isinstance(payload["models"], dict):
        raise ValueError("pricing snapshot models must be an object")
    for model, rates in payload["models"].items():
        if not isinstance(model, str) or not model:
            raise ValueError("pricing snapshot model id must be non-empty")
        if not isinstance(rates, dict) or set(rates) != {
            "input_per_million",
            "cached_input_per_million",
            "output_per_million",
        }:
            raise ValueError(f"pricing snapshot rates are invalid for {model}")
        if any(not isinstance(rate, (int, float)) or rate < 0 for rate in rates.values()):
            raise ValueError(f"pricing snapshot rates must be non-negative for {model}")
    return payload


def estimate_cost_usd(
    usage: dict[str, int | None] | None,
    pricing: dict[str, Any] | None,
    model: str,
) -> float | None:
    """Estimate token cost only when complete usage and matching snapshot rates exist."""
    if usage is None or pricing is None or model not in pricing["models"]:
        return None
    input_tokens = usage["input_tokens"]
    cached_tokens = usage["cached_input_tokens"]
    output_tokens = usage["output_tokens"]
    if input_tokens is None or cached_tokens is None or output_tokens is None:
        return None
    if cached_tokens > input_tokens:
        raise ValueError("cached input tokens cannot exceed total input tokens")
    rates = pricing["models"][model]
    uncached_tokens = input_tokens - cached_tokens
    cost = (
        uncached_tokens * rates["input_per_million"]
        + cached_tokens * rates["cached_input_per_million"]
        + output_tokens * rates["output_per_million"]
    ) / 1_000_000
    return round(cost, 9)


def _sum_optional(values: list[int | float | None]) -> int | float | None:
    """Sum a metric only when every row contains it, preserving unavailable as unavailable."""
    if any(value is None for value in values):
        return None
    return sum(value for value in values if value is not None)


def aggregate_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize grounding quality, latency, usage, and cost without inventing missing metrics."""
    if not rows:
        return {"case_count": 0}
    latencies = [row.get("latency_seconds") for row in rows]
    costs = [row.get("estimated_cost_usd") for row in rows]
    usage_rows = [row.get("usage") for row in rows]

    def usage_values(field: str) -> list[int | None]:
        return [usage.get(field) if isinstance(usage, dict) else None for usage in usage_rows]

    total_latency = _sum_optional(latencies)
    return {
        "case_count": len(rows),
        "passed": sum(bool(row.get("evaluation", {}).get("passed")) for row in rows),
        "pass_rate": sum(bool(row.get("evaluation", {}).get("passed")) for row in rows) / len(rows),
        "average_latency_seconds": (
            round(float(total_latency) / len(rows), 3) if total_latency is not None else None
        ),
        "total_input_tokens": _sum_optional(usage_values("input_tokens")),
        "total_cached_input_tokens": _sum_optional(usage_values("cached_input_tokens")),
        "total_output_tokens": _sum_optional(usage_values("output_tokens")),
        "total_reasoning_tokens": _sum_optional(usage_values("reasoning_tokens")),
        "total_estimated_cost_usd": _sum_optional(costs),
    }
