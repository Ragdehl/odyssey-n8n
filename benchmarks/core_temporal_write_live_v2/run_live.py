"""One-shot no-mutation focused Core semantic-write regression gate."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from collections import Counter
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
from odyssey_core.request_planning import PlannerClarification, RequestPlan, WriteAction

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
MATRIX = HERE / "matrix.json"
RESULTS = HERE / "results"
SCHEMA = ROOT / "config/note-schema.json"
MATRIX_SHA256 = "3600ad45d021b29e1819274118c9cbfa29d54ee1b82ad85900deaca1a5643e92"
AUTH_ENV = "ODYSSEY_RUN_CORE_TEMPORAL_WRITE_V2"
MAX_CALLS = 4
PROPOSED_CEILING_USD = 0.05
REGIONAL_MULTIPLIER = 1.10
INPUT_TOKEN_ENVELOPE = 40_000
RATES = {"gpt-5.6-luna": (0.20, 1.20)}
SOURCE_FILES = (
    "odyssey_core/experimental_luna_planning.py",
    "odyssey_core/request_planning.py",
    "odyssey_core/semantic_write.py",
    "odyssey_core/domain_interpretation.py",
    "odyssey_core/temporal.py",
    "odyssey_core/temporal_resolution.py",
)


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source_digest() -> str:
    digest = hashlib.sha256()
    for relative in SOURCE_FILES:
        path = ROOT / relative
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _budget_upper(matrix: dict[str, Any]) -> float:
    calls = len(matrix["cases"])
    input_rate, output_rate = RATES["gpt-5.6-luna"]
    standard = (
        calls
        * (INPUT_TOKEN_ENVELOPE * input_rate + LUNA_EXPERIMENT_MAX_OUTPUT_TOKENS * output_rate)
        / 1_000_000
    )
    return standard * REGIONAL_MULTIPLIER


class RecordingResponses:
    """Record provider usage while enforcing the one-shot call and cost ceilings."""

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
        self.records.append(
            {
                "model": kwargs.get("model"),
                "reasoning_effort": (kwargs.get("reasoning") or {}).get("effort"),
                "input_tokens": int(getattr(usage, "input_tokens", 0) or 0),
                "output_tokens": int(getattr(usage, "output_tokens", 0) or 0),
                "response_id": getattr(response, "id", None),
                "status": getattr(response, "status", None),
                "output_text": getattr(response, "output_text", None),
            }
        )
        if self.estimated_cost(regional=True) > PROPOSED_CEILING_USD:
            raise RuntimeError("authorized live-gate cost ceiling exceeded")
        return response

    def estimated_cost(self, *, regional: bool) -> float:
        total = 0.0
        for row in self.records:
            input_rate, output_rate = RATES[row["model"]]
            total += row["input_tokens"] * input_rate / 1_000_000
            total += row["output_tokens"] * output_rate / 1_000_000
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


def _core_actual(result: Any) -> dict[str, Any]:
    if isinstance(result, PlannerClarification):
        return {"kind": "clarify", "code": result.code, "footprint": "", "anchors": []}
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
                    "target": {
                        "entity": unit.target.entity,
                        "query": unit.target.query,
                        "type": unit.target.type,
                        "self_target": unit.target.self_target,
                    },
                    "facts": list(unit.facts),
                    "references": [
                        {
                            "mention": ref.mention,
                            "role": ref.role,
                            "query": ref.selection.query if ref.selection else None,
                        }
                        for ref in unit.references
                    ],
                    "reference_lookup_only": unit.reference_lookup_only,
                    "anchors": unit_anchors,
                }
            )
    footprint = json.dumps(units, ensure_ascii=False, separators=(",", ":")).casefold()
    return {"kind": "plan", "units": units, "footprint": footprint, "anchors": anchors}


def _preflight(*, require_live: bool) -> tuple[dict[str, Any], dict[str, Any]]:
    matrix = _load(MATRIX)
    if _sha(MATRIX) != MATRIX_SHA256:
        raise SystemExit("frozen matrix digest changed")
    if matrix.get("version") != 2 or len(matrix.get("cases", [])) != MAX_CALLS:
        raise SystemExit("frozen gate call count/version changed")
    if _budget_upper(matrix) > PROPOSED_CEILING_USD:
        raise SystemExit("proposed cost envelope changed")
    if subprocess.run(["git", "-C", str(ROOT), "diff", "--check"], check=False).returncode != 0:
        raise SystemExit("git diff --check failed")
    if require_live:
        if os.environ.get(AUTH_ENV) != "1":
            raise SystemExit(f"refusing live calls without {AUTH_ENV}=1")
        if not os.environ.get("OPENAI_API_KEY"):
            raise SystemExit("OPENAI_API_KEY unavailable")
        RESULTS.mkdir(parents=True, exist_ok=True)
        if any(RESULTS.glob("*.json")):
            raise SystemExit("v2 live evidence already exists; refusing a second run")
    return matrix, _load(SCHEMA)


def preflight() -> int:
    matrix, _schema = _preflight(require_live=False)
    print(f"core_calls={len(matrix['cases'])}")
    print(f"max_calls={MAX_CALLS}")
    print(f"budget_upper_usd={_budget_upper(matrix):.8f}")
    print(f"proposed_ceiling_usd={PROPOSED_CEILING_USD:.8f}")
    print(f"matrix_sha256={_sha(MATRIX)}")
    print(f"source_digest={_source_digest()}")
    print("mutation_authority=False")
    print("live_calls=0")
    return 0


def run() -> int:
    matrix, schema = _preflight(require_live=True)
    from openai import OpenAI

    base = OpenAI(max_retries=0, timeout=30.0)
    recorder = RecordingResponses(base.responses)
    client = SimpleNamespace(responses=recorder)
    rows: list[dict[str, Any]] = []

    for case in matrix["cases"]:
        planner = OpenAILunaExperimentalPlanner(
            client,
            schema,
            matrix["current_context"],
            domain_interpretation=_interpretation(case),
        )
        try:
            result = planner.plan(case["source"])
            actual = _core_actual(result)
            footprint_ok = all(
                token.casefold() in actual["footprint"] for token in case["must_contain"]
            )
            anchors_ok = Counter(actual["anchors"]) == Counter(case["expect_anchors"])
            passed = actual["kind"] == "plan" and footprint_ok and anchors_ok
            error = None
        except Exception as exc:
            actual, passed, error = {}, False, type(exc).__name__
        rows.append(
            {
                "id": case["id"],
                "passed": passed,
                "actual": actual,
                "expect_anchors": case["expect_anchors"],
                "must_contain": case["must_contain"],
                "error": error,
            }
        )

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
        "matrix_sha256": _sha(MATRIX),
        "source_digest": _source_digest(),
        "provider_attempts": recorder.attempts,
        "automatic_retries": 0,
        "mutation_authority": False,
        "budget_upper_usd": _budget_upper(matrix),
        "estimated_standard_cost_usd": recorder.estimated_cost(regional=False),
        "estimated_regional_cost_usd": recorder.estimated_cost(regional=True),
        "passed": recorder.attempts == MAX_CALLS and all(row["passed"] for row in rows),
        "rows": rows,
        "provider_records": recorder.records,
    }
    output = RESULTS / f"{artifact['source_digest'][:12]}.json"
    output.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"provider_attempts={artifact['provider_attempts']}")
    print(f"budget_upper_usd={artifact['budget_upper_usd']:.8f}")
    print(f"estimated_regional_cost_usd={artifact['estimated_regional_cost_usd']:.8f}")
    print(f"passed={artifact['passed']}")
    for row in rows:
        suffix = f" {row['error']}" if row["error"] else ""
        print(f"core {row['id']}: {'PASS' if row['passed'] else 'FAIL'}{suffix}")
    print(f"artifact={output.relative_to(ROOT)}")
    return 0 if artifact["passed"] else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preflight", action="store_true")
    args = parser.parse_args()
    return preflight() if args.preflight else run()


if __name__ == "__main__":
    raise SystemExit(main())
