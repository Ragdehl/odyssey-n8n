"""One-shot Luna gate for Core's parts-only fixed-destination semantic enrichment contract."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from odyssey_core.experimental_luna_planning import (
    LUNA_EXPERIMENT_MODEL,
    LUNA_EXPERIMENT_REASONING_EFFORT,
    OpenAILunaExperimentalPlanner,
)
from odyssey_core.fixed_fact_capture import (
    FIXED_FACT_ENRICHMENT_MAX_OUTPUT_TOKENS,
    fixed_fact_enrichment_json_schema,
    render_fixed_fact_enrichment_prompt,
)
from odyssey_core.semantic_write import (
    CandidateScopeExtent,
    IdentityBinding,
    IdentityPart,
    LiteralPart,
    SemanticFact,
)

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "config/note-schema.json"
CASES_PATH = Path(__file__).with_name("cases.json")
RESULTS_DIR = Path(__file__).resolve().parent / "results"
AUTH_ENV = "ODYSSEY_RUN_FIXED_FACT_ENRICHMENT_V1"
PRODUCTION_MODEL = "gpt-5.6-luna"
REASONING_EFFORT = "low"
MAX_CALLS = 3
AUTHORIZED_CEILING_USD = Decimal("0.012")
CASES_SHA256 = "fc1f53c35be88c2136524dc7b732371d78efad1a721bce19fb3d6c250b8a46da"
PROMPT_SHA256 = "ac71eca521f29079d2f757095576dd7f76335758dee9172c185248cdda321322"
PROVIDER_SCHEMA_SHA256 = "f8c259623f1f30e2a9bf8598d64c304dc2428f213d6a773997912c248ad1d687"
INPUT_OVERHEAD_BYTES = 1024
STANDARD_INPUT_USD_PER_M = Decimal("0.20")
STANDARD_OUTPUT_USD_PER_M = Decimal("1.20")


def load_cases() -> list[dict[str, str]]:
    payload = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or set(payload) != {"version", "cases"}:
        raise RuntimeError("fixed-fact live registry shape is invalid")
    cases = payload["cases"]
    if payload["version"] != "fixed-fact-enrichment-live-v1" or not isinstance(cases, list):
        raise RuntimeError("fixed-fact live registry version is invalid")
    return cases


def contract_hashes(schema: dict[str, Any]) -> tuple[str, str]:
    prompt = render_fixed_fact_enrichment_prompt().encode("utf-8")
    provider = json.dumps(
        fixed_fact_enrichment_json_schema(schema), ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(prompt).hexdigest(), hashlib.sha256(provider).hexdigest()


def budget_snapshot() -> dict[str, Decimal | int]:
    cases = load_cases()
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    prompt = render_fixed_fact_enrichment_prompt()
    provider = json.dumps(
        fixed_fact_enrichment_json_schema(schema), ensure_ascii=False, separators=(",", ":")
    )
    input_bound = (
        max(len((prompt + provider + case["text"]).encode("utf-8")) for case in cases)
        + INPUT_OVERHEAD_BYTES
    )
    per_call = (
        Decimal(input_bound) * STANDARD_INPUT_USD_PER_M
        + Decimal(FIXED_FACT_ENRICHMENT_MAX_OUTPUT_TOKENS) * STANDARD_OUTPUT_USD_PER_M
    ) / Decimal(1_000_000)
    return {
        "calls": len(cases),
        "input_bound": input_bound,
        "conservative_usd_upper": per_call * Decimal(len(cases)),
    }


def evaluate(fact: SemanticFact, case: dict[str, str]) -> tuple[bool, list[str]]:
    """Check only semantic occurrence structure; Core resolution is covered provider-free."""
    identities = [part for part in fact.parts if isinstance(part, IdentityPart)]
    findings: list[str] = []

    def by_text(text: str) -> IdentityPart | None:
        return next((part for part in identities if part.text.casefold() == text.casefold()), None)

    bea = by_text("Bea")
    children = by_text("mis hijos")
    expected = case["expect"]
    if expected in {"nickname_identity", "mixed_identity_and_set"}:
        if bea is None:
            findings.append("missing_nickname_identity")
        elif bea.identity.binding is not IdentityBinding.DESCRIBED:
            findings.append("nickname_not_described_identity")
    if expected in {"complete_self_set", "mixed_identity_and_set"}:
        if children is None:
            findings.append("missing_children_identity")
        else:
            scope = children.identity.candidate_scope
            if scope is None:
                findings.append("missing_children_candidate_scope")
            else:
                if scope.source is not IdentityBinding.SELF:
                    findings.append("children_scope_not_self")
                if scope.extent is not CandidateScopeExtent.COMPLETE_SET:
                    findings.append("children_scope_not_complete_set")
                if "hij" not in scope.member_query.casefold():
                    findings.append("children_member_query_lost")
    if expected == "nickname_identity" and children is not None:
        findings.append("spurious_children_identity")
    if expected == "complete_self_set" and bea is not None:
        findings.append("spurious_nickname_identity")
    if not all(isinstance(part, (LiteralPart, IdentityPart)) for part in fact.parts):
        findings.append("unsupported_fact_part")
    return not findings, findings or ["all_checks_passed"]


class RecordingResponses:
    def __init__(self, responses: Any) -> None:
        self._responses = responses
        self.attempts = 0
        self.records: list[dict[str, int]] = []
        self.failures: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> Any:
        self.attempts += 1
        try:
            response = self._responses.create(**kwargs)
        except Exception as error:
            self.failures.append(
                {
                    "attempt": self.attempts,
                    "error_type": type(error).__name__,
                    "status_code": getattr(error, "status_code", None),
                }
            )
            raise
        usage = getattr(response, "usage", None)
        self.records.append(
            {
                "input_tokens": int(getattr(usage, "input_tokens", 0) or 0),
                "output_tokens": int(getattr(usage, "output_tokens", 0) or 0),
            }
        )
        return response


def _estimated_cost(records: list[dict[str, int]]) -> Decimal:
    return sum(
        (
            Decimal(row["input_tokens"]) * STANDARD_INPUT_USD_PER_M
            + Decimal(row["output_tokens"]) * STANDARD_OUTPUT_USD_PER_M
        )
        / Decimal(1_000_000)
        for row in records
    )


def _preflight() -> tuple[list[dict[str, str]], dict[str, Any]]:
    cases = load_cases()
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    if hashlib.sha256(CASES_PATH.read_bytes()).hexdigest() != CASES_SHA256:
        raise SystemExit("fixed-fact v1 case registry changed")
    if contract_hashes(schema) != (PROMPT_SHA256, PROVIDER_SCHEMA_SHA256):
        raise SystemExit("fixed-fact v1 model-facing contract changed")
    if (LUNA_EXPERIMENT_MODEL, LUNA_EXPERIMENT_REASONING_EFFORT) != (
        PRODUCTION_MODEL,
        REASONING_EFFORT,
    ):
        raise SystemExit("fixed-fact v1 production model contract changed")
    budget = budget_snapshot()
    if budget["calls"] != MAX_CALLS or budget["conservative_usd_upper"] > AUTHORIZED_CEILING_USD:
        raise SystemExit("fixed-fact v1 budget changed; fresh authorization required")
    if os.environ.get(AUTH_ENV) != "1":
        raise SystemExit(f"Refusing live calls: set {AUTH_ENV}=1 only after explicit authorization")
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("Refusing live calls: OPENAI_API_KEY is unavailable")
    if subprocess.check_output(
        ["git", "-C", str(ROOT), "status", "--porcelain"], text=True
    ).strip():
        raise SystemExit("Refusing live calls from a dirty worktree")
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    if any(RESULTS_DIR.glob("*.json")):
        raise SystemExit("fixed-fact v1 already has retained live evidence; refusing a second run")
    return cases, schema


def run() -> int:
    cases, schema = _preflight()
    from openai import OpenAI

    recorder = RecordingResponses(OpenAI(max_retries=0, timeout=30.0).responses)
    planner = OpenAILunaExperimentalPlanner(
        SimpleNamespace(responses=recorder),
        schema,
        {"date": "2026-10-03", "time": "20:30", "timezone": "Europe/Paris"},
    )
    rows: list[dict[str, Any]] = []
    for case in cases:
        try:
            fact = planner.enrich_fixed_fact(case["text"])
            passed, findings = evaluate(fact, case)
            error = None
        except Exception as exc:
            passed = False
            findings = [planner.last_error_category or type(exc).__name__[:120]]
            error = type(exc).__name__
        rows.append(
            {
                "case_id": case["id"],
                "passed": passed,
                "findings": findings,
                "error": error,
                "usage": planner.last_usage,
            }
        )
    actual_cost = _estimated_cost(recorder.records)
    if recorder.attempts > MAX_CALLS or actual_cost > AUTHORIZED_CEILING_USD:
        raise SystemExit("Authorized fixed-fact v1 ceiling exceeded")
    acceptable = all(row["passed"] for row in rows)
    artifact = {
        "version": 1,
        "commit": subprocess.check_output(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True
        ).strip(),
        "cases_sha256": CASES_SHA256,
        "prompt_sha256": PROMPT_SHA256,
        "provider_schema_sha256": PROVIDER_SCHEMA_SHA256,
        "provider_attempts": recorder.attempts,
        "completed_provider_responses": len(recorder.records),
        "automatic_retries": 0,
        "sol_calls": 0,
        "estimated_standard_cost_usd": str(actual_cost),
        "acceptable": acceptable,
        "failed_case_ids": [row["case_id"] for row in rows if not row["passed"]],
        "rows": rows,
        "provider_failures": recorder.failures,
    }
    out = RESULTS_DIR / f"{artifact['commit'][:12]}.json"
    out.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"provider_attempts={recorder.attempts}")
    print(f"completed_provider_responses={len(recorder.records)}")
    print(f"standard_cost_usd={actual_cost}")
    print(f"acceptable={acceptable}")
    print(f"failed_case_ids={artifact['failed_case_ids']}")
    print(f"artifact={out.relative_to(ROOT)}")
    return 0 if acceptable else 1


if __name__ == "__main__":
    raise SystemExit(run())
