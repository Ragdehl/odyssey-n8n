#!/usr/bin/env python3
"""Exactly one live Core-planner read-only probe of selected candidate evidence."""

import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory

from odyssey_core.candidate_continuation_plan import inspect_selected_candidate_plan
from odyssey_core.domain_interpretation import DomainEvidence, DomainInterpretation
from odyssey_core.experimental_luna_planning import OpenAILunaExperimentalPlanner
from odyssey_core.request_planning import RequestPlan
from tests.runtime.test_candidate_continuation_plan import _ready_inspector
from tests.runtime.test_temporal_user_path_e2e import SCHEMA


def main():
    if os.environ.get("ODYSSEY_E5_PLANNER_ONCE") != "1":
        raise SystemExit("Refused non-authorized planner probe")
    with TemporaryDirectory(prefix="odyssey-e5-planner-") as tmp:
        context, _fixture_plan, _ = _ready_inspector(Path(tmp))
        clock = {"date": "2026-10-04", "time": "17:35:00", "timezone": "Europe/Paris"}
        domain = DomainInterpretation(
            "core",
            context.pending_source,
            "CANONICAL_REFERENCE",
            (
                DomainEvidence(
                    "canonical_reference", context.reference_text, "person:" + context.selected_name
                ),
            ),
        )
        planner = OpenAILunaExperimentalPlanner.from_environment(
            SCHEMA, clock, domain_interpretation=domain
        )
        try:
            plan = planner.plan(context.pending_source)
            if not isinstance(plan, RequestPlan):
                print(json.dumps({"kind": type(plan).__name__, "inspected": False}))
                return 1
            try:
                inspected = inspect_selected_candidate_plan(context, plan)
                print(
                    json.dumps(
                        {
                            "kind": "RequestPlan",
                            "inspected": True,
                            "fact_count": len(inspected.proposed_facts),
                            "texts": [f.text for f in inspected.proposed_facts],
                            "dates": [f.temporal_values for f in inspected.proposed_facts],
                            "chosen_indexes": inspected.selected_identity_reference_ordinals,
                            "model": planner.model,
                        },
                        ensure_ascii=False,
                    )
                )
                return 0
            except Exception as error:
                print(
                    json.dumps(
                        {
                            "kind": "RequestPlan",
                            "inspected": False,
                            "reason": str(error),
                            "actions": len(plan.actions),
                            "model": planner.model,
                        },
                        ensure_ascii=False,
                    )
                )
                return 1
        except Exception as error:
            print(
                json.dumps(
                    {"kind": "exception", "type": type(error).__name__, "reason": str(error)},
                    ensure_ascii=False,
                )
            )
            return 1


if __name__ == "__main__":
    raise SystemExit(main())
