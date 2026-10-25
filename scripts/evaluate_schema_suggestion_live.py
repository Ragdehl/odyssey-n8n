"""Strict, synthetic-only, billable schema prompt evaluation. Requires explicit opt-in.

Never reads user vault, touches Odyssey deployments, publishes schemas, or logs keys.
Record results in a caller-supplied local temp JSON file (no private content).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any

from odyssey_apps.events.schema import EVENT_SCHEMA_EXTENSION
from odyssey_apps.tasks.schema import TASK_SCHEMA_EXTENSION
from odyssey_runtime.conversation_gateway import OpenAIConversationGateway
from odyssey_runtime.schema_suggestion import (
    SCHEMA_SUGGESTION_INSTRUCTIONS,
    SUGGESTION_SCHEMA,
    SchemaSuggestionService,
)
from odyssey_runtime.user_schema_registry import UserSchemaRegistry

ROOT = Path(__file__).resolve().parents[1]
MATRIX = ROOT / "tests/fixtures/schema_suggestion/evaluation_v1.json"
CONFIRM_FLAG = "ODYSSEY_SCHEMA_LIVE_EVAL_APPROVED"
MAX_CALLS = 24
MAX_OUTPUT_TOKENS_PER_CALL = 1200
MAX_INPUT_CHARS = 1200


class RecordingResponses:
    def __init__(self, underlying: Any):
        self._underlying = underlying
        self.calls = 0
        self.usage: list[dict[str, int]] = []
        self.duration_seconds: list[float] = []
        self.last_text: str | None = None

    def create(self, **kwargs: Any) -> Any:
        assert kwargs["max_output_tokens"] <= MAX_OUTPUT_TOKENS_PER_CALL
        assert kwargs["model"] == "gpt-6-luna"
        assert kwargs["reasoning"] == {"effort": "low"}
        assert kwargs["store"] is False
        assert "tools" not in kwargs
        self.calls += 1
        start = time.perf_counter()
        try:
            response = self._underlying.create(**kwargs)
        finally:
            self.duration_seconds.append(round(time.perf_counter() - start, 3))
        # All model inputs are synthetic. Save the strict JSON output only to
        # the private temporary evidence file so rejected proposals are auditable.
        self.last_text = getattr(response, "output_text", None)
        usage = getattr(response, "usage", None)
        self.usage.append(
            {
                "input_tokens": int(getattr(usage, "input_tokens", 0) or 0),
                "output_tokens": int(getattr(usage, "output_tokens", 0) or 0),
            }
        )
        return response


class RecordingClient:
    def __init__(self, upstream: Any):
        self.responses = RecordingResponses(upstream.responses)


def run(*, max_cases: int, first_index: int, output: Path) -> int:
    if os.environ.get(CONFIRM_FLAG) != "1":
        raise ValueError("Explicit bounded synthetic-only live-model evaluation approval missing")
    if os.environ.get("ODYSSEY_DEPLOYMENT_ENV") != "DEV_EVAL":
        raise ValueError("Only isolated DEV_EVAL process can run this evaluator")
    if not 1 <= max_cases <= MAX_CALLS or not 0 <= first_index < MAX_CALLS:
        raise ValueError("Invalid call bound")
    if max_cases + first_index > MAX_CALLS:
        raise ValueError("Call budget exceeds matrix")
    if not output.is_absolute() or not output.parent.is_dir():
        raise ValueError("Output must be an existing absolute, local temporary path")
    matrix = json.loads(MATRIX.read_text(encoding="utf-8"))
    cases = matrix["cases"]
    assert len(cases) == MAX_CALLS
    selected = cases[first_index : first_index + max_cases]
    assert all(0 < len(case["source"]) <= MAX_INPUT_CHARS for case in selected)

    # Same provider and schema as production composition, without installing it
    # in either DEV or PROD. No private user context ever enters the prompt.
    from openai import OpenAI

    provider = RecordingClient(OpenAI(max_retries=0, timeout=30.0))
    gateway = OpenAIConversationGateway(provider)
    if gateway.model != matrix["model"] or gateway.reasoning_effort != matrix["reasoning_effort"]:
        raise ValueError("Unreviewed model or reasoning effort")
    results = []
    with tempfile.TemporaryDirectory(prefix="odyssey-schema-eval-") as location:
        schema_path = ROOT / "config/note-schema.json"
        canonical = json.loads(schema_path.read_text(encoding="utf-8"))
        registry = UserSchemaRegistry(
            Path(location), canonical, (TASK_SCHEMA_EXTENSION, EVENT_SCHEMA_EXTENSION)
        )
        service = SchemaSuggestionService(gateway)
        for case in selected:
            provider.responses.last_text = None
            started = time.perf_counter()
            record: dict[str, Any] = {"id": case["id"], "expected": case["expected"]}
            try:
                result = service.suggest(case["source"], registry, expected_revision=0)
                decision = result["decision"]
                actual = (
                    result["change"]["operation"].upper() if decision == "PROPOSE" else decision
                )
                record.update(
                    actual=actual, pass_semantics=(actual == case["expected"]), validated=True
                )
                if result.get("change"):
                    record["draft_change"] = result["change"]
                if result.get("reuse_type_id"):
                    record["reuse_type_id"] = result["reuse_type_id"]
            except Exception as error:
                # Do not print provider responses, credentials or private exception internals.
                record.update(
                    actual="INVALID",
                    pass_semantics=False,
                    validated=False,
                    error_type=type(error).__name__,
                )
                if type(error).__name__ in {"SchemaSuggestionError", "UserSchemaError"}:
                    record["error_category"] = str(error)[:180]
            if provider.responses.last_text is not None:
                try:
                    record["model_json"] = json.loads(provider.responses.last_text)
                except (ValueError, TypeError):
                    record["model_json_type"] = "not-json"
            record["elapsed_seconds"] = round(time.perf_counter() - started, 3)
            results.append(record)
            print(
                f"CASE {len(results):02d}/{len(selected)} {case['id']}: "
                f"{record['actual']} expected={record['expected']} "
                f"{'PASS' if record['pass_semantics'] else 'MISMATCH'} "
                f"latency={record['elapsed_seconds']}s",
                flush=True,
            )
            # No replay/retry, because retrying may hide an unstable/failed
            # response and cost more. One bounded call per example.
            if provider.responses.calls != len(results):
                raise RuntimeError("Case call budget anomaly")
            assert registry.snapshot()[0] == 0
    results_summary = {
        "suite_version": matrix["suite_version"],
        "prompt_sha256": hashlib.sha256(SCHEMA_SUGGESTION_INSTRUCTIONS.encode()).hexdigest(),
        "schema_sha256": hashlib.sha256(
            json.dumps(SUGGESTION_SCHEMA, sort_keys=True).encode()
        ).hexdigest(),
        "model": gateway.model,
        "reasoning_effort": gateway.reasoning_effort,
        "max_cases": max_cases,
        "first_index": first_index,
        "attempted_calls": provider.responses.calls,
        "usage": provider.responses.usage,
        "pass_count": sum(item["pass_semantics"] for item in results),
        "invalid_count": sum(not item["validated"] for item in results),
        "results": results,
        "contains_only_synthetic_prompts": True,
        "real_provider": True,
        "changed_user_data": False,
    }
    output.write_text(
        json.dumps(results_summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    output.chmod(0o600)
    print(
        "LIVE_EVAL",
        results_summary["pass_count"],
        "/",
        len(results),
        "tokens_in",
        sum(x["input_tokens"] for x in provider.responses.usage),
        "tokens_out",
        sum(x["output_tokens"] for x in provider.responses.usage),
        "record",
        str(output),
        flush=True,
    )
    return 0  # The evidence can contain mismatches; exit 0 means test ran, not pass.


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-cases", type=int, required=True)
    parser.add_argument("--first-index", type=int, default=0)
    parser.add_argument("--output", type=Path, required=True)
    options = parser.parse_args()
    raise SystemExit(
        run(max_cases=options.max_cases, first_index=options.first_index, output=options.output)
    )
