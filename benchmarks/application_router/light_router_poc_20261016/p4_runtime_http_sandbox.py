"""P4 isolated REAL HTTP runtime acceptance with new model calls, existing Core Writer.

This is a transport acceptance HARNESS, not a deployed light Router.
n8n and browser are not on this path; output reports these limitations.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from dataclasses import replace
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from types import SimpleNamespace
from uuid import uuid4

from openai import OpenAI

from benchmarks.application_router.light_router_poc_20261016.p2_integrated_bridge import (
    OUT,
    ROOT,
    clone,
    evidence_check,
    plan_for_record,
    plan_for_task,
    reject_unproven_existing_name_collision,
    reviewed_semantics,
)
from benchmarks.application_router.light_router_poc_20261016.p4_physical_readback import (
    assert_reviewed_markdown,
)
from benchmarks.application_router.light_router_poc_20261016.p4_speaker_live_matrix import (
    PROMPT_A,
    PROMPT_B,
    SPEAKER_SCHEMA,
)
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
from odyssey_core.application import ApplicationResult, ApplicationStatus, execute_request
from odyssey_core.context import ContextIndex
from odyssey_core.identity_boundary import AuthenticatedActorContext, SelfBindingRepository
from odyssey_core.local_conversations import ConversationRootResolver
from odyssey_core.note_queries import NotesQueryService
from odyssey_core.notes import parse_note, validate_note
from odyssey_core.request_planning import (
    KnowledgeReference,
    KnowledgeUnit,
    RequestPlan,
    SelectionCriteria,
    WriteAction,
)
from odyssey_core.whole_message_coverage import WholeMessageCoverageError
from odyssey_core.whole_message_identity_guard import UnprovenPersonIdentityError
from odyssey_core.whole_message_speaker_proof import (
    WholeMessageSpeakerError,
    attach_speaker_to_day_action,
    validate_dual_speaker_review,
)
from odyssey_runtime.composition import RuntimeComposition
from odyssey_runtime.server import _handler_for
from tests.core.test_reference_preflight import EmptyIndex, UnresolvedReasoner
from tests.runtime.test_temporal_user_path_e2e import ConstantEmbedder

CLOCK = {"date": "2026-10-16", "time": "15:30:00", "timezone": "Europe/Paris"}
NOW = "2026-10-16T15:30:00+02:00"
INPUTS = (
    ("http-maya-1", "Ayer hablé con Maya."),
    ("http-maya-2", "Ayer cené con Maya y hoy he vuelto a hablar con ella."),
    ("http-maite-3", "Hoy he conocido a Maite, mañana tengo que llamarla."),
    (
        "http-ana-4",
        "Hoy he hablado con Ana y Luis. Ana se va a París mañana y Luis vuelve el domingo.",
    ),
    ("http-ambig-5", "Ayer vi a Eric y Luis; mañana iré con él al cine."),
)


EXTENDED_INPUTS = (
    ("http-guillem-short-6", "Hoy he conocido a Guillem."),
    ("http-guillem-exact-7", "Hoy he conocido a Guillem Valls."),
    ("http-guillem-undated-8", "He conocido a Guillem Valls."),
    ("http-third-guillem-9", "Hoy Guillem Valls ha conocido a Sergio."),
    ("http-two-days-10", "Hoy compré pan y mañana compraré leche."),
    ("http-guillermo-11", "Hoy he conocido a Guillermo."),
    ("http-guillem-pronoun-12", "Hoy he conocido a Guillem Valls, mañana tengo que llamarlo."),
    ("http-negative-13", "No he conocido a Guillem Valls."),
    ("http-conditional-14", "Si mañana conociera a Guillem Valls, lo llamaría."),
    ("http-experiencer-15", "A mí me gusta la subida."),
    ("http-elided-16", "Me encanta pasear por la montaña."),
    ("http-new-guillem-17", "Hoy he conocido a Guillem Prueba."),
)


def undated_self_record(facts):
    """A validated speaker assertion belongs to SELF, not an invented Day."""
    helpers = {}
    refs = []
    values = []
    for item in facts:
        text = item["reviewed_text"]
        for index, name in enumerate(item["reference_names"]):
            helper = helpers.setdefault(name, len(helpers))
            slot = len(refs)
            refs.append(KnowledgeReference(helper + 1, "person", name))
            text = text.replace("{{ref:" + str(index) + "}}", "{{ref:" + str(slot) + "}}")
        values.append(text)
    owner = KnowledgeUnit(
        SelectionCriteria(None, "yo", "person", (), None, self_target="self"),
        "record",
        (),
        (),
        tuple(values),
        tuple(refs),
    )
    helper_units = tuple(
        KnowledgeUnit(
            SelectionCriteria(name, name, "person", (), None),
            "record",
            (),
            (),
            (),
            (),
            reference_lookup_only=True,
        )
        for name in helpers
    )
    return RequestPlan((WriteAction((owner, *helper_units)),), ())


def run():
    if os.getenv("ODYSSEY_APPROVE_LIGHT_POC") != "1":
        raise SystemExit("Explicit isolated P4 approval required")
    extended = "--extended" in os.sys.argv
    selected_inputs = INPUTS + EXTENDED_INPUTS if extended else INPUTS
    only = os.getenv("ODYSSEY_P4_ONLY")
    if only:
        selected_inputs = tuple(item for item in selected_inputs if item[0] in only.split(","))
    report_file = (
        "p4_runtime_http_extended_receipts.json" if extended else "p4_runtime_http_receipts.json"
    )
    schema = compose_application_schema(
        json.loads((ROOT / "config/note-schema.json").read_text()), (TASK_SCHEMA_EXTENSION,)
    )
    report = {
        "test": "isolated product HTTP runtime with genuine live LLM Router Planner Reviewer",
        "transport": "real TCP HTTP via odyssey_runtime.server._handler_for on ephemeral loopback",
        "n8n_traversed": False,
        "browser_traversed": False,
        "full_prod_embeddings": False,
        "isolated_dev_clone": True,
        "source_note_count": 97,
        "cases": [],
    }
    with tempfile.TemporaryDirectory(prefix="odyssey-p4-http-") as tmp:
        temp = Path(tmp)
        repo = clone(temp / "vault")
        state = temp / "state"
        state.mkdir()
        actor = AuthenticatedActorContext(str(uuid4()))
        bindings = SelfBindingRepository(state, repo, schema)
        bindings.bind(actor.stable_user_id, "odyssey-dev-synthetic-person")
        for path in repo.list_markdown_paths():
            validate_note(parse_note(repo.read_text(path)), schema)
        embed = ConstantEmbedder()
        index = ContextIndex(temp / "context.sqlite3")
        index.rebuild(repo, schema, embed)
        client = OpenAI(max_retries=0, timeout=70)
        provider_usage = []
        speaker_usage = []
        calls = []
        semantic_diagnostics = {}
        acceptance_failures = []

        def execute_route(source, request_id, auth, conversation_id):
            assert auth == actor and conversation_id == "main"
            calls.append(request_id)
            local_provider = BoundedProvider(client.responses)
            route = prompt(
                local_provider,
                MODEL_ROUTE,
                ROUTER_INSTRUCTIONS,
                {"original_source": source, "clock": CLOCK},
                ROUTE_SCHEMA,
                "odyssey_light_capability_route_v1",
            )
            hints, family = relevant_notes(repo, source)
            proposed = prompt(
                local_provider,
                MODEL_PLAN,
                PLANNER_INSTRUCTIONS,
                {
                    "original_source": source,
                    "clock": CLOCK,
                    "routing_hint": route,
                    "known_notes": hints,
                    "verified_family": family,
                },
                PLAN_SCHEMA,
                "odyssey_light_shared_semantic_plan_v1",
            )
            provider_usage.extend(local_provider.calls)
            proposed["_allowed_capabilities"] = route["capabilities"]
            review, _ = reviewed_semantics(client, source, proposed)
            semantic_diagnostics[request_id] = {"router": route, "plan": proposed, "review": review}
            try:
                evidence_check(source, proposed, review)
                reject_unproven_existing_name_collision(repo, schema, review)
                attested = None
                if extended:
                    speaker_provider = BoundedProvider(client.responses)
                    payload = {
                        "original_source": source,
                        "facts": [
                            {"source_evidence": f["source_evidence"]} for f in proposed["facts"]
                        ],
                        "clock": CLOCK,
                    }
                    first = prompt(
                        speaker_provider,
                        MODEL_PLAN,
                        PROMPT_A,
                        payload,
                        SPEAKER_SCHEMA,
                        "odyssey_speaker_full_A",
                    )
                    second = prompt(
                        speaker_provider,
                        MODEL_ROUTE,
                        PROMPT_B,
                        payload,
                        SPEAKER_SCHEMA,
                        "odyssey_speaker_full_B",
                    )
                    speaker_usage.extend(speaker_provider.calls)
                    semantic_diagnostics[request_id]["speaker_first"] = first
                    semantic_diagnostics[request_id]["speaker_second"] = second
                    attested = validate_dual_speaker_review(
                        source, proposed["facts"], first, second
                    )
                    semantic_diagnostics[request_id]["authenticated_speaker_roles"] = [
                        attested.requires_self_link(i) for i in range(len(attested.facts))
                    ]
                    if any(f.assertion not in {"asserted", "planned"} for f in attested.facts):
                        raise WholeMessageCoverageError(
                            "Conditional/negated event cannot be promoted"
                        )
                elif any(
                    item["kind"] == "record" and item["date"] is None for item in review["facts"]
                ):
                    raise WholeMessageCoverageError("Record owner not established")
            except (
                WholeMessageCoverageError,
                UnprovenPersonIdentityError,
                WholeMessageSpeakerError,
            ) as error:
                semantic_diagnostics[request_id]["rejection"] = (
                    type(error).__name__ + ": " + str(error)[:180]
                )
                # Bounded public diagnostic; source/model messages must never leak.
                return ApplicationResult(
                    request_id,
                    ApplicationStatus.NEEDS_ATTENTION,
                    (),
                    (),
                    clarification_code="FULL_SOURCE_REVIEW_OR_IDENTITY_UNVERIFIED",
                )
            results = []
            for day in sorted(
                {
                    f["date"]
                    for f in review["facts"]
                    if f["kind"] == "record" and f["date"] is not None
                }
            ):
                assert day
                fixed = plan_for_record(review, day)
                if extended and attested is not None:
                    positions = [
                        i
                        for i, f in enumerate(review["facts"])
                        if f["kind"] == "record" and f["date"] == day
                    ]
                    flags = [attested.requires_self_link(i) for i in positions]
                    fixed = replace(
                        fixed, actions=(attach_speaker_to_day_action(fixed.actions[0], flags),)
                    )
                result = execute_request(
                    source,
                    planner=SimpleNamespace(plan=lambda _s, _p=fixed: _p),
                    repository=repo,
                    schema=schema,
                    context_index=index,
                    semantic_index=EmptyIndex(),
                    embedder=embed,
                    contextual_reasoner=UnresolvedReasoner(),
                    authenticated_actor=auth,
                    self_binding_repository=bindings,
                    actor="p4-http-isolated",
                    now=NOW,
                    context_limit=7,
                    request_id_factory=lambda _day=day: f"{request_id}-day-{_day}",
                )
                results.append(result)
                if result.status is not ApplicationStatus.COMPLETED:
                    break
                index.rebuild(repo, schema, embed)
            else:
                undated = [
                    (i, f)
                    for i, f in enumerate(review["facts"])
                    if f["kind"] == "record" and f["date"] is None
                ]
                if undated:
                    if attested is None or not all(
                        attested.requires_self_link(i) for i, _ in undated
                    ):
                        return ApplicationResult(
                            request_id,
                            ApplicationStatus.NEEDS_ATTENTION,
                            (),
                            (),
                            clarification_code="UNVERIFIED_UNDATED_OWNER",
                        )
                    fixed = undated_self_record([f for _, f in undated])
                    undated_result = execute_request(
                        source,
                        planner=SimpleNamespace(plan=lambda *_, _plan=fixed: _plan),
                        repository=repo,
                        schema=schema,
                        context_index=index,
                        semantic_index=EmptyIndex(),
                        embedder=embed,
                        contextual_reasoner=UnresolvedReasoner(),
                        authenticated_actor=auth,
                        self_binding_repository=bindings,
                        actor="p4-http-isolated",
                        now=NOW,
                        context_limit=7,
                        request_id_factory=lambda: f"{request_id}-self",
                    )
                    results.append(undated_result)
                    if undated_result.status is not ApplicationStatus.COMPLETED:
                        return replace(undated_result, request_id=request_id)
                    index.rebuild(repo, schema, embed)
                for item in [x for x in review["facts"] if x["kind"] == "task"]:
                    fixed = plan_for_task(item)
                    planned = TaskCorePlanner(
                        SimpleNamespace(plan=lambda *_, _plan=fixed: _plan),
                        TaskInterpretation(source, TaskOperation.CREATE),
                    )
                    result = execute_request(
                        source,
                        planner=planned,
                        repository=repo,
                        schema=schema,
                        context_index=index,
                        semantic_index=EmptyIndex(),
                        embedder=embed,
                        contextual_reasoner=UnresolvedReasoner(),
                        actor="p4-http-isolated",
                        authenticated_actor=auth,
                        self_binding_repository=bindings,
                        now=NOW,
                        context_limit=7,
                        write_preflight_guard=TaskLifecycleGuard(TaskOperation.CREATE),
                        request_id_factory=lambda: f"{request_id}-task",
                    )
                    results.append(result)
                    if result.status is not ApplicationStatus.COMPLETED:
                        break
                    index.rebuild(repo, schema, embed)
            if not results:
                raise ValueError("No Core/Tasks execution decisions")
            status = (
                ApplicationStatus.COMPLETED
                if all(r.status is ApplicationStatus.COMPLETED for r in results)
                else ApplicationStatus.PARTIAL
            )
            affected = tuple(dict.fromkeys(n for r in results for n in r.affected_stable_note_ids))
            # Aggregate actual Core receipts; no imaginary successful Action/Unit.
            return replace(
                results[-1],
                request_id=request_id,
                status=status,
                action_results=tuple(action for r in results for action in r.action_results),
                affected_stable_note_ids=affected,
            )

        def safe_execute_route(source, request_id, auth, conversation_id):
            try:
                return execute_route(source, request_id, auth, conversation_id)
            except Exception as error:
                semantic_diagnostics.setdefault(request_id, {})["unexpected_exception"] = (
                    type(error).__name__ + ": " + str(error)[:250]
                )
                raise

        resolver = ConversationRootResolver(state)
        runtime = RuntimeComposition(
            core_execute=lambda *_: (_ for _ in ()).throw(
                AssertionError("Legacy Core bypass is disallowed")
            ),
            refresh_indexes=lambda: None,
            conversation_root_resolver=resolver,
            hybrid_candidate_execute=safe_execute_route,
            full_source_mutation_guard=True,
        )
        server = ThreadingHTTPServer(("127.0.0.1", 0), _handler_for(runtime))
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        port = server.server_address[1]

        def post(payload):
            conn = HTTPConnection("127.0.0.1", port, timeout=90)
            conn.request(
                "POST",
                "/execute",
                json.dumps(payload, ensure_ascii=False).encode(),
                headers={"Content-Type": "application/json"},
            )
            response = conn.getresponse()
            data = json.loads(response.read())
            status = response.status
            conn.close()
            return status, data

        try:
            for request_id, source in selected_inputs:
                payload = {
                    "request": source,
                    "request_id": request_id,
                    "conversation_id": "main",
                    "authenticated_actor": {"stable_user_id": actor.stable_user_id},
                }
                old_snapshot = {p: repo.read_text(p) for p in repo.list_markdown_paths()}
                old_count = len(old_snapshot)
                started = time.perf_counter()
                status, result = post(payload)
                elapsed = round(time.perf_counter() - started, 2)
                snapshot = {p: repo.read_text(p) for p in repo.list_markdown_paths()}
                is_negative = request_id in {
                    "http-ana-4",
                    "http-ambig-5",
                    "http-guillem-short-6",
                    "http-negative-13",
                    "http-conditional-14",
                }
                safe_no_write = is_negative and snapshot == old_snapshot
                validated_readback = {}
                if (
                    not extended
                    and not is_negative
                    and status == 200
                    and result.get("status") == "completed"
                ):
                    changed = {
                        p: body for p, body in snapshot.items() if old_snapshot.get(p) != body
                    }
                    matching_fact_receipts = sum(
                        body.count("odyssey:fact request=" + request_id)
                        for body in changed.values()
                    )
                    expected_fact_count = 2 if request_id in {"http-maya-2", "http-maite-3"} else 1
                    # Maite's 2 facts are in two notes, Maya's 2 facts in two dates.
                    if matching_fact_receipts != expected_fact_count:
                        raise AssertionError(
                            "Actual Markdown fact receipts differ from the source plan"
                        )
                    person_name = "Maite" if request_id == "http-maite-3" else "Maya"
                    exact_people = [
                        parse_note(body)
                        for body in snapshot.values()
                        if parse_note(body).metadata["type"] == "person"
                        and parse_note(body).metadata["name"] == person_name
                    ]
                    if len(exact_people) != 1:
                        raise AssertionError("Person identity was duplicated or missing")
                    person_id = exact_people[0].metadata["id"]
                    backlinks = NotesQueryService(repo, schema, index).backlinks(person_id)
                    target_days = (
                        {"date:2026-10-15", "date:2026-10-16"}
                        if request_id == "http-maya-2"
                        else (
                            {"date:2026-10-15"}
                            if request_id == "http-maya-1"
                            else {"date:2026-10-16"}
                        )
                    )
                    backlink_source_ids = {b.source.id for b in backlinks.items}
                    if not target_days.issubset(backlink_source_ids):
                        raise AssertionError("Missing canonical Person Day backlink")
                    validated_readback = {
                        "fact_receipts": matching_fact_receipts,
                        "unique_person_id": person_id,
                        "backlink_source_ids": sorted(backlink_source_ids),
                        "changed_note_paths": sorted(changed),
                    }
                    if request_id == "http-maite-3":
                        tasks = [
                            parse_note(body)
                            for body in snapshot.values()
                            if parse_note(body).metadata["type"] == "task"
                            and parse_note(body).metadata["name"] == "Llamar a Maite"
                        ]
                        if (
                            len(tasks) != 1
                            or tasks[0].metadata["target_date"] != "2026-10-17"
                            or tasks[0].metadata["status"] != "pending"
                        ):
                            raise AssertionError("Maite task target/state not saved")
                        if tasks[0].metadata["id"] not in backlink_source_ids:
                            raise AssertionError("Task not backlinking the same canonical Maite")
                        validated_readback["task_id"] = tasks[0].metadata["id"]
                if extended and status == 200 and result.get("status") == "completed":
                    evidence = semantic_diagnostics[request_id]
                    try:
                        validated_readback = assert_reviewed_markdown(
                            repository=repo,
                            schema=schema,
                            context_index=index,
                            before=old_snapshot,
                            after=snapshot,
                            request_id=request_id,
                            review=evidence["review"],
                            self_roles=tuple(evidence["authenticated_speaker_roles"]),
                            self_id="odyssey-dev-synthetic-person",
                        )
                    except (AssertionError, ValueError, KeyError) as error:
                        acceptance_failures.append(request_id)
                        validated_readback = {
                            "physical_validation_failure": (
                                type(error).__name__ + ": " + str(error)[:200]
                            )
                        }
                status_replay, replayed = post(payload)
                same_bytes = {p: repo.read_text(p) for p in repo.list_markdown_paths()} == snapshot
                row = {
                    "id": request_id,
                    "source": source,
                    "http_status": status,
                    "product_status": result.get("status"),
                    "product_outcome": result.get("product_outcome"),
                    "notes": result.get("affected_stable_note_ids"),
                    "action_count": len(result.get("actions", [])),
                    "duration_s": elapsed,
                    "replay_http_status": status_replay,
                    "replay_marked": replayed.get("delivery_replayed", False),
                    "replay_preserved_all_note_bytes": same_bytes,
                    "notes_added": len(repo.list_markdown_paths()) - old_count,
                    "network_errors": result.get("error"),
                    "real_model_runs": calls.count(request_id),
                    "expected_safe_abstention": is_negative,
                    "safe_no_write": safe_no_write,
                    "validated_canonical_readback": validated_readback,
                    "prewrite_rejection": semantic_diagnostics.get(request_id, {}).get("rejection"),
                    "unexpected_exception": semantic_diagnostics.get(request_id, {}).get(
                        "unexpected_exception"
                    ),
                }
                report["cases"].append(row)
                print(json.dumps(row, ensure_ascii=False), flush=True)
                (OUT / report_file).write_text(
                    json.dumps(report, ensure_ascii=False, indent=2) + "\n"
                )
                if (
                    status != 200
                    or result.get("status") != ("needs_attention" if is_negative else "completed")
                    or (is_negative and not safe_no_write)
                    or status_replay != 200
                    or not row["replay_marked"]
                    or not same_bytes
                    or calls.count(request_id) != 1
                ):
                    acceptance_failures.append(request_id)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
        # The real runtime delivery cache must survive a NEW composition,
        # not merely short-circuit duplicate messages in the same Python process.
        restarted = RuntimeComposition(
            core_execute=lambda *_: (_ for _ in ()).throw(
                AssertionError("After restart no old Core execution is permitted")
            ),
            refresh_indexes=lambda: None,
            conversation_root_resolver=resolver,
            hybrid_candidate_execute=lambda *_: (_ for _ in ()).throw(
                AssertionError("After restart no new LLM route is permitted")
            ),
            full_source_mutation_guard=True,
        )
        retry = restarted.execute_product(
            selected_inputs[0][1], selected_inputs[0][0], "main", actor
        )
        assert retry["delivery_replayed"] is True
        report["replay_survived_new_runtime_composition"] = True
        if os.getenv("ODYSSEY_P4_DEBUG") == "1":
            report["synthetic_semantic_diagnostics"] = semantic_diagnostics
        report["llm_route_planner_calls"] = provider_usage
        report["llm_estimated_usd_route_planner"] = round(
            sum(x["estimated_usd"] for x in provider_usage), 7
        )
        report["llm_speaker_calls"] = speaker_usage
        report["llm_estimated_usd_speaker"] = round(
            sum(x["estimated_usd"] for x in speaker_usage), 7
        )
        report["temporary_vault_deleted"] = True
        report["acceptance_failures"] = acceptance_failures
        report["outcome"] = "BLOCKED" if acceptance_failures else "PASS"
    (OUT / report_file).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(
        "P4_HTTP_SANDBOX_RESULT",
        report["outcome"],
        len(report["cases"]),
        "failed",
        report["acceptance_failures"],
        flush=True,
    )
    if report["outcome"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    run()
