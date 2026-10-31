"""A completed stage must prove real app E2E, not simply a green offline suite."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from scripts.odyssey_stage_acceptance import (
    ROOT,
    StageAcceptanceError,
    inspect_stage_acceptance,
)

STAGE = json.loads((ROOT / "docs/architecture/odyssey-phase-acceptance.json").read_text())


def _stage() -> dict:
    return copy.deepcopy(STAGE)


def test_r0_is_unaccepted_but_original_27_sources_remain_anchored():
    result = inspect_stage_acceptance()
    assert result == {
        "stage": "R0",
        "review_stage": "R0",
        "accepted_stages": [],
        "cases": 30,
        "accepted": False,
    }


def test_cannot_skip_stage_or_claim_unearned_acceptance():
    invalid = _stage()
    invalid["review_stage"] = "R3"
    with pytest.raises(StageAcceptanceError, match="has not started"):
        inspect_stage_acceptance(manifest=invalid)
    invalid = _stage()
    invalid["stages"][1]["status"] = "accepted"
    with pytest.raises(StageAcceptanceError, match="out of order"):
        inspect_stage_acceptance(manifest=invalid)
    invalid = _stage()
    invalid["stages"][0]["status"] = "accepted"
    with pytest.raises(StageAcceptanceError, match="requires tracked"):
        inspect_stage_acceptance(manifest=invalid)
    invalid = _stage()
    invalid["stages"][0]["acceptance_receipt"] = "docs/architecture/e2e-receipts/fictional.json"
    with pytest.raises(StageAcceptanceError, match="Unaccepted"):
        inspect_stage_acceptance(manifest=invalid)


def test_27_case_contract_cannot_be_silently_reduced(tmp_path: Path):
    design = json.loads((ROOT / STAGE["original_case_design"]).read_text())
    corpus = json.loads((ROOT / STAGE["corpus_manifest"]).read_text())
    destination = tmp_path / "benchmarks/application_router"
    destination.mkdir(parents=True)
    (destination / "fact_units_v2.design.json").write_text(json.dumps(design))
    target = tmp_path / "tests/fixtures/full_message_corpus_v1"
    target.mkdir(parents=True)
    corpus["case_ids"].pop()
    (target / "manifest.json").write_text(json.dumps(corpus))
    with pytest.raises(StageAcceptanceError, match="27-case"):
        inspect_stage_acceptance(root=tmp_path, manifest=_stage())


def _evidence(tmp_path: Path) -> tuple[dict, dict]:
    """Test the validator with synthetic records; NEVER call this a live run."""
    design = json.loads((ROOT / STAGE["original_case_design"]).read_text())
    corpus = json.loads((ROOT / STAGE["corpus_manifest"]).read_text())
    extra = json.loads((ROOT / STAGE["additional_regression_source"]).read_text())
    for relative, document in (
        (STAGE["original_case_design"], design),
        (STAGE["corpus_manifest"], corpus),
        (STAGE["additional_regression_source"], extra),
    ):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(document))
    evidence = tmp_path / "docs/architecture/e2e-receipts"
    evidence.mkdir(parents=True)
    sha = "e" * 40
    rows = []
    for case in [*design["cases"], *extra["cases"]]:
        ident = case["id"]
        trace = evidence / (ident + ".json")
        trace.write_text(json.dumps({"synthetic_validator_fixture": ident}))
        rows.append(
            {
                "id": ident,
                "source_sha256": hashlib.sha256(case["source"].encode()).hexdigest(),
                "outcome": "safely_ambiguous" if ident in {"F14", "F27"} else "passed",
                "request_id": f"test-request-{ident}",
                "visible_ui_submitted": True,
                "live_provider_observed": True,
                "source_preserved": True,
                "canonical_result_checked": True,
                "ui_readback_checked": True,
                "no_unsupported_writes": True,
                "semantic_oracle_reviewed": True,
                "unit_verifications": [
                    {
                        "ordinal": index,
                        "expected_state": unit.get("state", "end_to_end"),
                        "disposition": (
                            "pending_unresolved"
                            if unit.get("state") == "ambiguous_identity"
                            else "persisted"
                        ),
                        "source_supported": True,
                        "canonical_readback": True,
                        "proof_sha256": hashlib.sha256(
                            f"synthetic-only-{ident}-{index}".encode()
                        ).hexdigest(),
                    }
                    for index, unit in enumerate(
                        case.get("expected_units") or [{"state": "end_to_end"}]
                    )
                ],
                "trace_artifact": "docs/architecture/e2e-receipts/" + ident + ".json",
                "trace_artifact_sha256": hashlib.sha256(trace.read_bytes()).hexdigest(),
            }
        )
    auditors = []
    for role in sorted(["generality", "quality", "testing", "performance"]):
        receipt = evidence / (role + ".md")
        receipt.write_text("synthetic validation sample: " + role)
        auditors.append(
            {
                "role": role,
                "status": "pass",
                "source_sha": sha,
                "receipt_path": "docs/architecture/e2e-receipts/" + role + ".md",
                "receipt_sha256": hashlib.sha256(receipt.read_bytes()).hexdigest(),
            }
        )
    payload = {
        "schema": "odyssey-stage-live-e2e-v1",
        "phase": STAGE["phase"],
        "stage_id": "R0",
        "source_sha": sha,
        "deployed_sha": sha,
        "provider_mode": "fresh_real_model",
        "provider_calls": 30,
        "provider_model": "test-model",
        "browser_mode": "visible_authenticated_user_actions",
        "n8n_mode": "real",
        "isolated_actor_vault": True,
        "markdown_physical_readback": True,
        "browser_notes_calendar_reload": True,
        "replay_no_duplicate_write": True,
        "trace_provenance_reviewed": True,
        "cases": rows,
        "reviewers": auditors,
    }
    (evidence / "R0.json").write_text(json.dumps(payload))
    claimed = _stage()
    claimed["stages"][0] = {
        "id": "R0",
        "status": "accepted",
        "acceptance_receipt": "docs/architecture/e2e-receipts/R0.json",
    }
    claimed["stages"][1]["status"] = "in_progress"
    return claimed, payload


def test_closure_validator_requires_all_27_case_traces_and_four_roles(tmp_path: Path):
    manifest, receipt = _evidence(tmp_path)
    assert inspect_stage_acceptance(root=tmp_path, manifest=manifest)["accepted_stages"] == ["R0"]
    receipt["cases"].pop()
    (tmp_path / manifest["stages"][0]["acceptance_receipt"]).write_text(json.dumps(receipt))
    with pytest.raises(StageAcceptanceError, match="All 27"):
        inspect_stage_acceptance(root=tmp_path, manifest=manifest)


def test_missing_genuine_stage_evidence_blocks_completion(tmp_path: Path):
    manifest, receipt = _evidence(tmp_path)
    receipt["reviewers"][0]["status"] = "not_run"
    target = tmp_path / manifest["stages"][0]["acceptance_receipt"]
    target.write_text(json.dumps(receipt))
    with pytest.raises(StageAcceptanceError, match="four audited"):
        inspect_stage_acceptance(root=tmp_path, manifest=manifest)
    receipt["reviewers"][0]["status"] = "pass"
    receipt["cases"][0]["live_provider_observed"] = False
    target.write_text(json.dumps(receipt))
    with pytest.raises(StageAcceptanceError, match="non-live case"):
        inspect_stage_acceptance(root=tmp_path, manifest=manifest)
    receipt["cases"][0]["live_provider_observed"] = True
    target.write_text(json.dumps(receipt))
    (tmp_path / receipt["cases"][0]["trace_artifact"]).write_text("altered")
    with pytest.raises(StageAcceptanceError, match="Altered browser trace"):
        inspect_stage_acceptance(root=tmp_path, manifest=manifest)


def test_additional_regressions_cannot_disappear_from_an_accepted_stage(tmp_path: Path):
    manifest, receipt = _evidence(tmp_path)
    additional_path = tmp_path / STAGE["additional_regression_source"]
    extra = json.loads(additional_path.read_text())
    extra["cases"].pop()
    additional_path.write_text(json.dumps(extra))
    # The prior 30-case receipt has more cases than the altered 29-case catalog;
    # a supposed complete stage must now fail rather than silently ignore one.
    with pytest.raises(StageAcceptanceError, match="regression sources changed"):
        inspect_stage_acceptance(root=tmp_path, manifest=manifest)


def test_frozen_source_rewrite_is_not_accepted_even_with_new_receipts(tmp_path: Path):
    manifest, _receipt = _evidence(tmp_path)
    cases = tmp_path / STAGE["additional_regression_source"]
    additional = json.loads(cases.read_text())
    additional["cases"][0]["source"] = "He visto a alguien."
    cases.write_text(json.dumps(additional))
    with pytest.raises(StageAcceptanceError, match="regression sources changed"):
        inspect_stage_acceptance(root=tmp_path, manifest=manifest)


def test_additional_regression_ids_cannot_be_reordered_or_reused():
    from scripts.odyssey_r0_browser_campaign import additional_cases, campaign_cases

    addition = additional_cases()
    assert [case.id for case in addition] == ["R28", "R29", "R30"]
    assert [case.id for case in campaign_cases()] == [
        *(f"F{i:02d}" for i in range(1, 28)),
        "R28",
        "R29",
        "R30",
    ]
    assert len({case.source_sha256 for case in campaign_cases()}) == 30


def test_real_model_call_count_must_cover_all_appended_cases(tmp_path: Path):
    manifest, receipt = _evidence(tmp_path)
    receipt["provider_calls"] = 29
    path = tmp_path / manifest["stages"][0]["acceptance_receipt"]
    path.write_text(json.dumps(receipt))
    with pytest.raises(StageAcceptanceError, match="provider-call count"):
        inspect_stage_acceptance(root=tmp_path, manifest=manifest)


def test_compound_source_cannot_pass_with_only_first_fact_verified(tmp_path: Path):
    """F01 has three occurrences; a saved park fact cannot hide missing cinema/concert."""
    manifest, receipt = _evidence(tmp_path)
    f01 = receipt["cases"][0]
    assert len(f01["unit_verifications"]) == 3
    f01["unit_verifications"] = f01["unit_verifications"][:1]
    (tmp_path / manifest["stages"][0]["acceptance_receipt"]).write_text(json.dumps(receipt))
    with pytest.raises(StageAcceptanceError, match="per-unit semantic verification"):
        inspect_stage_acceptance(root=tmp_path, manifest=manifest)


def test_ambiguous_reference_must_stay_unresolved_with_proof(tmp_path: Path):
    """F14 may persist the proven conversation, never guess the cinema companion."""
    manifest, receipt = _evidence(tmp_path)
    f14 = receipt["cases"][13]
    assert [unit["disposition"] for unit in f14["unit_verifications"]] == [
        "persisted",
        "pending_unresolved",
    ]
    f14["unit_verifications"][1]["disposition"] = "persisted"
    (tmp_path / manifest["stages"][0]["acceptance_receipt"]).write_text(json.dumps(receipt))
    with pytest.raises(StageAcceptanceError, match="invented identity"):
        inspect_stage_acceptance(root=tmp_path, manifest=manifest)


def test_existing_fact_noop_requires_canonical_proof(tmp_path: Path):
    """F09 equivalence is allowed but must be grounded, not a missing write."""
    manifest, receipt = _evidence(tmp_path)
    f09 = receipt["cases"][8]
    f09["unit_verifications"][0]["disposition"] = "existing_proven"
    f09["unit_verifications"][0]["canonical_readback"] = False
    (tmp_path / manifest["stages"][0]["acceptance_receipt"]).write_text(json.dumps(receipt))
    with pytest.raises(StageAcceptanceError, match="Incomplete semantic unit"):
        inspect_stage_acceptance(root=tmp_path, manifest=manifest)


def test_original_unit_oracle_cannot_delete_cinema_or_concert(tmp_path: Path):
    manifest, _receipt = _evidence(tmp_path)
    file = tmp_path / STAGE["original_case_design"]
    design = json.loads(file.read_text())
    assert len(design["cases"][0]["expected_units"]) == 3
    design["cases"][0]["expected_units"].pop()
    file.write_text(json.dumps(design))
    with pytest.raises(StageAcceptanceError, match="regression sources changed"):
        inspect_stage_acceptance(root=tmp_path, manifest=manifest)


def test_added_case_expectation_and_fixture_are_immutable(tmp_path: Path):
    manifest, _receipt = _evidence(tmp_path)
    file = tmp_path / STAGE["additional_regression_source"]
    catalog = json.loads(file.read_text())
    catalog["cases"][1]["fixture_setup"][0]["facts"] = ["La persona conoció a otra persona."]
    file.write_text(json.dumps(catalog))
    with pytest.raises(StageAcceptanceError, match="regression sources changed"):
        inspect_stage_acceptance(root=tmp_path, manifest=manifest)
