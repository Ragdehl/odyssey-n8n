"""Exploratory *real-LLM* light-router/context PoC; never imports runtime mutators.

Genuine OpenAI calls with store=false, immutable whole message, bounded cost.
Reads a TEMPORARY CLONE of DEV Markdown solely to supply minimal verified name hints.
It tests SEMANTIC FEASIBILITY, not Core Writer/E3 or n8n/UI completion.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from openai import OpenAI

from benchmarks.application_router.light_router_poc_20261016.prompt_contract import (
    PLANNER_INSTRUCTIONS,
    ROUTER_INSTRUCTIONS,
)
from odyssey_apps.schema_extensions import compose_application_schema
from odyssey_apps.tasks.schema import TASK_SCHEMA_EXTENSION
from odyssey_core.notes import parse_note, validate_note
from odyssey_core.storage import VaultRepository

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
VAULT = Path("/data/odyssey-dev/vault")
MODEL_ROUTE = "gpt-6-luna"
MODEL_PLAN = "gpt-5.6-luna"
CASES = [
    ("maya_simple", "Ayer hablé con Maya."),
    ("guillermo_control", "Hoy he conocido a Guillermo."),
    (
        "children_subject",
        "Mis hijos fueron al parque, después comieron un helado y por la tarde vieron una película.",
    ),
    ("two_dates", "Hoy he comprado pan y mañana compraré leche."),
    ("maya_pronoun", "Ayer cené con Maya y hoy he vuelto a hablar con ella."),
    (
        "ana_luis",
        "Hoy he hablado con Ana y Luis. Ana se va a París mañana y Luis vuelve el domingo.",
    ),
    ("maite_cross_app", "Hoy he conocido a Maite, mañana tengo que llamarla."),
    (
        "maite_variant",
        "He conocido a una chica llamada Nora. Tengo que enviarle un correo el lunes.",
    ),
    ("independent_apps", "Tengo que llamar al banco mañana. Por cierto, me gusta el jazz."),
    ("gender_disambiguated", "Ayer vi a Ana y Luis; mañana iré con él al cine."),
    ("ambiguous_two_males", "Ayer vi a Eric y Luis; mañana iré con él al cine."),
]
RATE = {MODEL_ROUTE: (0.10, 0.50), MODEL_PLAN: (0.20, 1.20)}
MAX_CALLS = 22
MAX_USD = 0.085

ROUTE_SCHEMA = {
    "type": "object",
    "properties": {
        "capabilities": {
            "type": "array",
            "items": {"type": "string", "enum": ["core", "tasks", "temporal"]},
        },
        "interpretation": {"type": "string", "enum": ["joint", "separable"]},
        "reason": {
            "type": "string",
            "enum": ["single", "shared_subject", "shared_reference", "shared_event", "independent"],
        },
        "app_scopes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "capability": {"type": "string", "enum": ["core", "tasks"]},
                    "description": {"type": "string"},
                    "depends_on_another_scope": {"type": "boolean"},
                },
                "required": ["capability", "description", "depends_on_another_scope"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["capabilities", "interpretation", "reason", "app_scopes"],
    "additionalProperties": False,
}
ENTITY = {
    "type": "object",
    "properties": {
        "mention": {"type": "string"},
        "canonical_name": {"type": ["string", "null"]},
        "note_type": {"type": "string", "enum": ["person", "project"]},
        "confidence": {"type": "string", "enum": ["explicit", "inferred_unambiguous", "ambiguous"]},
    },
    "required": ["mention", "canonical_name", "note_type", "confidence"],
    "additionalProperties": False,
}
FACT = {
    "type": "object",
    "properties": {
        "meaning": {"type": "string"},
        "kind": {"type": "string", "enum": ["record", "task"]},
        "subject": {"type": "string"},
        "date": {"type": ["string", "null"]},
        "daypart": {"type": ["string", "null"]},
        "participants": {"type": "array", "items": {"type": "string"}},
        "source_evidence": {"type": "string"},
        "dependent_on_fact_index": {"type": ["integer", "null"]},
        "needs_clarification": {"type": "boolean"},
    },
    "required": [
        "meaning",
        "kind",
        "subject",
        "date",
        "daypart",
        "participants",
        "source_evidence",
        "dependent_on_fact_index",
        "needs_clarification",
    ],
    "additionalProperties": False,
}
PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "entities": {"type": "array", "items": ENTITY},
        "facts": {"type": "array", "items": FACT},
        "unresolved": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["entities", "facts", "unresolved"],
    "additionalProperties": False,
}


class BoundedProvider:
    def __init__(self, actual):
        self.actual = actual
        self.calls = []
        self.usd = 0.0

    def create(self, **kwargs):
        model = kwargs["model"]
        if (
            len(self.calls) >= MAX_CALLS
            or self.usd >= MAX_USD
            or model not in RATE
            or kwargs.get("store") is not False
        ):
            raise RuntimeError("PoC budget/privacy/model guard")
        started = time.perf_counter()
        output = self.actual.create(**kwargs)
        inp = int(getattr(output.usage, "input_tokens", 0) or 0)
        outp = int(getattr(output.usage, "output_tokens", 0) or 0)
        rate = RATE[model]
        cost = (inp * rate[0] + outp * rate[1]) / 1_000_000
        self.usd += cost
        self.calls.append(
            {
                "model": model,
                "duration_s": round(time.perf_counter() - started, 2),
                "input_tokens": inp,
                "output_tokens": outp,
                "estimated_usd": round(cost, 7),
                "status": output.status,
            }
        )
        if self.usd > MAX_USD:
            raise RuntimeError("PoC budget reached after provider call")
        return output


def prompt(client, model, system, payload, schema, name):
    result = client.create(
        model=model,
        reasoning={"effort": "low"},
        max_output_tokens=1700,
        store=False,
        input=[
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
        text={"format": {"type": "json_schema", "name": name, "strict": True, "schema": schema}},
    )
    if result.status != "completed":
        raise RuntimeError("Model response incomplete: " + result.status)
    return json.loads(result.output_text)


def relevant_notes(repo, text):
    notes = []
    words = set(re.findall(r"[\wÀ-ÿ]+", text.casefold()))
    for path in repo.list_markdown_paths():
        note = parse_note(repo.read_text(path))
        if note.metadata["type"] not in ("person", "project"):
            continue
        name = str(note.metadata["name"])
        parts = [p.casefold() for p in re.findall(r"[\wÀ-ÿ]+", name)]
        if parts and len(parts[0]) >= 3 and parts[0] in words:
            notes.append(
                {"name": name, "type": note.metadata["type"], "id": str(note.metadata["id"])}
            )
    family = []
    if "mis hijos" in text.casefold():
        for path in repo.list_markdown_paths():
            note = parse_note(repo.read_text(path))
            if note.metadata["id"] == "odyssey-dev-synthetic-person":
                # Discover authenticated synthetic DEV family links from authoritative Note.
                body = repo.read_text(path)
                match = re.search(r"Mis hijos son (.+?)\.\n", body)
                if match:
                    for target, label in re.findall(r"\[\[([^\]|]+)\|([^\]]+)\]\]", match.group(1)):
                        family.append({"name": label, "verified_link": target})
                break
    return notes, family


def main():
    if os.getenv("ODYSSEY_APPROVE_LIGHT_POC") != "1":
        raise SystemExit("Missing explicit PoC opt-in")
    if not os.getenv("OPENAI_API_KEY"):
        raise SystemExit("No OpenAI API key")
    if not VAULT.is_dir():
        raise SystemExit("No DEV Markdown root")
    output = {
        "name": "light_router_poc_20261016",
        "utc_now": datetime.now(ZoneInfo("UTC")).isoformat(),
        "code_commit": "10b9ddf",
        "model_router": MODEL_ROUTE,
        "model_shared_planner": MODEL_PLAN,
        "max_usd": MAX_USD,
        "has_real_write_readback": False,
        "has_n8n_ui_e2e": False,
        "revision": "v2-generic-constraints",
        "cases": [],
    }
    provider = BoundedProvider(OpenAI(max_retries=0, timeout=70).responses)
    only = sys.argv[1] if len(sys.argv) > 1 else None
    if only and only not in {name for name, _ in CASES}:
        raise SystemExit("Unknown case")
    selected_cases = [(name, text) for name, text in CASES if not only or name == only]
    report_path = OUT / ("observations_" + only + ".json" if only else "observations.json")
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="odyssey-real-vault-light-poc-") as tmp:
        temp_root = Path(tmp) / "vault"
        temp_root.mkdir()
        for source in VAULT.rglob("*.md"):
            if ".git" in source.parts:
                continue
            dst = temp_root / source.relative_to(VAULT)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, dst)
        repo = VaultRepository(temp_root)
        schema = compose_application_schema(
            json.loads((ROOT / "config/note-schema.json").read_text()), (TASK_SCHEMA_EXTENSION,)
        )
        note_count = len(repo.list_markdown_paths())
        for path in repo.list_markdown_paths():
            validate_note(parse_note(repo.read_text(path)), schema)
        output["real_dev_vault_clone_count"] = note_count
        clock = {"date": "2026-10-16", "time": "11:00:00", "timezone": "Europe/Paris"}
        router_instructions = ROUTER_INSTRUCTIONS
        planner_instructions = PLANNER_INSTRUCTIONS
        for ident, source in selected_cases:
            local_begin = time.perf_counter()
            notes, family = relevant_notes(repo, source)
            row = {
                "case": ident,
                "original_source": source,
                "known_relevant_notes": notes,
                "verified_family": family,
                "router": None,
                "shared_plan": None,
                "error": None,
            }
            try:
                route = prompt(
                    provider,
                    MODEL_ROUTE,
                    router_instructions,
                    {"original_source": source, "clock": clock},
                    ROUTE_SCHEMA,
                    "odyssey_light_capability_route_v1",
                )
                plan = prompt(
                    provider,
                    MODEL_PLAN,
                    planner_instructions,
                    {
                        "original_source": source,
                        "clock": clock,
                        "routing_hint": route,
                        "known_notes": notes,
                        "verified_family": family,
                    },
                    PLAN_SCHEMA,
                    "odyssey_light_shared_semantic_plan_v1",
                )
                for fact in plan["facts"]:
                    if fact["source_evidence"] not in source:
                        raise ValueError("Model fact source evidence not exact substring")
                    if fact["dependent_on_fact_index"] is not None and (
                        fact["dependent_on_fact_index"] < 0
                        or fact["dependent_on_fact_index"] >= plan["facts"].index(fact)
                    ):
                        raise ValueError("Unsafe or invalid dependency index")
                row["router"] = route
                row["shared_plan"] = plan
            except Exception as error:
                row["error"] = f"{type(error).__name__}: {str(error)[:200]}"
            row["duration_s"] = round(time.perf_counter() - local_begin, 2)
            output["cases"].append(row)
            output["calls"] = len(provider.calls)
            output["estimated_total_usd"] = round(provider.usd, 7)
            report_path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n")
            print(
                json.dumps(
                    {
                        "case": ident,
                        "error": row["error"],
                        "reason": row["router"]["reason"] if row["router"] else None,
                        "mode": row["router"]["interpretation"] if row["router"] else None,
                        "fact_count": len(row["shared_plan"]["facts"])
                        if row["shared_plan"]
                        else None,
                        "participants": [f["participants"] for f in row["shared_plan"]["facts"]]
                        if row["shared_plan"]
                        else None,
                        "duration_s": row["duration_s"],
                        "usd": output["estimated_total_usd"],
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
        output["provider_calls"] = provider.calls
        output["total_duration_s"] = round(time.perf_counter() - started, 2)
        output["clone_discarded"] = True
        report_path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n")
    print(
        "SUMMARY",
        json.dumps(
            {
                "cases": len(output["cases"]),
                "calls": len(provider.calls),
                "estimated_usd": output["estimated_total_usd"],
                "duration_s": output["total_duration_s"],
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
