# Future extension points

## Purpose

This document is the canonical home for **cross-phase product directions that are intentionally not
implemented yet**. Current planner behavior belongs in the
[Phase 15 Planning Contract](phase-15-write-planning.md); phase order/status belongs in the
[Functional Roadmap](functional-roadmap.md).

The goal is to preserve future requirements without forcing speculative infrastructure or duplicating
active contracts.

## 1. Concrete capability routing and execution

Odyssey is expected to support additional applications or capabilities built on the same knowledge
foundation: structured analytics, purchase/ticket processing, project workflows, translation-related
workflows, and others.

Phase 15.3 implements generic delegation detection in the top-level planner. The remaining scalable
direction is concrete app selection and execution after that generic boundary.
The top-level Sol planner should not receive an ever-growing catalog of every installed app.

The current `RequestPlan` may contain:

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

**Status: conditional later extension; not part of the initial Phase 16.6 CREATE implementation.**

Once Phase 15 has selected a canonical note type, Odyssey could eventually use type-specific writing
guidance for body structure, useful sections, style, and other presentation conventions that are not
canonical metadata properties.

This is not another classification problem. The type is already known. If this capability is later
needed, selection should therefore remain deterministic:

```text
canonical note type
      |
      v
load type-aware writing guidance
      |
      v
body creation / bounded semantic patch
```

Phase 16.6 deliberately does **not** introduce this representation. The existing Phase 16.3 corpus
already exercised fifteen `CREATE_BODY` cases across multiple note semantics using one generic bounded
writer contract, without demonstrating a type-specific failure that requires another configuration
layer. The simplest initial CREATE path therefore remains one shared Luna-medium writer policy.

If focused CREATE evidence or later real usage demonstrates a concrete type whose body is materially
poor without specialized organization, start with the smallest representation. Short guidance may
live as an optional schema-linked field or compact registry entry. If it grows large or example-heavy,
move it to a dedicated Markdown profile keyed by type and keep only a stable reference in the type
registry.

Writing guidance would control human-readable rendering only; `config/note-schema.json` remains the
machine-readable owner of note types/properties and validation. Guidance must never silently invent
metadata fields, change creation authorization, or become a second ontology.

This direction remains available without freezing generic CREATE formatting forever, but it now has a
clear evidence gate: **do not implement a profile system until measured body-quality failures justify
it.**

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

## 5. Large-vault retrieval reduction with a cheap reasoner

**Status: future benchmark hypothesis only; this is not current production retrieval behavior.**

Phase 11B.1c stress evidence over a frozen synthetic 1,000-note vault showed a useful asymmetry:
multilingual MiniLM retained the expected contextual entity at **Recall@100 = 100%**, while
Recall@5 was only **72%**. The broad-retrieval problem is therefore currently solved better than the
safe-reduction problem. GitHub issue #20 preserves the detailed benchmark context and the original
recall-first selector hypothesis.

Preliminary Phase 16.3 writer evidence suggests that Luna may be capable of useful bounded semantic
reasoning at much lower cost than the strongest model. That writer evidence does **not** prove that
Luna is safe for identity retrieval, where dropping or selecting the wrong entity is more dangerous.
It is only a reason to benchmark Luna as a future retrieval component.

The simplest next hypothesis to test is:

```text
1,000+ notes
    |
    v
MiniLM local broad retrieval
    |
    v
Top 100 candidates
    |
    v
Luna high-recall selector
    |
    +--> keep ~20
    +--> keep ~10
    `--> keep ~5        # evidence only; do not assume this is safe
    |
    v
