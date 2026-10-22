"""Read-only and conservative operator status for a non-programmer Odyssey owner.

Reads current Git/installed DEV and machine-checked contract inventory rather
than remembering a previous chat. Reports offline evidence at its actual level
and NEVER authorizes deployment without a real authenticated product receipt.

Example: python scripts/odyssey_operator_status.py --json
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.odyssey_acceptance_contracts import inspect_contracts  # noqa: E402

DEV = ROOT.parent / "odyssey-dev"
ROADMAP = ROOT / "docs/architecture/functional-roadmap.md"
HEADER = "## Current —"


def _git(path: Path, *args: str) -> str | None:
    if not path.is_dir():
        return None
    outcome = subprocess.run(
        ["git", "-C", str(path), *args],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    return outcome.stdout.strip() if outcome.returncode == 0 else None


def operator_status(root: Path = ROOT, dev: Path = DEV) -> dict:
    """Make the deployed-vs-tested distinction unambiguous, with no secrets."""
    roadmap = (root / "docs/architecture/functional-roadmap.md").read_text()
    start = roadmap.find(HEADER)
    if start < 0:
        raise ValueError("Current canonical roadmap entry is missing")
    end = roadmap.find("\n## ", start + len(HEADER))
    current = roadmap[start : end if end >= 0 else len(roadmap)]
    first = next(
        (line.strip() for line in current.splitlines() if line.startswith("**Latest verified")),
        None,
    )
    if not first:
        raise ValueError("Current canonical roadmap checkpoint is missing")
    contracts = inspect_contracts(root=root)
    ledger = json.loads((root / "docs/architecture/odyssey-acceptance-contracts.json").read_text())
    blocked_ids = set(contracts["blocked_product_contracts"])
    unmet = [
        {
            "id": row["id"],
            "invariant": row["invariant"],
            "declared_evidence_ceiling": row["max_evidence_level"],
        }
        for row in ledger["contracts"]
        if row["id"] in blocked_ids
    ]
    if len(unmet) != len(blocked_ids):
        raise ValueError("Active acceptance ledger and test inventory disagree")
    branch = _git(root, "branch", "--show-current")
    head = _git(root, "rev-parse", "--short", "HEAD")
    dirty = _git(root, "status", "--porcelain")
    installed_dev = _git(dev, "rev-parse", "--short", "HEAD")
    if branch is None or head is None or dirty is None:
        raise ValueError("Current feature Git state cannot be verified")
    if installed_dev is None:
        raise ValueError("Installed DEV version cannot be independently checked")
    return {
        "status_schema": "odyssey-operator-status-v1",
        "feature_branch": branch,
        "feature_commit": head,
        "feature_tree_clean": not bool(dirty),
        "installed_dev_commit": installed_dev,
        "branch_matches_installed_dev": head == installed_dev,
        "roadmap_checkpoint": first.replace("**", ""),
        "registered_acceptance_invariants": contracts["contract_count"],
        "acceptance_test_anchors": contracts["existing_offline_test_anchors"],
        "verified_browser_n8n": False,
        "p4_dev_ready": False,
        "prod_change_authorized": False,
        "offline_gate_replay_authority": False,
        "acceptance_scope": contracts["scope"],
        "next_step_source": "docs/architecture/functional-roadmap.md",
        # Read the actual acceptance inventory, never an agent-maintained
        # list of hardcoded blockers that can silently become stale.
        "pending_acceptance_count": len(unmet),
        "pending_acceptance": unmet,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        result = operator_status()
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        print("ODYSSEY_STATUS_UNAVAILABLE:", type(error).__name__)
        return 1
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print("Odyssey — estado de Git/DEV y contratos de aceptación (solo lectura)")
        print(
            "El ledger indica garantías pendientes, no invalida automáticamente el DEV ya desplegado."
        )
        print(f"Rama de trabajo: {result['feature_branch']} @ {result['feature_commit']}")
        print(f"DEV instalado: {result['installed_dev_commit']} (checkout comprobado)")
        print(
            f"Árbol de trabajo: {'limpio' if result['feature_tree_clean'] else 'CAMBIOS SIN COMMIT'}"
        )
        print(f"Contratos registrados: {result['registered_acceptance_invariants']} ")
        print("Contratos pendientes de aceptación final de producto:")
        print("(Algunos ya funcionan en pruebas aisladas; falta verificar el recorrido completo.)")
        for item in result["pending_acceptance"][:6]:
            print(f"  - {item['id']}: {item['invariant']}")
        remaining = result["pending_acceptance_count"] - 6
        if remaining > 0:
            print(f"  … y {remaining} contratos de aceptación más")
        print(f"Fuente de próxima acción: {result['next_step_source']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
