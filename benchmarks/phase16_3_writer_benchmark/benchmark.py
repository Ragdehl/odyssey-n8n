"""Load frozen Phase 16.3 inputs and build the closed writer-output schema."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

BENCHMARK_DIR = Path(__file__).resolve().parent
CASES_PATH = BENCHMARK_DIR / "cases.json"
PROMPT_PATH = BENCHMARK_DIR / "prompt.md"
CONTRACT_PATH = BENCHMARK_DIR / "schema_contract.json"


class BenchmarkContractError(ValueError):
    """Indicate malformed frozen benchmark input or writer output."""


def load_cases() -> list[dict[str, Any]]:
    """Load exactly sixty frozen synthetic benchmark cases.

    Returns:
        Cases containing label-free model inputs plus a deterministic semantic oracle.

    Raises:
        BenchmarkContractError: If coverage, IDs, context mode, or body presence is invalid.
    """
    try:
        cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))["cases"]
    except (OSError, KeyError, json.JSONDecodeError) as error:
        raise BenchmarkContractError("Phase 16.3 cases are unreadable") from error
    if not isinstance(cases, list) or len(cases) != 60:
        raise BenchmarkContractError("Phase 16.3 requires exactly 60 frozen cases")
    identifiers = [case.get("id") for case in cases if isinstance(case, dict)]
    if (
        len(identifiers) != 60
        or len(set(identifiers)) != 60
        or not all(isinstance(value, str) and value for value in identifiers)
    ):
        raise BenchmarkContractError("Phase 16.3 case IDs are invalid")
    for case in cases:
        if case.get("mode") not in {"UPDATE", "CREATE"} or not isinstance(case.get("facts"), list):
            raise BenchmarkContractError("Phase 16.3 case mode or facts are invalid")
        if case["mode"] == "UPDATE" and not isinstance(case.get("current_body"), str):
            raise BenchmarkContractError("UPDATE case lacks authoritative body")
        if case["mode"] == "CREATE" and "current_body" in case:
            raise BenchmarkContractError("CREATE case must not have an existing body")
    return cases


def render_prompt() -> str:
    """Return the immutable model instruction text for every provider stage."""
    return PROMPT_PATH.read_text(encoding="utf-8").rstrip()


def writer_json_schema() -> dict[str, Any]:
    """Build the strict closed Structured Outputs schema for bounded writer operations."""
    # Responses Structured Outputs does not permit ``oneOf`` here.  All nullable fields are
    # required for provider compatibility; the local evaluator restores each operation's exact
    # field contract before evidence can pass.
    operation = {
        "type": "object",
        "properties": {
            "op": {
                "type": "string",
                "enum": ["NO_CHANGE", "APPEND", "REPLACE", "REMOVE", "INSERT_AFTER", "CREATE_BODY"],
            },
            "text": {"type": ["string", "null"]},
            "old": {"type": ["string", "null"]},
            "new": {"type": ["string", "null"]},
            "anchor": {"type": ["string", "null"]},
            "content": {"type": ["string", "null"]},
        },
        "required": ["op", "text", "old", "new", "anchor", "content"],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {"operations": {"type": "array", "minItems": 1, "items": operation}},
        "required": ["operations"],
        "additionalProperties": False,
    }


def render_request(case: dict[str, Any], *, context: str | None = None) -> str:
    """Render one label-free writer request using full or pre-frozen reduced context.

    Args:
        case: One validated frozen benchmark case.
        context: Optional authoritative context override for reduced-context probes.

    Returns:
        Compact JSON evidence passed as the sole user input.
    """
    evidence = {
        "mode": case["mode"],
        "canonical_note_type": case["note_type"],
        "write_intent": case["intent"],
        "facts": case["facts"],
    }
    if case["mode"] == "UPDATE":
        evidence["current_authoritative_markdown_body"] = (
            context if context is not None else case["current_body"]
        )
    return json.dumps(evidence, ensure_ascii=False, separators=(",", ":"))
