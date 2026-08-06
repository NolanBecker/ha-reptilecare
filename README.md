<p align="center">
  <img src="brand/logo.png" alt="ReptileCare" width="560">
</p>

<p align="center"><strong>Care today. Thrive tomorrow.</strong></p>

ReptileCare is a Home Assistant integration for reptile husbandry. It is being
built around an event-driven, multi-reptile architecture so care
history can grow without coupling independent features together. Its long-term
experience is centered on CareTasks: clear actions that tell keepers what each
reptile needs today.

> [!NOTE]
> ReptileCare currently provides domain, persistence, CareTask generation,
> CareEngine execution, Home Assistant services, and the first per-reptile
> entity layer, plus the first bundled Lovelace frontend card. It does not yet
> expose reptile management UI, notifications, or the future ReptileCare
> Center.

## Features

The current foundation provides:

- UI configuration through Home Assistant's config flow
- Safe setup, reload, and unload behavior
- An event-driven `DataUpdateCoordinator` with no periodic polling
- Immutable event and reptile domain models
- A versioned species-profile domain model and built-in profile registry
- A versioned task-template domain model and built-in task template registry
- A versioned workflow-graph domain model and built-in workflow graph registry
- A versioned care-plan domain model and persistent care plan repository
- A persistent CareTask model, repository, due-state projection, and startup
  generation service
- A deterministic CareEngine that resolves tasks, records CareEvents, evaluates
  workflows, and creates follow-up tasks
- A Home Assistant service adapter for reptile management, care-plan
  management, task generation and preview, task resolution, manual event
  logging, runtime health diagnostics, and read-only task and timeline queries
- Per-reptile Home Assistant devices with compact care-summary sensors, binary
  sensors, and a task-generation button
- A bundled "Today's Care" Lovelace card that loads from the integration and
  resolves tasks through the public service layer with direct quick actions,
  dynamic completion dialogs, and entity-backed refresh behavior
- A validated multi-reptile repository with immutable keeper-owned records
- Separate, versioned persistence for reptiles and CareEvent history
- Versioned persistent CareEvent history backed by Home Assistant storage
- Reusable timeline queries for chronological history and filtering
- Downloadable diagnostics containing non-sensitive runtime and entity
  projection metadata

Planned feature modules include feeding, cleaning, weight, shedding, health,
notes, photos, and environmental tracking. Schedules, reminders, dashboards,
and pet logic are intentionally outside this initial milestone.

## Installation through HACS

Until ReptileCare is listed in the default HACS catalog:

1. Open HACS in Home Assistant.
2. Select **Integrations** and open the three-dot menu.
3. Choose **Custom repositories**.
4. Add `https://github.com/NolanBecker/ha-reptilecare` with the **Integration**
   category.
5. Install **ReptileCare** and restart Home Assistant.
6. Go to **Settings → Devices & services → Add integration**, then search for
   **ReptileCare**.

## Manual installation

1. Copy `custom_components/reptilecare` into the `custom_components` directory
   in your Home Assistant configuration directory.
2. Restart Home Assistant.
3. Add **ReptileCare** from **Settings → Devices & services**.

## Development setup

Python 3.14.2 or newer is recommended.

```bash
git clone https://github.com/NolanBecker/ha-reptilecare.git
cd ha-reptilecare
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[test]"
ruff format --check .
ruff check .
pytest
```

On Windows, activate the environment with `.venv\Scripts\activate`.

## Development Workflow

ReptileCare uses short-lived feature branches and draft pull requests so work
stays reviewable and CI stays meaningful.

Recommended flow:

```text
feature branch
    ↓
draft pull request
    ↓
review
    ↓
squash merge to main
```

Pull request titles must use Conventional Commit format because the PR title
becomes the parseable commit title on `main` when squash merging. See
[Contributing](CONTRIBUTING.md) for branch naming, accepted title types, merge
guidance, and local quality expectations.

## Release Workflow

Releases are automated with Release Please.

Recommended release path:

```text
feature branch
    ↓
draft PR
    ↓
review
    ↓
merge
    ↓
Release Please creates or updates release PR
    ↓
merge release PR
    ↓
GitHub Release and tag
    ↓
HACS update
```

Release Please reads Conventional Commits on `main`, updates
`CHANGELOG.md`, bumps the project version and integration manifest version,
opens a release PR, and creates the GitHub release after that PR is merged.
The standard validation workflows remain the gate before any release is cut.

Current baseline:

- latest published release: `v0.1.2`
- future Release Please parsing starts after commit
  `9a7c45b41f95a9ab79253026ae80c61f52b3ddb9`

If Release Please reports `No user facing commits found`, the most common cause
is that no merged `feat:` or `fix:` title exists on `main` since the current
release baseline.

After the bootstrap fix merged on August 6, 2026, the first valid
`fix(release):` PR merged with squash merge should produce a patch release PR
proposing `v0.1.3`.

## Architecture

ReptileCare stores facts as immutable `CareEvent` records rather than
persisting derived care state. The event store loads and saves versioned history
through Home Assistant's storage helper. `Timeline` orders that history and
provides reusable queries, while the coordinator publishes a lightweight
snapshot and exposes the timeline to future entities:

```text
Home Assistant Store
        ↓
     Timeline
        ↓
    Coordinator
        ↓
Future Home Assistant entities
```

The `CareEventStore` and `ReptilePersistence` protocols keep persistence behind
narrow boundaries. The canonical `CareEventType` enum provides a stable
vocabulary for future feature modules.

