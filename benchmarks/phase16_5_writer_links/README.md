# Phase 16.5C focused writer evidence

This small benchmark checks the material writer-input change introduced by deterministic reference
rendering. It uses the already-selected `gpt-5.6-luna` / `medium` / `FULL_NOTE` configuration and
does not perform model selection.

The first 2026-08-26 run made six production calls covering one bound APPEND, a bound employer
REPLACE, two different links, a repeated link, a preallocated same-request CREATE target, and a
no-link regression sentinel. All six returned valid bounded operations and passed review for exact
target/display preservation, no invented links, correct bounded semantics, no whole-note rewrite,
and no unrelated content damage.

That first run retained provider operations but did **not** retain its complete request inputs. The
review therefore must not present that historical JSONL as fully reproducible evidence. `cases.json`
now freezes six explicit production-shaped requests and `run_benchmark.py` executes those exact cases
through the real `OpenAILunaWriter`, retaining each exact request, raw provider output, rendered body,
and deterministic validation result. Future live regression evidence should use this runner.

Run from the repository root with an `OPENAI_API_KEY` available:

```bash
python benchmarks/phase16_5_writer_links/run_benchmark.py
```

The runner creates a timestamped directory under `results/`, uses `store:false` through the production
writer boundary, performs no model selection, and exits non-zero if any case fails deterministic
writer/link validation.
