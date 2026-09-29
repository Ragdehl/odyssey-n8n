# Semantic WRITE frontend v6

This is the offline successor to consumed v5. It reuses the same 10 SWR cases and 3 generic sentinels.

v5 passed SWR01-SWR07 and failed SWR08 because the described companion lost its named event-source bound. The run also exposed one over-constrained SWR08 oracle detail: requiring `mayor` inside the relationship anchor contradicted the deterministic compiler contract, which intentionally allows `mi hija` as the candidate universe while retaining `mi hija mayor` in the full target description. v6 corrects that oracle detail and keeps the real bounded-companion requirement unchanged.

The only model-facing correction refines the existing generic mentor/designer teaching example: a participant defined as coming from a specific named roster carries `EXISTING_DESCRIPTION` even without the literal word “existing”. This does not assert the source exists or authorize creation; Core must ground it or clarify. Mere descriptive event context without named membership remains unbounded.

The gate permits at most 13 Luna/low calls, zero retries, and zero Sol calls. Conservative input bound: 51,832 bytes. No-cache ceiling: `$0.166712`. `MAX_COST_USD` remains `$0.00` until fresh explicit authorization.
