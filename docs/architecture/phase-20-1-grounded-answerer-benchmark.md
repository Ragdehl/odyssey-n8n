# Phase 20.1 — Grounded answerer benchmark

Status: **20.1A offline contract/harness complete on merge; 20.1B live provider evidence pending**

## Objective

Select the smallest production answerer configuration that can turn Odyssey's bounded public retrieval evidence into a useful conversational response without inventing unsupported knowledge.

The answerer is not a retriever, planner, writer, or knowledge authority. It receives only the current user request plus the bounded public evidence already returned by Odyssey.

```text
user request
     +
public Odyssey evidence
     |
     v
bounded answerer
     |
     v
conversational response
```

## Architecture challenge

Result: **PROCEED**.

The problem is model/prompt selection over an already-defined consumer boundary. No production Core, runtime, n8n, persistence, retrieval, or schema change is required to measure it. The smallest reliable preparation is an isolated benchmark harness with frozen fixtures, a closed structured-output contract, deterministic local validation, and later focused live provider calls.

Reuse the existing Phase 17E answer-path patterns where useful, but do not couple Phase 20.1 to the old retrieval benchmark artifacts. Phase 20.1 starts from the product-facing evidence shape that Odyssey Online will actually supply.

The repository development pipeline normally prefers Codex for benchmark/harness work because local iteration is useful. While the Raspberry/Codex environment is unavailable, the bounded offline contract can be prepared through the GitHub-capable path and independently validated by CI. Live provider evidence remains a separate gate.

### 20.1A / 20.1B boundary

20.1A deliberately contains **no provider-calling entrypoint**. It freezes what a live adapter must send and how returned evidence will be validated, without adding network or credential handling merely to prepare the experiment.

```text
20.1A
  frozen cases
  + prompt/schema
  + provider-neutral request payload
  + response validation/oracles
  + usage/cost aggregation helpers
        |
        v
20.1B
  tiny provider adapter
  + exact model/reasoning profiles
  + resumable paid evidence
  + dated pricing snapshot
  + human semantic review
```

The first draft of 20.1A included a generic live CLI with caller-selected filesystem paths. Sonar security feedback correctly made that unnecessary surface visible. Rather than suppress the finding or add sanitization complexity to a phase that makes no calls, 20.1A removes the live adapter entirely. The provider adapter belongs to 20.1B, where its exact profiles, credentials environment, persistence behavior, and supported API options can be reviewed against the real runtime used for the paid evidence.

## Candidate strategy

Start with the cheapest realistic configuration of each selected candidate and increase effort only if the lower-cost configuration fails the grounding/quality gate.

Initial comparison:

- `gpt-5.6-luna` — preferred current cost-sensitive candidate;
- `gpt-5-nano` — materially cheaper alternative worth testing despite being an older/smaller model;
- `gpt-5.6-sol` — strong quality reference only, not an assumed production choice.

Do not add more models merely to produce a larger leaderboard. A near-price-equivalent model should be added only if the first inexpensive comparison exposes a concrete quality gap that needs another trade-off point.

Pin model IDs and reasoning effort explicitly in live artifacts. Provider pricing is volatile and must not become architecture truth: 20.1B records one dated pricing snapshot and source separately from token usage and uses that same frozen snapshot for all comparable rows in that evidence run.

## Input boundary

Each frozen case contains only data the standalone answerer is allowed to see:

```json
{
  "request": "¿Dónde trabaja Marta?",
  "status": "completed",
  "retrieval_query": "Dónde trabaja Marta",
  "items": [
    {
      "id": "marta-id",
      "type": "person",
      "path": "people/Marta.md",
      "content": "Marta trabaja en Thales."
    }
  ]
}
```

Each evidence item represents one canonical retrieved note with stable identity/path. A benchmark case must not manufacture several IDs for different fragments of the same canonical note.

The benchmark must never supply hidden planner reasoning, prompts from upstream models, Git details, pending-work records, operational traces, SQLite data, provider payloads, or filesystem access.

## Closed answer contract

The model returns a benchmark-only structured object:

```json
{
  "outcome": "ANSWER | INSUFFICIENT_EVIDENCE",
  "answer": "...",
  "supporting_item_ids": ["..."],
  "limitations": ["PARTIAL_RESULT"]
}
```

Rules:

- `ANSWER` requires at least one supplied supporting item;
- every supporting ID must come from the supplied evidence and be unique;
- `INSUFFICIENT_EVIDENCE` carries no supporting IDs and must not invent a factual answer;
- when Odyssey status is `partial`, include `PARTIAL_RESULT` in `limitations` whenever the benchmark oracle requires that incompleteness to remain visible;
- the answerer may paraphrase supplied evidence but may not add unsupported facts from model memory.

