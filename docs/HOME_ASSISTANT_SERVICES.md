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
- `limit`

### `reptilecare.get_timeline`

Returns serialized immutable `CareEvent` records in chronological order.

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
