# Phase 16.7B soft DELETE

Status: **implemented; deterministic verification passed**

This document is the canonical contract for Phase 16.7B. It defines the initial deletion semantics for Odyssey notes before implementation.

## Objective

Support user-requested whole-note deletion without destroying historical Markdown context, without rewriting every inbound wikilink, and without allowing deleted notes to continue participating in ordinary active knowledge behavior.

The initial operation is a reversible **soft delete**, not physical destruction:

```text
resolved active note
      |
      v
set deleted: true
      |
      +--> preserve stable ID
      +--> preserve path
      +--> preserve body
      +--> preserve existing inbound/outbound wikilinks
      `--> exclude from active Odyssey behavior
```

The real problem is not implementing generic deletion infrastructure. It is retiring one canonical note from active knowledge safely while preserving enough historical continuity that existing journal entries, project notes, and other Markdown remain meaningful.

## Canonical lifecycle field

Phase 16.7B introduces optional universal metadata:

```yaml
deleted: true
```

Contract:

- `deleted` is a boolean lifecycle field shared by all canonical note types;
- absence of `deleted` means the note is active;
- Odyssey does not need to persist `deleted: false`;
- `deleted` is Core-managed lifecycle state and must not become an ordinary planner-writable property;
- the initial schema change is backward-compatible for existing notes: notes without the field remain active and valid;
- implementation should avoid forcing a vault-wide rewrite merely to add the optional field;
- the canonical schema/validator must explicitly support the boolean value type needed by this field.

Because this is a canonical schema change, the behavior in this document has been explicitly approved before implementation.

## Delete materialization

The initial Phase 16.7B mutation is deliberately narrow:

```text
KnowledgeUnit(intent=delete, cardinality=one)
        |
        v
existing Phase 16 target resolution
        |
        +--> unresolved / ambiguous -> no mutation
        |
        `--> one resolved ACTIVE note
                |
                v
        revision-guarded Core soft-delete
                |
                v
           deleted: true
```

The delete path must:

- operate only on one already-resolved active note;
- preserve the existing stable ID, path, canonical name, type, body, aliases, properties, tags, and links;
- increment the normal revision/update lifecycle metadata through Core;
- make no LLM call for deletion materialization;
- not reinterpret or rewrite note prose;
- not introduce a generic transaction engine.

A dedicated Core lifecycle operation is preferred over allowing callers to set `deleted` through ordinary `update_entity()` metadata mutations, because callers must not gain generic authority over Core-managed lifecycle state.

## Active-knowledge exclusion

A note with `deleted: true` is physically present but is not ordinary active Odyssey knowledge.

By default it must be excluded from:

- ordinary exact identity resolution;
- semantic entity candidate retrieval;
- contextual identity resolution;
- general context retrieval;
- semantic/context index projections and rebuilds;
- deterministic bulk selection;
- future structured calculations/aggregations unless an explicit deleted/history mode is introduced later.

The authoritative Markdown state remains decisive. A stale derived index must never re-authorize a note that current Markdown marks deleted. Read/resolution boundaries therefore need an authoritative active-state check in addition to omitting deleted notes from future index rebuilds.

## Existing wikilinks and backlinks

Soft delete must **not** rewrite notes that already mention or link to the deleted note.

Example:

```markdown
Hoy he comido con [[Marta]].
```

Deleting Marta must leave that Markdown unchanged. Rewriting every backlink would turn one logical delete into a broad multi-note mutation with partial-failure, revision, audit, and historical-information risks.

The deleted target remains physically present, so existing wikilinks continue to point to a recoverable historical object.

### Future presentation behavior

A future frontend may render a wikilink whose destination is deleted with a visual deleted state, for example:

```text
~~Marta~~ [eliminada]
```

This is presentation behavior only. The authoritative source Markdown remains `[[Marta]]`; Phase 16.7B does not rewrite stored prose or wikilinks merely to display deletion state.

## CREATE interaction and deleted identity collisions

Deleted notes are excluded from normal identity resolution, but they are not invisible to every safety check.

A later implicit CREATE decision can otherwise accidentally duplicate an identity that the user previously deleted. The initial guard is intentionally narrow and deterministic:

