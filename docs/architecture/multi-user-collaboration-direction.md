# Multi-user collaboration direction

## Status and purpose

This document preserves a **committed post-E2E product direction**. It is not an implementation contract
for the current single-user phases and must not cause speculative authentication, authorization, sync,
or storage infrastructure to be added now.

Odyssey should remain useful as a fully private single-user knowledge system. A later collaboration
layer should let users selectively turn particular knowledge into shared knowledge without forcing the
rest of their vault into a shared workspace.

The desired product shape is:

```text
private knowledge stays private
          |
          +--> user explicitly shares selected knowledge
          |
          v
one logical shared note
          |
          +--> authorized user/group A
          +--> authorized user/group B
          `--> authorized user/group C
                    |
                    v
          local replicas stay synchronized
```

This direction should be designed as infrastructure/capability beneath Odyssey applications, not
reimplemented separately by Projects, Shopping, Reminders, or other domain applications.

## 1. One logical note, multiple replicas

A shared note must not become several unrelated notes that merely happen to contain similar text.
The same stable Odyssey note identity should represent the logical note across all authorized users.

Conceptually:

```text
logical note: 8b2f...
current shared revision: 12
       /                 \
      /                   \
user A vault           user B vault
replica rev 12         replica rev 12
```

The Markdown file in each user's storage may be a local replica, but stable note identity lets Odyssey
know that both files represent the same logical knowledge item.

This is one reason stable note IDs are important independently of filenames, paths, or vault layout.
No additional multi-user fields need to be added to the canonical note schema now merely to reserve
this future behavior.

## 2. Identity, authorization, and note content are separate concerns

A future collaboration layer will need stable user identity, but note content must not itself be the
authority that grants access.

For example, Markdown such as:

```yaml
shared_with:
  - alice
```

cannot be a security boundary when users may edit their own files directly. Changing frontmatter must
not grant access to protected shared data.

The authoritative sharing model should therefore live in an authorization boundary controlled by the
collaboration service. Conceptually a grant is:

```text
principal     permission     resource
---------     ----------     --------
user:alice    write          note:8b2f...
group:home    write          note:4ac1...
user:bob      read           note:913d...
```

Markdown may later expose non-authoritative sharing hints for user experience if useful, but those hints
must never become the mechanism that enforces privacy.

## 3. Groups are a first-class future principal

Sharing should support both individual users and **groups**. This avoids requiring the owner to maintain
large per-note user lists and makes recurring collaboration understandable in product terms.

Examples:

```text
group:household
  - Edgar
  - partner

Shopping list -> household:write
Home maintenance -> household:write
School calendar -> household:read
```

```text
group:project-alpha
  - Alice
  - Bob
  - Carla

Project Alpha -> project-alpha:write
Private salary note -> no group grant
```

A useful conceptual data model is:

```text
User -----< GroupMembership >----- Group
                                   |
                                   v
                                Grant
                                   |
                                   v
                                  Note
```

A permission can therefore target a user or a group without changing the note representation.
Changing group membership should normally change effective access without rewriting the permissions of
every shared note individually.

Do not implement nested groups, organization hierarchies, inherited folder permissions, or complex role
systems until real use cases require them. The initial collaboration phase should prefer a small grant
model such as read versus write plus the minimum ownership/administration semantics needed to manage
sharing safely.

## 4. Private-first sharing rather than shared-workspace-first design

The product goal is not simply to reproduce a team wiki. Odyssey should preserve the ability to think
privately while selectively sharing useful knowledge.

Example:

```text
Edgar vault
  |
  +-- personal reflection               PRIVATE
  +-- gift idea                         PRIVATE
  +-- family shopping list -------------+--> household
  +-- boiler maintenance note ----------+--> household
  `-- Project X task --------------------+--> project-x
```

Sharing one note must not accidentally expose neighboring notes merely because they are linked.
References from a shared note to private knowledge therefore require an explicit future visibility
policy. The safe default is fail closed: a link must never make an otherwise private note readable.

Applications may provide the user-facing sharing experience, but applications should call one common
Odyssey collaboration capability rather than implementing their own user/group/sync systems.

Conceptually:

```text
Projects app ----\
Shopping app -----+--> Odyssey collaboration capability --> authorization + sync
Notes UI --------/
```

## 5. Synchronization and offline replicas

A collaboration service should coordinate revisions of shared logical notes. It does not imply that a
central server must become the source of truth for every private vault.

A simple future sync interaction is:

