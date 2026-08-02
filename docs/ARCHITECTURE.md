# Architecture

LizardCare is a local-first Home Assistant integration built around domain
models, immutable history, and derived state. The architecture separates what a
reptile needs, what a user does, what the system records, and how Home Assistant
presents the result.

## Domain flow

```text
Reptile
   ↓
Care Plans
   ↓
Care Tasks
   ↓
Events
   ↓
Timeline
   ↓
Coordinator
   ↓
Home Assistant Entities
```

This is a dependency direction, not merely a screen flow. Each layer has a
distinct responsibility and should not absorb the concerns of the layer above
or below it.

## Reptile

A **Reptile** represents one animal and its durable identity. Display names can
change; identifiers must remain stable so plans, tasks, and history continue to
refer to the same animal.

The model holds descriptive profile information such as species, morph, hatch
date, sex, and notes. It does not store derived care state such as “last fed” or
“cleaning overdue.”

## Care Plans

A **Care Plan** expresses intended care for a reptile. It answers questions such
as what kind of care is expected, how recurrence works, and when the plan is
active.

Plans are definitions, not history. Revising a plan changes future expectations
without rewriting what happened in the past. Plans should remain independent of
Home Assistant entity state so the same domain rules can support dashboards,
services, notifications, and tests.

## Care Tasks

A **Care Task** is a concrete action presented to the user. Tasks are derived
from Care Plans and relevant history, although future versions may also support
ad hoc tasks.

Care Tasks are LizardCare’s primary user interaction. A keeper completes,
defers, dismisses, or reviews a task; they should not need to create raw Events
or understand the event engine. Completing a Care Task records the appropriate
Event and allows the system to derive the next state.

## Events

An **Event** is an immutable fact in the historical audit log. Every event has a
UUID, reptile identifier, timezone-aware UTC timestamp, canonical event type,
and flexible metadata.

Events describe what was recorded, not what should happen next. Examples
include a feeding, food removal, spot clean, deep clean, weight measurement,
shed, health note, or photograph.

### Why immutable events

Immutable events provide several important properties:

- **Auditability:** the current answer can be traced to recorded facts.
- **Consistency:** there is one source of truth rather than duplicated “last”
  fields that can disagree with history.
- **Reinterpretation:** improved projection logic can operate on existing
  history without rewriting stored state.
- **Extensibility:** new features can consume earlier events without changing
  the event engine’s core contract.
- **Recovery:** state can be rebuilt after restart from persisted history.

Corrections should eventually be modeled explicitly rather than silently
mutating historical records. The correction policy is intentionally deferred
until editing workflows are designed.

## Event Store

The `EventStore` protocol is the persistence boundary. Runtime code depends on
the protocol rather than Home Assistant’s storage implementation.

The current `HomeAssistantEventStore` uses Home Assistant’s versioned `Store`
helper. It loads automatically during config-entry setup and saves after each
successful append. It provides deterministic ordering, duplicate UUID
protection, serialized writes, migration hooks, and graceful recovery from
malformed data.

Storage records use JSON-compatible values. Deserialization reconstructs typed
domain objects before history reaches the Timeline.

## Timeline

The **Timeline** is the read-only query layer over ordered Events. It centralizes
chronological ordering and common filters so future features do not repeatedly
implement subtly different history logic.

The Timeline can return all Events, find the latest Event, find the latest Event
of a type, filter by reptile, select a time interval, and count matching Events.
It does not decide when a reptile should be fed or whether a Care Task is due.
Those projections belong to future Care Plan and Care Task layers.

Keeping Timeline separate from storage also makes query behavior deterministic
and easy to test without filesystem or Home Assistant dependencies.

## Coordinator

The `LizardCareCoordinator` owns the Event Store and current Timeline. On
startup it builds a lightweight snapshot from persisted history. When future
feature modules publish a new snapshot, the coordinator updates the Timeline
before notifying listeners.

The coordinator is event-driven and has no polling interval. Future Home
Assistant entities should consume coordinator data and Timeline queries rather
than access persistence directly.

## Home Assistant entities

Entities are presentation and automation adapters at the outer edge of the
system. They should expose stable domain results to Home Assistant while keeping
business rules in the domain layers.

An entity may display today’s next Care Task or derived recent-care information,
but it should not calculate those answers independently or persist its own copy
of them. This keeps dashboards, services, and notifications consistent.

No entities are implemented in the current foundation.

## Why state is derived

Directly storing values such as `last_feeding`, `last_cleaning`, or
`food_present` creates multiple sources of truth. A changed or removed record
can leave those fields stale, and new logic cannot reliably reconstruct how the
answer was reached.

LizardCare instead derives state from ordered Events, interpreted in the
context of a Reptile and its Care Plans. Derived state may be cached for
performance in the future, but any cache must be disposable and reproducible
from authoritative history.

## Architectural boundaries

- Domain logic must not depend on dashboard layout.
- Entities and services must not write storage records directly.
- Care Plans define intent; they do not represent completion.
- Care Tasks represent actionable work; they are not the audit log.
- Events record facts; they do not prescribe future care.
- Timeline queries history; it does not implement husbandry policy.
- Automation may capture context quietly, but it must preserve clear ownership
  of recorded data.

Changes to these boundaries affect the long-term compatibility of the project
and should be discussed before implementation.
