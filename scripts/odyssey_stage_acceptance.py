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
            or not isinstance(row.get("expected_units"), list)
            or not row["expected_units"]
            or any(
                not isinstance(unit, dict)
                or unit.get("state") not in {"candidate", "ambiguous_identity"}
                or not isinstance(unit.get("source_anchors"), list)
                or not unit["source_anchors"]
                or any(
                    not isinstance(anchor, str) or anchor not in row["source"]
                    for anchor in unit["source_anchors"]
                )
                for unit in row["expected_units"]
            )
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
        if receipt["provider_calls"] < sum(
            row["provider_calls_observed"] for row in receipt["cases"]
        ):
            raise StageAcceptanceError("Aggregate provider-call proof does not cover each source")
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
            or type(row.get("provider_calls_observed")) is not int
            or row["provider_calls_observed"] < 1
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
        # Bind each semantic claim to an independently inspectable final
        # canonical/pending readback. Multiple semantic units MAY share one
        # physical note, and one user meaning MAY involve several notes: no
        # equality is imposed on Router partitions, writer count or prose.
        _verify_final_input_output(row, digest, outcome, root)
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


def _verify_final_input_output(row: dict, digest: str, outcome: str, root: Path) -> None:
    """Require actual end-state evidence, rather than intermediate model shapes.

    A reviewer still MUST inspect the authenticated browser and genuine model
    provenance; a self-authored artifact alone cannot demonstrate semantics.
    """
    path = row.get("final_output_artifact")
    checksum = row.get("final_output_artifact_sha256")
    if (
        not isinstance(path, str)
        or not path.startswith("docs/architecture/e2e-receipts/")
        or not isinstance(checksum, str)
        or re.fullmatch(r"[0-9a-f]{64}", checksum) is None
    ):
        raise StageAcceptanceError("Missing final input-output proof")
    artifact = _json(root, path)
    if hashlib.sha256((root / path).read_bytes()).hexdigest() != checksum:
        raise StageAcceptanceError("Altered final output readback")
    review = artifact.get("semantic_review")
    ui = artifact.get("ui_after_reload")
    notes = artifact.get("canonical_notes")
    pendings = artifact.get("canonical_pending")
    sha256 = r"[0-9a-f]{64}"
    if (
        artifact.get("schema") != "odyssey-final-input-output-v1"
        or artifact.get("source_sha256") != digest
        or not isinstance(artifact.get("before_vault_sha256"), str)
        or re.fullmatch(sha256, artifact["before_vault_sha256"]) is None
        or not isinstance(artifact.get("after_vault_sha256"), str)
        or re.fullmatch(sha256, artifact["after_vault_sha256"]) is None
        or not isinstance(notes, list)
        or not isinstance(pendings, list)
        or not notes
        and not pendings
        or not isinstance(ui, dict)
        or ui.get("notes_and_calendar_loaded") is not True
        or not isinstance(ui.get("assistant_reply"), str)
        or not ui["assistant_reply"].strip()
        or not isinstance(review, dict)
        or review.get("judgement")
        != ("safe_partial_pending" if outcome == "safely_ambiguous" else "semantically_sufficient")
        or review.get("all_source_meanings_accounted_for") is not True
        or review.get("no_invented_facts_or_actions") is not True
        or not isinstance(review.get("explanation"), str)
        or len(review["explanation"].strip()) < 20
        or type(review.get("alternate_safe_representation")) is not bool
        or review["alternate_safe_representation"] is True
        and len(review["explanation"].strip()) < 35
    ):
        raise StageAcceptanceError("Final output is not independently reviewable")
    readback_proofs = set()
    note_ids = set()
    for note in notes:
        if (
            not isinstance(note, dict)
            or not isinstance(note.get("note_id"), str)
            or not note["note_id"].strip()
            or note["note_id"] in note_ids
            or not isinstance(note.get("note_path"), str)
            or not note["note_path"].strip()
            or not isinstance(note.get("markdown_sha256"), str)
            or re.fullmatch(sha256, note["markdown_sha256"]) is None
            or not isinstance(note.get("content_excerpt"), str)
            or not note["content_excerpt"].strip()
            or not isinstance(note.get("markdown_utf8"), str)
            or not note["markdown_utf8"].strip()
            or len(note["markdown_utf8"]) > 20000
            or note["content_excerpt"] not in note["markdown_utf8"]
            or hashlib.sha256(note["markdown_utf8"].encode("utf-8")).hexdigest()
            != note["markdown_sha256"]
        ):
            raise StageAcceptanceError("Canonical note readback is invalid")
        note_ids.add(note["note_id"])
        readback_proofs.add(note["markdown_sha256"])
    for pending in pendings:
        if (
            not isinstance(pending, dict)
            or not isinstance(pending.get("reason"), str)
            or not pending["reason"].strip()
            or not isinstance(pending.get("pending_sha256"), str)
            or re.fullmatch(sha256, pending["pending_sha256"]) is None
        ):
            raise StageAcceptanceError("Safe pending proof missing")
        readback_proofs.add(pending["pending_sha256"])
    if (
        outcome == "safely_ambiguous"
        and not pendings
        or not isinstance(ui.get("opened_note_ids"), list)
        or any(not isinstance(n, str) or n not in note_ids for n in ui["opened_note_ids"])
        or not all(
            unit.get("proof_sha256") in readback_proofs for unit in row["unit_verifications"]
        )
    ):
        raise StageAcceptanceError("Semantic units lack final canonical/pending readback")


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
