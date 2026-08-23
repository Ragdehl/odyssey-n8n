# Phase 15.3 acceptance review

This is a derived human adjudication of append-only evidence. It does not replace or alter the strict
oracle, metadata, raw model outputs, provider usage, or historical classifications.

## Decision

- Strict latest full-run score: **16/18 PASS**.
- Semantic acceptance: **18/18 core behaviors acceptable**, with two recorded precision limitations.
- Accepted boundary: generic delegation preserves safely representable Odyssey selection; concrete
  application choice and execution remain deferred.

The accepted full evidence is
`results/phase15-3-sol-low-20260824-selection-operation/`. Its A07 and A08 rows strictly fail because
the canonical `person` narrowing hint is absent from `link_scope.anchor.type`. The raw rows retain the
classification produced by the evaluator at execution time; the 16/18 score is the offline result from
the subsequently hardened strict evaluator.

| Case | Preserved core behavior | Strict difference | Adjudication |
|---|---|---|---|
| A07 | RetrieveAction; outer selection; Marta anchor; `both`; depth 1 | optional anchor type is null | ACCEPT_WITH_LIMITATION |
| A08 | DelegateAction; delegated selection; Marta anchor; `both`; depth 1 | optional anchor type is null | ACCEPT_WITH_LIMITATION |

`NoteSelector.type` is nullable. Without it, exact lookup may consider same-name notes across canonical
types, increasing ambiguity and work. The exact resolver keeps all such candidates and returns an
ambiguous result rather than choosing arbitrarily. Supplying `type=person` would narrow that search but
would not distinguish two different person notes both named Marta.

## Evidence history

- `results/phase15-3-sol-low-20260824/`: initial interrupted/invalid evidence; A07/A08 also lost
  `link_scope`; duplicate A17/A18 rows exposed the original resume bug.
- `results/phase15-3-sol-low-20260824-linkscope/`: clean strict 16/18; A07/A08 still lost `link_scope`.
- `targeted_results/phase15-3-targeted-sol-low-20260824-selection-operation/`: 4/4 targeted proof after
  Selection-before-Operation prompting.
- `results/phase15-3-sol-low-20260824-selection-operation/`: latest full evidence; 16/18 strict with
  graph semantics restored and the optional-type limitation above.

No retry, raw-output edit, metadata edit, or oracle weakening was used to manufacture a strict 18/18.
