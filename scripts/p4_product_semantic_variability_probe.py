"""Real provider P4 source-stage diagnostics with ZERO real user data or writes.

Opt-in. A distinct disposable vault/actor/delivery and new provider calls for
EACH repetition; records bounded categories/structural metadata only, not raw
messages, person names, Note contents, prompt bodies, IDs or model text facts.
This is NOT real n8n/browser acceptance and does not alter P4 production code.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from openai import OpenAI

import odyssey_runtime.whole_source_light as p4
from tests.runtime.test_whole_source_light_product_p4 import _fixture

SOURCES = {
    "two_dates": "Hoy compré pan y mañana compraré leche.",
    "cross_app": "Hoy he conocido a Maite Solis, mañana tengo que llamarla.",
}


def run():
    if os.environ.get("ODYSSEY_APPROVE_LIGHT_POC") != "1":
        raise SystemExit("Synthetic genuine GPT run needs explicit opt-in")
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("No real provider authorization")
    case = os.environ.get("ODYSSEY_P4_CASE", "two_dates")
    if case not in SOURCES:
        raise ValueError("Unknown bounded synthetic scenario")
    source = SOURCES[case]
    count = int(os.environ.get("ODYSSEY_P4_REPEAT", "4"))
    if not 1 <= count <= 8:
        raise ValueError("Safe run budget 1–8")
    results = []
    for index in range(count):
        evidence = {"run": index + 1, "case": case, "model_steps": [], "validator_errors": []}
        with tempfile.TemporaryDirectory(prefix="p4-source-var-") as tmp:
            repo, actor, service, runtime = _fixture(Path(tmp))
            service.client = OpenAI(max_retries=0, timeout=80)
            original_ask = service._ask

            def inspect(
                model, instructions, payload, schema, name, _ask=original_ask, _ev=evidence
            ):
                response = _ask(model, instructions, payload, schema, name)
                item = {"step": name}
                if name == "odyssey_light_capability_route_v1":
                    item["capabilities"] = response.get("capabilities")
                elif name == "odyssey_light_shared_semantic_plan_v1":
                    item["facts"] = [
                        {
                            "kind": f.get("kind"),
                            "date": f.get("date"),
                            "daypart": f.get("daypart"),
                            "subject_present": bool(f.get("subject")),
                            "participant_count": len(f.get("participants", [])),
                            "needs_clarification": f.get("needs_clarification"),
                        }
                        for f in response.get("facts", [])
                    ]
                    item["unresolved_count"] = len(response.get("unresolved", []))
                elif name == "odyssey_mixed_task_create_v1":
                    item["only_new_task_creations"] = response.get("only_new_task_creations")
                    item["no_work_session_or_lifecycle_transition"] = response.get(
                        "no_work_session_or_lifecycle_transition"
                    )
                    item["same_source_quote"] = response.get("source_quote") == source
                elif name == "odyssey_p2_source_coverage_v1":
                    item["approved"] = response.get("approved")
                    item["complete"] = response.get("complete")
                    item["facts"] = [
                        {
                            "kind": f.get("kind"),
                            "date": f.get("date"),
                            "supported": f.get("supported"),
                            "reference_count": len(f.get("reference_names", [])),
                        }
                        for f in response.get("facts", [])
                    ]
                    # Reviewer reasons are untrusted free text: never record them.
                elif name.startswith("odyssey_speaker_full_"):
                    item["roles"] = [f.get("role") for f in response.get("facts", [])]
                    item["assertions"] = [f.get("assertion") for f in response.get("facts", [])]
                _ev["model_steps"].append(item)
                return response

            service._ask = inspect
            original = {}
            for label in (
                "validate_whole_message_coverage",
                "reject_unproven_person_collisions",
                "validate_dual_speaker_review",
                "compile_reviewed_operations",
            ):
                base = getattr(p4, label)
                original[label] = base

                def intercept(*args, _label=label, _base=base, _ev=evidence, **kwargs):
                    try:
                        return _base(*args, **kwargs)
                    except Exception as error:
                        static_coverage_errors = {
                            "Whole message not completely accounted for",
                            "Atomic source evidence mismatch",
                            "Source quote is ambiguous or absent",
                            "Source reviewer invented a participant",
                            "Participant absent from original source",
                            "Cross-operation identity handoff has no shared person",
                            "Fact evidence order differs from source order",
                            "Symbolic Core references missing or repeated",
                        }
                        reason = str(error)
                        _ev["validator_errors"].append(
                            {
                                "boundary": _label,
                                "error_type": type(error).__name__,
                                "fixed_reason": reason
                                if _label == "validate_whole_message_coverage"
                                and reason in static_coverage_errors
                                else "other",
                            }
                        )
                        raise

                setattr(p4, label, intercept)
            try:
                response = runtime.execute_product(source, f"variance-{index}", "main", actor)
                evidence["status"] = response.get("status")
                evidence["physical_fact_count"] = sum(
                    repo.read_text(path).count("odyssey:fact request=variance-")
                    for path in repo.list_markdown_paths()
                )
            except Exception as error:
                evidence["status"] = "exception"
                evidence["error_type"] = type(error).__name__
            finally:
                for label, base in original.items():
                    setattr(p4, label, base)
            results.append(evidence)
            print(json.dumps(evidence, ensure_ascii=False), flush=True)
    path = Path("/tmp/odyssey-p4-source-variance-" + case + ".json")
    path.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n")
    print(
        f"SYNTHETIC_RUNS={count} COMPLETED={sum(r.get('status') == 'completed' for r in results)}"
    )


if __name__ == "__main__":
    run()
