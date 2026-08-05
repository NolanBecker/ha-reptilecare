# Entities

ReptileCare exposes a small per-reptile entity layer for dashboards and
automations. These entities are read-only projections over existing
repositories, `Timeline`, and due-state logic. They do not execute workflows,
write storage, or create one entity per `CareTask`.

## Reptile Device Model

Each reptile is represented as one Home Assistant device with:

- identifier: `(reptilecare, reptile_id)`
- name: current `display_name`
- manufacturer: `ReptileCare`
- model: referenced `SpeciesProfile.display_name` when available

Device identity is based on `reptile_id`. Changing `display_name` or `slug`
updates presentation only; it does not create a new device or new entity unique
IDs.

Disabled reptiles keep their existing entities and device identity. The current
policy is:

- historical data remains intact
- entity unique IDs remain stable
- entity state becomes unavailable while the reptile is disabled
- re-enabling restores the same entities

## Entities Per Reptile

### Sensors

`pending_tasks`

- state: actionable pending task count
- attributes:
  - `next_due`
  - `due_count`
  - `overdue_count`
  - `upcoming_count`
  - `snoozed_count`
  - bounded `task_ids`

`next_task`

- state: display name of the next actionable task
- state is unknown when no actionable task exists
- tie-breaking order:
  - earliest `due_at`
  - higher priority
  - lexical `task_id`
- attributes:
  - `task_id`
  - `task_template_id`
  - `care_plan_id`
  - `due_at`
  - `timing_state`
  - `priority`
  - `generation_reason`

`last_event`

- state: compact event label such as `Feeding` or `Health Note`
- state is unknown when no event exists yet
- attributes:
  - `event_id`
  - `event_type`
  - `timestamp`
  - `outcome_id`
  - `task_id`
  - `care_plan_id`
  - `source`

### Binary Sensors

`care_due`

- on when at least one actionable task is currently due

`overdue_care`

- on when at least one actionable task is overdue

`pending_care`

- on when any actionable pending task exists

These binary sensors reuse the same projection counts as the sensors. They do
not implement a second care-status algorithm.

### Buttons

`generate_tasks`

- generates missing tasks for the reptile through the production
  `CareTaskGenerator`
- uses the normal default horizon
- preserves generation idempotency
- refreshes entity projections after completion

ReptileCare does not add a preview-generation button because the useful preview
result is already available through the `preview_task_generation` response
service.

## Dynamic Entity Creation

Reptiles created after integration setup are discovered dynamically without a
Home Assistant restart. The entity platforms subscribe to a runtime update
signal that is emitted after:

- reptile create, update, enable, and disable
- care-plan create, update, enable, and disable
- task generation
- task resolution
- manual event logging

This keeps entity state aligned with the existing domain and application
services without adding polling or direct storage reloads in entity code.

## Why CareTasks Are Not Entities

ReptileCare does not create one entity per `CareTask` because that would cause:

- entity-registry churn
- large recorder volume
- unstable dashboard structure
- duplicated task and workflow state in Home Assistant presentation code

The stable entity layer is intentionally compact. Full task and event history
remains available through the Home Assistant query services.

## Example Entity IDs

Generated entity IDs vary with Home Assistant naming rules and user
customization, but examples may look like:

- `sensor.pixel_pending_care_tasks`
- `sensor.pixel_next_care_task`
- `sensor.pixel_last_care_event`
- `binary_sensor.pixel_care_due`
- `binary_sensor.pixel_overdue_care`
- `binary_sensor.pixel_pending_care`
- `button.pixel_generate_tasks`
