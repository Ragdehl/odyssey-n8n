"""Run the approved five-case Phase 15 Sol/low targeted follow-up once."""

from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime

from benchmarks.phase15_write_planning.benchmark import render_prompt
from benchmarks.phase15_write_planning.run_benchmark import CONFIGURATIONS, _load_schema
from benchmarks.phase15_write_planning.targeted.benchmark import BENCHMARK_DIR, load_cases
from benchmarks.phase15_write_planning.targeted.evaluate import evaluate_plan
from odyssey_core.request_planning import request_plan_json_schema

RESULTS_DIR = BENCHMARK_DIR / "results"


def run(run_id: str, configuration: str) -> None:
    """Call Sol/low once per approved targeted case and preserve raw evidence.

    Args:
        run_id: New, unique targeted evidence identifier.
        configuration: The approved configuration name, ``sol``.

    Raises:
        ValueError: If configuration or run ID is not approved.
        RuntimeError: If the OpenAI SDK is unavailable during explicit execution.
    """
    if configuration not in CONFIGURATIONS:
        raise ValueError("Only the approved Sol/low configuration is available")
    directory = RESULTS_DIR / run_id
    if directory.exists():
        raise ValueError("Refusing to alter an existing targeted benchmark run")
    try:
        from openai import OpenAI
    except ImportError as error:
        raise RuntimeError("Install the OpenAI SDK before executing the benchmark") from error
    schema, client = _load_schema(), OpenAI()
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
                status, findings = evaluate_plan(case["id"], payload)
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
    """Parse the explicit human-approved targeted benchmark arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--configuration", required=True, choices=sorted(CONFIGURATIONS))
    arguments = parser.parse_args()
    run(arguments.run_id, arguments.configuration)


if __name__ == "__main__":
    main()