```text
user A local replica: revision 7
        |
        | edit + submit(base_revision=7)
        v
sync service: revision 7
        |
        | accept
        v
sync service: revision 8
        |
        `----> user B later connects
                 local revision 7
                        |
                        v
                 receive revision 8
```

The eventual storage design may retain enough canonical shared content/history on the server to provide
durable synchronization, while private local-only knowledge remains entirely outside that shared
boundary. The exact server/storage split must be decided during the multi-user phase rather than assumed
now.

## 6. Conflict detection comes before clever merging

Offline-first use means two authorized users may edit the same shared note from the same base revision.
Odyssey should detect this deterministically rather than silently choosing the last writer.

Example:

```text
server revision = 7

Edgar edits rev 7 ----> accepted ----> server rev 8
Alice edits rev 7 ----> submits base_revision=7
                                  |
                                  v
                         current revision is 8
                                  |
                                  v
                               CONFLICT
```

The first implementation should prioritize **no silent data loss**. A conflict may initially become
pending work requiring user resolution or a conservative deterministic merge where clearly safe.
More advanced structural or semantic merging can be evaluated later, but an LLM must not be used as an
unreviewed authority that discards one user's changes.

Odyssey's small, atomic knowledge units should make many conflicts simpler than collaboration over large
free-form documents, but that hypothesis must be validated with real usage.

## 7. Revision and authorship are not ownership

The collaboration design should distinguish at least these concepts:

```text
owner / sharing authority    who can manage access
permission                   who may read or write
revision author              who produced a particular change
replica                      one user's local synchronized copy
```

They must not be collapsed into a generic `user` property on the note.

An audit trail for permission changes and shared-note revisions is likely valuable, but the exact
retention/history design belongs to the future implementation phase. Existing request-correlated Git
history may inform the design without automatically becoming the network synchronization protocol.

## 8. Early validation scenarios

The first multi-user implementation should be validated with small, concrete scenarios rather than a
generic enterprise collaboration system.

### Household shopping

```text
Household group = Edgar + partner

Edgar: "Añade leche a la compra"
       |
       v
shared shopping knowledge changes
       |
       v
partner reconnects and sees milk
       |
partner marks/buys/updates it
       |
       v
Edgar receives the shared update
```

This validates group permission, disconnected users, propagation, and concurrent modification with a
real product use case.

### Selective private/shared knowledge

```text
private gift idea about partner      -> partner cannot retrieve it
shared family holiday plan           -> household can read/write
linked private budgeting reflection  -> link does not leak its content
```

This validates that collaboration does not weaken the private-memory model.

### Project group

```text
Project X group = Alice + Bob + Carla
Project X notes -> group:write
Alice leaves group
        |
        v
access changes centrally
        |
        `--> no rewrite of every Project X Markdown note required
```

This validates why groups should be a first-class authorization principal.

## 9. Deferred decisions for the real multi-user phase

The implementation phase must explicitly decide and test:

- authentication and stable user identities;
- group creation, membership, removal, and administration;
- minimal read/write/ownership permission semantics;
- authorization enforcement before retrieval as well as before writes;
- how private links/references appear inside shared knowledge;
- central shared-state persistence versus user-owned local replicas;
- revision identifiers and synchronization protocol;
- deletion/tombstone behavior across replicas;
- conflict preservation and resolution UX;
- auditability of permission changes and shared revisions;
- encryption/security guarantees and what a server operator can see;
- behavior when a user loses access while possessing an older local replica;
- compatibility with direct Obsidian/filesystem edits.

These are real security and data-model decisions and should not be guessed incrementally.

## 10. Architectural guardrails now

Until the dedicated multi-user phase:

- keep Odyssey Core and the canonical schema single-user-simple;
- preserve stable note identity independently of filenames/paths;
- do not add speculative `owner`, `users`, group, ACL, or revision fields to every Markdown note;
- do not assume one vault is globally synonymous with one logical knowledge universe;
- keep authorization separate from note content;
- design applications so they can later delegate sharing to one common collaboration capability;
- preserve private-by-default behavior;
- treat groups as a supported future authorization principal, even if the first prototype begins with
  individual grants;
- never claim multi-user privacy guarantees until the real authentication, authorization, storage, and
  sync boundaries are implemented and tested.

The collaboration layer may eventually become its own service or deployable component. That packaging
decision is secondary: the important boundary is that collaboration is shared Odyssey infrastructure,
not domain logic owned independently by each application.
