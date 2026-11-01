"""The E4 acceptance proof must not be self-validating on fabricated evidence."""

from __future__ import annotations

import copy
import hashlib
import json

import pytest

from scripts.odyssey_e4_functional_acceptance import (
    RECEIPT,
    ROOT,
    AcceptanceError,
    validate_live_receipt,
    validate_provenance,
)


@pytest.fixture
def actual():
    return json.loads(RECEIPT.read_text(encoding="utf8"))


def test_historical_real_receipt_still_has_valid_results_but_cannot_certify_new_source():
    """Keep old E4 evidence as history; a changed runtime invalidates its acceptance.

    The historic receipt represents a specific previous source commit. Treating
    that proof as current would silently bypass R0's SHA-bound acceptance gate.
    """
    historical = json.loads(RECEIPT.read_text(encoding="utf8"))
    trace = (ROOT / historical["committed_full_log"]).resolve()
    assert trace.is_relative_to((ROOT / "docs/architecture").resolve())
    assert trace.is_file()
    assert hashlib.sha256(trace.read_bytes()).hexdigest() == historical["full_log_sha256"]
    result = validate_live_receipt(historical)
    assert result["people"] == ["Ana María", "Luis"]
    assert result["http_searches_verified"] == 3
    with pytest.raises(AcceptanceError, match="Runtime changed after the proven live E2E"):
        validate_provenance()


@pytest.mark.parametrize(
    "change",
    [
        lambda r: r["browser"]["notes"].update(verifiedPersonBacklinks=1),
        lambda r: r["physical_result"].update(physical_tasks=2),
        lambda r: r["browser"]["notes"]["searchObservations"][1].update(apiResponse=False),
        lambda r: r["browser"]["notes"]["searchObservations"][2].update(matchRows=0),
        lambda r: r["physical_result"].update(markdown_e3_replay_unchanged=False),
        lambda r: r["browser"].update(recordedFixture=True),
        lambda r: r["browser"]["progressTrace"].update(advanced=False),
        lambda r: r.update(expected_people=["María", "Luis"]),
        lambda r: r["physical_result"].update(gpt="recorded"),
        lambda r: r["browser"].update(pass_=False),
    ],
)
def test_false_success_or_stale_ui_evidence_is_rejected(actual, change):
    tampered = copy.deepcopy(actual)
    change(tampered)
    if "pass_" in tampered["browser"]:
        tampered["browser"]["pass"] = False
    with pytest.raises(AcceptanceError):
        validate_live_receipt(tampered)