The support IDs and limitation flag are benchmark/server-side evidence. Phase 20 does not require exposing them in the browser UI.

## Frozen case families

The 12-case suite covers:

1. simple single-note answer;
2. multiple notes with irrelevant distractors;
3. synthesis across two distinct relevant canonical notes;
4. empty retrieval;
5. non-empty but insufficient evidence;
6. partial Odyssey result with usable evidence;
7. Spanish request;
8. French request;
9. exact names/domain terms that must be preserved;
10. missing fact where the model must refuse to invent;
11. a conjunctive/multi-condition question where all conditions must be grounded;
12. a misleading distractor containing plausible but wrong information.

Cases are deliberately small. This phase benchmarks answer formulation, not retrieval recall.

## Deterministic evaluation

The harness evaluates without asking another model to grade the answer.

For every live row it can check at least:

- structured-output validity;
- no unknown or duplicate supporting IDs;
- required supporting item coverage for answerable cases;
- correct `ANSWER` vs `INSUFFICIENT_EVIDENCE` outcome;
- required partial-status limitation;
- frozen required/forbidden answer fragments where an exact semantic sentinel is appropriate;
- input/output/reasoning token usage when supplied by the provider;
- latency supplied by the 20.1B adapter;
- estimated cost from a dated live pricing snapshot when all required usage/rate data is available.

Deterministic checks cannot prove that arbitrary prose contains no subtle unsupported implication. The final live evidence therefore also requires compact human semantic review of each failed/ambiguous row before model adoption. Do not introduce an LLM-as-judge merely for this small benchmark.

## Adoption gate

Prefer the cheapest candidate/configuration that satisfies all critical grounding sentinels and matches the required answer quality.

Critical failures include:

- invented answer when evidence is empty or insufficient;
- citing an evidence ID that was not supplied;
- omitting a required evidence item when the answer depends on it;
- stating a partial result as fully established when the incompleteness matters;
- materially wrong answer despite sufficient supplied evidence.

A more expensive model is not selected for stylistic preference alone. If Luna and the cheaper alternative both pass, choose using measured cost/latency and response usefulness. Sol is retained only if cheaper candidates fail material quality/grounding requirements.

## 20.1A — offline preparation acceptance

20.1A is ready for merge when:

- frozen cases cover the required families and preserve stable canonical note identity;
- answer schema and validator fail closed;
- benchmark prompt is explicit about supplied-evidence-only grounding;
- a provider-neutral request builder freezes the exact prompt/input/schema payload for each case without making a network call;
- stable hashes identify the exact cases plus prompt/schema and can later be combined with model/reasoning to identify live evidence;
- usage and cost helpers preserve unavailable metrics as unavailable rather than fabricating zeroes;
- deterministic tests cover schema, grounding, insufficiency, partial status, stable evidence identity, case loading, request construction, usage/cost, and aggregation;
- no provider call, credential handling, paid checkpoint writer, production prompt/model change, n8n change, or real-vault access is introduced.

## 20.1B — live evidence acceptance

Production adoption additionally requires:

- verify the current API-supported lowest reasoning effort for each candidate before paid execution;
- add the smallest provider adapter using only fixed benchmark files/locations and exact allowlisted benchmark profiles;
- resumable paid evidence must fail closed across model/reasoning/cases/prompt-schema mismatches;
- focused live runs for the exact candidate model/reasoning configurations;
- one dated official pricing snapshot used consistently for comparable cost calculation;
- all critical grounding sentinels pass;
- compact human review confirms no unsupported factual claims on accepted rows;
- quality, token usage, latency, and cost are compared transparently;
- one explicit production recommendation is recorded;
- any accepted production answer prompt/model configuration receives the focused live regression evidence required by `AGENTS.md`.

## Out of scope

- changing Odyssey retrieval strategy;
- adding the answerer to Core;
- deploying n8n answerer nodes;
- frontend implementation;
- Cloudflare/security changes;
- provider credentials in repository files;
- real-vault reads;
- LLM-as-judge infrastructure;
- chat history or conversational memory.

## Open decisions

- exact lowest supported reasoning effort for each live candidate, verified at live-run time against current provider documentation/API behavior;
- whether the materially cheaper alternative passes the grounding/quality gate;
- final production model/configuration;
- final dated pricing snapshot used for the live cost comparison.
