# Core Luna v3 focused diagnostic

One-shot two-case diagnostic authorized after the v3 global gate lost row detail.
It uses the unchanged Journal-converged GPT-5.6 Luna / low Core contract, zero retries,
and no vault mutation.

Retained result on `8a63bf8730ae6a7d2d3c3eda2d025c170ed05ec7`:
- 2 provider attempts / 2 completed responses / 0 retries.
- Standard estimated cost: `$0.0051432`.
- `SWF-MIXED-ORDER-01`: PASS.
- `SWR10-relational-target-two-bounded-references`: FAIL only on `both_references_bounded_to_event`.
- Each case is retained in a distinct JSON file plus a separate summary to prevent artifact collisions.

The SWR10 output preserved both full descriptive qualifiers but omitted the relationship/event
candidate bound on both reference lookup units. This remains blocking rather than a reviewed safe degradation.
