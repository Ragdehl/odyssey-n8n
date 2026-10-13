"""One bounded genuine GPT-6 Router v5 sweep, with source-only output evidence."""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

from openai import OpenAI

from odyssey_apps.fact_candidates import OpenAIFactCandidateRouter
from odyssey_runtime.hybrid_group_compiler import compile_hybrid_candidate_bundle
from tests.apps.test_fact_candidates import CASES

OUT = Path(__file__).parent
BASE_USD = 0.59769438
MAX_NEW_USD = 0.04
MAX_TOTAL_USD = 1.0
RATE_INPUT = 0.10
RATE_OUTPUT = 0.50
SAFETY_MULTIPLIER = 1.1


class CappedResponses:
    def __init__(self, client):
        self.client = client
        self.records = []

    @property
    def cost(self):
        return SAFETY_MULTIPLIER * sum(
            (r["input_tokens"] * RATE_INPUT + r["output_tokens"] * RATE_OUTPUT) / 1_000_000
            for r in self.records
        )

    def create(self, **kwargs):
        if (
            self.cost >= MAX_NEW_USD
            or BASE_USD + self.cost >= MAX_TOTAL_USD
            or len(self.records) >= 9
        ):
            raise RuntimeError("Experiment provider budget exhausted before request")
        if kwargs.get("model") != "gpt-6-luna":
            raise RuntimeError("Only source-only Router model is allowed")
        response = self.client.create(**kwargs)
        usage = response.usage
        self.records.append(
            {
                "model": kwargs["model"],
                "status": response.status,
                "output_text": response.output_text,
                "input_tokens": int(getattr(usage, "input_tokens", 0) or 0),
                "output_tokens": int(getattr(usage, "output_tokens", 0) or 0),
            }
        )
        if self.cost >= MAX_NEW_USD or BASE_USD + self.cost >= MAX_TOTAL_USD:
            raise RuntimeError("Experiment provider budget exceeded after request")
        return response


def main(ids):
    if os.environ.get("ODYSSEY_APPROVE_HYBRID_EXPERIMENT") != "1":
        raise SystemExit("No approval flag")
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("No credential")
    if not ids or len(ids) > 9 or len(ids) != len(set(ids)):
        raise SystemExit("Select 1..9 distinct cases")
    source_by_id = {r["id"]: r["source"] for r in CASES}
    if any(case not in source_by_id for case in ids):
        raise SystemExit("Only immutable source corpus cases supported")
    if any((OUT / f"{case}.json").exists() for case in ids):
        raise SystemExit("A genuine result cannot be overwritten")
    sdk = CappedResponses(OpenAI(max_retries=0, timeout=85).responses)
    rows = []
    for case in ids:
        src = source_by_id[case]
        previous = len(sdk.records)
        status = "exception"
        error = None
        candidates = []
        routing = []
        try:
            proposal = OpenAIFactCandidateRouter(
                SimpleNamespace(responses=sdk), prompt_revision="v5"
            ).propose(src)
            candidates = [
                {
                    "kind": c.kind,
                    "state": c.state,
                    "anchors": [x.text for x in c.anchors],
                    "roles": [{"role": x.role, "text": x.anchor.text} for x in c.scopes],
                    "inheritance": [{"role": x.role, "from": x.from_unit} for x in c.inheritance],
                }
                for c in proposal.candidates
            ]
            bundle = compile_hybrid_candidate_bundle(proposal)
            routing = [
                {
                    "capability": u.route.capability_id,
                    "source": u.route.source_text,
                    "depends_on": u.route.depends_on,
                    "dependent_mention": u.route.dependent_mention,
                }
                for u in bundle.units
            ]
            status = "completed"
        except Exception as exc:
            error = type(exc).__name__ + ": " + str(exc)[:300]
        receipt = {
            "case": case,
            "source_sha256": hashlib.sha256(src.encode()).hexdigest(),
            "status": status,
            "error": error,
            "real_model_outputs": sdk.records[previous:],
            "candidates": candidates,
            "routes": routing,
            "estimated_new_usd": round(sdk.cost, 8),
            "estimated_cumulative_usd": round(BASE_USD + sdk.cost, 8),
        }
        (OUT / f"{case}.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
        rows.append(
            {
                "case": case,
                "status": status,
                "candidate_kinds": [c["kind"] for c in candidates],
                "dependency": [r["dependent_mention"] for r in routing],
                "error": error,
            }
        )
        print(json.dumps(rows[-1], ensure_ascii=False), flush=True)
    summary = {
        "results": rows,
        "estimated_new_usd": round(sdk.cost, 8),
        "estimated_cumulative_usd": round(BASE_USD + sdk.cost, 8),
    }
    (OUT / "SUMMARY.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    print("Estimated charge USD", summary["estimated_new_usd"])


if __name__ == "__main__":
    main(sys.argv[1:])
