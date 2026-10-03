# Application Router + Calendar live gate v11

Focused one-shot evidence for the Journal-converged Router and Calendar contracts.

- Router: GPT-6 Luna / medium, 9 frozen cases from `application_router/regression_v3.json`.
- Calendar: GPT-6 Luna / low, 9 frozen cases from `calendar_planner/regression_v7.json`.
- Maximum 18 provider calls, zero SDK retries, no Core planner calls, and no vault mutation.
- Provider authority is disabled unless `ODYSSEY_RUN_APPLICATION_ROUTER_CALENDAR_V11=1` is explicitly set after human authorization.
- The conservative regional cost ceiling is `$0.013`; the runner refuses contract, matrix, budget, dirty-tree, or second-run drift.

The two new Journal sentinels prove that explicit-date and implicit-today personal diary capture route to Calendar and return exact grounded `capture_text` rather than creating a Journal note.

Retained execution on `208c47de13075bf4aa1484aca74d165207e97f67`: 18/18 completed responses, zero retries, `passed=true`, standard cost `$0.00221490` (regional estimate `$0.00243639`). The detailed row artifact was accidentally overwritten during post-run local staging because multiple gates shared the same commit-derived filename; `results/208c47de1307.reconstructed.json` records only the runner stdout facts and is explicitly marked as reconstructed. The gate must not be rerun under the consumed authorization.
