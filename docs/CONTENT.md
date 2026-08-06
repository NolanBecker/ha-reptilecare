# Content

ReptileCare now treats built-in husbandry data as a separate content layer that
can evolve independently from the execution engine.

## Philosophy

ReptileCare is now:

```text
Engine
  +
Content
```

- The engine executes workflows, generates tasks, resolves tasks, and records
  immutable history.
- The content layer describes reusable species data and recommended care.

## Current structure

Built-in content lives under `custom_components/reptilecare/content/`:

```text
content/
  care_plans/
  species/
```

The architecture also reserves room for future content families such as:

- `task_templates/`
- `workflow_graphs/`
- `future/`

## Species packages

Each species lives in its own YAML file.

Example:

```text
content/species/gargoyle_gecko.yaml
```

Current authoritative fields:

- `species_id`
- `display_name`
- `scientific_name`
- `category`
- `description`
- `aliases`
- `environmental_targets`
- `recommended_care_plan_ids`
- `default_task_template_ids`

Reserved for future expansion:

- richer husbandry metadata
- localized care guidance
- community package metadata
- external documentation references
- import/export metadata

## Care plan content

Recommended care plans are also data-driven.

Each packaged care-plan definition includes:

- stable `content_id`
- display name
- reusable `task_template_id`
- reusable `workflow_id`
- schedule intent
- priority

During onboarding or later management flows, these built-in care-plan
definitions are converted into keeper-owned `CarePlan` records for a specific
reptile.

## Built-in library

The first bundled species catalog includes:

- Gargoyle Gecko
- Crested Gecko
- Leopard Gecko
- Ball Python
- Corn Snake

These packages include placeholder husbandry values intended to make first-run
setup useful today while leaving room for future expert-reviewed expansion.

## Registry behavior

`BuiltinContentLoader`:

- discovers packaged YAML files
- validates schema structure
- loads species and care-plan registries
- skips malformed items with warnings
- keeps the domain layer free of Home Assistant imports

The runtime exposes the validated content bundle so onboarding, options flow,
diagnostics, and future UI layers can reuse the same catalog.

## Future compatibility

This content architecture is designed so future releases can add:

- community species packages
- additional recommended care packs
- localized content
- versioned content migrations
- optional workflow and task-template packages

without redesigning CareEngine or changing reptile history semantics.
