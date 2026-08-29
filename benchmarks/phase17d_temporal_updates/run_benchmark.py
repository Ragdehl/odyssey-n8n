"""Run the focused Phase 17D production planner/writer semantic evidence suite."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from openai import OpenAI  # noqa: E402

from odyssey_core.materialization import (  # noqa: E402
    OpenAILunaWriter,
    StructuredPropertyChangeContext,
    WriterRequest,
    apply_writer_operations,
    validate_writer_output,
)
from odyssey_core.request_planning import OpenAIRequestPlanner, WriteAction  # noqa: E402

SCHEMA = json.loads((ROOT / "config/note-schema.json").read_text(encoding="utf-8"))
CONTEXT = {"date": "2026-08-29", "time": "10:00", "timezone": "Europe/Paris"}

CASES: tuple[dict[str, Any], ...] = (
    {
        "id": "transition_employer",
        "user": "Marta ha dejado Airbus y ahora trabaja en Thales.",
        "body": "Marta trabaja en Airbus.",
        "semantics": "transition",
        "facts": ["Marta ha dejado Airbus y ahora trabaja en Thales."],
        "must_keep": ["Airbus"],
        "must_add": ["Thales"],
    },
    {
        "id": "correction_employer",
        "user": "Me equivoqué: Marta nunca trabajó en Airbus; trabaja en Thales.",
        "body": "Marta trabaja en Airbus.",
        "semantics": "correction",
        "facts": ["Me equivoqué: Marta nunca trabajó en Airbus; trabaja en Thales."],
        "must_absent": ["Airbus"],
        "must_add": ["Thales"],
    },
    {
        "id": "transition_dated_residence",
        "user": "Marta dejó Toulouse el 12 de junio y ahora vive en Lyon.",
        "body": "Marta vive en Toulouse.",
        "semantics": "transition",
        "facts": ["Marta dejó Toulouse el 12 de junio y ahora vive en Lyon."],
        "must_keep": ["Toulouse", "12 de junio"],
        "must_add": ["Lyon"],
    },
    {
        "id": "transition_undated_residence",
        "user": "Marta ya no vive en Toulouse; ahora vive en Lyon.",
        "body": "Marta vive en Toulouse.",
        "semantics": "transition",
        "facts": ["Marta ya no vive en Toulouse; ahora vive en Lyon."],
        "must_keep": ["Toulouse"],
        "must_add": ["Lyon"],
    },
    {
        "id": "ordinary_ambiguous_residence",
        "user": "Marta vive en Lyon.",
        "body": "Marta vive en Toulouse.",
        "semantics": "ordinary",
        "facts": ["Marta vive en Lyon."],
        "must_keep": ["Toulouse"],
        "must_add": ["Lyon"],
    },
    {
        "id": "property_transition",
        "user": "Marta era mi compañera de trabajo y ahora es mi jefa.",
        "body": "",
        "semantics": "transition",
        "facts": ["Marta era mi compañera de trabajo y ahora es mi jefa."],
        "property": ["relationship_to_user", "compañera", "jefa"],
        "must_keep": ["compañera"],
        "must_add": ["jefa"],
    },
    {
        "id": "property_correction",
        "user": "Me equivoqué: Marta nunca fue mi compañera; es mi jefa.",
        "body": "Marta era mi compañera de trabajo.",
        "semantics": "correction",
        "facts": ["Me equivoqué: Marta nunca fue mi compañera; es mi jefa."],
        "property": ["relationship_to_user", "compañera", "jefa"],
        "must_absent": ["compañera"],
        "must_add": ["jefa"],
    },
    {
        "id": "property_ordinary",
        "user": "Marta es mi jefa.",
        "body": "",
        "semantics": "ordinary",
        "facts": [],
        "property": ["relationship_to_user", "compañera", "jefa"],
        "must_keep": ["compañera"],
        "must_add": ["jefa"],
    },
    {
        "id": "append_regression",
        "user": "Marta toca el piano.",
        "body": "Marta vive en Lyon.",
        "semantics": "ordinary",
        "facts": ["Marta toca el piano."],
        "must_keep": ["Lyon"],
        "must_add": ["piano"],
    },
    {
        "id": "no_change_regression",
        "user": "Marta toca el piano.",
        "body": "Marta toca el piano.",
        "semantics": "ordinary",
        "facts": ["Marta toca el piano."],
        "must_keep": ["piano"],
        "must_no_change": True,
    },
    {
        "id": "remove_regression",
        "user": "Elimina que Marta trabaja en Airbus.",
        "body": "Marta trabaja en Airbus.\nMarta toca el piano.",
        "semantics": "ordinary",
        "intent": "remove",
        "facts": ["Marta trabaja en Airbus."],
        "must_absent": ["Airbus"],
        "must_keep": ["piano"],
    },
    {
        "id": "bound_wikilink_regression",
        "user": "Marta trabaja con Ada.",
        "body": "Marta vive en Lyon.",
        "semantics": "ordinary",
        "facts": ["Marta trabaja con [[people/Ada - ada|Ada]]."],
        "must_keep": ["[[people/Ada - ada|Ada]]"],
        "must_add": ["Ada"],
    },
)


class _RecordingResponses:
    """Proxy Responses calls while retaining only provider usage metadata."""

    def __init__(self, responses: Any) -> None:
        """Wrap one SDK Responses resource."""
        self._responses = responses
        self.usage: list[dict[str, Any] | None] = []

    def create(self, **kwargs: Any) -> Any:
        """Forward one call and retain its usage metadata when available."""
        response = self._responses.create(**kwargs)
        self.usage.append(_usage(response))
        return response


class _RecordingClient:
    """Expose the minimal planner client surface with recorded usage."""

    def __init__(self, responses: Any) -> None:
        """Attach the recording Responses proxy."""
        self.responses = _RecordingResponses(responses)


def _usage(response: Any) -> dict[str, Any] | None:
    """Return JSON-safe Responses usage when the SDK response exposes it."""
    usage = getattr(response, "usage", None)
    if usage is None:
        return None
    return usage.model_dump() if hasattr(usage, "model_dump") else dict(usage)


def _writer_request(case: dict[str, Any]) -> WriterRequest:
    """Build one bounded writer request without granting metadata mutation authority."""
    changes: tuple[StructuredPropertyChangeContext, ...] = ()
    if "property" in case:
        field, old, new = case["property"]
        changes = (StructuredPropertyChangeContext(field, True, old, "set", True, new),)
    return WriterRequest(
        "marta",
        "person",
        case.get("intent", "amend"),
        tuple(case["facts"]),
        case["body"],
        case["semantics"],
        changes,
    )


def _evaluate(case: dict[str, Any], operations: tuple[Any, ...], body: str) -> list[str]:
    """Return bounded acceptance failures for one rendered writer body."""
    failures: list[str] = []
    if case.get("must_no_change") and any(operation.op != "NO_CHANGE" for operation in operations):
        failures.append("exact duplicate was not NO_CHANGE")
    if case["semantics"] in {"transition", "ordinary"} and any(
        operation.op == "REMOVE" for operation in operations
    ):
        failures.append("transition/ordinary emitted destructive REMOVE")
    for value in case.get("must_keep", []):
        if value not in body:
            failures.append(f"missing preserved value: {value}")
    for value in case.get("must_add", []):
        if value not in body:
            failures.append(f"missing new value: {value}")
    for value in case.get("must_absent", []):
        if value in body:
            failures.append(f"false/removed value remained: {value}")
    return failures


def main() -> int:
    """Run exactly twelve Sol/low planner and Luna/medium writer evidence calls."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=False)
    client = _RecordingClient(OpenAI().responses)
    planner = OpenAIRequestPlanner(client, SCHEMA, CONTEXT)
    writer = OpenAILunaWriter()
    records: list[dict[str, Any]] = []
    planner_usage: list[dict[str, Any] | None] = []
    for case in CASES:
        record: dict[str, Any] = {"id": case["id"], "semantic_discriminator": case["semantics"]}
        try:
            plan = planner.plan(case["user"])
            units = [
                unit
                for action in plan.actions
                if isinstance(action, WriteAction)
                for unit in action.units
            ]
            record["planner_output"] = [
                {
                    "intent": unit.intent,
                    "update_semantics": unit.update_semantics,
                    "properties": [asdict(change) for change in unit.properties],
                    "facts": list(unit.facts),
                }
                for unit in units
            ]
            if not any(unit.update_semantics == case["semantics"] for unit in units):
                record.update(
                    {
                        "pass": False,
                        "reason": "planner did not emit the required semantic discriminator",
                    }
                )
                records.append(record)
                continue
            planner_usage.append(client.responses.usage[-1])
        except Exception as error:
            cause = error.__cause__
            detail = f"{type(error).__name__}: {error}"
            if cause is not None:
                detail += f"; cause: {type(cause).__name__}: {cause}"
            record.update({"pass": False, "reason": f"planner: {detail}"})
            records.append(record)
            continue
        request = _writer_request(case)
        record["writer_request"] = {
            "intent": request.intent,
            "update_semantics": request.update_semantics,
            "facts": list(request.facts),
            "current_body": request.current_body,
            "structured_property_changes": [
                asdict(change) for change in request.structured_property_changes
            ],
        }
        try:
            output = writer.write(request)
            operations = validate_writer_output(
                output, request.current_body, request.intent, request.update_semantics
            )
            body = apply_writer_operations(request.current_body, operations)
            failures = _evaluate(case, operations, body)
            record.update(
                {
                    "writer_operations": [asdict(operation) for operation in operations],
                    "final_rendered_body": body,
                    "pass": not failures,
                    "reason": "; ".join(failures) if failures else "PASS",
                }
            )
        except Exception as error:
            record.update({"pass": False, "reason": f"writer: {type(error).__name__}: {error}"})
        records.append(record)
    (args.output_dir / "results.json").write_text(
        json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    metadata = {
        "phase": "17D",
        "planner": {"model": "gpt-5.6-sol", "reasoning": "low", "calls": len(CASES)},
        "writer": {"model": "gpt-5.6-luna", "reasoning": "medium", "calls": len(CASES)},
        "planner_usage": planner_usage,
        "writer_usage": "not retained: existing writer boundary exposes parsed output only",
        "passed": sum(record.get("pass", False) for record in records),
        "failed": sum(not record.get("pass", False) for record in records),
    }
    (args.output_dir / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(metadata, ensure_ascii=False))
    for record in records:
        print(f"{record['id']}: {'PASS' if record.get('pass') else 'FAIL'}: {record['reason']}")
    return 0 if metadata["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
