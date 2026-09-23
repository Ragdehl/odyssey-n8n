"""Run one explicit, sequential P1 baseline against a dedicated P1 product boundary.

The runner measures the ordinary dedicated P1 n8n request path. It never calls a provider directly,
never retries a request, resets the disposable fixture before each frozen case, and writes a
content-free JSONL record after every completed case. The historical whole-run USD 0.20
reservation code remains available in :mod:`budget`, but is deliberately not a live gate after
the human retired that theoretical-certification requirement.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4

from .budget import load_pricing
from .dev_fixture import (
    P1_ROOT,
    P1_STATE,
    P1_VAULT,
    FixtureError,
    _require_exact_p1_roots,
    reset_fixture,
)
from .report import _estimated_call_cost

P1_N8N_URL_ENV = "ODYSSEY_P1_N8N_URL"
P1_RUNTIME_SERVICE = "odyssey-p1-fixture-runtime.service"
_MAX_PROVIDER_CALLS = 64
_BASELINE_FACTS = {
    "Marta": ("Marta trabaja en Thales.", "Marta vive en Lyon."),
    "Elena": ("Elena vive en Girona.",),
    "Pablo": ("Pablo vive en Barcelona.",),
}


class LiveRunError(RuntimeError):
    """Raised when a live baseline cannot safely retain trustworthy evidence."""


HttpPost = Callable[[str, dict[str, object], float], dict[str, Any]]
FixtureReset = Callable[[dict[str, Any]], dict[str, object]]
RuntimeRestart = Callable[[], None]


def _project_root() -> Path:
    """Return the source checkout containing this runner."""
    return Path(__file__).resolve().parents[2]


def _safe_json(payload: object) -> str:
    """Encode one bounded JSON request body without logging its contents."""
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def post_json(url: str, payload: dict[str, object], timeout_s: float) -> dict[str, Any]:
    """Perform exactly one JSON POST with no retry behavior.

    Raises:
        LiveRunError: If the DEV endpoint is unavailable, rejects the request, or returns a
            malformed JSON object.
    """
    request = urllib.request.Request(
        url,
        data=_safe_json(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:  # noqa: S310
            decoded = json.loads(response.read().decode("utf-8"))
    except (
        urllib.error.HTTPError,
        urllib.error.URLError,
        TimeoutError,
        json.JSONDecodeError,
    ) as error:
        raise LiveRunError(
            "isolated DEV request did not return a valid product response"
        ) from error
    if not isinstance(decoded, dict):
        raise LiveRunError("isolated DEV request response is not an object")
    return decoded


def _source_provenance(source_root: Path) -> dict[str, str]:
    """Verify the runner source is the exact clean commit recorded in the P1 fixture root."""
    head = subprocess.check_output(
        ["git", "-C", str(source_root), "rev-parse", "HEAD"], text=True
    ).strip()
    dirty = subprocess.check_output(
        ["git", "-C", str(source_root), "status", "--porcelain"], text=True
    )
    deployed = (P1_ROOT / "runtime" / "deployed-commit").read_text(encoding="utf-8").strip()
    if dirty or not deployed or deployed != head:
        raise LiveRunError("P1 fixture source is not the clean commit recorded as deployed")
    return {"source_commit": head, "deployed_commit": deployed}


def _restart_runtime() -> None:
    """Restart only the dedicated P1 runtime and wait for its local health response.

    The manual DEV runtime is deliberately not a valid target. A dedicated P1 deployment must
    provide this service and its matching n8n endpoint before a live baseline can start.
    """
    subprocess.run(["systemctl", "--user", "restart", P1_RUNTIME_SERVICE], check=True)
    deadline = time.monotonic() + 90.0
    health_url = "http://127.0.0.1:28781/healthz"
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(health_url, timeout=2.0) as response:  # noqa: S310
                if response.status == 200:
                    return
        except (urllib.error.URLError, TimeoutError):
            pass
        time.sleep(1.0)
    raise LiveRunError("dedicated P1 runtime did not become healthy after fixture reset")


def _reset_case_fixture(case: dict[str, Any]) -> dict[str, object]:
    """Reset only synthetic DEV data and return non-content fixture identity."""
    schema = json.loads(
        (_project_root() / "config" / "note-schema.json").read_text(encoding="utf-8")
    )
    extra = case.get("extra_fixture_facts")
    if extra is not None and not isinstance(extra, dict):
        raise LiveRunError("frozen case fixture additions are malformed")
    try:
        return reset_fixture(schema, extra_facts=extra)
    except FixtureError as error:
        raise LiveRunError("dedicated P1 fixture could not be reset safely") from error


def _append_prior_turns(
    case: dict[str, Any], run_id: str, post: HttpPost, timeout_s: float, conversation_url: str
) -> None:
    """Persist frozen conversational context through the regular P1 n8n boundary."""
    turns = case.get("prior_turns", [])
    if not isinstance(turns, list):
        raise LiveRunError("frozen prior turns are malformed")
    for ordinal, turn in enumerate(turns):
        if not isinstance(turn, dict) or turn.get("role") not in {"user", "assistant"}:
            raise LiveRunError("frozen prior turns are malformed")
        text = turn.get("text")
        if not isinstance(text, str) or not text:
            raise LiveRunError("frozen prior turns are malformed")
        request_id = f"p1-{run_id}-{case['id']}-context-{ordinal}"
        response = post(
            conversation_url,
            {"operation": "turn", "request_id": request_id, "role": turn["role"], "text": text},
            timeout_s,
        )
        if response.get("conversation_id") != "main":
            raise LiveRunError("P1 conversation setup did not confirm the main conversation")


def _request_payload(
    case: dict[str, Any], request_id: str, n8n_url: str
) -> tuple[str, dict[str, object]]:
    """Build one frozen product request without introducing a benchmark-specific path."""
    kind = case.get("kind")
    request = case.get("request")
    if not isinstance(request, str) or not request:
        raise LiveRunError("frozen case request is malformed")
    if kind == "chat":
        return f"{n8n_url}/api/request", {"request": request, "request_id": request_id}
    if kind == "notes_intelligent":
        return f"{n8n_url}/api/notes", {
            "operation": "intelligent",
            "query": request,
            "filters": [],
            "page_size": 20,
            "sort": "relevance",
        }
    raise LiveRunError("frozen case kind is unsupported")


def _provider_calls(operational: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten bounded request-local provider evidence without coalescing repeated calls."""
    stages = operational.get("stages")
    if not isinstance(stages, list):
        raise LiveRunError("operational stages are unavailable")
    calls: list[dict[str, Any]] = []
    for stage in stages:
        if not isinstance(stage, dict):
            raise LiveRunError("operational stage is malformed")
        stage_calls = stage.get("provider_calls", [])
        if not isinstance(stage_calls, list):
            raise LiveRunError("operational provider calls are malformed")
        for call in stage_calls:
            if not isinstance(call, dict):
                raise LiveRunError("operational provider call is malformed")
            calls.append(call)
    if len(calls) > _MAX_PROVIDER_CALLS:
        raise LiveRunError("unexpected provider-call fan-out; stopping baseline")
    return calls


