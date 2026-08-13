---
name: odyssey-post-merge
description: Safely synchronize the Odyssey repository and clean up only the confirmed merged feature branch after a pull request is merged. Use for requests such as "I merged the PR," "sync after merge," or "run Odyssey post-merge cleanup." Do not use to merge a PR or begin the next implementation phase.
---

# Odyssey Post-Merge

Synchronize `main` and remove only the branch proven to belong to the merged PR. Favor preserving branches whenever identity or merge status is uncertain.

## Workflow

1. Read `AGENTS.md` and inspect `git status --short --branch`, the current branch, its upstream, and repository remotes.
2. Identify the relevant PR from the user's PR number, the current feature branch, or recent merged PR history. Record the feature branch before switching away from it.
3. Query GitHub for the PR state, base branch, head branch, and merge commit. Continue cleanup only when the PR state is conclusively merged and the head branch exactly matches the identified feature branch.
4. Stop before switching or deleting if the working tree is not clean. Report the files that prevent safe synchronization without discarding them.
5. Switch to `main`, fetch and prune `origin`, and fast-forward with `git merge --ff-only origin/main`. Never create a merge commit for synchronization.
6. Verify local `main` and `origin/main` resolve to the same commit and the working tree remains clean.
7. Before deletion, state the exact confirmed feature branch and why it is safe to remove. Never delete `main`, an unmerged branch, an unrelated branch, or any branch whose PR identity or merge state is uncertain.
8. Delete the local feature branch with the safe branch-delete operation. Delete the same remote branch only if it still exists and GitHub confirmed its PR was merged. Treat an already absent remote branch as success.
9. Recheck the current branch, ref equality, branch presence, and working-tree state. Do not start another phase or implementation task.

## Report

Report the merged PR number, current branch, whether `main` is synchronized, whether the local feature branch was removed, whether the remote feature branch was removed or already absent, whether the working tree is clean, and any blocker.