```text
implicit CREATE candidate
        |
        v
no active identity resolved
        |
        v
exact name/alias lookup among deleted notes only
        |
        +--> no exact deleted match -> ordinary CREATE path may continue
        |
        `--> exactly one relevant deleted match -> NEEDS_CLARIFICATION
```

Rules:

- do not semantically search deleted notes for this guard;
- do not use deleted notes as ordinary identity candidates;
- do not automatically restore a deleted note;
- do not permanently reserve a human-readable name merely because it existed before;
- an explicitly requested **new** entity may receive a fresh stable ID even when a deleted note has the same name;
- an implicit create that collides exactly with one deleted canonical name/alias must fail closed for later application/HITL handling rather than silently creating a duplicate.

This distinction intentionally separates:

```text
"Is this an active entity?"
        !=
"Did an exactly matching deleted identity previously exist?"
```

## Restore and purge

Phase 16.7B does not implement either operation.

- **Restore** may later clear deleted state on the same stable identity so historical links become active again. The interactive decision belongs naturally with the Phase 17 application/pending-work boundary.
- **Purge** would physically destroy the Markdown note and raises a different class of backlink, audit, recovery, and irreversible-data questions. It requires a separate explicit contract if ever justified.

Soft delete must not be treated as permission to implement purge implicitly.

## Bulk DELETE

Initial Phase 16.7B supports only `cardinality=one` DELETE.

Although Phase 16.7A introduced deterministic `all_matching` cardinality, autonomous deletion of an entire selected set is a broader destructive behavior and is not required to establish safe deletion semantics. Bulk DELETE remains deferred until there is a demonstrated product requirement and its confirmation/presentation behavior is explicit.

## Acceptance criteria

Phase 16.7B is complete when deterministic tests prove at least:

1. the canonical schema accepts optional boolean `deleted` lifecycle metadata without requiring existing active notes to be rewritten;
2. notes without `deleted` remain active;
3. one resolved `intent=delete`, `cardinality=one` note can be revision-guarded and soft-deleted without an LLM call;
4. delete preserves stable ID, path, body, canonical metadata, properties, tags, and wikilinks except normal update lifecycle fields plus `deleted`;
5. deleted notes are excluded from normal exact, semantic, contextual, context-retrieval, and bulk-selection paths;
6. derived index rebuilds omit deleted notes;
7. stale derived indexes cannot cause current deleted Markdown to be returned or selected as active knowledge;
8. persistence duplicate-ID protection still sees deleted notes so a stable ID cannot be duplicated;
9. an implicit CREATE with one exact deleted name/alias collision fails closed for later clarification rather than silently creating a second identity;
10. deleted identity collision checking uses exact deterministic evidence only, not semantic similarity or another LLM call;
11. an explicitly requested new entity is not permanently forbidden merely because a deleted note has the same human-readable name;
12. existing backlinks/wikilinks in other Markdown files are not rewritten;
13. restore, purge, bulk DELETE, and frontend rendering are not accidentally implemented as part of this phase;
14. full deterministic Odyssey verification passes.

## Out of scope

- hard delete / physical file removal;
- automatic backlink or inbound-link rewriting;
- replacing stored links with `deleted` text;
- restore execution;
- purge execution;
- bulk `all_matching` DELETE;
- semantic search over deleted notes for duplicate prevention;
- deleted-note browsing UI;
- frontend rendering implementation;
- general HITL/application orchestration;
- Phase 17 pending-work persistence;
- n8n integration.

## Open decisions

None required before implementation of the bounded Phase 16.7B slice. Exact public class/function names and small internal placement choices remain implementation details as long as the lifecycle and fail-closed boundaries above are preserved.

## Architecture challenge

**PROCEED.**

The originally proposed soft-delete direction remains the simplest safe behavior once two boundaries are made explicit: deleting one note must not trigger broad backlink rewrites, and deleted identities must not become ordinary active candidates. Preserving the Markdown note with `deleted: true` keeps history/recovery simple. A narrow exact-only deleted-identity check before an otherwise implicit CREATE prevents accidental duplicate identities without building a restore engine or semantically searching deleted knowledge. Frontend strike-through/deleted presentation is useful later but belongs to presentation rather than authoritative Markdown mutation.
