"""Live independent LLM reviewed family facts -> ordinary authenticated Core Writer.

Isolated cloned DEV Notes and SELF binding; not a production Router.
The relationship source span is a test fixture, NOT a production heuristic.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from openai import OpenAI

from benchmarks.application_router.light_router_poc_20261016.p2_integrated_bridge import (
    OUT,
    ROOT,
    clone,
    evidence_check,
    reviewed_semantics,
)
from odyssey_apps.schema_extensions import compose_application_schema
from odyssey_apps.tasks.schema import TASK_SCHEMA_EXTENSION
from odyssey_core.application import ApplicationStatus, execute_request
from odyssey_core.context import ContextIndex
from odyssey_core.identity_boundary import AuthenticatedActorContext, SelfBindingRepository
from odyssey_core.note_queries import NotesQueryService
from odyssey_core.request_planning import (
    KnowledgeReference,
    KnowledgeUnit,
    RequestPlan,
    SelectionCriteria,
    WriteAction,
)
from odyssey_core.whole_message_relationship_proof import (
    recheck_self_relationship,
    verify_self_relationship,
)
from tests.core.test_reference_preflight import EmptyIndex, UnresolvedReasoner
from tests.runtime.test_temporal_user_path_e2e import ConstantEmbedder


def main():
    assert os.getenv("ODYSSEY_APPROVE_LIGHT_POC") == "1"
    row = next(
        c
        for c in json.loads((OUT / "observations.json").read_text())["cases"]
        if c["case"] == "children_subject"
    )
    source = row["original_source"]
    schema = compose_application_schema(
        json.loads((ROOT / "config/note-schema.json").read_text()), (TASK_SCHEMA_EXTENSION,)
    )
    report = {
        "case": "children_subject",
        "source": source,
        "status": "failed",
        "cloned_dev": True,
        "fresh_independent_reviewer": True,
    }
    with tempfile.TemporaryDirectory(prefix="odyssey-p3-real-children-") as tmp:
        root = Path(tmp)
        repo = clone(root / "vault")
        (root / "state").mkdir()
        auth = AuthenticatedActorContext(str(uuid4()))
        bindings = SelfBindingRepository(root / "state", repo, schema)
        bindings.bind(auth.stable_user_id, "odyssey-dev-synthetic-person")
        before = {p: repo.read_text(p) for p in repo.list_markdown_paths()}
        proof = verify_self_relationship(
            source, "Mis hijos", repository=repo, schema=schema, actor=auth, bindings=bindings
        )
        plan = dict(row["shared_plan"])
        plan["_allowed_capabilities"] = row["router"]["capabilities"]
        plan["_verified_family_names"] = [name for _id, name in proof.members]
        review, usage = reviewed_semantics(
            OpenAI(max_retries=0, timeout=60), source, plan, verified_relationship=proof
        )
        report["review"] = review
        report["review_tokens"] = usage
        try:
            evidence_check(source, plan, review)
            recheck_self_relationship(
                proof, repository=repo, schema=schema, actor=auth, bindings=bindings
            )
            member_indexes = {name: index + 1 for index, (_id, name) in enumerate(proof.members)}
            reference_list = []
            fact_texts = []
            for fact in review["facts"]:
                if fact["kind"] != "record" or fact["date"] is not None:
                    raise ValueError("Shared undated group fact is outside scope")
                if set(fact["reference_names"]) != set(member_indexes):
                    raise ValueError("The reviewer omitted a proven child from a fact")
                text = fact["reviewed_text"]
                for index, name in enumerate(fact["reference_names"]):
                    local = len(reference_list)
                    reference_list.append(KnowledgeReference(member_indexes[name], "person", name))
                    text = text.replace("{{ref:" + str(index) + "}}", "{{ref:" + str(local) + "}}")
                fact_texts.append(text)
            owner = KnowledgeUnit(
                SelectionCriteria(None, "mis hijos", "person", (), None, self_target="self"),
                "record",
                (),
                (),
                tuple(fact_texts),
                tuple(reference_list),
            )
            helpers = tuple(
                KnowledgeUnit(
                    SelectionCriteria(name, name, "person", (), None),
                    "record",
                    (),
                    (),
                    (),
                    (),
                    reference_lookup_only=True,
                )
                for _id, name in proof.members
            )
            fixed = RequestPlan((WriteAction((owner, *helpers)),), ())
            embed = ConstantEmbedder()
            idx = ContextIndex(root / "context.sqlite3")
            idx.rebuild(repo, schema, embed)
            outcome = execute_request(
                source,
                planner=SimpleNamespace(plan=lambda *_: fixed),
                repository=repo,
                schema=schema,
                context_index=idx,
                semantic_index=EmptyIndex(),
                embedder=embed,
                contextual_reasoner=UnresolvedReasoner(),
                actor="p3-temp-self-group",
                authenticated_actor=auth,
                self_binding_repository=bindings,
                now="2026-10-16T11:00:00+02:00",
                context_limit=7,
                request_id_factory=lambda: "p3-real-children",
            )
            report["writer_status"] = outcome.status.value
            report["writer_units"] = [
                {"op": u.operation, "id": u.stable_note_id}
                for a in outcome.action_results
                for u in a.unit_results
            ]
            if outcome.status is not ApplicationStatus.COMPLETED:
                raise ValueError("Core Writer failed")
            idx.rebuild(repo, schema, embed)
            after = {p: repo.read_text(p) for p in repo.list_markdown_paths()}
            changed = [p for p in after if p not in before or before[p] != after[p]]
            report["changed_notes"] = changed
            self_path = next(p for p in changed if "odyssey-dev-synthetic-person" in p)
            if (
                len(changed) != 1
                or after[self_path].count("odyssey:fact request=p3-real-children") != 3
            ):
                raise AssertionError("Expected three facts on the existing SELF Note only")
            query = NotesQueryService(repo, schema, idx)
            backlinks = {}
            for note_id, name in proof.members:
                links = query.backlinks(note_id).items
                matched = [b for b in links if b.source.id == proof.source_id]
                if len(matched) != 1 or matched[0].occurrences < 3:
                    raise AssertionError("Every child must have 3 canonical backlinks")
                backlinks[name] = matched[0].occurrences
            report.update(
                {
                    "status": "completed",
                    "facts_written": 3,
                    "backlinks": backlinks,
                    "new_person_notes": 0,
                }
            )
        except Exception as error:
            report["error"] = f"{type(error).__name__}: {str(error)[:270]}"
    report["temp_vault_deleted"] = True
    (OUT / "p3_children_real_write.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    )
    print(
        json.dumps(
            {
                key: report.get(key)
                for key in (
                    "status",
                    "error",
                    "writer_status",
                    "facts_written",
                    "backlinks",
                    "new_person_notes",
                    "changed_notes",
                )
            },
            ensure_ascii=False,
        )
    )

    if report["status"] != "completed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
