# Notes grouped browsing UX

Status: **implemented and in isolated DEV for human review; grouped-Notes polish remains iterative before the Calendar redesign**.

This follow-on to [UI-2 read-only Notes](ui-2-read-only-notes.md) replaces the flat Notes landing
feed with mobile-first groups derived from the runtime-composed Notes capability projection. It does
not change the canonical schema, ontology, Markdown authority, identity rules, or application
ownership.

## Product and responsibility contract

Core projects every Notes-visible canonical type with its canonical description and property
metadata (`id`, `description`, `value_type`, `required`, and `filterable`). Runtime composition may
therefore add an application-owned visible type such as Task without a browser semantic registry.
Browser-owned presentation remains limited to localized labels/copy, icons, colors, layout, and
temporary view state. The current Spanish UI may overlay localized descriptions for the currently
known types/properties while retaining the runtime-projected canonical descriptions as the fallback;
this is presentation only. A later product-wide language switch must replace this bounded overlay with
one coherent localization contract rather than translating schema semantics or stored knowledge.

Ordinary feed and local browsing issue one bounded deterministic query per eligible visible type,
requesting three notes initially and retaining an independent cursor for each group. General filters,
query, and sort refresh all eligible groups. A property filter restricts eligibility to types whose
runtime `applies_to` capability supports that property; it is never forwarded to an incompatible
group. The ordinary filter sheet consequently has no explicit type selector, while a validated type
filter arriving from an intelligent or historical state remains representable and constrains the
visible groups.

Intelligent search keeps one planner invocation. The browser groups only the loaded deterministic
result page and continues through the existing global `query(mode=intelligent)` cursor; it never fans
out planning by type. Historical and affected-note snapshots likewise keep their exact ordered
stable-ID membership, unavailable positions, status, rerun semantics, and global cursor. Grouping is
presentation only.

Group collapse is optional session UI state stored in `sessionStorage` with a fail-safe in-memory
fallback. It is not canonical knowledge or durable product state. The final `Crear nuevo tipo` card,
the per-group create control, and the type-information `Editar tipo` control are explicitly work in
progress and have no schema or Note mutation path. They may explain the intended future action but
must not issue a write until the corresponding Core/schema authoring contract exists.

## Calendar boundary and next phase

Calendar Day remains absent from Notes capabilities, ordinary groups, the feed, and intelligent
Notes results. Direct Calendar Day links still navigate to the Calendar surface and may use the
browser presentation map for their semantic icon/color. Work Session remains application-managed
supporting state and is not a Notes-visible group.

The next UX phase is the Calendar redesign. This phase deliberately does not choose or implement its
new navigation/detail contract.

## Acceptance evidence

Deterministic Core, runtime, browser-client, browser-controller, static-contract, and Tasks
integration tests cover schema-derived capability metadata, runtime-composed Task visibility,
Calendar Day/Work Session exclusion, grouped paging and stale-cursor recovery, compatible property
filtering, session-only collapse, latest-query-wins recovery when local search is cleared during an
in-flight refresh, single-plan intelligent continuation, exact snapshots, localized type information,
the WIP authoring controls, and semantic inline-link icon color. Provider/live-model calls are outside
this provider-free phase.
