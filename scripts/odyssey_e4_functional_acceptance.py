"""Bounded E4 functional acceptance, replacing repetitive four-agent signoff.

Runs existing physical/adversarial regression suites and verifies a pinned,
post-commit real GPT+n8n+Chromium receipt. This is NOT a p95 certificate, a
DEV deployment, or permission to mutate PROD/personal data.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RECEIPT = ROOT / "docs/architecture/e4-v14-postcommit-browser-receipt-20261021.json"
SOURCE_PATHS = (
    "odyssey_core",
    "odyssey_apps",
    "odyssey_runtime",
    "scripts/odyssey_e4_live_browser.cjs",
    "scripts/odyssey_e4_live_browser_n8n.py",
)
SUITES = (
    "tests/core/test_p4_source_cohort_coverage.py",
    "tests/core/test_p4_dependent_group_graph.py",
    "tests/core/test_p4_multi_reference_set_guard.py",
    "tests/core/test_p4_finite_plural_reference_forms.py",
    "tests/runtime/test_p4_verified_plural_source_path.py",
    "tests/runtime/test_p4_plural_person_full_vertical.py",
    "tests/runtime/test_p4_composition_plural_postwrite_loss.py",
    "tests/runtime/test_p4_e4_campaign_oracle.py",
    "tests/runtime/test_p4_aliased_prior_person.py",
    "tests/runtime/test_p4_independent_mixed_scopes.py",
)


class AcceptanceError(ValueError):
    """Required functional proof is absent or incorrect."""


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise AcceptanceError(reason)


def validate_live_receipt(data: dict) -> dict:
    """Validate actual returned values, not fixture-derived counts."""
    expected = data.get("expected_people")
    require(expected == ["Ana María", "Luis"], "Missing exact two-person compound-name trial")
    require(data.get("physical_result", {}).get("gpt") == "real", "Not a real GPT trial")
    physical = data["physical_result"]
    browser = data.get("browser", {})
    notes = browser.get("notes", {})
    observations = notes.get("searchObservations", [])
    require(physical.get("passed") is True and browser.get("pass") is True, "E2E not PASS")
    require(
        physical.get("physical_persons") == len(expected)
        and physical.get("physical_tasks") == 1
        and physical.get("person_task_link") is True
        and notes.get("verifiedPersonBacklinks") == len(expected),
        "Actual persisted Persons, Task or backlinks mismatch",
    )
    require(
        len(observations) == len(expected) + 1
        and sorted(
            (o.get("kind"), o.get("query")) for o in observations if o.get("kind") == "person"
        )
        == [("person", "Ana María"), ("person", "Luis")]
        and len([o for o in observations if o.get("kind") == "task"]) == 1
        and all(o.get("apiResponse") is True and o.get("matchRows") == 1 for o in observations),
        "Search may have accepted stale UI rows or unverified HTTP data",
    )
    require(
        physical.get("markdown_e3_replay_unchanged") is True
        and browser.get("progressTrace", {}).get("advanced") is True
        and browser.get("progressTrace", {}).get("monotonic") is True
        and browser.get("jsErrorsCount") == 0,
        "Replay, progress, or browser error contract failed",
    )
    require(
        physical.get("dev_prod_untouched") is True
        and physical.get("cloudflare_access_tested") is False
        and browser.get("recordedFixture") is False,
        "E2E scope or provenance does not match isolated GPT acceptance",
    )
    return {
        "people": expected,
        "physical_person_count": physical["physical_persons"],
        "physical_task_count": physical["physical_tasks"],
        "http_searches_verified": len(observations),
        "backlinks_verified": notes["verifiedPersonBacklinks"],
        "replay_identical": True,
        "click_to_response_seconds": browser.get("userRequestSeconds"),
        "whole_harness_seconds": physical.get("seconds"),
    }


def validate_provenance(receipt_path: Path = RECEIPT) -> dict:
    data = json.loads(receipt_path.read_text(encoding="utf8"))
    trace_name = data.get("committed_full_log")
    require(
        isinstance(trace_name, str) and trace_name.startswith("docs/architecture/"),
        "Untrusted trace path",
    )
    trace = (ROOT / trace_name).resolve()
    require(trace.is_relative_to((ROOT / "docs/architecture").resolve()), "Trace path escapes docs")
    require(trace.is_file(), "Trace absent from repository")
    require(
        hashlib.sha256(trace.read_bytes()).hexdigest() == data.get("full_log_sha256"),
        "E2E SHA-256 changed",
    )
    commit = data.get("source_commit")
    require(
        isinstance(commit, str) and re.fullmatch("[0-9a-f]{40}", commit) is not None,
        "Missing source SHA",
    )
    tracked_diff = subprocess.run(
        ["git", "diff", "--name-only", commit, "HEAD", "--", *SOURCE_PATHS],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    require(not tracked_diff.stdout.strip(), "Runtime changed after the proven live E2E")
    return validate_live_receipt(data)


def accept() -> dict:
    proof = validate_provenance()
    check = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", *SUITES],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    require(
        check.returncode == 0,
        "Focused test suite failed: " + check.stdout[-2000:] + check.stderr[-500:],
    )
    found = re.search(r"(\d+) passed", check.stdout)
    require(found is not None, "Cannot confirm pytest pass total")
    return {
        "status": "FUNCTIONAL_ACCEPTANCE_PASS",
        "validated_source_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "postcommit_real_gpt_n8n_browser": proof,
        "focused_pytest_passed": int(found.group(1)),
        "adversarial_test_files": list(SUITES),
        "limits": [
            "No four-agent audit required under revised E4 acceptance decision",
            "Not a statistically established p95 or capacity/parallelism guarantee",
            "DEV not activated by this command; PROD and personal vault untouched",
            "Observed live positive plus deterministic negative regression matrix; not zero-risk",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    opts = parser.parse_args()
    try:
        status = accept()
    except (AcceptanceError, OSError, ValueError, subprocess.CalledProcessError) as error:
        print("E4_FUNCTIONAL_ACCEPTANCE_FAIL:", str(error))
        return 2
    if opts.json:
        print(json.dumps(status, indent=2, ensure_ascii=False))
    else:
        print(
            f"E4 FUNCTIONAL ACCEPTANCE PASS: {status['focused_pytest_passed']} focused tests, "
            "real GPT+n8n+browser readback and unchanged replay"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
