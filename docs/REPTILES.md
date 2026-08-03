# Reptiles

Reptiles are the keeper-owned runtime records at the center of ReptileCare.
They represent individual animals without embedding care scheduling, workflow,
dashboard, or Home Assistant entity concerns.

## Species Profiles and Reptiles

A `SpeciesProfile` is immutable, versioned husbandry reference data shared by
many animals. A `Reptile` is one animal and references exactly one profile by
its stable `species_profile_id`.

The distinction is deliberate:

- Species Profiles describe general species knowledge.
- Reptiles hold keeper-specific identity and configuration.
- Changing one Reptile never mutates its Species Profile.
- Future CarePlans can attach to a stable `reptile_id` independently of the
  animal's display name.

`reptile_id` is permanent. `display_name` and other descriptive fields may be
replaced by saving an updated immutable record with the same identifier.

## Keeper-owned fields

The initial `Reptile` model records display name, Species Profile identity,
morph, sex, hatch and acquisition dates, an optional photo reference, notes,
enabled state, optional enclosure identity, and overrides. A photo reference is
only an opaque string at this stage; ReptileCare does not manage photo content.

Reptiles own these values because they describe an individual animal or the
keeper's choices. Species Profiles never contain live runtime state, enclosure
assignments, media references, or per-animal preferences.

## Overrides

`ReptileOverrides` is an immutable mapping of lowercase dotted identifiers to
JSON scalar values. It is intentionally generic so later milestones can define
specific supported keys without changing the container.

An absent override inherits the applicable recommendation from the referenced
Species Profile. A present override replaces that value only for the individual
Reptile. Overrides do not copy or mutate Species Profile data, and this
foundation does not interpret override keys yet.

## Repository

`ReptileRepository` is the domain owner for the active collection. It validates
unique IDs and Species Profile references, and provides asynchronous add,
update, remove, enable, and disable operations plus synchronous lookup and
deterministically ordered listing.

The repository depends only on a small `ReptilePersistence` protocol. Tests use
an in-memory implementation, so repository rules do not require Home Assistant.
The repository validates and saves a complete replacement collection before
publishing it in memory, preventing failed writes from exposing unpersisted
state.

## Persistence

Home Assistant runtime uses `HomeAssistantReptilePersistence`, backed by a
versioned `Store` under a reptile-specific storage key. Reptiles are serialized
explicitly to JSON-compatible values and reconstructed as immutable domain
objects when the config entry loads.

Reptile storage is separate from both packaged Species Profiles and persisted
CareEvents:

```text
Packaged Species Profiles --> SpeciesProfileRegistry

Home Assistant reptile Store --> ReptileRepository

Home Assistant event Store --> Timeline --> Coordinator
```

This separation prevents repository operations from rewriting husbandry
reference data or historical events.

## Archival and deletion

Disabling a Reptile is the preferred archival strategy. A disabled animal
remains addressable, persisted, and available to future history and CarePlan
queries while being omittable from active lists.

Removal deletes only the keeper-owned Reptile record. It does not cascade to
CareEvents, which remain an immutable historical audit log keyed by the former
`reptile_id`. User-facing deletion and restoration workflows are intentionally
deferred; future interfaces should recommend disabling unless permanent record
removal is explicitly required.

## Current boundaries

This foundation does not create sample animals, CarePlans, CareTasks, services,
entities, observations, or dashboards. Pixel, a Gargoyle Gecko using
`builtin:gargoyle_gecko`, exists only in the test suite.
