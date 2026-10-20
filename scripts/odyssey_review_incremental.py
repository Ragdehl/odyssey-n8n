"""Pure checks for safe inherited independent audits after a small correction.

Only a prior complete, four-PASS, immutable review can be inherited. A change
in Core, Writer, identity, E3, schema or other cross-surface code invalidates
all four and requires a full new review. This module never calls Codex.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts import odyssey_review_scope as scope


class IncrementalReviewError(ValueError):
    pass


def audited_prior(prior: dict, artifacts_root: Path, job: str) -> dict[str, str]:
    """Verify original individual PASS receipts, never rely on status text alone."""
    if prior.get("job") != job or prior.get("phase") not in (
        "reviewed_browser_gate_pending",
        "reviewed_tooling_ready",
    ):
        raise IncrementalReviewError("Prior job lacks complete formal independent review")
    previous_commit = prior.get("feature_commit")
    source_sha = prior.get("audit_source_sha256")
    if (
        not isinstance(previous_commit, str)
        or len(previous_commit) != 40
        or (not isinstance(source_sha, str) or len(source_sha) != 64)
    ):
        raise IncrementalReviewError("Prior source identity is not pinned")
    if set(prior.get("reviews", {})) != set(scope.REVIEW_ROLES):
        raise IncrementalReviewError("Prior review must contain all four specialists")
    artifacts = prior.get("review_artifacts", {})
    if set(artifacts) != set(scope.REVIEW_ROLES):
        raise IncrementalReviewError("Prior review artifacts are incomplete")
    artifact_hashes = {}
    round_number = prior.get("round")
    for role in scope.REVIEW_ROLES:
        record = prior["reviews"].get(role)
        if not isinstance(record, dict) or record.get("verdict") != "pass":
            raise IncrementalReviewError("Cannot inherit a failed or blocked specialist")
        expected = artifacts_root / job / f"round-{round_number}" / f"{role}-completed.json"
        if artifacts[role] != str(expected) or expected.is_symlink() or not expected.is_file():
            raise IncrementalReviewError("Untrusted prior specialist receipt location")
        raw = expected.read_bytes()
        try:
            receipt = json.loads(raw)
        except (ValueError, UnicodeDecodeError) as error:
            raise IncrementalReviewError("Unreadable prior specialist receipt") from error
        if receipt.get("role") != role or receipt.get("verdict") != record:
            raise IncrementalReviewError("Prior receipt does not match published verdict")
        artifact_hashes[role] = hashlib.sha256(raw).hexdigest()
    return artifact_hashes


def inherited_roles(prior: dict, current: dict) -> tuple[str, ...]:
    """No inheritance if impact classifier would require a full review."""
    paths = current.get("changed_paths")
    if not isinstance(paths, list) or not paths or any(not isinstance(p, str) for p in paths):
        raise IncrementalReviewError("No bounded correction path manifest")
    invalidated = scope.invalidated_roles(tuple(paths))
    return tuple(role for role in scope.REVIEW_ROLES if role not in invalidated)
