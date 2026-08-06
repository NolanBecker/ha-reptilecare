# Frontend

ReptileCare now ships its first production-facing frontend module: the
**Today's Care** custom Lovelace card.

This branch establishes the browser-side structure that future frontend work
can reuse without reshuffling files or moving business logic back into cards.
It also turns **Today's Care** into a more polished, production-quality daily
interaction surface.

## Goals

The frontend layer should:

- stay thin at the card level
- consume the public Home Assistant service layer
- reuse the existing ReptileCare entity layer for friendly status and refresh
  cues
- avoid direct repository or workflow access
- reuse small frontend-side services, models, and dialogs
- remain compatible with future cards such as Timeline, Health, and Summary
  views
- feel native to Home Assistant while still reading as calm, warm, and clear
- prioritize one-handed mobile use and fast scanning

The frontend layer should not:

- write storage directly
- duplicate scheduling or workflow logic
- hardcode feeding-specific outcome handling
- bypass `reptilecare.get_tasks` or `reptilecare.resolve_task`

## Module layout

Bundled frontend files live under:

`custom_components/reptilecare/frontend/`

Current structure:

- `cards/`
  - `todays-care-card.js`
- `components/`
  - `task-list-item.js`
- `dialogs/`
  - `task-completion-dialog.js`
- `models/`
  - `todays-care-model.js`
- `services/`
  - `reptilecare-api.js`
- `styles/`
  - `reptilecare-styles.js`
- `utils/`
  - formatting and HTML helpers

The integration serves these modules as static frontend assets and registers a
single entry module with Home Assistant’s frontend runtime.

## Card lifecycle

The bundled card type is:

`custom:reptilecare-todays-care-card`

Configuration requires exactly one reptile identifier:

- `reptile_id`
- `slug`

Example:

```yaml
type: custom:reptilecare-todays-care-card
slug: pixel
title: Today's Care
```

On load, the card:

1. validates the card config
2. calls `reptilecare.get_tasks` with `include_details: true`
3. normalizes the returned task records into frontend models
4. combines those task records with existing per-reptile entity state
5. renders loading, summary, empty, error, or task-list states

## Interaction philosophy

The card is optimized to answer one question quickly:

`What does this reptile need right now?`

To do that, it emphasizes:

- a compact but informative header
- urgency-based grouping
- quick actions for simple outcomes
- minimal taps on mobile
- per-task progress feedback instead of whole-card blocking
- empty states that still feel informative rather than broken

## Header and grouping

The polished card header now surfaces:

- reptile name
- optional species label when available from existing entity state
- current pending-task count
- overdue count when relevant
- a status chip such as `All Caught Up`, `Due Today`, or `Overdue`

Tasks are grouped into:

- Overdue
- Due Now
- Upcoming Today
- Future

This keeps the most urgent work visually closest to the top of the card.

## Task display

Each task row shows:

- icon
- title
- due time
- overdue or due-state badge
- priority
- optional care-plan label
- optional short description

The card intentionally displays only actionable pending tasks.

When no tasks are actionable, the card renders a friendly clear state such as:

- `✨ Pixel is all caught up!`
- `No care is currently due.`

When overdue work exists, the card elevates that state with a warning summary
such as:

- `⚠️ Pixel needs attention`

Task rows now also use clearer urgency styling, larger tap targets, and
per-task status labels so icons are never the only state indicator.

## Quick actions

Quick actions are enabled when a task template exposes:

- three or fewer outcomes
- no required structured fields

In that case, the card renders outcome buttons directly in the task row.

Example:

- Feed Fruit Mix
  - Ate Normally
  - Ate Partially
  - Refused

Quick actions still resolve through `reptilecare.resolve_task`.

The card does not hardcode feeding outcomes. It reads the allowed outcomes from
the `completion_schema` returned by `reptilecare.get_tasks`.

If required structured fields exist, the card always uses the completion dialog
instead of rendering quick actions directly.

When quick actions are not appropriate, the card uses a single `Complete`
button that opens the dialog without requiring task-type-specific frontend
logic.

## Completion dialog

When a task has more than three outcomes or requires structured input, the card
uses the reusable completion dialog.

The dialog shows:

- task title
- due information
- dynamic outcome choices
- dynamic structured fields from the referenced `TaskTemplate`
- optional keeper notes
- cancel and complete actions

The dialog is keyboard accessible, uses the browser dialog element, and keeps
focus inside the modal while open.

Structured fields are serialized into `outcome_metadata`.
Keeper notes are sent through the `notes` field.

## Completion experience

Resolution feedback now stays scoped to the affected task:

- only the active task becomes busy
- the active task shows progress feedback
- successful completions animate task removal
- generated follow-up tasks animate in
- backend failures restore the task and show inline error feedback

The card still performs a silent reconciliation refresh after local optimistic
updates so frontend state stays aligned with the backend without feeling
laggy.

## Refresh behavior

The card refreshes when:

- it first mounts
- the user presses the card refresh button
- it completes, skips, or quick-completes a task
- related ReptileCare entities change state after task generation, resolution,
  or event logging

This keeps the card aligned with existing runtime update behavior without
adding a polling loop.

Those refreshes now originate from backend application events translated into
Home Assistant dispatcher signals and then reflected through the existing
ReptileCare entity layer.

The card does not implement a separate polling or scheduling layer.

Rapid state changes are coalesced so the card avoids redundant refresh work.

## Service contracts used by the card

The frontend relies on two existing public services:

- `reptilecare.get_tasks`
- `reptilecare.resolve_task`

`get_tasks` now supports `include_details: true`, which returns:

- `presentation`
  - title
  - description
  - icon
  - priority
  - care plan display name
- `completion_schema`
  - outcomes
  - context fields

This preserves the architectural rule that frontend code should not query
repositories directly.

The card also watches existing ReptileCare sensor, binary sensor, and button
entities for the selected reptile so it can refresh after backend-driven task
generation or resolution without duplicating state derivation rules.

## Accessibility

The polished card is designed to support:

- keyboard navigation
- visible focus rings
- screen-reader-friendly live regions
- text-based urgency labels
- sufficient touch target sizes
- reduced-motion preferences

The completion dialog continues to rely on the platform dialog element and
keeps semantic form controls for outcomes, notes, and structured fields.

## Mobile recommendations

The layout now favors narrow dashboards first:

- actions wrap instead of forcing horizontal scrolling
- task buttons stay comfortably tappable
- header metadata stacks cleanly on smaller widths
- grouped sections remain readable in single-column dashboards

Recommended Home Assistant usage:

- place the card in a single-column dashboard section on phones
- avoid placing it beside dense multi-entity grids on narrow breakpoints
- prefer one card instance per reptile for the clearest daily workflow

## Screenshots

Screenshot placeholders:

- polished header with due-state chip
- grouped overdue and due-now sections
- quick-action task row
- completion dialog on mobile

Real screenshots should be added in a future documentation pass once the UI is
captured from a live Home Assistant instance.

## Future cards

The current structure is intended to support future frontend modules such as:

- Timeline Card
- Health Card
- Reptile Summary Card
- Care Plan Editor
- ReptileCare Center

Those future modules should reuse:

- `reptilecare-api.js`
- task normalization models
- task sorting and summary helpers
- shared formatting utilities
- reusable task list and dialog components
- shared styles

## Build and validation

The shipped card is served as plain ES modules from the integration. There is
no bundling step yet.

Frontend validation currently uses:

- ESLint
- Vitest

Commands:

```bash
npm install
npm run lint:frontend
npm run test:frontend
```

Python and Home Assistant validation remain unchanged:

```bash
ruff format --check .
ruff check .
pytest
```
