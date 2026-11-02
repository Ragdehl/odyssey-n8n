#!/usr/bin/env python3
"""Read-only AST tripwire: new case-shaped branches need a deliberate review.

This does NOT certify that existing product code is generic. The pinned
baseline is a *debt inventory*, not an allowlist of correct semantics. Only
removed or unchanged findings pass; adding/changing one fails for review.
No provider, personal notes, network, runtime process or code mutation.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import subprocess
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "docs/architecture/r0-semantic-branch-baseline.json"
PACKAGES = ("odyssey_core", "odyssey_runtime", "odyssey_apps")
SOURCE_WORDS = frozenset(
    {
        "source",
        "message",
        "text",
        "utterance",
        "raw_source",
        "original_source",
        "phrase",
        "statement",
    }
)
TYPE_WORDS = frozenset(
    {"note_type", "type_hint", "entity_type", "target_type", "canonical_type", "note_kind", "kind"}
)
TYPE_LITERALS = frozenset(
    {"person", "project", "document", "concept", "task", "calendar_day", "event", "work_session"}
)
COUNT_WORDS = frozenset(
    {
        "people",
        "participants",
        "references",
        "mentions",
        "candidates",
        "groups",
        "spans",
        "members",
        "identities",
        "names",
        "relation_spans",
        "route_scopes",
        "proposed_relation_spans",
        "reviewed_facts",
    }
)
SMALL_LIMITS = frozenset({2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 16})


def _symbols(node: ast.AST) -> set[str]:
    return {x.id for x in ast.walk(node) if isinstance(x, ast.Name)} | {
        x.attr for x in ast.walk(node) if isinstance(x, ast.Attribute)
    }


def _branch_reasons(predicate: ast.AST) -> tuple[str, ...]:
    reasons: set[str] = set()
    for node in ast.walk(predicate):
        if isinstance(node, ast.Compare):
            strings = {
                x.value
                for x in ast.walk(node)
                if isinstance(x, ast.Constant) and isinstance(x.value, str)
            }
            symbols = _symbols(node)
            if strings & TYPE_LITERALS and symbols & TYPE_WORDS:
                reasons.add("typed_dispatch_review")
            if (
                strings
                and symbols & SOURCE_WORDS
                and any(isinstance(op, (ast.In, ast.NotIn, ast.Eq, ast.NotEq)) for op in node.ops)
            ):
                reasons.add("source_literal_review")
            if any(isinstance(op, (ast.Gt, ast.GtE, ast.Lt, ast.LtE, ast.Eq)) for op in node.ops):
                numbers = {
                    x.value
                    for x in (node.left, *node.comparators)
                    if isinstance(x, ast.Constant) and type(x.value) is int
                }
                if numbers & SMALL_LIMITS and any(
                    isinstance(call, ast.Call)
                    and isinstance(call.func, ast.Name)
                    and call.func.id == "len"
                    and bool(_symbols(call) & COUNT_WORDS)
                    for call in ast.walk(node)
                ):
                    reasons.add("semantic_count_review")
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in {"startswith", "endswith", "find", "count"}
            and bool(_symbols(node.func.value) & SOURCE_WORDS)
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            reasons.add("source_literal_review")
    return tuple(sorted(reasons))


def inspect_module(source: str, *, path: str) -> list[dict[str, str | list[str]]]:
    """Find suspicious predicates in any function, including nested functions."""
    tree = ast.parse(source, filename=path)
    results: list[dict[str, str | list[str]]] = []

    def walk(node: ast.AST, context: str) -> None:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            context = f"{context}.{node.name}" if context != "<module>" else node.name
        if isinstance(node, (ast.If, ast.IfExp, ast.Match)):
            predicate = node.subject if isinstance(node, ast.Match) else node.test
            reasons = set(_branch_reasons(predicate))
            if isinstance(node, ast.Match):
                names = _symbols(predicate)
                literals = {
                    part.value
                    for case in node.cases
                    for part in ast.walk(case.pattern)
                    if isinstance(part, ast.Constant) and isinstance(part.value, str)
                }
                if names & TYPE_WORDS and literals & TYPE_LITERALS:
                    reasons.add("typed_dispatch_review")
                if names & SOURCE_WORDS and literals:
                    reasons.add("source_literal_review")
            if reasons:
                # AST shape, not line numbers or formatting, is the identity.
                fingerprint = hashlib.sha256(
                    ast.dump(predicate, include_attributes=False).encode("utf-8")
                ).hexdigest()
                results.append(
                    {
                        "file": path,
                        "owner": context,
                        "predicate_sha256": fingerprint,
                        "categories": sorted(reasons),
                    }
                )
        for child in ast.iter_child_nodes(node):
            walk(child, context)

    walk(tree, "<module>")
    return results


def inventory(root: Path = ROOT) -> list[dict[str, str | list[str]]]:
    result = []
    for folder in PACKAGES:
        for file in sorted((root / folder).rglob("*.py")):
            result.extend(
                inspect_module(
                    file.read_text(encoding="utf-8"), path=file.relative_to(root).as_posix()
                )
            )
    return sorted(
        result, key=lambda x: (str(x["file"]), str(x["owner"]), str(x["predicate_sha256"]))
    )


def _key(row: dict) -> str:
    return json.dumps(row, sort_keys=True, separators=(",", ":"))


def novel_findings(current: list[dict], baseline: list[dict]) -> list[dict]:
    """Count duplicates; deleting legacy branches is allowed, adding is not."""
    budget = Counter(_key(x) for x in baseline)
    unexpected = []
    for item in current:
        key = _key(item)
        if budget[key] > 0:
            budget[key] -= 1
        else:
            unexpected.append(item)
    return unexpected


def audit(root: Path = ROOT, baseline_file: Path = BASELINE) -> dict:
    frozen = json.loads(baseline_file.read_text(encoding="utf-8"))
    if frozen.get("schema") != "odyssey-r0-semantic-branch-baseline-v1" or not isinstance(
        frozen.get("observations"), list
    ):
        raise ValueError("Invalid pinned R0 AST review inventory")
    existing = frozen["observations"]
    current = inventory(root)
    added = novel_findings(current, existing)
    return {
        "status": "REVIEW_REQUIRED" if added else "NO_NEW_FLAGS",
        "baseline": len(existing),
        "current": len(current),
        "removed": len(existing) - len(current) + len(added),
        "new_review_required": added,
        "warning": "Heuristic AST review only; existing suspicious branches remain OPEN, not certified generic",
    }


def unreferenced_new_production_definitions(
    before: dict[str, str], after: dict[str, str], production: dict[str, str]
) -> list[dict[str, str]]:
    """Block newly introduced source definitions without a reachable production caller.

    A production caller that existed before the patch anchors the graph. New
    functions calling each other are not themselves proof of integration.
    Tests are deliberately excluded; static reachability is a NECESSARY but
    never a sufficient condition for genuine reuse or semantic generality.
    """
    definitions: dict[tuple[str, str], ast.AST] = {}
    for path, source in after.items():
        if not path.startswith(PACKAGES) or not path.endswith(".py"):
            continue
        old_names = set()
        if path in before:
            old_names = {
                (type(node).__name__, node.name)
                for node in ast.parse(before[path], filename=path).body
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
            }
        for node in ast.parse(source, filename=path).body:
            if (
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                and (type(node).__name__, node.name) not in old_names
            ):
                definitions[(path, node.name)] = node

    if not definitions:
        return []
    by_name: dict[str, set[tuple[str, str]]] = {}
    for key in definitions:
        by_name.setdefault(key[1], set()).add(key)
    uses: dict[tuple[str, str] | None, set[tuple[str, str]]] = {}
    for path, source in production.items():
        if not path.startswith(PACKAGES) or not path.endswith(".py"):
            continue
        tree = ast.parse(source, filename=path)
        for node in tree.body:
            # Module-level expressions and pre-existing definitions are roots.
            # A new definition is not a root just because a test imports it.
            caller = (
                (path, node.name)
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                else None
            )
            owner = caller if caller in definitions else None
            found = uses.setdefault(owner, set())
            for access in ast.walk(node):
                # ImportFrom is not a usage: imported-but-unused exports are
                # still blocked, and `__all__` string literals are ignored.
                name = (
                    access.id
                    if isinstance(access, ast.Name) and isinstance(access.ctx, ast.Load)
                    else access.attr
                    if isinstance(access, ast.Attribute)
                    else None
                )
                if name:
                    for target in by_name.get(name, ()):
                        if target != caller:
                            found.add(target)

    reachable = set(uses.get(None, ()))
    while True:
        next_reachable = reachable | set().union(
            *(uses.get(node, set()) for node in reachable), set()
        )
        if next_reachable == reachable:
            break
        reachable = next_reachable
    return [
        {
            "file": path,
            "name": name,
            "reason": "new_production_definition_without_existing_path",
        }
        for path, name in sorted(definitions)
        if (path, name) not in reachable
    ]


def new_definition_usage_for_branch(root: Path = ROOT, base: str | None = None) -> list[dict]:
    """Diff against a real Git base; include staged files for pre-commit.

    For a PR this should be the actual integration base (normally origin/dev),
    not a dated exception list. Missing Git evidence fails closed.
    """

    def git(*args: str) -> str:
        return subprocess.check_output(
            ["git", *args], cwd=root, text=True, stderr=subprocess.DEVNULL
        ).strip()

    if base is None:
        base = git("merge-base", "HEAD", "origin/dev")
    base = git("rev-parse", "--verify", f"{base}^{{commit}}")
    modified = git("diff", "--name-only", "--diff-filter=ACMR", base, "--", *PACKAGES)
    old: dict[str, str] = {}
    new: dict[str, str] = {}
    for path in modified.splitlines():
        if not path.endswith(".py") or not path.startswith(PACKAGES):
            continue
        new[path] = (root / path).read_text(encoding="utf-8")
        result = subprocess.run(
            ["git", "show", f"{base}:{path}"], cwd=root, text=True, capture_output=True, check=False
        )
        if result.returncode == 0:
            old[path] = result.stdout
    production = {
        path.relative_to(root).as_posix(): path.read_text(encoding="utf-8")
        for package in PACKAGES
        for path in (root / package).rglob("*.py")
    }
    return unreferenced_new_production_definitions(old, new, production)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-production-use", action="store_true")
    parser.add_argument("--base", help="Git SHA/ref of the integration base")
    args = parser.parse_args()
    report = audit()
    if args.require_production_use:
        report["unreferenced_new_definitions"] = new_definition_usage_for_branch(base=args.base)
        if report["unreferenced_new_definitions"]:
            report["status"] = "REVIEW_REQUIRED"
    print(json.dumps(report, indent=2, ensure_ascii=False))
    raise SystemExit(1 if report["status"] != "NO_NEW_FLAGS" else 0)
