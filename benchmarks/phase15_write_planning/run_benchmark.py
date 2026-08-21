"""Run the human-approved Phase 15 Sol/low benchmark exactly once per case by default."""

from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime
from typing import Any

from benchmarks.phase15_write_planning.benchmark import (
    BENCHMARK_DIR,
    load_cases,
    load_contract,
    load_oracle,
    load_planner_capabilities,
    render_prompt,
)
from benchmarks.phase15_write_planning.evaluate import evaluate_plan
from odyssey_core.planner_capabilities import build_planner_capabilities
from odyssey_core.request_planning import (
    PLANNER_MODEL,
    PLANNER_REASONING_EFFORT,
    request_plan_json_schema,
)

RESULTS_DIR = BENCHMARK_DIR / "results"
CONFIGURATIONS = {"sol": (PLANNER_MODEL, PLANNER_REASONING_EFFORT)}


def _load_schema() -> dict[str, Any]:
    """Load the canonical schema and reject drift from the frozen type snapshot.

    Returns:
        Current canonical note schema suitable for Structured Outputs.

    Raises:
        ValueError: If canonical type vocabulary drifted after benchmark preparation.
    """
    root = BENCHMARK_DIR.parents[1]
    schema = json.loads((root / "config" / "note-schema.json").read_text(encoding="utf-8"))
    if [item["id"] for item in schema["types"]] != load_contract()["canonical_types"]:
        raise ValueError("Canonical types differ from the frozen Phase 15 benchmark contract")
    if load_planner_capabilities() != build_planner_capabilities(
        schema,
        current_context={"date": "2026-08-20", "time": "10:30", "timezone": "Europe/Madrid"},
    ):
        raise ValueError("Planner capabilities differ from the frozen Phase 15 production snapshot")
    return schema


def run(run_id: str, configuration: str) -> None:
    """Call the approved planner once for every frozen case and append raw evidence.

    Args:
        run_id: New evidence-directory identifier.
        configuration: The approved configuration name, currently only ``sol``.

    Raises:
        ValueError: If a non-Sol configuration or existing run ID is supplied.
        RuntimeError: If OpenAI SDK/API access fails while explicitly executing the experiment.
    """
    if configuration not in CONFIGURATIONS:
        raise ValueError("Only the approved Sol/low configuration is available")
    directory = RESULTS_DIR / run_id
    if directory.exists():
        raise ValueError("Refusing to alter an existing benchmark run")
    try:
        from openai import OpenAI
    except ImportError as error:
        raise RuntimeError("Install the OpenAI SDK before executing the benchmark") from error
    schema, client, oracle = _load_schema(), OpenAI(), load_oracle()
    directory.mkdir(parents=True)
    model, effort = CONFIGURATIONS[configuration]
    metadata = {
        "created_at": datetime.now(UTC).isoformat(),
        "benchmark_version": "1.0.0",
        "model": model,
        "reasoning_effort": effort,
        "store": False,
        "repetitions": 1,
        "planned_calls": len(load_cases()),
    }
    (directory / "metadata.json").write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
    )
    with (directory / "raw_results.jsonl").open("x", encoding="utf-8") as stream:
        for case in load_cases():
            response = client.responses.create(
                model=model,
                reasoning={"effort": effort},
                store=False,
                input=[
                    {"role": "system", "content": render_prompt()},
                    {"role": "user", "content": case["request"]},
                ],
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "odyssey_phase15_request_plan",
                        "strict": True,
                        "schema": request_plan_json_schema(schema),
                    }
                },
            )
            try:
                payload = json.loads(response.output_text)
            except (TypeError, json.JSONDecodeError):
                status, findings, payload = "CRITICAL", [{"code": "invalid_json"}], None
            else:
                status, findings = evaluate_plan(payload, oracle[case["id"]])
            requires_human_semantic_review = bool(
                isinstance(payload, dict)
                and any(
                    isinstance(action, dict) and action.get("kind") == "write"
                    for action in payload.get("actions", [])
                )
            )
            stream.write(
                json.dumps(
                    {
                        "test_id": case["id"],
                        "request": case["request"],
                        "raw_output": response.output_text,
                        "parsed_output": payload,
                        "status": status,
                        "findings": findings,
                        "requires_human_semantic_review": requires_human_semantic_review,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
            stream.flush()
            os.fsync(stream.fileno())


def main() -> None:
    """Parse the explicit human-approved benchmark command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--configuration", required=True, choices=sorted(CONFIGURATIONS))
    arguments = parser.parse_args()
    run(arguments.run_id, arguments.configuration)


if __name__ == "__main__":
    main()