def _actual_cost(calls: list[dict[str, Any]], pricing: dict[str, Any]) -> Decimal | None:
    """Sum only fully evidenced observed estimates under the frozen P1 pricing snapshot."""
    estimates = [_estimated_call_cost(call, pricing) for call in calls]
    return (
        sum(estimates, Decimal(0))
        if estimates and all(cost is not None for cost in estimates)
        else None
    )


def _fixture_note_text(person: str) -> str:
    """Load one synthetic P1 note only to evaluate its frozen mutation oracle."""
    paths = {
        "Marta": "people/p1-marta.md",
        "Elena": "people/p1-elena.md",
        "Pablo": "people/p1-pablo.md",
    }
    try:
        return (P1_VAULT / paths[person]).read_text(encoding="utf-8").casefold()
    except (KeyError, OSError) as error:
        raise LiveRunError("synthetic P1 fixture note is unavailable") from error


def _semantic_oracle(case: dict[str, Any], response: dict[str, Any]) -> tuple[bool, str]:
    """Evaluate the frozen outcome without persisting response text or Markdown content."""
    expected = case.get("expected")
    if not isinstance(expected, dict):
        return False, "malformed_expected_oracle"
    if case.get("kind") == "notes_intelligent":
        items = response.get("items")
        if (
            response.get("kind") != expected.get("kind")
            or response.get("mode") != expected.get("mode")
            or not isinstance(items, list)
        ):
            return False, "notes_shape"
        item_ids = {item.get("id") for item in items if isinstance(item, dict)}
        return "p1-marta" in item_ids, "notes_contains_marta"
    if response.get("status") != expected.get("status"):
        return False, "unexpected_status"
    detail = response.get("request_detail")
    changes = detail.get("changes") if isinstance(detail, dict) else None
    units = changes.get("units") if isinstance(changes, dict) else None
    if expected.get("mutation") is False:
        if expected.get("clarification_code") and response.get("kind") != "clarification":
            return False, "clarification_not_returned"
        answer_fact = expected.get("answer_fact")
        if answer_fact is not None:
            message = response.get("message")
            if not isinstance(answer_fact, str) or not isinstance(message, str):
                return False, "answer_evidence_unavailable"
            if answer_fact.casefold() not in message.casefold():
                return False, "answer_fact_missing"
        return isinstance(units, list) and not units, "no_mutation"
    facts_by_person = expected.get("facts_by_person")
    if not isinstance(facts_by_person, dict) or response.get("kind") != "acknowledgement":
        return False, "write_shape"
    for person, facts in facts_by_person.items():
        if not isinstance(person, str) or not isinstance(facts, list):
            return False, "malformed_expected_facts"
        text = _fixture_note_text(person)
        if any(not isinstance(fact, str) or fact.casefold() not in text for fact in facts):
            return False, "expected_fact_missing"
        if expected.get("forbidden_cross_assignment"):
            for other in {"Marta", "Elena", "Pablo"} - {person}:
                other_text = _fixture_note_text(other)
                if any(
                    isinstance(fact, str)
                    and not any(
                        fact.casefold() in baseline.casefold()
                        for baseline in _BASELINE_FACTS[other]
                    )
                    and fact.casefold() in other_text
                    for fact in facts
                ):
                    return False, "cross_assignment"
    return True, "write_facts_verified"


