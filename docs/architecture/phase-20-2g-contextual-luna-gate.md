# Phase 20.2G — contextual reasoner Luna replacement gate

Status: **live gate completed; prompt/configuration parity correction in progress; adoption blocked**.

## Objective

Test whether `gpt-5.6-luna` can safely replace the remaining production `gpt-5.6-sol` contextual
entity reasoner without changing the established contextual-resolution prompt, candidate evidence,
Structured Outputs contract, or reasoning effort.

The first comparison changes only the model:

```text
current production:  Sol / medium
candidate:           Luna / medium
```

Reasoning effort remains `medium` so a failure or improvement can be attributed to the model change
rather than a simultaneous model-and-reasoning change.

## Historical reason for the gate

Phase 11B.1b selected Sol/medium because Luna/medium produced one clear false `RESOLVED` decision on
the frozen 90-case few-shot benchmark. In A19, the generic reference `the work project` had no Atlas,
Mercury, Delta, city, or colleague evidence, but Luna resolved it to Atlas. The frozen expected result
is `AMBIGUOUS`. Sol returned the safe frozen result and passed the historical safety gate.

This phase does not reinterpret that historical failure. A19 is mandatory regression evidence.

## Bounded live gate

Run exactly eight synthetic cases using the unchanged frozen ten-example few-shot production prompt:

| Case | Expected | Purpose |
| --- | --- | --- |
| A02 | RESOLVED `xavi-pujol` | positive person resolution, English |
| A09 | RESOLVED `delta` | positive project resolution, Spanish |
| A11 | RESOLVED `carrefour-balma` | positive store resolution, French |
| A19 | AMBIGUOUS | mandatory historical Luna false-resolution regression |
| A22 | AMBIGUOUS | ambiguous store, Spanish |
| A28 | AMBIGUOUS | ambiguous project, French |
| A31 | UNRESOLVED | absent project, English |
| A34 | UNRESOLVED | absent person, Spanish |

The runner is `benchmarks/run_contextual_luna_mini_gate.py`.

## Live gate result

The authorized eight-case Luna/medium gate completed exactly once per case. It made 8 provider
calls, with zero retries and zero invalid outputs. The bounded evidence is retained in the
gitignored `benchmarks/.live-results/contextual-luna-mini-gate-20.2g.json` artifact; it contains
only normalized decisions, response IDs, usage counters, and scoring metadata.

| Case | Result | Expected | Review |
| --- | --- | --- | --- |
| A02 | `RESOLVED`, `xavi-pujol` | `RESOLVED`, `xavi-pujol` | correct |
| A09 | `RESOLVED`, `delta` | `RESOLVED`, `delta` | correct |
| A11 | `RESOLVED`, `carrefour-balma` | `RESOLVED`, `carrefour-balma` | correct |
| A19 | `AMBIGUOUS`, `null` | `AMBIGUOUS`, `null` | historical false-resolution sentinel passed |
| A22 | `UNRESOLVED`, `null` | `AMBIGUOUS`, `null` | conservative abstention; adoption blocked |
| A28 | `AMBIGUOUS`, `null` | `AMBIGUOUS`, `null` | correct |
| A31 | `UNRESOLVED`, `null` | `UNRESOLVED`, `null` | correct |
| A34 | `UNRESOLVED`, `null` | `UNRESOLVED`, `null` | correct |

Aggregate usage was 22,142 input tokens, 0 cached input tokens, 612 output tokens, and 412
reasoning tokens. The runner estimated `$0.005163` using the dated repository pricing snapshot.
The gate scored 7/8: clear false `RESOLVED` = 0, invalid = 0, and A19 safe, but A22's
`UNRESOLVED` versus frozen `AMBIGUOUS` label is a conservative distinction that must not be
silently relaxed. Production remains `gpt-5.6-sol` / medium; no adoption change was made.

## Prompt-parity follow-up

Review after the mini-gate found that production composition had constructed the contextual
reasoner without the ten labelled calibration turns, while the benchmark supplied them. This was
configuration drift against ADR 0003's selected Sol/medium few-shot contract and ADR 0004's
production-parity checkpoint. The canonical ordered examples now live in
`config/contextual-calibration.json`, are loaded by `odyssey_core` for production, and are consumed
by the benchmark adapter; production does not import from `benchmarks/`. The production default
remains Sol/medium and the `ODYSSEY_CONTEXTUAL_MODEL` override remains supported.

A22's frozen candidate evidence contains all three plausible exact Carrefour entities:
`carrefour-balma`, `carrefour-labege`, and `carrefour-market-capitole`, plus two lower-plausibility
stores. Its `UNRESOLVED` Luna result was therefore a conservative abstention, not evidence that
the candidate set was incomplete. Current write-target semantics already treat ambiguous exact
evidence as clarification even when contextual output is `UNRESOLVED`; the distinction remains
material for the benchmark and is not relaxed or converted into a Carrefour-specific rule.

After deterministic parity verification, the smallest proposed follow-up is five new Luna/medium
calls using frozen cases `A22`, `A19`, `A28`, `A31`, and `A02` (collision, historical ambiguity,
another ambiguity, unresolved, and positive resolution). No provider calls are authorized by this
follow-up preparation. At the previous gate's observed token envelope, the conservative no-cache
planning estimate is approximately `$0.004` for five calls; production adoption remains blocked
until this separate gate is explicitly authorized and passes.

## Acceptance criteria

1. Exactly 8 Luna provider calls, one per frozen case.
2. Model is `gpt-5.6-luna`; reasoning effort is `medium`.
3. The frozen ten-example few-shot prompt and existing provider contract are reused unchanged.
4. Automatic/application retries are zero.
5. All outputs pass existing deterministic contextual-decision validation.
6. Clear false `RESOLVED` count is zero.
7. All three positive resolution cases select the correct supplied candidate.
8. All eight frozen labels are correct.
9. A19 specifically returns `AMBIGUOUS` with `id = null`.
10. No Odyssey action, real-vault mutation, deployment, or production model change occurs during the benchmark.

If Luna misses only by a conservative abstention (`AMBIGUOUS` versus `UNRESOLVED`, or vice versa), do
not silently weaken the gate. Review the case against current production semantics before deciding
whether any adoption evidence is sufficient.

## Architecture challenge

Result: **PROCEED**.

No new architecture is needed. The existing contextual reasoner boundary, frozen benchmark corpus,
provider adapter, deterministic validation, and historical runner already provide the required
mechanics. The new runner is only a bounded selector/scorer around those existing assets. Do not add
a router, second provider abstraction, new prompt, fallback chain, or service for this experiment.

## Out of scope

- changing the production contextual model before the live gate passes;
- changing contextual reasoning from medium to low;
- changing the contextual prompt, calibration examples, candidate evidence, or schema;
- rerunning the full historical 90-case benchmark by default;
- changing the Luna-first request planner or grounded answerer;
- real-vault writes or identity mutations;
- Phase 20.3 Cloudflare/security work.

## Next decision

If the eight-case Luna/medium gate passes, review the retained evidence and then make the smallest
separate production adoption change: switch the runtime contextual model default from Sol to Luna,
run deterministic CI, deploy, and perform one bounded production smoke that naturally exercises
contextual resolution. Lower reasoning effort, if desired, requires its own later evidence rather
than being bundled into the model replacement.
