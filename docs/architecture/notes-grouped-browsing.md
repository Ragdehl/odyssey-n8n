# Notes grouped browsing UX

Status: **implemented on the current feature branch; review and isolated-DEV adoption remain pending**.

This follow-on to [UI-2 read-only Notes](ui-2-read-only-notes.md) replaces the flat Notes landing
feed with mobile-first groups derived from the runtime-composed Notes capability projection. It does
not change the canonical schema, ontology, Markdown authority, identity rules, or application
ownership.

## Product and responsibility contract

Core projects every Notes-visible canonical type with its canonical description and property
metadata (`id`, `description`, `value_type`, `required`, and `filterable`). Runtime composition may
therefore add an application-owned visible type such as Task without a browser semantic registry.
Browser-owned presentation remains limited to localized labels, icons, colors, layout, and temporary
view state.

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
fallback. It is not canonical knowledge or durable product state. The final `Crear nuevo tipo` card
is explicitly work in progress and has no schema mutation path.

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
filtering, session-only collapse, single-plan intelligent continuation, exact snapshots, the WIP card,
and semantic inline-link icon color. Provider/live-model calls are outside this provider-free phase.
