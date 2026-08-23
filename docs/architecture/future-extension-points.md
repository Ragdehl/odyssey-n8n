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

The Phase 15 interpretation boundary is the natural place to recognize, per subrequest, whether the
user is asking for ordinary Odyssey knowledge work or for another capability. It already performs
semantic decomposition into ordered actions.

### Preferred scalable direction: generic delegation first, app selection second

The top-level Sol planner should **not** receive an ever-growing catalog of every installed app. Its
stable responsibility should remain small: split the message and decide whether each piece is:

```text
RequestPlan.actions[]
    |
    +--> RetrieveAction     # direct Odyssey knowledge retrieval
    +--> WriteAction        # direct Odyssey knowledge mutation
    `--> DelegateAction     # another capability is required
```

`DelegateAction` does not need to know the final app ID. It preserves the normalized subrequest and,
when useful, the same generic note-selection information already understood by Odyssey (entity,
query, type, filters, explicit tags, link scope). This lets the first planner retain useful structure
without knowing app-specific operations.

Example:

```text
"¿Cuántas compras hice en Carrefour este año? Apunta el resultado en mi nota de presupuesto."

1. DelegateAction(
     request="cuántas compras hice en Carrefour este año",
     selection=<generic Odyssey note selection when safely expressible>
   )
2. WriteAction(...presupuesto...)
```

The delegated action is then routed separately:

```text
DelegateAction
     |
     v
cheap app router
     |
     +--> analytics
     +--> purchases
     +--> translation
     `--> NO_MATCH
     |
     v
load only selected app contract
     |
     v
app-specific planning/execution
```

This avoids making the expensive top-level semantic planner prompt grow linearly with the app catalog.
It also allows Odyssey to report an unsupported delegated capability when no installed app matches,
rather than forcing the top-level planner to know availability.

### App manifests and cheap routing

Each installed app should expose a compact routing manifest with a stable `app_id`, short description,
and activation examples/guidance. Markdown is a reasonable human-readable source format:

```text
apps/
├── analytics/APP.md
├── purchases/APP.md
└── translation/APP.md
```

The app router can be much cheaper than the main Sol planner. Prefer the simplest measured option:

1. use local embeddings / MiniLM over compact app routing summaries to retrieve a very small candidate
   set;
2. if needed, use a cheap model (for example Luna or a suitable local classifier) to choose among the
   candidates or return `NO_MATCH`;
3. only after routing, load the selected app's detailed instructions/schema.

Do not introduce a second expensive general reasoning call merely for routing. With only a handful of
apps, an even simpler deterministic or embedding-only router may be sufficient if benchmarks support
it.

An app selection belongs to an **action**, not to the whole request, because one user message may mix
normal Odyssey reads/writes with delegated capabilities.

Do not implement app routing merely to reserve syntax. Add it when the first concrete app exists and
benchmark the boundary then. Analytics remains a likely first app because deterministic counts, sums,
averages, grouping, and similar operations can execute against rebuildable derived SQLite data rather
than loading the Markdown vault into an LLM.

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

## 3. Tags — explicit user-controlled transversal labels

### What transversal means

A tag is an axis independent from the note's canonical type. It does **not** have to make sense on
every type; it should be useful across several unrelated types without redefining what those notes are.

For example, a future `familia` tag can mean "this knowledge belongs to my family context" and may
reasonably apply to a `person`, `journal_entry`, `project`, `task`, `purchase`, `document`, or recipe.
It must not be confused with `person.relationship_to_user`: saying "Marta es mi hermana" records a
structured relationship and does not silently add `familia`.

Other plausible transversal domain labels, if later demonstrated and added to the registry, include
`trabajo`, `casa`, `finanzas`, and `viajes`. By contrast, fields that drive deterministic behavior such
as task priority/status or access permissions should normally become proper structured properties or
security rules rather than tags.

### Explicit-only safety rule

The core product rule is:

```text
semantic wording only
    -> NEVER create a tag filter or tag mutation

user explicitly asks for tag/etiqueta X (or another accepted explicit tag form)
    -> tag operation may be represented deterministically
```

Examples:

```text
"Busca ideas sobre Odyssey"
    -> NO tag filter

"Busca notas con el tag idea"
    -> explicit tag filter is allowed

"Apunta esta idea"
    -> NO automatic tag mutation

"Apunta esto y añade el tag review"
    -> explicit tag add is allowed
```

This applies equally to retrieval, write-target selection, graph anchors, and note mutation. A hard tag
restriction can exclude relevant notes, so it must never come from semantic guesswork.

### Phase 15.2 implementation direction

This explicit-only behavior is small enough to include in the Phase 15.2 planner-contract work without
redesigning the tag ontology.

For **selection**, reuse the existing deterministic filter language rather than add another query
system. `tags` is already canonical `array[string]` metadata and Core already supports `contains` for
array filters. A planner tag filter is therefore valid only when the user explicitly requested a
controlled tag:

```text
ContextFilter(field="tags", op="contains", value="review")
```

The current planner capability projection intentionally hides tags under ADR 0008. Phase 15.2 may
refine that decision by exposing the controlled tag vocabulary with strict explicit-only guidance.
The essential ADR 0008 safety conclusion remains: **never infer tags from semantic wording**.

For **writes**, do not model `add tag X` as a whole-array `set`, because the planner does not know all
existing tags and could overwrite them. Use a small item-level mutation contract, conceptually:

```text
TagChange
├─ op: add | remove
└─ value: controlled_tag_id
```

and attach ordered explicit `tag_changes` to `KnowledgeUnit`. Phase 16 can then apply those changes
deterministically after resolving the note.

Unknown tags remain unsupported/limited under the current controlled registry; Phase 15.2 must not
silently create a new tag ID. User-extensible tag creation, normalization, aliases, and registry
management are a separate future schema decision.

### Vocabulary remains a separate ontology question

The current canonical registry contains values such as `idea`, `decision`, `reflection`, `question`,
`reference`, `hypothesis`, `explore`, `someday`, and `review`. Explicit-only planning does **not**
require changing that list now.

Some of those may later move or be retired. In particular, `idea` is a plausible future canonical note
type rather than a tag. That migration should be decided separately because it changes classification
semantics and existing data; it should not be bundled merely to enable safe explicit tag filtering.

Therefore the near-term rule is simple: keep the current controlled registry, allow only explicit use,
and evolve the vocabulary only when concrete notes/use cases justify it.

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
  - add explicit-only controlled tag filters and tag changes
  - never infer tags from semantic wording

Phase 16
  - decide minimal type-aware writer-profile representation
  - apply explicit tag changes after safe target resolution
  - use writer profiles for safe note creation/body mutation

When first concrete app exists
  - let the top-level planner emit generic DelegateAction for non-Core capabilities
  - route delegated actions separately using cheap/local routing over compact app manifests
  - load app-specific detail only after selection

Later tag ontology evolution
  - decide whether `idea` becomes a type and which semantic tags remain
  - decide if/when user-extensible tag creation is needed

Later multi-user phase
  - design authentication/authorization/storage boundary first
  - only then add sharing metadata required by that design
```

The overarching principle is progressive disclosure and one interpretation responsibility per layer:
the top-level planner should preserve meaning it already understands, while detailed app instructions,
writer profiles, graph execution, analytics, and authorization are loaded or executed only when the
selected operation actually needs them.