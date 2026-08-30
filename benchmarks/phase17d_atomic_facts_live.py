"""Focused live evidence for the append-first Phase 17D planner and fact selector."""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from openai import OpenAI  # noqa: E402

from odyssey_core.fact_selection import (  # noqa: E402
    FactCandidate,
    OpenAILunaFactSelector,
    validate_fact_selection,
)
from odyssey_core.request_planning import OpenAIRequestPlanner, WriteAction  # noqa: E402

SCHEMA = json.loads((ROOT / "config/note-schema.json").read_text(encoding="utf-8"))
CONTEXT = {"date": "2026-08-30", "time": "10:00", "timezone": "Europe/Paris"}
SOL_CASES = [
    ("atomic_split", "Marta trabaja en Thales, tiene dos hijos y se va a mudar a Lyon."),
    ("property_fact", "Marta ahora es mi jefa."),
    ("unregistered_concept", "Marta ahora trabaja en Thales."),
    ("transition_append", "Marta ha dejado Airbus y ahora trabaja en Thales."),
    ("correction", "Me equivoqué: Marta no trabaja en Airbus; trabaja en Thales."),
    ("explicit_remove", "Borra lo de que Marta tiene dos hijos."),
    ("reference_regression", "La amiga de Marta ahora trabaja en Airbus."),
    ("person_sentinel", "Guarda que Carlos nació el 3 de mayo de 1980."),
    ("journal_property_sentinel", "Hoy estoy pensando si cambiar el sofá."),
    ("type_sentinel", "Busca mis notas de tipo proyecto sobre Odyssey."),
    ("ordinary_write_sentinel", "Marta trabaja en Thales."),
]
LUNA_CASES = [
    ("unique_match", "borra el hecho del piano", [("r:1", "Marta toca el piano.")], "MATCH"),
    ("no_match", "borra el hecho del violín", [("r:1", "Marta toca el piano.")], "NO_MATCH"),
    (
        "ambiguous",
        "borra lo de Marta trabaja",
        [("r:1", "Marta trabaja en Thales."), ("r:2", "Marta trabaja en Airbus.")],
        "AMBIGUOUS",
    ),
    (
        "wikilink_match",
        "borra el hecho de Ada",
        [("r:1", "Marta trabaja con [[people/Ada - ada|Ada]].")],
        "MATCH",
    ),
]


def write_row(path: Path, row: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(row, ensure_ascii=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def run(output_dir: Path, *, luna_only: bool = False) -> None:
    """Run the fixed planner and selector matrices and persist inspectable evidence."""
    output_dir.mkdir(parents=True, exist_ok=True)
    client = OpenAI(max_retries=0)
    planner = OpenAIRequestPlanner(client, SCHEMA, CONTEXT)
    result_path = output_dir / "results.jsonl"
    for case_id, text in () if luna_only else SOL_CASES:
        row: dict[str, Any] = {
            "suite": "sol",
            "case": case_id,
            "input": text,
            "model": "gpt-5.6-sol",
            "reasoning": "low",
        }
        try:
            plan = planner.plan(text)
            units = [
                u
                for action in plan.actions
                if isinstance(action, WriteAction)
                for u in action.units
            ]
            row["knowledge_units"] = [asdict(u) for u in units]
            facts = [fact for unit in units for fact in unit.facts]
            properties = [change.field for unit in units for change in unit.properties]
            if case_id == "atomic_split":
                ok = len(facts) == 3
            elif case_id == "property_fact":
                ok = bool(facts) and "birth_date" not in properties
            elif case_id == "unregistered_concept":
                ok = bool(facts) and "employer" not in properties
            elif case_id == "correction":
                ok = any(u.intent == "remove" for u in units) and any(
                    u.intent == "amend" and u.facts for u in units
                )
            elif case_id == "explicit_remove":
                ok = any(u.intent == "remove" and u.facts for u in units)
            elif case_id == "reference_regression":
                ok = any("{{ref:0}}" in f for f in facts) and any(u.references for u in units)
            elif case_id == "person_sentinel":
                ok = bool(facts) and "birth_date" not in properties
            elif case_id == "journal_property_sentinel":
                ok = bool(facts) and all(field == "entry_date" for field in properties)
            elif case_id == "type_sentinel":
                ok = any(getattr(action, "kind", None) == "retrieve" for action in plan.actions)
            elif case_id == "ordinary_write_sentinel":
                ok = bool(facts) and all(u.intent in {"record", "amend"} for u in units)
            else:
                ok = bool(facts) and all(u.intent in {"record", "amend"} for u in units)
            row.update(
                {
                    "pass": ok,
                    "reason": "contract satisfied" if ok else "contract expectation failed",
                }
            )
        except Exception as exc:
            row.update({"pass": False, "reason": f"{type(exc).__name__}: {exc}"})
        write_row(result_path, row)
    selector = OpenAILunaFactSelector()
    for case_id, description, raw_candidates, expected in LUNA_CASES:
        candidates = tuple(FactCandidate(locator, text) for locator, text in raw_candidates)
        row = {
            "suite": "luna",
            "case": case_id,
            "description": description,
            "candidates": [asdict(c) for c in candidates],
            "model": "gpt-5.6-luna",
            "reasoning": "medium",
        }
        try:
            value = selector.select("marta", description, candidates)
            selected = validate_fact_selection(value, candidates)
            ok = selected.outcome == expected and (
                selected.locator in {c.locator for c in candidates}
                if selected.outcome == "MATCH"
                else selected.locator is None
            )
            row.update(
                {
                    "result": value,
                    "validated": asdict(selected),
                    "pass": ok,
                    "reason": "contract satisfied" if ok else "unexpected bounded outcome",
                }
            )
        except Exception as exc:
            row.update({"pass": False, "reason": f"{type(exc).__name__}: {exc}"})
        write_row(result_path, row)
    rows = [json.loads(line) for line in result_path.read_text(encoding="utf-8").splitlines()]
    summary = {
        "sol": [
            {"case": r["case"], "pass": r["pass"], "reason": r["reason"]}
            for r in rows
            if r["suite"] == "sol"
        ],
        "luna": [
            {"case": r["case"], "pass": r["pass"], "reason": r["reason"]}
            for r in rows
            if r["suite"] == "luna"
        ],
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--luna-only", action="store_true")
    arguments = parser.parse_args()
    run(arguments.output_dir, luna_only=arguments.luna_only)
