"""E2 read-only source DAG for N:M dependent interpretation groups.

An untrusted Router or reviewer may describe edges; neither can create an
identity or authorize a mutation. A consumer still needs Core's *per-edge*
canonical backlink evidence and current CAS after each predecessor writes.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .source_provenance import SourceEvidenceError, anchor_original_partition

REVIEW_REASONS = frozenset(
    {
        "APPROVED",
        "SOURCE_COVERAGE",
        "GROUP_CLASSIFICATION",
        "GROUP_ATOMICITY",
        "DEPENDENCY_AMBIGUOUS",
        "DEPENDENCY_UNGROUNDED",
        "DEPENDENCY_MISSING",
        "OTHER",
    }
)


class DependentGroupGraphError(ValueError):
    """Exact source, ordered dependencies, or reviewer agreement is missing."""


@dataclass(frozen=True, slots=True)
class GroupDependency:
    predecessor_index: int
    mention: str
    antecedent_mention: str


@dataclass(frozen=True, slots=True)
class SourceGroup:
    ordinal: int
    capability: str
    source: str
    dependencies: tuple[GroupDependency, ...]


@dataclass(frozen=True, slots=True)
class ReviewedSourceGraph:
    original: str
    groups: tuple[SourceGroup, ...]

    @property
    def edges(self) -> tuple[tuple[int, int, str, str], ...]:
        return tuple(
            (
                dependency.predecessor_index,
                group.ordinal,
                dependency.antecedent_mention,
                dependency.mention,
            )
            for group in self.groups
            for dependency in group.dependencies
        )


def verify_dependent_group_graph(
    original: str,
    proposal: Mapping[str, Any],
    review: Mapping[str, Any],
) -> ReviewedSourceGraph:
    """Prove bounded exact-span N:M source graph without assuming canonical IDs.

    Review must independently attest the EXACT same topology. Every edge's
    source mention is unique within the dependent span, and every predecessor
    is earlier than its consumer (topological execution in original order).
    A lexical edge is not evidence that the referred canonical Note exists.
    """
    if not isinstance(original, str) or not original.strip() or len(original) > 4096:
        raise DependentGroupGraphError("Source is invalid or over budget")
    if not isinstance(proposal, Mapping) or not isinstance(review, Mapping):
        raise DependentGroupGraphError("Source proposal and independent review required")
    if (
        set(proposal) != {"full_source_quote", "groups"}
        or set(review)
        != {
            "full_source_quote",
            "complete",
            "dependency_edges_verified",
            "review_reason",
            "failing_group_index",
            "groups",
        }
        or review.get("review_reason") != "APPROVED"
        or review.get("failing_group_index") is not None
        or proposal["full_source_quote"] != original
        or review["full_source_quote"] != original
        or review["complete"] is not True
        or review["dependency_edges_verified"] is not True
        or review["groups"] != proposal["groups"]
    ):
        raise DependentGroupGraphError("Reviewer did not attest full source and exact DAG")
    raw_groups = proposal["groups"]
    if not isinstance(raw_groups, list) or not 2 <= len(raw_groups) <= 16:
        raise DependentGroupGraphError("Bounded groups required")
    if any(
        not isinstance(group, Mapping)
        or set(group) != {"capability", "source_quote", "dependencies"}
        or group.get("capability") not in ("core", "tasks")
        or not isinstance(group.get("source_quote"), str)
        or not group["source_quote"].strip()
        or not isinstance(group.get("dependencies"), list)
        for group in raw_groups
    ):
        raise DependentGroupGraphError("Unrecognized source group or operation")
    try:
        anchor_original_partition(original, [group["source_quote"] for group in raw_groups])
    except SourceEvidenceError as error:
        raise DependentGroupGraphError(
            "Source spans omit, duplicate, or reorder characters"
        ) from error
    groups = []
    has_dependency = False
    for i, group in enumerate(raw_groups):
        dependencies = []
        seen = set()
        for entry in group["dependencies"]:
            if not isinstance(entry, Mapping) or set(entry) != {
                "predecessor_index",
                "mention",
                "antecedent_mention",
            }:
                raise DependentGroupGraphError("Unrecognized dependency edge")
            parent = entry["predecessor_index"]
            mention = entry["mention"]
            antecedent_mention = entry["antecedent_mention"]
            key = (parent, antecedent_mention, mention)
            if (
                not isinstance(parent, int)
                or isinstance(parent, bool)
                or not 0 <= parent < i
                or key in seen
                or not isinstance(mention, str)
                or not mention.strip()
                or mention != mention.strip()
                or len(mention) > 120
                or group["source_quote"].casefold().count(mention.casefold()) != 1
                or not isinstance(antecedent_mention, str)
                or not antecedent_mention.strip()
                or antecedent_mention != antecedent_mention.strip()
                or len(antecedent_mention) > 120
                or raw_groups[parent]["source_quote"]
                .casefold()
                .count(antecedent_mention.casefold())
                != 1
            ):
                raise DependentGroupGraphError("Ambiguous, forward, or ungrounded dependency")
            seen.add(key)
            dependencies.append(GroupDependency(parent, mention, antecedent_mention))
        if len(dependencies) > 8:
            raise DependentGroupGraphError("Dependency fan-in exceeds budget")
        has_dependency |= bool(dependencies)
        groups.append(
            SourceGroup(i, group["capability"], group["source_quote"], tuple(dependencies))
        )
    if not has_dependency:
        raise DependentGroupGraphError("Independent groups require the independent-source contract")
    return ReviewedSourceGraph(original, tuple(groups))


def classify_dependent_group_review_rejection(
    original: str, proposal: Mapping[str, Any], review: Mapping[str, Any]
) -> tuple[str, int | None]:
    """Validate a diagnostic from the independent auditor, never authorize it.

    A model-generated rejection code is informational only; it cannot become
    approval or an alternate source partition. Only canonical graph verifier
    grants the *structural* acceptance for an APPROVED review.
    """
    if (
        not isinstance(original, str)
        or not original.strip()
        or not isinstance(proposal, Mapping)
        or not isinstance(review, Mapping)
    ):
        raise DependentGroupGraphError("Invalid rejection diagnostic source")
    expected = {
        "full_source_quote",
        "complete",
        "dependency_edges_verified",
        "review_reason",
        "failing_group_index",
        "groups",
    }
    if (
        set(review) != expected
        or proposal.get("full_source_quote") != original
        or review.get("full_source_quote") != original
        or review.get("review_reason") not in REVIEW_REASONS
    ):
        raise DependentGroupGraphError("Rejection diagnostic identity is invalid")
    reason = review["review_reason"]
    group = review["failing_group_index"]
    groups = proposal.get("groups")
    if (
        reason == "APPROVED"
        or review["complete"] is not False
        and review["dependency_edges_verified"] is not False
        or review["groups"] != []
        or not isinstance(groups, list)
        or not isinstance(group, (int, type(None)))
        or isinstance(group, bool)
        or (group is not None and not 0 <= group < len(groups))
    ):
        raise DependentGroupGraphError("Contradictory or unsupported rejection diagnostic")
    return reason, group
