# Phase 20.2G — contextual reasoner Luna replacement gate

Status: **benchmark preparation; live evidence not yet run**.

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
