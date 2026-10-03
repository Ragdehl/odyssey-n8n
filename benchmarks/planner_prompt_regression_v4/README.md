# Core planner prompt regression v4 — focused successor

This gate closes the only still-relevant uncertainty from v3 without rerunning unrelated model
selection. The v3 global run already exercised the full 16-case GPT-5.6 Luna / low matrix under the
current Journal-converged Core contract. Its failures were the three event-like `journal_entry`
fixtures (SWR07/SWR08/SWR10) plus `SWF-MIXED-ORDER-01`; the later focused diagnostic passed
`SWF-MIXED-ORDER-01` under the unchanged contract.

The old “cena relacional de prueba” fixtures are not current product requirements: they represented
an event-like source as `journal_entry`, a legacy shape that new writes must not create. v4 therefore
runs only the three separately versioned current-schema successors using the canonical `document`
source `Directorio Faro`. Nothing else in the previously exercised matrix is rerun.

The ordinary Core prompt, provider schema, teaching examples, production model, and reasoning
effort are exactly the v3 candidate contract. All three successor cases must pass; there are no
accepted failures in this focused gate. Provider authority is zero unless the exact matrix,
contract hashes, clean worktree, bounded cost, and explicit authorization flag all match. The gate
is one-shot, zero-retry, and has no vault mutation authority.
