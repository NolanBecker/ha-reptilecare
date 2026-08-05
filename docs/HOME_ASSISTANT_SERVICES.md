# Home Assistant Services

ReptileCare now exposes a small Home Assistant service API. These services are
adapters over the existing repositories, `CareTaskGenerator`, `CareEngine`, and
event store. They do not write storage directly and they do not reproduce
workflow or scheduling logic in the Home Assistant layer.

## Identity

Reptiles support two external identifiers:

- `reptile_id`: the canonical UUID used internally across repositories, tasks,
  plans, and events
- `slug`: an optional stable automation identifier such as `pixel`

Services that target a reptile accept exactly one of `reptile_id` or `slug`.
`display_name` is never treated as a stable identifier.

The entity layer follows the same rule: reptile devices and entity unique IDs
use `reptile_id`, not `slug` or `display_name`.

## Key Services

### `reptilecare.create_reptile`

```yaml
service: reptilecare.create_reptile
data:
  display_name: Pixel
  slug: pixel
  species_profile_id: builtin:gargoyle_gecko
```

### `reptilecare.create_care_plan`

```yaml
service: reptilecare.create_care_plan
data:
  slug: pixel
  task_template_id: builtin:feed_fruit
  workflow_id: builtin:feeding_cycle
  display_name: Feed Fruit
  schedule:
    schedule_type: interval
    every: 2
    unit: days
```

### `reptilecare.generate_tasks`

```yaml
service: reptilecare.generate_tasks
data:
  slug: pixel
  horizon_duration:
    days: 2
```

Returns:

- `created_task_ids`
- `existing_task_ids`
- `skipped_plan_ids`
- `warnings`
- `errors`

### `reptilecare.preview_task_generation`

Runs the same scheduling and validation path as `generate_tasks` without
writing to repositories.

Returns:

- `would_create`
- `already_exists`
- `skipped`
- `warnings`

### `reptilecare.resolve_task`

```yaml
service: reptilecare.resolve_task
data:
  task_id: 223e4567-e89b-12d3-a456-426614174000
  action: complete
  outcome_id: ate_normally
  outcome_metadata:
    food_used: papaya
    quantity: 30
  notes: Ate normally
  environmental_context:
    temperature_f: 78
```

Returns:

- `task`
- `care_event`
- `created_follow_up_tasks`
- `existing_follow_up_tasks`
- `workflow_completed`
- `replayed_existing_result`
- `warnings`

Actor attribution uses the Home Assistant user ID when one exists. Automation
calls may omit an actor, but the source remains `home_assistant_service`.

### `reptilecare.log_event`

```yaml
service: reptilecare.log_event
data:
  slug: pixel
  event_type: health_note
  context:
    observation: Alert and active
  notes: Observed normal behavior
```

### `reptilecare.get_tasks`

Returns serialized tasks with derived `due_state` values. Supported filters:

- `reptile_id` or `slug`
- `status`
- `due_state`
- `care_plan_id`
- `due_before`
- `due_after`
- `include_terminal`
- `include_details`
- `limit`

When `include_details: true` is supplied, each task also includes:

- `presentation`
  - `title`
  - `description`
  - `icon`
  - `priority`
  - `care_plan_display_name`
- `completion_schema`
  - `outcomes`
  - `context_fields`

This richer response shape is intended for frontend consumers such as the
bundled Today's Care card. It keeps the card on the public service API while
still exposing dynamic outcome choices and structured completion fields from
the referenced `TaskTemplate`.

### `reptilecare.get_timeline`

Returns serialized immutable `CareEvent` records in chronological order.

### `reptilecare.system_health`

Returns a small diagnostic payload for automations and future dashboards:

- `integration_version`
- `schema_version`
- `species_profile_count`
- `reptile_count`
- `care_plan_count`
- `task_template_count`
- `workflow_graph_count`
- `pending_task_count`
- `completed_task_count`
- `care_event_count`

For dashboard-safe status summaries, prefer the per-reptile entities described
in [Entities](ENTITIES.md). Query services remain the place for richer task and
event detail, including the bundled frontend card documented in
[Frontend](FRONTEND.md) and the dashboard patterns documented in
[Dashboard examples](DASHBOARD.md).

## Common Errors

Services return Home Assistant-facing errors for cases such as:

- reptile not found
- duplicate slug
- invalid schedule
- invalid outcome
- conflicting task resolution
- invalid event type

The adapter hides storage internals while preserving clear messages about which
identifier or field failed validation.
