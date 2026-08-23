# Future extension points

## Purpose

This document is the canonical home for **cross-phase product directions that are intentionally not
implemented yet**. Current planner behavior belongs in the
[Phase 15 Planning Contract](phase-15-write-planning.md); phase order/status belongs in the
[Functional Roadmap](functional-roadmap.md).

The goal is to preserve future requirements without forcing speculative infrastructure or duplicating
active contracts.

## 1. App / capability delegation

Odyssey is expected to support additional applications or capabilities built on the same knowledge
foundation: structured analytics, purchase/ticket processing, project workflows, translation-related
workflows, and others.

The preferred scalable direction is **generic delegation first, concrete app selection second**.
The top-level Sol planner should not receive an ever-growing catalog of every installed app.

Conceptually, a future `RequestPlan` may contain:

```text
RequestPlan.actions[]
    |
    +--> RetrieveAction     # direct Odyssey knowledge retrieval
    +--> WriteAction        # direct Odyssey knowledge mutation
    `--> DelegateAction     # another capability is required
```

`DelegateAction` should preserve the normalized subrequest and any generic Odyssey selection
information that the main planner already understands safely. It does not need the final app ID.

Routing then happens separately:

```text
DelegateAction
      |
      v
cheap/local app router
      |
      +--> analytics
      +--> purchases
      +--> translation
      `--> NO_MATCH
      |
      v
load only selected app contract
```

Each installed app should expose a compact routing manifest with stable `app_id`, short description,
and activation examples/guidance. Markdown such as `apps/<app>/APP.md` is a reasonable human-readable
source format.

Prefer the simplest measured router:

1. local embeddings / MiniLM over compact routing summaries to retrieve a small candidate set;
2. only if needed, a cheap model such as Luna or a suitable local classifier chooses among candidates
   or returns `NO_MATCH`;
3. only after routing, load the selected app's detailed instructions/schema.

Do not introduce another expensive general reasoning call only for routing. Implement this when the
first real app is executable and benchmark routing then. Structured analytics is a likely first app:
LLMs can produce a validated structured query plan while deterministic code/SQL performs counts,
sums, averages and grouping over rebuildable index data.

## 2. Type-aware note-writing profiles ("skills")

Once Phase 15 has selected a canonical note type, Odyssey should know how that type is normally
written: body structure, useful sections, style, and type-specific content conventions that are not
canonical metadata properties.

This is not another classification problem. The type is already known, so Phase 16 should
deterministically select its writing guidance before note-body creation or semantic patching.

```text
canonical note type
      |
      v
load type-aware writing guidance
      |
      v
body creation / bounded semantic patch
```

Start with the smallest representation. Short guidance may live as an optional field under the
canonical type definition. If it grows large or example-heavy, move it to a dedicated Markdown profile
keyed by type and keep only the stable reference in the type registry.

Writing guidance controls human-readable rendering; `config/note-schema.json` remains the
machine-readable owner of note types/properties and validation. Guidance must not silently invent
metadata fields.

This must be decided during Phase 16 before note-body rendering behavior is frozen.

## 3. Tag vocabulary evolution

The active planner contract for tags is already canonical in
[Phase 15 Planning Contract](phase-15-write-planning.md): tags are **explicit-only**. Semantic wording
never creates a tag filter or mutation; only an explicit user request may do so.

What remains future work is the **vocabulary**, not that safety rule.

The current controlled registry contains semantic values such as `idea`, `decision`, `reflection`,
`question`, `reference`, `hypothesis`, `explore`, `someday`, and `review`. Some may later be moved,
retired, or replaced. In particular, `idea` is a plausible canonical note type rather than a tag.

Future tag design should preserve the meaning of a tag as a transversal axis independent from note
type. It need not apply to every type, only to multiple types without redefining what the note is.
Possible user-facing transversal domains, if demonstrated, include:

```text
familia
trabajo
casa
finanzas
viajes
```

For example, `familia` could apply to a person, journal entry, task, project, purchase, document, or
recipe as a context label. It is not a substitute for structured information such as
`person.relationship_to_user`.

Before changing the current registry, make a focused ontology/schema decision covering:

- which semantic tags remain useful;
- whether `idea` or other values become canonical types;
- whether tags stay controlled or become user-extensible;
- normalization/collision rules for user-defined tags;
- how unknown explicit tags are created or rejected;
- migration behavior for existing notes if the vocabulary changes.

Do not use tags for deterministic lifecycle/security behavior merely for convenience. Task status or
priority belongs in structured task semantics when needed; privacy/access control belongs in the
security model.

## 4. Future multi-user ownership and sharing

A future Odyssey application may support multiple users and notes that are private, shared read-only,
or shared read/write.

Conceptually that may eventually require ownership/grant semantics, but **do not add `owner`, `users`,
or permission arrays to the note schema merely to reserve them**. Frontmatter cannot enforce privacy
if a user can access the underlying vault directly.

A multi-user phase must first decide:

- authentication and stable user identity;
- ownership semantics;
- read/write grant model;
- where authorization is enforced before note access;
- private versus shared storage/vault boundaries;
- interaction with Obsidian/direct filesystem access;
- whether sharing metadata belongs in Markdown, a separate authorization store, or both;
- audit requirements for permission changes.

The current single-user architecture should remain simple. Stable note IDs, explicit application
boundaries and rebuildable indexes do not block a later multi-user design.

## Placement

```text
NOW / Phase 15.2
  - current planner contract lives in phase-15-write-planning.md
  - no speculative app router or user model

Phase 16
  - choose minimal type-aware writing-profile representation
  - execute already-planned explicit tag changes after safe target resolution

When first concrete app exists
  - add generic DelegateAction
  - route with cheap/local app selection
  - load only selected app detail

Later ontology work
  - evolve tag vocabulary/types only from demonstrated needs

Later multi-user phase
  - design authentication/authorization/storage boundaries first
  - add sharing metadata only after the security model is real
```

The general rule is progressive disclosure and one canonical owner per contract: the main planner
preserves meaning it already understands, while app instructions, writing profiles, analytics,
graph execution, and authorization are loaded or executed only when needed.
