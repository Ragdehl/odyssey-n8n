# Future capture-context provenance

Status: **committed future product direction; implement after the Phase 20 Odyssey Online MVP is proven, before the first location-aware application/capability needs it**

## Objective

Allow Odyssey to remember **the context in which the user supplied a fact**, without confusing that context with knowledge about the entity itself.

A request may eventually carry optional capture context such as device location. That context belongs conceptually to the request, but facts created by the request should retain enough provenance to remain independently queryable and rebuildable.

The motivating query is:

```text
"Dime todo lo que te conté cuando estaba en Mallorca en 2026."
```

This is different from asking where an entity is located. If the user writes a fact about Marta while physically in Mallorca, Mallorca describes the **capture context**, not Marta.

```text
knowledge about entity
    !=
context where user captured that knowledge
```

## Existing temporal provenance

Phase 17D already gives atomic facts request-correlated provenance and human-visible capture chronology. The durable fact locator uses the containing note plus `request_id + ordinal`, and request/Git provenance can reconstruct when Odyssey recorded the fact.

Therefore the first implementation should **reuse the existing capture-time provenance** rather than add a redundant per-fact timestamp merely for convenience.

```text
captured_at != happened_at
```

A real-world date stated by the user remains part of the fact/domain knowledge. The time Odyssey recorded the fact is capture provenance.

If future implementation evidence shows that exact machine-readable capture time cannot be rebuilt reliably enough for the required query/index path, reconsider the smallest machine timestamp then. Do not duplicate it pre-emptively.

## Future request capture context

A future Odyssey client may supply optional capture context alongside the ordinary request.

Conceptually:

```json
{
  "request": "Hoy hemos descubierto una cala genial.",
  "request_id": "web-...",
  "capture_context": {
    "location": {
      "lat": 39.57,
      "lon": 2.65,
      "accuracy_m": 35,
      "place_label": "Mallorca, España"
    }
  }
}
```

The exact transport/schema is deliberately deferred until implementation. The principles are:

- location is optional;
- the client obtains it only with the normal platform/browser permission model;
- absence or denial of permission is ordinary and must not block the request;
- latitude/longitude are the durable geometric signal when supplied;
- accuracy should be preserved when the platform supplies it;
- a human-readable place label may be stored when safely obtained, but must not replace the original coordinate signal;
- capture location is not authentication, authorization, entity identity, or semantic truth about the note subject.

Future privacy controls may deliberately reduce coordinate precision if real use shows that exact coordinates are unnecessary. Do not invent a privacy/precision policy before the first implementation contract.

## Fact-level provenance

One request may materialize several atomic facts, possibly across several notes. The request's capture location should be projected into the provenance of every fact actually created by that request.

```text
request R123
location: Mallorca
      |
      +--> note A / fact R123:0 / capture location Mallorca
      +--> note A / fact R123:1 / capture location Mallorca
      `--> note B / fact R123:2 / capture location Mallorca
```

This is deliberate duplication at the canonical fact-provenance boundary. It avoids introducing a separate authoritative request table merely to recover capture context later.

The preferred future representation is to extend the existing **hidden fact metadata adjacent to/below the fact** with the optional capture-location provenance, while keeping ordinary Markdown reading uncluttered. The exact marker syntax is deferred so it can be designed with the parser and backwards-compatibility contract.

Conceptually:

```markdown
- Descubrimos una cala que nos encantó.
  <!-- odyssey:fact request=R123 ordinal=0 capture_location=... -->
```

Do not turn `location` into a universal note frontmatter property. A note can contain facts captured in different places at different times.

## Rebuildable query index

When location/time queries become a real feature, derive a fact-level SQLite/index projection from canonical Markdown fact provenance plus the existing request/Git capture-time evidence.

Conceptually:

```text
fact_capture_index

note_id | request_id | ordinal | captured_at | lat | lon | accuracy_m | place_label
```

The exact table name/schema is implementation detail. Its architectural role is not:

```text
canonical Markdown + fact provenance
             |
             v
       rebuildable index
             |
             +--> temporal filtering
             +--> geographic filtering
             `--> later semantic retrieval/answering
```

SQLite remains derived and disposable. Rebuilding it must not lose capture location or time.

This enables cheap deterministic filtering before semantic work, for example:

```text
"todo lo que te dije en Mallorca en 2026"
        |
        +--> captured_at within 2026
        +--> capture location within/near Mallorca
        v
matching facts
        |
        `--> semantic selection / conversational answer only if useful
```

Other possible queries include:

- what I noted while I was in Palma;
- things I told Odyssey during a trip;
- facts captured near home;
- what I recorded in a place during a given date range.

Place-name queries may eventually require deterministic geocoding/place-boundary support. Do not make an LLM the geographic filter when coordinate/boundary logic can answer it deterministically.

## Placement in the roadmap

Do **not** add this to Phase 20.1, 20.2, or 20.3 merely because the browser can technically expose geolocation.

Preferred timing:

```text
Phase 20 Odyssey Online MVP proven
        |
        v
real mobile usage establishes capture-context value
        |
        v
capture-context provenance + rebuildable fact index
        |
        v
first location-aware apps/capabilities
(travel, purchases, journal, contextual reminders, etc.)
```

Implement it before the first product feature that needs queries by capture place/time. If a planned fact-level/structured analytics index already exists at that point, extend that rebuildable projection rather than creating a parallel database.

## Guardrails

- Markdown remains the canonical knowledge/provenance source.
- Location describes capture context, never the entity automatically.
- Existing `captured_at` semantics remain distinct from event/domain time.
- Do not create a canonical `request` note/type merely to hold capture context.
- Do not create an authoritative request-location database.
- Do not require location for ordinary Odyssey use.
- Do not expose location to an answer model unless the current query actually needs that evidence.
- A denied/unavailable location must degrade to normal request behavior.
- Derived indexes must be fully rebuildable.
- Exact transport fields, marker syntax, geocoding provider, precision policy, and index schema remain implementation decisions for the future architecture checkpoint.

## Future acceptance scenarios

A future implementation should prove at least:

1. one request can create several facts that retain the same optional capture location;
2. facts in one entity note may have different capture locations without changing the entity's own properties;
3. capture time remains recoverable without confusing it with a user-stated event date;
4. rebuilding the derived index from canonical provenance preserves temporal/geographic queryability;
5. a query such as `todo lo que te dije en Mallorca en 2026` can first filter deterministically by capture provenance;
6. no-location requests continue to work normally;
7. location permission/absence cannot mutate semantic meaning or authorization;
8. the implementation does not introduce a second source of truth.
