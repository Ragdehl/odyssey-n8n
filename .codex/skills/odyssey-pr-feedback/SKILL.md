---
name: odyssey-pr-feedback
description: Inspect and address review feedback on an existing Odyssey pull request while preserving its branch and approved architecture. Use for requests such as "review the PR comments," "address feedback on PR #X," or "continue the PR after my GitHub review." Do not use to create a replacement PR or merge one.
---

# Odyssey PR Feedback

Process all available review surfaces before editing, keep changes traceable to feedback, and stop for material ambiguity.

## Workflow

1. Read `AGENTS.md` and architecture relevant to the change. Inspect the current branch, working tree, upstream, and diff.
2. Resolve the repository and target PR. Confirm the local feature branch matches the PR head before editing or pushing.
3. Read PR metadata, the current PR diff, general comments, submitted reviews, inline comments, and review threads. Use a thread-aware GitHub read when unresolved, resolved, or outdated state matters.
4. Group feedback into:
   - straightforward actionable changes;
   - informational comments;
   - already addressed, resolved, or outdated comments;
   - ambiguous, conflicting, or material architecture/product/schema decisions.
5. Apply straightforward in-scope changes autonomously. Stop and ask the user when comments conflict, contradict approved architecture, or require a material decision. Do not broaden the phase or change unrelated files.
6. Keep work on the existing PR branch. Run `$odyssey-verify-change`, selecting checks relevant to the modified components.
7. Re-read review threads after implementation to detect new feedback and map each change to its thread or feedback cluster.
8. If verification passes, update status documentation when appropriate, commit with a sensible message, and push to the same branch so the existing PR updates.
9. Do not create a replacement PR, merge the PR, or resolve/reply to review threads unless the user explicitly requests it or project rules clearly authorize it.

## Report

Report feedback threads inspected, threads addressed, threads intentionally left open with reasons, files changed, tests and results, commit hash, whether the existing PR was updated, and any blocker.