The product architecture will build from Reptiles to CarePlans, then CareTasks.
Completing a CareTask records an immutable CareEvent; Timeline and Coordinator
layers derive the information exposed to Home Assistant. CareEvents are the
historical audit log, not the primary user interaction.

Reusable `TaskTemplate` definitions now sit between shared reference data and
future CarePlans. They describe what kind of action exists without attaching
that action to a reptile, schedule, or workflow runtime.

Reusable `WorkflowGraph` definitions now describe what follow-up behavior may
exist after a task outcome without executing that behavior yet. They are loaded
beside task templates and prepare the future `TaskWorkflowService`.

Keeper-owned `CarePlan` definitions now connect one reptile to one reusable
task template and one reusable workflow graph with descriptive schedule and
reminder configuration.

The CareTask and CareEngine foundations now generate bounded, persistent,
idempotent task occurrences from enabled CarePlans during startup, resolve
terminal CareTask outcomes into immutable CareEvents, evaluate reusable
workflow graphs, and create deterministic follow-up tasks. Home Assistant
services and the first per-reptile entity adapters sit on top of those domain
and application layers. Notifications and richer UI remain future work.

## Project documentation

- [Vision](VISION.md) — mission, philosophy, long-term direction, and non-goals
- [Roadmap](docs/ROADMAP.md) — committed development phases and future ideas
- [Architecture](docs/ARCHITECTURE.md) — domain boundaries and data flow
- [Core domain design proposal](docs/CORE_DOMAIN_DESIGN.md) — implementation-ready
  boundaries for profiles, plans, tasks, outcomes, events, and workflows
- [Species profiles](docs/SPECIES_PROFILES.md) — profile schema, validation,
  sourcing policy, and compatibility rules
- [Task templates](docs/TASK_TEMPLATES.md) — reusable care-action definitions,
  typed outcomes, context fields, and registry behavior
- [Workflow graphs](docs/WORKFLOW_GRAPHS.md) — reusable post-outcome behavior
  definitions, graph validation, and registry behavior
- [Care plans](docs/CARE_PLANS.md) — keeper-owned care intent, scheduling
  abstraction, persistence, and repository behavior
- [Care tasks](docs/CARE_TASKS.md) — generated operational work, idempotency,
  startup reconciliation, and due-state projection
- [Care engine](docs/CARE_ENGINE.md) — task resolution lifecycle, workflow
  evaluation, follow-up generation, and restart reconciliation
- [Home Assistant services](docs/HOME_ASSISTANT_SERVICES.md) — service
  contracts, identifiers, responses, and examples
- [Live updates](docs/LIVE_UPDATES.md) — application events, dispatcher
  translation, and reactive entity/frontend refresh behavior
- [Entities](docs/ENTITIES.md) — reptile devices, summary sensors, binary
  sensors, buttons, and projection behavior
- [Frontend](docs/FRONTEND.md) — bundled frontend architecture, the Today's
  Care card, dialogs, quick actions, and future card reuse
- [Dashboard examples](docs/DASHBOARD.md) — built-in Lovelace layouts for
  adding care management to an existing reptile dashboard
- [Reptiles](docs/REPTILES.md) — individual-animal ownership, overrides,
  repository behavior, persistence, and archival policy
- [UX principles](docs/UX_PRINCIPLES.md) — standards for a calm, care-first
  experience
- [Development workflow](DEVELOPMENT.md) — GitHub Issues, milestones, labels,
  project board, and pull request lifecycle
- [Contributing](CONTRIBUTING.md) — branch workflow, Conventional Commits,
  release policy, quality requirements, and pull request expectations
- [ReptileCare Roadmap project](https://github.com/users/NolanBecker/projects/1)
  — live Kanban planning for committed work

## Roadmap summary

- Maintain the Home Assistant lifecycle and event/storage foundation
- Add multi-reptile profile management
- Define CarePlans and generate user-facing CareTasks
- Expose stable Home Assistant services and first dashboard-safe entities
- Build reusable dashboard cards and the future ReptileCare Center
- Add actionable notifications and derived statistics
- Support structured health observations, photos, and growth tracking

## Dashboard examples

ReptileCare now includes reusable built-in Lovelace YAML examples for adding
care-management sections to an existing reptile dashboard.

- [Dashboard guide](docs/DASHBOARD.md)
- [Reptile overview example](examples/dashboard/reptile_overview.yaml)
- [Today's Care example](examples/dashboard/todays_care.yaml)
- [Recent activity example](examples/dashboard/recent_activity.yaml)
- [Full Pixel dashboard example](examples/dashboard/full_pixel_dashboard.yaml)

Screenshot note:

- A real dashboard screenshot will be added in a future update after the
  example layouts stabilize.

## Frontend card

ReptileCare now also ships a bundled custom Lovelace card:

- `custom:reptilecare-todays-care-card`

The card is served by the integration itself and retrieves actionable tasks
through the existing `reptilecare.get_tasks` and `reptilecare.resolve_task`
services rather than bypassing the public application API.

Backend writes now flow through a lightweight application-event layer so
services, entities, and the bundled frontend refresh without polling.

See [Frontend](docs/FRONTEND.md) for card configuration, lifecycle, empty and
overdue states, quick-action behavior, and completion-dialog behavior.

Pixel, a Gargoyle Gecko, is the first development reptile and will guide early
use cases. ReptileCare is intentionally designed to support many individual
reptiles and reptile species in future releases. See the full
[project roadmap](docs/ROADMAP.md) for the planned sequence.

## License

ReptileCare is licensed under the [MIT License](LICENSE).
