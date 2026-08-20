# Phase 14 retrieval-plan model benchmark

This experiment chooses the cheapest OpenAI model/reasoning configuration that preserves retrieval recall safely. It does not implement the production Phase 14 interpreter and does not modify Phase 13 retrieval behavior.

```text
prompt.md + schema_contract.json + one cases.json request
                         |
                         v
               OpenAI Responses API
              strict Structured Output
                         |
                         v
                 local plan validation
                         |
                         v
        locked oracle.json deterministic evaluation
                         |
                         v
        raw results + evaluation + decision summary
```

## Frozen inputs

- `prompt.md` is the actual long, production-like common prompt sent byte-for-byte for every request.
- `cases.json` contains T01-T45 separately and fixes `2026-08-20 10:30 Europe/Madrid`; machine time is never used for request interpretation.
- `oracle.json` contains semantic retrieval invariants and was locked before model calls.
- `schema_contract.json` is a projection of the canonical repository schema. The runner and evaluator stop if `config/note-schema.json` no longer projects to the same contract.
- `pricing.json` records official OpenAI model-page rates and retrieval date. Prices are estimates from API token counters, not invoice data.
- `proposed_production_prompt.md` is a shorter draft for later human review. It is never used by this benchmark.

The oracle evaluates effective retrieval behavior. Equivalent top-level/type-filter and required-tags/tags-filter representations are accepted. Unexpected hard filters, lost semantic entities, wrong date fields or bounds, narrowed type sets, and invalid plans are critical. Missing safe deterministic constraints or silently lost structural limitations are major. Harmless reporting differences are minor.

## Setup and security

Use Python 3.13 and install the official SDK in an isolated environment:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r benchmarks/phase14_retrieval_plan/requirements.txt
```

The live runner reads the key only from `OPENAI_API_KEY`. It never prints or stores the key, sends `store: false`, sanitizes key-shaped strings from errors, and preserves no `.env` file.

## Reproduce the staged run

Run the cost-conscious initial matrix. Each T01-T45 case is one independent API request; no case ID, oracle, other question, or prior answer is sent to the model.

```bash
export OPENAI_API_KEY='<set outside the repository>'
.venv/bin/python benchmarks/phase14_retrieval_plan/run_benchmark.py \
  --run-id 20260820T_PHASE14_INITIAL \
  --configuration gpt-5.6-luna:none \
  --configuration gpt-5.6-luna:low \
  --configuration gpt-5.6-terra:low \
  --configuration gpt-5.6-sol:low

.venv/bin/python benchmarks/phase14_retrieval_plan/evaluate.py \
  benchmarks/phase14_retrieval_plan/results/20260820T_PHASE14_INITIAL
```

The model IDs are exact and are never substituted. Official model documentation retrieved on 2026-08-20 states that Luna, Terra, and Sol support the Responses API, Structured Outputs, prompt caching, and reasoning efforts `none`, `low`, `medium`, `high`, `xhigh`, and `max`:

- <https://developers.openai.com/api/docs/models/gpt-5.6-luna>
- <https://developers.openai.com/api/docs/models/gpt-5.6-terra>
- <https://developers.openai.com/api/docs/models/gpt-5.6-sol>
- <https://developers.openai.com/api/docs/guides/structured-outputs>

The runner is resumable. Existing logical requests are skipped; failures remain explicit and can be intentionally retried with `--retry-failures`. It refuses to reuse a run ID if any prompt, case, oracle, contract, or pricing input changed.

After the first evaluation, select every critical, major, borderline, or materially divergent case. Target at least four total repetitions (the initial response plus three reruns) for the leading cheap candidate and Sol quality reference:

```bash
.venv/bin/python benchmarks/phase14_retrieval_plan/run_benchmark.py \
  --run-id 20260820T_PHASE14_INITIAL \
  --configuration gpt-5.6-luna:none \
  --configuration gpt-5.6-sol:low \
  --repetitions 4 \
  --case-id T03 \
  --case-id T10

.venv/bin/python benchmarks/phase14_retrieval_plan/evaluate.py \
  benchmarks/phase14_retrieval_plan/results/20260820T_PHASE14_INITIAL \
  --replace-derived
```

Replace the example case IDs with the actual deterministic selection from the initial comparison. If quality requires further differentiation, start a new immutable run for Terra none/medium or Sol medium and document why the extra spend is warranted.

## Verification

The evaluator has native pytest tests. Standard project checks are:

```bash
ruff format --check benchmarks/phase14_retrieval_plan tests/benchmarks
ruff check benchmarks/phase14_retrieval_plan tests/benchmarks
pytest tests/benchmarks/test_phase14_retrieval_plan.py
```

Result directories contain immutable metadata and append-only raw JSONL. `evaluation.json` and `summary.md` are derived and may be intentionally regenerated after a resumed run with `--replace-derived`.
