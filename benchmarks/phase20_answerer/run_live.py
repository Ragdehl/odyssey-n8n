"""Run the fixed-profile Phase 20.1B grounded-answerer evidence matrix."""

from __future__ import annotations

import argparse
import json
import os
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from benchmarks.phase20_answerer.benchmark import (
    CASES_PATH,
    aggregate_rows,
    estimate_cost_usd,
    evaluate_case,
    load_cases,
    load_pricing_snapshot,
    normalize_usage,
    provider_request,
    run_identity,
    select_cases,
    validate_answer,
)

RESULTS_ROOT = Path(__file__).with_name("results")
RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{2,63}$")


@dataclass(frozen=True)
class Profile:
    """One allowlisted provider model and its exact reasoning configuration."""

    name: str
    model: str
    reasoning: str
    api_reasoning: str | None


PROFILES = (
    Profile("luna-none", "gpt-5.6-luna", "none", "none"),
    # GPT-5 nano is an older GPT-5 model and rejects the Responses reasoning field.
    Profile("nano-default", "gpt-5-nano", "default", None),
    Profile("sol-none", "gpt-5.6-sol", "none", "none"),
)
PROFILE_BY_NAME = {profile.name: profile for profile in PROFILES}


def _json_line(path: Path, value: dict[str, Any]) -> None:
    """Append one reproducible evidence row without writing provider secrets."""
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n")


def _load_metadata(run_dir: Path) -> dict[str, Any] | None:
    """Load existing run metadata when a resumable run has already started."""
    path = run_dir / "metadata.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def _assert_run_identity(metadata: dict[str, Any], expected: dict[str, Any]) -> None:
    """Refuse to resume a run whose frozen contract or matrix differs."""
    if metadata.get("identity") != expected:
        raise SystemExit("refusing resume: run identity does not match the requested benchmark")


def _profile(name: str) -> Profile:
    """Resolve one fixed profile and reject caller-selected model identifiers."""
    try:
        return PROFILE_BY_NAME[name]
    except KeyError as error:
        raise SystemExit(f"profile must be one of: {', '.join(PROFILE_BY_NAME)}") from error


def _request(profile: Profile, case: Any) -> dict[str, Any]:
    """Build the exact frozen request plus an allowlisted model configuration."""
    request = provider_request(case)
    request["model"] = profile.model
    if profile.api_reasoning is not None:
        request["reasoning"] = {"effort": profile.api_reasoning}
    return request


def _response_text(response: Any) -> str:
    """Extract only the provider's structured answer text, never hidden reasoning."""
    value = getattr(response, "output_text", None)
    if not isinstance(value, str) or not value.strip():
        raise ValueError("provider response did not contain output_text")
    return value


def _run_case(
    client: Any, profile: Profile, case: Any, pricing: dict[str, Any] | None
) -> dict[str, Any]:
    """Execute and deterministically evaluate one frozen answerer case."""
    started = time.perf_counter()
    row: dict[str, Any] = {
        "profile": profile.name,
        "model": profile.model,
        "reasoning": profile.reasoning,
        "case": case.id,
        "provider_success": False,
        "failure_category": None,
        "usage": None,
        "latency_seconds": None,
        "estimated_cost_usd": None,
    }
    try:
        response = client.responses.create(**_request(profile, case))
        row["provider_success"] = True
        row["raw_model_output"] = _response_text(response)
        row["usage"] = normalize_usage(getattr(response, "usage", None))
        row["estimated_cost_usd"] = estimate_cost_usd(row["usage"], pricing, profile.model)
        parsed = json.loads(row["raw_model_output"])
        try:
            validated = validate_answer(parsed, {item["id"] for item in case.input["items"]})
        except (TypeError, ValueError) as error:
            row["failure_category"] = "contract_invalid"
            row["validation_error"] = str(error)
        else:
            row["validated_answer"] = validated
            row["evaluation"] = evaluate_case(case, validated)
            if not row["evaluation"]["passed"]:
                row["failure_category"] = "oracle_failure"
    except json.JSONDecodeError as error:
        row["failure_category"] = "malformed_output"
        row["validation_error"] = str(error)
    except Exception as error:  # provider/auth/transport failures are not quality results
        row["failure_category"] = "provider_error"
        row["provider_error_type"] = type(error).__name__
        row["provider_error"] = str(error)[:500]
    finally:
        row["latency_seconds"] = round(time.perf_counter() - started, 3)
    return row


def _run(run_id: str, profiles: tuple[Profile, ...], cases: tuple[Any, ...], smoke: bool) -> Path:
    """Run or resume fixed evidence rows under the benchmark-owned results directory."""
    if not RUN_ID_RE.fullmatch(run_id):
        raise SystemExit("run-id must be a safe 3-64 character local identifier")
    run_dir = RESULTS_ROOT / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    pricing = load_pricing_snapshot()
    identities = [
        run_identity(profile.model, profile.reasoning, tuple(case.id for case in cases))
        for profile in profiles
    ]
    identity = {"profiles": identities, "smoke": smoke, "cases": [case.id for case in cases]}
    metadata = _load_metadata(run_dir)
    if metadata is None:
        metadata = {
            "run_id": run_id,
            "started_at": datetime.now(UTC).isoformat(),
            "smoke": smoke,
            "identity": identity,
            "pricing": pricing,
            "cases_path": str(CASES_PATH.relative_to(Path(__file__).parents[2])),
        }
        (run_dir / "metadata.json").write_text(
            json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    else:
        _assert_run_identity(metadata, identity)

    rows_path = run_dir / "rows.jsonl"
    completed = set()
    if rows_path.exists():
        for line in rows_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                completed.add((row["profile"], row["case"]))
    from openai import OpenAI

    client = OpenAI(max_retries=0)
    for profile in profiles:
        for case in cases:
            if (profile.name, case.id) in completed:
                continue
            _json_line(rows_path, _run_case(client, profile, case, pricing))
    all_rows = [
        json.loads(line)
        for line in rows_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    summary = {
        profile.name: aggregate_rows([row for row in all_rows if row["profile"] == profile.name])
        for profile in profiles
    }
    (run_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return run_dir


def main() -> None:
    """Run one smoke probe or the complete fixed Phase 20.1B candidate matrix."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    cases = load_cases()
    if args.smoke:
        cases = select_cases(cases, (cases[0].id,))
        profiles = (PROFILES[0],)
    else:
        profiles = PROFILES
    print(_run(args.run_id, profiles, cases, args.smoke))


if __name__ == "__main__":
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY is required for the live benchmark")
    main()
