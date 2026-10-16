"""Real-provider existing FULL-SOURCE Core→Writer feasibility control on cloned 97 DEV notes.

This is NOT light Router integration: demonstrates whether the already-existing
unused full-message seam passes the current Core prewrite guards and Writer.
No mutations to DEV/PROD, no n8n/browser; derived embeddings are synthetic.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

from openai import OpenAI

from odyssey_apps.fact_candidates import OpenAIFactCandidateRouter
from odyssey_apps.schema_extensions import compose_application_schema
from odyssey_apps.tasks.schema import TASK_SCHEMA_EXTENSION
from odyssey_core.candidate_attribution import OpenAICoreCandidateAttributor
from odyssey_core.context import ContextIndex
from odyssey_core.experimental_luna_planning import OpenAILunaExperimentalPlanner
from odyssey_core.notes import parse_note, validate_note
from odyssey_core.semantic import SemanticEntityIndex
from odyssey_core.storage import VaultRepository
from odyssey_core.temporal_interpretation import OpenAITemporalInterpreter
from odyssey_runtime.complete_source_handoff import execute_complete_message_with_core
from tests.runtime.test_temporal_user_path_e2e import ConstantEmbedder

ROOT = Path(__file__).resolve().parents[3]
SRC = Path("/data/odyssey-dev/vault")
OUT = Path(__file__).resolve().parent
CASES = [
    ("maya_simple", "Ayer hablé con Maya."),
    ("guillermo_existing", "Hoy he conocido a Guillermo."),
    (
        "children_shared",
        "Mis hijos fueron al parque, después comieron un helado y por la tarde vieron una película.",
    ),
]
RATE = {"gpt-6-luna": (0.10, 0.50), "gpt-5.6-luna": (0.20, 1.20)}


class Budget:
    def __init__(self, base):
        self.base = base
        self.calls = []
        self.usd = 0

    def create(self, **kw):
        if (
            len(self.calls) >= 16
            or self.usd > 0.035
            or kw.get("store") is not False
            or kw.get("model") not in RATE
        ):
            raise RuntimeError("isolated full-source PoC call/budget guard")
        r = self.base.create(**kw)
        u = r.usage
        inp = int(getattr(u, "input_tokens", 0) or 0)
        out = int(getattr(u, "output_tokens", 0) or 0)
        a, b = RATE[kw["model"]]
        cost = (inp * a + out * b) / 1e6
        self.usd += cost
        self.calls.append(
            {
                "model": kw["model"],
                "input_tokens": inp,
                "output_tokens": out,
                "usd": round(cost, 7),
                "status": r.status,
            }
        )
        return r


def clone(root: Path):
    root.mkdir()
    for f in SRC.rglob("*.md"):
        if ".git" in f.parts:
            continue
        target = root / f.relative_to(SRC)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, target)
    return VaultRepository(root)


def main():
    if os.getenv("ODYSSEY_APPROVE_LIGHT_POC") != "1":
        raise RuntimeError("Missing PoC approval")
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("Missing provider key")
    schema = compose_application_schema(
        json.loads((ROOT / "config/note-schema.json").read_text()), (TASK_SCHEMA_EXTENSION,)
    )
    clock = {"date": "2026-10-16", "time": "11:00:00", "timezone": "Europe/Paris"}
    api = Budget(OpenAI(max_retries=0, timeout=65).responses)
    sdk = SimpleNamespace(responses=api)
    report = {
        "name": "full-source existing Core/Writer baseline on copied live DEV Markdown",
        "not_light_router_implementation": True,
        "uses_real_model": True,
        "provider_store": False,
        "mock_embeddings": True,
        "can_write_to_actual_dev": False,
        "cases": [],
    }
    import odyssey_core.candidate_attribution as attribution_module

    original_review = attribution_module.review_model_candidate_fact_coverage
    selected = [x for x in CASES if len(sys.argv) == 1 or x[0] == sys.argv[1]]
    if not selected:
        raise SystemExit("Unknown case")
    out_path = OUT / (
        "integration_detail_" + sys.argv[1] + ".json"
        if len(sys.argv) > 1
        else "integration_control.json"
    )
    for name, source in selected:
        with tempfile.TemporaryDirectory(prefix="odyssey-poc-integration-") as tmp:
            base = Path(tmp)
            repo = clone(base / "vault")
            files = repo.list_markdown_paths()
            for path in files:
                validate_note(parse_note(repo.read_text(path)), schema)
            before = {path: repo.read_text(path) for path in files}
            emb = ConstantEmbedder()
            idx = ContextIndex(base / "ctx.sqlite3")
            sem = SemanticEntityIndex(base / "semantic.sqlite3")
            idx.rebuild(repo, schema, emb)
            sem.rebuild(repo, schema, emb)
            row = {
                "case": name,
                "original_source": source,
                "source_note_count": len(files),
                "status": None,
                "reason": None,
                "error": None,
                "changes": [],
                "readback": False,
            }
            started = time.perf_counter()
            calls_start = len(api.calls)

            def audited_review(*args, _row=row, **kwargs):
                try:
                    return original_review(*args, **kwargs)
                except Exception as e:
                    _row["coverage_exception"] = str(e)[:330]
                    _row["coverage_cause"] = str(e.__cause__)[:330] if e.__cause__ else None
                    plan = args[2] if len(args) > 2 else None
                    _row["plan_facts"] = [
                        str(u.facts)[:240]
                        for a in getattr(plan, "actions", ())
                        for u in getattr(a, "units", ())
                    ]
                    _row["plan_unit_guards"] = [
                        {
                            "type": u.target.type,
                            "query": u.target.query,
                            "force_create": u.force_create,
                            "reference_only": u.reference_lookup_only,
                            "ref_count": len(u.references),
                            "facts": len(u.facts),
                        }
                        for a in getattr(plan, "actions", ())
                        for u in getattr(a, "units", ())
                    ]
                    raise

            attribution_module.review_model_candidate_fact_coverage = audited_review
            try:
                result = execute_complete_message_with_core(
                    source,
                    router=OpenAIFactCandidateRouter(sdk, prompt_revision="v6"),
                    temporal=OpenAITemporalInterpreter(
                        sdk, clock, max_output_tokens=1536, scoped_date_time_context=True
                    ),
                    core_planner_factory=lambda c, d: OpenAILunaExperimentalPlanner(
                        sdk, schema, clock, candidate_context=c, domain_interpretation=d
                    ),
                    core_candidate_attributor=OpenAICoreCandidateAttributor(sdk),
                    repository=repo,
                    schema=schema,
                    context_index=idx,
                    semantic_index=sem,
                    embedder=emb,
                    contextual_reasoner=object(),
                    actor="light-poc-isolated-test",
                    now="2026-10-16T11:00:00+02:00",
                    context_limit=5,
                    request_id_factory=lambda _name=name: "isolated-light-poc-" + _name,
                )
                row["status"] = result.status.value
                row["reason"] = result.clarification_code
                row["stages"] = [
                    {
                        "name": s.name,
                        "outcome": s.outcome.value,
                        "error_category": str(s.error_category) if s.error_category else None,
                    }
                    for s in result.operational.stages
                ]
                row["affected_stable_note_ids"] = list(result.affected_stable_note_ids)
            except Exception as e:
                row["status"] = "exception"
                row["error"] = f"{type(e).__name__}: {str(e)[:210]}"
            finally:
                attribution_module.review_model_candidate_fact_coverage = original_review
            now = {path: repo.read_text(path) for path in repo.list_markdown_paths()}
            row["changes"] = [
                path for path in now if path not in before or now[path] != before[path]
            ]
            row["readback"] = any(
                "odyssey:fact request=isolated-light-poc-" + name in doc for doc in now.values()
            )
            row["duration_s"] = round(time.perf_counter() - started, 2)
            row["model_calls"] = api.calls[calls_start:]
            report["cases"].append(row)
            report["estimated_total_usd"] = round(api.usd, 7)
            out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
            print(
                json.dumps(
                    {
                        "case": name,
                        "status": row["status"],
                        "reason": row["reason"],
                        "error": row["error"],
                        "changes": row["changes"],
                        "readback": row["readback"],
                        "calls": len(row["model_calls"]),
                        "usd": report["estimated_total_usd"],
                        "seconds": row["duration_s"],
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
    report["temporary_vaults_discarded"] = True
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
