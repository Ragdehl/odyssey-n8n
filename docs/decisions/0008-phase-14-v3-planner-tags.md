# ADR 0008: Phase 14 v3 removes tags from planner interpretation

- Status: Proposed for human review (offline v3 benchmark prepared)
- Date: 2026-08-21

## Decision

The Phase 14 RequestPlan v3 planner contract excludes tags completely. Generic former tag vocabulary—such as `idea`, `decision`, `reflection`, `review`, `explore`, and `someday`—is semantic language and remains in the retrieval query. It does not create deterministic filters or infer a canonical type.

Hard filters can permanently exclude valid notes before semantic ranking. Therefore, v3 only renders schema-owned deterministic capabilities that have an explicit and safe mapping. The canonical schema now carries optional retrieval guidance and examples, from which the frozen v3 planner capability JSON is deterministically rendered.

Existing Core tag storage, schema, and index capabilities remain untouched for compatibility. This is deliberate experimental isolation, not a storage migration. If a concrete product need later requires exact behavioral state—for example, a “must review” workflow—Odyssey should introduce an explicit property designed for that behavior rather than restore a generic tag vocabulary by default. After v3 validation, tag removal from Core is a separate decision.
