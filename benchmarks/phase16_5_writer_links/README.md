# Phase 16.5C focused writer evidence

This small benchmark checks the material writer-input change introduced by deterministic reference
rendering. It uses the already-selected `gpt-5.6-luna` / `medium` / `FULL_NOTE` configuration and
does not perform model selection.

The 2026-08-26 run made six production calls covering one bound APPEND, a bound employer REPLACE,
two different links, a repeated link, a preallocated same-request CREATE target, and a no-link
regression sentinel. All six returned valid bounded operations and passed review for exact target
and display-text preservation, no invented links, correct operation semantics, no whole-note
rewrite, and no unrelated content damage. Raw provider output is retained in the adjacent JSONL.
