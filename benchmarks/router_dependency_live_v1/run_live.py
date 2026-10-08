"""One-shot bounded current-Luna route-dependency validation, no data writes."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

from odyssey_apps import ApplicationDescriptor, ApplicationRegistry
from odyssey_apps.router import (
    ROUTER_MAX_OUTPUT_TOKENS,
    ROUTER_MODEL,
    ROUTER_REASONING_EFFORT,
    OpenAIApplicationRouter,
    render_router_prompt,
    route_plan_json_schema,
)

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
AUTH_ENV = "ODYSSEY_ROUTER_DEPENDENCY_LIVE_V1"
MAX_CALLS = 6
MAX_USD = 0.01
CASES = (
    (
        "dependent-person",
        "Ayer hablé con Eric. Mañana iré al cine con él. Hoy compré pan.",
        (
            ("temporal", "Ayer hablé con Eric.", None, None),
            ("temporal", "Mañana iré al cine con él.", 0, "él"),
            ("temporal", "Hoy compré pan.", None, None),
        ),
    ),
    (
        "independent-core",
        "Marta vive en Lyon. Luis vive en París.",
        (("core", "Marta vive en Lyon.", None, None), ("core", "Luis vive en París.", None, None)),
    ),
    (
        "single-temporal",
        "Mañana viene el fontanero.",
        (("temporal", "Mañana viene el fontanero.", None, None),),
    ),
    ("implicit-subject", "Hoy conocí a Eric. Mañana vendrá conmigo al teatro.", None),
    (
        "independent-temporal",
        "Ayer vi a Ana y hoy vi a Luis.",
        (("temporal", "Ayer vi a Ana", None, None), ("temporal", "y hoy vi a Luis.", None, None)),
    ),
    (
        "shared-participants",
        "El martes iré al parque con Ana y Luis.",
        (("temporal", "El martes iré al parque con Ana y Luis.", None, None),),
    ),
)


def catalog():
    """Match live Router capability scope without touching a real vault."""
    return ApplicationRegistry.from_descriptors(
        (
            ApplicationDescriptor(
                "tasks", "task lifecycle, due dates, completion and obligations", ("temporal",)
            ),
        )
    ).catalog()


def contract_hashes() -> tuple[str, str]:
    """Freeze the tested candidate schema and prompt for reviewer comparison."""
    cat = catalog()
    return (
        hashlib.sha256(render_router_prompt(cat, ()).encode()).hexdigest(),
        hashlib.sha256(
            json.dumps(
                route_plan_json_schema(cat), ensure_ascii=False, separators=(",", ":")
            ).encode()
        ).hexdigest(),
    )


def run() -> int:
    """Run at most six non-retried provider requests with an enforced small bound."""
    if os.environ.get(AUTH_ENV) != "YES" or not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("Live gate not authorized or missing provider key")
    assert ROUTER_MODEL == "gpt-6-luna" and ROUTER_REASONING_EFFORT == "low"
    assert ROUTER_MAX_OUTPUT_TOKENS <= 512 and len(CASES) == MAX_CALLS
    assert len(render_router_prompt(catalog(), ())) < 28000
    # 7k input tokens + 512 output tokens across 6 calls under $0.01,
    # at the historical Luna (0.10,0.50) USD/m-token rates and 10% margin.
    upper = MAX_CALLS * (7000 * 0.10 + 512 * 0.50) / 1_000_000 * 1.10
    if upper > MAX_USD:
        raise SystemExit("Worst-case cost envelope exceeded")
    router = OpenAIApplicationRouter.from_environment(catalog())
    rows = []
    for case_id, source, expected in CASES:
        try:
            plan = router.route(source)
            actual = tuple(
                (
                    item.capability_id,
                    item.source_text.strip(),
                    item.depends_on,
                    item.dependent_mention,
                )
                for item in plan.routes
            )
            if expected is None:
                ok = plan.outcome.value in ("CLARIFY", "ROUTE") and (
                    plan.outcome.value != "ROUTE" or len(plan.routes) == 1
                )
            else:
                ok = plan.outcome.value == "ROUTE" and actual == expected
            category = None
        except Exception as error:
            ok, actual, category = False, (), type(error).__name__
        usage = router.last_usage
        rows.append(
            {
                "id": case_id,
                "pass": ok,
                "routes": [list(x) for x in actual],
                "error": category,
                "input_tokens": getattr(usage, "input_tokens", None),
                "output_tokens": getattr(usage, "output_tokens", None),
            }
        )
        if category:
            break  # Never automatically retry a provider or parse failure.
    result = {
        "model": ROUTER_MODEL,
        "effort": ROUTER_REASONING_EFFORT,
        "contract_hashes": contract_hashes(),
        "calls": len(rows),
        "passed": len(rows) == MAX_CALLS and all(row["pass"] for row in rows),
        "cases": rows,
    }
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")), flush=True)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm-live-provider-calls", action="store_true")
    args = parser.parse_args()
    if not args.confirm_live_provider_calls:
        raise SystemExit("Explicit bounded live flag required")
    raise SystemExit(run())
