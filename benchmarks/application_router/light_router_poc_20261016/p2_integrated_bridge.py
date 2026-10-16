"""P2 experimental typed semantic/source-review -> existing Core Writer & Tasks.

Do not import this into production. The independent source review is a PROVISIONAL
gate, not the existing hybrid candidate coverage contract. Every mutation is
performed by the original Core execute_request and Tasks preflight guard, but
production adoption requires formal review of this new gate.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from openai import OpenAI

from benchmarks.application_router.light_router_poc_20261016.prompt_contract import (
    PLANNER_INSTRUCTIONS,
    ROUTER_INSTRUCTIONS,
)
from benchmarks.application_router.light_router_poc_20261016.run_poc import (
    MODEL_PLAN,
    MODEL_ROUTE,
    PLAN_SCHEMA,
    ROUTE_SCHEMA,
    BoundedProvider,
    prompt,
    relevant_notes,
)
from odyssey_apps.schema_extensions import compose_application_schema
from odyssey_apps.tasks import (
    TaskCorePlanner,
    TaskInterpretation,
    TaskLifecycleGuard,
    TaskOperation,
)
from odyssey_apps.tasks.schema import TASK_SCHEMA_EXTENSION
from odyssey_core.application import ApplicationStatus, execute_request
from odyssey_core.context import ContextIndex
from odyssey_core.note_queries import NotesQueryService
from odyssey_core.notes import parse_note, validate_note
from odyssey_core.request_planning import (
    KnowledgeReference,
    KnowledgeUnit,
    PropertyChange,
    RequestPlan,
    SelectionCriteria,
    WriteAction,
)
from odyssey_core.storage import VaultRepository
from odyssey_core.temporal import TemporalAnchor
from tests.core.test_reference_preflight import EmptyIndex, UnresolvedReasoner
from tests.runtime.test_temporal_user_path_e2e import ConstantEmbedder

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
VAULT = Path("/data/odyssey-dev/vault")
CASES = (
    "maya_simple",
    "guillermo_control",
    "maya_pronoun",
    "ana_luis",
    "maite_cross_app",
    "two_dates",
)
REVIEW_MODEL = "gpt-5.6-luna"
REVIEW_SCHEMA = {
    "type": "object",
    "properties": {
        "approved": {"type": "boolean"},
        "complete": {"type": "boolean"},
        "reason": {"type": ["string", "null"]},
        "facts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "ordinal": {"type": "integer"},
                    "source_quote": {"type": "string"},
                    "kind": {"type": "string", "enum": ["record", "task"]},
                    "reviewed_text": {"type": "string"},
                    "date": {"type": ["string", "null"]},
                    "reference_names": {"type": "array", "items": {"type": "string"}},
                    "supported": {"type": "boolean"},
                },
                "required": [
                    "ordinal",
                    "source_quote",
                    "kind",
                    "reviewed_text",
                    "date",
                    "reference_names",
                    "supported",
                ],
                "additionalProperties": False,
            },
        },
    },
    "required": ["approved", "complete", "reason", "facts"],
    "additionalProperties": False,
}
REF = re.compile(r"\{\{ref:(\d+)\}\}")


def evidence_check(source: str, proposal: dict[str, Any], review: dict[str, Any]):
    facts = proposal["facts"]
    if (
        not review["approved"]
        or not review["complete"]
        or len(review["facts"]) != len(facts)
        or proposal["unresolved"]
    ):
        raise ValueError("Whole-message proof incomplete or ambiguous")
    for index, (fact, check) in enumerate(zip(facts, review["facts"], strict=True)):
        if (
            check["ordinal"] != index
            or fact["source_evidence"] not in check["source_quote"]
            or check["source_quote"] not in source
            or check["kind"] != fact["kind"]
            or check["date"] != fact["date"]
            or not check["supported"]
        ):
            raise ValueError("Source coverage mismatch")
        names = check["reference_names"]
        if len(names) != len(set(names)) or len(names) > 4:
            raise ValueError("Invalid reference set")
        valid = set(fact["participants"]) | {e["mention"] for e in proposal["entities"]}
        if not set(names).issubset(valid):
            raise ValueError("Unproven participant")
        marks = [int(s) for s in REF.findall(check["reviewed_text"])]
        if sorted(marks) != list(range(len(names))) or len(marks) != len(names):
            raise ValueError("Each Core fact needs every typed reference once")
        if any("[[" in check["reviewed_text"] or "]]" in check["reviewed_text"] for _ in (0,)):
            raise ValueError("Model attempted raw canonical link")
        if not check["reviewed_text"].strip() or len(check["reviewed_text"]) > 320:
            raise ValueError("Invalid fact text")
        if fact["needs_clarification"]:
            raise ValueError("Ambiguous fact cannot write")
        if fact["kind"] == "task" and "tasks" not in proposal.get(
            "_allowed_capabilities", ("tasks",)
        ):
            raise ValueError("Task without routing scope")
    return True


def reject_unproven_existing_name_collision(
    repo: VaultRepository, schema: dict[str, Any], review: dict[str, Any]
) -> None:
    """Conservative PoC-only safety gate: partial name match is NOT identity proof.

    There can be multiple Ana-like people or aliases. A synthetic no-candidates
    embedding index is incapable of proving identity. Abstain BEFORE any write.
    The real P2 contract will need Core-owned, evidence-backed resolution.
    """
    named_people: set[str] = set()
    for fact in review["facts"]:
        named_people.update(fact["reference_names"])
    for name in named_people:
        candidates = []
        for path in repo.list_markdown_paths():
            note = parse_note(repo.read_text(path))
            validate_note(note, schema)
            if note.metadata["type"] != "person" or note.metadata.get("deleted"):
                continue
            canonical = str(note.metadata["name"])
            if canonical.casefold().startswith(name.casefold() + " ") or name.casefold().startswith(
                canonical.casefold() + " "
            ):
                candidates.append(canonical)
        if candidates:
            raise ValueError("UNPROVEN_PARTIAL_CANONICAL_IDENTITY: " + name)


def verify_readback(
    repo: VaultRepository,
    schema: dict[str, Any],
    review: dict[str, Any],
    name: str,
    receipts: list[dict[str, Any]],
    context_index: ContextIndex,
) -> dict[str, Any]:
    """Verify every written fact physically, not only that some note changed."""
    records = [r for r in review["facts"] if r["kind"] == "record"]
    tasks = [r for r in review["facts"] if r["kind"] == "task"]
    assertions = []
    for date in sorted({r["date"] for r in records}):
        path = f"calendar/days/{date}.md"
        content = repo.read_text(path)
        owned = [r for r in records if r["date"] == date]
        expected = f"odyssey:fact request=p2-{name}-day-{date}"
        if content.count(expected) != len(owned):
            raise AssertionError(f"Day Markdown missing exact fact receipts: {date}")
        for fact in owned:
            for person in fact["reference_names"]:
                if not re.search(r"\[\[[^\]\n]+\|" + re.escape(person) + r"\]\]", content):
                    raise AssertionError("Day missing canonical participant link")
        assertions.append(f"day:{date}:{len(owned)}")
    for item in tasks:
        task_receipt = next(x for x in receipts if x["type"] == "task")
        task_id = task_receipt["units"][0]["id"]
        notes = [
            parse_note(repo.read_text(path))
            for path in repo.list_markdown_paths()
            if repo.read_text(path).find(str(task_id)) >= 0
        ]
        tasks_by_id = [x for x in notes if x.metadata.get("id") == task_id]
        if len(tasks_by_id) != 1:
            raise AssertionError("Task readback ID missing/ambiguous")
        task = tasks_by_id[0]
        if (
            task.metadata.get("type") != "task"
            or task.metadata.get("status") != "pending"
            or task.metadata.get("target_date") != item["date"]
        ):
            raise AssertionError("Task date or state not persisted")
        for person in item["reference_names"]:
            if not re.search(r"\[\[[^\]\n]+\|" + re.escape(person) + r"\]\]", task.content):
                raise AssertionError("Task missing linked person in body")
        if not any(
            f"p2-{name}-task" in repo.read_text(path) for path in repo.list_markdown_paths()
        ):
            raise AssertionError("Task body missing canonical fact receipt")
        assertions.append(f"task:{task_id}:{item['date']}")
    all_people = [
        parse_note(repo.read_text(path))
        for path in repo.list_markdown_paths()
        if parse_note(repo.read_text(path)).metadata["type"] == "person"
    ]
    for person in {ref for item in review["facts"] for ref in item["reference_names"]}:
        exact = [n for n in all_people if n.metadata["name"].casefold() == person.casefold()]
        if len(exact) != 1:
            raise AssertionError("Expected exactly one canonical person for reference")
        expected_day_ids = {
            "date:" + item["date"] for item in records if person in item["reference_names"]
        }
        task_ids = {
            receipt["units"][0]["id"]
            for receipt in receipts
            if receipt["type"] == "task"
            and any(person in item["reference_names"] for item in tasks)
        }
        query = NotesQueryService(repo, schema, context_index)
        backlinks = query.backlinks(str(exact[0].metadata["id"]))
        sources = {item.source.id for item in backlinks.items}
        if not expected_day_ids.union(task_ids).issubset(sources):
            raise AssertionError("Actual backlinks do not contain every linked fact and Task")
        assertions.append("backlinks:" + person + ":" + str(len(sources)))
    return {"assertions": assertions, "count": len(assertions)}


def clone(root: Path):
    root.mkdir()
    for source in VAULT.rglob("*.md"):
        if ".git" in source.parts:
            continue
        dest = root / source.relative_to(VAULT)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)
    return VaultRepository(root)


def make_action(
    items: list[dict[str, Any]], *, date: str | None, kind: str, other_label: str | None = None
):
    if kind == "task":
        assert len(items) == 1 and date
        item = items[0]
        title = item["reviewed_text"]
        for i, name in enumerate(item["reference_names"]):
            title = title.replace("{{ref:" + str(i) + "}}", name)
        title = title.strip().rstrip(".")
        if not title or title.startswith("Hoy "):
            raise ValueError("Unrecognized task title")
        primary = KnowledgeUnit(
            SelectionCriteria(title, title, "task", (), None),
            "record",
            (
                PropertyChange("status", "set", "pending"),
                PropertyChange("target_date", "set", date),
            ),
            (),
            (item["reviewed_text"],),
            tuple(
                KnowledgeReference(i + 1, "person", name)
                for i, name in enumerate(item["reference_names"])
            ),
            fact_temporal_anchors=((),),
            force_create=True,
        )
    elif kind == "record":
        if date is None:
            raise ValueError("Undated Core fact requires explicit owner, not Day")
        references = []
        fact_texts = []
        anchors = []
        helpers = {}
        for item in items:
            value = item["reviewed_text"]
            for index, name in enumerate(item["reference_names"]):
                helper = helpers.setdefault(name, len(helpers))
                local = len(references)
                references.append(KnowledgeReference(helper + 1, "person", name))
                value = value.replace("{{ref:" + str(index) + "}}", "{{ref:" + str(local) + "}}")
            fact_texts.append(value)
            anchors.append((TemporalAnchor.from_value(date),))
        primary = KnowledgeUnit(
            SelectionCriteria(None, date, "calendar_day", (), None),
            "record",
            (),
            (),
            tuple(fact_texts),
            tuple(references),
            fact_temporal_anchors=tuple(anchors),
        )
    else:
        raise ValueError("Unknown operation kind")
    seen = []
    if kind == "record":
        seen = list(helpers)
    else:
        seen = item["reference_names"]
    helpers_units = [
        KnowledgeUnit(
            SelectionCriteria(name, name, "person", (), None),
            "record",
            (),
            (),
            (),
            (),
            reference_lookup_only=True,
        )
        for name in seen
    ]
    return WriteAction((primary, *helpers_units))


def plan_for_record(review: dict[str, Any], date: str):
    items = [r for r in review["facts"] if r["kind"] == "record" and r["date"] == date]
    return RequestPlan((make_action(items, date=date, kind="record"),), ())


def plan_for_task(item: dict[str, Any]):
    return RequestPlan((make_action([item], date=item["date"], kind="task"),), ())


def reviewed_semantics(client: Any, source: str, proposal: dict[str, Any]):
    instructions = (
        "INDEPENDENT conservative Core source-coverage reviewer. Input original unmodified "
        "message and untrusted atomic fact suggestions from a separate LLM. Inspect every "
        "event, speaker, pronoun, obligation, person, and date; reject if fabricated, omitted, "
        "semantically misattributed, ambiguous or not entailed by exact source. "
        "All proposed facts must be covered; approval false unless complete. "
        "The current time is TRUSTED and explicitly provided in the JSON clock; "
        "relative words hoy ayer and manana MUST be resolved against it. "
        "A specific person appearing in an assertion MUST be represented by a typed {{ref:N}} marker rather than bare literal; fail if missing. "
        "For each original quoted scope, return a concise natural SPANISH fact text "
        "equivalent to what the user said. Use {{ref:0}}, {{ref:1}} etc where and ONLY "
        "where that fact has actual specific persons as participants. Reference_names ordered "
        "by marker index; they must be individuals in the supplied proposed participant list. "
        "Resolve explicit antecedents (e.g. 'ella') only where UNIQUE; never invent a name. "
        "A person identity is a suggestion for later Core resolution, NOT a canonical note ID. "
        "For tasks, write an actionable label (e.g. Llamar a {{ref:0}}.) but do NOT turn "
        "future indicative plans into obligations. Exact dates MUST equal proposed date. "
        "Preserve date=null when not specified. If the message has multiple facts, "
        "review each separately; no raw markdown or note IDs. No execution authority."
    )
    payload = {
        "source": source,
        "clock": {"date": "2026-10-16", "time": "11:00:00", "timezone": "Europe/Paris"},
        "proposed_facts": proposal["facts"],
        "proposed_entities": proposal["entities"],
        "safety_notice": "This is ONLY a semantic opinion. Core later resolves IDs and writer changes.",
    }
    reply = client.responses.create(
        model=REVIEW_MODEL,
        reasoning={"effort": "low"},
        max_output_tokens=1500,
        store=False,
        input=[
            {"role": "system", "content": instructions},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
        text={
            "format": {
                "type": "json_schema",
                "name": "odyssey_p2_source_coverage_v1",
                "strict": True,
                "schema": REVIEW_SCHEMA,
            }
        },
    )
    if reply.status != "completed":
        raise ValueError("Reviewer incomplete")
    usage = reply.usage
    return json.loads(reply.output_text), {
        "in": int(getattr(usage, "input_tokens", 0) or 0),
        "out": int(getattr(usage, "output_tokens", 0) or 0),
    }


def execute_one(repo, schema, idx, review, source, ident, now, day):
    fixed_plan = plan_for_record(review, day)
    planner = SimpleNamespace(plan=lambda text: fixed_plan)
    assert isinstance(planner.plan(source), RequestPlan)
    return execute_request(
        source,
        planner=planner,
        repository=repo,
        schema=schema,
        context_index=idx,
        semantic_index=EmptyIndex(),
        embedder=ConstantEmbedder(),
        contextual_reasoner=UnresolvedReasoner(),
        actor="p2-ephemeral-reviewed-gate",
        now=now,
        context_limit=7,
        request_id_factory=lambda: f"p2-{ident}-day-{day}",
    )


def execute_task(repo, schema, idx, review, source, ident, now, item):
    base = plan_for_task(item)
    task = TaskInterpretation(source, TaskOperation.CREATE)
    planner = TaskCorePlanner(SimpleNamespace(plan=lambda *_: base), task)
    return execute_request(
        source,
        planner=planner,
        repository=repo,
        schema=schema,
        context_index=idx,
        semantic_index=EmptyIndex(),
        embedder=ConstantEmbedder(),
        contextual_reasoner=UnresolvedReasoner(),
        actor="p2-ephemeral-reviewed-gate",
        now=now,
        context_limit=7,
        write_preflight_guard=TaskLifecycleGuard(TaskOperation.CREATE),
        request_id_factory=lambda: f"p2-{ident}-task",
    )


def main():
    if os.getenv("ODYSSEY_APPROVE_LIGHT_POC") != "1":
        raise SystemExit("PoC opt-in required")
    if not os.getenv("OPENAI_API_KEY"):
        raise SystemExit("Provider credentials required")
    fresh_models = "--fresh" in sys.argv
    arguments = set(sys.argv[1:]) - {"--fresh"}
    selected = arguments if arguments else set(CASES)
    if not selected.issubset(CASES):
        raise SystemExit("Unknown source case")
    base = json.loads((OUT / "observations.json").read_text())
    by = {case["case"]: case for case in base["cases"]}
    schema = compose_application_schema(
        json.loads((ROOT / "config/note-schema.json").read_text()), (TASK_SCHEMA_EXTENSION,)
    )
    client = OpenAI(max_retries=0, timeout=75)
    live_semantic_provider = BoundedProvider(client.responses) if fresh_models else None
    report = {
        "purpose": "P2 source→independent semantic review→existing Core Writer and Tasks",
        "fresh_semantic_route_and_plan": fresh_models,
        "WARNING": "Experimental source-review gate; NOT production candidate_coverage",
        "model": REVIEW_MODEL,
        "real_ai": True,
        "provider_store": False,
        "synthetic_embeddings": True,
        "isolated_vault": True,
        "results": [],
    }
    total_usd = 0.0
    for name in CASES:
        if name not in selected:
            continue
        record = by[name]
        source = record["original_source"]
        proposal = dict(record["shared_plan"])
        proposal["_allowed_capabilities"] = record["router"]["capabilities"]
        run = {
            "case": name,
            "source": source,
            "status": None,
            "reason": None,
            "review": None,
            "writes": [],
            "note_changes": [],
            "source_notes_count": 97,
        }
        start = time.perf_counter()
        with tempfile.TemporaryDirectory(prefix="odyssey-p2-reviewed-write-") as tmp:
            root = Path(tmp)
            repo = clone(root / "vault")
            original = {p: repo.read_text(p) for p in repo.list_markdown_paths()}
            for p in original:
                validate_note(parse_note(original[p]), schema)
            emb = ConstantEmbedder()
            idx = ContextIndex(root / "context.sqlite3")
            idx.rebuild(repo, schema, emb)
            try:
                if fresh_models:
                    notes, family = relevant_notes(repo, source)
                    current_clock = {
                        "date": "2026-10-16",
                        "time": "11:00:00",
                        "timezone": "Europe/Paris",
                    }
                    assert live_semantic_provider is not None
                    route = prompt(
                        live_semantic_provider,
                        MODEL_ROUTE,
                        ROUTER_INSTRUCTIONS,
                        {"original_source": source, "clock": current_clock},
                        ROUTE_SCHEMA,
                        "odyssey_light_capability_route_v1",
                    )
                    fresh_plan = prompt(
                        live_semantic_provider,
                        MODEL_PLAN,
                        PLANNER_INSTRUCTIONS,
                        {
                            "original_source": source,
                            "clock": current_clock,
                            "routing_hint": route,
                            "known_notes": notes,
                            "verified_family": family,
                        },
                        PLAN_SCHEMA,
                        "odyssey_light_shared_semantic_plan_v1",
                    )
                    proposal = dict(fresh_plan)
                    proposal["_allowed_capabilities"] = route["capabilities"]
                    run["fresh_router"] = route
                    run["fresh_semantic_plan"] = fresh_plan
                    run["fresh_provider_calls"] = live_semantic_provider.calls[-2:]
                review, usage = reviewed_semantics(client, source, proposal)
                total_usd += (usage["in"] * 0.2 + usage["out"] * 1.2) / 1e6
                run["review_usage"] = usage
                run["review"] = review
                evidence_check(source, proposal, review)
                reject_unproven_existing_name_collision(repo, schema, review)
                date_groups = sorted(
                    {
                        item["date"]
                        for item in review["facts"]
                        if item["kind"] == "record" and item["date"]
                    }
                )
                if len([x for x in review["facts"] if x["kind"] == "record"]) != sum(
                    1 for x in review["facts"] if x["kind"] == "record" and x["date"]
                ):
                    raise ValueError("No validated owner for undated fact")
                for date in date_groups:
                    result = execute_one(
                        repo, schema, idx, review, source, name, "2026-10-16T11:00:00+02:00", date
                    )
                    run["writes"].append(
                        {
                            "type": "core_day",
                            "date": date,
                            "status": result.status.value,
                            "reason": result.planning_error,
                            "units": [
                                {
                                    "operation": u.operation,
                                    "status": u.status.value,
                                    "id": u.stable_note_id,
                                    "reason": u.reason,
                                }
                                for a in result.action_results
                                for u in a.unit_results
                            ],
                        }
                    )
                    if result.status is not ApplicationStatus.COMPLETED:
                        raise ValueError("Core Day write not completed")
                    idx.rebuild(repo, schema, emb)
                tasks = [item for item in review["facts"] if item["kind"] == "task"]
                for item in tasks:
                    result = execute_task(
                        repo, schema, idx, review, source, name, "2026-10-16T11:00:00+02:00", item
                    )
                    run["writes"].append(
                        {
                            "type": "task",
                            "date": item["date"],
                            "status": result.status.value,
                            "reason": result.planning_error,
                            "units": [
                                {
                                    "operation": u.operation,
                                    "status": u.status.value,
                                    "id": u.stable_note_id,
                                    "reason": u.reason,
                                }
                                for a in result.action_results
                                for u in a.unit_results
                            ],
                        }
                    )
                    if result.status is not ApplicationStatus.COMPLETED:
                        raise ValueError("Tasks CREATE not completed")
                    idx.rebuild(repo, schema, emb)
                current = {p: repo.read_text(p) for p in repo.list_markdown_paths()}
                run["note_changes"] = [
                    p for p in current if p not in original or current[p] != original[p]
                ]
                run["verified_facts"] = []
                for p in run["note_changes"]:
                    note = parse_note(current[p])
                    validate_note(note, schema)
                    if p in original and current[p] == original[p]:
                        raise AssertionError("No mutation despite diff")
                    if "p2-" + name in current[p]:
                        run["verified_facts"].append(p)
                run["verified_readback"] = verify_readback(
                    repo, schema, review, name, run["writes"], idx
                )
                run["status"] = (
                    "completed"
                    if len(run["verified_facts"]) >= len(date_groups) + len(tasks)
                    else "partial"
                )
            except Exception as error:
                run["status"] = "failed"
                run["reason"] = f"{type(error).__name__}: {str(error)[:230]}"
                current = {p: repo.read_text(p) for p in repo.list_markdown_paths()}
                run["note_changes"] = [
                    p for p in current if p not in original or current[p] != original[p]
                ]
            run["duration_s"] = round(time.perf_counter() - start, 2)
            report["results"].append(run)
            report["total_estimated_usd"] = round(total_usd, 7)
            report_file = (
                "p2_integration_receipts_fresh.json"
                if fresh_models
                else "p2_integration_receipts.json"
            )
            (OUT / report_file).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
            print(
                json.dumps(
                    {
                        "case": name,
                        "status": run["status"],
                        "reason": run["reason"],
                        "notes": run["note_changes"],
                        "units": run["writes"],
                        "duration_s": run["duration_s"],
                        "usd": report["total_estimated_usd"],
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
    report["temporary_vaults_discarded"] = True
    report["fresh_semantic_estimated_usd"] = (
        round(live_semantic_provider.usd, 7) if live_semantic_provider else 0.0
    )
    report_file = (
        "p2_integration_receipts_fresh.json" if fresh_models else "p2_integration_receipts.json"
    )
    (OUT / report_file).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
