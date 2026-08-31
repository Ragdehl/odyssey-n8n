# Phase 17E retrieval-unit benchmark

This is evidence-only. It does not modify `ContextIndex`, production Top-K, persistence, write
authority, or the canonical vault. Run it from the repository root with the already configured
local runtime:

```bash
./.venv/bin/python -m benchmarks.phase17e_retrieval.benchmark \
  > /data/odyssey/runtime/phase17e-retrieval/results.json
```

Use the previously selected offline artifact explicitly for the scale run:

```bash
./.venv/bin/python -m benchmarks.phase17e_retrieval.benchmark \
  --cache-dir /data/odyssey/runtime/phase11a-benchmark/embedding-cache \
  --scale-size 1000
```

The benchmark uses the canonical schema and one frozen synthetic corpus in `cases.json`. The
corpus deliberately contains long heterogeneous notes, short controls, Spanish and French
queries, contextual/entity-disambiguation queries, exact-fact queries, and reusable identity
patterns from earlier retrieval work. No live personal vault data is read.

## Retrieval projections

Whole-note is exactly the current production projection: `build_context_retrieval_text(note, path)`.
It includes `Name`, aliases, `Type`, tags, non-technical metadata, and the humanized Markdown body.

Fact-level parses the existing Odyssey-owned atomic-fact markers and embeds one unit per fact:

```text
Name: Marta
Type: person
Fact: Trabaja en Thales.
```

This preserves attribution while avoiding a naked fact. The unit's entity ID and exact fact text
are retained only for evaluation/reporting; they are not appended to the embedding text.

Combined is intentionally small: it embeds both whole-note and identity-preserving fact units,
then adds reciprocal-rank evidence (`1 / (60 + rank)`) from the whole-note rank and the fact-unit
rank. There is no generic reranker or learned fusion.

For every strategy, Top-K is reported twice where facts are involved: raw retrieved units and
unique entities. ANY- and ALL-required-fact evidence is reported only for cases with a fact oracle. Payload
tokens are an approximate `characters / 4` planning measure, not a provider tokenizer count.
Vector bytes are the float32 payload only; SQLite/index metadata and model artifacts are reported
separately when real evidence is available.

The real run requires the existing Odyssey MiniLM artifact because the production adapter is
offline-only. The prior Odyssey artifact is expected at
`/data/odyssey/runtime/phase11a-benchmark/embedding-cache`; `--cache-dir` makes discovery explicit.
If it is unavailable, the runner fails explicitly; deterministic tests use a fake embedder and are
not model evidence.

`run_planner_live.py` uses the current production `OpenAIRequestPlanner` boundary with
`gpt-5.6-sol` and low reasoning. It writes raw JSONL evidence to a caller-selected path and applies
only a tolerant, human-readable rubric; it does not change the production prompt.
