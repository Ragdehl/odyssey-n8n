"""Validate Odyssey's always-on instructions, skills and active documentation links.

This is a deterministic, offline check: no LLM calls, credentials, deployment
or private data inspection.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / ".codex/skills"

REQUIRED_SKILLS = {
    "odyssey-start-work",
    "odyssey-generality",
    "odyssey-llm-stage",
    "odyssey-live-provider",
    "odyssey-dev-e2e",
    "odyssey-architecture-challenge",
    "odyssey-verify-change",
    "odyssey-pr-feedback",
    "odyssey-post-merge",
    "odyssey-skill-steward",
    "odyssey-results",
}
CHECK_LINKS = (
    "AGENTS.md",
    "README.md",
    "docs/architecture/application-extensibility-plan.md",
    "docs/architecture/functional-roadmap.md",
    "docs/architecture/instruction-map.md",
    "docs/infrastructure/raspberry-runtime.md",
)


def check_markdown_links(path: Path) -> list[str]:
    """Report missing relative targets of Markdown inline links."""
    bad: list[str] = []
    data = path.read_text(encoding="utf-8")
    for raw in re.findall(r"(?<!!)\]\(([^)]+)\)", data):
        target = raw.split("#", 1)[0].strip()
        if (
            not target
            or target.startswith(("http://", "https://", "mailto:", "/"))
            or " " in target
        ):
            continue
        if not (path.parent / target).exists():
            bad.append(f"{path.relative_to(ROOT)}: broken link {raw!r}")
    return bad


# Immutable original 4-role global repository audit. New findings are append-only
# in the ledger; edits to the original audit or root-cause assignments require
# explicit code review, never silent changes to make a documentation gate green.
R0_AUDIT_SHA256 = "cf55785a07ab809f952ab5a3327ae609737628fd9c695876711bd7a40638e5df"
R0_ORIGIN_ASSIGNMENTS_SHA256 = "aa6b66df637faf4b2016fff22a77cc1cb1a8f256a49eac8480f0840a5044aad2"
R0_ROLE_ORDER = ("core", "runtime", "apps_ui", "qa_ops")
R0_STATES = frozenset({"open", "in_progress", "code_verified", "closed", "deferred_after_r0"})


def check_r0_findings(root: Path = ROOT) -> list[str]:
    """Verify traceable R0 findings; this is NOT a semantic/live acceptance test."""
    audit_path = root / "docs/architecture/r0-whole-repository-source-audit-evidence-20261031.json"
    ledger_path = root / "docs/architecture/r0-remediation-ledger.json"
    plan_path = root / "docs/architecture/r0-remediation-plan.md"
    if not audit_path.is_file() or not ledger_path.is_file() or not plan_path.is_file():
        return ["R0: immutable audit, remediation ledger and plan must all exist"]
    audit_bytes = audit_path.read_bytes()
    if hashlib.sha256(audit_bytes).hexdigest() != R0_AUDIT_SHA256:
        return ["R0: original whole-repository audit changed; do not rewrite findings"]
    try:
        audit = json.loads(audit_bytes)
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeError):
        return ["R0: original audit or ledger has invalid JSON"]
    if not isinstance(ledger, dict) or ledger.get("schema") != "odyssey-r0-findings-ledger-v1":
        return ["R0: remediation ledger schema missing or invalid"]
    errors: list[str] = []
    if ledger.get("audit_snapshot_sha") != audit.get("snapshot"):
        errors.append("R0: remediation ledger source commit drift")
    if ledger.get("audit_evidence") != str(audit_path.relative_to(root)):
        errors.append("R0: remediation ledger original evidence link changed")
    if ledger.get("plan") != str(plan_path.relative_to(root)):
        errors.append("R0: remediation ledger plan link changed")
    groups = ledger.get("workstreams")
    if not isinstance(groups, list) or len(groups) != 13:
        errors.append("R0: expected 13 original root-cause groups")
        groups = []
    group_ids = [g.get("id") for g in groups if isinstance(g, dict)]
    if (
        len(group_ids) != 13
        or len(set(group_ids)) != 13
        or set(group_ids) != {f"G{i:02}" for i in range(1, 14)}
    ):
        errors.append("R0: root-cause group IDs deleted/duplicated")
    for g in groups:
        if not isinstance(g, dict):
            errors.append("R0: root-cause group is not an object")
            continue
        if (
            g.get("status")
            not in {"not_started", "in_progress", "code_verified", "closed", "deferred_after_r0"}
            or g.get("review_decision")
            not in {"pending_review", "approved_for_implementation", "needs_revision"}
            or not g.get("existing_owner")
            or not g.get("change_contract")
            or not g.get("verification")
            or not isinstance(g.get("depends_on"), list)
            or any(item not in group_ids or item == g.get("id") for item in g["depends_on"])
        ):
            errors.append(f"R0: invalid root-cause plan/owner/status: {g.get('id')}")
    findings = ledger.get("findings")
    if not isinstance(findings, list) or len(findings) != 24:
        return errors + ["R0: exactly 24 original audit findings must remain"]
    if not all(isinstance(f, dict) for f in findings):
        return errors + ["R0: finding row must be a JSON object"]
    expected: list[tuple[str, int, dict]] = [
        (role, idx, original)
        for role in R0_ROLE_ORDER
        for idx, original in enumerate(audit["roles"][role]["findings"], 1)
    ]
    if len(expected) != len(findings):
        return errors + ["R0: original audit origin count changed"]
    assignments: list[tuple[str, int, str]] = []
    for count, (f, (role, index, original)) in enumerate(zip(findings, expected, strict=True), 1):
        fingerprint = hashlib.sha256(
            json.dumps(original, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        if (
            f.get("id") != f"R0-F{count:03}"
            or f.get("audit_role") != role
            or f.get("audit_index") != index
            or f.get("audit_fingerprint_sha256") != fingerprint
            or f.get("severity") != original["severity"]
            or f.get("reference") != original["path"]
        ):
            errors.append(f"R0: origin/severity/reference changed for finding R0-F{count:03}")
        group = f.get("workstream_id")
        if group not in group_ids:
            errors.append(f"R0: finding R0-F{count:03} has no recognized remediation group")
        assignments.append((role, index, group))
        status = f.get("state")
        if status not in R0_STATES:
            errors.append(f"R0: invalid state for R0-F{count:03}")
        if status == "deferred_after_r0" and (group != "G13" or original["severity"] != "warning"):
            errors.append(f"R0: architectural blocker cannot be deferred: R0-F{count:03}")
        proof = f.get("closure")
        if status in {"code_verified", "closed"}:
            if not isinstance(proof, dict):
                errors.append(f"R0: closure evidence missing for R0-F{count:03}")
            elif (
                not isinstance(proof.get("commit_sha"), str)
                or not re.fullmatch(r"[0-9a-f]{40}", proof["commit_sha"])
                or not isinstance(proof.get("before_after"), str)
                or len(proof["before_after"].strip()) < 30
                or not isinstance(proof.get("tests"), list)
                or not proof["tests"]
                or not all(
                    isinstance(p, str) and p.startswith("tests/") and (root / p).is_file()
                    for p in proof["tests"]
                )
                or status == "closed"
                and (
                    not isinstance(proof.get("independent_reviews"), list)
                    or not proof["independent_reviews"]
                    or not all(
                        isinstance(v, str) and v.strip() for v in proof["independent_reviews"]
                    )
                )
            ):
                errors.append(f"R0: incomplete closure proof for R0-F{count:03}")
        elif proof is not None:
            errors.append(f"R0: unverified closure attached to R0-F{count:03}")
    assignments_sha = hashlib.sha256(
        json.dumps(assignments, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()
    if assignments_sha != R0_ORIGIN_ASSIGNMENTS_SHA256:
        errors.append(
            "R0: finding to root-cause assignment changed without explicit reviewed policy"
        )
    # New user-discovered regressions are appended here; original 24 findings
    # remain immutable. Each follow-up must be source-anchored and assigned.
    followups = ledger.get("followups")
    if not isinstance(followups, list):
        errors.append("R0: follow-up regression ledger missing")
    else:
        for i, extra in enumerate(followups, 1):
            if (
                not isinstance(extra, dict)
                or extra.get("id") != f"R0-N{i:03}"
                or extra.get("workstream_id") not in group_ids
                or extra.get("state") not in {"open", "in_progress", "code_verified", "closed"}
                or not isinstance(extra.get("source"), str)
                or not extra["source"].strip()
                or not isinstance(extra.get("observed_failure"), str)
                or not extra["observed_failure"].strip()
                or not isinstance(extra.get("expected_effect"), str)
                or not extra["expected_effect"].strip()
                or extra.get("state") in {"code_verified", "closed"}
                and not isinstance(extra.get("closure"), dict)
            ):
                errors.append(f"R0: invalid appended regression R0-N{i:03}")
    if any(
        g.get("status") == "closed"
        and any(f["workstream_id"] == g["id"] and f["state"] != "closed" for f in findings)
        for g in groups
        if isinstance(g, dict)
    ):
        errors.append("R0: root-cause group closed with unresolved findings")
    return errors


def check(root: Path = ROOT) -> list[str]:
    """Return all structural violations without modifying repository data."""
    errors: list[str] = []
    agents = (root / "AGENTS.md").read_text(encoding="utf-8")
    roadmap = (root / "docs/architecture/functional-roadmap.md").read_text(encoding="utf-8")
    if len(agents.splitlines()) > 150:
        errors.append("AGENTS.md exceeds 150 lines: move detail into skills")
    if "odyssey-llm-stage" not in agents or "odyssey-generality" not in agents:
        errors.append("AGENTS.md lost required always-on skill routing")
    if len(roadmap.splitlines()) > 140:
        errors.append("active roadmap exceeds 140 lines: move history to archive")
    if "functional-roadmap-history-20261023.md" not in roadmap:
        errors.append("active roadmap is not linked to preserved historical evidence")
    if "not yet active in DEV/PROD" in agents:
        errors.append("AGENTS.md contains a superseded current-state claim")

    for skill in REQUIRED_SKILLS:
        path = root / ".codex/skills" / skill / "SKILL.md"
        if not path.is_file():
            errors.append(f"missing skill: {skill}")
            continue
        data = path.read_text(encoding="utf-8")
        match = re.match(
            r"\A---\nname: ([a-z][a-z0-9-]*)\ndescription: (.+?)\n---\n",
            data,
        )
        if not match or match.group(1) != skill or len(match.group(2)) < 25:
            errors.append(f"invalid skill frontmatter: {skill}")
        if len(data.strip().splitlines()) < 8:
            errors.append(f"missing workflow detail in skill: {skill}")
        metadata = path.parent / "agents/openai.yaml"
        if not metadata.is_file():
            errors.append(f"missing Codex skill metadata: {skill}")
        else:
            meta = metadata.read_text(encoding="utf-8")
            if ("$" + skill) not in meta or "\\$" in meta or "default_prompt:" not in meta:
                errors.append(f"invalid skill invocation metadata: {skill}")

    errors.extend(check_r0_findings(root))

    for relative in CHECK_LINKS:
        path = root / relative
        if path.is_file():
            errors.extend(check_markdown_links(path))
        else:
            errors.append(f"missing canonical doc: {relative}")
    map_path = root / "docs/architecture/instruction-map.md"
    if map_path.is_file():
        errors.extend(check_markdown_links(map_path))
    for name in REQUIRED_SKILLS:
        path = root / ".codex/skills" / name / "SKILL.md"
        if path.is_file():
            errors.extend(check_markdown_links(path))
    return sorted(set(errors))


def main() -> int:
    """Print a compact reproducible offline validation verdict."""
    problems = check()
    for problem in problems:
        print("FAIL", problem)
    if problems:
        return 1
    print(
        "ODYSSEY_DOCS_GUARD PASS",
        len(REQUIRED_SKILLS),
        "skills,",
        len(CHECK_LINKS),
        "canonical docs,",
        "short AGENTS and roadmap",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
