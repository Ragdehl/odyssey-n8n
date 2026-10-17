"""Reproducible mutation regression gate across Odyssey chat/UI/domain boundaries.

Example: python scripts/odyssey_cross_surface_gate.py --output /tmp/odyssey-gate.json
The ordinary gate is provider-free and uses disposable test vaults. Live LLM,
real n8n and authenticated browser checks remain a separate REQUIRED adoption
gate, never silently labeled passed here.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Contract coverage, not a set of special natural-language exceptions. Each
# group owns reusable invariants and is extended when a new App is introduced.
GROUPS: dict[str, tuple[str, ...]] = {
    "e2_identity_and_source": (
        "tests/core/test_execution_context.py",
        "tests/core/test_e2_person_target_subject_coverage.py",
        "tests/core/test_e2_fact_temporal_ownership.py",
        "tests/core/test_whole_message_coverage_p3.py",
        "tests/core/test_whole_message_speaker_proof_p4.py",
        "tests/core/test_whole_source_compilation_prewrite_p4.py",
        "tests/core/test_p4_source_bound_dependency.py",
        "tests/core/test_p4_dependent_source_scopes.py",
        "tests/core/test_p4_dependent_group_graph.py",
        "tests/core/test_p4_canonical_group_handoff.py",
        "tests/core/test_write_plan_enrichment_e2.py",
        "tests/runtime/test_hybrid_speaker_fact_e2e.py",
        "tests/runtime/test_full_message_corpus_regression.py",
    ),
    "task_chat_core": (
        "tests/apps/tasks/test_core_interop.py",
        "tests/apps/tasks/test_user_path_e2e.py",
        "tests/runtime/test_hybrid_task_app_delegation.py",
        "tests/runtime/test_hybrid_tasks_named_source_live_replay_20261013.py",
        "tests/runtime/test_hybrid_tasks_real_provider_replay.py",
        "tests/runtime/test_hybrid_v6_prewrite_writer_vertical.py",
    ),
    "task_ui_and_subtask": (
        "tests/apps/tasks/test_direct_mutations.py",
        "tests/apps/tasks/test_batch_preflight.py",
        "tests/apps/tasks/test_session_evidence.py",
        "tests/apps/tasks/test_session_dependency.py",
        "tests/apps/tasks/test_relationships_e2e.py",
        "tests/apps/tasks/test_lifecycle.py",
        "tests/apps/tasks/test_work_session_runtime.py",
        "tests/core/test_direct_note_mutations.py",
    ),
    "work_sessions_shared": (
        "tests/apps/tasks/test_work_sessions.py",
        "tests/apps/tasks/test_work_session_runtime.py",
        "tests/runtime/test_cross_surface_task_session_contract_p4.py",
        "tests/apps/tasks/test_work_session_e2_qualitative.py",
        "tests/apps/tasks/test_interpretation.py",
    ),
    "e3_retry_and_crashes": (
        "tests/core/test_mutation_gate.py",
        "tests/runtime/test_full_source_delivery_guard_p4.py",
        "tests/runtime/test_p4_e3_claim_forensics.py",
        "tests/runtime/test_p4_operation_manifest.py",
        "tests/runtime/test_runtime_process_safety.py",
        "tests/runtime/test_hybrid_postwrite_safety.py",
        "tests/runtime/test_conversation_reply_server_commit_p4.py",
    ),
    "canonical_graph_and_notes": (
        "tests/core/test_note_queries.py",
        "tests/core/test_context_deterministic_projection.py",
        "tests/core/test_reference_preflight.py",
        "tests/core/test_atomic_facts.py",
        "tests/runtime/test_hybrid_independent_linked_events_real_core_replay.py",
        "tests/benchmarks/test_p4_physical_readback_checks.py",
        "tests/core/test_whole_source_task_readback_p4.py",
        "tests/runtime/test_general_source_fact_graph_e2e.py",
    ),
    "runtime_http_and_isolation": (
        "tests/runtime/test_runtime_boundary.py",
        "tests/runtime/test_runtime_process_safety.py",
        "tests/runtime/test_conversation_reply_server_commit_p4.py",
        "tests/apps/tasks/test_work_session_runtime.py",
        "tests/runtime/test_cross_surface_notes_http_p4.py",
        "tests/runtime/test_whole_source_light_product_p4.py",
        "tests/runtime/test_p4_model_contract_strict_schema.py",
        "tests/runtime/test_p4_independent_mixed_scopes.py",
        "tests/runtime/test_p4_dependent_task_target.py",
        "tests/runtime/test_p4_production_composition_task_ui.py",
        "tests/runtime/test_p4_dependent_router_integrated.py",
        "tests/runtime/test_p4_dependent_n_graph_execution.py",
        "tests/runtime/test_p4_dependent_factory_product.py",
        "tests/runtime/test_p4_verified_group_e2.py",
        "tests/runtime/test_p4_taskonly_real_session_parity.py",
        "tests/runtime/test_p4_chat_to_ui_http_flow.py",
        "tests/benchmarks/test_cross_surface_gate_contract.py",
        "tests/benchmarks/test_odyssey_acceptance_contracts.py",
        "tests/benchmarks/test_odyssey_operator_status.py",
        "tests/benchmarks/test_semantic_validator_isolation_p4.py",
    ),
    "performance_and_indexes": (
        "tests/core/test_vault_repository.py",
        "tests/core/test_verified_metadata_catalog.py",
        "tests/core/test_indexed_queries_and_freshness.py",
        "tests/core/test_index_publication_races.py",
        "tests/runtime/test_p4_index_startup_reuse.py",
        "tests/benchmarks/test_performance_p1_budget.py",
        "tests/core/test_scoped_note_decode_cache.py",
        "tests/core/test_p4_indexed_name_hints.py",
        "tests/apps/tasks/test_incremental_indexes.py",
        "tests/core/test_parallel_note_lookup.py",
        "tests/runtime/test_runtime_boundary.py",
    ),
    "workflow_and_web": (
        "tests/test_odyssey_online_workflow.py",
        "tests/test_odyssey_web_static.py",
        "tests/benchmarks/test_p4_runtime_http_live_receipts.py",
    ),
}

# Tests below exercise contracts in different environments. Never claim these
# cover the actual browser->n8n->GPT->Markdown->browser route.
PENDING_LIVE_GATES = (
    "fresh real-model mixed Core/Task/Work Session/subtask requests with real provider variance",
    "real authenticated browser + n8n webhook + runtime + Writer + UI graph/donut",
    "post-write crash and multi-note recovery with real n8n and request IDs",
    "production-like indexes and 250/1000/5000-note Raspberry CPU/RAM benchmarks",
    "clarification/continuation after a partial multi-App write",
    "dependent Core+Work Session real-model and browser validation, plus NEW light-router subtask readback",
)


def validate_selection() -> None:
    if not GROUPS or any(not selectors for selectors in GROUPS.values()):
        raise ValueError("Every mutation surface must have a nonempty test group")
    for group, selectors in GROUPS.items():
        if not re.fullmatch(r"[a-z0-9_]+", group):
            raise ValueError("Invalid regression group")
        for selector in selectors:
            if not selector.startswith("tests/") or not selector.endswith(".py"):
                raise ValueError(f"Unsafe non-test selector: {selector}")
            if not (ROOT / selector).is_file():
                raise ValueError(f"Required test file is missing: {selector}")


def run(*, names: list[str], output: Path | None, python: str) -> int:
    validate_selection()
    unknown = sorted(set(names) - GROUPS.keys())
    if unknown:
        raise ValueError(f"Unknown group(s): {', '.join(unknown)}")
    # Deduplicate shared test files; file-level run lets pytest discover added cases.
    files = list(dict.fromkeys(path for group in names for path in GROUPS[group]))
    command = [python, "-m", "pytest", "-q", *files]
    # Default is forcibly offline: credentials never need to reach a suite
    # whose purpose is deterministic regression testing.
    offline_env = {**os.environ, "PYTHONPATH": str(ROOT)}
    for secret in ("OPENAI_API_KEY", "OPENAI_ORGANIZATION", "OPENAI_PROJECT"):
        offline_env.pop(secret, None)
    proc = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        env=offline_env,
    )
    tail = "\n".join((proc.stdout + "\n" + proc.stderr).splitlines()[-30:])
    collected = re.search(r"(\d+) passed", tail)
    # Node tests validate the actual browser client code and locally compiled
    # n8n mapping, but not a real browser/n8n webhook session.
    node_files = sorted((ROOT / "tests").glob("*.test.mjs"))
    if not node_files:
        raise ValueError("Web test files are missing")
    node = subprocess.run(
        ["node", "--test", *(str(path) for path in node_files)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        env=offline_env,
    )
    node_tail = "\n".join((node.stdout + "\n" + node.stderr).splitlines()[-18:])
    match = re.search(r"(?m)^# pass (\d+)$", node_tail)
    failed = re.search(r"(?m)^# fail (\d+)$", node_tail)
    node_ok = (
        node.returncode == 0 and match is not None and failed is not None and failed.group(1) == "0"
    )
    report = {
        "schema": "odyssey-cross-surface-gate-v1",
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "status": "PASS" if proc.returncode == 0 and collected and node_ok else "BLOCKED",
        "groups": names,
        "test_files": files,
        "passed": int(collected.group(1)) if collected else 0,
        "pytest_exit": proc.returncode,
        "node_exit": node.returncode,
        "node_passed": int(match.group(1)) if match else 0,
        "node_test_files": len(node_files),
        "node_output_tail": node_tail,
        "levels_proven": ["deterministic_core", "isolated_runtime", "frozen_provider_replay"],
        "real_full_product_e2e": False,
        "provider_credentials_withheld": True,
        "pending_live_gates": PENDING_LIVE_GATES,
        "output_tail": tail,
    }
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(
        f"CROSS_SURFACE_GATE {report['status']} {report['passed']} tests, "
        f"{len(files)} files, {len(names)} groups. "
        f"pytest_exit={proc.returncode}, node={report['node_passed']} "
        f"node_exit={node.returncode}",
        flush=True,
    )
    print(tail, flush=True)
    print(node_tail, flush=True)
    return 0 if report["status"] == "PASS" else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--group", action="append", choices=tuple(GROUPS))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args()
    validate_selection()
    if args.list:
        print(
            json.dumps(
                {"groups": GROUPS, "pending_live_gates": PENDING_LIVE_GATES},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    return run(names=args.group or list(GROUPS), output=args.output, python=args.python)


if __name__ == "__main__":
    raise SystemExit(main())
