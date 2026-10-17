"""E2 read-only source DAG for N:M dependent interpretation groups.

An untrusted Router or reviewer may describe edges; neither can create an
identity or authorize a mutation. A consumer still needs Core's *per-edge*
canonical backlink evidence and current CAS after each predecessor writes.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


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
        or set(review) != {"full_source_quote", "complete", "dependency_edges_verified", "groups"}
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
    if "".join(group["source_quote"] for group in raw_groups) != original:
        raise DependentGroupGraphError("Source spans omit, duplicate, or reorder characters")
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
