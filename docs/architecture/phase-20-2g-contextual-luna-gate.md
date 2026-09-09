# Phase 20.2G — contextual reasoner Luna replacement gate

Status: **full live evidence passed safety review; Luna/medium adoption staged in PR #102, not deployed**.

## Objective

Test whether `gpt-5.6-luna` can safely replace the remaining production `gpt-5.6-sol` contextual
entity reasoner without changing the established contextual-resolution prompt, candidate evidence,
Structured Outputs contract, or reasoning effort.

The comparison changes only the model:

```text
current deployed production:  Sol / medium
staged candidate:              Luna / medium
```

Reasoning effort remains `medium` so the evidence isolates the model change rather than a simultaneous
model-and-reasoning change.

## Historical reason for the gate

Phase 11B.1b selected Sol/medium because Luna/medium produced one clear false `RESOLVED` decision on
the frozen 90-case few-shot benchmark. In A19, the generic reference `the work project` had no Atlas,
Mercury, Delta, city, or colleague evidence, but Luna resolved it to Atlas. The frozen expected result
is `AMBIGUOUS`. Sol returned the safe frozen result and passed the historical safety gate.

This phase does not reinterpret that historical failure. A19 remains mandatory regression evidence.

## Initial bounded live gate

The authorized eight-case Luna/medium gate completed exactly once per case with zero retries and zero
invalid outputs.

| Case | Result | Expected | Review |
| --- | --- | --- | --- |
| A02 | `RESOLVED`, `xavi-pujol` | `RESOLVED`, `xavi-pujol` | correct |
| A09 | `RESOLVED`, `delta` | `RESOLVED`, `delta` | correct |
| A11 | `RESOLVED`, `carrefour-balma` | `RESOLVED`, `carrefour-balma` | correct |
| A19 | `AMBIGUOUS`, `null` | `AMBIGUOUS`, `null` | historical false-resolution sentinel passed |
| A22 | `UNRESOLVED`, `null` | `AMBIGUOUS`, `null` | conservative abstention |
| A28 | `AMBIGUOUS`, `null` | `AMBIGUOUS`, `null` | correct |
| A31 | `UNRESOLVED`, `null` | `UNRESOLVED`, `null` | correct |
| A34 | `UNRESOLVED`, `null` | `UNRESOLVED`, `null` | correct |

Aggregate usage was 22,142 input tokens, 0 cached input tokens, 612 output tokens, and 412 reasoning
tokens. Estimated cost was `$0.005163`. The 7/8 result had zero clear false `RESOLVED` and zero
invalid outputs, but adoption remained blocked for review.

## Prompt-parity correction

Review after the mini-gate found that production composition had constructed the contextual reasoner
without the ten labelled calibration turns, while the benchmark supplied them. This was configuration
drift against ADR 0003's selected Sol/medium few-shot contract and ADR 0004's production-parity
checkpoint.

The canonical ordered examples now live in `config/contextual-calibration.json`, are loaded by
`odyssey_core` for production, and are consumed by the benchmark adapter. Production does not import
from `benchmarks/`. The `ODYSSEY_CONTEXTUAL_MODEL` override remains supported.

A22's frozen candidate evidence contains all three plausible exact Carrefour entities:
`carrefour-balma`, `carrefour-labege`, and `carrefour-market-capitole`, plus two lower-plausibility
stores. Its initial `UNRESOLVED` Luna result was conservative abstention, not missing candidate
evidence. Current write-target semantics already treat ambiguous exact evidence as clarification even
when contextual output is `UNRESOLVED`; the distinction remained material for benchmark quality and
was not relaxed or converted into a Carrefour-specific rule.

## Authorized five-case follow-up

The separately authorized five-case Luna/medium follow-up used the canonical ten-example
configuration and made 5 Luna calls, 0 retries, 0 Sol calls, with 0 invalid outputs and 0 clear false
`RESOLVED` decisions.

| Case | Result | Frozen expected | Review |
| --- | --- | --- | --- |
| A22 | `UNRESOLVED`, `null` | `AMBIGUOUS`, `null` | same conservative abstention as the first gate |
| A19 | `AMBIGUOUS`, `null` | `AMBIGUOUS`, `null` | historical sentinel passed |
| A28 | `AMBIGUOUS`, `null` | `AMBIGUOUS`, `null` | correct |
| A31 | `UNRESOLVED`, `null` | `UNRESOLVED`, `null` | correct |
| A02 | `RESOLVED`, `xavi-pujol` | `RESOLVED`, `xavi-pujol` | correct |

