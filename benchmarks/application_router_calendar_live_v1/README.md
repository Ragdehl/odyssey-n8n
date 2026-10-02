# Application Router + Calendar Planner live gate v1

This gate evaluates the first GPT-6 Luna/low application Router and Calendar Planner contracts after deterministic Slice 5 validation. The Router and Calendar matrices were frozen before provider execution; neither oracle may be edited to make a failed model result pass.

## Attempt 1 — failed, retained

Authorization covered at most 16 GPT-6 Luna calls and a $0.02 ceiling. Commit `f5949ec` executed exactly 16 calls with zero automatic retries: 8 Router and 8 Calendar Planner cases. Usage was 18,872 input tokens and 2,623 output tokens, for an estimated Standard cost of $0.00319870 and a 10%-regional upper estimate of $0.00351857.

Eleven of sixteen cases passed: Router 7/8 and Calendar 4/8. The five failures were reviewed against pre-existing architecture and semantic-write evidence before any prompt change.

- Router dependent temporal/entity statement: returned `CLARIFY` instead of the required single Calendar route.
- Calendar exact `+3 days` occurrence: normalized the correct date but incorrectly classified it as Tasks lifecycle work.
- Calendar next-week occurrence: normalized the correct range but incorrectly classified it as Tasks lifecycle work.
- Calendar next-month occurrence: provider output failed the local Calendar correlation contract; no executable plan was accepted.
- Calendar entity-owned exact-date write: preserved the temporal reference and Marta target but omitted the required Airbus semantic identity reference.

The Airbus oracle is not over-constrained: the established reference-relationship gate already treats `Marta trabaja en Airbus` as an ordinary named-reference case with Marta as target and Airbus through Core `KnowledgeReference` binding. Likewise, the temporal-range failures conflict with the approved Calendar contract rather than merely differing in presentation.

Attempt 1 therefore does **not** validate production adoption. No DEV/PROD deployment or real-vault mutation occurred. A successor prompt revision must preserve these frozen matrices, complete deterministic validation, receive a new bounded-cost authorization, and run as a distinct attempt rather than overwriting this evidence.

Operational learning: the Attempt-1 runner retained parsed semantic outcomes and usage but not the provider's raw structured output. This was sufficient for four semantic failures but left the next-month local contract rejection without its precise provider payload. A successor runner should retain the synthetic structured output (never secrets, prompts, or personal data) before local parsing so a fail-closed correlation error remains diagnosable without another paid call.
