"""Read-only audit of known case-specific validators and their actual product callers.

Lists direct imports for five identified legacy adapters. This is a bounded
inventory, NOT a claim to count every semantic validation rule in Odyssey.
Fails if a new product caller silently extends legacy syntax-specific logic.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ("odyssey_core", "odyssey_runtime", "odyssey_apps")
LEGACY = {
    "candidate_sequential_contacts": {
        "path": "odyssey_core/candidate_sequential_contacts.py",
        "allowed_product_consumers": [
            "odyssey_core/candidate_coverage.py",
            "odyssey_core/candidate_attribution.py",
        ],
        "status": "legacy_coverage_and_attribution_active_only",
    },
    "candidate_multi_participant": {
        "path": "odyssey_core/candidate_multi_participant.py",
        "allowed_product_consumers": [
            "odyssey_core/candidate_attribution.py",
            "odyssey_core/candidate_coverage.py",
        ],
        "status": "two_person_legacy_candidate_validation_active",
    },
    "candidate_scoped_handoff": {
        "path": "odyssey_core/candidate_scoped_handoff.py",
        "allowed_product_consumers": ["odyssey_core/candidate_scoped_planning.py"],
        "status": "narrow_scoped_preview_experimental_not_P4",
    },
    "candidate_continuation_guard": {
        "path": "odyssey_core/candidate_continuation_guard.py",
        "allowed_product_consumers": [],
        "status": "experimental_test_only_no_product_import",
    },
    "task_core_planner": {
        "path": "odyssey_apps/tasks/planning.py",
        "allowed_product_consumers": [
            "odyssey_apps/tasks/__init__.py",
            "odyssey_runtime/composition.py",
        ],
        "status": "legacy_tasks_adapter_active_not_P4",
    },
}


def product_python_files():
    for package in PACKAGES:
        yield from sorted((ROOT / package).rglob("*.py"))


def audit() -> dict:
    observed = {key: [] for key in LEGACY}
    for path in product_python_files():
        source = path.relative_to(ROOT).as_posix()
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                raw = node.module or ""
                modules = [raw]
                if node.level and path.parent.name == "tasks" and raw == "planning":
                    modules.append("odyssey_apps.tasks.planning")
                if node.level and path.parent.name == "odyssey_core":
                    modules.append("odyssey_core." + raw)
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
                names = []
            else:
                continue
            for key in LEGACY:
                module = LEGACY[key]["path"].removesuffix(".py").replace("/", ".")
                imports = key == "task_core_planner" and "TaskCorePlanner" in names
                if module in modules or (
                    imports
                    and any(
                        m in {"odyssey_apps.tasks", "odyssey_apps.tasks.planning", "planning"}
                        for m in modules
                    )
                ):
                    observed[key].append(source)
    result = {}
    for key, contract in LEGACY.items():
        actual = sorted(set(observed[key]) - {contract["path"]})
        expected = sorted(contract["allowed_product_consumers"])
        if actual != expected:
            raise ValueError(
                f"Legacy semantic boundary changed: {key}, actual={actual}, expected={expected}"
            )
        result[key] = {"status": contract["status"], "product_callers": actual}
    return {
        "version": 1,
        "scope": "five_identified_case_specific_adapters",
        "not_a_global_validator_count": True,
        "identified": result,
        "P4_product_caller_of_legacy_adapters": False,
    }


if __name__ == "__main__":
    print(json.dumps(audit(), indent=2, ensure_ascii=False))
