"""Run the focused Phase 16.5C writer-link regression against the production writer boundary."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from odyssey_core.materialization import (
    WRITER_CONTEXT_MODE,
    WRITER_MODEL,
    WRITER_REASONING_EFFORT,
    OpenAILunaWriter,
    WriterRequest,
    _validate_bound_wikilinks,
    apply_writer_operations,
    validate_writer_output,
)

BENCHMARK_DIR = Path(__file__).resolve().parent
CASES_PATH = BENCHMARK_DIR / "cases.json"


def load_cases() -> list[dict[str, Any]]:
    """Load the six frozen focused writer-link cases."""
    payload = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    cases = payload.get("cases")
    if not isinstance(cases, list) or len(cases) != 6:
        raise ValueError("Phase 16.5C benchmark requires exactly six cases")
    return cases


def run_case(case: dict[str, Any], writer: OpenAILunaWriter) -> dict[str, Any]:
    """Execute and deterministically validate one production writer call."""
    request = WriterRequest(
        note_id=case["note_id"],
        note_type=case["note_type"],
        intent=case["intent"],
        facts=tuple(case["facts"]),
        current_body=case["current_body"],
    )
    record: dict[str, Any] = {
        "id": case["id"],
        "request": {
            "note_id": request.note_id,
            "note_type": request.note_type,
            "intent": request.intent,
            "facts": list(request.facts),
            "current_body": request.current_body,
        },
    }
    try:
        output = writer.write(request)
        operations = validate_writer_output(output, request.current_body)
        rendered_body = apply_writer_operations(request.current_body, operations)
        _validate_bound_wikilinks(
            request.current_body, rendered_body, request.facts, request.intent
        )
    except Exception as error:  # benchmark must retain the failed case rather than abort the run
        record.update(
            {
                "pass": False,
                "error_type": type(error).__name__,
                "error": str(error),
            }
        )
        return record
    record.update(
        {
            "pass": True,
            "provider_output": output,
            "rendered_body": rendered_body,
        }
    )
    return record


def main() -> int:
    """Run all frozen cases and retain exact requests plus provider outputs."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    output_dir = args.output_dir or (
        BENCHMARK_DIR
        / "results"
        / f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}_phase16-5c-luna-medium"
    )
    output_dir.mkdir(parents=True, exist_ok=False)

    writer = OpenAILunaWriter()
    records = [run_case(case, writer) for case in load_cases()]
    raw_path = output_dir / "raw_results.jsonl"
    raw_path.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
    )
    passed = sum(bool(record["pass"]) for record in records)
    metadata = {
        "phase": "16.5C",
        "model": WRITER_MODEL,
        "reasoning": WRITER_REASONING_EFFORT,
        "context_mode": WRITER_CONTEXT_MODE,
        "store": False,
        "calls": len(records),
        "passed": passed,
        "failed": len(records) - passed,
        "selection_rerun": False,
        "sol_calls": 0,
        "cases_path": str(CASES_PATH.relative_to(BENCHMARK_DIR)),
    }
    (output_dir / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return 0 if passed == len(records) else 1


if __name__ == "__main__":
    raise SystemExit(main())
