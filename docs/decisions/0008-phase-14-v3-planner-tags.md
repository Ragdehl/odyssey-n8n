# ADR 0008: Phase 14 v3 removes tags from planner interpretation

- Status: Proposed for human review (offline v3 benchmark prepared)
- Date: 2026-08-21

## Decision

The Phase 14 RequestPlan v3 planner contract excludes tags completely. Generic former tag vocabulary—such as `idea`, `decision`, `reflection`, `review`, `explore`, and `someday`—is semantic language and remains in the retrieval query. It does not create deterministic filters or infer a canonical type.

Hard filters can permanently exclude valid notes before semantic ranking. Therefore, v3 only renders schema-owned deterministic capabilities that have an explicit and safe mapping. The canonical schema now carries optional retrieval guidance and examples, from which `odyssey_core.planner_capabilities.build_planner_capabilities(...)` deterministically renders planner capability JSON. Production must call that projection dynamically from the canonical schema; only the benchmark freezes one generated snapshot so Terra and Sol use identical inputs.

Existing Core tag storage, schema, and index capabilities remain untouched for compatibility. This is deliberate experimental isolation, not a storage migration. The production integration confirmed the live vault has no tagged notes, but removal still changes the established Phase 13 retrieval API, schema-validation contract, index format, fixtures, and documentation. It is therefore deferred as a separate migration decision rather than bundled into the RequestPlan boundary. If a concrete product need later requires exact behavioral state—for example, a “must review” workflow—Odyssey should introduce an explicit property designed for that behavior rather than restore a generic tag vocabulary by default.
