# Luna-first planner experiment

This frozen, non-production benchmark asks whether `gpt-5.6-luna` with `low` reasoning can safely
return the current Odyssey `RequestPlan`, request clarification, or explicitly escalate to the
established `gpt-5.6-sol` / `low` planner. The first diagnostic is Luna-only: an escalation is
recorded, never followed, and no returned action is executable here.

## Frozen boundary

- `teaching_examples.json` contains seven prompt examples and is not evaluation evidence.
- `cases.json` contains 24 held-out cases that are not present verbatim in the prompt.
- `oracle.json` contains one deterministic oracle per held-out case.
- `frozen_manifest.json` locks those inputs and the dated pricing evidence by SHA-256.
- `evaluate.py` classifies validated results without an LLM judge.
- `cost.py` keeps input, cached-input, cache-write, output, and reasoning counters separate. It
  returns cost as unavailable rather than inventing missing usage or pricing.

The benchmark's pricing authority is the repository's 2026-09-07 snapshot at
`benchmarks/phase20_answerer/pricing_snapshot.json`. Reasoning tokens remain visible but are already
included in billed output tokens. That snapshot contains no cache-write rate, so an observed
non-zero cache-write counter makes the corresponding estimate unavailable.

## Live runner (not authorized by this change)

The fixed output is gitignored at `benchmarks/.live-results/luna-first-planner.jsonl`; creation uses
exclusive mode and refuses overwrite. The runner accepts only frozen IDs, makes one Luna attempt per
selected case with `max_retries=0` and `max_output_tokens=2048`, retains bounded evidence, and has no
Sol or execution integration.

```bash
.venv/bin/python -m benchmarks.luna_first_planner.run_live \
  --confirm-live-provider-calls \
  --case-id HD01 \
  --case-id HO01
```

Do not run that command without separate human authorization for the exact live subset.
