# Phase 14 v3 targeted stability experiment: S04 / B05

Status: **blocked by provider transport failures**. The frozen benchmark and
evaluator were unchanged. The experiment appended all requested attempts, but
no new model output was received, so a four-repetition quality matrix cannot be
calculated.

## Baseline verified before execution

- HEAD: `d0ee9a07da48defa90de17f294d0200c333cd843`
- Terra repetition 1: S04 PASS; B05 CRITICAL, covering only 1990 and omitting
  the 2000 branch.
- Sol repetition 1: S04 CRITICAL because the query was empty and local
  RequestPlan validation rejected it; B05 PASS with separate 1990 and 2000
  branches.
- Existing evidence: 24 Terra and 24 Sol repetition-1 records.
- No S04/B05 repetitions 2–4 existed before execution.
- Metadata artifact hashes matched the frozen files; the worktree was clean.

## Targeted attempts

The existing runner was invoked exactly for S04 and B05, repetitions 2–4, at
low effort, first for Terra and then for Sol. Each of the 12 logical requests
received an initial attempt and an explicit transport-only retry. All 24 new
records reported `failure_kind: transport` and `provider_error: Connection
error.` No raw model output, usage counters, or estimated cost was returned.

| Model | Case | Rep 1 | Rep 2 | Rep 3 | Rep 4 | PASS count |
|---|---|---|---|---|---|---|
| Terra | S04 | PASS | transport | transport | transport | 1/4* |
| Terra | B05 | CRITICAL | transport | transport | transport | 0/4* |
| Sol | S04 | CRITICAL | transport | transport | transport | 0/4* |
| Sol | B05 | PASS | transport | transport | transport | 1/4* |

`*` These counts are not stability results: repetitions 2–4 have no quality
observation. Transport failures are not model-quality evidence.

## B05 analysis

The frozen evaluator requires both half-open regions:

- 1990: `birth_date >= 1990-01-01` and `< 1991-01-01`
- 2000: `birth_date >= 2000-01-01` and `< 2001-01-01`

New coverage success: Terra unavailable (0/3 observed); Sol unavailable (0/3
observed). The only available Terra observation drops the 2000 branch; the
only available Sol observation covers both. Reproducibility cannot be decided.

## S04 analysis

The deterministic requirement is `aliases contains "Ody"` plus a non-empty
retrieval query. New valid-plan success: Terra unavailable (0/3 observed); Sol
unavailable (0/3 observed). Sol's repetition-1 empty-query failure remains
automatically detectable by local validation. Reproducibility cannot be
decided.

## Failure severity

The baseline Terra B05 issue is a silent valid-but-wrong plan: it can execute
while losing the 2000 candidate region. The baseline Sol S04 issue is an
invalid plan rejected locally, so Core detects it before retrieval. The new
transport failures are provider failures, not either model-quality category.
The silent B05 recall loss is therefore the more dangerous observed failure
mode, but this targeted run provides no evidence about its stability.

## Cost and cache

| Metric | New Terra | New Sol |
|---|---:|---:|
| Logical requests | 6 | 6 |
| API attempts | 12 | 12 |
| Cache writes / tokens | 0 / unavailable | 0 / unavailable |
| Cache reads / cached-input tokens | 0 / unavailable | 0 / unavailable |
| Ordinary input tokens | unavailable | unavailable |
| Output tokens | unavailable | unavailable |
| Reasoning tokens | unavailable | unavailable |
| Estimated cost | unavailable | unavailable |
| Mean / median latency | transport-only; not quality latency | transport-only; not quality latency |

The original v3 stages recorded $0.060691 Terra and $0.138511 Sol. Therefore
the cumulative v3 spend is $0.060691 Terra + $0.138511 Sol = **$0.199202**,
excluding the failed new attempts because the provider returned no usage or
cost counters. The new attempt records preserve the absence of counters; no
cache behavior is inferred.

## Decision analysis

Questions about reproducibility, deterministic-safety ranking, stochastic
versus systematic behavior, and Sol's price/quality trade-off remain
unresolved because all new observations were transport failures. The baseline
suggests Terra has a dangerous silent deterministic-OR failure, while Sol's
baseline failure is locally detectable. A simple empty-query safeguard is
realistically useful and deterministic; generically proving that an arbitrary
plan covers every semantic OR branch is materially harder. No second semantic
planner is proposed.

### Future cost optimization

If production evidence later shows Sol is materially safer but more expensive,
Odyssey could evaluate a cheap/local routing layer: simple semantic retrieval,
one-field deterministic filters, and simple create intents could go to Terra;
multiple independent branches, disjoint deterministic OR ranges, and complex
mixed constraints could go to Sol. Possible implementations include
deterministic heuristics, a small local classifier, or an already-available
local embedding/classification component. This is **not part of Phase 14**:
do not add LangGraph/router infrastructure or another LLM call now, and do not
optimize before observing real production request distribution and cost. If Sol
remains only roughly 2–3× Terra at fractions-of-a-cent-per-request scale,
routing complexity may not be justified.

## Scope confirmation

- Frozen benchmark artifacts, evaluator semantics, RequestPlan contract,
  context, cache key, and historical summaries were not modified.
- Production code and `note-schema.json` were not modified.
- No merge was performed.
