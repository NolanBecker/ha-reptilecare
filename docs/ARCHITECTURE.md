# Architecture

ReptileCare is a local-first Home Assistant integration built around domain
models, immutable history, and derived state. The architecture separates what a
reptile needs, what a user does, what the system records, and how Home Assistant
presents the result.

## Domain flow

```text
SpeciesProfile --> Reptile ----+
                               |
TaskTemplate ----------------> CarePlans --> CareTasks --> CareEvents
        |                           ^
        v                           |
 WorkflowGraphs --> future TaskWorkflowService
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

The [core domain design proposal](CORE_DOMAIN_DESIGN.md) extends these accepted
boundaries with implementation-ready recommendations for `SpeciesProfile`,
`TaskTemplate`, task outcomes, workflow-generated follow-ups, persistence, and
Home Assistant adapters. It is a proposal rather than implemented runtime
behavior.

## Reptile

A **Reptile** represents one animal and its durable identity. Display names can
change; identifiers must remain stable so plans, tasks, and history continue to
refer to the same animal.

The immutable model references one SpeciesProfile and holds keeper-owned values
such as display name, morph, dates, sex, photo reference, notes, enclosure,
enabled state, and overrides. It does not store derived care state such as
“last fed” or “cleaning overdue.”

`ReptileRepository` owns validation, lookup, and mutation of the reptile
collection behind an async persistence protocol. The Home Assistant adapter
stores reptiles in a dedicated versioned Store. Disabling is the preferred
archive operation; removing a reptile record never cascades into immutable
CareEvent history. See [Reptiles](REPTILES.md) for the complete boundary.

## Species profiles

A **SpeciesProfile** is versioned reference data containing reusable species
identity and reviewed husbandry recommendations. Recommendations do not
represent live enclosure conditions and remain separate from future Home
Assistant sensor entities. A profile is separate from a Reptile: selecting a
profile must not replace the individual animal's stable identity or silently
overwrite reptile-specific CarePlan choices.

Built-in JSON profiles are loaded through a pure-domain registry during
config-entry setup. The registry is exposed in config-entry runtime data for
future CarePlan and user-interface layers. It does not participate in
coordinator polling, event history, or Home Assistant entity mapping. See
[Species profiles](SPECIES_PROFILES.md) for its validation and sourcing policy.

`ProfileOrigin` provides a typed, serialized provenance marker. Bundled
profiles use `builtin`, which is the only currently supported source. Reserved
`community` and `user` values prepare the domain vocabulary for possible later
expansion without adding loading or management behavior today.

### Possible future evolution

The Species Profile boundary could eventually support community-maintained
profile libraries, user-created profiles, or curated **Care Packs** that group
compatible profile and care-plan recommendations. It could also represent
multiple husbandry methodologies for the same species without declaring one
universal approach. These are architectural possibilities, not committed
roadmap items, and would require explicit sourcing, trust, versioning, and
migration policies before implementation.

## Task templates

A **TaskTemplate** is an immutable reusable care-action definition. It answers
what kind of work exists, such as **Feed Fruit Mix**, **Spot Clean**,
**Medication**, or **Replace UVB**.

Task Templates do not belong to a reptile, are not scheduled, and do not
execute workflows. They define typed categories, allowed outcomes, optional
structured context fields, presentation hints, and descriptive completion
behavior placeholders for future workflow layers.

Built-in JSON templates are loaded through a pure-domain registry during
config-entry setup and exposed in config-entry runtime data beside the species
registry and reptile repository. They are intentionally outside coordinator
polling, event history, and entity projection concerns. See
[Task templates](TASK_TEMPLATES.md) for the complete boundary.

## Workflow graphs

A **WorkflowGraph** is an immutable reusable behavior definition. It answers
what should happen after a task reaches a given outcome, such as recording a
CareEvent, waiting for a delay, or describing a follow-up task creation step.

Workflow Graphs do not execute behavior. They contain node, transition,
trigger, delay, and descriptive action definitions only. A future
`TaskWorkflowService` will interpret them later.

Built-in JSON workflow graphs are loaded through `WorkflowRegistry` during
config-entry setup and exposed in runtime data beside the species and template
registries. This keeps workflow language available to future service, plan,
task, dashboard, and automation layers without coupling the graph model to Home
Assistant entities or coordinator logic.

## CarePlans

A **CarePlan** expresses intended care for a reptile. It answers questions such
as what kind of care is expected, how recurrence works, and when the plan is
active.

Plans are definitions, not history. Revising a plan changes future expectations
without rewriting what happened in the past. Plans should remain independent of
Home Assistant entity state so the same domain rules can support dashboards,
services, notifications, and tests.

## CareTasks

A **CareTask** is a concrete action presented to the user. Tasks are derived
from CarePlans and relevant history, although future versions may also support
ad hoc tasks.

CareTasks are ReptileCare’s primary user interaction. A keeper completes,
defers, dismisses, or reviews a task; they should not need to create raw CareEvents
or understand the CareEvent engine. Completing a CareTask records the appropriate
CareEvent and allows the system to derive the next state.

## CareEvents

A **CareEvent** is an immutable fact in the historical audit log. Every
CareEvent has a UUID, reptile identifier, timezone-aware UTC timestamp,
canonical event type, and flexible metadata.

CareEvents describe what was recorded, not what should happen next. Examples
include a feeding, food removal, spot clean, deep clean, weight measurement,
shed, health note, or photograph.

### Why immutable CareEvents

Immutable CareEvents provide several important properties:

- **Auditability:** the current answer can be traced to recorded facts.
- **Consistency:** there is one source of truth rather than duplicated “last”
  fields that can disagree with history.
- **Reinterpretation:** improved projection logic can operate on existing
  history without rewriting stored state.
- **Extensibility:** new features can consume earlier events without changing
  the CareEvent engine’s core contract.
- **Recovery:** state can be rebuilt after restart from persisted history.

Corrections should eventually be modeled explicitly rather than silently
mutating historical records. The correction policy is intentionally deferred
until editing workflows are designed.

## CareEventStore

The `CareEventStore` protocol is the persistence boundary. Runtime code depends on
the protocol rather than Home Assistant’s storage implementation.

The current `HomeAssistantCareEventStore` uses Home Assistant’s versioned `Store`
helper. It loads automatically during config-entry setup and saves after each
successful append. It provides deterministic ordering, duplicate UUID
protection, serialized writes, migration hooks, and graceful recovery from
malformed data.

Storage records use JSON-compatible values. Deserialization reconstructs typed
domain objects before history reaches the Timeline.

## Timeline

The **Timeline** is the read-only query layer over ordered CareEvents. It centralizes
chronological ordering and common filters so future features do not repeatedly
implement subtly different history logic.

The Timeline can return all CareEvents, find the latest CareEvent, find the latest CareEvent
of a type, filter by reptile, select a time interval, and count matching CareEvents.
It does not decide when a reptile should be fed or whether a CareTask is due.
Those projections belong to future CarePlan and CareTask layers.

Keeping Timeline separate from storage also makes query behavior deterministic
and easy to test without filesystem or Home Assistant dependencies.

## Coordinator

The `ReptileCareCoordinator` owns the CareEventStore and current Timeline. On
startup it builds a lightweight snapshot from persisted history. When future
feature modules publish a new snapshot, the coordinator updates the Timeline
before notifying listeners.

The coordinator is event-driven and has no polling interval. Future Home
Assistant entities should consume coordinator data and Timeline queries rather
than access persistence directly.

Config-entry runtime data exposes the SpeciesProfile registry, TaskTemplate
registry, WorkflowGraph registry, Reptile repository, and the coordinator's
current Timeline. The repository is not owned by the coordinator:
individual-animal persistence and event-derived projections have separate
responsibilities and lifecycles.

## Home Assistant entities

Entities are presentation and automation adapters at the outer edge of the
system. They should expose stable domain results to Home Assistant while keeping
business rules in the domain layers.

An entity may display today’s next CareTask or derived recent-care information,
but it should not calculate those answers independently or persist its own copy
of them. This keeps dashboards, services, and notifications consistent.

No entities are implemented in the current foundation.

## Why state is derived

Directly storing values such as `last_feeding`, `last_cleaning`, or
`food_present` creates multiple sources of truth. A changed or removed record
can leave those fields stale, and new logic cannot reliably reconstruct how the
answer was reached.

ReptileCare instead derives state from ordered CareEvents, interpreted in the
context of a Reptile and its CarePlans. Derived state may be cached for
performance in the future, but any cache must be disposable and reproducible
from authoritative history.

## Architectural boundaries

- Domain logic must not depend on dashboard layout.
- Entities and services must not write storage records directly.
- TaskTemplates define reusable action vocabulary; they must not hold runtime state.
- WorkflowGraphs define reusable behavior vocabulary; they must not execute runtime state changes.
- CarePlans define intent; they do not represent completion.
- CareTasks represent actionable work; they are not the audit log.
- CareEvents record facts; they do not prescribe future care.
- Timeline queries history; it does not implement husbandry policy.
- Automation may capture context quietly, but it must preserve clear ownership
  of recorded data.

Changes to these boundaries affect the long-term compatibility of the project
and should be discussed before implementation.
