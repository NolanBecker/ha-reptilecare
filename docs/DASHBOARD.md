# Dashboard Examples

ReptileCare is designed to enhance an existing reptile dashboard, not replace
it.

Most keepers already have enclosure-focused cards for cameras, temperature,
humidity, lighting, misting, and history graphs. ReptileCare adds care
management to that environment so the dashboard can answer one practical
question:

> What does this reptile need today?

The example layouts in [`examples/dashboard/`](../examples/dashboard/) use only
standard Home Assistant Lovelace cards. They are modular, mobile-friendly, and
safe to copy into an existing dashboard one section at a time.

## Reptile Identity In Dashboards

Replace every example entity ID with your own generated IDs.

Example ReptileCare entities for Pixel might look like:

- `sensor.pixel_pending_care_tasks`
- `sensor.pixel_next_care_task`
- `sensor.pixel_last_care_event`
- `binary_sensor.pixel_care_due`
- `binary_sensor.pixel_overdue_care`
- `binary_sensor.pixel_pending_care`
- `button.pixel_generate_tasks`

Environmental entities in the examples are placeholders outside ReptileCare,
such as:

- `camera.pixel_enclosure`
- `sensor.pixel_temperature`
- `sensor.pixel_humidity`

ReptileCare does not create or manage those environmental entities.

## Recommended Layout

The recommended order is:

1. Reptile summary
2. Today's Care
3. Next Care Task
4. Current care status
5. Recent activity
6. Existing environmental sensors and graphs
7. Advanced management actions or instructions

That order keeps the dashboard glanceable on both desktop and mobile while
preserving room for environmental cards the user already relies on.

## Reptile Overview

Use a compact top section that combines:

- reptile name
- species label
- pending task count
- overdue status
- next task
- last care event

Current limitation:

- ReptileCare does not expose a separate species entity today.
- If you want species visible on the dashboard, include it as static Markdown
  text or as part of the card title until a richer dashboard surface exists.

The overview should not duplicate the same state across multiple cards. One
name/species block plus a few high-signal tiles is enough.

## Today's Care

This section should make current care urgency obvious.

Show:

- pending care count
- whether care is due
- whether anything is overdue
- next task
- a Generate Tasks action

Recommended dependencies:

- `sensor.<reptile>_pending_care_tasks`
- `sensor.<reptile>_next_care_task`
- `binary_sensor.<reptile>_care_due`
- `binary_sensor.<reptile>_overdue_care`
- `button.<reptile>_generate_tasks`

Use the built-in button entity for task generation rather than calling the
service manually from the dashboard. That keeps the example aligned with the
public entity layer.

Current limitations:

- ReptileCare does not create one entity per `CareTask`.
- Standard Lovelace cannot yet render a dynamic actionable task list from
  `CareTask` records alone.
- Standard Lovelace also cannot present a polished task-resolution flow for an
  arbitrary task ID yet.

For richer task inspection or manual resolution today, use:

- `reptilecare.get_tasks`
- `reptilecare.resolve_task`

from **Developer Tools** or from your own automations and scripts.

## Recent Activity

Recent activity should stay compact.

Use:

- `sensor.<reptile>_last_care_event`
- a short Markdown note that explains how to query fuller history with
  `reptilecare.get_timeline`

Do not duplicate or store full event history in entity attributes. ReptileCare
intentionally keeps entity attributes small and recorder-friendly.

## Pixel Example

The full Pixel example combines:

- enclosure camera placeholder
- temperature placeholder
- humidity placeholder
- history graph placeholder
- ReptileCare overview
- Today's Care
- recent activity

Those environmental placeholders are generic examples only. Replace them with
your own camera and sensor entity IDs.

## Mobile Guidance

The example YAML favors vertical stacking and shallow grids so it works well on
phones.

Recommended mobile behavior:

- keep headings short
- prefer one or two columns at most
- avoid dense attribute-only cards
- keep tap targets large
- keep status cards near the top
- place action buttons close to the next-task summary

For desktop dashboards, the same sections can be placed in wider grids, but the
core examples intentionally remain mobile-safe first.

## Optional Enhancements

These are optional Home Assistant-only enhancements that work without changing
ReptileCare's public API:

- conditional cards when `binary_sensor.<reptile>_overdue_care` is `on`
- visibility rules to hide low-value cards when no tasks are pending
- Markdown summaries that explain current limitations or next steps
- navigation buttons to the user's preferred dashboard or admin area

If you mention `browser_mod` at all, treat it as an optional community add-on,
not a requirement.

## Dashboard Philosophy

Use these principles when adapting the examples:

- enhance existing dashboards rather than replace them
- daily care should require as few taps as possible
- care status should be glanceable
- overdue items should be visually obvious
- detailed history stays in services or the future Care Center
- entity attributes must remain small
- environmental entities remain user-configured

## Files

The example files are:

- [`examples/dashboard/reptile_overview.yaml`](../examples/dashboard/reptile_overview.yaml)
- [`examples/dashboard/todays_care.yaml`](../examples/dashboard/todays_care.yaml)
- [`examples/dashboard/recent_activity.yaml`](../examples/dashboard/recent_activity.yaml)
- [`examples/dashboard/full_pixel_dashboard.yaml`](../examples/dashboard/full_pixel_dashboard.yaml)

