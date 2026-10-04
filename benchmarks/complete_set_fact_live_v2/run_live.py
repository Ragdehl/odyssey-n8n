"""One-shot Sol gate proving the production fallback uses the shared semantic frontend."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from odyssey_core.domain_interpretation import (
    TEMPORAL_REFERENCE_EVIDENCE,
    DomainEvidence,
    DomainInterpretation,
)
from odyssey_core.experimental_luna_planning import (
    LUNA_EXPERIMENT_MAX_OUTPUT_TOKENS,
    OpenAILunaExperimentalPlanner,
)
from odyssey_core.request_planning import (
    PLANNER_MODEL,
    PLANNER_REASONING_EFFORT,
    PlannerClarification,
    RequestPlan,
    WriteAction,
)

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
MATRIX = HERE / "matrix.json"
RESULTS = HERE / "results"
SCHEMA = ROOT / "config/note-schema.json"
MATRIX_SHA256 = "9d35be2fb16e060d99b38a61f717ac0c52b3f06269a4cb8cf4f263939f64b915"
AUTH_ENV = "ODYSSEY_RUN_COMPLETE_SET_FACT_V2"
MAX_CALLS = 1
PROPOSED_CEILING_USD = 0.23
REGIONAL_MULTIPLIER = 1.10
SOL_INPUT_RATE = 4.0
SOL_OUTPUT_RATE = 20.0
INPUT_TOKEN_ENVELOPE = 40_000
SOURCE_FILES = (
    "odyssey_core/experimental_luna_planning.py",
    "odyssey_core/cost_aware_planning.py",
    "odyssey_core/semantic_write.py",
    "odyssey_core/request_planning.py",
    "odyssey_core/application.py",
    "odyssey_core/reference_preflight.py",
)


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source_digest() -> str:
    digest = hashlib.sha256()
    for relative in SOURCE_FILES:
        digest.update(relative.encode())
        digest.update(b"\0")
        digest.update((ROOT / relative).read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _budget_upper() -> float:
    standard = (
        INPUT_TOKEN_ENVELOPE * SOL_INPUT_RATE + LUNA_EXPERIMENT_MAX_OUTPUT_TOKENS * SOL_OUTPUT_RATE
    ) / 1_000_000
    return standard * REGIONAL_MULTIPLIER


class RecordingResponses:
    """Record exactly one Sol provider attempt and enforce the approved cost ceiling."""

    def __init__(self, responses: Any) -> None:
        self._responses = responses
        self.records: list[dict[str, Any]] = []
        self.attempts = 0

    def create(self, **kwargs: Any) -> Any:
        if self.attempts >= MAX_CALLS:
            raise RuntimeError("live gate call ceiling reached")
        self.attempts += 1
        response = self._responses.create(**kwargs)
        usage = getattr(response, "usage", None)
        row = {
            "model": kwargs.get("model"),
            "reasoning_effort": (kwargs.get("reasoning") or {}).get("effort"),
            "max_output_tokens": kwargs.get("max_output_tokens"),
            "input_tokens": int(getattr(usage, "input_tokens", 0) or 0),
            "output_tokens": int(getattr(usage, "output_tokens", 0) or 0),
            "response_id": getattr(response, "id", None),
            "status": getattr(response, "status", None),
            "output_text": getattr(response, "output_text", None),
            "format_name": (((kwargs.get("text") or {}).get("format") or {}).get("name")),
        }
        self.records.append(row)
        if self.estimated_cost(regional=True) > PROPOSED_CEILING_USD:
            raise RuntimeError("authorized live-gate cost ceiling exceeded")
        return response

    def estimated_cost(self, *, regional: bool) -> float:
        total = sum(
            row["input_tokens"] * SOL_INPUT_RATE / 1_000_000
            + row["output_tokens"] * SOL_OUTPUT_RATE / 1_000_000
            for row in self.records
        )
        return total * (REGIONAL_MULTIPLIER if regional else 1.0)


def _interpretation(case: dict[str, Any]) -> DomainInterpretation:
    return DomainInterpretation(
        "temporal",
        case["source"],
        "TEMPORAL_RESOLUTION",
        tuple(
            DomainEvidence(TEMPORAL_REFERENCE_EVIDENCE, text, value)
            for text, value in case["evidence"]
        ),
    )


def _plan_actual(result: Any) -> dict[str, Any]:
    if isinstance(result, PlannerClarification):
        return {"kind": "clarify", "footprint": "", "anchors": []}
    assert isinstance(result, RequestPlan)
    units: list[dict[str, Any]] = []
    anchors: list[str] = []
    for action in result.actions:
        if not isinstance(action, WriteAction):
            continue
        for unit in action.units:
            unit_anchors = [
                anchor.value for group in unit.fact_temporal_anchors for anchor in group
            ]
            anchors.extend(unit_anchors)
            units.append(
                {
                    "target": {"query": unit.target.query, "type": unit.target.type},
                    "facts": list(unit.facts),
                    "references": [reference.mention for reference in unit.references],
                    "anchors": unit_anchors,
                }
            )
    footprint = json.dumps(units, ensure_ascii=False, separators=(",", ":")).casefold()
    return {"kind": "plan", "units": units, "footprint": footprint, "anchors": anchors}


def _raw_extent(output_text: str | None, phrase: str) -> str | None:
    if not output_text:
        return None
    try:
        payload = json.loads(output_text)
    except json.JSONDecodeError:
        return None
    wanted = phrase.strip().casefold()
    found: list[str] = []

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            if value.get("kind") == "identity":
                text = value.get("text")
                identity = value.get("identity")
                if (
                    isinstance(text, str)
                    and text.strip().casefold() == wanted
                    and isinstance(identity, dict)
                ):
                    scope = identity.get("candidate_scope")
                    if isinstance(scope, dict) and isinstance(scope.get("extent"), str):
                        found.append(scope["extent"])
            for item in value.values():
                visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    visit(payload)
    return found[0] if len(set(found)) == 1 else None


def _preflight(*, live: bool) -> tuple[dict[str, Any], dict[str, Any]]:
    matrix = _load(MATRIX)
    if _sha(MATRIX) != MATRIX_SHA256:
        raise SystemExit("frozen matrix digest changed")
    if _budget_upper() > PROPOSED_CEILING_USD:
        raise SystemExit("proposed cost envelope changed")
    if subprocess.run(["git", "-C", str(ROOT), "diff", "--check"], check=False).returncode != 0:
        raise SystemExit("git diff --check failed")
    if live:
        if os.environ.get(AUTH_ENV) != "1":
            raise SystemExit(f"refusing live calls without {AUTH_ENV}=1")
        if not os.environ.get("OPENAI_API_KEY"):
            raise SystemExit("OPENAI_API_KEY unavailable")
        RESULTS.mkdir(parents=True, exist_ok=True)
        if any(RESULTS.glob("*.json")):
            raise SystemExit("complete-set v2 evidence already exists; refusing a second run")
    return matrix, _load(SCHEMA)


def run(*, preflight_only: bool = False) -> int:
    matrix, schema = _preflight(live=not preflight_only)
    if preflight_only:
        print("sol_calls=1")
        print(f"max_calls={MAX_CALLS}")
        print(f"budget_upper_usd={_budget_upper():.8f}")
        print(f"proposed_ceiling_usd={PROPOSED_CEILING_USD:.8f}")
        print(f"matrix_sha256={MATRIX_SHA256}")
        print(f"source_digest={_source_digest()}")
        print("shared_semantic_frontend=True")
        print("mutation_authority=False")
        print("live_calls=0")
        return 0

    from openai import OpenAI

    base = OpenAI(max_retries=0, timeout=30.0)
    recorder = RecordingResponses(base.responses)
    case = matrix["case"]
    planner = OpenAILunaExperimentalPlanner(
        SimpleNamespace(responses=recorder),
        schema,
        matrix["current_context"],
        domain_interpretation=_interpretation(case),
        model=PLANNER_MODEL,
        reasoning_effort=PLANNER_REASONING_EFFORT,
        max_output_tokens=LUNA_EXPERIMENT_MAX_OUTPUT_TOKENS,
    )
    try:
        actual = _plan_actual(planner.plan(case["source"]))
        extent = _raw_extent(recorder.records[-1]["output_text"], case["phrase"])
        passed = (
            recorder.attempts == 1
            and recorder.records[-1]["model"] == "gpt-5.6-sol"
            and recorder.records[-1]["reasoning_effort"] == "low"
            and recorder.records[-1]["max_output_tokens"] == LUNA_EXPERIMENT_MAX_OUTPUT_TOKENS
            and extent == case["expect_extent"]
            and all(token.casefold() in actual["footprint"] for token in case["must_contain"])
            and actual["anchors"] == case["expect_anchors"]
        )
        error = None
    except Exception as exc:
        actual, extent, passed, error = {}, None, False, type(exc).__name__

    artifact = {
        "version": 2,
        "head": subprocess.check_output(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True
        ).strip(),
        "dirty_worktree": bool(
            subprocess.check_output(
                ["git", "-C", str(ROOT), "status", "--porcelain"], text=True
            ).strip()
        ),
        "matrix_sha256": MATRIX_SHA256,
        "source_digest": _source_digest(),
        "provider_attempts": recorder.attempts,
        "automatic_retries": 0,
        "mutation_authority": False,
        "shared_semantic_frontend": True,
        "budget_upper_usd": _budget_upper(),
        "estimated_regional_cost_usd": recorder.estimated_cost(regional=True),
        "passed": passed,
        "row": {
            "id": case["id"],
            "passed": passed,
            "actual": actual,
            "raw_extent": extent,
            "expected_extent": case["expect_extent"],
            "error": error,
        },
        "provider_records": recorder.records,
    }
    output = RESULTS / f"{artifact['source_digest'][:12]}.json"
    output.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"provider_attempts={artifact['provider_attempts']}")
    print(f"budget_upper_usd={artifact['budget_upper_usd']:.8f}")
    print(f"estimated_regional_cost_usd={artifact['estimated_regional_cost_usd']:.8f}")
    print(f"passed={artifact['passed']}")
    print(
        f"sol {case['id']}: {'PASS' if passed else 'FAIL'} extent={extent!r}{(' ' + error) if error else ''}"
    )
    print(f"artifact={output.relative_to(ROOT)}")
    return 0 if passed else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--preflight", action="store_true")
    args = parser.parse_args()
    raise SystemExit(run(preflight_only=args.preflight))