def _sanitized_operational(response: dict[str, Any]) -> dict[str, Any]:
    """Keep only the already bounded request-detail operational hierarchy."""
    detail = response.get("request_detail")
    operational = (
        detail.get("operational") if isinstance(detail, dict) else response.get("operational")
    )
    if not isinstance(operational, dict):
        raise LiveRunError("product response omitted operational evidence")
    _provider_calls(operational)
    return operational


def _flush(stream: Any, row: dict[str, object]) -> None:
    """Durably append one content-free evidence row before proceeding to another case."""
    stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    stream.flush()
    os.fsync(stream.fileno())


def run_live_cases(
    cases: Sequence[dict[str, Any]],
    *,
    evidence_path: Path,
    pricing: dict[str, Any],
    provenance: dict[str, str],
    confirmed: bool,
    post: HttpPost = post_json,
    reset: FixtureReset = _reset_case_fixture,
    restart: RuntimeRestart = _restart_runtime,
    n8n_url: str = "http://p1-fixture.invalid",
    timeout_s: float = 130.0,
    run_id: str | None = None,
) -> list[dict[str, object]]:
    """Run every frozen case once, sequentially, with immutable incremental evidence.

    A normal semantic oracle failure is recorded and does not retry or block independent cases.
    Unsafe transport, replay, fixture, or telemetry failures stop immediately after their error row.
    """
    if not confirmed:
        raise LiveRunError("live provider calls require explicit confirmation")
    if evidence_path.exists():
        raise FileExistsError("Refusing to overwrite existing P1 evidence")
    expected_ids = ["R1", "R2", "W1", "W2", "W3", "C1", "N1"]
    if len(cases) != len(expected_ids) or [case.get("id") for case in cases] != expected_ids:
        raise LiveRunError("frozen P1 case registry is incomplete or reordered")
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    identity = run_id or uuid4().hex
    rows: list[dict[str, object]] = []
    with evidence_path.open("x", encoding="utf-8") as stream:
        _flush(
            stream,
            {
                "record_type": "run",
                "run_id": identity,
                "started_at": datetime.now(UTC).isoformat(),
                "environment": "isolated-p1-fixture",
                "pricing_basis": pricing.get("as_of"),
                **provenance,
            },
        )
        for case in cases:
            case_id = case["id"]
            setup_started = time.perf_counter()
            try:
                fixture = reset(case)
                restart()
                _append_prior_turns(
                    case, identity, post, timeout_s, f"{n8n_url.rstrip('/')}/api/conversation"
                )
                request_id = f"p1-{identity}-{case_id}-{uuid4().hex[:12]}"
                url, payload = _request_payload(case, request_id, n8n_url.rstrip("/"))
                request_started = time.perf_counter()
                response = post(url, payload, timeout_s)
                client_product_duration_ms = (time.perf_counter() - request_started) * 1000
                if case.get("kind") == "chat" and response.get("request_id") != request_id:
                    raise LiveRunError(
                        "product response request ID does not prove a fresh execution"
                    )
                operational = _sanitized_operational(response)
                calls = _provider_calls(operational)
                semantic_passed, oracle = _semantic_oracle(case, response)
                cost = _actual_cost(calls, pricing)
                row: dict[str, object] = {
                    "record_type": "case",
                    "run_id": identity,
                    "case_id": case_id,
                    "request_id": request_id if case.get("kind") == "chat" else None,
                    "fresh_execution": True,
                    "fixture": fixture,
                    "fixture_setup_duration_ms": (time.perf_counter() - setup_started) * 1000,
                    "runner_n8n_product_duration_ms": client_product_duration_ms,
                    "status": response.get("status")
                    if isinstance(response.get("status"), str)
                    else None,
                    "kind": response.get("kind") if isinstance(response.get("kind"), str) else None,
                    "semantic_passed": semantic_passed,
                    "semantic_oracle": oracle,
                    "estimated_cost_usd": str(cost) if cost is not None else None,
                    "pricing_basis": pricing.get("as_of"),
                    "provider_calls": calls,
                    "operational": operational,
                }
                _flush(stream, row)
                rows.append(row)
            except Exception as error:
                _flush(
                    stream,
                    {
                        "record_type": "unsafe_stop",
                        "run_id": identity,
                        "case_id": case_id,
                        "error_category": type(error).__name__,
                        "message": "P1 baseline stopped before another request; inspect local run evidence.",
                    },
                )
                raise
    return rows


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Require an explicit live-call acknowledgement and one new evidence artifact path."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-live-provider-calls", action="store_true")
    parser.add_argument("--evidence-path", required=True, type=Path)
    parser.add_argument(
        "--cases-path", type=Path, default=_project_root() / "benchmarks/performance_p1/cases.json"
    )
    parser.add_argument(
        "--p1-n8n-url",
        default=os.environ.get(P1_N8N_URL_ENV),
        help=f"Dedicated P1 n8n base URL (or set {P1_N8N_URL_ENV}).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Run one confirmed P1 baseline through the deployed dedicated P1 product boundary."""
    args = parse_args(argv)
    if not args.confirm_live_provider_calls:
        raise SystemExit("Refusing live calls without --confirm-live-provider-calls")
    if not isinstance(args.p1_n8n_url, str) or not args.p1_n8n_url.startswith("http"):
        raise SystemExit("Refusing live calls without a dedicated P1 n8n URL")
    try:
        _require_exact_p1_roots(P1_VAULT, P1_STATE)
        payload = json.loads(args.cases_path.read_text(encoding="utf-8"))
        cases = payload.get("cases") if isinstance(payload, dict) else None
        if not isinstance(cases, list):
            raise LiveRunError("frozen P1 case registry is malformed")
        provenance = _source_provenance(_project_root())
        pricing = load_pricing(_project_root() / "benchmarks/performance_p1/pricing_snapshot.json")
        run_live_cases(
            cases,
            evidence_path=args.evidence_path,
            pricing=pricing,
            provenance=provenance,
            confirmed=True,
            n8n_url=args.p1_n8n_url,
        )
    except (LiveRunError, FixtureError, OSError, ValueError, json.JSONDecodeError) as error:
        raise SystemExit(f"P1 live baseline stopped: {error}") from error
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
