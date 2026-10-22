#!/usr/bin/env python3
"""No-write real GPT Event+Task source partition and independent semantic veto."""

from __future__ import annotations

import json
import os

from openai import OpenAI

from odyssey_core.independent_source_scopes import verify_independent_source_scopes
from odyssey_runtime.whole_source_model_contract import (
    INDEPENDENT_SCOPE_REVIEW_SCHEMA,
    independent_partition_contract,
)

SOURCE = (
    "Concierto ficticio E5 el 24 de noviembre de 2026. "
    "Tengo que presentar el informe Atlas el 25 de noviembre de 2026."
)


def main():
    if os.environ.get("ODYSSEY_E5_LIVE_APPROVED") != "1":
        raise SystemExit("Live provider gate not approved")
    schema, proposal_prompt, review_prompt = independent_partition_contract(enable_events=True)
    client = OpenAI(timeout=65, max_retries=0)

    def ask(model, prompt, data, shape, name):
        response = client.responses.create(
            model=model,
            reasoning={"effort": "low"},
            store=False,
            max_output_tokens=1800,
            input=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": json.dumps(data, ensure_ascii=False)},
            ],
            text={"format": {"type": "json_schema", "name": name, "strict": True, "schema": shape}},
        )
        return json.loads(response.output_text)

    proposal = ask(
        "gpt-5.6",
        proposal_prompt,
        {"original_source": SOURCE},
        schema,
        "odyssey_independent_event_task_scopes_v1",
    )
    print(
        "E5_MIXED_PARTITION="
        + json.dumps(
            {
                "count": len(proposal.get("parts", [])),
                "kinds": [p.get("capability") for p in proposal.get("parts", [])],
                "exact_join": "".join(p.get("source_quote", "") for p in proposal.get("parts", []))
                == SOURCE,
            }
        ),
        flush=True,
    )
    review = ask(
        "gpt-6-luna",
        review_prompt,
        {"original_source": SOURCE, "proposed_scopes": proposal},
        INDEPENDENT_SCOPE_REVIEW_SCHEMA,
        "odyssey_independent_event_task_scopes_audit_v1",
    )
    try:
        attested = verify_independent_source_scopes(
            SOURCE, proposal, review, permitted_capabilities=frozenset({"events", "tasks"})
        )
        result = {
            "pass": True,
            "count": len(attested),
            "ordered_kinds": [x.capability for x in attested],
            "independent": review.get("independent"),
            "complete": review.get("complete"),
        }
    except ValueError as exc:
        result = {
            "pass": False,
            "code": type(exc).__name__,
            "independent": review.get("independent"),
            "complete": review.get("complete"),
        }
    print("E5_MIXED_LIVE_PREFLIGHT=" + json.dumps(result), flush=True)
    return 0 if result["pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
