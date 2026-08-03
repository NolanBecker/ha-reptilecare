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
> This first release is an architectural foundation. It creates a single
> ReptileCare config entry but does not yet expose entities or pet-management
> features.

## Features

The current foundation provides:

- UI configuration through Home Assistant's config flow
- Safe setup, reload, and unload behavior
- An event-driven `DataUpdateCoordinator` with no periodic polling
- Immutable event and reptile domain models
- A versioned species-profile domain model and built-in profile registry
- Versioned persistent CareEvent history backed by Home Assistant storage
- Reusable timeline queries for chronological history and filtering
- Downloadable diagnostics containing non-sensitive scaffold metadata

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

The `CareEventStore` protocol keeps persistence behind a narrow boundary, and the
canonical `CareEventType` enum provides a stable vocabulary for future feature
modules. No feeding schedules, care projections, or Home Assistant entities are
implemented at this milestone.

The product architecture will build from Reptiles to CarePlans, then CareTasks.
Completing a CareTask records an immutable CareEvent; Timeline and Coordinator
layers derive the information exposed to Home Assistant. CareEvents are the
historical audit log, not the primary user interaction.

## Project documentation

- [Vision](VISION.md) — mission, philosophy, long-term direction, and non-goals
- [Roadmap](docs/ROADMAP.md) — committed development phases and future ideas
- [Architecture](docs/ARCHITECTURE.md) — domain boundaries and data flow
- [Core domain design proposal](docs/CORE_DOMAIN_DESIGN.md) — implementation-ready
  boundaries for profiles, plans, tasks, outcomes, events, and workflows
- [Species profiles](docs/SPECIES_PROFILES.md) — profile schema, validation,
  sourcing policy, and compatibility rules
- [UX principles](docs/UX_PRINCIPLES.md) — standards for a calm, care-first
  experience
- [Development workflow](DEVELOPMENT.md) — GitHub Issues, milestones, labels,
  project board, and pull request lifecycle
- [Contributing](docs/CONTRIBUTING.md) — branch workflow, quality requirements,
  and pull request expectations
- [ReptileCare Roadmap project](https://github.com/users/NolanBecker/projects/1)
  — live Kanban planning for committed work

## Roadmap summary

- Maintain the Home Assistant lifecycle and event/storage foundation
- Add multi-reptile profile management
- Define CarePlans and generate user-facing CareTasks
- Expose stable Home Assistant services
- Build reusable dashboard cards and the future ReptileCare Center
- Add actionable notifications and derived statistics
- Support structured health observations, photos, and growth tracking

Pixel, a Gargoyle Gecko, is the first development reptile and will guide early
use cases. ReptileCare is intentionally designed to support many individual
reptiles and reptile species in future releases. See the full
[project roadmap](docs/ROADMAP.md) for the planned sequence.

## License

ReptileCare is licensed under the [MIT License](LICENSE).
