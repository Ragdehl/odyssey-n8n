# Pilot feature: P4 generic contract audit and controlled completion

## Goal
Audit the existing source-provenance and multi-application P4 implementation, with special emphasis on whether an arbitrary user-defined Odyssey app could reuse Core-owned identity, source anchoring, date, canonical Writer, and E2/E3 contracts rather than custom logic. Improve only safe, clearly bounded findings. This pilot must not deploy or modify user data.

## Acceptance criteria
The proposed architecture supports 0/1/N facts and mixed Notes with independent and dependent operations; no literal phrase, domain example or fixed action count is hard-coded. Core remains app-agnostic and apps expose narrow typed contracts. No alternate Writer. All known E2/E3 permissions and replay invariants remain enforced. Reviewers expose both passing and blocked checks, and provide exact code evidence. The end-to-end full browser gate is mandatory before declaring the feature user-ready.

## Forbidden shortcuts
No patching historical benchmark limits, skipping negative tests, treating mocked providers as genuine GPT, accessing PROD or a personal vault, unsafe n8n/Cloudflare modification, auto-deploy, publishing or unbounded agent recursion.

## Performance measurements
Record Raspberry Pi CPU, RAM/swap, source-to-write timings, and benchmark baseline where available. Missing authentic p95 or browser evidence must be labelled blocked rather than guessed.
