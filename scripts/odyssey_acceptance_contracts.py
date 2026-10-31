"""Machine-checked acceptance evidence, never self-issued authorization to deploy.

The single status owner remains docs/architecture/functional-roadmap.md.
This ledger is an index of contractual user invariants, their current test
anchors, and known acceptance gaps. It must NOT convert a passing offline
suite into a real-browser/n8n/LLM/Markdown product acceptance declaration.
"""

from __future__ import annotations

import argparse
import ast
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

if __package__:
    from .odyssey_stage_acceptance import inspect_stage_acceptance
else:
    from odyssey_stage_acceptance import inspect_stage_acceptance

# Support both `python scripts/file.py` in CI and package import in pytest.
if __package__:
    from .odyssey_cross_surface_gate import GROUPS
else:
    from odyssey_cross_surface_gate import GROUPS

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs/architecture/odyssey-acceptance-contracts.json"
STAGES = frozenset({"E2", "E3", "E4", "E5", "E6", "P4"})
LEVELS = frozenset({"none", "deterministic", "isolated_http", "real_provider_isolated"})
REQUIRED = frozenset(
    {
        "E2-SELF-SPEAKER",
        "E2-CANONICAL-GROUP",
        "E2-TEMPORAL-OWNERSHIP",
        "E3-CANONICAL-WRITER",
        "E3-CLAIM-CRASH",
        "E3-CHAT-PERSIST",
        "P4-TASK-WORKSESSION",
        "P4-MIXED-CORE-TASK",
        "E4-LEGACY-QUARANTINE",
        "P4-PERFORMANCE",
        "P4-REAL-BROWSER",
        "P4-E3-RECOVERY",
        "P4-SESSION-MIXED",
        "E5-EVENTS",
        "E6-INCREMENTAL-ARCH",
    }
)
FIELDS = frozenset(
    {
        "id",
        "phase",
        "invariant",
        "max_evidence_level",
        "offline_test_selectors",
        "blocks_p4_dev",
        "verified_real_browser_n8n",
    }
)


class AcceptanceContractError(ValueError):
    """Contractual proof or mandatory acceptance coverage went missing."""


@lru_cache(maxsize=256)
def _test_functions(path: Path) -> frozenset[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return frozenset(
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test_")
    )


def inspect_contracts(
    *,
    manifest: dict[str, Any] | None = None,
    root: Path = ROOT,
    groups: dict[str, tuple[str, ...]] | None = None,
) -> dict[str, Any]:
    """Read-only audit of links, integrity, blocking flags and evidence levels.

    Only AST *presence* is verified here. Actual test results, fresh model
    variability and remote authenticated E2E belong to independent gates.
    """
    if manifest is None:
        manifest = json.loads(
            (root / "docs/architecture/odyssey-acceptance-contracts.json").read_text()
        )
    if (
        not isinstance(manifest, dict)
        or manifest.get("schema") != "odyssey-user-invariant-ledger-v1"
    ):
        raise AcceptanceContractError("Unknown immutable acceptance schema")
    if manifest.get("authority") != "functional-roadmap.md":
        raise AcceptanceContractError("Functional Roadmap must remain sole owner of status")
    if manifest.get("required_product_gate") != "real_authenticated_browser_n8n_gpt_markdown_ui":
        raise AcceptanceContractError("Product gate cannot be weakened by a local test")
    contracts = manifest.get("contracts")
    if not isinstance(contracts, list) or not contracts or len(contracts) > 100:
        raise AcceptanceContractError("Invalid bounded contract inventory")
    listed = {entry.get("id") for entry in contracts if isinstance(entry, dict)}
    if len(listed) != len(contracts) or not REQUIRED.issubset(listed):
        raise AcceptanceContractError("Required user agreement missing or duplicate")
    listed_tests = {s for selections in (groups or GROUPS).values() for s in selections}
    evidence = 0
    blocked = []
    for contract in contracts:
        if not isinstance(contract, dict) or set(contract) != FIELDS:
            raise AcceptanceContractError("Incomplete invariant ledger entry")
        code = contract["id"]
        if (
            not isinstance(code, str)
            or not code
            or len(code) > 72
            or contract["phase"] not in STAGES
            or not isinstance(contract["invariant"], str)
            or not 24 <= len(contract["invariant"]) <= 320
            or contract["max_evidence_level"] not in LEVELS
            or type(contract["blocks_p4_dev"]) is not bool
            or type(contract["verified_real_browser_n8n"]) is not bool
        ):
            raise AcceptanceContractError("Invalid immutable invariant fields")
        if (contract["phase"] in {"E2", "E3", "E4", "P4"}) != contract["blocks_p4_dev"]:
            raise AcceptanceContractError(
                "An active E2/E3/E4/P4 invariant cannot waive its P4 gate"
            )
        if contract["verified_real_browser_n8n"]:
            # A separate validated replay+visual+authenticated receipt contract
            # must be introduced before promotion, not merely toggle a boolean.
            raise AcceptanceContractError("Cannot self-attest remote browser/n8n acceptance")
        selectors = contract["offline_test_selectors"]
        if (
            not isinstance(selectors, list)
            or len(selectors) > 6
            or len(set(selectors)) != len(selectors)
            or (contract["max_evidence_level"] != "none") != bool(selectors)
        ):
            raise AcceptanceContractError("Misstated offline evidence level")
        for selector in selectors:
            if not isinstance(selector, str) or selector.count("::") != 1:
                raise AcceptanceContractError("Test selector is not source-anchored")
            relative, function = selector.split("::")
            if (
                relative not in listed_tests
                or not relative.startswith("tests/")
                or (root / relative).is_symlink()
                or function not in _test_functions(root / relative)
            ):
                raise AcceptanceContractError(
                    "Missing or unselected executable regression: " + selector
                )
            evidence += 1
        if contract["blocks_p4_dev"]:
            blocked.append(code)
    stage_evidence = inspect_stage_acceptance(root=root)
    return {
        "stage_acceptance": stage_evidence,
        "schema": "odyssey-acceptance-integrity-v1",
        "contract_count": len(contracts),
        "existing_offline_test_anchors": evidence,
        "missing_or_invalid_contracts": 0,
        "real_browser_n8n_verified": False,
        "dev_ready": False,
        "blocked_product_contracts": blocked,
        "scope": "integrity_of_declared_requirements_only_not_test_execution",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--require-stage-accepted", choices=["R0", "R1", "R2", "R3", "R4"])
    parser.add_argument("--require-review-stage-accepted", action="store_true")
    args = parser.parse_args()
    try:
        result = inspect_contracts()
        required_stage = (
            result["stage_acceptance"]["review_stage"]
            if args.require_review_stage_accepted
            else args.require_stage_accepted
        )
        if required_stage and required_stage not in result["stage_acceptance"]["accepted_stages"]:
            raise AcceptanceContractError(
                "STAGE_E2E_NOT_VERIFIED: live browser/model/27 cases/4 audits absent"
            )
    except (AcceptanceContractError, ValueError, SyntaxError, OSError) as error:
        print("ACCEPTANCE_LEDGER_INTEGRITY_BLOCKED:", error)
        return 1
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(
            f"ACCEPTANCE_LEDGER_INTEGRITY_PASS: {result['contract_count']} invariants; "
            f"{result['existing_offline_test_anchors']} required offline anchors; "
            "P4 DEV UNAUTHORIZED (real product gate incomplete); "
            f"STAGE {result['stage_acceptance']['stage'].upper()} "
            f"({result['stage_acceptance']['cases']} cases)"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
