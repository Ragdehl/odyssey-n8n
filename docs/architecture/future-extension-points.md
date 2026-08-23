# Future extension points — apps, writer profiles, explicit tags, and users

## Status

Directional architecture notes captured during the Phase 15.2 design checkpoint. These items are
important product requirements or likely extension points, but they do **not** all belong in Phase
15.2 implementation. The purpose of this document is to preserve the intended boundaries so later
phases do not accidentally close them off or implement a more complex architecture than necessary.

The current direct Odyssey path remains:

```text
user request
    |
    v
Phase 15 planner
    |
    +--> RetrieveAction
    `--> WriteAction
             |
             v
      resolution / persistence
```

Future capabilities should extend this path rather than replace it with a generic workflow engine.

## 1. App / capability routing

### Product need

Odyssey is expected to gain additional applications or capabilities built on the same knowledge
model. Examples include purchase/ticket processing, project/task workflows, translation-related
workflows, structured analytics over notes, and other future applications.

The Phase 15 interpretation boundary is the natural place to recognize that the user's request is
asking for one of those capabilities because it already performs semantic decomposition of a user
message into ordered actions.

### Direction

Do not add a separate mandatory router LLM before the existing planner. Extend the existing top-level
planner, when the first real app requires it, so its ordered `RequestPlan` can contain an additional
application action alongside ordinary retrieve/write actions.

Conceptually:

```text
RequestPlan.actions[]
    |
    +--> RetrieveAction
    +--> WriteAction
    `--> AppAction
             |
             +--> app_id
             `--> original/normalized subrequest
```

An app selection belongs to an **action**, not to the whole request. A single user message may contain
several actions, including normal note work before or after an app action.

Example:

```text
"¿Cuántas compras hice en Carrefour este año? Apunta el resultado en mi nota de presupuesto."

1. AppAction(app=analytics, request="cuántas compras ...")
2. WriteAction(...)
```

### App manifests and progressive disclosure

Each installed Odyssey app should expose a compact manifest with a stable `app_id`, a short
description, and activation guidance. A Markdown manifest is a reasonable human-readable format.
The top-level planner should receive only the compact routing information needed to choose an app;
it should not receive every app's full implementation instructions or large schema on every request.

Conceptually:

```text
apps/
└── analytics/
    ├── APP.md          # id + what/when to use
    └── ...             # app-specific contract/resources
```

If an app needs additional semantic planning, its detailed contract can be loaded **after selection**
and handled by the app boundary. This preserves one top-level semantic decomposition call for normal
Odyssey use while avoiding an ever-growing planner prompt.

Do not add `AppAction` or an app registry merely to reserve syntax. Implement this extension when the
first concrete app is ready to execute and benchmark its routing behavior then.

### Analytics as a likely first app/capability

Structured counts, sums, averages, grouping, and similar deterministic operations are a strong
candidate for an analytics capability backed by the rebuildable derived SQLite index. The LLM should
produce a validated structured analytics plan; deterministic code/SQL should perform arithmetic.
Do not load the Markdown vault into an LLM to calculate deterministic aggregates.

## 2. Type-aware note-writing profiles ("skills")

### Product need

Once Phase 15 has selected a canonical note type, Odyssey should know how that type is normally
written: preferred body structure, useful sections, concise/verbose style, and any type-specific
content conventions that are not themselves canonical metadata properties.

Examples:

- a `person` note may prefer compact stable facts and readable relationship context;
- a `journal_entry` should read naturally as a dated personal entry rather than a database dump;
- a future `idea` type may preserve the idea, rationale, uncertainty, and relevant links without
  inventing task status;
- a `purchase` note may use a repeatable human-readable structure appropriate for line items and
  links.

### Direction

Treat this as **type-aware writing guidance**, not as another entity-classification step. The type is
already known from Phase 15, so the application should deterministically select the matching writer
profile before a note-body LLM call. Do not spend another model call asking which writing profile to
use.

Start with the simplest source of truth. Short type-specific guidance may live as an optional field in
the canonical type definition. If the guidance becomes large, example-heavy, or executable, split it
into a dedicated Markdown profile keyed by canonical type and keep only the stable reference in the
type registry.

Possible later shape:

```text
note type selected by Phase 15
        |
        v
