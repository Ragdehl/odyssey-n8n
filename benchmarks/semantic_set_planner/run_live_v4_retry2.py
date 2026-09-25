"""Continue frozen v4 from immutable retry1 prerequisite evidence only."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from benchmarks.semantic_set_planner.run_live import reserve_evidence_path, run_cases  # noqa: E402
from benchmarks.semantic_set_planner.v4_gate import (  # noqa: E402
    TEACHING_EXAMPLES_PATH,
    evaluate_v4_result,
    load_v4_registry,
    v4_preflight,
)
from odyssey_core.experimental_luna_planning import OpenAILunaExperimentalPlanner  # noqa: E402

OUTPUT_PATH = ROOT / "benchmarks/.live-results/semantic-set-slice1-v4-luna-gate-retry2.jsonl"
PRIOR_OUTPUT_PATH = ROOT / "benchmarks/.live-results/semantic-set-slice1-v4-luna-gate-retry1.jsonl"
SCHEMA_PATH = ROOT / "config/note-schema.json"
CONTINUATION_CASE_IDS = ("SSET03", "SSET04", "REG01", "REG02")
_FROZEN_FILE_DIGESTS = {
    ROOT
    / "benchmarks/semantic_set_planner/v4_cases.json": "0b1ac8285122b0d565926f5c474a6414b0cbc5bd48f5122e5a06c01276128a6e",
    ROOT
    / "benchmarks/semantic_set_planner/v4_oracle.json": "a34a4c7d50042be8a26052a41f8fc67ebe79894cdbdcf6976573073f8c7537e6",
    TEACHING_EXAMPLES_PATH: "8676f9c3281f089f3be2a4437e496fec8082c9bd5300fa8ba760ebf0bcfa89d9",
    SCHEMA_PATH: "57325966f5108a6ea2a042caabfa49ec2731aa75ac68604f3bf0fb7f99b6ed48",
}


def _verify_prerequisites() -> None:
    """Refuse continuation unless frozen files and prior PASS evidence are exact."""
    if any(
        hashlib.sha256(path.read_bytes()).hexdigest() != digest
        for path, digest in _FROZEN_FILE_DIGESTS.items()
    ):
        raise SystemExit("Live semantic-set v4 continuation contract changed")
    try:
        rows = [
            json.loads(line) for line in PRIOR_OUTPUT_PATH.read_text(encoding="utf-8").splitlines()
        ]
    except (OSError, json.JSONDecodeError) as error:
        raise SystemExit("Live semantic-set v4 continuation prerequisites unavailable") from error
    if [(row.get("case_id"), row.get("classification")) for row in rows[:2]] != [
        ("SSET01", "PASS"),
        ("SSET02", "PASS"),
    ]:
        raise SystemExit("Live semantic-set v4 continuation prerequisite evidence is invalid")


def main(argv: list[str] | None = None) -> int:
    """Run only the remaining frozen v4 cases after validated immutable prerequisites."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-live-provider-calls", action="store_true")
    args = parser.parse_args(argv)
    _verify_prerequisites()
    cases, oracles = load_v4_registry()
    schema: dict[str, Any] = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    print(json.dumps(v4_preflight(schema, cases), ensure_ascii=False, sort_keys=True))
    remaining = [case for case in cases["cases"] if case["id"] in CONTINUATION_CASE_IDS]
    if (
        not args.confirm_live_provider_calls
        or not os.environ.get("OPENAI_API_KEY")
        or OUTPUT_PATH.exists()
        or tuple(case["id"] for case in remaining) != CONTINUATION_CASE_IDS
    ):
        raise SystemExit("Live semantic-set v4 continuation preflight refused")
    teaching = json.loads(TEACHING_EXAMPLES_PATH.read_text(encoding="utf-8"))["examples"]
    with reserve_evidence_path(OUTPUT_PATH) as evidence:
        planner = OpenAILunaExperimentalPlanner.from_environment(
            schema, cases["fixed_context"], teaching_examples=teaching
        )
        rows = run_cases(planner, remaining, oracles, evidence, evaluator=evaluate_v4_result)
    return int(
        not (len(rows) == len(remaining) and all(row["classification"] == "PASS" for row in rows))
    )


if __name__ == "__main__":
    raise SystemExit(main())
