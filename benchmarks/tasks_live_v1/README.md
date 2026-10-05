# Tasks live v1

Frozen successor gate for Tasks v0.1 model-facing changes. It checks the Tasks interpreter's temporal/relationship roles and the shared planner's Task create/complete plus generic Core content-amend path.

Safety envelope: **8 provider calls maximum**, zero retries, zero mutations, no Router/Temporal provider calls, no Sol fallback, and a hard **$0.05** estimated regional cost ceiling. The runner refuses to execute without `ODYSSEY_RUN_TASKS_LIVE_V1=1`, refuses a changed matrix, and refuses a second evidence run.

## Consumed result

The authorized run consumed exactly **8 provider calls**, with **0 retries**, **0 Sol calls**, **0 mutations**, and an estimated regional cost of **$0.01027631**. The raw artifact is `results/52911b23792a.json`.

The artifact reports 7/8 because the original oracle incorrectly required `intent=amend` for the generic Core request “Añade a la tarea llamar al banco que tengo que preguntar por las comisiones.” The shared planner returned `intent=record`, target type `task`, no lifecycle property mutations, and the requested fact. Core semantics resolve `record` against an existing managed Task to an UPDATE; `record` only fails closed against a missing managed Task. A provider-free Core E2E freezes that exact behavior. Therefore the model-facing evidence is adjudicated **8/8 semantically valid** without any rerun. The runner oracle was corrected for future code review only; the one-shot evidence artifact remains unchanged.
