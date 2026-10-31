"""Fail-closed stage-completion check; offline CI never certifies a live E2E by itself.

The product acceptance boundary reads evidence captured by an *independent actual*
user-journey runner. Source files cannot establish that a provider/browser was
actually used: this guard detects missing, mismatched or incomplete receipts;
reviewers must still verify the provenance of the recorded run and safe actor.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any

if __package__:
    from .odyssey_r0_browser_campaign import (
        CampaignError,
        valid_fixture_setup,
        verify_source_anchors,
    )
else:
    from odyssey_r0_browser_campaign import (
        CampaignError,
        valid_fixture_setup,
        verify_source_anchors,
    )

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs/architecture/odyssey-phase-acceptance.json"
ROLES = frozenset({"generality", "quality", "testing", "performance"})
SHA = re.compile(r"[0-9a-f]{40}\Z")


class StageAcceptanceError(ValueError):
    """The declared phase is incomplete, forged or lacks required live evidence."""


def _json(root: Path, relative: str) -> dict[str, Any]:
    raw = root / relative
    path = raw.resolve()
    if not path.is_relative_to(root.resolve()) or raw.is_symlink() or not path.is_file():
        raise StageAcceptanceError("Missing or unsafe stage evidence: " + relative)
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise StageAcceptanceError("Stage evidence must be an object")
    return loaded


def _sha(value: object) -> bool:
    return isinstance(value, str) and SHA.fullmatch(value) is not None


def inspect_stage_acceptance(*, root: Path = ROOT, manifest: dict | None = None) -> dict:
    """Validate the immutable 27-source contract and fail on unsupported closure."""
    stage = (
        manifest
        if manifest is not None
        else _json(root, "docs/architecture/odyssey-phase-acceptance.json")
    )
    if (
        set(stage)
        != {
            "schema",
            "phase",
            "stages",
            "review_stage",
            "corpus_manifest",
            "original_case_design",
            "additional_regression_source",
            "evidence_rule",
        }
        or stage["schema"] != "odyssey-phase-acceptance-v1"
        or stage["phase"] != "thin-orchestrator-R0-R4"
        or stage["review_stage"] not in {"R0", "R1", "R2", "R3", "R4"}
        or stage["corpus_manifest"] != "tests/fixtures/full_message_corpus_v1/manifest.json"
        or stage["original_case_design"]
        != "benchmarks/application_router/fact_units_v2.design.json"
        or stage["additional_regression_source"]
        != "tests/fixtures/odyssey_additional_regressions_v1.json"
        or not isinstance(stage["evidence_rule"], str)
        or not all(
            marker in stage["evidence_rule"]
            for marker in ("real-model", "browser/n8n", "four independent", "F01-F27")
        )
    ):
        raise StageAcceptanceError("Stage contract was weakened or changed unexpectedly")
    stages = stage["stages"]
    if (
        not isinstance(stages, list)
        or len(stages) != 5
        or any(
            not isinstance(item, dict)
            or set(item) != {"id", "status", "acceptance_receipt"}
            or item["id"] != f"R{i}"
            or item["status"] not in {"not_started", "in_progress", "accepted"}
            for i, item in enumerate(stages)
        )
    ):
        raise StageAcceptanceError("All five stages must retain their acceptance gates")
    statuses = [item["status"] for item in stages]
    if stages[int(stage["review_stage"][1])]["status"] == "not_started":
        raise StageAcceptanceError("Cannot review a stage which has not started")
    if (
        statuses != sorted(statuses, key={"accepted": 0, "in_progress": 1, "not_started": 2}.get)
        or statuses.count("in_progress") > 1
    ):
        raise StageAcceptanceError("Cannot accept or start a stage out of order")
    corpus = _json(root, stage["corpus_manifest"])
    design = _json(root, stage["original_case_design"])
    ids = tuple(f"F{i:02d}" for i in range(1, 28))
    if (
        corpus.get("version") != 1
        or corpus.get("case_design") != stage["original_case_design"]
        or corpus.get("case_ids") != list(ids)
        or design.get("version") != 2
        or not isinstance(design.get("cases"), list)
        or [item.get("id") for item in design["cases"]] != list(ids)
        or any(
            not isinstance(item.get("source"), str) or not item["source"].strip()
            for item in design["cases"]
        )
    ):
        raise StageAcceptanceError("Original 27-case source corpus is missing or changed")
    extra = _json(root, stage["additional_regression_source"])
    additional = extra.get("cases")
    if (
        extra.get("schema") != "odyssey-additional-regressions-v1"
        or not isinstance(additional, list)
        or not additional
        or [row.get("id") for row in additional if isinstance(row, dict)]
        != [f"R{i:02d}" for i in range(28, 28 + len(additional))]
        or any(
            not isinstance(row, dict)
            or not isinstance(row.get("source"), str)
            or not row["source"].strip()
            or not isinstance(row.get("expectation"), str)
            or not row["expectation"].strip()
            or not valid_fixture_setup(row.get("fixture_setup"))
            or row.get("live_acceptance") != "pending"
            for row in additional
        )
    ):
        raise StageAcceptanceError("Additional regression case catalog is missing or invalid")
    # Preserve the 27 source IDs byte-for-byte; append-only regressions may
    # grow after them. No earlier failure may disappear from phase acceptance.
    try:
        verify_source_anchors(design["cases"], additional)
    except (CampaignError, KeyError, TypeError) as error:
        raise StageAcceptanceError("The original or added regression sources changed") from error
    all_ids = (*ids, *(row["id"] for row in additional))
    full_design = {"cases": [*design["cases"], *additional]}
    accepted_stages = []
    for item in stages:
        if item["status"] != "accepted":
            if item["acceptance_receipt"] is not None:
                raise StageAcceptanceError("Unaccepted stage may not claim a live receipt")
            continue
        reference = item["acceptance_receipt"]
        if not isinstance(reference, str) or not reference.startswith(
            "docs/architecture/e2e-receipts/"
        ):
            raise StageAcceptanceError(
                "Accepted stage requires tracked independent live E2E receipt"
            )
        receipt = _json(root, reference)
        source_sha, deployed_sha = receipt.get("source_sha"), receipt.get("deployed_sha")
        if (
            receipt.get("schema") != "odyssey-stage-live-e2e-v1"
            or receipt.get("phase") != stage["phase"]
            or receipt.get("stage_id") != item["id"]
            or not _sha(source_sha)
            or deployed_sha != source_sha
            or receipt.get("provider_mode") != "fresh_real_model"
            or type(receipt.get("provider_calls")) is not int
            or receipt["provider_calls"] < 1
            or not isinstance(receipt.get("provider_model"), str)
            or not receipt["provider_model"].strip()
            or receipt.get("browser_mode") != "visible_authenticated_user_actions"
            or receipt.get("n8n_mode") != "real"
            or receipt.get("isolated_actor_vault") is not True
            or receipt.get("markdown_physical_readback") is not True
            or receipt.get("browser_notes_calendar_reload") is not True
            or receipt.get("replay_no_duplicate_write") is not True
            or receipt.get("trace_provenance_reviewed") is not True
        ):
            raise StageAcceptanceError("Live E2E receipt lacks mandatory product evidence")
        if receipt["provider_calls"] < len(all_ids):
            raise StageAcceptanceError("Fresh provider-call count cannot cover every case")
        _verify_case_rows(receipt, full_design, all_ids, root)
        _verify_auditors(receipt, source_sha, root)
        if root.resolve() == ROOT.resolve():
            code_diff = subprocess.run(
                [
                    "git",
                    "-C",
                    str(root),
                    "diff",
                    "--quiet",
                    source_sha,
                    "HEAD",
                    "--",
                    "odyssey_core",
                    "odyssey_apps",
                    "odyssey_runtime",
                    "odyssey_web",
                    "workflows",
                    "config",
                ],
                check=False,
                capture_output=True,
            )
            if code_diff.returncode != 0:
                raise StageAcceptanceError("Code changed since the pinned real browser/model test")
        accepted_stages.append(item["id"])
    current = next((item["id"] for item in stages if item["status"] == "in_progress"), None)
    return {
        "stage": current,
        "accepted_stages": accepted_stages,
        "review_stage": stage["review_stage"],
        "cases": len(all_ids),
        "accepted": len(accepted_stages) == 5,
    }


def _verify_case_rows(receipt: dict, design: dict, ids: tuple[str, ...], root: Path) -> None:
    # Requiring an auditable trace for each case prevents counting a Router-only
    # replay, a simulated UI, or one successful request as a complete 27-case run.
    rows = receipt.get("cases")
    if not isinstance(rows, list) or len(rows) != len(ids):
        raise StageAcceptanceError(
            "All 27 original plus appended cases require a fresh per-case browser trace"
        )
    expected_ambiguous = {
        case["id"]
        for case in design["cases"]
        if any(unit.get("state") == "ambiguous_identity" for unit in case.get("expected_units", []))
    }
    used_requests: set[str] = set()
    for expected, row, case in zip(ids, rows, design["cases"], strict=True):
        if not isinstance(row, dict):
            raise StageAcceptanceError("Invalid case evidence")
        digest = hashlib.sha256(case["source"].encode("utf-8")).hexdigest()
        outcome = row.get("outcome")
        request_id = row.get("request_id")
        if (
            row.get("id") != expected
            or row.get("source_sha256") != digest
            or outcome not in {"passed", "safely_ambiguous"}
            or (expected in expected_ambiguous and outcome != "safely_ambiguous")
            or (expected not in expected_ambiguous and outcome != "passed")
            or not isinstance(request_id, str)
            or len(request_id) < 8
            or request_id in used_requests
            or row.get("visible_ui_submitted") is not True
            or row.get("live_provider_observed") is not True
            or row.get("source_preserved") is not True
            or row.get("canonical_result_checked") is not True
            or row.get("ui_readback_checked") is not True
            or row.get("trace_artifact_sha256") is None
            or not isinstance(row.get("trace_artifact_sha256"), str)
            or re.fullmatch(r"[0-9a-f]{64}", row["trace_artifact_sha256"]) is None
        ):
            raise StageAcceptanceError("Incomplete or non-live case evidence: " + expected)
        # One successful Chat acknowledgement cannot certify a compound
        # source: every original source unit (or appended scenario) needs its
        # own readback-supported semantic disposition. An ambiguous reference
        # is a positive safe-pending check, NOT a failed identity guess.
        expected_units = case.get("expected_units") or [{"state": "end_to_end"}]
        observed_units = row.get("unit_verifications")
        if (
            row.get("no_unsupported_writes") is not True
            or row.get("semantic_oracle_reviewed") is not True
            or not isinstance(observed_units, list)
            or len(observed_units) != len(expected_units)
        ):
            raise StageAcceptanceError(
                "Missing full-source per-unit semantic verification: " + expected
            )
        for index, (planned, observed) in enumerate(
            zip(expected_units, observed_units, strict=True)
        ):
            state = planned.get("state")
            required_dispositions = (
                {"pending_unresolved"}
                if state == "ambiguous_identity"
                else {"persisted", "existing_proven"}
            )
            if (
                not isinstance(observed, dict)
                or observed.get("ordinal") != index
                or observed.get("expected_state") != state
                or observed.get("disposition") not in required_dispositions
                or observed.get("source_supported") is not True
                or observed.get("canonical_readback") is not True
                or not isinstance(observed.get("proof_sha256"), str)
                or re.fullmatch(r"[0-9a-f]{64}", observed["proof_sha256"]) is None
            ):
                raise StageAcceptanceError(
                    "Incomplete semantic unit or invented identity: " + expected
                )
        used_requests.add(request_id)
        trace = row.get("trace_artifact")
        if not isinstance(trace, str) or not trace.startswith("docs/architecture/e2e-receipts/"):
            raise StageAcceptanceError("Missing trace artifact: " + expected)
        raw_artifact = root / trace
        artifact = raw_artifact.resolve()
        if (
            not artifact.is_relative_to(root.resolve())
            or not artifact.is_file()
            or raw_artifact.is_symlink()
        ):
            raise StageAcceptanceError("Unsafe trace artifact: " + expected)
        if hashlib.sha256(artifact.read_bytes()).hexdigest() != row["trace_artifact_sha256"]:
            raise StageAcceptanceError("Altered browser trace: " + expected)


def _verify_auditors(receipt: dict, source_sha: str, root: Path) -> None:
    reviewers = receipt.get("reviewers")
    if (
        not isinstance(reviewers, list)
        or {item.get("role") for item in reviewers if isinstance(item, dict)} != ROLES
        or len(reviewers) != len(ROLES)
        or any(
            item.get("status") != "pass"
            or item.get("source_sha") != source_sha
            or not isinstance(item.get("receipt_path"), str)
            or not item["receipt_path"].startswith("docs/architecture/e2e-receipts/")
            or not (root / item["receipt_path"]).is_file()
            or not isinstance(item.get("receipt_sha256"), str)
            or re.fullmatch(r"[0-9a-f]{64}", item["receipt_sha256"]) is None
            or hashlib.sha256((root / item["receipt_path"]).read_bytes()).hexdigest()
            != item["receipt_sha256"]
            for item in reviewers
        )
    ):
        raise StageAcceptanceError("All four audited roles must pass on the tested SHA")
