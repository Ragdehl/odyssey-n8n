"""Operator status cannot confuse working code, installed DEV or test pass."""

from __future__ import annotations

import pytest

from scripts import odyssey_operator_status as status


def _fixture(tmp_path, monkeypatch, *, committed=False, dev="old-dev"):
    root = tmp_path / "feature"
    dev_root = tmp_path / "dev"
    (root / "docs/architecture").mkdir(parents=True)
    dev_root.mkdir()
    (root / "docs/architecture/odyssey-acceptance-contracts.json").write_text(
        '{"contracts": [{"id": "E3-CLAIM-CRASH", "invariant": "Safe recovery after crash", '
        '"max_evidence_level": "isolated_http"}]}'
    )
    (root / "docs/architecture/functional-roadmap.md").write_text(
        "# Roadmap\n\n## Current — 23 October 2026\n\n"
        "**Latest verified before the documentation refactor**: fixture.\n\n"
        "## Siguiente\n\nNo actualizar manualmente.\n"
    )
    monkeypatch.setattr(
        status,
        "inspect_contracts",
        lambda **_kw: {
            "contract_count": 15,
            "existing_offline_test_anchors": 19,
            "scope": "integrity_only",
            "blocked_product_contracts": ["E3-CLAIM-CRASH"],
        },
    )

    def git(path, *args):
        if path == dev_root:
            return dev
        if args == ("branch", "--show-current"):
            return "feat/p4"
        if args == ("rev-parse", "--short", "HEAD"):
            return "new-work"
        if args == ("status", "--porcelain"):
            return "" if committed else " M files"
        raise AssertionError(args)

    monkeypatch.setattr(status, "_git", git)
    return root, dev_root


@pytest.mark.parametrize("clean", [False, True])
def test_status_shows_installed_dev_and_not_just_latest_code(tmp_path, monkeypatch, clean):
    root, dev = _fixture(tmp_path, monkeypatch, committed=clean)
    result = status.operator_status(root=root, dev=dev)
    assert result["feature_branch"] == "feat/p4"
    assert result["feature_commit"] == "new-work"
    assert result["installed_dev_commit"] == "old-dev"
    assert result["branch_matches_installed_dev"] is False
    assert result["feature_tree_clean"] is clean
    assert result["verified_browser_n8n"] is False
    assert result["p4_dev_ready"] is False
    assert result["prod_change_authorized"] is False
    assert result["acceptance_scope"] == "integrity_only"
    assert result["pending_acceptance_count"] == 1
    assert result["pending_acceptance"][0]["id"] == "E3-CLAIM-CRASH"
    assert result["pending_acceptance"][0]["invariant"] == "Safe recovery after crash"


def test_status_fails_closed_if_canonical_roadmap_is_missing(tmp_path, monkeypatch):
    root, dev = _fixture(tmp_path, monkeypatch)
    (root / "docs/architecture/functional-roadmap.md").write_text("# No roadmap")
    with pytest.raises(ValueError, match="canonical roadmap"):
        status.operator_status(root=root, dev=dev)


def test_status_fails_closed_without_independent_dev_version(tmp_path, monkeypatch):
    root, dev = _fixture(tmp_path, monkeypatch, dev=None)
    with pytest.raises(ValueError, match="DEV version"):
        status.operator_status(root=root, dev=dev)


def test_status_does_not_change_any_file(tmp_path, monkeypatch):
    root, dev = _fixture(tmp_path, monkeypatch)
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    status.operator_status(root=root, dev=dev)
    assert before == {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
