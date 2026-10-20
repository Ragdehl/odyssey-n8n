"""Deterministic, conservative role evidence and incremental recheck policy.

Role-specific evidence is a reading priority, NOT an access-control boundary.
Every role retains read-only access to the complete immutable checkout.
"""

from __future__ import annotations

REVIEW_ROLES = ("generality", "quality", "testing", "performance")


def fundamental(paths: tuple[str, ...]) -> bool:
    """Anything crossing Core, Writer, identity, E3 or schema demands a full audit."""
    return any(
        path.startswith(("odyssey_core/", "odyssey_runtime/", "config/", "workflows/"))
        or any(
            term in path.casefold()
            for term in (
                "writer",
                "identity",
                "mutation",
                "canonical",
                "source_bound",
                "e3_",
                "permission",
                "security",
                "review.schema",
                "agent_cycle.py",
                "odyssey_review_scope.py",
                "odyssey_review_incremental.py",
            )
        )
        for path in paths
    )


def specialist_paths(role: str, paths: tuple[str, ...]) -> tuple[str, ...]:
    """Select evidence emphasis, not the universe of source a reviewer may inspect."""
    if role not in REVIEW_ROLES:
        raise ValueError("Unknown review role")
    if fundamental(paths):
        return paths
    if role == "generality":
        selected = tuple(p for p in paths if not p.startswith("tests/"))
    elif role == "quality":
        selected = tuple(p for p in paths if not p.startswith("tests/") or "security" in p)
    elif role == "testing":
        selected = tuple(p for p in paths if p.startswith("tests/") or p.startswith("scripts/"))
    else:
        selected = tuple(
            p
            for p in paths
            if p.startswith("tests/benchmarks/")
            or any(term in p for term in ("performance", "benchmark", "index", "startup"))
        )
    return selected or paths


def invalidated_roles(paths: tuple[str, ...]) -> tuple[str, ...]:
    """Only narrow, proven test-only or non-contract docs corrections avoid all four.

    Everything else is conservatively treated as a full review; no guessed
    dependency graph and no model assertion can silently preserve approval.
    """
    if not paths or fundamental(paths):
        return REVIEW_ROLES
    if all(p.startswith("tests/") for p in paths):
        return ("testing",)
    if all(
        p.startswith("docs/") and "/decisions/" not in p and not p.endswith("-contract.md")
        for p in paths
    ):
        return ("generality", "quality")
    return REVIEW_ROLES
