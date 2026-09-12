"""Deterministic tests for the DEV deployment coherence guard."""

from __future__ import annotations

import subprocess
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "scripts" / "odyssey-dev"
CURRENT = "a" * 40
OTHER = "b" * 40


def coherence_result(current: str, recorded: str, deployed: str, dirty: str) -> bool:
    """Evaluate the operator's source-coherence predicate in Bash."""
    command = f"source {SCRIPT}; source_is_coherent {current} {recorded} {deployed} {dirty!r}"
    return subprocess.run(["bash", "-c", command], check=False).returncode == 0


def test_clean_checkout_at_deployed_commit_is_coherent() -> None:
    assert coherence_result(CURRENT, CURRENT, CURRENT, "") is True


def test_different_head_is_not_coherent() -> None:
    assert coherence_result(OTHER, CURRENT, CURRENT, "") is False


def test_dirty_checkout_is_not_coherent() -> None:
    assert coherence_result(CURRENT, CURRENT, CURRENT, " M scripts/odyssey-dev") is False