load writing guidance for that type
        |
        v
body creation / bounded semantic patch
```

This requirement directly affects Phase 16 body creation and semantic patching, so Phase 16 design
must decide the minimal profile representation before it freezes note-body rendering behavior.

Do not confuse writer guidance with canonical metadata validation. `config/note-schema.json` remains
the machine-readable owner of note types/properties; writing guidance controls human-readable body
rendering and must not silently invent schema fields.

## 3. Tags should be explicit user-controlled transversal labels

### Product direction

Tags are useful when they express a transversal label that the user deliberately wants to apply or
query, for example `familia`. They should **not** be inferred merely because the LLM believes a note
looks like an idea, reflection, decision, or similar semantic category.

Desired safety rule:

```text
semantic wording only
    -> do not create a tag filter or tag mutation

user explicitly asks for tag/etiqueta X
    -> tag operation may be represented deterministically
```

The same rule applies to reads and writes. A hard tag filter can permanently exclude relevant notes,
so it must originate from explicit user intent rather than planner guesswork.

### Current schema conflict to resolve later

The current canonical tag registry still contains semantic values such as `idea`, `decision`,
`reflection`, and others. The current planner deliberately stopped inferring these tags (ADR 0008),
but the registry itself remains for compatibility.

The newer product direction is different: `idea` is a candidate canonical **note type**, while tags
should represent deliberate cross-cutting labels. This is a material ontology/schema decision and
must not be changed silently inside Phase 15.2.

Before explicit tag planning is implemented, perform a focused schema decision covering at least:

- whether `idea` becomes a canonical note type;
- which existing semantic tags remain useful, move to types/other semantics, or are retired;
- whether tags remain a controlled registry or become user-extensible labels;
- normalization/collision rules for user-defined tags;
- how an explicit unknown tag is created or rejected;
- exact read/write syntax or planner evidence required to prove that the user explicitly requested a
  tag.

Until that decision is made, keep ADR 0008's conservative planner behavior: no semantic tag
inference.

## 4. Future multi-user ownership and sharing

### Product need

A future Odyssey application may support multiple users and notes that are private, shared read-only,
or shared read/write with selected users.

Conceptually the product may eventually need:

```text
note
├─ owner
└─ grants[]
     ├─ user
     └─ permission: read | write
```

### Do not add ACL fields yet

Do **not** add `users`, `owner`, or permission lists to the note schema merely to reserve them. Access
control is a security boundary, not only note metadata. A frontmatter field cannot enforce privacy if
a user can access the underlying filesystem/vault directly.

A future multi-user phase must first decide:

- user identity/authentication;
- ownership semantics;
- read/write grant model;
- where authorization is enforced before note access;
- private versus shared vault/storage boundaries;
- whether sharing metadata belongs in Markdown, a separate authorization store, or both;
- how Obsidian/direct filesystem access interacts with permissions;
- auditing of permission changes.

The current single-user architecture should stay simple. Stable note IDs, explicit application
boundaries, and rebuildable indexes do not prevent a later multi-user design, so no speculative schema
field is required now.

## Placement in the functional roadmap

These extension points map to different moments rather than one new phase:

```text
NOW / Phase 15.2
  - preserve entity + generalized link-selection intent
  - do not expand implementation with apps/users/tag migration

Phase 16
  - decide minimal type-aware writer-profile representation
  - use it for safe note creation/body mutation

When first concrete app exists
  - extend top-level RequestPlan with app/capability routing
  - feed compact app manifests to the same top-level planner
  - load app-specific detail only after selection

Before explicit tag support
  - resolve tag ontology/registry direction
  - then add explicit-only tag read/write behavior

Later multi-user phase
  - design authentication/authorization/storage boundary first
  - only then add sharing metadata required by that design
```

The overarching principle is progressive disclosure and one interpretation responsibility per layer:
the top-level planner should preserve meaning it already understands, while detailed app instructions,
writer profiles, graph execution, analytics, and authorization are loaded or executed only when the
selected operation actually needs them.
