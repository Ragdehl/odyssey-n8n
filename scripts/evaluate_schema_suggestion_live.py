"""Strict, synthetic-only, billable schema prompt evaluation. Requires explicit opt-in.

Never reads user vault, touches Odyssey deployments, publishes schemas, or logs keys.
Record results in a caller-supplied local temp JSON file (no private content).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MATRICES = {
    "v1": (ROOT / "tests/fixtures/schema_suggestion/evaluation_v1.json", 24),
    "v2_holdout": (ROOT / "tests/fixtures/schema_suggestion/evaluation_v2_holdout.json", 12),
    "v4_holdout": (ROOT / "tests/fixtures/schema_suggestion/evaluation_v4_holdout.json", 16),
    "v5_holdout": (ROOT / "tests/fixtures/schema_suggestion/evaluation_v5_holdout.json", 12),
}
CONFIRM_FLAG = "ODYSSEY_SCHEMA_LIVE_EVAL_APPROVED"
MAX_CALLS = 24
MAX_OUTPUT_TOKENS_PER_CALL = 1200
MAX_INPUT_CHARS = 1200


def accepted_case_decisions(case: dict[str, Any]) -> tuple[str, ...]:
    """Freeze known safe alternatives BEFORE model calls, never after scoring.

    Only a hypothetical CLARIFY vs ABSTAIN can have multiple accepted labels.
    ADD_TYPE/ADD_PROPERTY and REUSE cannot be silently added as alternatives.
    Other matrices remain strict exact-label baselines.
    """
    expected = case["expected"]
    alternative = case.get("also_safe_decision")
    if alternative is None:
        return (expected,)
    if expected != "CLARIFY" or alternative != "ABSTAIN":
        raise ValueError("Unsupported alternative evaluation outcome")
    return (expected, alternative)


def decision_score_only(
    expected: str, actual: str, *, accepted: tuple[str, ...] | None = None
) -> tuple[bool, str]:
    """Operation matching is NOT semantic approval of a target or property."""
    choices = accepted if accepted is not None else (expected,)
    if expected not in choices:
        raise ValueError("Frozen expected outcome missing from accepted choices")
    return actual in choices, (
        "rejected_before_semantic_review" if actual == "INVALID" else "awaiting_independent_review"
    )


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


def run(*, max_cases: int, first_index: int, output: Path, matrix_name: str = "v1") -> int:
    if os.environ.get(CONFIRM_FLAG) != "1":
        raise ValueError("Explicit bounded synthetic-only live-model evaluation approval missing")
    if os.environ.get("ODYSSEY_DEPLOYMENT_ENV") != "DEV_EVAL":
        raise ValueError("Only isolated DEV_EVAL process can run this evaluator")
    if matrix_name not in MATRICES:
        raise ValueError("Unknown frozen evaluation matrix")
    matrix_path, matrix_count = MATRICES[matrix_name]
    if not 1 <= max_cases <= MAX_CALLS or not 0 <= first_index < matrix_count:
        raise ValueError("Invalid call bound")
    if max_cases + first_index > matrix_count:
        raise ValueError("Call budget exceeds matrix")
    if (
        not output.is_absolute()
        or not output.parent.is_dir()
        or not output.parent.resolve().is_relative_to(Path("/tmp"))
    ):
        raise ValueError("Output must be an existing absolute temporary directory")
    if output.exists() or output.is_symlink():
        raise ValueError("Refusing to overwrite existing evaluation evidence")
    # Support both `python scripts/...` and `python -m scripts....`; avoid
    # loading providers until every explicit gate and output preflight passed.
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from odyssey_apps.events.schema import EVENT_SCHEMA_EXTENSION
    from odyssey_apps.tasks.schema import TASK_SCHEMA_EXTENSION
    from odyssey_runtime.conversation_gateway import OpenAIConversationGateway
    from odyssey_runtime.schema_suggestion import (
        SCHEMA_SUGGESTION_INSTRUCTIONS,
        SUGGESTION_SCHEMA,
        SchemaSuggestionService,
    )
    from odyssey_runtime.user_schema_registry import UserSchemaRegistry

    matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
    cases = matrix["cases"]
    assert len(cases) == matrix_count
    selected = cases[first_index : first_index + max_cases]
    assert all(0 < len(case["source"]) <= MAX_INPUT_CHARS for case in selected)
    # Preflight the complete frozen matrix: refuse to run any paid calls if an
    # alternative outcome is invalid or would accidentally permit mutation.
    for case in cases:
        accepted_case_decisions(case)

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
                accepted = accepted_case_decisions(case)
                decision_match, semantic_status = decision_score_only(
                    case["expected"], actual, accepted=accepted
                )
                record.update(
                    actual=actual,
                    decision_match=decision_match,
                    accepted_decisions=list(accepted),
                    semantic_status=semantic_status,
                    validated=True,
                )
                if result.get("change"):
                    record["draft_change"] = result["change"]
                if result.get("reuse_type_id"):
                    record["reuse_type_id"] = result["reuse_type_id"]
            except Exception as error:
                # Do not print provider responses, credentials or private exception internals.
                record.update(
                    actual="INVALID",
                    decision_match=False,
                    semantic_status="rejected_before_semantic_review",
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
                f"{'DECISION_MATCH' if record['decision_match'] else 'DECISION_MISMATCH'} "
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
        "matrix_name": matrix_name,
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
        "decision_match_count": sum(item["decision_match"] for item in results),
        "semantic_pass_count": None,
        "semantic_review_complete": False,
        "invalid_count": sum(not item["validated"] for item in results),
        "results": results,
        "contains_only_synthetic_prompts": True,
        "real_provider": True,
        "changed_user_data": False,
    }
    # O_EXCL + O_NOFOLLOW protect prior evidence against races and symlinks.
    fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write(json.dumps(results_summary, ensure_ascii=False, indent=2) + "\n")
    print(
        "LIVE_EVAL",
        "decision_matches",
        results_summary["decision_match_count"],
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
    parser.add_argument("--matrix", choices=sorted(MATRICES), default="v1")
    parser.add_argument("--max-cases", type=int, required=True)
    parser.add_argument("--first-index", type=int, default=0)
    parser.add_argument("--output", type=Path, required=True)
    options = parser.parse_args()
    raise SystemExit(
        run(
            max_cases=options.max_cases,
            first_index=options.first_index,
            output=options.output,
            matrix_name=options.matrix,
        )
    )