The follow-up scored 4/5 solely because A22 again returned `UNRESOLVED`. Aggregate usage was 13,819
input tokens, 0 cached input tokens, 530 output tokens, and 402 reasoning tokens; estimated cost was
`$0.0034`. The repeated conservative distinction motivated the complete frozen benchmark instead of
further tiny samples.

## Full 90-case Luna/medium benchmark

The complete frozen 90-case benchmark made exactly 90 Luna/medium provider calls, with zero retries,
zero invalid outputs, and no Sol fallback. Every case row was atomically retained. The runner's final
aggregation initially encountered an omitted optional `cache_write_tokens` field after the last
provider response; this was corrected deterministically to treat that optional counter as zero without
changing retained model evidence.

| Expected outcome | Correct | Total | Accuracy |
| --- | ---: | ---: | ---: |
| `RESOLVED` | 35 | 35 | 100.00% |
| `AMBIGUOUS` | 27 | 29 | 93.10% |
| `UNRESOLVED` | 26 | 26 | 100.00% |
| **Overall** | **88** | **90** | **97.78%** |

There were no clear false `RESOLVED` decisions and no invalid/malformed outputs. The two frozen-label
misses were:

- `en-project-generic`: conservative `AMBIGUOUS` -> `UNRESOLVED`;
- `en-toulouse-supermarket` (E13): `RESOLVED` to `carrefour-market-capitole`, retained as the
  historically disputed label rather than a clear safety failure.

Mandatory sentinels were safe: A19 returned `AMBIGUOUS / null`, and A22 returned `AMBIGUOUS / null`
in this full run. E13 remained `RESOLVED / carrefour-market-capitole` with its disputed status.

Measured usage was 250,707 input tokens, including 13,804 cached input tokens, 0 supplied cache-write
tokens, 4,347 output tokens, and 2,088 reasoning tokens. The repository pricing method estimated
`$0.052873` for this run.

Historical few-shot Luna was 86/90 (95.56%) with one clear false `RESOLVED`; historical Sol/medium was
89/90 (98.89%) with zero clear false `RESOLVED` and only disputed E13. The current Luna result is one
frozen-label point below Sol, but its sole non-disputed miss is conservative and it achieved 35/35
correct `RESOLVED` decisions with zero clear false resolutions.

This full run produced no error cluster requiring a prompt change. The existing canonical prompt is
therefore retained unchanged.

## Adoption decision

The full evidence supports Luna/medium as the contextual production default:

- 35/35 correct `RESOLVED` decisions;
- zero clear false `RESOLVED`;
- zero invalid outputs;
- A19 historical safety failure fixed;
- A22 correct in the complete run;
- 88/90 frozen-label accuracy versus historical Sol 89/90;
- the only non-disputed miss is conservative abstention;
- measured 90-case Luna cost was `$0.052873`.

PR #102 therefore stages the runtime default change from `gpt-5.6-sol` to `gpt-5.6-luna`, keeping
`reasoning_effort="medium"`, the same canonical ten-example few-shot prefix, strict output contract,
zero automatic retries, and `ODYSSEY_CONTEXTUAL_MODEL` override support. This branch change is not yet
merged or deployed; the currently running production runtime remains Sol/medium until the separate
human-controlled merge/deployment steps occur.

## Architecture challenge

Result: **PROCEED**.

No new architecture is needed. The existing contextual reasoner boundary, canonical calibration
configuration, provider adapter, deterministic validation, and benchmark corpus provide the required
mechanics. Do not add a router, second provider abstraction, prompt fork, fallback chain, or service for
this adoption.

## Out of scope

- lowering contextual reasoning from medium to low;
- changing the contextual prompt, calibration examples, candidate evidence, or schema;
- changing the Luna-first request planner or grounded answerer;
- real-vault writes or identity mutations;
- Phase 20.3 Cloudflare/security work.

## Next decision

Review PR #102 after deterministic CI/Sonar on the staged Luna default. If clean, human merge remains
the next gate. Deployment to the Raspberry and one bounded production contextual smoke are separate
actions after merge. Lower reasoning effort, if desired, requires separate evidence rather than being
bundled into this model replacement.