strong contextual resolver
(currently Sol unless later evidence changes that)
```

The selector is **not** an identity authority. Its job is only to remove clearly implausible
candidates while retaining the correct one. The critical benchmark failure is dropping the correct
candidate, not retaining too many false candidates.

Do not assume the previous 1,000-note corpus already has sufficient note-length coverage. Before the
next selector benchmark, inspect it and extend/freeze a new benchmark version if necessary so the
vault deliberately contains a realistic mix of:

- short notes with roughly 1-5 factual units;
- medium notes with roughly 10-20 factual units;
- long notes with roughly 40-60 meaningful factual units;
- a smaller set of very long notes around 1,500-3,000 words.

Long notes must contain meaningful heterogeneous knowledge rather than repeated filler. For identity
and contextual-reference cases, place the distinguishing evidence deliberately near the beginning,
middle, and end of different notes. Include long distractor notes that share names, organizations,
places, or vocabulary with the query while remaining the wrong entity. Measure MiniLM broad-retrieval
recall and Luna reduction recall separately by note-length bucket as well as in aggregate, so good
short-note performance cannot hide dilution or selection failures on long notes.

Reuse the existing 1,000-note adversarial corpus where it already provides valid coverage, rather
than replacing it merely to obtain nicer results, and measure at least:

- Recall@20, Recall@10, and Recall@5 after Luna selection;
- the exact IDs of any correct candidates dropped;
- recall broken down by short/medium/long/very-long source-note length;
- beginning/middle/end placement of the identity-bearing evidence in long notes;
- Spanish/French and contextual-reference behavior;
- input/output/reasoning tokens and real cost per query;
- latency;
- whether compact candidate evidence is sufficient without full note bodies.

Prefer a recall-first acceptance bar. A result such as MiniLM Recall@100 = 100% followed by Luna
Recall@10 = 100% would justify sending only those ten candidates to the strong resolver. Ordinary
accuracy or a nicer ranking is not enough if the correct note can disappear.

Only after that selector benchmark is strong should Odyssey test the more aggressive possibility that
Luna itself can perform contextual resolution and escalate uncertainty:

```text
MiniLM Top 100
      |
      v
     Luna
    /    \
confident  uncertain / ambiguous
   |             |
   v             v
Core validates   strong resolver (Sol)
chosen ID        decides fail-closed
```

That second experiment must retain the existing identity guardrails: the model never mutates a note
by path/name alone, Core validates stable IDs/current candidates, ambiguity fails closed, and the
strong resolver remains available when Luna is not sufficiently certain. Do not replace Sol in this
role merely because Luna performs well as a writer.

### Compact retrieval evidence

The existing issue #20 also proposes a compact retrieval/disambiguation summary for each note. If
future writer evidence supports it, a writer call that creates or materially updates a note could
also produce or refresh compact identity-bearing retrieval evidence in the same intelligent
operation, avoiding an extra model call. Candidate evidence might look conceptually like:

```text
id | canonical name | type | aliases | compact identity facts
```

rather than 100 full Markdown bodies. This could materially reduce Luna/Sol input tokens. Do not make
such a summary a universal canonical Markdown property yet: stale identity summaries are dangerous.
Prefer a revision-bound derived-index representation first unless a later contract demonstrates that
a canonical property is necessary.

### Do not build a model ladder prematurely

A deeper ladder remains a possible optimization, for example:

```text
MiniLM -> local selector -> Luna -> Sol
```

but do **not** introduce another local LLM/classifier merely because it might reduce Luna tokens.
Benchmark the simpler `MiniLM -> Luna -> Sol` path first. Add a local intermediate selector only if
measured Luna cost, latency, or candidate volume creates a concrete problem and the new stage can
preserve the required high recall.

## Placement

```text
NOW / Phase 16.6
  - current planner contract lives in phase-15-write-planning.md
  - generic delegation detection is implemented; no concrete app router or user model
  - CREATE uses the shared Luna-medium writer only when free-text facts require body generation
  - no type-writing-profile system unless focused evidence demonstrates a concrete need

Before large-vault contextual retrieval is considered production-ready
  - reuse/extend the existing 1,000-note corpus with explicit long-note coverage when needed
  - benchmark MiniLM Top-100 -> Luna high-recall Top-20/10/5 reduction
  - measure recall separately for short/medium/long/very-long notes
  - only if that is safe, test Luna resolution with fail-closed escalation to the strong resolver
  - evaluate compact revision-bound retrieval evidence before sending full note bodies

When first concrete app exists
  - route the existing generic DelegateAction with cheap/local app selection
  - load only selected app detail

Later writing-quality work, only if evidence requires it
  - add the smallest schema-linked type-writing guidance representation

Later ontology work
  - evolve tag vocabulary/types only from demonstrated needs

Later multi-user phase
  - design authentication/authorization/storage boundaries first
  - add sharing metadata only after the security model is real
```

The general rule is progressive disclosure and one canonical owner per contract: the main planner
preserves meaning it already understands, while app instructions, writing profiles, analytics,
graph execution, retrieval reduction, and authorization are loaded or executed only when needed.