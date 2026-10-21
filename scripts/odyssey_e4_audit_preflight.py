"""Fail-fast E4 audit readiness gate; never invokes a model or changes a vault.

Prevents repeating four expensive independent reviews before their declared
prerequisites exist. It does NOT certify implementation or production.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs/architecture"


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def _read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _browser_evidence_ok(receipt: dict) -> bool:
    log_path = receipt.get("committed_full_log")
    if not isinstance(log_path, str) or not log_path.startswith("docs/architecture/"):
        return False
    path = (ROOT / log_path).resolve()
    if not path.is_relative_to(DOCS.resolve()) or not path.is_file():
        return False
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    pinned = receipt.get("source_commit")
    if not isinstance(pinned, str) or not pinned:
        return False
    try:
        # Documentation-only receipt commits do not change the runtime under test.
        changed_code = _git(
            "diff",
            "--name-only",
            pinned,
            "HEAD",
            "--",
            "odyssey_core",
            "odyssey_apps",
            "odyssey_runtime",
            "scripts/odyssey_e4_live_browser_n8n.py",
            "scripts/odyssey_e4_live_browser.cjs",
        )
    except subprocess.CalledProcessError:
        return False
    return (
        not changed_code
        and receipt.get("full_log_sha256") == digest
        and receipt.get("physical_result", {}).get("passed") is True
        and receipt.get("physical_result", {}).get("gpt") == "real"
        and receipt.get("browser", {}).get("pass") is True
    )


def _qualified_samples(rows: object, *, browser: bool) -> list[float]:
    if not isinstance(rows, list):
        return []
    seen: set[str] = set()
    seen_cases: set[str] = set()
    durations: list[float] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        id_ = row.get("run_id")
        case = row.get("case")
        duration = row.get("seconds")
        if (
            not isinstance(id_, str)
            or not id_
            or id_ in seen
            or not isinstance(case, str)
            or not case
            or case in seen_cases
            or row.get("pass") is not True
            or row.get("status") != "completed"
            or not isinstance(duration, (float, int))
            or isinstance(duration, bool)
            or duration <= 0
            or (
                browser
                and (
                    not row.get("physical_browser_n8n_gpt")
                    or row.get("metric") != "send_to_first_response"
                )
            )
        ):
            continue
        seen.add(id_)
        seen_cases.add(case)
        durations.append(float(duration))
    return durations


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = (len(ordered) - 1) * percentile
    lo, hi = int(index), min(int(index) + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (index - lo)


def evaluate(*, require_clean: bool = True) -> dict:
    issues: list[str] = []
    if require_clean and _git("status", "--porcelain"):
        issues.append("Uncommitted E4 source: freeze source and receipts first")
    receipt = _read_json(DOCS / "e4-v14-postcommit-browser-receipt-20261021.json")
    if not _browser_evidence_ok(receipt):
        issues.append("Missing post-freeze v14 live GPT+n8n+browser trace with matching SHA-256")
    fast = _read_json(DOCS / "e4-v10-fastembed-isolated-pi-receipt-20261021.json")
    if not (
        fast.get("synthetic_only") is True
        and fast.get("index_250_synthetic_notes", {}).get("synthetic_notes") == 250
        and len(fast.get("offline_model_reloads", [])) >= 3
    ):
        issues.append("Missing isolated actual FastEmbed cold/warm/index receipt")
    samples = _read_json(DOCS / "e4-v10-performance-samples-20261021.json")
    counts = {}
    for key, median_limit in (("direct_positive", 60.0), ("browser_positive", 90.0)):
        rows = _qualified_samples(samples.get(key), browser=key == "browser_positive")
        median, p95 = _percentile(rows, 0.5), _percentile(rows, 0.95)
        # Three heterogeneous real-model runs permit a bounded review, NOT a
        # statistically certified product p95. Preserve that distinction.
        counts[key] = {
            "qualified": len(rows),
            "observed_median_s": median,
            "p95_s": p95 if len(rows) >= 20 else None,
            "sample_max_s": max(rows, default=None),
        }
        if len(rows) < 3:
            issues.append(
                f"{key}: {len(rows)}/3 distinct positive runs for bounded review (20 for future SLO study)"
            )
        elif median > median_limit or max(rows) > 120:
            issues.append(f"{key}: observed median or an individual run exceeds provisional budget")
    host = samples.get("host_resources_under_full_load")
    if not (
        isinstance(host, dict)
        and host.get("complete_run") is True
        and isinstance(host.get("samples"), int)
        and host["samples"] >= 30
        and all(
            isinstance(host.get(k), (float, int))
            for k in (
                "min_mem_available_kib",
                "min_swap_free_kib",
                "max_cpu_util_pct",
                "max_temperature_millideg",
                "peak_python_rss_kib",
                "peak_chrome_sum_rss_kib",
            )
        )
    ):
        issues.append("Missing full-duration Pi CPU/RAM/swap/thermal and process RSS measurements")
    return {
        "ready_to_spend_four_auditors": not issues,
        "source_head": _git("rev-parse", "HEAD"),
        "qualified_performance_samples": counts,
        "blocking_prerequisites": issues,
        "meaning": "Readiness to request independent review, never a PASS verdict or deploy approval",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    opts = parser.parse_args()
    report = evaluate()
    if opts.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print("E4 audit readiness:", "READY" if report["ready_to_spend_four_auditors"] else "HOLD")
        for reason in report["blocking_prerequisites"]:
            print(" -", reason)
    return 0 if report["ready_to_spend_four_auditors"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
