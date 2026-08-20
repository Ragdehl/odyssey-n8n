# Phase 14 retrieval-plan benchmark summary

Run: `20260820T103836Z-missing-api-key`
Git SHA: `8c6a8a3b7637a341aecae4cbe4db3ceb508045ed`
Fixed context: `{"current_date": "2026-08-20", "current_time": "10:30", "timezone": "Europe/Madrid"}`

Execution status: `blocked_before_api_calls`
Blocker: `OPENAI_API_KEY is unavailable`
Paid API requests: `0`

## Configuration overview

| Model | Effort | Tests | Critical | Major | Minor | Avg latency | Tokens | Estimated cost |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `gpt-5.6-luna` | none | 0/45 | 0 | 0 | 0 | — | 0 | not run |
| `gpt-5.6-luna` | low | 0/45 | 0 | 0 | 0 | — | 0 | not run |
| `gpt-5.6-terra` | low | 0/45 | 0 | 0 | 0 | — | 0 | not run |
| `gpt-5.6-sol` | low | 0/45 | 0 | 0 | 0 | — | 0 | not run |

API failures are reported separately and are not counted as model-quality failures.
Total measured API usage: 0 requests; $0.000000000 estimated.

## Per-test comparison

| Test | gpt-5.6-luna/none | gpt-5.6-luna/low | gpt-5.6-terra/low | gpt-5.6-sol/low |
| --- | --- | --- | --- | --- |
| T01 | NOT RUN | NOT RUN | NOT RUN | NOT RUN |
| T02 | NOT RUN | NOT RUN | NOT RUN | NOT RUN |
| T03 | NOT RUN | NOT RUN | NOT RUN | NOT RUN |
| T04 | NOT RUN | NOT RUN | NOT RUN | NOT RUN |
| T05 | NOT RUN | NOT RUN | NOT RUN | NOT RUN |
| T06 | NOT RUN | NOT RUN | NOT RUN | NOT RUN |
| T07 | NOT RUN | NOT RUN | NOT RUN | NOT RUN |
| T08 | NOT RUN | NOT RUN | NOT RUN | NOT RUN |
| T09 | NOT RUN | NOT RUN | NOT RUN | NOT RUN |
| T10 | NOT RUN | NOT RUN | NOT RUN | NOT RUN |
| T11 | NOT RUN | NOT RUN | NOT RUN | NOT RUN |
| T12 | NOT RUN | NOT RUN | NOT RUN | NOT RUN |
| T13 | NOT RUN | NOT RUN | NOT RUN | NOT RUN |
| T14 | NOT RUN | NOT RUN | NOT RUN | NOT RUN |
| T15 | NOT RUN | NOT RUN | NOT RUN | NOT RUN |
| T16 | NOT RUN | NOT RUN | NOT RUN | NOT RUN |
| T17 | NOT RUN | NOT RUN | NOT RUN | NOT RUN |
| T18 | NOT RUN | NOT RUN | NOT RUN | NOT RUN |
| T19 | NOT RUN | NOT RUN | NOT RUN | NOT RUN |
| T20 | NOT RUN | NOT RUN | NOT RUN | NOT RUN |
| T21 | NOT RUN | NOT RUN | NOT RUN | NOT RUN |
| T22 | NOT RUN | NOT RUN | NOT RUN | NOT RUN |
| T23 | NOT RUN | NOT RUN | NOT RUN | NOT RUN |
| T24 | NOT RUN | NOT RUN | NOT RUN | NOT RUN |
| T25 | NOT RUN | NOT RUN | NOT RUN | NOT RUN |
| T26 | NOT RUN | NOT RUN | NOT RUN | NOT RUN |
| T27 | NOT RUN | NOT RUN | NOT RUN | NOT RUN |
| T28 | NOT RUN | NOT RUN | NOT RUN | NOT RUN |
| T29 | NOT RUN | NOT RUN | NOT RUN | NOT RUN |
| T30 | NOT RUN | NOT RUN | NOT RUN | NOT RUN |
| T31 | NOT RUN | NOT RUN | NOT RUN | NOT RUN |
| T32 | NOT RUN | NOT RUN | NOT RUN | NOT RUN |
| T33 | NOT RUN | NOT RUN | NOT RUN | NOT RUN |
| T34 | NOT RUN | NOT RUN | NOT RUN | NOT RUN |
| T35 | NOT RUN | NOT RUN | NOT RUN | NOT RUN |
| T36 | NOT RUN | NOT RUN | NOT RUN | NOT RUN |
| T37 | NOT RUN | NOT RUN | NOT RUN | NOT RUN |
| T38 | NOT RUN | NOT RUN | NOT RUN | NOT RUN |
| T39 | NOT RUN | NOT RUN | NOT RUN | NOT RUN |
| T40 | NOT RUN | NOT RUN | NOT RUN | NOT RUN |
| T41 | NOT RUN | NOT RUN | NOT RUN | NOT RUN |
| T42 | NOT RUN | NOT RUN | NOT RUN | NOT RUN |
| T43 | NOT RUN | NOT RUN | NOT RUN | NOT RUN |
| T44 | NOT RUN | NOT RUN | NOT RUN | NOT RUN |
| T45 | NOT RUN | NOT RUN | NOT RUN | NOT RUN |

## Critical and major differences

None in the available evaluated results.
## Final recommendation

No configuration can yet be recommended: no complete evaluated configuration has demonstrated zero critical errors.
Quality reference remains unavailable until a complete Sol run exists.

A more articulate explanation is not evidence of better retrieval. The recommendation uses hard-filter safety and preservation of semantic recall first, then major/minor errors, actual estimated cost, and latency.
