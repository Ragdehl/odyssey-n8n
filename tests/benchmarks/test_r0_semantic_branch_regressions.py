"""G02: fail a future semantic special-case added anywhere in product Python.

AST review is a tripwire, NOT a proof that existing R0 debt is solved.
Synthetic negative mutations exercise the detector, not application behavior.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts import audit_semantic_branch_regressions as gate


def test_pinned_whole_product_inventory_is_not_silently_reanchored():
    baseline = gate.BASELINE.read_bytes()
    assert hashlib.sha256(baseline).hexdigest() == (
        "1a96cdc18e58f3c53b35f44e9e4aff186c2bef055a4dd1a26d13b77128fb6e7d"
    )
    stored = json.loads(baseline)
    assert stored["pinned_source_sha"] == "2dfd87ca251847012eb4932f6bb6b80ec38ddbe5"
    assert len(stored["observations"]) == 86
    assert len({x["file"] for x in stored["observations"]}) == 48
    assert all(x["file"].startswith(gate.PACKAGES) for x in stored["observations"])
    status = gate.audit()
    assert status["status"] == "NO_NEW_FLAGS", status["new_review_required"][:10]
    assert status["new_review_required"] == []
    # Existing debts must not be relabeled as "clean" to pass CI.
    assert status["current"] <= status["baseline"]
    assert "not certified generic" in status["warning"]


def test_new_phrase_type_and_participant_threshold_branches_are_detected():
    # Each of these is a forbidden production decision, regardless of names,
    # phrases, model or whether existing example-based tests happen to pass.
    mutated = """
def example(source, note_type, participants):
    if "mi padre" in source:
        return "special"
    if note_type == "project":
        return "special_project"
    if len(participants) > 8:
        return "reject_ninth"
    return None
"""
    flagged = gate.inspect_module(mutated, path="odyssey_runtime/new_semantic_path.py")
    assert len(flagged) == 3
    assert {category for x in flagged for category in x["categories"]} == {
        "source_literal_review",
        "typed_dispatch_review",
        "semantic_count_review",
    }
    assert len(gate.novel_findings(flagged, [])) == 3
    # The exact old P4 cap is itself prohibited as a newly reintroduced rule.
    flagged_cap = gate.inspect_module(
        "def old_limit(proposed_relation_spans):\n    if len(proposed_relation_spans) > 8:\n        return False\n",
        path="odyssey_runtime/whole_source_light.py",
    )
    assert len(flagged_cap) == 1
    assert flagged_cap[0]["categories"] == ["semantic_count_review"]


def test_match_case_style_semantic_dispatch_is_caught():
    examples = """
def match_case(source, note_type):
    match note_type:
        case "project":
            return 1
        case "person":
            return 2
    match source:
        case "Ayer hablé con Nora":
            return 3
"""
    flagged = gate.inspect_module(examples, path="odyssey_runtime/future.py")
    assert len(flagged) == 2
    assert {category for x in flagged for category in x["categories"]} == {
        "typed_dispatch_review",
        "source_literal_review",
    }


def test_cross_package_new_branch_fails_and_removing_a_legacy_branch_passes(tmp_path: Path):
    for package in gate.PACKAGES:
        folder = tmp_path / package
        folder.mkdir()
        (folder / "new.py").write_text(
            'def narrow(source):\n    if source.startswith("Ayer hablé con"):\n        return True\n'
        )
    known = json.loads(gate.BASELINE.read_text())["observations"]
    additions = gate.novel_findings(gate.inventory(tmp_path), known)
    assert len(additions) == len(gate.PACKAGES)
    assert {item["file"].split("/")[0] for item in additions} == set(gate.PACKAGES)
    assert gate.novel_findings(known[:-1], known) == []


def test_schema_driven_validation_and_source_provenance_are_not_auto_rejected():
    generic = """
def generic(source, evidence, schema, properties):
    if evidence.source_span not in source:
        raise ValueError("untrusted evidence")
    if evidence.note_type not in schema.types:
        raise ValueError("unknown schema type")
    if len(properties) > schema.max_properties:
        raise ValueError("bounded resources")
"""
    assert gate.inspect_module(generic, path="odyssey_core/generic.py") == []
    # This test does NOT authorize adding semantically narrow code under
    # another name: independent human and four-role review is still mandatory.
