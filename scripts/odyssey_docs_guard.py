"""Validate Odyssey's always-on instructions, skills and active documentation links.

This is a deterministic, offline check: no LLM calls, credentials, deployment
or private data inspection.
"""

from __future__ import annotations

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
